"""Information extraction service executing structured entity extraction on chunks."""
import logging
import re
from typing import List, Optional, Union
from pydantic import ValidationError

from app.ingestion.models import ChunkRecord
from app.extraction.models import ExtractedAlternative, ExtractionResult
from app.extraction.prompts import SYSTEM_EXTRACTION_PROMPT, build_extraction_user_prompt
from app.extraction.llm_client import (
    BaseLLMClient,
    get_default_llm_client,
    LLMEmptyResponseError,
    LLMError,
)


logger = logging.getLogger(__name__)

# Wording that marks a plan, promise, intention or deadline rather than something that already happened.
# Deliberately excludes bare "due"/"by <date>": "due to the migration, latency dropped" and
# "was deployed by October 15" are genuine past results.
_FUTURE_MARKERS = re.compile(
    r"\b("
    r"will|won't|shall|going to|gonna|would|should|must|needs? to|"
    r"plans? to|planned to|planning to|intends? to|intending to|expects? to|expected to|"
    r"scheduled (?:to|for)|is due|are due|due (?:on|by|in|next|this)|"
    r"to be (?:completed|done|delivered|finished|implemented)"
    r")\b",
    re.IGNORECASE,
)

# Outcome statuses that mean "not happened yet".
_NOT_YET_STATUSES = {
    "pending", "planned", "scheduled", "upcoming", "expected", "proposed",
    "in_progress", "in progress", "not_started", "not started", "todo", "to_do",
}


def is_future_commitment(text: str, status: Optional[str] = None) -> bool:
    """True if a would-be Outcome is really a plan/commitment/deadline (so it must not be an Outcome)."""
    if status and status.strip().lower() in _NOT_YET_STATUSES:
        return True
    return bool(text and _FUTURE_MARKERS.search(text))


def _normalize_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def resolve_target_alternative(
    target: Optional[str], alternatives: List[ExtractedAlternative]
) -> Optional[str]:
    """Map the model's `target_alternative` onto the exact name of one extracted alternative.

    Accepts the alternative's id, its name (ignoring case/punctuation), or an unambiguous
    containment of one name in the other. Anything that cannot be resolved to exactly one
    alternative becomes None: the target is never guessed.
    """
    if not target or not target.strip():
        return None

    for alt in alternatives:
        if alt.id == target:
            return alt.name

    wanted = _normalize_name(target)
    if not wanted:
        return None

    exact = [alt for alt in alternatives if _normalize_name(alt.name) == wanted]
    if len(exact) == 1:
        return exact[0].name
    if len(exact) > 1:
        return None

    def _is_partial_match(alt: ExtractedAlternative) -> bool:
        alt_norm = _normalize_name(alt.name)
        if len(alt_norm) < 4:
            return False
        if alt_norm in wanted:  # the alternative's full name appears inside the target
            return True
        # the target is only a fragment of the name: require at least two words so that a
        # single common word ("existing", "frontend") can never select an alternative
        return wanted in alt_norm and len(wanted.split()) >= 2

    partial = [alt for alt in alternatives if _is_partial_match(alt)]
    return partial[0].name if len(partial) == 1 else None


class ExtractionServiceError(Exception):
    """Raised when the extraction pipeline fails."""
    pass


class ExtractionValidationError(ExtractionServiceError):
    """Raised when LLM structured output fails schema validation."""
    pass


def extract_from_chunk(
    chunk: Union[ChunkRecord, dict],
    client: Optional[BaseLLMClient] = None,
) -> ExtractionResult:
    """Extract structured problems, alternatives, rationales, decisions, actions, people, and outcomes

    from a single text chunk while strictly preserving provenance.
    """
    if isinstance(chunk, ChunkRecord):
        chunk_id = chunk.chunk_id
        chunk_text = chunk.text
    elif isinstance(chunk, dict):
        chunk_id = chunk.get("chunk_id", "")
        chunk_text = chunk.get("text", "")
    else:
        raise ExtractionServiceError("Chunk must be a ChunkRecord or dictionary.")

    if not chunk_id:
        raise ExtractionServiceError("Chunk must have a valid non-empty chunk_id.")

    if not chunk_text or not chunk_text.strip():
        # Return empty extraction result for empty chunk
        return ExtractionResult(chunk_id=chunk_id)

    llm = client or get_default_llm_client()
    user_prompt = build_extraction_user_prompt(chunk_id=chunk_id, text=chunk_text)

    try:
        try:
            raw_json = llm.generate_json(
                system_prompt=SYSTEM_EXTRACTION_PROMPT,
                user_prompt=user_prompt,
            )
        except LLMEmptyResponseError:
            # The model sometimes returns nothing at all; ask once more about the SAME chunk.
            logger.warning("LLM returned an empty response for chunk %s; retrying once", chunk_id)
            try:
                raw_json = llm.generate_json(
                    system_prompt=SYSTEM_EXTRACTION_PROMPT,
                    user_prompt=user_prompt,
                )
            except LLMEmptyResponseError as retry_error:
                raise ExtractionServiceError(
                    f"The LLM returned an empty response for chunk {chunk_id} (retried once); "
                    "no entities were extracted."
                ) from retry_error
    except ExtractionServiceError:
        raise
    except LLMError as e:
        raise ExtractionServiceError(str(e)) from e
    except Exception as e:
        raise ExtractionServiceError("Unexpected error during LLM invocation") from e

    # Ensure chunk_id is present in root JSON
    if not isinstance(raw_json, dict):
        raise ExtractionValidationError(f"Expected JSON object from LLM, got {type(raw_json).__name__}")

    raw_json["chunk_id"] = chunk_id

    # Enforce chunk_id on all child entity lists to guarantee provenance integrity
    entity_keys = [
        "problems",
        "alternatives",
        "rationales",
        "decisions",
        "actions",
        "people",
        "outcomes",
    ]
    for key in entity_keys:
        items = raw_json.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    item["chunk_id"] = chunk_id

    try:
        result = ExtractionResult.model_validate(raw_json)
    except ValidationError as e:
        raise ExtractionValidationError(f"Schema validation failed on LLM output: {e}") from e

    # Quality guards. These only remove or null out unreliable output; ids, chunk_id provenance and
    # all other fields (including Action assignee/deadline/status) are left exactly as extracted.
    kept_outcomes = []
    for outcome in result.outcomes:
        if is_future_commitment(outcome.result, outcome.status):
            logger.info(
                "Dropped planned/future item from outcomes (chunk %s): %r", chunk_id, outcome.result
            )
        else:
            kept_outcomes.append(outcome)
    result.outcomes = kept_outcomes

    for rationale in result.rationales:
        resolved = resolve_target_alternative(rationale.target_alternative, result.alternatives)
        if rationale.target_alternative and resolved is None:
            logger.info(
                "Rationale target %r matches no single extracted alternative (chunk %s); left unlinked",
                rationale.target_alternative,
                chunk_id,
            )
        rationale.target_alternative = resolved

    return result

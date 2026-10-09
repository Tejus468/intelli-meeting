"""Unit tests for AI information extraction layer using mock LLM client."""
import os
import sys
from pathlib import Path
from typing import Dict, Any
import pytest

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.models import ChunkRecord
from app.extraction.models import (
    ExtractionResult,
    ExtractedProblem,
    ExtractedAlternative,
    ExtractedRationale,
    ExtractedDecision,
    ExtractedAction,
    ExtractedPerson,
    ExtractedOutcome,
)
from app.extraction.llm_client import (
    BaseLLMClient,
    OpenAICompatibleLLMClient,
    LLMConfigurationError,
    LLMResponseError,
    extract_json_from_text,
)
from app.extraction.service import (
    extract_from_chunk,
    ExtractionServiceError,
    ExtractionValidationError,
)


class MockLLMClient(BaseLLMClient):
    """Mock LLM client returning configurable canned responses."""

    def __init__(self, response: Any):
        self.response = response
        self.calls = []

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, str):
            return extract_json_from_text(self.response)
        return self.response

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if isinstance(self.response, Exception):
            raise self.response
        return str(self.response)


def test_valid_structured_extraction():
    chunk_id = "chk_test_101"
    mock_payload = {
        "chunk_id": chunk_id,
        "problems": [
            {
                "id": "prob_1",
                "chunk_id": chunk_id,
                "confidence": 0.95,
                "description": "Slow vector similarity search in current setup",
            }
        ],
        "alternatives": [
            {
                "id": "alt_1",
                "chunk_id": chunk_id,
                "confidence": 0.90,
                "name": "pgvector",
                "description": "PostgreSQL extension for vector search",
            },
            {
                "id": "alt_2",
                "chunk_id": chunk_id,
                "confidence": 0.85,
                "name": "Pinecone",
                "description": "Managed cloud vector database",
            },
        ],
        "rationales": [
            {
                "id": "rat_1",
                "chunk_id": chunk_id,
                "confidence": 0.92,
                "reason": "pgvector allows keeping relational metadata in one database",
                "stance": "supports",
                "target_alternative": "pgvector",
            }
        ],
        "decisions": [
            {
                "id": "dec_1",
                "chunk_id": chunk_id,
                "confidence": 0.98,
                "statement": "Adopt pgvector for all semantic search",
                "chosen_alternative": "pgvector",
                "status": "agreed",
            }
        ],
        "actions": [
            {
                "id": "act_1",
                "chunk_id": chunk_id,
                "confidence": 0.90,
                "task": "Set up pgvector schema migration",
                "assignee": "Alex",
                "deadline": "Friday EOD",
                "status": "pending",
            }
        ],
        "people": [
            {
                "id": "per_1",
                "chunk_id": chunk_id,
                "confidence": 0.99,
                "name": "Alex",
                "role": "Tech Lead",
            }
        ],
        "outcomes": [
            {
                "id": "out_1",
                "chunk_id": chunk_id,
                "confidence": 0.80,
                "result": "Benchmark showed 50ms latency",
                "status": "verified",
            }
        ],
    }

    mock_client = MockLLMClient(mock_payload)
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        source_id="src_01",
        text="Alex: We agreed to adopt pgvector for search because it keeps metadata unified.",
    )

    result = extract_from_chunk(chunk, client=mock_client)

    assert result.chunk_id == chunk_id
    assert len(result.problems) == 1
    assert result.problems[0].description == "Slow vector similarity search in current setup"
    assert len(result.alternatives) == 2
    assert len(result.rationales) == 1
    assert result.rationales[0].stance == "supports"
    assert len(result.decisions) == 1
    assert result.decisions[0].chosen_alternative == "pgvector"
    assert len(result.actions) == 1
    assert result.actions[0].assignee == "Alex"
    assert result.actions[0].deadline == "Friday EOD"
    assert len(result.people) == 1
    assert result.people[0].name == "Alex"
    assert len(result.outcomes) == 1


def test_empty_extraction():
    chunk_id = "chk_empty_01"
    mock_payload = {
        "chunk_id": chunk_id,
        "problems": [],
        "alternatives": [],
        "rationales": [],
        "decisions": [],
        "actions": [],
        "people": [],
        "outcomes": [],
    }

    mock_client = MockLLMClient(mock_payload)
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        source_id="src_01",
        text="Good morning everyone, let's start the call.",
    )

    result = extract_from_chunk(chunk, client=mock_client)
    assert result.chunk_id == chunk_id
    assert len(result.problems) == 0
    assert len(result.decisions) == 0
    assert len(result.actions) == 0


def test_invalid_json_handling():
    chunk_id = "chk_invalid_json"
    mock_client = MockLLMClient("This is not valid JSON string at all")
    chunk = ChunkRecord(chunk_id=chunk_id, source_id="src_01", text="Sample text")

    with pytest.raises(ExtractionServiceError) as exc_info:
        extract_from_chunk(chunk, client=mock_client)
    assert "Failed to parse LLM output as JSON" in str(exc_info.value)


def test_missing_required_fields_validation():
    chunk_id = "chk_missing_fields"
    # Missing required 'statement' field in decision
    mock_payload = {
        "chunk_id": chunk_id,
        "decisions": [
            {
                "id": "dec_1",
                "chunk_id": chunk_id,
                "confidence": 0.9,
                # 'statement' is missing
            }
        ],
    }
    mock_client = MockLLMClient(mock_payload)
    chunk = ChunkRecord(chunk_id=chunk_id, source_id="src_01", text="We decided.")

    with pytest.raises(ExtractionValidationError) as exc_info:
        extract_from_chunk(chunk, client=mock_client)
    assert "Schema validation failed" in str(exc_info.value)


def test_provenance_and_chunk_id_preservation():
    chunk_id = "chk_provenance_test"
    mock_payload = {
        "chunk_id": "wrong_chunk_id",
        "decisions": [
            {
                "id": "dec_1",
                "chunk_id": "wrong_chunk_id",
                "confidence": 0.95,
                "statement": "Decision text",
            }
        ],
        "actions": [
            {
                "id": "act_1",
                "chunk_id": "wrong_chunk_id",
                "confidence": 0.90,
                "task": "Action task",
            }
        ],
    }
    mock_client = MockLLMClient(mock_payload)
    chunk = ChunkRecord(chunk_id=chunk_id, source_id="src_01", text="Decision text")

    result = extract_from_chunk(chunk, client=mock_client)

    # Provenance enforcement must overwrite or guarantee the correct chunk_id
    assert result.chunk_id == chunk_id
    assert result.decisions[0].chunk_id == chunk_id
    assert result.actions[0].chunk_id == chunk_id


def test_confidence_validation():
    chunk_id = "chk_invalid_confidence"
    mock_payload = {
        "chunk_id": chunk_id,
        "problems": [
            {
                "id": "prob_1",
                "chunk_id": chunk_id,
                "confidence": 1.5,  # Invalid: > 1.0
                "description": "Some problem",
            }
        ],
    }
    mock_client = MockLLMClient(mock_payload)
    chunk = ChunkRecord(chunk_id=chunk_id, source_id="src_01", text="Problem text")

    with pytest.raises(ExtractionValidationError) as exc_info:
        extract_from_chunk(chunk, client=mock_client)
    assert "confidence" in str(exc_info.value)


def test_missing_api_key_configuration(monkeypatch):
    # The client falls back to settings.llm_api_key when api_key is empty, so a developer's real
    # .env key would make this test hit a live LLM. Clear the configured key to test the real
    # "no key anywhere" path, and fail loudly if any HTTP request is attempted.
    from app.core.config import settings
    from app.extraction import llm_client

    monkeypatch.setattr(settings, "llm_api_key", "")

    def no_network(*args, **kwargs):
        raise AssertionError("an HTTP request was attempted without an API key")

    monkeypatch.setattr(llm_client.httpx, "Client", no_network)

    client = OpenAICompatibleLLMClient(api_key="")
    with pytest.raises(LLMConfigurationError) as exc_info:
        client.generate_json("system", "user")
    assert "LLM API key is not configured" in str(exc_info.value)


def test_json_markdown_fence_stripping():
    raw_markdown = """```json
{
  "chunk_id": "chk_fenced",
  "problems": [],
  "alternatives": [],
  "rationales": [],
  "decisions": [],
  "actions": [],
  "people": [],
  "outcomes": []
}
```"""
    parsed = extract_json_from_text(raw_markdown)
    assert parsed["chunk_id"] == "chk_fenced"


# --- Extraction quality: rationale targets and outcomes -------------------------------------------
NEXTJS = "Rebuild frontend using Next.js"
OPTIMIZE = "Optimize existing React application"
CHUNK = "chk_quality_1"


def _quality_payload(rationales=None, outcomes=None, actions=None):
    def item(**fields):
        return {"chunk_id": CHUNK, "confidence": 0.9, **fields}

    return {
        "chunk_id": CHUNK,
        "alternatives": [
            item(id="alt_1", name=NEXTJS),
            item(id="alt_2", name=OPTIMIZE),
        ],
        "decisions": [
            item(id="dec_1", statement="We will rebuild the frontend using Next.js.", chosen_alternative=NEXTJS)
        ],
        "rationales": [item(id=f"rat_{i}", **r) for i, r in enumerate(rationales or [], 1)],
        "actions": [item(id=f"act_{i}", **a) for i, a in enumerate(actions or [], 1)],
        "outcomes": [item(id=f"out_{i}", **o) for i, o in enumerate(outcomes or [], 1)],
    }


def _extract(payload):
    return extract_from_chunk({"chunk_id": CHUNK, "text": "meeting text"}, client=MockLLMClient(payload))


def test_rationale_supporting_the_selected_alternative():
    result = _extract(_quality_payload(rationales=[
        {"reason": "Next.js gives better routing and cleaner architecture.", "stance": "supports", "target_alternative": NEXTJS}
    ]))
    assert result.rationales[0].stance == "supports"
    assert result.rationales[0].target_alternative == NEXTJS


def test_rationale_supporting_a_non_selected_alternative_is_not_moved_to_the_selected_one():
    result = _extract(_quality_payload(rationales=[
        {"reason": "Optimizing the existing application would require less development effort.",
         "stance": "supports", "target_alternative": OPTIMIZE}
    ]))
    rationale = result.rationales[0]
    assert rationale.target_alternative == OPTIMIZE
    assert rationale.target_alternative != NEXTJS
    assert rationale.stance == "supports"


def test_rationale_opposing_an_alternative():
    result = _extract(_quality_payload(rationales=[
        {"reason": "A rebuild would take longer.", "stance": "opposes", "target_alternative": NEXTJS}
    ]))
    assert result.rationales[0].stance == "opposes"
    assert result.rationales[0].target_alternative == NEXTJS


@pytest.mark.parametrize(
    "raw_target, expected",
    [
        ("alt_2", OPTIMIZE),  # by id
        ("optimize EXISTING react application.", OPTIMIZE),  # case/punctuation
        ("Next.js", NEXTJS),  # unambiguous containment
        ("Migrate to Kubernetes", None),  # matches nothing: never invented
        ("existing", None),  # too vague / ambiguous
        ("", None),
        (None, None),
    ],
)
def test_rationale_target_is_resolved_to_one_real_alternative_or_none(raw_target, expected):
    result = _extract(_quality_payload(rationales=[
        {"reason": "Some reason", "stance": "supports", "target_alternative": raw_target}
    ]))
    assert result.rationales[0].target_alternative == expected


def test_future_commitment_stays_an_action_and_is_not_an_outcome():
    result = _extract(_quality_payload(
        actions=[{"task": "Implement the new frontend", "assignee": "Bob", "deadline": "October 15", "status": "pending"}],
        outcomes=[{"result": "Bob will complete the initial implementation by October 15.", "status": "completed"}],
    ))
    assert result.outcomes == []
    action = result.actions[0]
    assert (action.task, action.assignee, action.deadline, action.status) == (
        "Implement the new frontend", "Bob", "October 15", "pending"
    )


@pytest.mark.parametrize(
    "result_text, status",
    [
        ("The new frontend was deployed successfully on October 15.", "completed"),
        ("Page load time dropped by 40% due to the migration.", "achieved"),
        ("The migration was finished by Friday.", None),
    ],
)
def test_genuine_completed_results_remain_eligible_as_outcomes(result_text, status):
    result = _extract(_quality_payload(outcomes=[{"result": result_text, "status": status}]))
    assert [o.result for o in result.outcomes] == [result_text]


@pytest.mark.parametrize(
    "text, status, expected",
    [
        ("Bob will complete the initial implementation by October 15.", "completed", True),
        ("I am going to finish the migration next week.", None, True),
        ("The team plans to evaluate usability after deployment.", None, True),
        ("The site should be live by the end of the month.", None, True),
        ("Rollout scheduled for Monday.", None, True),
        ("Anything at all", "planned", True),
        ("Anything at all", "In Progress", True),
        ("The release shipped on time.", "completed", False),
        ("Latency fell due to the new cache.", None, False),
    ],
)
def test_is_future_commitment(text, status, expected):
    from app.extraction.service import is_future_commitment

    assert is_future_commitment(text, status) is expected


def test_quality_guards_keep_provenance_and_unrelated_fields_intact():
    result = _extract(_quality_payload(
        rationales=[{"reason": "r", "stance": "supports", "target_alternative": "alt_1"}],
        outcomes=[
            {"result": "Bob will finish by Friday.", "status": "completed"},
            {"result": "The release shipped.", "status": "completed"},
        ],
    ))
    assert [o.result for o in result.outcomes] == ["The release shipped."]
    everything = (
        result.alternatives + result.rationales + result.decisions + result.outcomes
    )
    assert all(item.chunk_id == CHUNK for item in everything)
    assert result.decisions[0].chosen_alternative == NEXTJS


def test_prompt_states_the_rationale_target_and_outcome_rules():
    from app.extraction.prompts import SYSTEM_EXTRACTION_PROMPT

    assert "target_alternative" in SYSTEM_EXTRACTION_PROMPT
    assert "NOT chosen" in SYSTEM_EXTRACTION_PROMPT
    assert "NEVER Outcomes" in SYSTEM_EXTRACTION_PROMPT


# --- LLM client configuration: JSON mode and timeout -------------------------------------------
class _FakeHttpxClient:
    """Stands in for httpx.Client; records the request and replies with a canned completion."""

    calls = []
    content = '```json\n{"ok": true}\n```'

    def __init__(self, timeout=None):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        type(self).calls.append({"url": url, "json": json, "timeout": self.timeout})
        content = type(self).content

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return _Resp()


def _patched_client(monkeypatch):
    from app.extraction import llm_client

    _FakeHttpxClient.calls = []
    monkeypatch.setattr(llm_client.httpx, "Client", _FakeHttpxClient)
    return _FakeHttpxClient


def test_json_mode_sends_response_format_by_default(monkeypatch):
    fake = _patched_client(monkeypatch)
    client = OpenAICompatibleLLMClient(api_key="k", json_mode=True)
    assert client.generate_json("s", "u") == {"ok": True}
    assert fake.calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_json_mode_disabled_omits_response_format_but_still_parses_fenced_json(monkeypatch):
    fake = _patched_client(monkeypatch)
    client = OpenAICompatibleLLMClient(api_key="k", json_mode=False)
    assert client.generate_json("s", "u") == {"ok": True}
    assert "response_format" not in fake.calls[0]["json"]


def test_json_mode_and_timeout_default_from_settings(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_json_mode", False)
    monkeypatch.setattr(settings, "llm_timeout_seconds", 123.0)
    client = OpenAICompatibleLLMClient(api_key="k")
    assert client.json_mode is False
    assert client.timeout == 123.0
    assert OpenAICompatibleLLMClient(api_key="k", timeout=5).timeout == 5


def test_timeout_is_reported_as_timeout_not_connection_failure(monkeypatch):
    import httpx
    from app.extraction import llm_client
    from app.extraction.llm_client import LLMAPIError

    class _Slow(_FakeHttpxClient):
        def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm_client.httpx, "Client", _Slow)
    client = OpenAICompatibleLLMClient(api_key="k", timeout=42)
    with pytest.raises(LLMAPIError) as exc_info:
        client.generate_text("s", "u")
    assert "timed out after 42s" in str(exc_info.value)


# --- Empty / fenced LLM responses ---------------------------------------------------------------
EMPTY_CHUNK = "chk_empty_resp"
VALID_PAYLOAD_JSON = (
    '{"chunk_id": "chk_empty_resp", "problems": [], "alternatives": [], "rationales": [], '
    '"decisions": [{"id": "dec_1", "chunk_id": "chk_empty_resp", "confidence": 0.9, '
    '"statement": "Adopt PostgreSQL", "status": "agreed"}], "actions": [], "people": [], "outcomes": []}'
)


class _ScriptedHttpx:
    """httpx.Client stand-in: each POST returns the next scripted completion `content`."""

    replies = []
    requests = []

    def __init__(self, timeout=None):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        type(self).requests.append(json)
        content = type(self).replies[len(type(self).requests) - 1]

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return _Resp()


def _extract_via_real_client(monkeypatch, *replies):
    """Run extract_from_chunk through the real OpenAI-compatible client with scripted model replies."""
    from app.extraction import llm_client

    _ScriptedHttpx.replies = list(replies)
    _ScriptedHttpx.requests = []
    monkeypatch.setattr(llm_client.httpx, "Client", _ScriptedHttpx)
    client = OpenAICompatibleLLMClient(api_key="k", json_mode=False)
    chunk = ChunkRecord(chunk_id=EMPTY_CHUNK, source_id="src_1", text="We decided to adopt PostgreSQL.")
    return extract_from_chunk(chunk, client=client)


def test_valid_json_response_is_extracted_without_any_retry(monkeypatch):
    result = _extract_via_real_client(monkeypatch, VALID_PAYLOAD_JSON)

    assert [d.statement for d in result.decisions] == ["Adopt PostgreSQL"]
    assert len(_ScriptedHttpx.requests) == 1


def test_empty_first_response_is_retried_once_on_the_same_chunk(monkeypatch):
    result = _extract_via_real_client(monkeypatch, "", VALID_PAYLOAD_JSON)

    assert [d.statement for d in result.decisions] == ["Adopt PostgreSQL"]
    assert result.chunk_id == EMPTY_CHUNK
    assert len(_ScriptedHttpx.requests) == 2
    # the retry asks exactly the same question with the same configuration
    assert _ScriptedHttpx.requests[0] == _ScriptedHttpx.requests[1]


def test_whitespace_only_and_null_content_count_as_empty_and_are_retried(monkeypatch):
    result = _extract_via_real_client(monkeypatch, "  \n\t ", VALID_PAYLOAD_JSON)
    assert len(result.decisions) == 1 and len(_ScriptedHttpx.requests) == 2

    result = _extract_via_real_client(monkeypatch, None, VALID_PAYLOAD_JSON)
    assert len(result.decisions) == 1 and len(_ScriptedHttpx.requests) == 2


def test_empty_response_twice_raises_a_clear_error_and_invents_nothing(monkeypatch):
    with pytest.raises(ExtractionServiceError) as exc_info:
        _extract_via_real_client(monkeypatch, "", "   ")

    message = str(exc_info.value)
    assert "empty response" in message
    assert EMPTY_CHUNK in message
    assert "retried once" in message
    assert "Failed to parse LLM output as JSON" not in message
    assert len(_ScriptedHttpx.requests) == 2  # exactly one retry, never more


def test_fenced_json_response_is_parsed_without_a_retry(monkeypatch):
    fenced = "```json\n" + VALID_PAYLOAD_JSON + "\n```"
    result = _extract_via_real_client(monkeypatch, fenced)

    assert len(result.decisions) == 1
    assert len(_ScriptedHttpx.requests) == 1


def test_unclosed_fence_from_a_truncated_reply_is_still_parsed(monkeypatch):
    result = _extract_via_real_client(monkeypatch, "```json\n" + VALID_PAYLOAD_JSON)

    assert len(result.decisions) == 1
    assert len(_ScriptedHttpx.requests) == 1


def test_fenced_text_surrounded_by_prose_is_parsed(monkeypatch):
    reply = "Here is the extraction:\n```json\n" + VALID_PAYLOAD_JSON + "\n```\nHope that helps."
    assert len(_extract_via_real_client(monkeypatch, reply).decisions) == 1


def test_an_empty_fenced_block_is_treated_as_empty_and_retried(monkeypatch):
    result = _extract_via_real_client(monkeypatch, "```json\n```", VALID_PAYLOAD_JSON)

    assert len(result.decisions) == 1
    assert len(_ScriptedHttpx.requests) == 2


def test_non_empty_malformed_json_is_not_retried_and_keeps_its_existing_error(monkeypatch):
    with pytest.raises(ExtractionServiceError) as exc_info:
        _extract_via_real_client(monkeypatch, "this is not json", VALID_PAYLOAD_JSON)

    assert "Failed to parse LLM output as JSON" in str(exc_info.value)
    assert len(_ScriptedHttpx.requests) == 1


@pytest.mark.parametrize("raw", ["", "   \n\t", None, "```json\n```", "```\n   \n```"])
def test_extract_json_from_text_flags_empty_input_distinctly(raw):
    from app.extraction.llm_client import LLMEmptyResponseError

    with pytest.raises(LLMEmptyResponseError) as exc_info:
        extract_json_from_text(raw)
    assert "empty response" in str(exc_info.value)
    assert isinstance(exc_info.value, LLMResponseError)  # existing handlers still catch it


def test_other_llm_errors_are_not_retried():
    from app.extraction.llm_client import LLMAPIError

    client = MockLLMClient(LLMAPIError("LLM API returned HTTP 500"))
    chunk = ChunkRecord(chunk_id=EMPTY_CHUNK, source_id="src_1", text="text")

    with pytest.raises(ExtractionServiceError):
        extract_from_chunk(chunk, client=client)
    assert len(client.calls) == 1


if __name__ == "__main__":
    test_valid_structured_extraction()
    test_empty_extraction()
    test_invalid_json_handling()
    test_missing_required_fields_validation()
    test_provenance_and_chunk_id_preservation()
    test_confidence_validation()
    test_missing_api_key_configuration()
    test_json_markdown_fence_stripping()
    print("All extraction unit tests passed successfully!")

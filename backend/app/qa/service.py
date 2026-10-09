"""Evidence-backed Question Answering service integrating hybrid retrieval and LLM synthesis."""
from typing import List, Optional, Dict, Any, Tuple
from neo4j import Driver

from app.embeddings.model import BaseEmbeddingModel
from app.extraction.llm_client import BaseLLMClient, get_default_llm_client, LLMError
from app.retrieval.models import EvidenceItem, HybridSearchResult
from app.retrieval.hybrid import hybrid_search
from app.retrieval.graph_retriever import retrieve_decision_context
from app.qa.models import SourceReference, AnswerResponse
from app.qa.prompts import QA_SYSTEM_PROMPT, build_qa_user_prompt


class QAServiceError(Exception):
    """Base exception for Q&A pipeline errors."""
    pass


class QARetrievalError(QAServiceError):
    """Raised when retrieval fails during Q&A."""
    pass


class QALLMError(QAServiceError):
    """Raised when LLM answer generation fails."""
    pass


def extract_source_references(evidence: List[EvidenceItem]) -> List[SourceReference]:
    """Extract and deduplicate source and chunk references from retrieved evidence items."""
    ref_map: Dict[Tuple[Optional[str], Optional[str]], SourceReference] = {}

    for item in evidence:
        s_id = item.source_id
        c_id = item.chunk_id
        # Key on (source_id, chunk_id) to avoid duplicate citations for the same chunk
        key = (s_id, c_id)

        meta = item.metadata or {}
        score = round(float(item.score), 4)

        if key in ref_map:
            # Update score if higher relevance found
            if score > ref_map[key].relevance_score:
                ref_map[key].relevance_score = score
        else:
            ref_map[key] = SourceReference(
                source_id=s_id,
                chunk_id=c_id,
                title=meta.get("title"),
                page=meta.get("page"),
                speaker=meta.get("speaker"),
                start_ts=meta.get("start_ts"),
                end_ts=meta.get("end_ts"),
                relevance_score=score,
            )

    # Sort citations in descending order of relevance score
    sources = list(ref_map.values())
    sources.sort(key=lambda s: s.relevance_score, reverse=True)
    return sources


def answer_question(
    question: str,
    top_k: int = 5,
    model: Optional[BaseEmbeddingModel] = None,
    driver: Optional[Driver] = None,
    llm_client: Optional[BaseLLMClient] = None,
) -> AnswerResponse:
    """Answer a user question grounded exclusively in retrieved hybrid evidence."""
    if not question or not question.strip():
        raise ValueError("question must not be empty or whitespace")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    clean_question = question.strip()

    # 1. Run Hybrid Retrieval
    try:
        search_result: HybridSearchResult = hybrid_search(
            query=clean_question,
            top_k=top_k,
            model=model,
            driver=driver,
        )
    except Exception as e:
        raise QARetrievalError(f"Retrieval failed for question: {e}") from e

    evidence = search_result.evidence

    # 2. Handle Zero Evidence Case
    if not evidence:
        return AnswerResponse(
            question=clean_question,
            answer="I could not find any relevant evidence in the ingested meeting transcripts or documents to answer this question.",
            sources=[],
            evidence_count=0,
        )

    # 3. Build Prompt & Invoke LLM
    llm = llm_client or get_default_llm_client()
    # Structured view (alternatives, rationale targets, selected option) of the decisions behind the evidence
    decision_context = retrieve_decision_context(
        [item.chunk_id for item in evidence if item.chunk_id], driver=driver
    )
    user_prompt = build_qa_user_prompt(clean_question, evidence, decision_context)

    try:
        answer_text = llm.generate_text(
            system_prompt=QA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except LLMError as e:
        raise QALLMError(f"LLM answer generation failed: {e}") from e
    except Exception as e:
        raise QALLMError("Unexpected error during LLM generation") from e

    # 4. Construct Deduplicated Source References
    sources = extract_source_references(evidence)

    return AnswerResponse(
        question=clean_question,
        answer=answer_text,
        sources=sources,
        evidence_count=len(evidence),
    )

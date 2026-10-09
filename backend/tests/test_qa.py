"""Unit tests for evidence-backed Q&A service and FastAPI endpoint."""
import sys
from pathlib import Path
from typing import Dict, Any
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.extraction.llm_client import BaseLLMClient, LLMAPIError
from app.retrieval.models import ContextRationale, DecisionContext, EvidenceItem, HybridSearchResult
from app.qa.models import QuestionRequest, AnswerResponse, SourceReference
from app.qa.prompts import QA_SYSTEM_PROMPT, format_evidence_block, build_qa_user_prompt
from app.qa.service import (
    answer_question,
    extract_source_references,
    QALLMError,
    QARetrievalError,
)


@pytest.fixture(autouse=True)
def no_decision_context(monkeypatch):
    """By default no decision context is available; tests that need it patch their own."""
    from app.qa import service

    monkeypatch.setattr(service, "retrieve_decision_context", lambda chunk_ids, driver=None: [])


class MockQAClient(BaseLLMClient):
    """Mock LLM client returning canned answer strings."""

    def __init__(self, answer_text: str = "", error: Exception = None):
        self.answer_text = answer_text
        self.error = error
        self.calls = []

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return {}

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self.error:
            raise self.error
        return self.answer_text


def test_empty_question_validation():
    with pytest.raises(ValueError) as exc_info:
        QuestionRequest(question="")
    assert "empty or whitespace" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        QuestionRequest(question="   ")
    assert "empty or whitespace" in str(exc_info.value)


def test_invalid_top_k_validation():
    with pytest.raises(ValueError) as exc_info:
        QuestionRequest(question="Valid question?", top_k=0)
    assert "greater than 0" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        QuestionRequest(question="Valid question?", top_k=-1)
    assert "greater than 0" in str(exc_info.value)


def test_evidence_context_and_prompt_construction():
    evidence = [
        EvidenceItem(
            evidence_id="ev_1",
            evidence_type="decision",
            source_id="src_01",
            chunk_id="chk_01",
            node_id="dec_01",
            text="[DECISION] We chose PostgreSQL with pgvector for relational and vector co-location.",
            metadata={"speaker": "Alex", "start_ts": "00:05:00", "status": "agreed"},
            retrieval_method="hybrid",
            score=0.95,
        ),
        EvidenceItem(
            evidence_id="ev_2",
            evidence_type="action",
            source_id="src_01",
            chunk_id="chk_02",
            node_id="act_01",
            text="[ACTION] Rahul will prepare the PostgreSQL migration script.",
            metadata={"assignee": "Rahul", "deadline": "Friday"},
            retrieval_method="vector",
            score=0.82,
        ),
    ]

    block = format_evidence_block(evidence)
    assert "[Evidence #1] Type: DECISION" in block
    assert "Method: hybrid" in block
    assert "Speaker: Alex" in block
    assert "Time: 00:05:00" in block
    assert "[Evidence #2] Type: ACTION" in block
    assert "Assignee: Rahul" in block

    prompt = build_qa_user_prompt("Why was PostgreSQL selected?", evidence)
    assert "Why was PostgreSQL selected?" in prompt
    assert "Retrieved Evidence:" in prompt
    assert block in prompt


def test_successful_answer_generation(monkeypatch):
    from app.qa import service

    mock_evidence = [
        EvidenceItem(
            evidence_id="ev_01",
            evidence_type="decision",
            source_id="src_meeting_01",
            chunk_id="chk_10",
            text="Alex: We decided to adopt PostgreSQL because it provides ACID guarantees and vector search via pgvector.",
            metadata={"speaker": "Alex", "start_ts": "00:10:00", "page": None},
            retrieval_method="hybrid",
            score=0.96,
        )
    ]
    mock_search_result = HybridSearchResult(
        query="Why PostgreSQL?",
        evidence=mock_evidence,
        vector_results_count=1,
        graph_results_count=1,
    )

    monkeypatch.setattr(service, "hybrid_search", lambda **kwargs: mock_search_result)

    canned_answer = "PostgreSQL was adopted because it provides ACID transaction guarantees alongside vector search capabilities via pgvector."
    mock_llm = MockQAClient(answer_text=canned_answer)

    response = answer_question(
        question="Why was PostgreSQL chosen?",
        top_k=5,
        llm_client=mock_llm,
    )

    assert isinstance(response, AnswerResponse)
    assert response.question == "Why was PostgreSQL chosen?"
    assert response.answer == canned_answer
    assert response.evidence_count == 1
    assert len(response.sources) == 1

    src = response.sources[0]
    assert src.source_id == "src_meeting_01"
    assert src.chunk_id == "chk_10"
    assert src.speaker == "Alex"
    assert src.start_ts == "00:10:00"
    assert src.relevance_score == 0.96


def test_no_evidence_handling(monkeypatch):
    from app.qa import service

    mock_search_result = HybridSearchResult(
        query="Unknown topic",
        evidence=[],
        vector_results_count=0,
        graph_results_count=0,
    )
    monkeypatch.setattr(service, "hybrid_search", lambda **kwargs: mock_search_result)

    mock_llm = MockQAClient(answer_text="Should not be called")
    response = answer_question(
        question="What was decided about Kubernetes deployment?",
        top_k=5,
        llm_client=mock_llm,
    )

    assert "could not find any relevant evidence" in response.answer.lower()
    assert response.sources == []
    assert response.evidence_count == 0
    # LLM should not even be called when there is zero evidence
    assert len(mock_llm.calls) == 0


def test_source_reference_deduplication():
    evidence = [
        EvidenceItem(
            evidence_id="ev_1",
            evidence_type="decision",
            source_id="src_01",
            chunk_id="chk_shared",
            text="Text 1",
            metadata={"speaker": "Alex", "start_ts": "00:01:00"},
            score=0.90,
        ),
        EvidenceItem(
            evidence_id="ev_2",
            evidence_type="action",
            source_id="src_01",
            chunk_id="chk_shared",
            text="Text 2",
            metadata={"speaker": "Alex", "start_ts": "00:01:00"},
            score=0.95,  # Higher score
        ),
        EvidenceItem(
            evidence_id="ev_3",
            evidence_type="rationale",
            source_id="src_02",
            chunk_id="chk_other",
            text="Text 3",
            metadata={"speaker": "Sam"},
            score=0.75,
        ),
    ]

    sources = extract_source_references(evidence)
    # chk_shared should appear only once, taking max score (0.95)
    assert len(sources) == 2
    assert sources[0].chunk_id == "chk_shared"
    assert sources[0].relevance_score == 0.95
    assert sources[1].chunk_id == "chk_other"
    assert sources[1].relevance_score == 0.75


def test_llm_failure_handling(monkeypatch):
    from app.qa import service

    mock_evidence = [
        EvidenceItem(
            evidence_id="ev_01",
            evidence_type="chunk",
            text="Some text",
            score=0.8,
        )
    ]
    mock_search_result = HybridSearchResult(query="q", evidence=mock_evidence)
    monkeypatch.setattr(service, "hybrid_search", lambda **kwargs: mock_search_result)

    failing_llm = MockQAClient(error=LLMAPIError("API rate limited"))

    with pytest.raises(QALLMError) as exc_info:
        answer_question("test question", llm_client=failing_llm)
    assert "LLM answer generation failed" in str(exc_info.value)


def test_retrieval_failure_handling(monkeypatch):
    from app.qa import service

    def failing_retrieval(**kwargs):
        raise RuntimeError("Database connection timed out")

    monkeypatch.setattr(service, "hybrid_search", failing_retrieval)

    with pytest.raises(QARetrievalError) as exc_info:
        answer_question("test question")
    assert "Retrieval failed" in str(exc_info.value)


# --------------------------------------------------------------------------- "why was X not selected?"
OPTIMIZE = "Optimize existing React application"
NEXTJS = "Rebuild frontend using Next.js"
LESS_EFFORT = "Optimizing the existing application would require less development effort."
MAINTAINABILITY = "The long-term maintainability is more important."
TRANSCRIPT = (
    "Carol: Optimizing the existing application would require less development effort.\n"
    "Alice: The long-term maintainability is more important, so I propose that we rebuild the frontend using Next.js.\n"
    "Carol: I agree with the rebuild."
)
NO_REJECTION = "no explicit rejection recorded"


def _meeting_context(**overrides):
    fields = dict(
        decision_id="dec_meeting",
        statement="We will rebuild the frontend using Next.js.",
        status="agreed",
        selected_alternatives=[NEXTJS],
        considered_alternatives=[NEXTJS, OPTIMIZE],
        rationales=[
            ContextRationale(reason=LESS_EFFORT, stance="supports", target_alternatives=[OPTIMIZE]),
            ContextRationale(reason=MAINTAINABILITY, stance="supports", target_alternatives=[NEXTJS]),
        ],
    )
    fields.update(overrides)
    return DecisionContext(**fields)


def _meeting_search(question):
    evidence = [
        EvidenceItem(
            evidence_id="ev_vec_chk_1",
            evidence_type="chunk",
            source_id="src_1",
            chunk_id="chk_1",
            text=TRANSCRIPT,
            retrieval_method="hybrid",
            score=0.86,
        )
    ]
    return HybridSearchResult(query=question, evidence=evidence, vector_results_count=1, graph_results_count=1)


def test_structured_context_preserves_alternatives_rationales_stance_and_targets():
    from app.qa.prompts import format_decision_context

    text = format_decision_context([_meeting_context()])

    assert "We will rebuild the frontend using Next.js." in text  # decision statement
    assert "(status: agreed)" in text
    assert f"{NEXTJS} -- SELECTED" in text  # selected alternative
    assert f"{OPTIMIZE} -- CONSIDERED" in text  # alternative name and its status
    # rationale text + stance + the alternative it is actually about, on one line each
    assert f'SUPPORTS "{OPTIMIZE}": {LESS_EFFORT}' in text
    assert f'SUPPORTS "{NEXTJS}": {MAINTAINABILITY}' in text


def test_considered_alternative_is_never_labelled_rejected():
    from app.qa.prompts import format_decision_context

    text = format_decision_context([_meeting_context()])
    optimize_line = next(line for line in text.splitlines() if line.strip().startswith(f"- {OPTIMIZE}"))

    assert "CONSIDERED" in optimize_line
    assert NO_REJECTION in optimize_line
    assert "REJECTED" not in optimize_line


def test_the_three_statuses_are_kept_distinct():
    from app.qa.prompts import format_decision_context

    ctx = _meeting_context(
        selected_alternatives=["Plan A"],
        rejected_alternatives=["Plan C"],
        considered_alternatives=["Plan A", "Plan B", "Plan C"],
        rationales=[],
    )
    by_name = {
        line.strip()[2:].split(" -- ")[0]: line
        for line in format_decision_context([ctx]).splitlines()
        if " -- " in line
    }

    assert by_name["Plan A"].endswith("SELECTED")
    assert by_name["Plan C"].endswith("REJECTED")
    assert "CONSIDERED" in by_name["Plan B"] and "REJECTED" not in by_name["Plan B"]


def test_why_was_optimizing_not_selected_gets_that_alternatives_own_rationale(monkeypatch):
    from app.qa import service

    question = "Why was optimizing the existing React application not selected?"
    monkeypatch.setattr(service, "hybrid_search", lambda **kw: _meeting_search(question))
    seen = {}

    def fake_context(chunk_ids, driver=None):
        seen["chunk_ids"] = chunk_ids
        return [_meeting_context()]

    monkeypatch.setattr(service, "retrieve_decision_context", fake_context)
    expected = (
        "Optimizing the existing React application was considered because it would require less development "
        "effort, but the team favored Next.js because long-term maintainability was considered more important."
    )
    llm = MockQAClient(answer_text=expected)

    response = answer_question(question, top_k=5, llm_client=llm)

    # the context is looked up for the chunks that were actually retrieved
    assert seen["chunk_ids"] == ["chk_1"]
    prompt = llm.calls[0]["user"]
    system = llm.calls[0]["system"]

    # the model is handed the option's own rationale, linked to that option, plus the selected option's rationale
    assert f'SUPPORTS "{OPTIMIZE}": {LESS_EFFORT}' in prompt
    assert f'SUPPORTS "{NEXTJS}": {MAINTAINABILITY}' in prompt
    assert f"{NEXTJS} -- SELECTED" in prompt
    # ... and nothing in the evidence it is given says the option was rejected
    assert "REJECTED" not in prompt
    # the instructions say how to answer "why not selected" and forbid inventing a rejection
    assert "why an alternative was not selected" in system
    assert 'Say "not selected" rather than "rejected"' in system
    assert 'never call a CONSIDERED alternative "rejected"' in system
    # the answer and citations pass through unchanged
    assert response.answer == expected
    assert "rejected" not in response.answer.lower()
    assert response.sources[0].chunk_id == "chk_1" and response.sources[0].relevance_score == 0.86


def test_no_decision_context_leaves_the_prompt_unchanged():
    evidence = _meeting_search("q").evidence
    assert build_qa_user_prompt("q", evidence) == build_qa_user_prompt("q", evidence, [])
    assert "Structured decision context" not in build_qa_user_prompt("q", evidence, [])


def test_unsupported_question_keeps_its_safe_instructions(monkeypatch):
    # "What was the project budget?" must still be steered to the insufficient-evidence statement
    from app.qa import service

    question = "What was the project budget?"
    monkeypatch.setattr(service, "hybrid_search", lambda **kw: _meeting_search(question))
    monkeypatch.setattr(service, "retrieve_decision_context", lambda chunk_ids, driver=None: [_meeting_context()])
    llm = MockQAClient(answer_text="The available meeting and document evidence is insufficient to answer this question.")

    response = answer_question(question, llm_client=llm)

    system = llm.calls[0]["system"]
    assert "The available meeting and document evidence is insufficient to answer this question." in system
    assert "it never makes an unrelated question answerable" in system
    assert response.answer.startswith("The available meeting and document evidence is insufficient")


def test_zero_evidence_still_returns_the_safe_response_without_a_graph_lookup(monkeypatch):
    from app.qa import service

    monkeypatch.setattr(
        service, "hybrid_search", lambda **kw: HybridSearchResult(query="q", evidence=[], vector_results_count=0, graph_results_count=0)
    )

    def must_not_be_called(chunk_ids, driver=None):
        raise AssertionError("decision context must not be looked up when nothing was retrieved")

    monkeypatch.setattr(service, "retrieve_decision_context", must_not_be_called)

    response = answer_question("What was the project budget?", llm_client=MockQAClient(answer_text="unused"))
    assert "could not find any relevant evidence" in response.answer.lower()


def test_existing_safety_rules_are_still_in_the_prompt():
    assert "Do NOT claim an alternative was rejected unless explicit evidence confirms rejection." in QA_SYSTEM_PROMPT
    assert "Do NOT claim an action was completed unless explicit evidence confirms completion." in QA_SYSTEM_PROMPT
    assert "state clearly:" in QA_SYSTEM_PROMPT


# --------------------------------------------------------------------------- decision-context retrieval
class _CtxTx:
    def __init__(self, rows, record):
        self.rows, self.record = rows, record

    def run(self, query, **params):
        self.record.append((query, params))
        rows = self.rows

        class _Result:
            def data(self):
                return rows

        return _Result()


class _CtxSession:
    def __init__(self, rows, record, error=None):
        self.rows, self.record, self.error = rows, record, error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_read(self, fn):
        if self.error:
            raise self.error
        return fn(_CtxTx(self.rows, self.record))


class _CtxDriver:
    def __init__(self, rows=(), error=None):
        self.rows, self.error, self.record = list(rows), error, []

    def session(self):
        return _CtxSession(self.rows, self.record, self.error)


GRAPH_ROW = {
    "decision_id": "dec_1",
    "statement": "We will rebuild the frontend using Next.js.",
    "status": "agreed",
    "problems": ["Poor mobile performance"],
    "selected": [NEXTJS],
    "rejected": [],
    "considered_via_problem": [NEXTJS, OPTIMIZE],
    "rationales": [
        {"reason": LESS_EFFORT, "stance": "supports", "targets": [OPTIMIZE]},
        {"reason": MAINTAINABILITY, "stance": "supports", "targets": [NEXTJS]},
    ],
}


def test_retrieve_decision_context_maps_graph_rows():
    from app.retrieval.graph_retriever import retrieve_decision_context

    driver = _CtxDriver([GRAPH_ROW])
    result = retrieve_decision_context(["chk_1", "chk_1", "chk_2"], driver=driver)

    assert driver.record[0][1]["chunk_ids"] == ["chk_1", "chk_2"]  # deduplicated
    ctx = result[0]
    assert ctx.decision_id == "dec_1" and ctx.status == "agreed"
    assert ctx.selected_alternatives == [NEXTJS] and ctx.rejected_alternatives == []
    assert ctx.considered_alternatives == [NEXTJS, OPTIMIZE]
    assert [(r.stance, r.target_alternatives, r.reason) for r in ctx.rationales] == [
        ("supports", [OPTIMIZE], LESS_EFFORT),
        ("supports", [NEXTJS], MAINTAINABILITY),
    ]


def test_retrieve_decision_context_includes_alternatives_known_only_from_a_rationale():
    from app.retrieval.graph_retriever import retrieve_decision_context

    row = dict(GRAPH_ROW, considered_via_problem=[])  # e.g. an upload where no Problem was extracted
    ctx = retrieve_decision_context(["chk_1"], driver=_CtxDriver([row]))[0]

    assert OPTIMIZE in ctx.considered_alternatives


def test_retrieve_decision_context_query_is_read_only_and_uses_existing_relationships():
    from app.retrieval.graph_retriever import DECISION_CONTEXT_QUERY

    for relationship in ("EVIDENCED_BY", "SELECTED", "REJECTED", "JUSTIFIED_BY", "SUPPORTS|OPPOSES", "CONSIDERED"):
        assert relationship in DECISION_CONTEXT_QUERY
    for write in ("CREATE", "MERGE", "DELETE", "SET "):
        assert write not in DECISION_CONTEXT_QUERY


def test_retrieve_decision_context_degrades_to_empty_when_the_graph_fails_or_nothing_to_look_up():
    from app.retrieval.graph_retriever import retrieve_decision_context

    assert retrieve_decision_context([], driver=_CtxDriver([GRAPH_ROW])) == []
    assert retrieve_decision_context([None, ""], driver=_CtxDriver([GRAPH_ROW])) == []
    assert retrieve_decision_context(["chk_1"], driver=_CtxDriver(error=RuntimeError("neo4j down"))) == []


def test_retrieve_decision_context_skips_malformed_rows():
    from app.retrieval.graph_retriever import retrieve_decision_context

    rows = [dict(GRAPH_ROW, decision_id=None), dict(GRAPH_ROW, statement=None), GRAPH_ROW]
    assert [c.decision_id for c in retrieve_decision_context(["chk_1"], driver=_CtxDriver(rows))] == ["dec_1"]


def test_api_qa_ask_endpoint_success(monkeypatch):
    from app.qa import service

    mock_response = AnswerResponse(
        question="What is the architecture?",
        answer="The system uses FastAPI, Next.js, PostgreSQL with pgvector, and Neo4j.",
        sources=[
            SourceReference(
                source_id="src_arch",
                chunk_id="chk_01",
                title="Architecture Document",
                relevance_score=0.98,
            )
        ],
        evidence_count=1,
    )
    monkeypatch.setattr(service, "answer_question", lambda **kwargs: mock_response)

    client = TestClient(app)
    res = client.post(
        "/api/qa/ask",
        json={"question": "What is the architecture?", "top_k": 3},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["question"] == "What is the architecture?"
    assert "FastAPI, Next.js" in data["answer"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["chunk_id"] == "chk_01"


def test_api_qa_ask_endpoint_validation_errors():
    client = TestClient(app)

    # Empty question
    res1 = client.post("/api/qa/ask", json={"question": "", "top_k": 5})
    assert res1.status_code == 422 or res1.status_code == 400

    # Invalid top_k
    res2 = client.post("/api/qa/ask", json={"question": "Valid?", "top_k": 0})
    assert res2.status_code == 422 or res2.status_code == 400


if __name__ == "__main__":
    test_empty_question_validation()
    test_invalid_top_k_validation()
    test_evidence_context_and_prompt_construction()
    test_successful_answer_generation()
    test_no_evidence_handling()
    test_source_reference_deduplication()
    test_llm_failure_handling()
    test_retrieval_failure_handling()
    test_api_qa_ask_endpoint_success()
    test_api_qa_ask_endpoint_validation_errors()
    print("All Q&A unit tests passed successfully!")

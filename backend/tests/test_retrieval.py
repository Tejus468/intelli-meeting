"""Unit tests for hybrid retrieval, graph traversal, and multi-modal score fusion."""
import sys
from pathlib import Path
from typing import List, Dict, Any
import pytest

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.embeddings.models import VectorSearchResult
from app.retrieval.models import EvidenceItem, HybridSearchResult
from app.retrieval.graph_retriever import (
    retrieve_graph_evidence,
    extract_search_terms,
    GRAPH_SEARCH_BY_TERMS_QUERY,
    GRAPH_SEARCH_BY_SEED_CHUNKS_QUERY,
)
from app.retrieval.hybrid import hybrid_search, VECTOR_WEIGHT, GRAPH_WEIGHT


class MockGraphResult:
    """Mock Neo4j result returning dict records."""

    def __init__(self, data: List[Dict[str, Any]]):
        self._data = data

    def data(self):
        return self._data


class MockGraphTx:
    """Mock Neo4j transaction recording Cypher queries and parameters."""

    def __init__(self, records: List[Dict[str, Any]]):
        self.queries: List[Dict[str, Any]] = []
        self.records = records

    def run(self, query: str, **params):
        self.queries.append({"query": query.strip(), "params": params})
        return MockGraphResult(self.records)


class MockGraphSession:
    """Mock Neo4j session executing read transactions."""

    def __init__(self, tx: MockGraphTx):
        self.tx = tx

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute_read(self, tx_func):
        return tx_func(self.tx)


class MockGraphDriver:
    """Mock Neo4j driver providing MockGraphSession."""

    def __init__(self, records: List[Dict[str, Any]]):
        self.tx = MockGraphTx(records)

    def session(self):
        return MockGraphSession(self.tx)


def test_empty_query_validation():
    with pytest.raises(ValueError) as exc_info:
        hybrid_search("")
    assert "cannot be empty" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        hybrid_search("   ")
    assert "cannot be empty" in str(exc_info.value)


def test_invalid_top_k_validation():
    with pytest.raises(ValueError) as exc_info:
        hybrid_search("valid query", top_k=0)
    assert "greater than 0" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        hybrid_search("valid query", top_k=-5)
    assert "greater than 0" in str(exc_info.value)


def test_search_terms_extraction():
    terms = extract_search_terms("What did we decide about PostgreSQL and pgvector?")
    assert "postgresql" in terms
    assert "pgvector" in terms
    assert "decide" in terms
    # Stopwords should be excluded
    assert "what" not in terms
    assert "about" not in terms
    assert "and" not in terms


def test_graph_retrieval_cypher_construction_and_provenance():
    mock_records = [
        {
            "node_type": "Decision",
            "node_id": "dec_01",
            "text": "Adopt pgvector for similarity search",
            "node_props": {"status": "agreed", "confidence": 0.95},
            "chunk_id": "chk_01",
            "chunk_text": "Alex: We decided to adopt pgvector.",
            "speaker": "Alex",
            "start_ts": "00:02:15",
            "end_ts": "00:03:00",
            "page": None,
            "source_id": "src_01",
        }
    ]
    driver = MockGraphDriver(mock_records)

    evidence = retrieve_graph_evidence(
        query="pgvector decision",
        top_k=5,
        driver=driver,
        seed_chunk_ids=["chk_01"],
    )

    assert len(evidence) == 1
    item = evidence[0]
    assert item.evidence_id == "ev_graph_dec_01"
    assert item.evidence_type == "decision"
    assert item.source_id == "src_01"
    assert item.chunk_id == "chk_01"
    assert item.node_id == "dec_01"
    assert item.retrieval_method == "graph"
    assert item.metadata["speaker"] == "Alex"
    assert item.metadata["status"] == "agreed"
    assert 0.0 <= item.score <= 1.0

    # Verify Cypher queries executed
    queries = driver.tx.queries
    assert len(queries) == 2
    assert any("MATCH (n)" in q["query"] and "n:Decision" in q["query"] for q in queries)
    assert any("MATCH (c:Chunk)" in q["query"] and "c.chunk_id IN $seed_chunk_ids" in q["query"] for q in queries)


def test_no_provenance_graph_result_handling():
    """Graph node without connected chunk must still return valid EvidenceItem without crashing."""
    mock_records = [
        {
            "node_type": "Alternative",
            "node_id": "alt_orphan",
            "text": "MongoDB",
            "node_props": {"confidence": 0.7},
            "chunk_id": None,
            "chunk_text": None,
            "speaker": None,
            "start_ts": None,
            "end_ts": None,
            "page": None,
            "source_id": None,
        }
    ]
    driver = MockGraphDriver(mock_records)

    evidence = retrieve_graph_evidence("MongoDB option", top_k=5, driver=driver)
    assert len(evidence) == 1
    item = evidence[0]
    assert item.node_id == "alt_orphan"
    assert item.chunk_id is None
    assert item.source_id is None
    assert "[ALTERNATIVE] MongoDB" in item.text


def test_vector_only_evidence_conversion(monkeypatch):
    from app.retrieval import hybrid

    mock_vector_results = [
        VectorSearchResult(
            chunk_id="chk_v1",
            source_id="src_01",
            text="Vector retrieved text content",
            speaker="Priya",
            start_ts="00:01:00",
            end_ts="00:01:30",
            page=None,
            char_start=0,
            char_end=28,
            distance=0.1,
            similarity_score=0.9,
        )
    ]

    monkeypatch.setattr(hybrid, "search_similar_chunks", lambda **kwargs: mock_vector_results)
    monkeypatch.setattr(hybrid, "retrieve_graph_evidence", lambda **kwargs: [])

    result = hybrid_search("database choice", top_k=5)

    assert isinstance(result, HybridSearchResult)
    assert result.vector_results_count == 1
    assert result.graph_results_count == 0
    assert len(result.evidence) == 1

    item = result.evidence[0]
    assert item.chunk_id == "chk_v1"
    assert item.retrieval_method == "vector"
    assert item.metadata["speaker"] == "Priya"
    # Weighted vector score = 0.6 * 0.9 = 0.54
    assert item.score == pytest.approx(0.54, rel=1e-2)


def test_duplicate_evidence_handling_and_hybrid_fusion(monkeypatch):
    from app.retrieval import hybrid

    # Same chunk returned by both Vector search and Graph traversal
    mock_vector_results = [
        VectorSearchResult(
            chunk_id="chk_shared",
            source_id="src_01",
            text="Alex: We decided to use PostgreSQL.",
            speaker="Alex",
            start_ts="00:05:00",
            end_ts="00:05:30",
            page=1,
            char_start=0,
            char_end=35,
            distance=0.1,
            similarity_score=0.9,  # vector_score = 0.9
        )
    ]

    mock_graph_evidence = [
        EvidenceItem(
            evidence_id="ev_graph_dec_01",
            evidence_type="decision",
            source_id="src_01",
            chunk_id="chk_shared",
            node_id="dec_01",
            text="[DECISION] Adopt PostgreSQL",
            metadata={"status": "agreed", "confidence": 0.95},
            retrieval_method="graph",
            score=0.85,  # graph_score = 0.85
        )
    ]

    monkeypatch.setattr(hybrid, "search_similar_chunks", lambda **kwargs: mock_vector_results)
    monkeypatch.setattr(hybrid, "retrieve_graph_evidence", lambda **kwargs: mock_graph_evidence)

    result = hybrid_search("PostgreSQL decision", top_k=5)

    assert result.vector_results_count == 1
    assert result.graph_results_count == 1
    # Deduplication: single merged evidence item
    assert len(result.evidence) == 1

    item = result.evidence[0]
    assert item.chunk_id == "chk_shared"
    assert item.retrieval_method == "hybrid"
    assert item.node_id == "dec_01"
    assert item.metadata["speaker"] == "Alex"
    assert item.metadata["status"] == "agreed"
    assert item.metadata["graph_node_id"] == "dec_01"

    # Hybrid score = min(1.0, 0.6 * 0.9 + 0.4 * 0.85 + 0.1) = 0.54 + 0.34 + 0.1 = 0.98
    assert item.score == pytest.approx(0.98, rel=1e-2)


def test_combined_vector_and_graph_ranking(monkeypatch):
    from app.retrieval import hybrid

    # Three items: one hybrid match, one vector-only match, one graph-only match
    v_results = [
        VectorSearchResult(
            chunk_id="chk_hybrid",
            source_id="src_01",
            text="High relevance text",
            similarity_score=0.95,
            distance=0.05,
        ),
        VectorSearchResult(
            chunk_id="chk_vector_only",
            source_id="src_01",
            text="Medium vector text",
            similarity_score=0.70,
            distance=0.30,
        ),
    ]

    g_results = [
        EvidenceItem(
            evidence_id="ev_graph_1",
            evidence_type="decision",
            source_id="src_01",
            chunk_id="chk_hybrid",
            node_id="dec_01",
            text="[DECISION] High relevance decision",
            retrieval_method="graph",
            score=0.90,
        ),
        EvidenceItem(
            evidence_id="ev_graph_only",
            evidence_type="action",
            source_id="src_01",
            chunk_id="chk_graph_only",
            node_id="act_01",
            text="[ACTION] Low graph action",
            retrieval_method="graph",
            score=0.50,
        ),
    ]

    monkeypatch.setattr(hybrid, "search_similar_chunks", lambda **kwargs: v_results)
    monkeypatch.setattr(hybrid, "retrieve_graph_evidence", lambda **kwargs: g_results)

    result = hybrid_search("test query", top_k=2)

    # top_k = 2 should return top 2 ranked items
    assert len(result.evidence) == 2
    # First item must be the hybrid matched item with highest fused score
    assert result.evidence[0].chunk_id == "chk_hybrid"
    assert result.evidence[0].retrieval_method == "hybrid"
    # Scores must be in descending order
    assert result.evidence[0].score >= result.evidence[1].score


def test_evidence_score_normalization():
    item = EvidenceItem(
        evidence_id="ev_test",
        evidence_type="chunk",
        text="Sample text",
        score=0.85,
    )
    assert 0.0 <= item.score <= 1.0

    # Bounds validation
    with pytest.raises(Exception):
        EvidenceItem(
            evidence_id="ev_invalid",
            evidence_type="chunk",
            text="Invalid score",
            score=1.5,
        )


if __name__ == "__main__":
    test_empty_query_validation()
    test_invalid_top_k_validation()
    test_search_terms_extraction()
    test_graph_retrieval_cypher_construction_and_provenance()
    test_no_provenance_graph_result_handling()
    test_vector_only_evidence_conversion()
    test_duplicate_evidence_handling_and_hybrid_fusion()
    test_combined_vector_and_graph_ranking()
    test_evidence_score_normalization()
    print("All hybrid retrieval unit tests passed successfully!")

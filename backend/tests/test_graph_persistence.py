"""Unit tests for Neo4j persistence layer using mocked driver and transaction recording."""
import sys
from pathlib import Path
from typing import List, Dict, Any
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
from app.graph.service import (
    persist_extraction_to_graph,
    make_deterministic_person_id,
    GraphMissingProvenanceError,
    GraphPersistenceError,
)


class MockTransaction:
    """Mock Neo4j transaction recording Cypher queries and parameters."""

    def __init__(self):
        self.queries: List[Dict[str, Any]] = []

    def run(self, query: str, **params):
        self.queries.append({"query": query.strip(), "params": params})


class MockSession:
    """Mock Neo4j session executing transaction functions."""

    def __init__(self, tx: MockTransaction):
        self.tx = tx

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute_write(self, tx_func):
        return tx_func(self.tx)


class MockDriver:
    """Mock Neo4j driver providing MockSession."""

    def __init__(self):
        self.tx = MockTransaction()

    def session(self):
        return MockSession(self.tx)


def test_deterministic_person_id():
    id1 = make_deterministic_person_id("Alex Johnson")
    id2 = make_deterministic_person_id("alex johnson")
    id3 = make_deterministic_person_id("  ALEX JOHNSON  ")
    assert id1 == id2 == id3
    assert id1.startswith("per_")


def test_valid_extraction_persistence_and_relationships():
    driver = MockDriver()
    source = {
        "source_id": "src_100",
        "source_type": "transcript",
        "title": "Architecture Review",
        "source_date": "2026-09-08T10:00:00Z",
    }
    chunk = ChunkRecord(
        chunk_id="chk_200",
        source_id="src_100",
        text="Alex: We decided to use PostgreSQL because of reliability.",
        speaker="Alex",
        start_ts="00:05:00",
    )
    extraction = ExtractionResult(
        chunk_id="chk_200",
        problems=[
            ExtractedProblem(
                id="prob_1",
                chunk_id="chk_200",
                confidence=0.95,
                description="Database bottleneck",
            )
        ],
        alternatives=[
            ExtractedAlternative(
                id="alt_1",
                chunk_id="chk_200",
                confidence=0.90,
                name="PostgreSQL",
                description="Relational database with pgvector",
            )
        ],
        rationales=[
            ExtractedRationale(
                id="rat_1",
                chunk_id="chk_200",
                confidence=0.92,
                reason="High transaction reliability",
                stance="supports",
                target_alternative="PostgreSQL",
            )
        ],
        decisions=[
            ExtractedDecision(
                id="dec_1",
                chunk_id="chk_200",
                confidence=0.98,
                statement="Adopt PostgreSQL",
                chosen_alternative="PostgreSQL",
                status="agreed",
            )
        ],
        actions=[
            ExtractedAction(
                id="act_1",
                chunk_id="chk_200",
                confidence=0.90,
                task="Write migration scripts",
                assignee="Alex",
                deadline="End of sprint",
                status="pending",
            )
        ],
        people=[
            ExtractedPerson(
                id="per_alex",
                chunk_id="chk_200",
                confidence=0.99,
                name="Alex",
                role="Backend Lead",
            )
        ],
        outcomes=[
            ExtractedOutcome(
                id="out_1",
                chunk_id="chk_200",
                confidence=0.85,
                result="Latency dropped to 10ms",
                status="verified",
            )
        ],
    )

    result = persist_extraction_to_graph(source, chunk, extraction, driver=driver)

    assert result["status"] == "success"
    assert result["source_id"] == "src_100"
    assert result["chunk_id"] == "chk_200"
    assert result["counts"]["problems"] == 1
    assert result["counts"]["decisions"] == 1

    queries = driver.tx.queries
    query_texts = [q["query"] for q in queries]

    # 1. Check Source MERGE
    assert any("MERGE (s:Source {source_id: $source_id})" in q for q in query_texts)

    # 2. Check Chunk MERGE and HAS_CHUNK
    assert any("MERGE (c:Chunk {chunk_id: $chunk_id})" in q and "[:HAS_CHUNK]" in q for q in query_texts)

    # 3. Check Speaker SPOKEN_BY
    assert any("[:SPOKEN_BY]" in q for q in query_texts)

    # 4. Check EVIDENCED_BY for Problem, Alternative, Rationale, Decision, Action, Person, Outcome
    evidenced_queries = [q for q in query_texts if "[:EVIDENCED_BY]" in q]
    assert len(evidenced_queries) >= 7  # All 7 extracted entities must link EVIDENCED_BY to chunk

    # 5. Check semantic relationships
    assert any("[:DISCUSSED]" in q for q in query_texts)  # (Source)-[:DISCUSSED]->(Problem)
    assert any("[:CONSIDERED]" in q for q in query_texts)  # (Problem)-[:CONSIDERED]->(Alternative)
    assert any("[:SUPPORTS]" in q for q in query_texts)  # (Rationale)-[:SUPPORTS]->(Alternative)
    assert any("[:MADE_IN]" in q for q in query_texts)  # (Decision)-[:MADE_IN]->(Source)
    assert any("[:RESOLVES]" in q for q in query_texts)  # (Decision)-[:RESOLVES]->(Problem)
    assert any("[:JUSTIFIED_BY]" in q for q in query_texts)  # (Decision)-[:JUSTIFIED_BY]->(Rationale)
    assert any("[:SELECTED]" in q for q in query_texts)  # (Decision)-[:SELECTED]->(Alternative)
    assert any("[:ASSIGNS]" in q for q in query_texts)  # (Decision)-[:ASSIGNS]->(Action)
    assert any("[:OWNED_BY]" in q for q in query_texts)  # (Action)-[:OWNED_BY]->(Person)
    assert any("[:PRODUCED]" in q for q in query_texts)  # (Action)-[:PRODUCED]->(Outcome)


def test_rationale_is_linked_to_its_own_alternative_not_the_selected_one():
    from app.graph.cypher import LINK_RATIONALE_ALTERNATIVE_QUERY, LINK_DECISION_ALTERNATIVE_SELECTED_QUERY

    driver = MockDriver()
    chunk = ChunkRecord(chunk_id="chk_r", source_id="src_r", text="discussion")

    def item(cls, **fields):
        return cls(chunk_id="chk_r", confidence=0.9, **fields)

    extraction = ExtractionResult(
        chunk_id="chk_r",
        alternatives=[
            item(ExtractedAlternative, id="alt_next", name="Rebuild with Next.js"),
            item(ExtractedAlternative, id="alt_opt", name="Optimize existing app"),
        ],
        rationales=[
            item(ExtractedRationale, id="rat_opt", reason="Less effort", stance="supports", target_alternative="Optimize existing app"),
            item(ExtractedRationale, id="rat_cons", reason="Takes longer", stance="opposes", target_alternative="Rebuild with Next.js"),
            item(ExtractedRationale, id="rat_unknown", reason="General remark", stance="supports", target_alternative=None),
        ],
        decisions=[
            item(ExtractedDecision, id="dec_1", statement="Rebuild", chosen_alternative="Rebuild with Next.js"),
        ],
    )

    persist_extraction_to_graph({"source_id": "src_r"}, chunk, extraction, driver=driver)

    links = {
        q["params"]["rationale_id"]: (q["params"]["alternative_id"], q["params"]["stance"])
        for q in driver.tx.queries
        if q["query"] == LINK_RATIONALE_ALTERNATIVE_QUERY.strip()
    }
    # supports a NON-selected alternative -> linked to that one only
    assert links["rat_opt"] == ("alt_opt", "supports")
    # opposes an alternative -> linked with the opposing stance
    assert links["rat_cons"] == ("alt_next", "opposes")
    # target unknown and two alternatives exist -> nothing is invented
    assert "rat_unknown" not in links

    selected = [
        q["params"]["alternative_id"]
        for q in driver.tx.queries
        if q["query"] == LINK_DECISION_ALTERNATIVE_SELECTED_QUERY.strip()
    ]
    assert selected == ["alt_next"]


def test_empty_extraction_persistence():
    driver = MockDriver()
    source = {"source_id": "src_empty"}
    chunk = ChunkRecord(chunk_id="chk_empty", source_id="src_empty", text="Introductory remarks.")
    extraction = ExtractionResult(chunk_id="chk_empty")

    result = persist_extraction_to_graph(source, chunk, extraction, driver=driver)
    assert result["status"] == "success"
    assert result["counts"]["problems"] == 0
    assert result["counts"]["decisions"] == 0

    # Only Source and Chunk should be merged
    query_texts = [q["query"] for q in driver.tx.queries]
    assert len(query_texts) == 2


def test_missing_source_id_rejection():
    driver = MockDriver()
    source = {"source_id": ""}
    chunk = ChunkRecord(chunk_id="chk_1", source_id="src_1", text="text")
    extraction = ExtractionResult(chunk_id="chk_1")

    with pytest.raises(GraphMissingProvenanceError) as exc_info:
        persist_extraction_to_graph(source, chunk, extraction, driver=driver)
    assert "source_id" in str(exc_info.value)


def test_missing_chunk_id_rejection():
    driver = MockDriver()
    source = {"source_id": "src_1"}
    chunk = {"chunk_id": "", "text": "text"}
    extraction = ExtractionResult(chunk_id="chk_1")

    with pytest.raises(GraphMissingProvenanceError) as exc_info:
        persist_extraction_to_graph(source, chunk, extraction, driver=driver)
    assert "chunk_id" in str(exc_info.value)


def test_mismatched_extraction_chunk_id_rejection():
    driver = MockDriver()
    source = {"source_id": "src_1"}
    chunk = ChunkRecord(chunk_id="chk_1", source_id="src_1", text="text")
    extraction = ExtractionResult(chunk_id="chk_mismatch")

    with pytest.raises(GraphMissingProvenanceError) as exc_info:
        persist_extraction_to_graph(source, chunk, extraction, driver=driver)
    assert "does not match" in str(exc_info.value)


def test_idempotent_query_structure():
    """Verify that all write operations exclusively use MERGE statements to prevent duplicate nodes."""
    driver = MockDriver()
    source = {"source_id": "src_idem", "title": "Test Document"}
    chunk = ChunkRecord(chunk_id="chk_idem", source_id="src_idem", text="Text")
    extraction = ExtractionResult(
        chunk_id="chk_idem",
        decisions=[
            ExtractedDecision(
                id="dec_idem",
                chunk_id="chk_idem",
                confidence=0.9,
                statement="Idempotency confirmed",
            )
        ],
    )

    persist_extraction_to_graph(source, chunk, extraction, driver=driver)

    for q in driver.tx.queries:
        query_text = q["query"]
        # Must contain MERGE and not blind CREATE
        assert "MERGE" in query_text
        assert "CREATE (" not in query_text.replace("ON CREATE", "")


if __name__ == "__main__":
    test_deterministic_person_id()
    test_valid_extraction_persistence_and_relationships()
    test_empty_extraction_persistence()
    test_missing_source_id_rejection()
    test_missing_chunk_id_rejection()
    test_mismatched_extraction_chunk_id_rejection()
    test_idempotent_query_structure()
    print("All graph persistence unit tests passed successfully!")

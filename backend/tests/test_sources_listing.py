"""Tests for GET /api/ingestion/sources, run against real PostgreSQL in an isolated schema."""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.ingestion import service
from app.ingestion.models import ChunkRecord, ExtractionResult, ExtractedSegment
from app.main import app

EXPECTED_FIELDS = {
    "source_id",
    "title",
    "source_type",
    "source_date",
    "created_at",
    "number_of_chunks",
    "decision_ids",
}


class FakeDecisionGraph:
    """Stands in for Neo4j for the decisions-by-source read: rows are what MADE_IN would return."""

    def __init__(self):
        self.rows = []
        self.error = None
        self.queries = []

    def session(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        if self.error:
            raise self.error
        self.queries.append(query)
        rows = self.rows

        class _Result:
            def data(self):
                return rows

        return _Result()


@pytest.fixture(autouse=True)
def graph(monkeypatch):
    fake = FakeDecisionGraph()
    monkeypatch.setattr(service, "get_neo4j_driver", lambda: fake)
    return fake


def _persist(title: str, source_type: str, chunk_count: int, source_date=None) -> str:
    source_id = f"src_{uuid.uuid4().hex[:12]}"
    extraction = ExtractionResult(
        title=title,
        source_type=source_type,
        segments=[ExtractedSegment(text="x")],
        raw_text="x",
        source_date=source_date,
    )
    chunks = [
        ChunkRecord(chunk_id=f"chk_{uuid.uuid4().hex[:12]}", source_id=source_id, text=f"chunk {i}")
        for i in range(chunk_count)
    ]
    service.persist_source_and_chunks(source_id, extraction, chunks)
    return source_id


def test_empty_database_returns_empty_list(isolated_db):
    assert service.list_sources() == []

    response = TestClient(app).get("/api/ingestion/sources")
    assert response.status_code == 200
    assert response.json() == []


def test_sources_returned_from_postgres_with_correct_chunk_counts(isolated_db):
    id_a = _persist("Sprint Planning", "transcript", chunk_count=3)
    id_b = _persist("Architecture Notes", "pdf", chunk_count=1)

    response = TestClient(app).get("/api/ingestion/sources")
    assert response.status_code == 200
    body = {row["source_id"]: row for row in response.json()}

    assert set(body) == {id_a, id_b}
    assert body[id_a]["title"] == "Sprint Planning"
    assert body[id_a]["source_type"] == "transcript"
    assert body[id_a]["number_of_chunks"] == 3
    assert body[id_b]["title"] == "Architecture Notes"
    assert body[id_b]["source_type"] == "pdf"
    assert body[id_b]["number_of_chunks"] == 1


def test_source_without_chunks_has_zero_count(isolated_db):
    source_id = f"src_{uuid.uuid4().hex[:12]}"
    with service.get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sources (source_id, source_type, title) VALUES (%s, %s, %s);",
                (source_id, "txt", "Empty Source"),
            )
        conn.commit()

    result = service.list_sources()
    assert len(result) == 1
    assert result[0].source_id == source_id
    assert result[0].number_of_chunks == 0


def test_chunks_are_counted_per_source_not_globally(isolated_db):
    id_a = _persist("Doc A", "docx", chunk_count=2)
    id_b = _persist("Doc B", "docx", chunk_count=5)

    counts = {s.source_id: s.number_of_chunks for s in service.list_sources()}
    assert counts == {id_a: 2, id_b: 5}


def test_sources_listed_newest_first(isolated_db):
    first = _persist("First", "txt", chunk_count=1)
    second = _persist("Second", "txt", chunk_count=1)

    ids = [s.source_id for s in service.list_sources()]
    assert ids == [second, first]


def test_response_fields_match_api_contract(isolated_db):
    source_date = datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)
    source_id = _persist("Contract Doc", "txt", chunk_count=2, source_date=source_date)

    response = TestClient(app).get("/api/ingestion/sources")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list) and len(payload) == 1

    row = payload[0]
    assert set(row.keys()) == EXPECTED_FIELDS
    assert row["source_id"] == source_id
    assert isinstance(row["title"], str)
    assert isinstance(row["source_type"], str)
    assert isinstance(row["number_of_chunks"], int)
    assert datetime.fromisoformat(row["source_date"]) == source_date
    assert datetime.fromisoformat(row["created_at"]) is not None


def test_database_failure_returns_503(monkeypatch):
    def failing_connection():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(service, "get_postgres_connection", failing_connection)

    response = TestClient(app).get("/api/ingestion/sources")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- decision ids
def test_sources_expose_their_decision_ids(isolated_db, graph):
    with_one = _persist("Sprint Planning", "transcript", chunk_count=1)
    with_two = _persist("Architecture Review", "pdf", chunk_count=2)
    graph.rows = [
        {"source_id": with_one, "decision_ids": ["dec_aaa111"]},
        {"source_id": with_two, "decision_ids": ["dec_bbb222", "dec_ccc333"]},
    ]

    response = TestClient(app).get("/api/ingestion/sources")

    assert response.status_code == 200
    ids = {row["source_id"]: row["decision_ids"] for row in response.json()}
    assert ids[with_one] == ["dec_aaa111"]
    assert ids[with_two] == ["dec_bbb222", "dec_ccc333"]  # several decisions, order preserved


def test_source_without_decisions_returns_an_empty_list_not_null(isolated_db, graph):
    decided = _persist("Has decision", "txt", chunk_count=1)
    undecided = _persist("No decision", "txt", chunk_count=1)
    graph.rows = [{"source_id": decided, "decision_ids": ["dec_only"]}]

    rows = {r["source_id"]: r for r in TestClient(app).get("/api/ingestion/sources").json()}

    assert rows[undecided]["decision_ids"] == []
    assert rows[undecided]["decision_ids"] is not None
    assert rows[decided]["decision_ids"] == ["dec_only"]


def test_decisions_of_another_source_are_not_attached(isolated_db, graph):
    mine = _persist("Mine", "txt", chunk_count=1)
    graph.rows = [{"source_id": "src_some_other_source", "decision_ids": ["dec_other"]}]

    rows = TestClient(app).get("/api/ingestion/sources").json()

    assert [r["decision_ids"] for r in rows if r["source_id"] == mine] == [[]]


def test_decisions_are_read_through_the_made_in_relationship(isolated_db, graph):
    _persist("Doc", "txt", chunk_count=1)
    service.list_sources()
    assert "(d:Decision)-[:MADE_IN]->(s:Source)" in graph.queries[0]


def test_listing_reports_graph_outage_instead_of_claiming_no_decisions(isolated_db, graph):
    from neo4j.exceptions import ServiceUnavailable

    _persist("Doc", "txt", chunk_count=1)
    graph.error = ServiceUnavailable("down")

    response = TestClient(app).get("/api/ingestion/sources")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_listing_graph_failure_returns_500(isolated_db, graph):
    _persist("Doc", "txt", chunk_count=1)
    graph.error = RuntimeError("cypher boom")

    assert TestClient(app).get("/api/ingestion/sources").status_code == 500

"""Integration tests for the full upload pipeline:
parse -> chunk -> PostgreSQL -> LLM extraction -> Neo4j -> embeddings/pgvector.

PostgreSQL/pgvector are real (isolated throwaway schema). The LLM and Neo4j are fakes, so no live
Ollama or Neo4j server is needed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from app.embeddings import service as embedding_service
from app.embeddings.model import MockEmbeddingModel, set_embedding_model
from app.extraction import service as extraction_service
from app.extraction.llm_client import LLMAPIError
from app.extraction.models import ExtractionResult as ChunkExtraction
from app.graph import service as graph_service
from app.graph.cypher import MERGE_CHUNK_QUERY, MERGE_DECISION_QUERY, MERGE_SOURCE_QUERY
from app.ingestion import service
from app.main import app

TRANSCRIPT = (
    "[00:01:00] Alice: We should use PostgreSQL because pgvector gives us vector search.\n"
    "[00:02:00] Bob: Agreed, I will migrate the data by Friday.\n"
)


# --------------------------------------------------------------------------- fakes
class FakeLLM:
    """Returns the kind of output a small model gives: the SAME ids ("dec_1") for every chunk."""

    def __init__(self, fail=False, decision_count=1):
        self.fail = fail
        self.decision_count = decision_count
        self.prompts = []

    def generate_json(self, system_prompt, user_prompt):
        self.prompts.append(user_prompt)
        if self.fail:
            raise LLMAPIError("LLM API returned HTTP 404")
        return {
            "chunk_id": "WRONG",
            "problems": [{"id": "prob_1", "confidence": 0.9, "description": "Need vector search"}],
            "alternatives": [{"id": "alt_1", "confidence": 0.9, "name": "PostgreSQL"}],
            "rationales": [
                {"id": "rat_1", "confidence": 0.8, "reason": "pgvector", "stance": "supports", "target_alternative": "alt_1"}
            ],
            "decisions": [
                {"id": "dec_1", "confidence": 0.9, "statement": "Use PostgreSQL" if n == 0 else f"Use PostgreSQL ({n})", "chosen_alternative": "PostgreSQL"}
                for n in range(self.decision_count)
            ],
            "actions": [{"id": "act_1", "confidence": 0.9, "task": "Migrate data", "assignee": "Bob", "deadline": "Friday"}],
            "people": [{"id": "per_1", "confidence": 0.9, "name": "Bob"}],
            "outcomes": [],
        }

    def generate_text(self, system_prompt, user_prompt):
        return ""


class FakeTx:
    def __init__(self, driver):
        self.driver = driver

    def run(self, query, **params):
        self.driver.tx_runs.append((query, params))


class FakeSession:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_write(self, fn):
        if self.driver.write_error:
            raise self.driver.write_error
        fn(FakeTx(self.driver))

    def run(self, query, **params):
        if "MADE_IN" in query and "collect(d.decision_id)" in query:
            return self.driver.decisions_by_source_result()
        if self.driver.cleanup_error:
            raise self.driver.cleanup_error
        self.driver.cleanup_runs.append((query, params))
        if "DETACH DELETE s" in query:
            self.driver.removed_sources.add(params["source_id"])

        class _Result:
            def consume(self):
                return None

        return _Result()


class FakeDriver:
    def __init__(self, write_error=None, cleanup_error=None):
        self.write_error = write_error
        self.cleanup_error = cleanup_error
        self.tx_runs = []
        self.cleanup_runs = []
        self.removed_sources = set()

    def session(self):
        return FakeSession(self)

    def decisions_by_source_result(self):
        """What MATCH (d:Decision)-[:MADE_IN]->(s:Source) would return for the data written so far."""
        grouped = {}
        for query, params in self.tx_runs:
            if query == MERGE_DECISION_QUERY and params["source_id"] not in self.removed_sources:
                grouped.setdefault(params["source_id"], []).append(params["decision_id"])
        rows = [{"source_id": sid, "decision_ids": ids} for sid, ids in grouped.items()]

        class _Result:
            def data(self):
                return rows

        return _Result()


@pytest.fixture
def pipeline(isolated_db, monkeypatch):
    """Wire fakes into the pipeline; returns (client, llm, driver, connect)."""
    llm = FakeLLM()
    driver = FakeDriver()
    monkeypatch.setattr(extraction_service, "get_default_llm_client", lambda: llm)
    monkeypatch.setattr(graph_service, "get_neo4j_driver", lambda: driver)
    monkeypatch.setattr(service, "get_neo4j_driver", lambda: driver)
    set_embedding_model(MockEmbeddingModel())
    yield TestClient(app), llm, driver, isolated_db
    set_embedding_model(None)


def _upload(client, name="meeting.txt", content=TRANSCRIPT):
    return client.post("/api/ingestion/upload", files={"file": (name, content.encode(), "text/plain")})


def _count(connect, table):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table};")
        return cur.fetchone()[0]


# --------------------------------------------------------------------------- success path
def test_successful_upload_runs_every_stage(pipeline):
    client, llm, driver, connect = pipeline

    response = _upload(client)
    assert response.status_code == 201
    body = response.json()

    # existing contract preserved
    assert body["status"] == "success"
    assert {"source_id", "source_type", "title", "number_of_chunks"} <= set(body)
    n_chunks = body["number_of_chunks"]
    assert n_chunks >= 1

    # extraction invoked once per chunk
    assert len(llm.prompts) == n_chunks
    # entities written to the graph and reported
    assert body["entity_counts"]["decisions"] == n_chunks
    assert body["entity_counts"]["actions"] == n_chunks
    # embeddings generated and stored in pgvector
    assert body["number_of_embeddings"] == n_chunks
    assert _count(connect, "document_embeddings") == n_chunks
    assert _count(connect, "chunks") == n_chunks


def test_provenance_is_preserved_from_postgres_to_graph(pipeline):
    client, llm, driver, connect = pipeline
    body = _upload(client).json()
    source_id = body["source_id"]

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM chunks WHERE source_id = %s;", (source_id,))
        pg_chunk_ids = {row[0] for row in cur.fetchall()}

    # the prompt sent to the LLM carries the real chunk id
    for chunk_id in pg_chunk_ids:
        assert any(chunk_id in prompt for prompt in llm.prompts)

    runs = driver.tx_runs
    source_runs = [p for q, p in runs if q == MERGE_SOURCE_QUERY]
    chunk_runs = [p for q, p in runs if q == MERGE_CHUNK_QUERY]
    decision_runs = [p for q, p in runs if q == MERGE_DECISION_QUERY]

    assert {p["source_id"] for p in source_runs} == {source_id}
    assert {p["chunk_id"] for p in chunk_runs} == pg_chunk_ids
    # each extracted entity stays bound to the chunk it came from, and the source
    assert {p["chunk_id"] for p in decision_runs} == pg_chunk_ids
    assert {p["source_id"] for p in decision_runs} == {source_id}
    assert all(p["statement"] == "Use PostgreSQL" for p in decision_runs)


def test_extracted_entity_ids_do_not_collide_across_uploads(pipeline):
    client, llm, driver, connect = pipeline
    _upload(client, "a.txt")
    _upload(client, "b.txt")

    decision_ids = [p["decision_id"] for q, p in driver.tx_runs if q == MERGE_DECISION_QUERY]
    assert len(decision_ids) >= 2
    assert len(set(decision_ids)) == len(decision_ids)  # LLM said "dec_1" every time
    assert "dec_1" not in decision_ids
    assert all(d.startswith("dec_") for d in decision_ids)


def test_namespace_entity_ids_is_deterministic_and_keeps_alternative_references():
    def build():
        return ChunkExtraction.model_validate(
            {
                "chunk_id": "chk_abc",
                "alternatives": [{"id": "alt_1", "chunk_id": "chk_abc", "confidence": 1, "name": "X"}],
                "rationales": [
                    {"id": "rat_1", "chunk_id": "chk_abc", "confidence": 1, "reason": "r", "target_alternative": "alt_1"}
                ],
                "decisions": [
                    {"id": "dec_1", "chunk_id": "chk_abc", "confidence": 1, "statement": "s", "chosen_alternative": "alt_1"}
                ],
                "people": [{"id": "per_1", "chunk_id": "chk_abc", "confidence": 1, "name": "Bob"}],
            }
        )

    first, second = build(), build()
    service.namespace_entity_ids(first)
    service.namespace_entity_ids(second)

    assert first.alternatives[0].id == second.alternatives[0].id != "alt_1"
    # references that pointed at the old alternative id follow the new one
    assert first.rationales[0].target_alternative == first.alternatives[0].id
    assert first.decisions[0].chosen_alternative == first.alternatives[0].id
    # people use the graph service's deterministic name-based id (shared across documents)
    assert first.people[0].id == graph_service.make_deterministic_person_id("Bob")


# --------------------------------------------------------------------------- failure paths
def _assert_nothing_persisted(connect):
    assert _count(connect, "sources") == 0
    assert _count(connect, "chunks") == 0
    assert _count(connect, "document_embeddings") == 0


def test_extraction_failure_is_not_reported_as_success(pipeline):
    client, llm, driver, connect = pipeline
    llm.fail = True

    response = _upload(client)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "extraction failed" in detail.lower()
    assert "rolled back" in detail
    _assert_nothing_persisted(connect)
    assert driver.tx_runs == []  # nothing reached Neo4j


def test_graph_failure_is_reported_and_rolled_back(pipeline):
    client, llm, driver, connect = pipeline
    driver.write_error = RuntimeError("tx boom")

    response = _upload(client)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "knowledge graph" in detail.lower()
    assert "rolled back" in detail
    _assert_nothing_persisted(connect)
    # compensating cleanup was issued against Neo4j
    assert any("DETACH DELETE s" in q for q, _ in driver.cleanup_runs)


def test_neo4j_unavailable_returns_503(pipeline):
    client, llm, driver, connect = pipeline
    driver.write_error = ServiceUnavailable("down")

    response = _upload(client)

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
    _assert_nothing_persisted(connect)


def test_embedding_failure_is_reported_and_rolled_back(pipeline, monkeypatch):
    client, llm, driver, connect = pipeline

    def broken(chunks, model=None):
        raise embedding_service.VectorStorageError("pgvector write failed")

    monkeypatch.setattr(embedding_service, "batch_embed_and_store_chunks", broken)

    response = _upload(client)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "embedding" in detail.lower()
    assert "rolled back" in detail
    _assert_nothing_persisted(connect)
    # graph data had been written, so it is cleaned up too
    assert driver.tx_runs
    assert any("DETACH DELETE s" in q for q, _ in driver.cleanup_runs)


def test_incomplete_rollback_is_disclosed(pipeline, monkeypatch):
    client, llm, driver, connect = pipeline
    llm.fail = True
    monkeypatch.setattr(service, "_rollback_ingestion", lambda source_id, graph_touched: False)

    response = _upload(client)

    assert response.status_code == 502
    assert "rollback was incomplete" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- idempotency
def test_embedding_upsert_is_idempotent(isolated_db):
    set_embedding_model(MockEmbeddingModel())
    try:
        source_id = "src_idem"
        from app.ingestion.models import ChunkRecord, ExtractedSegment, ExtractionResult

        extraction = ExtractionResult(
            title="t", source_type="txt", segments=[ExtractedSegment(text="x")], raw_text="x"
        )
        chunk = ChunkRecord(chunk_id="chk_idem", source_id=source_id, text="same text")
        service.persist_source_and_chunks(source_id, extraction, [chunk])

        assert embedding_service.batch_embed_and_store_chunks([chunk]) == 1
        assert embedding_service.batch_embed_and_store_chunks([chunk]) == 1
        assert _count(isolated_db, "document_embeddings") == 1
    finally:
        set_embedding_model(None)


# --------------------------------------------------------------------------- deletion
def test_delete_removes_postgres_pgvector_and_graph_data(pipeline):
    client, llm, driver, connect = pipeline
    source_id = _upload(client).json()["source_id"]
    assert _count(connect, "document_embeddings") >= 1
    driver.cleanup_runs.clear()

    response = client.delete(f"/api/ingestion/sources/{source_id}")

    assert response.status_code == 200
    assert response.json() == {"source_id": source_id, "status": "deleted"}
    _assert_nothing_persisted(connect)
    assert client.get("/api/ingestion/sources").json() == []
    # graph data for exactly this source was removed, and now-orphaned people were swept
    removals = [p for q, p in driver.cleanup_runs if "DETACH DELETE s" in q]
    assert removals == [{"source_id": source_id}]
    assert any("MATCH (p:Person)" in q for q, _ in driver.cleanup_runs)


def test_delete_only_removes_the_requested_source(pipeline):
    client, llm, driver, connect = pipeline
    keep = _upload(client, "keep.txt").json()
    drop = _upload(client, "drop.txt").json()

    assert client.delete(f"/api/ingestion/sources/{drop['source_id']}").status_code == 200

    remaining = client.get("/api/ingestion/sources").json()
    assert [s["source_id"] for s in remaining] == [keep["source_id"]]
    assert _count(connect, "chunks") == keep["number_of_chunks"]
    assert _count(connect, "document_embeddings") == keep["number_of_embeddings"]


def test_delete_unknown_source_returns_404_without_touching_neo4j(pipeline):
    client, llm, driver, connect = pipeline

    response = client.delete("/api/ingestion/sources/src_does_not_exist")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    assert driver.cleanup_runs == []


@pytest.mark.parametrize(
    "error, expected_status",
    [(RuntimeError("cypher boom"), 500), (ServiceUnavailable("down"), 503)],
)
def test_delete_graph_failure_keeps_the_document_for_retry(pipeline, error, expected_status):
    client, llm, driver, connect = pipeline
    source_id = _upload(client).json()["source_id"]
    driver.cleanup_error = error

    response = client.delete(f"/api/ingestion/sources/{source_id}")

    assert response.status_code == expected_status
    assert "not removed" in response.json()["detail"].lower()
    # nothing deleted from PostgreSQL, so the user still sees it and can retry
    assert [s["source_id"] for s in client.get("/api/ingestion/sources").json()] == [source_id]
    assert _count(connect, "document_embeddings") >= 1

    driver.cleanup_error = None
    assert client.delete(f"/api/ingestion/sources/{source_id}").status_code == 200
    _assert_nothing_persisted(connect)


def test_delete_postgres_failure_returns_503(pipeline, monkeypatch):
    client, llm, driver, connect = pipeline
    source_id = _upload(client).json()["source_id"]

    def broken(source_id):
        raise RuntimeError("pg boom")

    monkeypatch.setattr(service, "_remove_source_from_postgres", broken)

    response = client.delete(f"/api/ingestion/sources/{source_id}")
    assert response.status_code == 503


# --------------------------------------------------------------------------- decision ids
def _persisted_decision_ids(driver, source_id):
    return [p["decision_id"] for q, p in driver.tx_runs if q == MERGE_DECISION_QUERY and p["source_id"] == source_id]


def test_upload_response_contains_the_persisted_decision_id(pipeline):
    client, llm, driver, connect = pipeline

    body = _upload(client).json()

    assert isinstance(body["decision_ids"], list) and len(body["decision_ids"]) == 1
    assert body["decision_ids"][0].startswith("dec_")
    # exactly the id written to Neo4j, not a derived or invented one
    assert body["decision_ids"] == _persisted_decision_ids(driver, body["source_id"])
    # existing fields are untouched
    assert body["status"] == "success"
    assert {"source_id", "source_type", "title", "number_of_chunks", "entity_counts", "number_of_embeddings"} <= set(body)


def test_multiple_decisions_are_all_returned(pipeline):
    client, llm, driver, connect = pipeline
    llm.decision_count = 2  # the model reuses "dec_1" for both: ids must still be distinct

    body = _upload(client).json()

    assert len(body["decision_ids"]) == 2 * body["number_of_chunks"]
    assert len(set(body["decision_ids"])) == len(body["decision_ids"])
    assert body["decision_ids"] == _persisted_decision_ids(driver, body["source_id"])


def test_document_without_decisions_returns_an_empty_list(pipeline):
    client, llm, driver, connect = pipeline
    llm.decision_count = 0

    body = _upload(client).json()
    assert body["status"] == "success"
    assert body["decision_ids"] == []

    listed = {s["source_id"]: s for s in client.get("/api/ingestion/sources").json()}
    assert listed[body["source_id"]]["decision_ids"] == []


def test_sources_listing_returns_the_same_decision_ids_as_the_upload(pipeline):
    client, llm, driver, connect = pipeline
    llm.decision_count = 2
    first = _upload(client, "a.txt").json()
    llm.decision_count = 1
    second = _upload(client, "b.txt").json()

    listed = {s["source_id"]: s["decision_ids"] for s in client.get("/api/ingestion/sources").json()}

    assert listed[first["source_id"]] == first["decision_ids"]
    assert listed[second["source_id"]] == second["decision_ids"]
    assert not set(listed[first["source_id"]]) & set(listed[second["source_id"]])


def test_deleted_document_no_longer_lists_decisions(pipeline):
    client, llm, driver, connect = pipeline
    keep = _upload(client, "keep.txt").json()
    drop = _upload(client, "drop.txt").json()

    assert client.delete(f"/api/ingestion/sources/{drop['source_id']}").status_code == 200

    listed = {s["source_id"]: s["decision_ids"] for s in client.get("/api/ingestion/sources").json()}
    assert listed == {keep["source_id"]: keep["decision_ids"]}


def test_failed_upload_exposes_no_decision_ids(pipeline):
    client, llm, driver, connect = pipeline
    driver.write_error = RuntimeError("tx boom")

    assert _upload(client).status_code == 500
    assert client.get("/api/ingestion/sources").json() == []


# --------------------------------------------------------------------------- empty LLM responses
def test_empty_llm_response_twice_fails_the_upload_clearly_and_rolls_back(pipeline, monkeypatch):
    from app.extraction.llm_client import LLMEmptyResponseError

    client, llm, driver, connect = pipeline
    calls = []

    class EmptyLLM:
        def generate_json(self, system_prompt, user_prompt):
            calls.append(user_prompt)
            raise LLMEmptyResponseError("LLM returned an empty response")

        def generate_text(self, system_prompt, user_prompt):
            return ""

    monkeypatch.setattr(extraction_service, "get_default_llm_client", lambda: EmptyLLM())

    response = _upload(client)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "empty response" in detail and "retried once" in detail and "rolled back" in detail
    assert len(calls) == 2  # the chunk was tried, then retried once
    assert driver.tx_runs == []  # no entities were invented or written
    _assert_nothing_persisted(connect)


def test_an_empty_first_llm_response_is_retried_during_upload(pipeline, monkeypatch):
    from app.extraction.llm_client import LLMEmptyResponseError

    client, llm, driver, connect = pipeline
    real_generate = llm.generate_json
    attempts = {"n": 0}

    def flaky(system_prompt, user_prompt):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise LLMEmptyResponseError("LLM returned an empty response")
        return real_generate(system_prompt, user_prompt)

    monkeypatch.setattr(llm, "generate_json", flaky)

    response = _upload(client)

    assert response.status_code == 201
    assert response.json()["status"] == "success"
    assert attempts["n"] == response.json()["number_of_chunks"] + 1  # one extra call: the retry

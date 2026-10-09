"""Unit tests for embedding generation, pgvector storage, and semantic similarity search."""
import sys
from pathlib import Path
from typing import List, Tuple, Any
import pytest

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.embeddings.model import MockEmbeddingModel
from app.embeddings.models import VectorSearchResult
from app.embeddings.service import (
    embed_text,
    embed_texts,
    validate_embedding_dimension,
    format_vector_param,
    VectorSearchError,
    VectorStorageError,
)


class MockPostgresCursor:
    """Mock PostgreSQL cursor recording executed SQL statements and parameters."""

    def __init__(self, fetch_data: Any = None):
        self.executed_queries: List[Tuple[str, Any]] = []
        self.executemany_queries: List[Tuple[str, List[Any]]] = []
        self.fetch_data = fetch_data or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, sql: str, params: Any = None):
        self.executed_queries.append((sql.strip(), params))

    def executemany(self, sql: str, params_list: List[Any]):
        self.executemany_queries.append((sql.strip(), params_list))

    def fetchall(self):
        return self.fetch_data

    def fetchone(self):
        if self.fetch_data:
            return self.fetch_data[0]
        return None


class MockPostgresConnection:
    """Mock PostgreSQL connection context manager."""

    def __init__(self, cursor: MockPostgresCursor):
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass


def test_single_text_embedding_shape_and_norm():
    model = MockEmbeddingModel(dimension=1024)
    vector = embed_text("PostgreSQL vector storage for decision intelligence", model=model)

    assert isinstance(vector, list)
    assert len(vector) == 1024
    # Ensure vector values are non-zero floats
    assert any(abs(v) > 0 for v in vector)


def test_batch_embedding_shape():
    model = MockEmbeddingModel(dimension=1024)
    texts = [
        "First meeting segment regarding database options.",
        "Second meeting segment regarding Neo4j graph structure.",
        "Third segment on action items and deadlines.",
    ]
    vectors = embed_texts(texts, model=model)

    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 1024


def test_dimension_validation():
    valid_vec = [0.1] * 1024
    invalid_short_vec = [0.1] * 512
    invalid_long_vec = [0.1] * 1536

    # Should pass without error
    validate_embedding_dimension(valid_vec, expected_dim=1024)

    # Should fail for incorrect lengths
    with pytest.raises(ValueError) as exc_info:
        validate_embedding_dimension(invalid_short_vec, expected_dim=1024)
    assert "dimension mismatch" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        validate_embedding_dimension(invalid_long_vec, expected_dim=1024)
    assert "dimension mismatch" in str(exc_info.value)


def test_empty_text_handling():
    model = MockEmbeddingModel(dimension=1024)
    empty_vec = embed_text("", model=model)
    whitespace_vec = embed_text("   ", model=model)

    assert len(empty_vec) == 1024
    assert all(x == 0.0 for x in empty_vec)
    assert len(whitespace_vec) == 1024
    assert all(x == 0.0 for x in whitespace_vec)


def test_format_vector_param():
    vec = [0.12345678, -0.98765432, 0.0]
    param_str = format_vector_param(vec)
    assert param_str == "[0.12345678,-0.98765432,0.00000000]"


def test_idempotent_embedding_storage_query(monkeypatch):
    from app.embeddings import service

    mock_cursor = MockPostgresCursor(fetch_data=[(1,)])  # Chunk exists
    mock_conn = MockPostgresConnection(mock_cursor)

    monkeypatch.setattr(service, "get_postgres_connection", lambda: mock_conn)

    service.store_chunk_embedding("chk_test_01", [0.05] * 1024)

    queries = mock_cursor.executed_queries
    assert len(queries) == 2

    # 1. Existence check
    assert "SELECT 1 FROM chunks WHERE chunk_id = %s" in queries[0][0]
    assert queries[0][1] == ("chk_test_01",)

    # 2. Idempotent upsert
    upsert_sql = queries[1][0]
    assert "INSERT INTO document_embeddings" in upsert_sql
    assert "ON CONFLICT (chunk_id)" in upsert_sql
    assert "DO UPDATE SET embedding = EXCLUDED.embedding" in upsert_sql
    assert queries[1][1][0] == "chk_test_01"


def test_batch_embed_and_store_chunks(monkeypatch):
    from app.embeddings import service

    mock_cursor = MockPostgresCursor()
    mock_conn = MockPostgresConnection(mock_cursor)
    mock_model = MockEmbeddingModel(dimension=1024)

    monkeypatch.setattr(service, "get_postgres_connection", lambda: mock_conn)

    chunks = [
        {"chunk_id": "chk_1", "text": "Text 1"},
        {"chunk_id": "chk_2", "text": "Text 2"},
    ]

    stored_count = service.batch_embed_and_store_chunks(chunks, model=mock_model)
    assert stored_count == 2

    assert len(mock_cursor.executemany_queries) == 1
    sql, rows = mock_cursor.executemany_queries[0]
    assert "ON CONFLICT (chunk_id)" in sql
    assert len(rows) == 2
    assert rows[0][0] == "chk_1"
    assert rows[1][0] == "chk_2"


def test_semantic_search_query_construction_and_result_parsing(monkeypatch):
    from app.embeddings import service

    mock_row = (
        "chk_101",
        "src_001",
        "Discussion on pgvector cosine similarity index.",
        "Rahul",
        "00:03:30",
        "00:04:15",
        None,
        150,
        320,
        0.15,  # distance
        0.85,  # similarity_score
    )
    mock_cursor = MockPostgresCursor(fetch_data=[mock_row])
    mock_conn = MockPostgresConnection(mock_cursor)
    mock_model = MockEmbeddingModel(dimension=1024)

    monkeypatch.setattr(service, "get_postgres_connection", lambda: mock_conn)

    results = service.search_similar_chunks(
        query="Which vector database did we select?",
        top_k=5,
        model=mock_model,
    )

    assert len(results) == 1
    res = results[0]
    assert isinstance(res, VectorSearchResult)
    assert res.chunk_id == "chk_101"
    assert res.source_id == "src_001"
    assert res.speaker == "Rahul"
    assert res.start_ts == "00:03:30"
    assert res.similarity_score == 0.85
    assert res.distance == 0.15

    # Check SQL
    sql, params = mock_cursor.executed_queries[0]
    assert "(de.embedding <=> %s::vector) AS distance" in sql
    assert "JOIN chunks c ON de.chunk_id = c.chunk_id" in sql
    assert "ORDER BY distance ASC" in sql
    assert "LIMIT %s" in sql
    assert params[2] == 5


def test_search_query_validation():
    with pytest.raises(ValueError) as exc_info:
        from app.embeddings.service import search_similar_chunks
        search_similar_chunks("", top_k=5)
    assert "query cannot be empty" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        from app.embeddings.service import search_similar_chunks
        search_similar_chunks("valid query", top_k=0)
    assert "top_k must be greater than 0" in str(exc_info.value)


if __name__ == "__main__":
    test_single_text_embedding_shape_and_norm()
    test_batch_embedding_shape()
    test_dimension_validation()
    test_empty_text_handling()
    test_format_vector_param()
    test_idempotent_embedding_storage_query()
    test_batch_embed_and_store_chunks()
    test_semantic_search_query_construction_and_result_parsing()
    test_search_query_validation()
    print("All vector embedding and semantic search tests passed successfully!")

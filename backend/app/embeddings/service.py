"""Vector embedding and semantic search service."""
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any

from app.core.config import settings
from app.db.postgres import get_postgres_connection
from app.ingestion.models import ChunkRecord
from app.embeddings.models import VectorSearchResult
from app.embeddings.model import BaseEmbeddingModel, get_embedding_model


class VectorSearchError(Exception):
    """Base exception for vector search operations."""
    pass


class VectorStorageError(Exception):
    """Base exception for vector storage operations."""
    pass


def format_vector_param(embedding: List[float]) -> str:
    """Format Python float list into pgvector string representation."""
    return f"[{','.join(f'{x:.8f}' for x in embedding)}]"


def validate_embedding_dimension(
    embedding: List[float],
    expected_dim: int = settings.embedding_dimension,
) -> None:
    """Validate that vector matches the expected dimension."""
    if not isinstance(embedding, list):
        raise ValueError(f"Expected embedding to be a list, got {type(embedding).__name__}")
    if len(embedding) != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(embedding)}"
        )


def embed_text(
    text: str,
    model: Optional[BaseEmbeddingModel] = None,
) -> List[float]:
    """Embed a single text string into a 1024-dimensional normalized vector."""
    active_model = model or get_embedding_model()
    vector = active_model.embed_text(text)
    validate_embedding_dimension(vector, expected_dim=active_model.dimension)
    return vector


def embed_texts(
    texts: List[str],
    model: Optional[BaseEmbeddingModel] = None,
) -> List[List[float]]:
    """Embed a batch of text strings into normalized vectors."""
    if not texts:
        return []
    active_model = model or get_embedding_model()
    vectors = active_model.embed_texts(texts)
    for v in vectors:
        validate_embedding_dimension(v, expected_dim=active_model.dimension)
    return vectors


def store_chunk_embedding(
    chunk_id: str,
    embedding: List[float],
) -> None:
    """Store or update a vector embedding for an existing chunk in PostgreSQL."""
    if not chunk_id or not chunk_id.strip():
        raise ValueError("chunk_id must be a non-empty string.")
    validate_embedding_dimension(embedding)

    now = datetime.now(timezone.utc)
    vector_str = format_vector_param(embedding)

    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                # 1. Verify chunk existence
                cur.execute("SELECT 1 FROM chunks WHERE chunk_id = %s;", (chunk_id,))
                if cur.fetchone() is None:
                    raise VectorStorageError(f"Cannot store embedding: chunk_id '{chunk_id}' does not exist.")

                # 2. Idempotent upsert into document_embeddings
                cur.execute(
                    """
                    INSERT INTO document_embeddings (chunk_id, embedding, created_at)
                    VALUES (%s, %s::vector, %s)
                    ON CONFLICT (chunk_id)
                    DO UPDATE SET embedding = EXCLUDED.embedding, created_at = EXCLUDED.created_at;
                    """,
                    (chunk_id, vector_str, now),
                )
            conn.commit()
    except Exception as e:
        if isinstance(e, (ValueError, VectorStorageError)):
            raise
        raise VectorStorageError(f"Failed to persist chunk embedding: {e}") from e


def batch_embed_and_store_chunks(
    chunks: List[Union[ChunkRecord, Dict[str, Any]]],
    model: Optional[BaseEmbeddingModel] = None,
) -> int:
    """Batch embed a list of chunks and persist vectors atomically in PostgreSQL."""
    if not chunks:
        return 0

    chunk_ids: List[str] = []
    texts: List[str] = []

    for c in chunks:
        if isinstance(c, ChunkRecord):
            chunk_ids.append(c.chunk_id)
            texts.append(c.text)
        elif isinstance(c, dict):
            chunk_ids.append(c.get("chunk_id", ""))
            texts.append(c.get("text", ""))

    # Validate non-empty chunk IDs
    for cid in chunk_ids:
        if not cid or not cid.strip():
            raise ValueError("All chunks must have a valid non-empty chunk_id.")

    # 1. Generate embeddings in batch
    embeddings = embed_texts(texts, model=model)

    now = datetime.now(timezone.utc)
    rows = [(cid, format_vector_param(emb), now) for cid, emb in zip(chunk_ids, embeddings)]

    # 2. Atomic bulk upsert
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO document_embeddings (chunk_id, embedding, created_at)
                    VALUES (%s, %s::vector, %s)
                    ON CONFLICT (chunk_id)
                    DO UPDATE SET embedding = EXCLUDED.embedding, created_at = EXCLUDED.created_at;
                    """,
                    rows,
                )
            conn.commit()
    except Exception as e:
        raise VectorStorageError(f"Failed to batch persist embeddings: {e}") from e

    return len(rows)


def search_similar_chunks(
    query: str,
    top_k: int = 5,
    model: Optional[BaseEmbeddingModel] = None,
) -> List[VectorSearchResult]:
    """Search PostgreSQL using pgvector cosine distance and return top-k similar chunks with provenance."""
    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    # 1. Embed query
    query_vector = embed_text(query, model=model)
    query_vector_str = format_vector_param(query_vector)

    sql = """
    SELECT
        c.chunk_id,
        c.source_id,
        c.text,
        c.speaker,
        c.start_ts,
        c.end_ts,
        c.page,
        c.char_start,
        c.char_end,
        (de.embedding <=> %s::vector) AS distance,
        (1.0 - (de.embedding <=> %s::vector)) AS similarity_score
    FROM document_embeddings de
    JOIN chunks c ON de.chunk_id = c.chunk_id
    ORDER BY distance ASC
    LIMIT %s;
    """

    results: List[VectorSearchResult] = []
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (query_vector_str, query_vector_str, top_k))
                rows = cur.fetchall()

                for row in rows:
                    results.append(
                        VectorSearchResult(
                            chunk_id=row[0],
                            source_id=row[1],
                            text=row[2],
                            speaker=row[3],
                            start_ts=row[4],
                            end_ts=row[5],
                            page=row[6],
                            char_start=row[7],
                            char_end=row[8],
                            distance=float(row[9]),
                            similarity_score=float(row[10]),
                        )
                    )
    except Exception as e:
        raise VectorSearchError(f"Vector similarity search failed: {e}") from e

    return results

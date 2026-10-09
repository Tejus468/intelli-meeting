"""PostgreSQL schema initialization module."""
import sys
from app.core.config import settings
from app.db.postgres import get_postgres_connection


def get_postgres_schema_sql(dimension: int = settings.embedding_dimension) -> str:
    """Generate SQL statements for PostgreSQL schema with pgvector."""
    return f"""
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Table: sources (provenance layer for transcripts, PDFs, DOCX, TXT)
CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(255) UNIQUE NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    source_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: chunks (granular text segments traceable to sources)
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(255) UNIQUE NOT NULL,
    source_id VARCHAR(255) NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    speaker VARCHAR(255),
    start_ts VARCHAR(50),
    end_ts VARCHAR(50),
    page INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: document_embeddings (dense vector representation per chunk)
CREATE TABLE IF NOT EXISTS document_embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(255) UNIQUE NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding vector({dimension}),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""


def init_postgres_db(dimension: int = settings.embedding_dimension) -> None:
    """Execute PostgreSQL schema creation."""
    sql = get_postgres_schema_sql(dimension=dimension)
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


if __name__ == "__main__":
    try:
        print("Initializing PostgreSQL schema...")
        init_postgres_db()
        print("PostgreSQL schema initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize PostgreSQL schema: {e}", file=sys.stderr)
        sys.exit(1)

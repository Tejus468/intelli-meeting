"""Shared fixtures: real PostgreSQL in a throwaway schema, so existing data is never touched."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.db.init_postgres import get_postgres_schema_sql
from app.db.postgres import get_postgres_connection


@pytest.fixture
def isolated_db(monkeypatch):
    """Create a throwaway schema with the real sources/chunks/document_embeddings DDL."""
    from app.embeddings import service as embedding_service
    from app.ingestion import service as ingestion_service

    schema = f"test_iso_{uuid.uuid4().hex[:10]}"
    try:
        admin = get_postgres_connection(connect_timeout=3)
    except Exception as e:
        pytest.skip(f"PostgreSQL not reachable: {e}")

    with admin.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}";')
    admin.commit()

    def connect():
        conn = get_postgres_connection()
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}", public;')
        conn.commit()
        return conn

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(get_postgres_schema_sql())
        conn.commit()

    monkeypatch.setattr(ingestion_service, "get_postgres_connection", connect)
    monkeypatch.setattr(embedding_service, "get_postgres_connection", connect)
    try:
        yield connect
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE;')
        admin.commit()
        admin.close()

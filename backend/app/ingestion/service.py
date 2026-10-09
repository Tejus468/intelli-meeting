"""Ingestion orchestrator service with atomic database persistence."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from neo4j.exceptions import ServiceUnavailable
from app.db.neo4j import get_neo4j_driver
from app.db.postgres import get_postgres_connection
from app.ingestion.models import (
    ExtractionResult,
    ChunkRecord,
    IngestionResponse,
    SourceSummary,
)
from app.ingestion.extractors import extract_document
from app.ingestion.chunker import create_chunks


class IngestionError(Exception):
    """Custom exception raised for ingestion pipeline failures."""
    pass


class IngestionDatabaseError(IngestionError):
    """Raised when database operations during ingestion fail."""
    pass


class SourceNotFoundError(IngestionError):
    """Raised when the requested source does not exist."""
    pass


class IngestionPipelineError(IngestionError):
    """A post-persistence stage (extraction, graph, embeddings) failed; ingestion was not completed."""

    stage = "pipeline"
    status_code = 500


class IngestionExtractionError(IngestionPipelineError):
    stage = "extraction"
    status_code = 502  # upstream LLM problem


class IngestionGraphError(IngestionPipelineError):
    stage = "graph"
    status_code = 500


class IngestionGraphUnavailableError(IngestionGraphError):
    status_code = 503  # Neo4j unreachable


class IngestionEmbeddingError(IngestionPipelineError):
    stage = "embedding"
    status_code = 500


logger = logging.getLogger(__name__)

_ENTITY_ID_PREFIXES = {
    "problems": "prob",
    "alternatives": "alt",
    "rationales": "rat",
    "decisions": "dec",
    "actions": "act",
    "outcomes": "out",
}

# Removes a source, its chunks and the entities evidenced by them. Person nodes are shared across
# documents by name, so they are handled separately (see _ORPHAN_PEOPLE_QUERY).
_REMOVE_SOURCE_GRAPH_QUERY = """
MATCH (s:Source {source_id: $source_id})
OPTIONAL MATCH (s)-[:HAS_CHUNK]->(c:Chunk)
OPTIONAL MATCH (e)-[:EVIDENCED_BY]->(c) WHERE NOT e:Person
WITH s, collect(DISTINCT c) AS chunks, collect(DISTINCT e) AS entities
FOREACH (x IN entities | DETACH DELETE x)
FOREACH (x IN chunks | DETACH DELETE x)
DETACH DELETE s
"""

# Decisions per source, via the existing (Decision)-[:MADE_IN]->(Source) relationship.
_DECISIONS_BY_SOURCE_QUERY = """
MATCH (d:Decision)-[:MADE_IN]->(s:Source)
WITH s, d ORDER BY d.created_at, d.decision_id
RETURN s.source_id AS source_id, collect(d.decision_id) AS decision_ids
"""

# People no longer connected to anything (only mentioned in the removed document).
_ORPHAN_PEOPLE_QUERY = "MATCH (p:Person) WHERE NOT (p)--() DELETE p"


def persist_source_and_chunks(
    source_id: str,
    extraction: ExtractionResult,
    chunks: List[ChunkRecord],
) -> datetime:
    """Store source and chunk records atomically in PostgreSQL; returns the stored source_date."""
    now = datetime.now(timezone.utc)
    source_date = extraction.source_date or now

    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                # 1. Insert into sources
                cur.execute(
                    """
                    INSERT INTO sources (source_id, source_type, title, source_date, created_at)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (
                        source_id,
                        extraction.source_type,
                        extraction.title,
                        source_date,
                        now,
                    ),
                )

                # 2. Bulk insert into chunks
                chunk_rows = [
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.text,
                        chunk.speaker,
                        chunk.start_ts,
                        chunk.end_ts,
                        chunk.page,
                        chunk.char_start,
                        chunk.char_end,
                        now,
                    )
                    for chunk in chunks
                ]

                cur.executemany(
                    """
                    INSERT INTO chunks (
                        chunk_id, source_id, text, speaker, start_ts, end_ts, page, char_start, char_end, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    chunk_rows,
                )

            conn.commit()
    except Exception as e:
        raise IngestionDatabaseError(f"Database persistence failed: {e}") from e

    return source_date


def _decision_ids_by_source() -> Dict[str, List[str]]:
    """Read persisted decision IDs per source from Neo4j (raises if the graph cannot be read)."""
    try:
        with get_neo4j_driver().session() as session:
            rows = session.run(_DECISIONS_BY_SOURCE_QUERY).data()
    except ServiceUnavailable as e:
        raise IngestionGraphUnavailableError(
            "Knowledge graph (Neo4j) is unavailable, so decision IDs could not be loaded."
        ) from e
    except Exception as e:
        raise IngestionGraphError(f"Could not load decision IDs from the knowledge graph: {e}") from e
    return {row["source_id"]: list(row["decision_ids"]) for row in rows}


def list_sources() -> List[SourceSummary]:
    """Return all persisted sources (newest first) with chunk counts derived from the chunks table."""
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT s.source_id, s.title, s.source_type, s.source_date, s.created_at,
                           COUNT(c.id) AS number_of_chunks
                    FROM sources s
                    LEFT JOIN chunks c ON c.source_id = s.source_id
                    GROUP BY s.id
                    ORDER BY s.created_at DESC, s.id DESC;
                    """
                )
                rows = cur.fetchall()
    except Exception as e:
        raise IngestionDatabaseError(f"Failed to list sources: {e}") from e

    decisions = _decision_ids_by_source()

    return [
        SourceSummary(
            source_id=row[0],
            title=row[1],
            source_type=row[2],
            source_date=row[3],
            created_at=row[4],
            number_of_chunks=row[5],
            decision_ids=decisions.get(row[0], []),
        )
        for row in rows
    ]


def namespace_entity_ids(extraction: Any) -> None:
    """Make extracted entity IDs unique per chunk (in place).

    The graph MERGEs nodes by entity id, and the LLM is asked for ids like "dec_<unique_id>" but
    commonly emits "dec_1" for every chunk. Left as-is, unrelated decisions/problems from different
    chunks or documents would collapse into one node. IDs are derived from (chunk_id, type, position),
    so re-persisting the same extraction of the same chunk stays idempotent. People get the graph
    service's own deterministic name-based id so the same person is shared across documents.
    """
    from app.graph.service import make_deterministic_person_id

    alt_id_map: Dict[str, str] = {}
    for kind, prefix in _ENTITY_ID_PREFIXES.items():
        for index, item in enumerate(getattr(extraction, kind)):
            digest = hashlib.sha256(f"{extraction.chunk_id}:{kind}:{index}".encode("utf-8")).hexdigest()[:12]
            if kind == "alternatives":
                alt_id_map[item.id] = f"{prefix}_{digest}"
            item.id = f"{prefix}_{digest}"

    # Keep rationale/decision references that pointed at an alternative by its (old) id working.
    for rationale in extraction.rationales:
        if rationale.target_alternative in alt_id_map:
            rationale.target_alternative = alt_id_map[rationale.target_alternative]
    for decision in extraction.decisions:
        if decision.chosen_alternative in alt_id_map:
            decision.chosen_alternative = alt_id_map[decision.chosen_alternative]

    for person in extraction.people:
        person.id = make_deterministic_person_id(person.name)


def _extract_all_chunks(chunks: List[ChunkRecord]) -> List[Any]:
    """Run LLM extraction on every chunk before anything is written to Neo4j."""
    from app.extraction import service as extraction_service

    results = []
    for chunk in chunks:
        try:
            result = extraction_service.extract_from_chunk(chunk)
        except Exception as e:
            raise IngestionExtractionError(
                f"Entity extraction failed on chunk {chunk.chunk_id}: {e}."
            ) from e
        namespace_entity_ids(result)
        results.append(result)
    return results


def _persist_graph(source: Dict[str, Any], chunks: List[ChunkRecord], extractions: List[Any]) -> Dict[str, int]:
    """Write each chunk's extraction to Neo4j; returns total entities written by type."""
    from app.graph import service as graph_service

    totals: Dict[str, int] = {}
    for chunk, extraction in zip(chunks, extractions):
        try:
            outcome = graph_service.persist_extraction_to_graph(source, chunk, extraction)
        except graph_service.GraphDatabaseUnavailableError as e:
            raise IngestionGraphUnavailableError(
                f"Knowledge graph (Neo4j) is unavailable while saving chunk {chunk.chunk_id}: {e}."
            ) from e
        except Exception as e:
            raise IngestionGraphError(
                f"Saving to the knowledge graph failed on chunk {chunk.chunk_id}: {e}."
            ) from e
        for entity_type, count in outcome.get("counts", {}).items():
            if entity_type not in ("sources", "chunks"):
                totals[entity_type] = totals.get(entity_type, 0) + count
    return totals


def _embed_chunks(chunks: List[ChunkRecord]) -> int:
    """Generate embeddings for all chunks and upsert them into pgvector."""
    from app.embeddings import service as embedding_service

    try:
        return embedding_service.batch_embed_and_store_chunks(chunks)
    except Exception as e:
        raise IngestionEmbeddingError(f"Embedding generation/storage failed: {e}.") from e


def _remove_source_from_graph(source_id: str) -> None:
    """Delete one source's data from Neo4j (raises on failure)."""
    with get_neo4j_driver().session() as session:
        session.run(_REMOVE_SOURCE_GRAPH_QUERY, source_id=source_id).consume()
        session.run(_ORPHAN_PEOPLE_QUERY).consume()


def _remove_source_from_postgres(source_id: str) -> None:
    """Delete one source row; its chunks and embeddings cascade (raises on failure)."""
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sources WHERE source_id = %s;", (source_id,))
        conn.commit()


def _rollback_ingestion(source_id: str, graph_touched: bool) -> bool:
    """Best-effort compensation after a failed stage. PostgreSQL and Neo4j cannot share a transaction,
    so remove what this ingestion wrote."""
    clean = True

    if graph_touched:
        try:
            _remove_source_from_graph(source_id)
        except Exception:
            clean = False
            logger.exception("Rollback of Neo4j data failed for source %s", source_id)

    try:
        _remove_source_from_postgres(source_id)
    except Exception:
        clean = False
        logger.exception("Rollback of PostgreSQL data failed for source %s", source_id)

    return clean


def delete_source(source_id: str) -> None:
    """Permanently remove a document: Neo4j graph data first, then PostgreSQL rows and embeddings.

    Graph data goes first so a Neo4j failure leaves the document fully intact (and listed) for a retry,
    rather than leaving graph data behind with no PostgreSQL record pointing at it.
    """
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM sources WHERE source_id = %s;", (source_id,))
                exists = cur.fetchone() is not None
    except Exception as e:
        raise IngestionDatabaseError(f"Failed to look up source: {e}") from e
    if not exists:
        raise SourceNotFoundError(f"Source '{source_id}' was not found.")

    try:
        _remove_source_from_graph(source_id)
    except ServiceUnavailable as e:
        raise IngestionGraphUnavailableError(
            "Knowledge graph (Neo4j) is unavailable, so the document was not removed. Try again once it is running."
        ) from e
    except Exception as e:
        raise IngestionGraphError(
            f"Could not remove the document's knowledge-graph data: {e}. The document was not removed."
        ) from e

    try:
        _remove_source_from_postgres(source_id)
    except Exception as e:
        raise IngestionDatabaseError(f"Failed to delete source from PostgreSQL: {e}") from e

    logger.info("Deleted source %s", source_id)


def ingest_file(file_bytes: bytes, filename: str) -> IngestionResponse:
    """Process an uploaded document/transcript end-to-end and persist to PostgreSQL."""
    if not file_bytes:
        raise IngestionError("Uploaded file is empty.")

    # 1. Extract content and provenance
    try:
        extraction = extract_document(file_bytes, filename)
    except ValueError as e:
        raise IngestionError(str(e)) from e

    if not extraction.segments:
        raise IngestionError("No extractable text segments found in the document.")

    # 2. Generate stable source identifier
    source_id = f"src_{uuid.uuid4().hex[:12]}"

    # 3. Create provenance-linked chunks
    chunks = create_chunks(extraction, source_id)
    if not chunks:
        raise IngestionError("Chunking produced zero chunks.")

    # 4. Atomically persist to PostgreSQL
    source_date = persist_source_and_chunks(source_id, extraction, chunks)

    # 5-7. Extraction -> Neo4j -> embeddings/pgvector. Any failure rolls back what this upload wrote
    # and is reported to the caller; a partially processed document is never reported as ingested.
    graph_touched = False
    try:
        extractions = _extract_all_chunks(chunks)

        graph_touched = True
        entity_counts = _persist_graph(
            {
                "source_id": source_id,
                "source_type": extraction.source_type,
                "title": extraction.title,
                "source_date": source_date,
            },
            chunks,
            extractions,
        )

        embedded = _embed_chunks(chunks)
        # the exact ids that were MERGEd into Neo4j above (see graph_service.persist_extraction_to_graph)
        decision_ids = [decision.id for result in extractions for decision in result.decisions]
    except IngestionPipelineError as e:
        logger.error("Ingestion of %s (%s) failed at %s stage: %s", source_id, filename, e.stage, e)
        rolled_back = _rollback_ingestion(source_id, graph_touched)
        suffix = (
            "The upload was rolled back; nothing was kept."
            if rolled_back
            else f"Automatic rollback was incomplete (source {source_id}); check server logs."
        )
        raise type(e)(f"{e} {suffix}") from e

    # 8. Build response
    return IngestionResponse(
        source_id=source_id,
        source_type=extraction.source_type,
        title=extraction.title,
        number_of_chunks=len(chunks),
        status="success",
        entity_counts=entity_counts,
        number_of_embeddings=embedded,
        decision_ids=decision_ids,
    )

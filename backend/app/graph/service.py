"""Graph persistence service for transforming extraction results into Neo4j knowledge graph."""
import hashlib
from typing import Dict, Any, Optional, Union, List
from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable, Neo4jError

from app.db.neo4j import get_neo4j_driver
from app.ingestion.models import ChunkRecord
from app.extraction.models import ExtractionResult
from app.graph.cypher import (
    MERGE_SOURCE_QUERY,
    MERGE_CHUNK_QUERY,
    MERGE_SPEAKER_QUERY,
    MERGE_PERSON_QUERY,
    MERGE_PROBLEM_QUERY,
    MERGE_ALTERNATIVE_QUERY,
    LINK_PROBLEM_ALTERNATIVE_QUERY,
    MERGE_RATIONALE_QUERY,
    LINK_RATIONALE_ALTERNATIVE_QUERY,
    MERGE_DECISION_QUERY,
    LINK_DECISION_PROBLEM_QUERY,
    LINK_DECISION_ALTERNATIVE_SELECTED_QUERY,
    LINK_DECISION_ALTERNATIVE_REJECTED_QUERY,
    LINK_DECISION_RATIONALE_QUERY,
    MERGE_ACTION_QUERY,
    LINK_DECISION_ACTION_QUERY,
    LINK_ACTION_PERSON_QUERY,
    MERGE_OUTCOME_QUERY,
    LINK_ACTION_OUTCOME_QUERY,
)


class GraphPersistenceError(Exception):
    """Base exception for graph persistence errors."""
    pass


class GraphMissingProvenanceError(GraphPersistenceError):
    """Raised when source or chunk provenance is missing or invalid."""
    pass


class GraphDatabaseUnavailableError(GraphPersistenceError):
    """Raised when the Neo4j database service is unreachable."""
    pass


def make_deterministic_person_id(name: str) -> str:
    """Generate stable person identifier from normalized person name."""
    clean = name.strip().lower()
    h = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]
    return f"per_{h}"


def persist_extraction_to_graph(
    source: Union[Dict[str, Any], Any],
    chunk: Union[ChunkRecord, Dict[str, Any]],
    extraction: ExtractionResult,
    driver: Optional[Driver] = None,
) -> Dict[str, Any]:
    """Atomically persist source, chunk, and extracted decision-intelligence entities into Neo4j."""
    # 1. Normalize Source properties
    if isinstance(source, dict):
        source_id = source.get("source_id")
        source_type = source.get("source_type", "transcript")
        title = source.get("title", "Untitled Document")
        source_date = source.get("source_date")
    else:
        source_id = getattr(source, "source_id", None)
        source_type = getattr(source, "source_type", "transcript")
        title = getattr(source, "title", "Untitled Document")
        source_date = getattr(source, "source_date", None)

    if not source_id:
        raise GraphMissingProvenanceError("Source must have a non-empty source_id.")

    # 2. Normalize Chunk properties
    if isinstance(chunk, ChunkRecord):
        chunk_id = chunk.chunk_id
        text = chunk.text
        speaker = chunk.speaker
        start_ts = chunk.start_ts
        end_ts = chunk.end_ts
        page = chunk.page
        char_start = chunk.char_start
        char_end = chunk.char_end
    elif isinstance(chunk, dict):
        chunk_id = chunk.get("chunk_id")
        text = chunk.get("text", "")
        speaker = chunk.get("speaker")
        start_ts = chunk.get("start_ts")
        end_ts = chunk.get("end_ts")
        page = chunk.get("page")
        char_start = chunk.get("char_start", 0)
        char_end = chunk.get("char_end", 0)
    else:
        raise GraphMissingProvenanceError("Chunk must be a ChunkRecord or dictionary.")

    if not chunk_id:
        raise GraphMissingProvenanceError("Chunk must have a non-empty chunk_id.")

    # 3. Provenance Verification
    if extraction.chunk_id != chunk_id:
        raise GraphMissingProvenanceError(
            f"Extraction chunk_id '{extraction.chunk_id}' does not match chunk '{chunk_id}'"
        )

    # Convert source_date to ISO string if datetime
    if source_date is not None and hasattr(source_date, "isoformat"):
        source_date_str = source_date.isoformat()
    elif source_date is not None:
        source_date_str = str(source_date)
    else:
        source_date_str = None

    active_driver = driver or get_neo4j_driver()

    counts = {
        "sources": 1,
        "chunks": 1,
        "people": len(extraction.people),
        "problems": len(extraction.problems),
        "alternatives": len(extraction.alternatives),
        "rationales": len(extraction.rationales),
        "decisions": len(extraction.decisions),
        "actions": len(extraction.actions),
        "outcomes": len(extraction.outcomes),
    }

    def _execute_tx(tx):
        # Step A: Merge Source
        tx.run(
            MERGE_SOURCE_QUERY,
            source_id=source_id,
            source_type=source_type,
            title=title,
            source_date=source_date_str,
        )

        # Step B: Merge Chunk & Link (Source)-[:HAS_CHUNK]->(Chunk)
        tx.run(
            MERGE_CHUNK_QUERY,
            source_id=source_id,
            chunk_id=chunk_id,
            text=text,
            speaker=speaker,
            start_ts=start_ts,
            end_ts=end_ts,
            page=page,
            char_start=char_start,
            char_end=char_end,
        )

        # Step C: Speaker link (Chunk)-[:SPOKEN_BY]->(Person)
        if speaker and speaker.strip():
            spk_id = make_deterministic_person_id(speaker)
            tx.run(
                MERGE_SPEAKER_QUERY,
                chunk_id=chunk_id,
                person_id=spk_id,
                name=speaker.strip(),
            )

        # Step D: Extracted People & (Person)-[:EVIDENCED_BY]->(Chunk)
        for p in extraction.people:
            p_id = p.id if p.id else make_deterministic_person_id(p.name)
            tx.run(
                MERGE_PERSON_QUERY,
                chunk_id=chunk_id,
                person_id=p_id,
                name=p.name,
                role=p.role,
                confidence=p.confidence,
            )

        # Step E: Extracted Problems & (Source)-[:DISCUSSED]->(Problem), (Problem)-[:EVIDENCED_BY]->(Chunk)
        for pr in extraction.problems:
            tx.run(
                MERGE_PROBLEM_QUERY,
                source_id=source_id,
                chunk_id=chunk_id,
                problem_id=pr.id,
                description=pr.description,
                confidence=pr.confidence,
            )

        # Step F: Extracted Alternatives & (Alternative)-[:EVIDENCED_BY]->(Chunk)
        for alt in extraction.alternatives:
            tx.run(
                MERGE_ALTERNATIVE_QUERY,
                chunk_id=chunk_id,
                alternative_id=alt.id,
                name=alt.name,
                description=alt.description,
                confidence=alt.confidence,
            )
            # Link (Problem)-[:CONSIDERED]->(Alternative)
            for pr in extraction.problems:
                tx.run(
                    LINK_PROBLEM_ALTERNATIVE_QUERY,
                    problem_id=pr.id,
                    alternative_id=alt.id,
                )

        # Step G: Extracted Rationales & (Rationale)-[:EVIDENCED_BY]->(Chunk), (Rationale)-[:SUPPORTS|OPPOSES]->(Alternative)
        for rat in extraction.rationales:
            tx.run(
                MERGE_RATIONALE_QUERY,
                chunk_id=chunk_id,
                rationale_id=rat.id,
                reason=rat.reason,
                stance=rat.stance or "supports",
                confidence=rat.confidence,
            )
            # Match target alternative if specified or single alternative
            target_alts: List[str] = []
            if rat.target_alternative:
                target_clean = rat.target_alternative.strip().lower()
                for alt in extraction.alternatives:
                    if alt.name.strip().lower() == target_clean or alt.id == rat.target_alternative:
                        target_alts.append(alt.id)
            elif len(extraction.alternatives) == 1:
                target_alts.append(extraction.alternatives[0].id)

            for alt_id in target_alts:
                tx.run(
                    LINK_RATIONALE_ALTERNATIVE_QUERY,
                    rationale_id=rat.id,
                    alternative_id=alt_id,
                    stance=rat.stance or "supports",
                )

        # Step H: Extracted Decisions & (Decision)-[:MADE_IN]->(Source), (Decision)-[:EVIDENCED_BY]->(Chunk)
        for dec in extraction.decisions:
            tx.run(
                MERGE_DECISION_QUERY,
                source_id=source_id,
                chunk_id=chunk_id,
                decision_id=dec.id,
                statement=dec.statement,
                status=dec.status or "agreed",
                confidence=dec.confidence,
            )

            # Link (Decision)-[:RESOLVES]->(Problem)
            for pr in extraction.problems:
                tx.run(
                    LINK_DECISION_PROBLEM_QUERY,
                    decision_id=dec.id,
                    problem_id=pr.id,
                )

            # Link (Decision)-[:JUSTIFIED_BY]->(Rationale)
            for rat in extraction.rationales:
                tx.run(
                    LINK_DECISION_RATIONALE_QUERY,
                    decision_id=dec.id,
                    rationale_id=rat.id,
                )

            # Link (Decision)-[:SELECTED|REJECTED]->(Alternative)
            if dec.chosen_alternative:
                c_clean = dec.chosen_alternative.strip().lower()
                for alt in extraction.alternatives:
                    if alt.name.strip().lower() == c_clean or alt.id == dec.chosen_alternative:
                        tx.run(
                            LINK_DECISION_ALTERNATIVE_SELECTED_QUERY,
                            decision_id=dec.id,
                            alternative_id=alt.id,
                        )
            elif extraction.alternatives:
                for alt in extraction.alternatives:
                    if dec.status == "rejected":
                        tx.run(
                            LINK_DECISION_ALTERNATIVE_REJECTED_QUERY,
                            decision_id=dec.id,
                            alternative_id=alt.id,
                        )
                    else:
                        tx.run(
                            LINK_DECISION_ALTERNATIVE_SELECTED_QUERY,
                            decision_id=dec.id,
                            alternative_id=alt.id,
                        )

        # Step I: Extracted Actions & (Action)-[:EVIDENCED_BY]->(Chunk)
        for act in extraction.actions:
            tx.run(
                MERGE_ACTION_QUERY,
                chunk_id=chunk_id,
                action_id=act.id,
                task=act.task,
                assignee=act.assignee,
                deadline=act.deadline,
                status=act.status or "pending",
                confidence=act.confidence,
            )

            # Link (Decision)-[:ASSIGNS]->(Action)
            for dec in extraction.decisions:
                tx.run(
                    LINK_DECISION_ACTION_QUERY,
                    decision_id=dec.id,
                    action_id=act.id,
                )

            # Link (Action)-[:OWNED_BY]->(Person)
            if act.assignee:
                act_person_id = make_deterministic_person_id(act.assignee)
                tx.run(
                    MERGE_SPEAKER_QUERY,
                    chunk_id=chunk_id,
                    person_id=act_person_id,
                    name=act.assignee.strip(),
                )
                tx.run(
                    LINK_ACTION_PERSON_QUERY,
                    action_id=act.id,
                    person_id=act_person_id,
                )

        # Step J: Extracted Outcomes & (Outcome)-[:EVIDENCED_BY]->(Chunk), (Action)-[:PRODUCED]->(Outcome)
        for out in extraction.outcomes:
            tx.run(
                MERGE_OUTCOME_QUERY,
                chunk_id=chunk_id,
                outcome_id=out.id,
                result=out.result,
                status=out.status,
                confidence=out.confidence,
            )
            # Link (Action)-[:PRODUCED]->(Outcome)
            for act in extraction.actions:
                tx.run(
                    LINK_ACTION_OUTCOME_QUERY,
                    action_id=act.id,
                    outcome_id=out.id,
                )

    try:
        with active_driver.session() as session:
            session.execute_write(_execute_tx)
    except ServiceUnavailable as e:
        raise GraphDatabaseUnavailableError("Neo4j database service is unavailable.") from e
    except Neo4jError as e:
        raise GraphPersistenceError(f"Neo4j transaction failed: {e.message}") from e
    except Exception as e:
        raise GraphPersistenceError(f"Graph persistence failed: {e}") from e

    return {
        "status": "success",
        "source_id": source_id,
        "chunk_id": chunk_id,
        "counts": counts,
    }

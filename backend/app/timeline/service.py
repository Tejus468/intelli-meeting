"""Decision timeline service reconstructing decision evolution and provenance from Neo4j."""
from typing import List, Dict, Any, Optional
from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable, Neo4jError

from app.db.neo4j import get_neo4j_driver
from app.timeline.models import TimelineEvent, DecisionTimeline

TYPE_ORDER = {
    "problem": 1,
    "alternative": 2,
    "rationale": 3,
    "decision": 4,
    "action": 5,
    "outcome": 6,
}


class TimelineError(Exception):
    """Base exception for timeline operations."""
    pass


class DecisionNotFoundError(TimelineError):
    """Raised when the requested decision ID does not exist in the graph."""
    pass


class TimelineDatabaseError(TimelineError):
    """Raised when Neo4j communication fails."""
    pass


DECISION_LOOKUP_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})
OPTIONAL MATCH (d)-[:MADE_IN]->(s_dec:Source)
OPTIONAL MATCH (d)-[:EVIDENCED_BY]->(c_dec:Chunk)
OPTIONAL MATCH (s_chunk:Source)-[:HAS_CHUNK]->(c_dec)
RETURN
    d.decision_id AS decision_id,
    d.statement AS statement,
    d.status AS status,
    d.confidence AS confidence,
    coalesce(s_dec.source_id, s_chunk.source_id) AS source_id,
    coalesce(s_dec.title, s_chunk.title) AS source_title,
    coalesce(s_dec.source_date, s_chunk.source_date) AS source_date,
    c_dec.chunk_id AS chunk_id,
    c_dec.speaker AS speaker,
    c_dec.start_ts AS start_ts,
    c_dec.end_ts AS end_ts,
    c_dec.page AS page
LIMIT 1
"""

DECISION_CONTEXT_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})

// 1. Connected Problems (RESOLVES)
OPTIONAL MATCH (d)-[:RESOLVES]->(pr:Problem)
OPTIONAL MATCH (pr)-[:EVIDENCED_BY]->(c_pr:Chunk)
OPTIONAL MATCH (s_pr:Source)-[:HAS_CHUNK]->(c_pr)

// 2. Connected Alternatives (SELECTED / REJECTED)
OPTIONAL MATCH (d)-[r_alt:SELECTED|REJECTED]->(alt:Alternative)
OPTIONAL MATCH (alt)-[:EVIDENCED_BY]->(c_alt:Chunk)
OPTIONAL MATCH (s_alt:Source)-[:HAS_CHUNK]->(c_alt)

// 3. Connected Rationales (JUSTIFIED_BY)
OPTIONAL MATCH (d)-[:JUSTIFIED_BY]->(rat:Rationale)
OPTIONAL MATCH (rat)-[:EVIDENCED_BY]->(c_rat:Chunk)
OPTIONAL MATCH (s_rat:Source)-[:HAS_CHUNK]->(c_rat)

// 4. Connected Actions (ASSIGNS) & Owners (OWNED_BY)
OPTIONAL MATCH (d)-[:ASSIGNS]->(act:Action)
OPTIONAL MATCH (act)-[:OWNED_BY]->(p_act:Person)
OPTIONAL MATCH (act)-[:EVIDENCED_BY]->(c_act:Chunk)
OPTIONAL MATCH (s_act:Source)-[:HAS_CHUNK]->(c_act)

// 5. Connected Outcomes (PRODUCED)
OPTIONAL MATCH (act)-[:PRODUCED]->(out:Outcome)
OPTIONAL MATCH (out)-[:EVIDENCED_BY]->(c_out:Chunk)
OPTIONAL MATCH (s_out:Source)-[:HAS_CHUNK]->(c_out)

RETURN
    // Problems
    collect(DISTINCT {
        event_type: 'problem',
        event_id: pr.problem_id,
        label: 'Problem Addressed',
        description: pr.description,
        status: null,
        source_id: s_pr.source_id,
        source_title: s_pr.title,
        source_date: s_pr.source_date,
        chunk_id: c_pr.chunk_id,
        speaker: c_pr.speaker,
        start_ts: c_pr.start_ts,
        end_ts: c_pr.end_ts,
        page: c_pr.page
    }) AS problems,

    // Alternatives
    collect(DISTINCT {
        event_type: 'alternative',
        event_id: alt.alternative_id,
        label: CASE WHEN type(r_alt) = 'SELECTED' THEN 'Selected Alternative' ELSE 'Rejected Alternative' END,
        description: coalesce(alt.description, alt.name),
        status: toLower(type(r_alt)),
        source_id: s_alt.source_id,
        source_title: s_alt.title,
        source_date: s_alt.source_date,
        chunk_id: c_alt.chunk_id,
        speaker: c_alt.speaker,
        start_ts: c_alt.start_ts,
        end_ts: c_alt.end_ts,
        page: c_alt.page
    }) AS alternatives,

    // Rationales
    collect(DISTINCT {
        event_type: 'rationale',
        event_id: rat.rationale_id,
        label: 'Rationale: ' + coalesce(rat.stance, 'supports'),
        description: rat.reason,
        status: rat.stance,
        source_id: s_rat.source_id,
        source_title: s_rat.title,
        source_date: s_rat.source_date,
        chunk_id: c_rat.chunk_id,
        speaker: c_rat.speaker,
        start_ts: c_rat.start_ts,
        end_ts: c_rat.end_ts,
        page: c_rat.page
    }) AS rationales,

    // Actions
    collect(DISTINCT {
        event_type: 'action',
        event_id: act.action_id,
        label: 'Action: ' + coalesce(act.task, 'Task'),
        description: act.task,
        status: act.status,
        assignee: coalesce(act.assignee, p_act.name),
        deadline: act.deadline,
        source_id: s_act.source_id,
        source_title: s_act.title,
        source_date: s_act.source_date,
        chunk_id: c_act.chunk_id,
        speaker: c_act.speaker,
        start_ts: c_act.start_ts,
        end_ts: c_act.end_ts,
        page: c_act.page
    }) AS actions,

    // Outcomes
    collect(DISTINCT {
        event_type: 'outcome',
        event_id: out.outcome_id,
        label: 'Observed Outcome',
        description: out.result,
        status: out.status,
        source_id: s_out.source_id,
        source_title: s_out.title,
        source_date: s_out.source_date,
        chunk_id: c_out.chunk_id,
        speaker: c_out.speaker,
        start_ts: c_out.start_ts,
        end_ts: c_out.end_ts,
        page: c_out.page
    }) AS outcomes
"""


def _clean_event_dict(raw: Dict[str, Any]) -> Optional[TimelineEvent]:
    """Convert raw query dictionary into a validated TimelineEvent, skipping null items."""
    event_id = raw.get("event_id")
    if not event_id:
        return None

    s_date = raw.get("source_date")
    source_date_str = s_date.isoformat() if hasattr(s_date, "isoformat") else (str(s_date) if s_date else None)

    return TimelineEvent(
        event_type=raw.get("event_type", "decision"),
        event_id=str(event_id),
        label=raw.get("label") or "Event",
        description=raw.get("description") or "",
        source_id=raw.get("source_id"),
        chunk_id=raw.get("chunk_id"),
        source_title=raw.get("source_title"),
        source_date=source_date_str,
        page=raw.get("page"),
        speaker=raw.get("speaker"),
        start_ts=raw.get("start_ts"),
        end_ts=raw.get("end_ts"),
        status=raw.get("status"),
    )


def get_decision_timeline(
    decision_id: str,
    driver: Optional[Driver] = None,
) -> DecisionTimeline:
    """Retrieve the full chronological context and evolution of a specific decision from Neo4j."""
    if not decision_id or not decision_id.strip():
        raise ValueError("decision_id must not be empty or whitespace")

    clean_id = decision_id.strip()
    active_driver = driver or get_neo4j_driver()

    def _execute_queries(tx):
        # 1. Fetch Decision node
        dec_res = tx.run(DECISION_LOOKUP_QUERY, decision_id=clean_id)
        dec_record = dec_res.single()
        if not dec_record:
            return None, None

        # 2. Fetch Connected Context
        ctx_res = tx.run(DECISION_CONTEXT_QUERY, decision_id=clean_id)
        ctx_record = ctx_res.single()
        return dec_record, ctx_record

    try:
        with active_driver.session() as session:
            dec_record, ctx_record = session.execute_read(_execute_queries)
    except (ServiceUnavailable, Neo4jError) as e:
        raise TimelineDatabaseError("Neo4j database is unavailable.") from e
    except Exception as e:
        raise TimelineDatabaseError(f"Error querying decision timeline: {e}") from e

    if not dec_record:
        raise DecisionNotFoundError(f"Decision with ID '{clean_id}' not found.")

    statement = dec_record.get("statement") or "Decision"
    status = dec_record.get("status") or "agreed"

    # Convert main decision node to a timeline event
    s_date = dec_record.get("source_date")
    dec_source_date_str = s_date.isoformat() if hasattr(s_date, "isoformat") else (str(s_date) if s_date else None)

    decision_event = TimelineEvent(
        event_type="decision",
        event_id=clean_id,
        label=f"Decision Agreed: {statement}",
        description=statement,
        source_id=dec_record.get("source_id"),
        chunk_id=dec_record.get("chunk_id"),
        source_title=dec_record.get("source_title"),
        source_date=dec_source_date_str,
        page=dec_record.get("page"),
        speaker=dec_record.get("speaker"),
        start_ts=dec_record.get("start_ts"),
        end_ts=dec_record.get("end_ts"),
        status=status,
    )

    events: List[TimelineEvent] = [decision_event]

    if ctx_record:
        # Collect and parse problems, alternatives, rationales, actions, outcomes
        categories = ["problems", "alternatives", "rationales", "actions", "outcomes"]
        for cat in categories:
            raw_list = ctx_record.get(cat) or []
            for raw in raw_list:
                cleaned = _clean_event_dict(raw)
                if cleaned:
                    events.append(cleaned)

    # Chronological & Fallback Ordering Strategy
    # Priority: 1) source_date, 2) start_ts, 3) Logical semantic flow
    def _sort_key(ev: TimelineEvent):
        date_key = ev.source_date or ""
        ts_key = ev.start_ts or ""
        type_priority = TYPE_ORDER.get(ev.event_type, 99)
        return (date_key, ts_key, type_priority, ev.event_id)

    events.sort(key=_sort_key)

    return DecisionTimeline(
        decision_id=clean_id,
        decision_statement=statement,
        decision_status=status,
        events=events,
    )

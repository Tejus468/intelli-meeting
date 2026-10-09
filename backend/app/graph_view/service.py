"""Graph visualization service for extracting frontend-friendly subgraphs from Neo4j."""
from typing import Dict, Any, List, Optional, Set
from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable, Neo4jError

from app.db.neo4j import get_neo4j_driver
from app.graph_view.models import GraphNode, GraphEdge, DecisionGraph


class GraphViewError(Exception):
    """Base exception for graph view operations."""
    pass


class DecisionNotFoundError(GraphViewError):
    """Raised when the target decision ID is not found in the graph."""
    pass


class GraphViewDatabaseError(GraphViewError):
    """Raised when Neo4j communication or transaction fails."""
    pass


DECISION_GRAPH_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})

// Decision core & provenance
OPTIONAL MATCH (d)-[:MADE_IN]->(s_dec:Source)
OPTIONAL MATCH (d)-[:EVIDENCED_BY]->(c_dec:Chunk)
OPTIONAL MATCH (s_dec_chunk:Source)-[:HAS_CHUNK]->(c_dec)

// Problems
OPTIONAL MATCH (d)-[:RESOLVES]->(pr:Problem)
OPTIONAL MATCH (pr)-[:EVIDENCED_BY]->(c_pr:Chunk)
OPTIONAL MATCH (s_pr:Source)-[:HAS_CHUNK]->(c_pr)

// Alternatives
OPTIONAL MATCH (d)-[r_da:SELECTED|REJECTED]->(alt:Alternative)
OPTIONAL MATCH (alt)-[:EVIDENCED_BY]->(c_alt:Chunk)
OPTIONAL MATCH (s_alt:Source)-[:HAS_CHUNK]->(c_alt)
OPTIONAL MATCH (pr)-[:CONSIDERED]->(alt)

// Rationales
OPTIONAL MATCH (d)-[:JUSTIFIED_BY]->(rat:Rationale)
OPTIONAL MATCH (rat)-[r_ra:SUPPORTS|OPPOSES]->(rat_alt:Alternative)
OPTIONAL MATCH (rat)-[:EVIDENCED_BY]->(c_rat:Chunk)
OPTIONAL MATCH (s_rat:Source)-[:HAS_CHUNK]->(c_rat)

// Actions & Owners
OPTIONAL MATCH (d)-[:ASSIGNS]->(act:Action)
OPTIONAL MATCH (act)-[:OWNED_BY]->(p_act:Person)
OPTIONAL MATCH (act)-[:EVIDENCED_BY]->(c_act:Chunk)
OPTIONAL MATCH (s_act:Source)-[:HAS_CHUNK]->(c_act)

// Outcomes
OPTIONAL MATCH (act)-[:PRODUCED]->(out:Outcome)
OPTIONAL MATCH (out)-[:EVIDENCED_BY]->(c_out:Chunk)
OPTIONAL MATCH (s_out:Source)-[:HAS_CHUNK]->(c_out)

RETURN
    d.decision_id AS decision_id,
    d.statement AS statement,
    d.status AS status,
    d.confidence AS confidence,
    s_dec.source_id AS dec_source_id,
    s_dec.title AS dec_source_title,
    s_dec.source_type AS dec_source_type,
    s_dec.source_date AS dec_source_date,
    c_dec.chunk_id AS dec_chunk_id,
    c_dec.text AS dec_chunk_text,
    c_dec.speaker AS dec_chunk_speaker,
    c_dec.start_ts AS dec_chunk_start_ts,
    c_dec.end_ts AS dec_chunk_end_ts,
    c_dec.page AS dec_chunk_page,
    s_dec_chunk.source_id AS dec_chunk_source_id,
    s_dec_chunk.title AS dec_chunk_source_title,
    s_dec_chunk.source_type AS dec_chunk_source_type,
    s_dec_chunk.source_date AS dec_chunk_source_date,

    collect(DISTINCT {
        problem_id: pr.problem_id,
        description: pr.description,
        confidence: pr.confidence,
        chunk_id: c_pr.chunk_id,
        chunk_text: c_pr.text,
        chunk_speaker: c_pr.speaker,
        chunk_start_ts: c_pr.start_ts,
        chunk_end_ts: c_pr.end_ts,
        chunk_page: c_pr.page,
        source_id: s_pr.source_id,
        source_title: s_pr.title,
        source_type: s_pr.source_type,
        source_date: s_pr.source_date
    }) AS problems,

    collect(DISTINCT {
        alternative_id: alt.alternative_id,
        name: alt.name,
        description: alt.description,
        confidence: alt.confidence,
        rel_type: type(r_da),
        problem_id: pr.problem_id,
        chunk_id: c_alt.chunk_id,
        chunk_text: c_alt.text,
        chunk_speaker: c_alt.speaker,
        chunk_start_ts: c_alt.start_ts,
        chunk_end_ts: c_alt.end_ts,
        chunk_page: c_alt.page,
        source_id: s_alt.source_id,
        source_title: s_alt.title,
        source_type: s_alt.source_type,
        source_date: s_alt.source_date
    }) AS alternatives,

    collect(DISTINCT {
        rationale_id: rat.rationale_id,
        reason: rat.reason,
        stance: rat.stance,
        confidence: rat.confidence,
        target_alt_id: rat_alt.alternative_id,
        target_alt_name: rat_alt.name,
        alt_rel_type: type(r_ra),
        chunk_id: c_rat.chunk_id,
        chunk_text: c_rat.text,
        chunk_speaker: c_rat.speaker,
        chunk_start_ts: c_rat.start_ts,
        chunk_end_ts: c_rat.end_ts,
        chunk_page: c_rat.page,
        source_id: s_rat.source_id,
        source_title: s_rat.title,
        source_type: s_rat.source_type,
        source_date: s_rat.source_date
    }) AS rationales,

    collect(DISTINCT {
        action_id: act.action_id,
        task: act.task,
        assignee: act.assignee,
        deadline: act.deadline,
        status: act.status,
        confidence: act.confidence,
        person_id: p_act.person_id,
        person_name: p_act.name,
        person_role: p_act.role,
        person_confidence: p_act.confidence,
        chunk_id: c_act.chunk_id,
        chunk_text: c_act.text,
        chunk_speaker: c_act.speaker,
        chunk_start_ts: c_act.start_ts,
        chunk_end_ts: c_act.end_ts,
        chunk_page: c_act.page,
        source_id: s_act.source_id,
        source_title: s_act.title,
        source_type: s_act.source_type,
        source_date: s_act.source_date
    }) AS actions,

    collect(DISTINCT {
        outcome_id: out.outcome_id,
        result: out.result,
        status: out.status,
        confidence: out.confidence,
        action_id: act.action_id,
        chunk_id: c_out.chunk_id,
        chunk_text: c_out.text,
        chunk_speaker: c_out.speaker,
        chunk_start_ts: c_out.start_ts,
        chunk_end_ts: c_out.end_ts,
        chunk_page: c_out.page,
        source_id: s_out.source_id,
        source_title: s_out.title,
        source_type: s_out.source_type,
        source_date: s_out.source_date
    }) AS outcomes
LIMIT 1
"""


def _format_date(val: Any) -> Optional[str]:
    """Safely format date values to ISO strings."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _add_edge(
    edges: Dict[str, GraphEdge],
    source_id: Optional[str],
    target_id: Optional[str],
    relationship: str,
    properties: Optional[Dict[str, Any]] = None,
) -> None:
    """Helper to deterministically add a unique edge between two valid node IDs."""
    if not source_id or not target_id:
        return
    edge_id = f"{source_id}_{relationship}_{target_id}"
    if edge_id not in edges:
        edges[edge_id] = GraphEdge(
            id=edge_id,
            source=str(source_id),
            target=str(target_id),
            relationship=relationship,
            properties=properties or {},
        )


def _add_source_and_chunk(
    nodes: Dict[str, GraphNode],
    edges: Dict[str, GraphEdge],
    entity_id: str,
    source_id: Optional[str],
    source_title: Optional[str],
    source_type: Optional[str],
    source_date: Any,
    chunk_id: Optional[str],
    chunk_text: Optional[str],
    chunk_speaker: Optional[str],
    chunk_start_ts: Optional[float],
    chunk_end_ts: Optional[float],
    chunk_page: Optional[int],
) -> None:
    """Helper to add Source and Chunk provenance nodes and link them to the entity."""
    # 1. Chunk Node
    if chunk_id:
        c_id = str(chunk_id)
        if c_id not in nodes:
            label = f"Chunk: {chunk_speaker}" if chunk_speaker else f"Chunk: {c_id}"
            nodes[c_id] = GraphNode(
                id=c_id,
                node_type="Chunk",
                label=label,
                properties={
                    "text": chunk_text,
                    "speaker": chunk_speaker,
                    "start_ts": chunk_start_ts,
                    "end_ts": chunk_end_ts,
                    "page": chunk_page,
                },
            )
        _add_edge(edges, entity_id, c_id, "EVIDENCED_BY")

    # 2. Source Node
    if source_id:
        s_id = str(source_id)
        if s_id not in nodes:
            nodes[s_id] = GraphNode(
                id=s_id,
                node_type="Source",
                label=source_title or f"Source: {s_id}",
                properties={
                    "title": source_title or "Untitled Document",
                    "source_type": source_type or "transcript",
                    "source_date": _format_date(source_date),
                },
            )
        # Link Source -> Chunk if chunk exists
        if chunk_id:
            _add_edge(edges, s_id, str(chunk_id), "HAS_CHUNK")


def get_decision_graph(
    decision_id: str,
    driver: Optional[Driver] = None,
) -> DecisionGraph:
    """Retrieve the connected context and provenance graph for a given decision."""
    if not decision_id or not decision_id.strip():
        raise ValueError("decision_id must not be empty or whitespace")

    clean_id = decision_id.strip()
    active_driver = driver or get_neo4j_driver()

    def _execute_query(tx):
        res = tx.run(DECISION_GRAPH_QUERY, decision_id=clean_id)
        return res.single()

    try:
        with active_driver.session() as session:
            record = session.execute_read(_execute_query)
    except (ServiceUnavailable, Neo4jError) as e:
        raise GraphViewDatabaseError("Neo4j database is unavailable.") from e
    except Exception as e:
        raise GraphViewDatabaseError(f"Error querying decision graph: {e}") from e

    if not record or not record.get("decision_id"):
        raise DecisionNotFoundError(f"Decision with ID '{clean_id}' not found.")

    nodes: Dict[str, GraphNode] = {}
    edges: Dict[str, GraphEdge] = {}

    # 1. Decision Node
    dec_statement = record.get("statement") or "Decision"
    dec_status = record.get("status") or "agreed"
    dec_confidence = record.get("confidence")

    nodes[clean_id] = GraphNode(
        id=clean_id,
        node_type="Decision",
        label=dec_statement,
        properties={
            "statement": dec_statement,
            "status": dec_status,
            "confidence": dec_confidence,
        },
    )

    # Decision provenance
    dec_source_id = record.get("dec_source_id") or record.get("dec_chunk_source_id")
    dec_source_title = record.get("dec_source_title") or record.get("dec_chunk_source_title")
    dec_source_type = record.get("dec_source_type") or record.get("dec_chunk_source_type")
    dec_source_date = record.get("dec_source_date") or record.get("dec_chunk_source_date")

    if dec_source_id:
        s_id = str(dec_source_id)
        if s_id not in nodes:
            nodes[s_id] = GraphNode(
                id=s_id,
                node_type="Source",
                label=dec_source_title or f"Source: {s_id}",
                properties={
                    "title": dec_source_title or "Untitled Document",
                    "source_type": dec_source_type or "transcript",
                    "source_date": _format_date(dec_source_date),
                },
            )
        _add_edge(edges, clean_id, s_id, "MADE_IN")

    if record.get("dec_chunk_id"):
        _add_source_and_chunk(
            nodes=nodes,
            edges=edges,
            entity_id=clean_id,
            source_id=dec_source_id,
            source_title=dec_source_title,
            source_type=dec_source_type,
            source_date=dec_source_date,
            chunk_id=record.get("dec_chunk_id"),
            chunk_text=record.get("dec_chunk_text"),
            chunk_speaker=record.get("dec_chunk_speaker"),
            chunk_start_ts=record.get("dec_chunk_start_ts"),
            chunk_end_ts=record.get("dec_chunk_end_ts"),
            chunk_page=record.get("dec_chunk_page"),
        )

    # 2. Problems
    problems = record.get("problems") or []
    for pr in problems:
        pr_id = pr.get("problem_id")
        if not pr_id:
            continue
        pr_id_str = str(pr_id)
        desc = pr.get("description") or "Problem"
        if pr_id_str not in nodes:
            nodes[pr_id_str] = GraphNode(
                id=pr_id_str,
                node_type="Problem",
                label=desc,
                properties={
                    "description": desc,
                    "confidence": pr.get("confidence"),
                },
            )
        _add_edge(edges, clean_id, pr_id_str, "RESOLVES")
        _add_source_and_chunk(
            nodes=nodes,
            edges=edges,
            entity_id=pr_id_str,
            source_id=pr.get("source_id"),
            source_title=pr.get("source_title"),
            source_type=pr.get("source_type"),
            source_date=pr.get("source_date"),
            chunk_id=pr.get("chunk_id"),
            chunk_text=pr.get("chunk_text"),
            chunk_speaker=pr.get("chunk_speaker"),
            chunk_start_ts=pr.get("chunk_start_ts"),
            chunk_end_ts=pr.get("chunk_end_ts"),
            chunk_page=pr.get("chunk_page"),
        )

    # 3. Alternatives
    alternatives = record.get("alternatives") or []
    for alt in alternatives:
        alt_id = alt.get("alternative_id")
        if not alt_id:
            continue
        alt_id_str = str(alt_id)
        name = alt.get("name") or alt.get("description") or "Alternative"
        if alt_id_str not in nodes:
            nodes[alt_id_str] = GraphNode(
                id=alt_id_str,
                node_type="Alternative",
                label=name,
                properties={
                    "name": name,
                    "description": alt.get("description"),
                    "confidence": alt.get("confidence"),
                },
            )

        # Relationship: SELECTED or REJECTED
        rel_type = alt.get("rel_type") or "SELECTED"
        _add_edge(edges, clean_id, alt_id_str, rel_type)

        # Relationship: Problem CONSIDERED Alternative
        if alt.get("problem_id"):
            _add_edge(edges, str(alt.get("problem_id")), alt_id_str, "CONSIDERED")

        _add_source_and_chunk(
            nodes=nodes,
            edges=edges,
            entity_id=alt_id_str,
            source_id=alt.get("source_id"),
            source_title=alt.get("source_title"),
            source_type=alt.get("source_type"),
            source_date=alt.get("source_date"),
            chunk_id=alt.get("chunk_id"),
            chunk_text=alt.get("chunk_text"),
            chunk_speaker=alt.get("chunk_speaker"),
            chunk_start_ts=alt.get("chunk_start_ts"),
            chunk_end_ts=alt.get("chunk_end_ts"),
            chunk_page=alt.get("chunk_page"),
        )

    # 4. Rationales
    rationales = record.get("rationales") or []
    for rat in rationales:
        rat_id = rat.get("rationale_id")
        if not rat_id:
            continue
        rat_id_str = str(rat_id)
        reason = rat.get("reason") or "Rationale"
        stance = rat.get("stance") or "supports"
        if rat_id_str not in nodes:
            nodes[rat_id_str] = GraphNode(
                id=rat_id_str,
                node_type="Rationale",
                label=reason,
                properties={
                    "reason": reason,
                    "stance": stance,
                    "confidence": rat.get("confidence"),
                },
            )
        _add_edge(edges, clean_id, rat_id_str, "JUSTIFIED_BY")

        # Rationale -> Alternative (SUPPORTS / OPPOSES)
        if rat.get("target_alt_id"):
            target_alt_id = str(rat.get("target_alt_id"))
            # The target may be an alternative that was not selected/rejected by the decision;
            # make sure its node exists so the edge has both endpoints.
            if target_alt_id not in nodes:
                target_name = rat.get("target_alt_name") or "Alternative"
                nodes[target_alt_id] = GraphNode(
                    id=target_alt_id,
                    node_type="Alternative",
                    label=target_name,
                    properties={"name": target_name},
                )
            alt_rel = rat.get("alt_rel_type") or ("OPPOSES" if stance == "opposes" else "SUPPORTS")
            _add_edge(edges, rat_id_str, target_alt_id, alt_rel)

        _add_source_and_chunk(
            nodes=nodes,
            edges=edges,
            entity_id=rat_id_str,
            source_id=rat.get("source_id"),
            source_title=rat.get("source_title"),
            source_type=rat.get("source_type"),
            source_date=rat.get("source_date"),
            chunk_id=rat.get("chunk_id"),
            chunk_text=rat.get("chunk_text"),
            chunk_speaker=rat.get("chunk_speaker"),
            chunk_start_ts=rat.get("chunk_start_ts"),
            chunk_end_ts=rat.get("chunk_end_ts"),
            chunk_page=rat.get("chunk_page"),
        )

    # 5. Actions & Owners
    actions = record.get("actions") or []
    for act in actions:
        act_id = act.get("action_id")
        if not act_id:
            continue
        act_id_str = str(act_id)
        task = act.get("task") or "Action"
        if act_id_str not in nodes:
            nodes[act_id_str] = GraphNode(
                id=act_id_str,
                node_type="Action",
                label=task,
                properties={
                    "task": task,
                    "assignee": act.get("assignee"),
                    "deadline": act.get("deadline"),
                    "status": act.get("status") or "pending",
                    "confidence": act.get("confidence"),
                },
            )
        _add_edge(edges, clean_id, act_id_str, "ASSIGNS")

        # Person Node & OWNED_BY
        p_id = act.get("person_id")
        p_name = act.get("person_name") or act.get("assignee")
        if p_id and p_name:
            p_id_str = str(p_id)
            if p_id_str not in nodes:
                nodes[p_id_str] = GraphNode(
                    id=p_id_str,
                    node_type="Person",
                    label=p_name,
                    properties={
                        "name": p_name,
                        "role": act.get("person_role"),
                        "confidence": act.get("person_confidence"),
                    },
                )
            _add_edge(edges, act_id_str, p_id_str, "OWNED_BY")

        _add_source_and_chunk(
            nodes=nodes,
            edges=edges,
            entity_id=act_id_str,
            source_id=act.get("source_id"),
            source_title=act.get("source_title"),
            source_type=act.get("source_type"),
            source_date=act.get("source_date"),
            chunk_id=act.get("chunk_id"),
            chunk_text=act.get("chunk_text"),
            chunk_speaker=act.get("chunk_speaker"),
            chunk_start_ts=act.get("chunk_start_ts"),
            chunk_end_ts=act.get("chunk_end_ts"),
            chunk_page=act.get("chunk_page"),
        )

    # 6. Outcomes
    outcomes = record.get("outcomes") or []
    for out in outcomes:
        out_id = out.get("outcome_id")
        if not out_id:
            continue
        out_id_str = str(out_id)
        result = out.get("result") or "Outcome"
        if out_id_str not in nodes:
            nodes[out_id_str] = GraphNode(
                id=out_id_str,
                node_type="Outcome",
                label=result,
                properties={
                    "result": result,
                    "status": out.get("status"),
                    "confidence": out.get("confidence"),
                },
            )

        # Action -> PRODUCED -> Outcome
        if out.get("action_id"):
            _add_edge(edges, str(out.get("action_id")), out_id_str, "PRODUCED")

        _add_source_and_chunk(
            nodes=nodes,
            edges=edges,
            entity_id=out_id_str,
            source_id=out.get("source_id"),
            source_title=out.get("source_title"),
            source_type=out.get("source_type"),
            source_date=out.get("source_date"),
            chunk_id=out.get("chunk_id"),
            chunk_text=out.get("chunk_text"),
            chunk_speaker=out.get("chunk_speaker"),
            chunk_start_ts=out.get("chunk_start_ts"),
            chunk_end_ts=out.get("chunk_end_ts"),
            chunk_page=out.get("chunk_page"),
        )

    return DecisionGraph(
        decision_id=clean_id,
        nodes=list(nodes.values()),
        edges=list(edges.values()),
    )

"""Graph retriever for querying entities, connected chunks, and provenance from Neo4j."""
import re
from typing import List, Optional, Set
from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable, Neo4jError

from app.db.neo4j import get_neo4j_driver
from app.retrieval.models import ContextRationale, DecisionContext, EvidenceItem

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "its", "itself", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "shouldn't", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "wasn't", "we", "were", "weren't",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with",
    "would", "wouldn't", "you", "your", "yours", "yourself", "yourselves"
}

GRAPH_SEARCH_BY_TERMS_QUERY = """
MATCH (n)
WHERE (n:Decision OR n:Action OR n:Problem OR n:Alternative OR n:Rationale OR n:Outcome OR n:Person)
  AND any(term IN $terms WHERE toLower(coalesce(n.statement, n.task, n.description, n.name, n.reason, n.result, '')) CONTAINS term)
OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c:Chunk)
OPTIONAL MATCH (s:Source)-[:HAS_CHUNK]->(c)
RETURN
    labels(n)[0] AS node_type,
    coalesce(n.decision_id, n.action_id, n.problem_id, n.alternative_id, n.rationale_id, n.outcome_id, n.person_id) AS node_id,
    coalesce(n.statement, n.task, n.description, n.name, n.reason, n.result, '') AS text,
    properties(n) AS node_props,
    c.chunk_id AS chunk_id,
    c.text AS chunk_text,
    c.speaker AS speaker,
    c.start_ts AS start_ts,
    c.end_ts AS end_ts,
    c.page AS page,
    s.source_id AS source_id
LIMIT $limit
"""

GRAPH_SEARCH_BY_SEED_CHUNKS_QUERY = """
MATCH (c:Chunk)
WHERE c.chunk_id IN $seed_chunk_ids
OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(c)
OPTIONAL MATCH (s:Source)-[:HAS_CHUNK]->(c)
WHERE n IS NOT NULL
RETURN
    labels(n)[0] AS node_type,
    coalesce(n.decision_id, n.action_id, n.problem_id, n.alternative_id, n.rationale_id, n.outcome_id, n.person_id) AS node_id,
    coalesce(n.statement, n.task, n.description, n.name, n.reason, n.result, '') AS text,
    properties(n) AS node_props,
    c.chunk_id AS chunk_id,
    c.text AS chunk_text,
    c.speaker AS speaker,
    c.start_ts AS start_ts,
    c.end_ts AS end_ts,
    c.page AS page,
    s.source_id AS source_id
LIMIT $limit
"""


def extract_search_terms(query: str) -> List[str]:
    """Extract significant lowercase keywords from user query for Cypher substring matching."""
    tokens = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query.lower())
    terms = [t for t in tokens if t not in STOPWORDS]
    return terms if terms else tokens


def retrieve_graph_evidence(
    query: str,
    top_k: int = 5,
    driver: Optional[Driver] = None,
    seed_chunk_ids: Optional[List[str]] = None,
) -> List[EvidenceItem]:
    """Query Neo4j for semantic decision entities and their provenance chunks."""
    if not query or not query.strip():
        return []
    if top_k <= 0:
        return []

    terms = extract_search_terms(query)
    active_driver = driver or get_neo4j_driver()
    items: List[EvidenceItem] = []
    seen_keys: Set[str] = set()

    def _execute_search(tx):
        records = []
        # 1. Term-based graph node search
        if terms:
            res_terms = tx.run(
                GRAPH_SEARCH_BY_TERMS_QUERY,
                terms=terms,
                limit=top_k * 2,
            )
            records.extend(res_terms.data())

        # 2. Seed chunk neighborhood expansion if seed chunks provided
        if seed_chunk_ids:
            res_seeds = tx.run(
                GRAPH_SEARCH_BY_SEED_CHUNKS_QUERY,
                seed_chunk_ids=seed_chunk_ids,
                limit=top_k * 2,
            )
            records.extend(res_seeds.data())

        return records

    try:
        with active_driver.session() as session:
            raw_records = session.execute_read(_execute_search)
    except (ServiceUnavailable, Neo4jError, Exception):
        # Gracefully return empty evidence list if Neo4j is offline or query fails
        return []

    for idx, rec in enumerate(raw_records):
        node_id = rec.get("node_id") or f"node_{idx}"
        chunk_id = rec.get("chunk_id")
        node_type = (rec.get("node_type") or "entity").lower()

        # Deduplication key for graph traversal results
        dedup_key = f"{node_id}:{chunk_id or ''}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        entity_text = rec.get("text") or ""
        chunk_text = rec.get("chunk_text") or ""
        combined_text = f"[{node_type.upper()}] {entity_text}"
        if chunk_text and chunk_text != entity_text:
            combined_text += f" — Context: {chunk_text}"

        node_props = rec.get("node_props") or {}
        confidence = float(node_props.get("confidence", 0.8))

        # Calculate keyword match score
        matches = sum(1 for t in terms if t in combined_text.lower())
        term_score = (matches / len(terms)) if terms else 0.5
        relevance_score = min(1.0, max(0.1, 0.4 * term_score + 0.6 * confidence))

        metadata = {
            "node_type": node_type,
            "speaker": rec.get("speaker"),
            "start_ts": rec.get("start_ts"),
            "end_ts": rec.get("end_ts"),
            "page": rec.get("page"),
            "status": node_props.get("status"),
            "assignee": node_props.get("assignee"),
            "deadline": node_props.get("deadline"),
            "stance": node_props.get("stance"),
            "confidence": confidence,
        }
        # Clean null values from metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}

        items.append(
            EvidenceItem(
                evidence_id=f"ev_graph_{node_id}",
                evidence_type=node_type,
                source_id=rec.get("source_id"),
                chunk_id=chunk_id,
                node_id=node_id,
                text=combined_text,
                metadata=metadata,
                retrieval_method="graph",
                score=round(relevance_score, 4),
            )
        )

        if len(items) >= top_k:
            break

    return items


DECISION_CONTEXT_QUERY = """
MATCH (d:Decision)-[:EVIDENCED_BY]->(c:Chunk)
WHERE c.chunk_id IN $chunk_ids
RETURN DISTINCT
    d.decision_id AS decision_id,
    d.statement AS statement,
    d.status AS status,
    [(d)-[:RESOLVES]->(p:Problem) | p.description] AS problems,
    [(d)-[:SELECTED]->(a:Alternative) | a.name] AS selected,
    [(d)-[:REJECTED]->(a:Alternative) | a.name] AS rejected,
    [(d)-[:RESOLVES]->(:Problem)-[:CONSIDERED]->(a:Alternative) | a.name] AS considered_via_problem,
    [(d)-[:JUSTIFIED_BY]->(r:Rationale) | {
        reason: r.reason,
        stance: coalesce(r.stance, 'supports'),
        targets: [(r)-[:SUPPORTS|OPPOSES]->(a:Alternative) | a.name]
    }] AS rationales
ORDER BY d.decision_id
LIMIT $limit
"""


def _unique(names: List[Optional[str]]) -> List[str]:
    seen: List[str] = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def retrieve_decision_context(
    chunk_ids: List[str],
    driver: Optional[Driver] = None,
    limit: int = 5,
) -> List[DecisionContext]:
    """Read the decisions evidenced by the given chunks, with their alternatives and rationales.

    Read-only. Returns an empty list when there is nothing to look up or the graph cannot be read, so
    question answering degrades to plain evidence instead of failing.
    """
    ids = [c for c in dict.fromkeys(chunk_ids) if c]
    if not ids or limit <= 0:
        return []

    def _execute(tx):
        return tx.run(DECISION_CONTEXT_QUERY, chunk_ids=ids, limit=limit).data()

    try:
        active_driver = driver or get_neo4j_driver()
        with active_driver.session() as session:
            rows = session.execute_read(_execute)
    except Exception:
        return []

    contexts: List[DecisionContext] = []
    for row in rows:
        if not row.get("decision_id") or not row.get("statement"):
            continue
        rationales = [
            ContextRationale(
                reason=r["reason"],
                stance=r.get("stance") or "supports",
                target_alternatives=_unique(r.get("targets") or []),
            )
            for r in (row.get("rationales") or [])
            if r.get("reason")
        ]
        selected = _unique(row.get("selected") or [])
        rejected = _unique(row.get("rejected") or [])
        contexts.append(
            DecisionContext(
                decision_id=row["decision_id"],
                statement=row["statement"],
                status=row.get("status"),
                problems=_unique(row.get("problems") or []),
                selected_alternatives=selected,
                rejected_alternatives=rejected,
                considered_alternatives=_unique(
                    selected
                    + rejected
                    + [t for r in rationales for t in r.target_alternatives]
                    + (row.get("considered_via_problem") or [])
                ),
                rationales=rationales,
            )
        )
    return contexts

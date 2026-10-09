"""Cypher queries and statement templates for Neo4j persistence."""

# 1. Merge Source
MERGE_SOURCE_QUERY = """
MERGE (s:Source {source_id: $source_id})
ON CREATE SET
    s.source_type = $source_type,
    s.title = $title,
    s.source_date = $source_date,
    s.created_at = datetime()
ON MATCH SET
    s.source_type = $source_type,
    s.title = $title,
    s.source_date = coalesce($source_date, s.source_date)
RETURN s.source_id AS id
"""

# 2. Merge Chunk and link (Source)-[:HAS_CHUNK]->(Chunk)
MERGE_CHUNK_QUERY = """
MATCH (s:Source {source_id: $source_id})
MERGE (c:Chunk {chunk_id: $chunk_id})
ON CREATE SET
    c.text = $text,
    c.speaker = $speaker,
    c.start_ts = $start_ts,
    c.end_ts = $end_ts,
    c.page = $page,
    c.char_start = $char_start,
    c.char_end = $char_end,
    c.created_at = datetime()
ON MATCH SET
    c.text = $text,
    c.speaker = coalesce($speaker, c.speaker),
    c.start_ts = coalesce($start_ts, c.start_ts),
    c.end_ts = coalesce($end_ts, c.end_ts),
    c.page = coalesce($page, c.page),
    c.char_start = coalesce($char_start, c.char_start),
    c.char_end = coalesce($char_end, c.char_end)
MERGE (s)-[:HAS_CHUNK]->(c)
RETURN c.chunk_id AS id
"""

# 3. Merge Person and link (Chunk)-[:SPOKEN_BY]->(Person)
MERGE_SPEAKER_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (p:Person {person_id: $person_id})
ON CREATE SET
    p.name = $name,
    p.created_at = datetime()
ON MATCH SET
    p.name = $name
MERGE (c)-[:SPOKEN_BY]->(p)
"""

# 4. Merge Extracted Person
MERGE_PERSON_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (p:Person {person_id: $person_id})
ON CREATE SET
    p.name = $name,
    p.role = $role,
    p.confidence = $confidence,
    p.created_at = datetime()
ON MATCH SET
    p.name = $name,
    p.role = coalesce($role, p.role),
    p.confidence = coalesce($confidence, p.confidence)
MERGE (p)-[:EVIDENCED_BY]->(c)
"""

# 5. Merge Problem and link (Source)-[:DISCUSSED]->(Problem), (Problem)-[:EVIDENCED_BY]->(Chunk)
MERGE_PROBLEM_QUERY = """
MATCH (s:Source {source_id: $source_id})
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (pr:Problem {problem_id: $problem_id})
ON CREATE SET
    pr.description = $description,
    pr.confidence = $confidence,
    pr.created_at = datetime()
ON MATCH SET
    pr.description = $description,
    pr.confidence = $confidence
MERGE (s)-[:DISCUSSED]->(pr)
MERGE (pr)-[:EVIDENCED_BY]->(c)
"""

# 6. Merge Alternative and link (Problem)-[:CONSIDERED]->(Alternative), (Alternative)-[:EVIDENCED_BY]->(Chunk)
MERGE_ALTERNATIVE_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (a:Alternative {alternative_id: $alternative_id})
ON CREATE SET
    a.name = $name,
    a.description = $description,
    a.confidence = $confidence,
    a.created_at = datetime()
ON MATCH SET
    a.name = $name,
    a.description = coalesce($description, a.description),
    a.confidence = $confidence
MERGE (a)-[:EVIDENCED_BY]->(c)
"""

# Link Problem -> Alternative if problems exist in chunk
LINK_PROBLEM_ALTERNATIVE_QUERY = """
MATCH (pr:Problem {problem_id: $problem_id})
MATCH (a:Alternative {alternative_id: $alternative_id})
MERGE (pr)-[:CONSIDERED]->(a)
"""

# 7. Merge Rationale, link (Rationale)-[:EVIDENCED_BY]->(Chunk), and (Rationale)-[:SUPPORTS|OPPOSES]->(Alternative)
MERGE_RATIONALE_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (r:Rationale {rationale_id: $rationale_id})
ON CREATE SET
    r.reason = $reason,
    r.stance = $stance,
    r.confidence = $confidence,
    r.created_at = datetime()
ON MATCH SET
    r.reason = $reason,
    r.stance = $stance,
    r.confidence = $confidence
MERGE (r)-[:EVIDENCED_BY]->(c)
"""

LINK_RATIONALE_ALTERNATIVE_QUERY = """
MATCH (r:Rationale {rationale_id: $rationale_id})
MATCH (a:Alternative {alternative_id: $alternative_id})
FOREACH (_ IN CASE WHEN $stance = 'opposes' THEN [1] ELSE [] END |
    MERGE (r)-[:OPPOSES]->(a)
)
FOREACH (_ IN CASE WHEN $stance <> 'opposes' THEN [1] ELSE [] END |
    MERGE (r)-[:SUPPORTS]->(a)
)
"""

# 8. Merge Decision, link (Decision)-[:MADE_IN]->(Source), (Decision)-[:EVIDENCED_BY]->(Chunk)
MERGE_DECISION_QUERY = """
MATCH (s:Source {source_id: $source_id})
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (d:Decision {decision_id: $decision_id})
ON CREATE SET
    d.statement = $statement,
    d.status = $status,
    d.confidence = $confidence,
    d.created_at = datetime()
ON MATCH SET
    d.statement = $statement,
    d.status = $status,
    d.confidence = $confidence
MERGE (d)-[:MADE_IN]->(s)
MERGE (d)-[:EVIDENCED_BY]->(c)
"""

LINK_DECISION_PROBLEM_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (pr:Problem {problem_id: $problem_id})
MERGE (d)-[:RESOLVES]->(pr)
"""

LINK_DECISION_ALTERNATIVE_SELECTED_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (a:Alternative {alternative_id: $alternative_id})
MERGE (d)-[:SELECTED]->(a)
"""

LINK_DECISION_ALTERNATIVE_REJECTED_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (a:Alternative {alternative_id: $alternative_id})
MERGE (d)-[:REJECTED]->(a)
"""

LINK_DECISION_RATIONALE_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (r:Rationale {rationale_id: $rationale_id})
MERGE (d)-[:JUSTIFIED_BY]->(r)
"""

# 9. Merge Action, link (Action)-[:EVIDENCED_BY]->(Chunk), (Decision)-[:ASSIGNS]->(Action), (Action)-[:OWNED_BY]->(Person)
MERGE_ACTION_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (ac:Action {action_id: $action_id})
ON CREATE SET
    ac.task = $task,
    ac.assignee = $assignee,
    ac.deadline = $deadline,
    ac.status = $status,
    ac.confidence = $confidence,
    ac.created_at = datetime()
ON MATCH SET
    ac.task = $task,
    ac.assignee = coalesce($assignee, ac.assignee),
    ac.deadline = coalesce($deadline, ac.deadline),
    ac.status = coalesce($status, ac.status),
    ac.confidence = $confidence
MERGE (ac)-[:EVIDENCED_BY]->(c)
"""

LINK_DECISION_ACTION_QUERY = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (ac:Action {action_id: $action_id})
MERGE (d)-[:ASSIGNS]->(ac)
"""

LINK_ACTION_PERSON_QUERY = """
MATCH (ac:Action {action_id: $action_id})
MATCH (p:Person {person_id: $person_id})
MERGE (ac)-[:OWNED_BY]->(p)
"""

# 10. Merge Outcome, link (Outcome)-[:EVIDENCED_BY]->(Chunk), (Action)-[:PRODUCED]->(Outcome)
MERGE_OUTCOME_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})
MERGE (o:Outcome {outcome_id: $outcome_id})
ON CREATE SET
    o.result = $result,
    o.status = $status,
    o.confidence = $confidence,
    o.created_at = datetime()
ON MATCH SET
    o.result = $result,
    o.status = coalesce($status, o.status),
    o.confidence = $confidence
MERGE (o)-[:EVIDENCED_BY]->(c)
"""

LINK_ACTION_OUTCOME_QUERY = """
MATCH (ac:Action {action_id: $action_id})
MATCH (o:Outcome {outcome_id: $outcome_id})
MERGE (ac)-[:PRODUCED]->(o)
"""

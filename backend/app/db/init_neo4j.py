"""Neo4j schema and constraints initialization module."""
import sys
from typing import List, Tuple
from app.db.neo4j import get_neo4j_driver, close_neo4j_driver

# List of (constraint_name, cypher_statement) for unique entity IDs in Neo4j 5+
NEO4J_CONSTRAINTS: List[Tuple[str, str]] = [
    (
        "source_id_unique",
        "CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (s:Source) REQUIRE s.source_id IS UNIQUE",
    ),
    (
        "chunk_id_unique",
        "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    ),
    (
        "person_id_unique",
        "CREATE CONSTRAINT person_id_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.person_id IS UNIQUE",
    ),
    (
        "problem_id_unique",
        "CREATE CONSTRAINT problem_id_unique IF NOT EXISTS FOR (pr:Problem) REQUIRE pr.problem_id IS UNIQUE",
    ),
    (
        "alternative_id_unique",
        "CREATE CONSTRAINT alternative_id_unique IF NOT EXISTS FOR (a:Alternative) REQUIRE a.alternative_id IS UNIQUE",
    ),
    (
        "rationale_id_unique",
        "CREATE CONSTRAINT rationale_id_unique IF NOT EXISTS FOR (r:Rationale) REQUIRE r.rationale_id IS UNIQUE",
    ),
    (
        "decision_id_unique",
        "CREATE CONSTRAINT decision_id_unique IF NOT EXISTS FOR (d:Decision) REQUIRE d.decision_id IS UNIQUE",
    ),
    (
        "action_id_unique",
        "CREATE CONSTRAINT action_id_unique IF NOT EXISTS FOR (ac:Action) REQUIRE ac.action_id IS UNIQUE",
    ),
    (
        "outcome_id_unique",
        "CREATE CONSTRAINT outcome_id_unique IF NOT EXISTS FOR (o:Outcome) REQUIRE o.outcome_id IS UNIQUE",
    ),
]


def init_neo4j_schema() -> None:
    """Execute Neo4j schema constraint creation."""
    driver = get_neo4j_driver()
    with driver.session() as session:
        for name, cypher in NEO4J_CONSTRAINTS:
            session.run(cypher)


if __name__ == "__main__":
    try:
        print("Initializing Neo4j constraints...")
        init_neo4j_schema()
        print("Neo4j constraints initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize Neo4j constraints: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        close_neo4j_driver()

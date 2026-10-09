from typing import Optional
from neo4j import GraphDatabase, Driver
from app.core.config import settings

_driver: Optional[Driver] = None


def get_neo4j_driver(connection_timeout: float = 3.0) -> Driver:
    """Get or create singleton Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            connection_timeout=connection_timeout,
        )
    return _driver


def close_neo4j_driver() -> None:
    """Close the Neo4j driver connection pool."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def check_neo4j_health() -> bool:
    """Verify connectivity to the Neo4j instance."""
    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        return True
    except Exception:
        return False


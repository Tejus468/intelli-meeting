import psycopg
from app.core.config import settings


def get_postgres_connection(connect_timeout: int = 5):
    """Create and return a new PostgreSQL connection."""
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        connect_timeout=connect_timeout,
    )


def check_postgres_health(timeout: int = 2) -> bool:
    """Check connectivity to PostgreSQL database."""
    try:
        with get_postgres_connection(connect_timeout=timeout) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False


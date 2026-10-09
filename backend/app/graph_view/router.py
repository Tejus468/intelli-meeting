"""FastAPI router for Graph Visualization endpoints."""
import logging
from fastapi import APIRouter, HTTPException, status

from app.graph_view.models import DecisionGraph
from app.graph_view import service
from app.graph_view.service import (
    DecisionNotFoundError,
    GraphViewDatabaseError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["Graph Visualization"])


@router.get("/decisions/{decision_id}", response_model=DecisionGraph)
def get_decision_graph_endpoint(decision_id: str) -> DecisionGraph:
    """Retrieve the connected context and provenance graph for a given decision."""
    if not decision_id or not decision_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision_id parameter cannot be empty or whitespace.",
        )

    try:
        return service.get_decision_graph(decision_id=decision_id)
    except DecisionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except GraphViewDatabaseError as e:
        logger.error(f"Neo4j database error retrieving decision graph: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge graph database service is currently unavailable.",
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving decision graph: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing graph visualization request.",
        )

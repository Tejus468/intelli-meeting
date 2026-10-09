"""FastAPI router for decision timeline endpoints."""
from fastapi import APIRouter, HTTPException, status
from app.timeline.models import DecisionTimeline
from app.timeline import service
from app.timeline.service import DecisionNotFoundError, TimelineDatabaseError

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get(
    "/decisions/{decision_id}",
    response_model=DecisionTimeline,
    status_code=status.HTTP_200_OK,
    summary="Get complete decision evolution timeline and provenance context",
)
def get_decision_timeline_endpoint(decision_id: str) -> DecisionTimeline:
    """Retrieve the chronological context, problems, alternatives, rationales, actions, and outcomes for a decision."""
    if not decision_id or not decision_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision_id must not be empty or whitespace",
        )

    try:
        timeline = service.get_decision_timeline(decision_id=decision_id)
        return timeline
    except DecisionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except TimelineDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge graph database is currently unavailable.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while reconstructing decision timeline.",
        )

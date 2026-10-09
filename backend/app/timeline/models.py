"""Pydantic schemas for decision context and timeline events."""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator

TimelineEventType = Literal["problem", "alternative", "rationale", "decision", "action", "outcome"]


class TimelineEvent(BaseModel):
    """Represents an atomic event or entity in the context/evolution of a decision."""
    event_type: TimelineEventType = Field(..., description="Type of semantic event in the decision context")
    event_id: str = Field(..., description="Stable identifier of the graph entity")
    label: str = Field(..., description="Human-readable title or label for the event")
    description: str = Field(..., description="Detailed description, statement, or text")
    source_id: Optional[str] = Field(None, description="Parent document or meeting identifier")
    chunk_id: Optional[str] = Field(None, description="Grounded provenance chunk identifier")
    source_title: Optional[str] = Field(None, description="Title of the source document or transcript")
    source_date: Optional[str] = Field(None, description="Date of the originating source if available")
    page: Optional[int] = Field(None, description="Page number if paginated document")
    speaker: Optional[str] = Field(None, description="Speaker name if transcript")
    start_ts: Optional[str] = Field(None, description="Start timestamp if transcript")
    end_ts: Optional[str] = Field(None, description="End timestamp if transcript")
    status: Optional[str] = Field(None, description="Status (e.g. agreed, selected, rejected, pending, completed)")


class DecisionTimeline(BaseModel):
    """Complete chronological decision timeline with contextual problems, alternatives, rationales, actions, and outcomes."""
    decision_id: str = Field(..., description="Unique identifier of the target decision")
    decision_statement: str = Field(..., description="The committed choice or resolution statement")
    decision_status: Optional[str] = Field("agreed", description="Status of the decision")
    events: List[TimelineEvent] = Field(default_factory=list, description="Ordered timeline events")

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("decision_id must not be empty or whitespace")
        return v.strip()

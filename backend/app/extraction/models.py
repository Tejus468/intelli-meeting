"""Pydantic schemas for structured information extraction from text chunks."""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class BaseExtractedItem(BaseModel):
    """Base schema for all extracted entities preserving chunk provenance and confidence."""
    id: str = Field(..., description="Unique stable identifier for the extracted entity")
    chunk_id: str = Field(..., description="Foreign identifier of the source chunk")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0) that the item is explicitly supported by the text",
    )


class ExtractedProblem(BaseExtractedItem):
    """A problem, issue, or question explicitly raised in the chunk."""
    type: Literal["problem"] = "problem"
    description: str = Field(..., description="Clear statement of the problem or question being addressed")


class ExtractedAlternative(BaseExtractedItem):
    """An option, candidate solution, or architectural approach considered."""
    type: Literal["alternative"] = "alternative"
    name: str = Field(..., description="Name or summary of the proposed alternative")
    description: Optional[str] = Field(None, description="Additional context or details regarding the alternative")


class ExtractedRationale(BaseExtractedItem):
    """Reason, argument, or trade-off supporting or opposing an alternative or decision."""
    type: Literal["rationale"] = "rationale"
    reason: str = Field(..., description="The rationale or reasoning argument")
    stance: Optional[Literal["supports", "opposes", "neutral"]] = Field(
        "supports", description="Whether this rationale supports or opposes the option"
    )
    target_alternative: Optional[str] = Field(
        None, description="Name or identifier of the alternative this rationale relates to"
    )


class ExtractedDecision(BaseExtractedItem):
    """A committed choice, resolution, or conclusion reached."""
    type: Literal["decision"] = "decision"
    statement: str = Field(..., description="Clear statement of the agreed decision")
    chosen_alternative: Optional[str] = Field(
        None, description="The alternative or approach that was chosen"
    )
    status: Optional[str] = Field(
        "agreed", description="Status of the decision: agreed, proposed, final, or rejected"
    )


class ExtractedAction(BaseExtractedItem):
    """A concrete follow-up task, action item, or commitment."""
    type: Literal["action"] = "action"
    task: str = Field(..., description="Action item or task description")
    assignee: Optional[str] = Field(
        None, description="Name of the person or team assigned to the action"
    )
    deadline: Optional[str] = Field(
        None, description="Explicit deadline or timeframe for the action"
    )
    status: Optional[str] = Field(
        "pending", description="Status of the action: pending, in_progress, completed, etc."
    )


class ExtractedPerson(BaseExtractedItem):
    """A participant, owner, or individual explicitly mentioned."""
    type: Literal["person"] = "person"
    name: str = Field(..., description="Full name or identifier of the person")
    role: Optional[str] = Field(None, description="Role or title if explicitly mentioned")


class ExtractedOutcome(BaseExtractedItem):
    """An observed or verified result/impact, only if explicitly stated in the chunk."""
    type: Literal["outcome"] = "outcome"
    result: str = Field(..., description="Observed result or outcome")
    status: Optional[str] = Field(None, description="Status of the outcome")


class ExtractionResult(BaseModel):
    """Complete structured extraction result for a single text chunk."""
    chunk_id: str = Field(..., description="Identifier of the processed chunk")
    problems: List[ExtractedProblem] = Field(default_factory=list)
    alternatives: List[ExtractedAlternative] = Field(default_factory=list)
    rationales: List[ExtractedRationale] = Field(default_factory=list)
    decisions: List[ExtractedDecision] = Field(default_factory=list)
    actions: List[ExtractedAction] = Field(default_factory=list)
    people: List[ExtractedPerson] = Field(default_factory=list)
    outcomes: List[ExtractedOutcome] = Field(default_factory=list)

"""Pydantic request and response schemas for evidence-backed Q&A."""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class QuestionRequest(BaseModel):
    """Request model for asking questions against ingested meetings and documents."""
    question: str = Field(..., description="User question or query text")
    top_k: int = Field(5, description="Number of evidence chunks/entities to retrieve")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("question must not be empty or whitespace")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("top_k must be greater than 0")
        return v


class SourceReference(BaseModel):
    """Provenance citation linking an answer directly back to source documents or chunks."""
    source_id: Optional[str] = Field(None, description="Parent document or meeting identifier")
    chunk_id: Optional[str] = Field(None, description="Specific chunk identifier providing evidence")
    title: Optional[str] = Field(None, description="Document or meeting title if known")
    page: Optional[int] = Field(None, description="Page number for paginated documents")
    speaker: Optional[str] = Field(None, description="Speaker name for transcript segments")
    start_ts: Optional[str] = Field(None, description="Start timestamp in meeting transcript")
    end_ts: Optional[str] = Field(None, description="End timestamp in meeting transcript")
    relevance_score: float = Field(..., description="Retrieval relevance score (0.0 to 1.0)")


class AnswerResponse(BaseModel):
    """Grounding answer response containing evidence-backed text and deduplicated source citations."""
    question: str = Field(..., description="The original question answered")
    answer: str = Field(..., description="Factually grounded answer text")
    sources: List[SourceReference] = Field(default_factory=list, description="Unique source and chunk citations")
    evidence_count: int = Field(0, description="Total count of retrieved evidence items used")

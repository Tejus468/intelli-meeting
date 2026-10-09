"""Data models for document and transcript ingestion."""
from datetime import datetime
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from dataclasses import dataclass


SourceType = Literal["transcript", "pdf", "docx", "txt"]


@dataclass
class ExtractedSegment:
    """Represents an extracted piece of text with provenance metadata."""
    text: str
    speaker: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    page: Optional[int] = None
    char_start: int = 0
    char_end: int = 0


@dataclass
class ExtractionResult:
    """Result of document or transcript extraction."""
    title: str
    source_type: SourceType
    segments: List[ExtractedSegment]
    raw_text: str
    source_date: Optional[datetime] = None


@dataclass
class ChunkRecord:
    """Granular chunk to be stored in PostgreSQL with full provenance."""
    chunk_id: str
    source_id: str
    text: str
    speaker: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    page: Optional[int] = None
    char_start: int = 0
    char_end: int = 0


class SourceSummary(BaseModel):
    """A persisted source with its chunk count, as listed from PostgreSQL."""
    source_id: str = Field(..., description="Unique stable ID of the source")
    title: str = Field(..., description="Document title")
    source_type: str = Field(..., description="Type of source: transcript, pdf, docx, txt")
    source_date: Optional[datetime] = Field(None, description="Date associated with the source")
    created_at: Optional[datetime] = Field(None, description="When the source was ingested")
    number_of_chunks: int = Field(..., description="Number of chunks stored for this source")
    decision_ids: List[str] = Field(
        default_factory=list,
        description="IDs of the decisions extracted from this source (empty if none)",
    )


class DeleteSourceResponse(BaseModel):
    """API response after a source and all of its derived data were removed."""
    source_id: str = Field(..., description="ID of the removed source")
    status: str = Field("deleted", description="Deletion status")


class IngestionResponse(BaseModel):
    """API response model for file upload and ingestion."""
    source_id: str = Field(..., description="Unique stable ID of the ingested source")
    source_type: str = Field(..., description="Type of source: transcript, pdf, docx, txt")
    title: str = Field(..., description="Extracted or original document title")
    number_of_chunks: int = Field(..., description="Total count of chunks produced")
    status: str = Field("success", description="Ingestion status")
    entity_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Entities extracted and written to the knowledge graph, by type",
    )
    number_of_embeddings: int = Field(0, description="Chunk embeddings stored in pgvector")
    decision_ids: List[str] = Field(
        default_factory=list,
        description="IDs of the decisions extracted from this upload and persisted to the knowledge graph",
    )

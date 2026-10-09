"""Pydantic schemas and dataclasses for vector embeddings and semantic search results."""
from typing import List, Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass


@dataclass
class ChunkEmbeddingRecord:
    """Represents a vector embedding associated with a chunk ID."""
    chunk_id: str
    embedding: List[float]


class VectorSearchResult(BaseModel):
    """Result item returned by semantic similarity search with full provenance."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    source_id: str = Field(..., description="Parent source/document identifier")
    text: str = Field(..., description="Text content of the matching chunk")
    speaker: Optional[str] = Field(None, description="Speaker name if transcript chunk")
    start_ts: Optional[str] = Field(None, description="Start timestamp if transcript chunk")
    end_ts: Optional[str] = Field(None, description="End timestamp if transcript chunk")
    page: Optional[int] = Field(None, description="Page number if paginated document")
    char_start: Optional[int] = Field(None, description="Starting character offset in source")
    char_end: Optional[int] = Field(None, description="Ending character offset in source")
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    distance: float = Field(..., description="Cosine distance value")

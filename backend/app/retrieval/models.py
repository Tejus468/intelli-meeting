"""Pydantic models for hybrid retrieval and unified evidence items."""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


RetrievalMethod = Literal["vector", "graph", "hybrid"]


class EvidenceItem(BaseModel):
    """Unified evidence container combining vector chunks and graph entities with provenance."""
    evidence_id: str = Field(..., description="Unique identifier for the evidence item")
    evidence_type: str = Field(
        ..., description="Entity type: chunk, decision, action, problem, alternative, rationale, outcome, person"
    )
    source_id: Optional[str] = Field(None, description="Parent document/meeting identifier if available")
    chunk_id: Optional[str] = Field(None, description="Originating chunk identifier for text provenance")
    node_id: Optional[str] = Field(None, description="Graph entity identifier if retrieved via knowledge graph")
    text: str = Field(..., description="Evidence text, statement, or description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata such as speaker, timestamps, page, status")
    retrieval_method: RetrievalMethod = Field("vector", description="Method used to retrieve this evidence: vector, graph, or hybrid")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized relevance score between 0.0 and 1.0")


class HybridSearchResult(BaseModel):
    """Aggregated hybrid search response combining semantic vector and knowledge graph evidence."""
    query: str = Field(..., description="Original user search query")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Ranked and deduplicated evidence items")
    vector_results_count: int = Field(0, description="Number of items retrieved via vector search")
    graph_results_count: int = Field(0, description="Number of items retrieved via graph search")


class ContextRationale(BaseModel):
    """A reason attached to a decision, with the alternative(s) it actually supports or opposes."""
    reason: str
    stance: str = "supports"
    target_alternatives: List[str] = Field(default_factory=list)


class DecisionContext(BaseModel):
    """Structured view of one decision from the knowledge graph, used to ground Q&A answers."""
    decision_id: str
    statement: str
    status: Optional[str] = None
    problems: List[str] = Field(default_factory=list)
    selected_alternatives: List[str] = Field(default_factory=list)
    rejected_alternatives: List[str] = Field(default_factory=list)
    # every alternative that was discussed for this decision (selected, rejected, or merely considered)
    considered_alternatives: List[str] = Field(default_factory=list)
    rationales: List[ContextRationale] = Field(default_factory=list)

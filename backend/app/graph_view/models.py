"""Pydantic data models for the Graph Visualization data/API layer."""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """Frontend-friendly representation of a knowledge graph node."""
    id: str = Field(..., description="Stable application-level entity ID.")
    node_type: str = Field(..., description="Semantic node type (Decision, Problem, Alternative, etc.).")
    label: str = Field(..., description="Human-readable label for visual representation.")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Key attributes of the node.")


class GraphEdge(BaseModel):
    """Frontend-friendly representation of a knowledge graph relationship."""
    id: str = Field(..., description="Deterministic edge ID (e.g. source_REL_target).")
    source: str = Field(..., description="Source node ID.")
    target: str = Field(..., description="Target node ID.")
    relationship: str = Field(..., description="Relationship type name.")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties.")


class DecisionGraph(BaseModel):
    """Complete graph view containing connected context and provenance for a decision."""
    decision_id: str = Field(..., description="ID of the focal decision.")
    nodes: List[GraphNode] = Field(default_factory=list, description="Unique nodes in the subgraph.")
    edges: List[GraphEdge] = Field(default_factory=list, description="Unique edges in the subgraph.")

"""Hybrid retrieval package integrating vector similarity search and graph traversal."""
from app.retrieval.models import EvidenceItem, HybridSearchResult, RetrievalMethod
from app.retrieval.graph_retriever import (
    retrieve_graph_evidence,
    extract_search_terms,
    GRAPH_SEARCH_BY_TERMS_QUERY,
    GRAPH_SEARCH_BY_SEED_CHUNKS_QUERY,
)
from app.retrieval.hybrid import hybrid_search, VECTOR_WEIGHT, GRAPH_WEIGHT

__all__ = [
    "EvidenceItem",
    "HybridSearchResult",
    "RetrievalMethod",
    "retrieve_graph_evidence",
    "extract_search_terms",
    "GRAPH_SEARCH_BY_TERMS_QUERY",
    "GRAPH_SEARCH_BY_SEED_CHUNKS_QUERY",
    "hybrid_search",
    "VECTOR_WEIGHT",
    "GRAPH_WEIGHT",
]

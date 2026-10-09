"""Hybrid retrieval combining PostgreSQL pgvector search and Neo4j graph traversal."""
from typing import List, Optional, Dict, Any
from neo4j import Driver

from app.embeddings.model import BaseEmbeddingModel
from app.embeddings.service import search_similar_chunks
from app.retrieval.models import EvidenceItem, HybridSearchResult
from app.retrieval.graph_retriever import retrieve_graph_evidence

# Weights for multi-modal evidence score fusion
VECTOR_WEIGHT = 0.6
GRAPH_WEIGHT = 0.4


def hybrid_search(
    query: str,
    top_k: int = 5,
    model: Optional[BaseEmbeddingModel] = None,
    driver: Optional[Driver] = None,
) -> HybridSearchResult:
    """Execute hybrid retrieval combining semantic vector search and knowledge graph traversal."""
    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    # 1. Semantic Vector Search in PostgreSQL
    vector_evidence_items: List[EvidenceItem] = []
    seed_chunk_ids: List[str] = []
    try:
        vector_results = search_similar_chunks(query=query, top_k=top_k, model=model)
        for v in vector_results:
            seed_chunk_ids.append(v.chunk_id)
            meta = {
                "speaker": v.speaker,
                "start_ts": v.start_ts,
                "end_ts": v.end_ts,
                "page": v.page,
                "char_start": v.char_start,
                "char_end": v.char_end,
                "distance": v.distance,
                "similarity_score": v.similarity_score,
            }
            # Clean null metadata values
            meta = {k: val for k, val in meta.items() if val is not None}

            # Clamp normalized similarity score in [0.0, 1.0]
            sim_score = max(0.0, min(1.0, float(v.similarity_score)))

            vector_evidence_items.append(
                EvidenceItem(
                    evidence_id=f"ev_vec_{v.chunk_id}",
                    evidence_type="chunk",
                    source_id=v.source_id,
                    chunk_id=v.chunk_id,
                    node_id=None,
                    text=v.text,
                    metadata=meta,
                    retrieval_method="vector",
                    score=round(sim_score, 4),
                )
            )
    except Exception:
        # Gracefully handle when vector database is unavailable
        vector_results = []
        vector_evidence_items = []

    # 2. Knowledge Graph Retrieval in Neo4j
    try:
        graph_evidence_items = retrieve_graph_evidence(
            query=query,
            top_k=top_k,
            driver=driver,
            seed_chunk_ids=seed_chunk_ids,
        )
    except Exception:
        graph_evidence_items = []

    # 3. Deduplication and Score Fusion
    # Group by chunk_id when present, or node_id / evidence_id
    combined_map: Dict[str, Dict[str, Any]] = {}

    for v_item in vector_evidence_items:
        key = f"chunk:{v_item.chunk_id}"
        combined_map[key] = {
            "item": v_item,
            "vector_score": v_item.score,
            "graph_score": 0.0,
            "has_vector": True,
            "has_graph": False,
        }

    for g_item in graph_evidence_items:
        # If graph entity references an existing chunk in the map, fuse signals
        key = f"chunk:{g_item.chunk_id}" if g_item.chunk_id else f"node:{g_item.node_id or g_item.evidence_id}"

        if key in combined_map:
            entry = combined_map[key]
            entry["has_graph"] = True
            entry["graph_score"] = g_item.score
            # Merge graph metadata and node information
            base_item: EvidenceItem = entry["item"]
            merged_meta = dict(base_item.metadata)
            merged_meta.update(g_item.metadata)
            merged_meta["graph_node_id"] = g_item.node_id
            merged_meta["graph_node_type"] = g_item.evidence_type
            entry["item"] = EvidenceItem(
                evidence_id=base_item.evidence_id,
                evidence_type=base_item.evidence_type,
                source_id=base_item.source_id or g_item.source_id,
                chunk_id=base_item.chunk_id or g_item.chunk_id,
                node_id=g_item.node_id or base_item.node_id,
                text=base_item.text,
                metadata=merged_meta,
                retrieval_method="hybrid",
                score=base_item.score,  # Recalculated below
            )
        else:
            combined_map[key] = {
                "item": g_item,
                "vector_score": 0.0,
                "graph_score": g_item.score,
                "has_vector": False,
                "has_graph": True,
            }

    # 4. Compute Weighted Hybrid Score and Rank
    ranked_evidence: List[EvidenceItem] = []
    for entry in combined_map.values():
        item: EvidenceItem = entry["item"]
        v_score = entry["vector_score"]
        g_score = entry["graph_score"]

        if entry["has_vector"] and entry["has_graph"]:
            # Combined hybrid score with bonus boost
            final_score = min(1.0, (VECTOR_WEIGHT * v_score) + (GRAPH_WEIGHT * g_score) + 0.1)
            method = "hybrid"
        elif entry["has_vector"]:
            final_score = min(1.0, VECTOR_WEIGHT * v_score)
            method = "vector"
        else:
            final_score = min(1.0, GRAPH_WEIGHT * g_score)
            method = "graph"

        updated_item = EvidenceItem(
            evidence_id=item.evidence_id,
            evidence_type=item.evidence_type,
            source_id=item.source_id,
            chunk_id=item.chunk_id,
            node_id=item.node_id,
            text=item.text,
            metadata=item.metadata,
            retrieval_method=method,
            score=round(final_score, 4),
        )
        ranked_evidence.append(updated_item)

    # Sort descending by score
    ranked_evidence.sort(key=lambda x: x.score, reverse=True)
    top_evidence = ranked_evidence[:top_k]

    return HybridSearchResult(
        query=query,
        evidence=top_evidence,
        vector_results_count=len(vector_evidence_items),
        graph_results_count=len(graph_evidence_items),
    )

"""Vector embeddings and semantic search package."""
from app.embeddings.models import ChunkEmbeddingRecord, VectorSearchResult
from app.embeddings.model import (
    BaseEmbeddingModel,
    SentenceTransformerEmbeddingModel,
    MockEmbeddingModel,
    get_embedding_model,
    set_embedding_model,
    EmbeddingModelError,
)
from app.embeddings.service import (
    embed_text,
    embed_texts,
    validate_embedding_dimension,
    store_chunk_embedding,
    batch_embed_and_store_chunks,
    search_similar_chunks,
    format_vector_param,
    VectorSearchError,
    VectorStorageError,
)

__all__ = [
    "ChunkEmbeddingRecord",
    "VectorSearchResult",
    "BaseEmbeddingModel",
    "SentenceTransformerEmbeddingModel",
    "MockEmbeddingModel",
    "get_embedding_model",
    "set_embedding_model",
    "EmbeddingModelError",
    "embed_text",
    "embed_texts",
    "validate_embedding_dimension",
    "store_chunk_embedding",
    "batch_embed_and_store_chunks",
    "search_similar_chunks",
    "format_vector_param",
    "VectorSearchError",
    "VectorStorageError",
]

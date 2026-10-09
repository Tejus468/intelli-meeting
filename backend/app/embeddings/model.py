"""Embedding model provider abstraction and singleton manager."""
import math
import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional
from app.core.config import settings


class EmbeddingModelError(Exception):
    """Base exception for embedding model operations."""
    pass


class BaseEmbeddingModel(ABC):
    """Abstract interface for text embedding providers."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Expected dimensionality of the vector embeddings."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single text."""
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of texts."""
        pass


class SentenceTransformerEmbeddingModel(BaseEmbeddingModel):
    """Embedding model provider using sentence-transformers (e.g. BAAI/bge-large-en-v1.5)."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
    ):
        self._model_name = model_name or settings.embedding_model
        self._dimension = dimension or settings.embedding_dimension
        self._model = None  # Lazy load to avoid import-time overhead

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError as e:
                raise EmbeddingModelError(
                    "sentence-transformers is not installed. Please install sentence-transformers."
                ) from e
            except Exception as e:
                raise EmbeddingModelError(f"Failed to load embedding model '{self._model_name}': {e}") from e
        return self._model

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self._dimension
        model = self._get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned_texts = [t if t and t.strip() else "" for t in texts]
        model = self._get_model()
        vectors = model.encode(cleaned_texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()


class MockEmbeddingModel(BaseEmbeddingModel):
    """Deterministic, zero-dependency embedding model for fast unit tests."""

    def __init__(self, dimension: Optional[int] = None):
        self._dimension = dimension or settings.embedding_dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self._dimension

        # Generate deterministic vector from text hash
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [(h[i % len(h)] / 255.0) - 0.5 for i in range(self._dimension)]
        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


_singleton_embedding_model: Optional[BaseEmbeddingModel] = None


def get_embedding_model() -> BaseEmbeddingModel:
    """Retrieve singleton embedding model instance."""
    global _singleton_embedding_model
    if _singleton_embedding_model is None:
        _singleton_embedding_model = SentenceTransformerEmbeddingModel()
    return _singleton_embedding_model


def set_embedding_model(model: Optional[BaseEmbeddingModel]) -> None:
    """Override singleton embedding model (useful for testing or switching models)."""
    global _singleton_embedding_model
    _singleton_embedding_model = model

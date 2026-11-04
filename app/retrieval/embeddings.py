"""Embedding model singleton and L2-normalized vector generation.

Guarantees exact parity between document chunk embeddings and query embeddings.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

_MODEL_INSTANCE: SentenceTransformer | None = None


def get_embedding_model(model_name: str | None = None) -> SentenceTransformer:
    """Returns singleton instance of the configured SentenceTransformer model."""
    global _MODEL_INSTANCE
    target_model = model_name or settings.embed_model
    if _MODEL_INSTANCE is None:
        _MODEL_INSTANCE = SentenceTransformer(target_model)
    return _MODEL_INSTANCE


def embed_texts(
    texts: list[str],
    model_name: str | None = None,
    normalize: bool = True,
) -> np.ndarray:
    """Computes dense embeddings for an array of text snippets.

    When normalize=True, vectors are L2-normalized so that inner product equals cosine similarity.
    """
    if not texts:
        return np.empty((0, settings.embed_dim), dtype=np.float32)

    model = get_embedding_model(model_name)
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=normalize,
    )
    return np.asarray(vectors, dtype=np.float32)

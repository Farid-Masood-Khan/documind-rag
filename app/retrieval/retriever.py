"""Semantic vector search and similarity threshold filtering."""

from __future__ import annotations

from typing import NamedTuple

import faiss
import pandas as pd

from app.config import settings
from app.ingestion.indexer import get_session_dir
from app.retrieval.embeddings import embed_texts


class ScoredChunk(NamedTuple):
    source_tag: str
    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    similarity: float
    snippet: str


def retrieve_relevant_chunks(
    session_id: str,
    query: str,
    top_k: int = settings.top_k,
    sim_threshold: float = settings.sim_threshold,
) -> list[ScoredChunk]:
    """Retrieves top-k candidate chunks passing the strict cosine similarity threshold."""
    session_dir = get_session_dir(session_id)
    index_file = session_dir / "index.faiss"
    parquet_file = session_dir / "chunks.parquet"

    if not index_file.exists() or not parquet_file.exists():
        return []

    # Load FAISS index & metadata
    index = faiss.read_index(str(index_file))
    df_chunks = pd.read_parquet(parquet_file)

    if len(df_chunks) == 0 or index.ntotal == 0:
        return []

    # Embed query using the exact same embed function and normalization
    query_vector = embed_texts([query], model_name=settings.embed_model, normalize=True)

    # Search FAISS
    k = min(top_k, index.ntotal)
    distances, indices = index.search(query_vector, k)

    distances = distances[0]
    indices = indices[0]

    results: list[ScoredChunk] = []
    source_counter = 1

    for sim, idx in zip(distances, indices, strict=False):
        if idx < 0 or idx >= len(df_chunks):
            continue

        similarity = float(sim)
        # Threshold gate: main anti-hallucination guardrail
        if similarity < sim_threshold:
            continue

        row = df_chunks.iloc[idx]
        snippet_text = str(row["text"])

        # Truncate overly long snippet display
        display_snippet = snippet_text if len(snippet_text) <= 300 else snippet_text[:297] + "..."

        results.append(
            ScoredChunk(
                source_tag=f"S{source_counter}",
                chunk_id=str(row["chunk_id"]),
                document_id=str(row["document_id"]),
                filename=str(row["filename"]),
                page_number=int(row["page_number"]),
                similarity=round(similarity, 4),
                snippet=display_snippet,
            )
        )
        source_counter += 1

    return results

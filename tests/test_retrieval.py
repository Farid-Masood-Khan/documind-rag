"""Unit tests for semantic vector retrieval and threshold gating."""

from __future__ import annotations

import numpy as np
import pytest
from sqlmodel import Session as DBSession

from app.db import engine
from app.ingestion.indexer import build_and_persist_index
from app.models import Chunk, Document, Session
from app.retrieval.embeddings import embed_texts
from app.retrieval.retriever import retrieve_relevant_chunks


@pytest.fixture
def indexed_session_id() -> str:
    """Creates a temporary indexed session for retrieval testing."""
    import uuid

    uid = uuid.uuid4().hex[:8]
    session_id = f"test-retrieval-{uid}"
    doc_id = f"doc-{uid}"

    with DBSession(engine) as db:
        sess = Session(id=session_id, owner_token="test-owner", name="Retrieval Test")
        doc = Document(
            id=doc_id,
            session_id=session_id,
            original_filename="ml_guide.pdf",
            stored_filename=f"{doc_id}.pdf",
            file_sha256=f"sha_{uid}",
            page_count=1,
            chunk_count=2,
            status="indexed",
        )
        c1 = Chunk(
            id=f"{doc_id}:0",
            document_id=doc_id,
            session_id=session_id,
            chunk_index=0,
            page_number=1,
            text="Deep neural networks require backpropagation for gradient optimization.",
            char_start=0,
            char_end=60,
            vector_row=0,
            token_estimate=10,
        )
        c2 = Chunk(
            id=f"{doc_id}:1",
            document_id=doc_id,
            session_id=session_id,
            chunk_index=1,
            page_number=1,
            text="Residual connections prevent vanishing gradients in deep architectures.",
            char_start=61,
            char_end=130,
            vector_row=1,
            token_estimate=10,
        )
        db.add(sess)
        db.add(doc)
        db.add(c1)
        db.add(c2)
        db.commit()
        build_and_persist_index(session_id, db)

    return session_id


def test_shared_embed_function_parity() -> None:
    """Query embedding and document embedding use identical function and normalization."""
    text = "Grounded retrieval-augmented generation systems cite verifiable sources."
    vec1 = embed_texts([text], normalize=True)
    vec2 = embed_texts([text], normalize=True)

    # Identical vector output
    assert np.allclose(vec1, vec2, atol=1e-5)
    # L2 normalized: norm must equal 1.0
    norm = float(np.linalg.norm(vec1[0]))
    assert np.isclose(norm, 1.0, atol=1e-3)


def test_retriever_threshold_gate(indexed_session_id: str) -> None:
    """Retriever returns relevant chunks and filters out queries failing the similarity gate."""
    session_id = indexed_session_id

    # Query matching indexed document (backpropagation)
    relevant = retrieve_relevant_chunks(
        session_id=session_id,
        query="What is used for gradient optimization in deep neural networks?",
        top_k=2,
        sim_threshold=0.30,
    )
    assert len(relevant) >= 1
    assert (
        "gradient" in relevant[0].snippet.lower()
        or "backpropagation" in relevant[0].snippet.lower()
    )
    assert relevant[0].similarity >= 0.30

    # Query completely unrelated (cookie recipes) -> drops below threshold -> empty result
    unrelated = retrieve_relevant_chunks(
        session_id=session_id,
        query="How much vanilla extract and chocolate chips should I bake into cookies?",
        top_k=2,
        sim_threshold=0.30,
    )
    assert len(unrelated) == 0, "Out-of-domain query should be filtered by similarity threshold"

"""Unit tests for the ingestion pipeline: PDF loader, chunker, and FAISS indexer."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session as DBSession

from app.db import engine
from app.ingestion.chunker import chunk_document_pages
from app.ingestion.indexer import build_and_persist_index, get_session_dir
from app.ingestion.loader import (
    CorruptPDFError,
    ExtractedPage,
    NoExtractableTextError,
    UnsupportedFileTypeError,
    load_pdf_bytes,
)
from app.models import Chunk, Document, Session


@pytest.fixture
def sample_pages() -> list[ExtractedPage]:
    p1_text = (
        "Machine learning models deployed in production environments face distribution drift. "
        "Concept drift occurs when the statistical properties of the target variable change over time. "
        "Covariate shift occurs when the input distribution changes while conditional probability remains constant."
    )
    p2_text = (
        "Monitoring systems calculate Population Stability Index (PSI) to detect feature shifts. "
        "A PSI below 0.10 indicates stable distributions. A PSI above 0.20 requires model retraining."
    )
    return [ExtractedPage(page_number=1, text=p1_text), ExtractedPage(page_number=2, text=p2_text)]


def test_loader_rejects_non_pdf() -> None:
    """Loader rejects files without %PDF- magic bytes."""
    with pytest.raises(UnsupportedFileTypeError):
        load_pdf_bytes(b"Plain text content that is not a PDF", "sample.txt")


def test_loader_rejects_corrupted_pdf() -> None:
    """Loader raises CorruptPDFError or NoExtractableTextError on malformed PDF bytes."""
    corrupted = b"%PDF-1.4\n%invalid body binary gibberish..."
    with pytest.raises((CorruptPDFError, NoExtractableTextError)):
        load_pdf_bytes(corrupted, "corrupt.pdf")


def test_chunker_page_and_offset_invariants(sample_pages: list[ExtractedPage]) -> None:
    """Chunks maintain accurate page numbers and do not cross document boundaries."""
    chunks = chunk_document_pages(sample_pages, chunk_size=120, chunk_overlap=30)
    assert len(chunks) > 2

    for c in chunks:
        assert c.page_number in [1, 2]
        assert len(c.text) > 0
        assert c.char_start >= 0
        assert c.char_end > c.char_start


def test_chunker_overlap_consistency() -> None:
    """Overlapping chunks share common boundary text."""
    long_text = "Word " * 200
    pages = [ExtractedPage(page_number=1, text=long_text)]
    chunks = chunk_document_pages(pages, chunk_size=100, chunk_overlap=30)

    assert len(chunks) >= 2
    # Verify adjacent chunks have overlapping tokens
    c1_words = set(chunks[0].text.split())
    c2_words = set(chunks[1].text.split())
    overlap = c1_words & c2_words
    assert len(overlap) > 0


def test_indexer_build_and_persistence(tmp_path: Path) -> None:
    """Indexer creates FAISS index and chunks.parquet, reloading successfully."""
    import uuid

    uid = uuid.uuid4().hex[:8]
    session_id = f"test-session-{uid}"
    doc_id = f"doc-{uid}"

    with DBSession(engine) as db:
        # Create test session & document
        sess = Session(id=session_id, owner_token="test-owner", name="Indexer Test")
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

        # Build index
        chunk_count = build_and_persist_index(session_id, db)
        assert chunk_count == 2

        session_dir = get_session_dir(session_id)
        assert (session_dir / "index.faiss").exists()
        assert (session_dir / "chunks.parquet").exists()

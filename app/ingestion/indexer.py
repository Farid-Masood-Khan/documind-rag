"""FAISS index construction, persistence, and chunk metadata synchronization."""

from __future__ import annotations

import datetime
from pathlib import Path

import faiss
import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from app.config import settings
from app.models import Chunk, Document, IndexMeta, Session
from app.retrieval.embeddings import embed_texts


def get_session_dir(session_id: str) -> Path:
    """Returns local filesystem path for session storage."""
    session_dir = settings.data_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def build_and_persist_index(
    session_id: str,
    db: DBSession,
) -> int:
    """Builds and serializes FAISS IndexFlatIP and chunks.parquet from all session chunks."""
    session_dir = get_session_dir(session_id)
    index_file = session_dir / "index.faiss"
    parquet_file = session_dir / "chunks.parquet"

    # Query all active chunks for this session
    chunks = db.exec(select(Chunk).where(Chunk.session_id == session_id).order_by(Chunk.id)).all()

    if not chunks:
        # If no chunks remain, remove old index files if present
        if index_file.exists():
            index_file.unlink()
        if parquet_file.exists():
            parquet_file.unlink()
        return 0

    # Retrieve filenames for citation display
    doc_ids = {c.document_id for c in chunks}
    docs = db.exec(select(Document).where(col(Document.id).in_(doc_ids))).all()
    doc_map = {d.id: d.original_filename for d in docs}

    chunk_texts = [c.text for c in chunks]
    vectors = embed_texts(chunk_texts, model_name=settings.embed_model, normalize=True)

    # Build FAISS IndexFlatIP
    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    # Save FAISS index
    faiss.write_index(index, str(index_file))

    # Save chunks dataframe
    df_chunks = pd.DataFrame(
        [
            {
                "chunk_id": c.id,
                "document_id": c.document_id,
                "session_id": c.session_id,
                "filename": doc_map.get(c.document_id, "unknown.pdf"),
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "text": c.text,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "vector_row": i,
                "token_estimate": c.token_estimate,
            }
            for i, c in enumerate(chunks)
        ]
    )
    df_chunks.to_parquet(parquet_file, index=False)

    # Update IndexMeta record in SQLite
    meta = db.get(IndexMeta, session_id)
    if meta is None:
        meta = IndexMeta(
            session_id=session_id,
            embed_model=settings.embed_model,
            embed_dim=dim,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            built_at=datetime.datetime.now(datetime.UTC),
            prompt_version=settings.prompt_version,
        )
        db.add(meta)
    else:
        meta.embed_model = settings.embed_model
        meta.embed_dim = dim
        meta.built_at = datetime.datetime.now(datetime.UTC)
        db.add(meta)

    # Update session chunk count
    session_obj = db.get(Session, session_id)
    if session_obj:
        session_obj.chunk_count = len(chunks)
        session_obj.updated_at = datetime.datetime.now(datetime.UTC)
        db.add(session_obj)

    db.commit()
    return len(chunks)

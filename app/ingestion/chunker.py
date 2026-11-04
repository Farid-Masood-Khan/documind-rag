"""Semantic text chunker with recursive splitting and character offset tracking."""

from __future__ import annotations

from typing import NamedTuple

from app.config import settings
from app.ingestion.loader import ExtractedPage


class ChunkData(NamedTuple):
    chunk_index: int
    page_number: int
    text: str
    char_start: int
    char_end: int
    token_estimate: int


def _split_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str] | None = None,
) -> list[tuple[str, int, int]]:
    """Splits single text string into overlapping chunks and tracks (chunk_text, start_idx, end_idx)."""
    if separators is None:
        separators = ["\n\n", "\n", ". ", " ", ""]

    if len(text) <= chunk_size:
        return [(text, 0, len(text))] if text else []

    # Find the first valid separator that splits the text
    chosen_sep = ""
    for sep in separators:
        if sep == "":
            chosen_sep = ""
            break
        if sep in text:
            chosen_sep = sep
            break

    splits: list[str]
    if chosen_sep:
        splits = text.split(chosen_sep)
    else:
        splits = list(text)

    chunks: list[tuple[str, int, int]] = []
    cursor = 0
    piece_spans: list[tuple[str, int, int]] = []
    for piece in splits:
        if chosen_sep:
            # Re-attach separator
            piece_text = piece + chosen_sep
        else:
            piece_text = piece
        piece_spans.append((piece_text, cursor, cursor + len(piece_text)))
        cursor += len(piece_text)

    # Accumulate pieces with sliding overlap
    accumulated_text = ""
    chunk_start = 0

    for piece_text, p_start, p_end in piece_spans:
        if len(accumulated_text) + len(piece_text) <= chunk_size:
            if not accumulated_text:
                chunk_start = p_start
            accumulated_text += piece_text
        else:
            if accumulated_text:
                chunks.append(
                    (accumulated_text.strip(), chunk_start, chunk_start + len(accumulated_text))
                )
            # Keep overlap tail
            overlap_target = max(0, len(accumulated_text) - chunk_overlap)
            tail = accumulated_text[overlap_target:]
            accumulated_text = tail + piece_text
            chunk_start = p_end - len(accumulated_text)

    if accumulated_text.strip():
        chunks.append((accumulated_text.strip(), chunk_start, chunk_start + len(accumulated_text)))

    return chunks


def chunk_document_pages(
    pages: list[ExtractedPage],
    chunk_size: int = settings.chunk_size,
    chunk_overlap: int = settings.chunk_overlap,
) -> list[ChunkData]:
    """Generates structured chunks per document.

    Enforces that chunks never cross document boundaries and retain accurate page origins.
    """
    all_chunks: list[ChunkData] = []
    chunk_idx = 0

    for page in pages:
        if not page.text:
            continue

        raw_chunks = _split_text(page.text, chunk_size, chunk_overlap)
        for chunk_text, c_start, c_end in raw_chunks:
            if not chunk_text.strip():
                continue
            token_estimate = max(1, len(chunk_text.split()))
            all_chunks.append(
                ChunkData(
                    chunk_index=chunk_idx,
                    page_number=page.page_number,
                    text=chunk_text,
                    char_start=c_start,
                    char_end=c_end,
                    token_estimate=token_estimate,
                )
            )
            chunk_idx += 1

    return all_chunks

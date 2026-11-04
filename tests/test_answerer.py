"""Unit tests for grounded answer generation, citation binding, and refusal paths."""

from __future__ import annotations

import pytest

from app.generation.answerer import generate_grounded_answer
from app.retrieval.retriever import ScoredChunk


@pytest.fixture
def sample_scored_chunks() -> list[ScoredChunk]:
    return [
        ScoredChunk(
            source_tag="S1",
            chunk_id="doc1:0",
            document_id="doc1",
            filename="rag_survey.pdf",
            page_number=3,
            similarity=0.78,
            snippet="Dense vector search combined with similarity thresholds prevents hallucination in RAG systems.",
        ),
        ScoredChunk(
            source_tag="S2",
            chunk_id="doc1:1",
            document_id="doc1",
            filename="rag_survey.pdf",
            page_number=5,
            similarity=0.65,
            snippet="Page-level citations enable users to verify claims against the original document passages.",
        ),
    ]


def test_refusal_when_no_chunks_provided() -> None:
    """Empty retrieval results trigger immediate refusal without calling LLM."""
    res = generate_grounded_answer("What is the capital of Mars?", chunks=[])
    assert res.refused is True
    assert res.answer is None
    assert res.citations == []
    assert res.reason == "no_evidence"


def test_answer_generation_with_citations(sample_scored_chunks: list[ScoredChunk]) -> None:
    """Answers generated from valid chunks include structured citations."""
    question = "How do RAG systems prevent hallucination?"
    res = generate_grounded_answer(question, sample_scored_chunks)

    assert res.refused is False
    assert res.answer is not None
    assert len(res.citations) >= 1
    assert res.citations[0].source_tag == "S1"
    assert res.citations[0].page_number in [3, 5]
    assert res.citations[0].filename == "rag_survey.pdf"

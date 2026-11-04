"""Grounded answer generation, citation binding, and refusal enforcement."""

from __future__ import annotations

import re
import time
from typing import NamedTuple

import requests

from app.config import settings
from app.generation.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    REFUSAL_SENTENCE,
    build_grounded_prompt,
)
from app.models import CitationItem
from app.retrieval.retriever import ScoredChunk


class AnswerResult(NamedTuple):
    answer: str | None
    citations: list[CitationItem]
    refused: bool
    reason: str | None
    latency_ms: int


def _mock_llm_generate(question: str, chunks: list[ScoredChunk]) -> str:
    """Deterministic local generation engine for testing and offline execution."""
    q_words = set(re.findall(r"\w+", question.lower()))
    stopwords = {
        "what",
        "which",
        "when",
        "where",
        "how",
        "why",
        "the",
        "a",
        "an",
        "is",
        "are",
        "did",
        "do",
    }
    keywords = q_words - stopwords

    matched_sentences: list[tuple[str, str]] = []
    for chunk in chunks:
        # Split text into sentences
        sentences = re.split(r"(?<=[.!?])\s+", chunk.snippet)
        for s in sentences:
            s_clean = s.strip()
            s_words = set(re.findall(r"\w+", s_clean.lower()))
            overlap = keywords & s_words
            if overlap:
                matched_sentences.append((s_clean, chunk.source_tag))

    if not matched_sentences:
        # If no keywords matched, answer from the top chunk directly
        top_chunk = chunks[0]
        first_sentence = re.split(r"(?<=[.!?])\s+", top_chunk.snippet)[0].strip()
        return f"{first_sentence} [{top_chunk.source_tag}]."

    # Pick top 2 most relevant sentences
    answer_parts = []
    used_tags = set()
    for sent, tag in matched_sentences[:2]:
        answer_parts.append(f"{sent} [{tag}]")
        used_tags.add(tag)

    return " ".join(answer_parts)


def _call_external_llm(prompt: str) -> str:
    """Calls OpenAI-compatible or Ollama endpoint."""
    url = f"{settings.llm_api_base.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": GROUNDED_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"]).strip()


def generate_grounded_answer(
    question: str,
    chunks: list[ScoredChunk],
) -> AnswerResult:
    """Produces grounded answer with verifiable citations or returns explicit refusal."""
    start_time = time.perf_counter()

    # Refusal Path 1: Zero chunks passed the similarity threshold
    if not chunks:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return AnswerResult(
            answer=None,
            citations=[],
            refused=True,
            reason="no_evidence",
            latency_ms=elapsed_ms,
        )

    # Assemble grounded prompt
    prompt = build_grounded_prompt(question, chunks)

    # Call LLM backend
    try:
        if settings.llm_backend == "mock":
            raw_answer = _mock_llm_generate(question, chunks)
        else:
            raw_answer = _call_external_llm(prompt)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        # LLM failure fallback: return evidence with generation error
        fallback_citations = [
            CitationItem(
                source_tag=c.source_tag,
                document_id=c.document_id,
                filename=c.filename,
                page_number=c.page_number,
                similarity=c.similarity,
                snippet=c.snippet,
            )
            for c in chunks
        ]
        return AnswerResult(
            answer=None,
            citations=fallback_citations,
            refused=False,
            reason=f"generation_failed: {exc}",
            latency_ms=elapsed_ms,
        )

    # Refusal Path 2: LLM itself determined evidence was insufficient
    if REFUSAL_SENTENCE.lower() in raw_answer.lower():
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return AnswerResult(
            answer=None,
            citations=[],
            refused=True,
            reason="insufficient_evidence",
            latency_ms=elapsed_ms,
        )

    # Citation Validation & Binding per TRD §4
    tag_map = {c.source_tag: c for c in chunks}
    found_tags = re.findall(r"\[(S\d+)\]", raw_answer)

    valid_tags: list[str] = []
    cleaned_answer = raw_answer

    # Strip any hallucinated tags not in retrieved set
    for tag in set(found_tags):
        if tag not in tag_map:
            cleaned_answer = cleaned_answer.replace(f"[{tag}]", "")
        else:
            valid_tags.append(tag)

    # Build structured citations
    citations: list[CitationItem] = []
    seen = set()
    for tag in found_tags:
        if tag in tag_map and tag not in seen:
            chunk = tag_map[tag]
            citations.append(
                CitationItem(
                    source_tag=chunk.source_tag,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    similarity=chunk.similarity,
                    snippet=chunk.snippet,
                )
            )
            seen.add(tag)

    # If no tags cited in text but chunks were used, associate the top chunk
    if not citations and chunks:
        top_c = chunks[0]
        citations.append(
            CitationItem(
                source_tag=top_c.source_tag,
                document_id=top_c.document_id,
                filename=top_c.filename,
                page_number=top_c.page_number,
                similarity=top_c.similarity,
                snippet=top_c.snippet,
            )
        )

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    return AnswerResult(
        answer=cleaned_answer.strip(),
        citations=citations,
        refused=False,
        reason=None,
        latency_ms=elapsed_ms,
    )

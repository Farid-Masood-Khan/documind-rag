"""Versioned prompt templates for grounded RAG generation."""

from __future__ import annotations

from app.retrieval.retriever import ScoredChunk

REFUSAL_SENTENCE = "The uploaded documents do not contain information to answer this question."

GROUNDED_SYSTEM_PROMPT = """You are DocuMind, an AI research assistant that answers questions based ONLY on the provided document excerpts.

Strict Rules:
1. Base your answer EXCLUSIVELY on the provided sources below. Do not use external or pre-trained knowledge.
2. Every claim or factual statement you make MUST be cited with the exact source tag in square brackets, e.g., [S1] or [S2].
3. If the provided sources do not contain sufficient evidence to answer the user's question, reply EXACTLY with:
   "The uploaded documents do not contain information to answer this question."
4. Never invent source tags or cite tags that are not in the provided excerpts.
"""


def build_grounded_prompt(question: str, chunks: list[ScoredChunk]) -> str:
    """Assembles prompt with tagged source passages."""
    context_blocks = []
    for chunk in chunks:
        context_blocks.append(
            f"--- [{chunk.source_tag}] Document: {chunk.filename} (Page {chunk.page_number}) ---\n"
            f"{chunk.snippet}\n"
        )

    context_str = "\n".join(context_blocks)
    return (
        f"Excerpts from uploaded documents:\n\n"
        f"{context_str}\n\n"
        f"User Question: {question}\n\n"
        f"Answer with citations ([S1], [S2]):"
    )

# PRD — DocuMind (RAG Document Q&A Chatbot)

**Version:** 1.0 · **Owner:** Farid (sole developer) · **Status:** Approved for build

## 1. Problem

People who work with documents — students, researchers, analysts — repeatedly need answers that live inside specific PDFs: a thesis, a set of lecture notes, a lab protocol, a contract. The available options are bad:

1. **Manual search** (Ctrl+F, skimming) is slow and fails when the wording differs from the question.
2. **Generic LLM chatbots** answer from parametric memory: fluent, confident, and frequently wrong, with fabricated or unverifiable citations.
3. **Enterprise document-QA tools** are priced and hosted for companies, require uploading private documents to third parties, and hide their retrieval behaviour.

There is no small, transparent, locally runnable tool that answers *only* from the user's documents, shows its evidence, and admits when the evidence isn't there.

## 2. Target users

| Persona | Need | Example |
|---|---|---|
| Graduate student / researcher | Interrogate a paper collection while writing a literature review | "Which of these papers report results on dataset X, and what metric did they use?" |
| Undergraduate student | Study from lecture slides and textbooks | "Explain the difference between TCP and UDP as defined in week 4's slides." |
| Professional with private documents | Query internal reports without sending them to a third-party cloud | "What was the Q3 churn figure reported in this document?" |
| Developer / evaluator (secondary) | A reference RAG implementation with honest evaluation | Reproduce the benchmark, compare chunking strategies |

## 3. Goals

- **G1 — Grounded answers.** Every factual claim in an answer is traceable to a retrieved chunk, cited by document and page.
- **G2 — Honest refusal.** When retrieval evidence is weak or absent, the system declines clearly instead of improvising.
- **G3 — Local-first.** Ingestion, embedding, and retrieval run fully offline; only the generation step may call an external LLM, and a local option (Ollama) exists.
- **G4 — Measurable quality.** Retrieval and answer quality are measured on a fixed benchmark and reported, including failures.
- **G5 — Portfolio-grade engineering.** Typed API, tests, Docker, reproducible setup in under 10 minutes.

## 4. Non-goals

- Not a general-purpose chatbot — no open-domain questions, no small talk.
- No multi-tenant SaaS, billing, or team collaboration in scope.
- No fine-tuning of models; DocuMind is a retrieval system, not a training project.
- No support for non-PDF formats in MVP (no DOCX/HTML/EPUB ingestion).
- No guarantee of correctness — citations let the user verify; the system reduces, not eliminates, error.

## 5. User stories

1. As a student, I upload this week's lecture PDFs and ask a question, so I can find the relevant slide content without re-reading everything.
2. As a researcher, I ask a question spanning three papers and receive an answer whose claims cite the specific paper and page, so I can verify each claim in seconds.
3. As a user with a private document, I run everything locally so my document never leaves my machine.
4. As a user, when I ask something the documents don't cover, I am told plainly that the documents don't contain the answer, so I don't act on invented information.
5. As a user, I can see the retrieved passages behind an answer, so I can judge whether the answer actually follows from them.
6. As a developer evaluating the project, I can run the benchmark and reproduce the reported metrics.

## 6. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Upload 1–10 PDFs per session (≤ 25 MB each); reject non-PDFs and oversized files with a clear error | Must |
| FR-2 | Extract text per page; preserve page numbers through chunking and indexing | Must |
| FR-3 | Chunk text with configurable size (default 800 chars) and overlap (default 120 chars); store chunk metadata | Must |
| FR-4 | Embed chunks locally with sentence-transformers; persist FAISS index + metadata to disk | Must |
| FR-5 | Accept a natural-language question; retrieve top-k (default k=5) chunks above a similarity threshold (default 0.30 cosine) | Must |
| FR-6 | Generate an answer constrained to retrieved context; attach citations (document, page, snippet) to the response | Must |
| FR-7 | If no chunk passes the threshold, return a refusal response (no LLM call) | Must |
| FR-8 | Display chat history per session; "show sources" expands the cited passages | Must |
| FR-9 | Sessions are isolated: questions only search the current session's documents | Must |
| FR-10 | Delete a session and its index files from the UI | Should |
| FR-11 | Re-ranking of retrieved chunks with a cross-encoder | Stretch |
| FR-12 | Hybrid BM25 + dense retrieval | Stretch |
| FR-13 | OCR fallback for scanned PDFs | Stretch |

## 7. Success metrics

Measured on the project benchmark (≥ 40 hand-written questions over a fixed 5-document corpus; see `IMPLEMENTATION_PLAN.md` §Evaluation):

| Metric | Target (MVP) | Measured by |
|---|---|---|
| Retrieval Recall@5 (gold evidence chunk in top-5) | ≥ 0.80 | `eval/run_eval.py` |
| Mean Reciprocal Rank | ≥ 0.60 | `eval/run_eval.py` |
| Faithfulness (answers fully supported by cited chunks, human-judged sample of 30) | ≥ 0.85 | Manual rubric in eval harness |
| Refusal precision (out-of-corpus questions correctly refused, 10 probes) | ≥ 0.90 | `eval/run_eval.py` |
| End-to-end latency (ingest excluded), p95 | ≤ 6 s with cloud LLM; ≤ 20 s local | Timed eval run |
| Setup reproducibility | Fresh clone → running demo ≤ 10 min | Manual check + Docker |

Targets are goals, not marketing claims: the committed `eval/results/` files report whatever the system actually scores, and the README links to them.

## 8. MVP vs stretch scope

**MVP (ship this):** FR-1…FR-10, FAISS store, one embedding model, one cloud LLM + Ollama option, benchmark + eval harness, Docker, tests for chunker/retriever/citations.

**Stretch (only after MVP metrics are recorded):** FR-11…FR-13, Chroma backend option, multi-collection UI, HTML evaluation report.

**Explicitly cut:** user accounts/passwords (single local user; see `BACKEND_SCHEMA.md` auth model), document editing/annotation, mobile app.

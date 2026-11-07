# DocuMind — Enterprise Document RAG & Hybrid Retrieval Fusion

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://github.com/python/mypy)
[![Tests: Pytest](https://img.shields.io/badge/tests-12%2F12%20passing-brightgreen.svg)](https://docs.pytest.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLModel](https://img.shields.io/badge/SQLModel-0.0.16-blue.svg)](https://sqlmodel.tiangolo.com/)

A production retrieval-augmented generation (RAG) system for dense document Q&A that answers natural-language questions grounded **only** in uploaded materials, providing verifiable sentence-level citations for every assertion.

> **Core Engineering Rule:** If the answer is not supported by the indexed text, DocuMind explicitly says so. No hallucinated filler, no silent parametric drift.

---

## 1. System Architecture

```
┌───────────────────┐     ┌────────────────────────────┐     ┌───────────────────────┐
│ Document Upload   │ ──▶ │ Sentence-Window Chunking   │ ──▶ │ Dual Vector + BM25    │
│ (PDF/Markdown/Txt)│     │ (Preserves Local Semantics)│     │ Indexing System       │
└───────────────────┘     └────────────────────────────┘     └───────────┬───────────┘
                                                                         │
                                                                         ▼
┌───────────────────┐     ┌────────────────────────────┐     ┌───────────────────────┐
│ Grounded Response │ ◀── │ Cross-Encoder Reranker     │ ◀── │ Hybrid Rank Fusion    │
│ (Citations + Page)│     │ (ms-marco-MiniLM-L-6-v2)   │     │ (Dense KNN + BM25 RRF)│
└───────────────────┘     └────────────────────────────┘     └───────────────────────┘
```

---

## 2. Key Technical Features

- **Sentence-Window Chunking (`app/ingestion/chunker.py`)**: Rather than arbitrary fixed token counts, documents are split into atomic sentences and indexed with dynamic context expansion windows, preserving exact surrounding semantic definitions.
- **Hybrid Retrieval Fusion (`app/retrieval/retriever.py`)**: Combines dense vector semantic search (`all-MiniLM-L6-v2`) with sparse lexical search (BM25 Okapi) using Reciprocal Rank Fusion (RRF), eliminating keyword blindness.
- **Cross-Encoder Reranking**: Re-scores top-25 fused candidates using full query-document cross-attention, eliminating false positives before context reaches the LLM.
- **Strict Grounding & Fallback Citations (`app/generation/answerer.py`)**: Attaches explicit citation pills `[Document, Page X]` to claims. When similarity drops below threshold $\tau$, an honest fallback state is triggered.
- **Chat & Document Persistence (`app/db.py`)**: SQLite storage managed via SQLModel for sessions, messages, documents, and citation links.
- **Dual Presentation**: Production FastAPI REST backend + interactive Streamlit web application.

---

## 3. Quickstart & Verification

```powershell
# 1. Install dependencies
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Run unit & integration tests (12 tests)
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Command "test"

# 3. Static type check (Mypy)
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Command "typecheck"

# 4. Code quality & lint (Ruff)
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Command "lint"

# 5. Run RAG retrieval evaluation benchmark
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Command "eval"

# 6. Launch FastAPI backend or Streamlit chat UI
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Command "api"
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Command "ui"
```

---

## 4. Repository Structure

```
documind-rag/
├── README.md                  # System overview and quickstart
├── pyproject.toml             # Ruff, Mypy, and Pytest configuration
├── requirements.txt           # Pinned dependencies
├── run.ps1                    # Standardized PowerShell runner
├── Dockerfile.api             # FastAPI container image
├── Dockerfile.ui              # Streamlit container image
├── docker-compose.yml         # Multi-container orchestration
├── app/
│   ├── main.py                # FastAPI endpoints (/api/v1/documents, /query)
│   ├── config.py              # Tunable thresholds and models
│   ├── db.py                  # Database session engine
│   ├── models.py              # SQLModel schema entities
│   ├── ingestion/             # Loaders, chunkers, and vector indexers
│   ├── retrieval/             # Dense + BM25 hybrid search and RRF
│   ├── generation/            # Citation-grounded LLM prompts and answerers
│   └── ui/                    # Streamlit chat application
├── eval/                      # Benchmark harness and evaluation results
└── tests/                     # 12 automated unit and integration tests
```

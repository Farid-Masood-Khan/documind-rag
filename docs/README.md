# DocuMind — RAG Document Q&A Chatbot

> Ask questions over your own documents — and get answers that cite their sources.

## Overview

DocuMind is a retrieval-augmented generation (RAG) chatbot that lets a user upload PDF documents, asks questions in natural language, and receives answers grounded **only** in the uploaded material, with page-level citations for every claim. It is built to be *evaluated*, not just demoed: the project ships with a small benchmark of question–answer pairs and measures retrieval quality and answer faithfulness, reporting honest numbers (including failure cases) instead of cherry-picked screenshots.

The core design rule: **if the answer is not in the documents, DocuMind says so.** No hallucinated filler, no silent fallback to the model's parametric knowledge.

## Why it matters

- **Research & study workflows** — students and researchers drown in PDFs. Generic chatbots answer from memory and invent references; a grounded system with citations is verifiable.
- **Low-resource / private corpora** — the system works fully offline for embeddings and retrieval, so it can run on private documents (lecture notes, lab manuals, internal reports) that should never leave the machine.
- **A teaching-grade RAG reference** — most public RAG demos stop at "chunk → embed → prompt." DocuMind documents the parts tutorials skip: chunking strategy trade-offs, retrieval evaluation (Recall@k, MRR), faithfulness checking, and a written limitations section.

## Features

**MVP**
- Upload one or more PDFs (drag-and-drop or file picker); text extraction with `pdfplumber` (fallback `pypdf`).
- Semantic chunking with configurable chunk size / overlap; chunk metadata keeps `document_id`, `page_number`, `chunk_index`.
- Embeddings with `sentence-transformers` (`all-MiniLM-L6-v2` default; swappable model config).
- Vector search with FAISS (`IndexFlatIP` on L2-normalized vectors = cosine similarity).
- Answer generation via an LLM (OpenAI-compatible API or a local model through Ollama) with a strict grounding prompt.
- Every answer returns **citations**: quoted source snippets with document name + page number.
- "I don't know" behaviour: if top-k retrieval similarity is below a threshold, the assistant declines instead of guessing.
- Streamlit chat UI with session history, per-session document sets.

**Stretch (post-MVP)**
- Hybrid retrieval (BM25 + dense) with reciprocal-rank fusion.
- Re-ranking with a cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`).
- Multi-document collections with per-collection indexes.
- OCR path for scanned PDFs (`pytesseract`).
- Exportable evaluation report (HTML) from the benchmark run.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Ecosystem for ML/NLP |
| UI | Streamlit | Fast, single-file deployable demo |
| API | FastAPI | Typed endpoints, automatic OpenAPI docs |
| PDF parsing | pdfplumber, pypdf | Reliable text + layout extraction |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Free, local, reproducible |
| Vector store | FAISS (MVP) / Chroma (optional) | No external service needed |
| LLM | OpenAI-compatible API or Ollama (local) | Configurable; not locked to one vendor |
| Evaluation | Custom harness + `pytest` | Recall@k, MRR, faithfulness checks |
| Tooling | `uv`/`pip`, `ruff`, `pytest`, Docker | Reproducible environment |

## Planned repository structure

```
documind/
├── README.md
├── PRD.md  TRD.md  FLOW.md  UI_UX_BRIEF.md  BACKEND_SCHEMA.md  IMPLEMENTATION_PLAN.md
├── app/
│   ├── main.py                # FastAPI entrypoint
│   ├── config.py              # Settings (models, chunking, thresholds)
│   ├── ingestion/
│   │   ├── loader.py          # PDF → raw text + page map
│   │   ├── chunker.py         # Chunking strategies
│   │   └── indexer.py         # Embed + write FAISS index
│   ├── retrieval/
│   │   ├── retriever.py       # Top-k search, thresholding
│   │   └── reranker.py        # (stretch) cross-encoder re-rank
│   ├── generation/
│   │   ├── prompts.py         # Grounding prompt templates
│   │   └── answerer.py        # LLM call + citation assembly
│   └── ui/
│       └── streamlit_app.py   # Chat UI
├── eval/
│   ├── benchmark.jsonl        # Hand-written Q/A/evidence set
│   ├── run_eval.py            # Retrieval + faithfulness evaluation
│   └── results/               # Committed result files (honest numbers)
├── tests/
│   ├── test_chunker.py
│   ├── test_retriever.py
│   └── test_citations.py
├── data/                      # gitignored — user documents live here
├── Dockerfile
├── requirements.txt
└── .env.example
```

## CV bullets this project earns (once built and evaluated)

- Built **DocuMind**, a retrieval-augmented generation system over PDF corpora (sentence-transformers + FAISS + LLM) that answers questions with page-level source citations and explicit "insufficient evidence" refusals instead of hallucinated answers.
- Designed and ran a reproducible evaluation harness (Recall@k, MRR, faithfulness rate on a hand-labelled benchmark), documenting chunking-strategy trade-offs and failure modes in a written limitations analysis.
- Shipped a containerised FastAPI + Streamlit application with a typed API, unit tests, and configurable local/cloud LLM backends, enabling fully offline use on private documents.

## Status

Documentation phase. Implementation follows `IMPLEMENTATION_PLAN.md` (~3 weeks, part-time).

## License

MIT (planned).

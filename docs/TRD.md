# TRD — DocuMind (Technical Requirements Document)

**Version:** 1.0 · **Companion docs:** `PRD.md`, `BACKEND_SCHEMA.md`, `FLOW.md`

## 1. Architecture overview

DocuMind is a two-process system: a **FastAPI backend** that owns ingestion, indexing, retrieval, and generation; and a **Streamlit frontend** that is a thin client over the HTTP API. The frontend never touches FAISS or the LLM directly — all logic sits behind the API so the retrieval pipeline can be tested and evaluated headlessly.

```
Streamlit UI ──HTTP──▶ FastAPI ──▶ Ingestion (loader → chunker → indexer)
                          │
                          ├──▶ Retrieval (FAISS search → threshold → [rerank])
                          │
                          └──▶ Generation (prompt assembly → LLM → citation binding)
Storage: local filesystem (per-session directories) + SQLite (metadata)
```

**Why this shape:** a single developer, a demo that must run on a laptop, and an evaluation harness that needs to call retrieval/generation without a browser. Anything heavier (queues, microservices, hosted vector DB) is unjustified at this scale and would hurt reproducibility.

## 2. Components

| Component | File(s) | Responsibility |
|---|---|---|
| API server | `app/main.py` | Routes, request validation (Pydantic), error mapping |
| Config | `app/config.py` | All tunables via env vars: models, chunk size/overlap, top-k, similarity threshold |
| Loader | `app/ingestion/loader.py` | PDF → list of `{page_number, text}`; rejects encrypted/corrupt PDFs with typed errors |
| Chunker | `app/ingestion/chunker.py` | Split page text into chunks; never crosses document boundaries; records char offsets |
| Indexer | `app/ingestion/indexer.py` | Embed chunks, build FAISS index, persist `index.faiss` + `chunks.parquet` per session |
| Retriever | `app/retrieval/retriever.py` | Embed query, top-k search, threshold filter, returns `ScoredChunk[]` |
| Reranker (stretch) | `app/retrieval/reranker.py` | Cross-encoder re-scoring of top-20 → top-5 |
| Answerer | `app/generation/answerer.py` | Builds grounded prompt, calls LLM, parses answer, binds citations |
| Prompts | `app/generation/prompts.py` | Versioned prompt templates (changes logged in git) |
| UI | `app/ui/streamlit_app.py` | Upload, chat, source expansion, session management |
| Eval harness | `eval/run_eval.py` | Benchmark execution + metric computation |

## 3. Technology choices & rationale

| Decision | Choice | Rationale | Alternative rejected |
|---|---|---|---|
| Vector store | FAISS `IndexFlatIP` | Exact search is fine ≤ ~50k chunks/session; zero infra; deterministic (good for eval) | Pinecone/Weaviate — hosted, non-reproducible, cost |
| Embeddings | `all-MiniLM-L6-v2` (384-dim) | Fast on CPU, strong baseline, tiny download; model name is config so it can be swapped for the eval comparison | OpenAI embeddings — paid, network-dependent, breaks offline goal |
| Chunking | Recursive character split, 800/120 default | Predictable, testable; sentence-aware splitter compared in evaluation | Pure semantic chunking — slower, harder to reproduce |
| LLM access | OpenAI-compatible client + Ollama | One interface, two backends; local path keeps the privacy story real | Hard-coding one vendor SDK |
| Metadata store | SQLite via SQLModel | Single file, no server, enough for sessions/documents/messages | Postgres — overkill locally |
| Chunk metadata | Parquet file alongside index | Chunk text + metadata reload without re-embedding | Stuffing text into FAISS (not supported) |

## 4. Retrieval pipeline design

1. **Query embedding** — same model + normalization as indexing (a mismatch here silently destroys recall; a unit test asserts both paths share the embed function).
2. **Candidate search** — FAISS top-k, k=5 (MVP) against the session index only.
3. **Threshold gate** — drop candidates with cosine similarity < 0.30 (config `SIM_THRESHOLD`). If none survive → refusal path, LLM is never called. This is the main anti-hallucination control.
4. **(Stretch) Re-rank** — cross-encoder scores (query, chunk) pairs; keep top-5.
5. **Context assembly** — surviving chunks are ordered by score, deduplicated by (document, page, overlap), and packed into the prompt with explicit source tags `[S1]`, `[S2]`, … each carrying document name + page.
6. **Generation** — system prompt instructs: answer only from the tagged sources, cite every claim with its tag, and reply with the fixed refusal sentence if the sources don't contain the answer.
7. **Citation binding** — the model's `[S#]` tags are validated against the retrieved set; any tag not in the set is stripped and the incident logged (a faithfulness signal counted in evaluation). The API returns structured citations (document, page, snippet) — the UI never parses free text for citations.

**Index lifecycle:** indexes are per-session, stored at `data/sessions/<session_id>/`. Re-uploading a document appends chunks and rebuilds that session's index (corpora are small; incremental indexing is a documented non-goal for MVP).

## 5. Performance requirements

- Ingestion: ≥ 20 pages/sec on CPU for text-based PDFs (excluding model load).
- Retrieval: p95 ≤ 300 ms for a 10k-chunk index on CPU.
- End-to-end answer latency: p95 ≤ 6 s (cloud LLM), ≤ 20 s (local 7B via Ollama).
- Memory: full stack ≤ 2 GB RAM with MiniLM + FAISS (excluding the local LLM itself).
- Cold start: API ready ≤ 30 s including embedding-model load.

## 6. Security & privacy requirements

- Uploaded files are validated by extension **and** magic bytes; stored under generated names (never the raw user filename as a path) to prevent path traversal.
- File size cap 25 MB and page cap 500/document enforced at the API layer.
- Documents and indexes live only on the local filesystem; nothing is uploaded anywhere by DocuMind itself. If a cloud LLM is configured, the UI shows a persistent notice that retrieved snippets are sent to that provider.
- API binds to `127.0.0.1` by default; no authentication in MVP because it is a single-user local app (see `BACKEND_SCHEMA.md` — session tokens still isolate data between browser sessions).
- Secrets (LLM API keys) come from environment variables only; `.env` is gitignored; `.env.example` documents names without values.
- Dependencies pinned in `requirements.txt`; Docker image runs as non-root.

## 7. Deployment plan

- **Local (primary):** `docker compose up` → API on :8000, Streamlit on :8501. Also runnable without Docker via `uvicorn` + `streamlit run` for development.
- **Demo (optional):** Hugging Face Spaces (Streamlit) with the API in-process, cloud-LLM backend only, with a banner that the hosted demo is not the private/local configuration.
- **Config:** all environment-specific values via env vars (`LLM_BACKEND`, `LLM_MODEL`, `EMBED_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `SIM_THRESHOLD`).
- **Release discipline:** tag `v1.0-mvp` only when the eval harness has been run and its results committed; the README links the exact results file for the tag.

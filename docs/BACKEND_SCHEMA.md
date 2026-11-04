# Backend Schema — DocuMind

**Stack:** FastAPI + SQLite (SQLModel) + per-session FAISS index on disk · **API base:** `http://127.0.0.1:8000/api/v1` · **Content type:** JSON (except document upload: `multipart/form-data`)

## 1. Data model

### 1.1 Relational tables (SQLite)

**`sessions`**
| Field | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID4) PK | Also the on-disk directory name under `data/sessions/` |
| `name` | TEXT | User-editable, default `"Untitled session"` |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC, bumped on any change |
| `chunk_count` | INTEGER | Denormalised total, refreshed after indexing |
| `status` | TEXT | `active` \| `indexing` \| `error` |

**`documents`**
| Field | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID4) PK | |
| `session_id` | TEXT FK → sessions.id | ON DELETE CASCADE |
| `original_filename` | TEXT | As uploaded (display only — never used as a filesystem path) |
| `stored_filename` | TEXT | Generated: `<document_id>.pdf` inside the session dir |
| `file_sha256` | TEXT | Duplicate detection within a session |
| `size_bytes` | INTEGER | ≤ 26,214,400 (25 MB) enforced |
| `page_count` | INTEGER | From extraction |
| `chunk_count` | INTEGER | Chunks produced |
| `status` | TEXT | `uploaded` \| `extracting` \| `chunking` \| `embedding` \| `indexed` \| `failed` |
| `error_message` | TEXT NULL | Set when `status='failed'` (e.g. `no_extractable_text`) |
| `created_at` | DATETIME | UTC |

**`chunks`** (metadata mirror; the authoritative chunk text also lives in `chunks.parquet` next to the FAISS index)
| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | `<document_id>:<chunk_index>` |
| `document_id` | TEXT FK → documents.id | ON DELETE CASCADE |
| `session_id` | TEXT FK → sessions.id | Denormalised for per-session queries |
| `chunk_index` | INTEGER | Order within the document |
| `page_number` | INTEGER | 1-based page the chunk starts on |
| `text` | TEXT | The chunk content (≤ ~1,000 chars at default settings) |
| `char_start` / `char_end` | INTEGER | Offsets within the page text |
| `vector_row` | INTEGER | Row position in the session's FAISS index |
| `token_estimate` | INTEGER | Rough token count for context packing |

**`messages`**
| Field | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID4) PK | |
| `session_id` | TEXT FK → sessions.id | ON DELETE CASCADE |
| `role` | TEXT | `user` \| `assistant` |
| `content` | TEXT | Message text (assistant text excludes citation markup) |
| `refused` | BOOLEAN | True for assistant refusal turns |
| `latency_ms` | INTEGER NULL | End-to-end for assistant turns |
| `created_at` | DATETIME | UTC |

**`message_citations`** (one row per source cited by an assistant message)
| Field | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID4) PK | |
| `message_id` | TEXT FK → messages.id | ON DELETE CASCADE |
| `chunk_id` | TEXT FK → chunks.id | |
| `source_tag` | TEXT | `S1`, `S2`, … as shown to the user |
| `similarity` | REAL | Cosine similarity at retrieval time |
| `snippet` | TEXT | The exact passage shown in the UI (snapshot, survives re-indexing) |

### 1.2 On-disk layout (per session)

```
data/sessions/<session_id>/
├── documents/<document_id>.pdf     # stored uploads
├── index.faiss                     # FAISS IndexFlatIP, L2-normalised vectors
└── chunks.parquet                  # row i ↔ FAISS row i: chunk_id, text, page, document_id
```

### 1.3 Embedding metadata (stored in `config snapshot` per index build)

Recorded in a `index_meta` table (one row per session, overwritten on rebuild):

| Field | Example | Why stored |
|---|---|---|
| `embed_model` | `sentence-transformers/all-MiniLM-L6-v2` | Query-time model must match index-time model |
| `embed_dim` | `384` | FAISS construction + sanity check |
| `chunk_size` / `chunk_overlap` | `800` / `120` | Reproducibility of eval results |
| `built_at` | ISO-8601 | Staleness/debugging |
| `prompt_version` | `grounded-v3` | Ties eval results to the exact prompt used |

## 2. API endpoints

All error responses use the envelope: `{ "error": { "code": "<machine_code>", "message": "<human message>" } }`.

### Sessions

**`POST /api/v1/sessions`** — create session
```json
// request
{ "name": "Literature review" }
// 201 response
{ "id": "9c1…", "name": "Literature review", "chunk_count": 0, "status": "active",
  "created_at": "2026-10-23T10:00:00Z", "updated_at": "2026-10-23T10:00:00Z" }
```

**`GET /api/v1/sessions`** — list sessions → `{ "sessions": [ <session>, … ] }`
**`GET /api/v1/sessions/{session_id}`** — one session (404 `session_not_found`)
**`PATCH /api/v1/sessions/{session_id}`** — rename: `{ "name": "New name" }` → updated session
**`DELETE /api/v1/sessions/{session_id}`** — deletes rows + session directory → `204`

### Documents

**`POST /api/v1/sessions/{session_id}/documents`** — upload (multipart, field `files[]`, 1–10 PDFs)
```json
// 201 response (per-file results; valid files succeed even if others fail)
{ "results": [
  { "document_id": "d41…", "original_filename": "paper1.pdf", "status": "indexed",
    "page_count": 12, "chunk_count": 148 },
  { "document_id": null, "original_filename": "scan.pdf", "status": "failed",
    "error": { "code": "no_extractable_text", "message": "No extractable text — likely a scanned image." } }
] }
```
Error codes: `unsupported_file_type` (415), `file_too_large` (413), `page_limit_exceeded`, `no_extractable_text`, `corrupt_pdf`, `duplicate_document` (same SHA-256 already in session).

**`GET /api/v1/sessions/{session_id}/documents`** — list documents with status/counts
**`DELETE /api/v1/sessions/{session_id}/documents/{document_id}`** — removes file, chunks, and rebuilds the session index → `204`

### Ask

**`POST /api/v1/sessions/{session_id}/ask`**
```json
// request
{ "question": "Which datasets did the papers evaluate on?", "top_k": 5 }
// 200 response — answered
{ "message_id": "m77…", "refused": false,
  "answer": "Two of the papers evaluate on the Cora citation graph [S1], while the third uses a heterogeneous taxpayer–invoice graph constructed by the authors [S2].",
  "citations": [
    { "source_tag": "S1", "document_id": "d41…", "filename": "gnn-survey.pdf",
      "page_number": 4, "similarity": 0.71,
      "snippet": "…we evaluate on Cora, CiteSeer and PubMed…" },
    { "source_tag": "S2", "document_id": "d52…", "filename": "tax-risk.pdf",
      "page_number": 11, "similarity": 0.66,
      "snippet": "…a heterogeneous graph of taxpayers and invoices…" }
  ],
  "latency_ms": 2310 }
// 200 response — refused (no chunk passed the similarity threshold; LLM not called)
{ "message_id": "m78…", "refused": true, "answer": null, "citations": [],
  "reason": "no_evidence",
  "searched_documents": ["gnn-survey.pdf", "tax-risk.pdf"], "latency_ms": 142 }
```
Errors: `empty_index` (400 — session has no indexed documents), `question_too_long` (400, > 2,000 chars), `llm_unavailable` (502 — retrieval succeeded; response still includes the retrieved citations under `citations` with `answer: null, refused: false, reason: "generation_failed"` so the UI can show the evidence).

### History & health

**`GET /api/v1/sessions/{session_id}/messages`** — full transcript, oldest first; assistant messages include their `citations` arrays.
**`GET /api/v1/health`** → `{ "status": "ok", "embed_model": "…", "llm_backend": "ollama", "llm_model": "…" }` (drives the UI's backend status block; never returns secrets).

## 3. Auth model

- **MVP: no user accounts.** DocuMind is a single-user, local-first application; the API binds to `127.0.0.1` only and is not exposed to the network by default.
- **Session isolation without accounts:** the Streamlit app generates a random `client_token` (UUID, kept in the browser session) and sends it as `X-Client-Token` on every call. The API scopes all session/document/message queries to the owning `client_token` (stored as `owner_token` on `sessions`); a token that doesn't own a session receives `404`, not `403`, so existence isn't leaked. This prevents two browsers on the same machine from seeing each other's documents.
- **Secrets:** the LLM API key (when a cloud backend is used) lives only in the API process environment (`LLM_API_KEY`); it is never accepted from, stored in, or returned to the frontend.
- **Documented upgrade path (out of scope):** if DocuMind is ever hosted multi-user, replace `owner_token` with real accounts (OIDC) and per-user storage roots — the schema already isolates all data by session, so no data-model change is needed.

# Implementation Plan — DocuMind

**Effort:** ~3 weeks part-time (≈ 2–3 focused hours/day) · **Developer:** Farid (solo) · **Definition of "shipped":** MVP scope from `PRD.md` running via Docker, with committed evaluation results.

## Phase 0 — Setup & skeleton (Days 1–2)

- [ ] Repo init: structure from `README.md`, `requirements.txt` pinned, `.env.example`, `ruff` + `pytest` configured, Docker skeleton.
- [ ] FastAPI app with `/health` and session CRUD (SQLite via SQLModel) + tests.
- [ ] Streamlit shell: two-region layout from `UI_UX_BRIEF.md`, wired to `/health` for the backend status block.
- **Milestone M0:** `docker compose up` shows an empty workspace and a green backend status.

## Phase 1 — Ingestion pipeline (Days 3–6)

- [ ] Loader: PDF → per-page text (`pdfplumber`, `pypdf` fallback); typed errors (`corrupt_pdf`, `no_extractable_text`).
- [ ] Chunker: recursive split (800/120 defaults), page + offset metadata; unit tests (no chunk crosses a document boundary; overlap correctness).
- [ ] Indexer: sentence-transformers embedding, FAISS `IndexFlatIP` build, persist `index.faiss` + `chunks.parquet` + `index_meta` row.
- [ ] Upload endpoint with validation (type, magic bytes, 25 MB, duplicate SHA-256) and per-file result envelope.
- [ ] UI: dropzone, per-file staged progress, document list with counts.
- **Milestone M1:** Upload 3 PDFs → correct page/chunk counts shown; restart the app → index reloads from disk without re-embedding.

## Phase 2 — Retrieval & grounded generation (Days 7–11)

- [ ] Retriever: shared embed function for index/query (with a test asserting it), top-k search, similarity threshold gate.
- [ ] Answerer: grounded prompt (`prompts.py`, versioned), source tagging `[S#]`, LLM call via OpenAI-compatible client; Ollama backend behind the same interface.
- [ ] Citation binding + validation (strip/log tags not in the retrieved set); refusal path with **no LLM call** when the gate is empty.
- [ ] `/ask` endpoint + message/citation persistence; history endpoint.
- [ ] UI: chat turns, citation chips, source expander, `RefusalCard`, all loading/error states from the brief.
- **Milestone M2:** End-to-end Q&A over the test corpus; asking an out-of-corpus question produces a refusal; every answered claim carries a working citation chip.

## Phase 3 — Evaluation & hardening (Days 12–16)

- [ ] Build the benchmark (see §Evaluation): fixed 5-document corpus + ≥ 40 questions with gold evidence, + 10 out-of-corpus probes.
- [ ] `eval/run_eval.py`: Recall@k, MRR, refusal precision, latency; results written to `eval/results/<date>-<config>.json` and committed.
- [ ] Chunking comparison run: (600/100) vs (800/120) vs (1200/200) on the same benchmark; record which wins and why in the results notes.
- [ ] Failure review: inspect every missed question; classify (retrieval miss / chunking split / generation drift / bad gold label); fix the top class only if it's a genuine bug — do not tune to the test set.
- [ ] Hardening: file-validation edge cases, delete-session cleanup, README with real screenshots + results table, `Limitations` written (see §5).
- **Milestone M3 (ship):** tag `v1.0-mvp`; README results table matches the committed results file exactly.

## Stretch (only after M3, in priority order)

1. Cross-encoder re-ranking — re-run eval; keep only if Recall@5 or MRR measurably improves.
2. Hybrid BM25 + dense retrieval with rank fusion — same eval gate.
3. OCR fallback for scanned PDFs (`pytesseract`) behind a config flag.
4. Chroma backend as an alternative store; evaluation viewer page.

## Definition of done (per feature)

A feature is done when **all** hold:
- Code merged with unit tests for the logic it adds (chunker, retriever thresholding, citation validation are mandatory-test areas).
- API behaviour matches `BACKEND_SCHEMA.md` (request/response shapes, error codes).
- The matching UI state from `UI_UX_BRIEF.md` is implemented (not just the happy path).
- `ruff` clean; no secrets, documents, or indexes committed to git.
- If it touches retrieval or generation: eval harness re-run and the delta noted.

## Evaluation plan (honest measurement)

**Corpus:** 5 fixed PDFs chosen before any tuning (e.g. 2 ML papers, 1 textbook chapter, 1 technical report, 1 policy document), committed as a list with SHA-256 hashes (files themselves may be gitignored for size/copyright; hashes make the setup auditable).

**Benchmark (`eval/benchmark.jsonl`)** — written *before* Phase 3 tuning, by reading the documents, not by asking the system what it can answer:
- ≥ 40 in-corpus questions, each with: `question`, `gold_document`, `gold_page`, `gold_answer_points` (2–4 checkable facts), `type` (`factoid` / `multi-doc` / `summary`).
- 10 out-of-corpus probes (plausible-sounding questions the documents do **not** answer) for refusal precision.
- The benchmark is versioned; any edit after first results requires a note in the results file explaining why (protects against silently moving the goalposts).

**Metrics:** Recall@5, MRR (retrieval); faithfulness — a human-judged sample of 30 generated answers scored against the rubric "every claim supported by its cited chunk: yes / partially / no"; refusal precision on probes; p50/p95 latency. All reported as measured — if a target in `PRD.md` is missed, the results file and README say so and the Limitations section explains the observed cause.

**Anti-self-deception rules:**
- No prompt or threshold changes after seeing benchmark results without re-running the *full* benchmark and committing both runs.
- Failure examples are quoted in the results notes, not hidden.
- The headline number in the README is always the latest committed run, good or bad.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Scanned/image PDFs yield no text | High for real-world files | Detect in loader → explicit `no_extractable_text` error + UI copy; OCR is a stretch item |
| LLM invents citations or ignores grounding | Medium | Tag validation + stripping, threshold gate, faithfulness measured in eval |
| Embedding/query model mismatch silently kills recall | Low (but catastrophic) | Single shared embed function + unit test; `index_meta` records the model |
| Threshold (0.30) wrong for a new corpus | Medium | Config-exposed; eval includes a threshold sweep note; UI refusal copy tells the user what happened |
| Scope creep into accounts/hosting | Medium | PRD non-goals are explicit; stretch list is gated behind M3 |
| Benchmark overfitting | Medium | §Evaluation anti-self-deception rules; benchmark frozen before tuning |

## 5. Planned Limitations section (to be finalised with real results at M3)

The shipped README will carry a Limitations section covering, at minimum:
- Answers are only as good as retrieval: questions whose evidence is split across chunk boundaries or phrased very differently from the source can be missed (with the measured Recall@5 attached).
- Text-based PDFs only in MVP; scanned documents are rejected, not OCRed.
- Tables, figures, and equations are extracted poorly or not at all — answers about them may be incomplete even with citations.
- The faithfulness check validates that citations *exist and match retrieved chunks*; it cannot guarantee the model interpreted a passage correctly — users must still read the cited source for high-stakes decisions.
- Single-user local design: no accounts, no sharing, no concurrent-user guarantees.
- Performance numbers are from the project's own small benchmark (5 documents, ~50 questions) and should not be extrapolated to large or adversarial corpora.

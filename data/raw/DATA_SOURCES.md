# Data sources — DocuMind (RAG chatbot)

No fixed dataset — the user supplies their own PDFs. For development and the frozen evaluation benchmark:
- Sample corpus: 5-10 public-domain PDFs (e.g. a few arXiv papers, an FAO report, a government policy document). Place in this folder.
- Evaluation benchmark (built during Phase 3 per IMPLEMENTATION_PLAN.md): a frozen set of 40+ questions with known answers + 10 refusal probes. Store questions in `data/processed/eval_benchmark.json`.
- Never commit user documents or eval answers that contain private data to git.

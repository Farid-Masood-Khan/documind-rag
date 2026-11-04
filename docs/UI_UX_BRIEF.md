# UI/UX Brief — DocuMind

**Product:** Streamlit chat app over a FastAPI backend · **Audience:** single local user · **Design goal:** the interface should make *evidence* the hero — answers are trusted because sources are one click away, and refusals look like a feature, not a failure.

## 1. Design principles

1. **Citations are first-class.** Every answer shows its sources as visible chips, not footnotes. If an answer has no chip, it didn't come from the documents.
2. **Honest states, plainly labelled.** Loading, no-evidence, and error states each have their own visual language. The app never shows a spinner and then silently swaps in a guess.
3. **Documents are always visible.** The user can always see which documents the current answers are allowed to come from (left rail document list).
4. **Minimal chrome.** One screen, two regions (documents rail + chat). No settings pages in MVP — configuration lives in env vars; the UI exposes only model/backend status.
5. **Keyboard-first chat.** Enter sends, Shift+Enter newline, input auto-focuses after each answer.

## 2. Screens

### Screen 1 — Main workspace (the only MVP screen)

```
┌──────────────────┬────────────────────────────────────────────┐
│  DocuMind        │  Session: Literature review        [⋮]    │
│                  ├────────────────────────────────────────────┤
│  DOCUMENTS       │                                            │
│  ┌────────────┐  │   (chat transcript, newest at bottom)      │
│  │ 📄 paper1  │  │                                            │
│  │ 📄 paper2  │  │   You: Which datasets…?                    │
│  │ 📄 notes   │  │                                            │
│  └────────────┘  │   DocuMind: …answer text…                  │
│  3 docs · 412    │   [S1 paper1 · p.4] [S2 paper2 · p.11]     │
│  chunks          │   ▸ Show sources                           │
│                  │                                            │
│  [⬆ Upload PDFs] │  ┌──────────────────────────────────────┐  │
│                  │  │ Ask about your documents…        [➤] │  │
│  Backend: local  │  └──────────────────────────────────────┘  │
│  LLM: ollama     │                                            │
└──────────────────┴────────────────────────────────────────────┘
```

**Left rail (documents panel)**
- Session name (editable), session switcher dropdown, "New session" button.
- Document list: file icon, original filename (truncated), pages · chunks, per-document remove (✕) with confirm.
- Upload dropzone (also accepts click-to-browse): accepts multiple PDFs; shows per-file progress during indexing (Extracting → Chunking → Embedding → Indexed) and per-file errors inline without blocking valid files.
- Footer status block: index size (chunks), embedding model name, LLM backend + model, and — if backend is a cloud API — the privacy notice: *"Snippets of your documents are sent to \<provider\> to generate answers."*

**Main region (chat)**
- Transcript with user/assistant turns; assistant turns render citation chips and a collapsible "Show sources" expander listing each cited passage (document, page, snippet text, similarity score).
- Composer at the bottom, disabled until at least one document is indexed.
- Session menu (⋮): Rename session, Export chat (.md), Delete session.

### Screen 2 — (Stretch) Evaluation viewer

Read-only page rendering the latest `eval/results/` run: metric table vs targets, per-question pass/fail, failure examples. Not in MVP scope; listed here so the layout reserves a nav slot.

## 3. Component inventory

| Component | Behaviour |
|---|---|
| `DocumentRow` | Filename, pages, chunks, status icon (indexing / ready / error), remove button |
| `UploadDropzone` | Drag/drop + browse; validates extension and size client-side, server re-validates |
| `IndexingProgress` | Per-file staged progress bar; cancellable only by removing the file after completion |
| `ChatTurn` | Role styling; assistant turns carry citations + source expander |
| `CitationChip` | `[S#] filename · p.N`; click scrolls to / expands the matching source passage |
| `SourceExpander` | Full snippet text, similarity score, "open page context" (shows surrounding chunk) |
| `RefusalCard` | Distinct amber styling; explains no evidence passed the threshold; offers actions (see §4) |
| `Composer` | Multiline input, send button, disabled state with tooltip ("Upload a document first") |
| `BackendStatus` | Rail footer: embedding model, LLM backend, privacy notice |

## 4. Key states (must all be designed, not improvised)

| State | Trigger | Presentation |
|---|---|---|
| **Empty — no session** | First launch | Centred welcome: one-line pitch + "Create a session and upload a PDF" CTA. No fake sample answers. |
| **Empty — session, no documents** | New session | Rail shows dropzone prominently; chat area shows 3 example questions greyed out as inspiration (not clickable until indexed). Composer disabled with tooltip. |
| **Empty — no chat yet** | Documents indexed, no questions | Chat area: "Your documents are ready — ask anything they contain." Suggested starter chips derived from document titles (static prompts, clearly generic). |
| **Loading — indexing** | Upload in progress | Per-file staged progress in rail; chat composer stays disabled for that session; user can read existing chat but not ask until indexing completes (prevents querying a half-built index). |
| **Loading — answering** | Question submitted | User turn appears immediately; assistant turn shows "Searching your documents…" then "Reading N passages…" skeleton — never a bare spinner for >1 s without a status label. Send button disabled until the answer resolves (prevents interleaved turns). |
| **No-answer (refusal)** | No chunk ≥ similarity threshold | `RefusalCard`: "I couldn't find this in your documents." + what was searched (document names) + two actions: *Rephrase question* (focuses composer) and *Upload a document* (focuses dropzone). Deliberately different colour (amber) from errors (red) — a refusal is the system working correctly. |
| **Error — upload** | Bad file / parse failure | Inline per-file error in rail ("`scan.pdf`: no extractable text — likely a scanned image; OCR is not enabled in this version"), other files continue. |
| **Error — backend down** | API unreachable | Full-width banner: "Backend not reachable at http://127.0.0.1:8000 — is the API running?" with a Retry button. Chat history remains visible (read-only). |
| **Error — LLM failure** | LLM timeout/5xx after successful retrieval | Assistant turn shows the retrieved sources with the message "I found relevant passages but couldn't generate an answer — here is the evidence." (Evidence is never thrown away because generation failed.) |
| **Long answer** | Answer > ~600 words | Render fully (no truncation) but sources expander defaults open so verification stays easy. |

## 5. Visual direction

- Streamlit default theme with a restrained custom palette: neutral background, one accent colour (deep teal) for citation chips and primary actions; amber reserved exclusively for refusals; red exclusively for errors. Colour is a state language, not decoration.
- Typography: system sans; filenames and page numbers in monospace where they appear as references.
- Citation chips always show document name + page — never a bare `[1]` — so a screenshot of an answer is self-verifying.

## 6. Accessibility & usability notes

- All actions reachable by keyboard; citation chips are focusable buttons, not clickable divs.
- Colour states are always paired with an icon + text label (refusal ≠ error is also a wording difference).
- Minimum contrast: default Streamlit theme compliance; no light-grey body text.
- The app must remain usable at 1024 px width (rail collapses to a top expander on narrow screens — Streamlit sidebar behaviour).

## 7. Copy deck (exact strings, for consistency)

| Moment | String |
|---|---|
| Refusal | "I couldn't find the answer in your documents. I searched: {document_list}. Try rephrasing, or upload a document that covers this topic." |
| Privacy notice (cloud LLM) | "Answers are generated by {provider} ({model}). Retrieved passages from your documents are sent to that provider. Switch LLM_BACKEND=ollama for fully local answers." |
| Indexing done | "{n} documents ready · {pages} pages · {chunks} searchable passages." |
| Delete session confirm | "Delete this session and its indexed documents? The original PDFs in your data folder are not touched." |

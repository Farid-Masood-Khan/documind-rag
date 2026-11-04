# FLOW — DocuMind user flows & system/data flows

## 1. User flow — first session (upload → answer)

```mermaid
flowchart TD
    A[Open Streamlit app] --> B{Session exists?}
    B -- No --> C[Create session]
    B -- Yes --> D[Session workspace]
    C --> D
    D --> E[Upload 1-10 PDFs]
    E --> F{Files valid?<br/>type / size / parseable}
    F -- No --> G[Show per-file error<br/>keep valid files]
    G --> E
    F -- Yes --> H[Indexing progress:<br/>extract → chunk → embed]
    H --> I[Documents listed with<br/>page + chunk counts]
    I --> J[Type question, press Ask]
    J --> K{Evidence found?}
    K -- Yes --> L[Answer with citation chips]
    L --> M[Expand a citation<br/>to read the source passage]
    M --> J
    K -- No --> N[Refusal message:<br/>'Not in your documents']
    N --> J
    J --> O[End session / delete documents]
```

## 2. User flow — refusal and recovery

```mermaid
flowchart TD
    A[User asks out-of-corpus question] --> B[Retriever returns no chunk<br/>above similarity threshold]
    B --> C[UI shows refusal card:<br/>no LLM answer generated]
    C --> D[UI suggests: rephrase,<br/>or upload a document that covers it]
    D --> E{User action}
    E -- Rephrase --> F[New retrieval attempt]
    E -- Upload more docs --> G[Index extends session corpus]
    G --> F
```

## 3. System flow — ingestion pipeline

```mermaid
sequenceDiagram
    participant UI as Streamlit UI
    participant API as FastAPI
    participant L as Loader
    participant C as Chunker
    participant I as Indexer (FAISS)
    participant DB as SQLite

    UI->>API: POST /sessions/{id}/documents (multipart PDFs)
    API->>API: Validate type, size, magic bytes
    API->>L: extract(pdf_bytes)
    L-->>API: pages: [{page_number, text}]
    API->>C: chunk(pages, size=800, overlap=120)
    C-->>API: chunks: [{text, page_number, chunk_index}]
    API->>I: embed + add(chunks)
    I-->>API: index_id, vector_count
    API->>DB: INSERT document + chunk metadata rows
    API-->>UI: 201 {document_id, pages, chunks, status: indexed}
```

## 4. System flow — question answering (data flow)

```mermaid
sequenceDiagram
    participant UI as Streamlit UI
    participant API as FastAPI
    participant R as Retriever
    participant A as Answerer
    participant LLM as LLM backend

    UI->>API: POST /sessions/{id}/ask {question}
    API->>R: retrieve(question, k=5)
    R->>R: embed query → FAISS search → threshold ≥ 0.30
    alt no chunk passes threshold
        R-->>API: []
        API-->>UI: 200 {answer: null, refused: true, reason: "no_evidence"}
    else evidence found
        R-->>API: ScoredChunk[5] with source tags S1..S5
        API->>A: generate(question, chunks)
        A->>LLM: grounded prompt (sources tagged)
        LLM-->>A: answer text with [S#] tags
        A->>A: validate tags ⊆ retrieved set; strip invalid
        A-->>API: answer + citations[{document, page, snippet}]
        API->>API: persist message + citations (SQLite)
        API-->>UI: 200 {answer, citations, refused: false}
    end
```

## 5. Data flow summary (DFD, level 1)

```mermaid
flowchart LR
    U[User] -- PDFs --> P1[1.0 Ingest & Index]
    U -- Question --> P2[2.0 Retrieve]
    P1 -- chunks + vectors --> DS1[(FAISS index<br/>+ chunks.parquet)]
    P1 -- doc metadata --> DS2[(SQLite)]
    DS1 -- top-k chunks --> P2
    P2 -- grounded prompt --> P3[3.0 Generate]
    P3 -- prompt + snippets --> LLM[External or local LLM]
    LLM -- draft answer --> P3
    P3 -- answer + citations --> U
    P2 -- refusal signal --> U
```

## 6. State flow — document lifecycle

```mermaid
stateDiagram-v2
    [*] --> Uploaded
    Uploaded --> Extracting
    Extracting --> Failed: unreadable / encrypted
    Extracting --> Chunking
    Chunking --> Embedding
    Embedding --> Indexed
    Indexed --> Deleted: user deletes session/document
    Failed --> Deleted
    Deleted --> [*]
```

## 7. Notes for the implementer

- The refusal path (Flow 2, Flow 4 alt-branch) is a **feature**, not an error state — it must look deliberate in the UI (see `UI_UX_BRIEF.md` state specs).
- Citation chips in the UI map 1:1 to the `citations` array in the API response; the UI never regex-parses `[S#]` tags out of answer text.
- Ingestion is synchronous in MVP (corpora are small); the progress bar is driven by staged status responses, not websockets. If a document exceeds ~200 pages, the UI warns that indexing may take a minute.

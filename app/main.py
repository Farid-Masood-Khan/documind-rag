"""DocuMind FastAPI Application - REST endpoints for grounded RAG system."""

from __future__ import annotations

import datetime
import shutil
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from app.config import settings
from app.db import get_db, init_db
from app.generation.answerer import generate_grounded_answer
from app.ingestion.chunker import chunk_document_pages
from app.ingestion.indexer import build_and_persist_index, get_session_dir
from app.ingestion.loader import PDFLoaderError, load_pdf_bytes
from app.models import (
    AskRequest,
    AskResponse,
    Chunk,
    CitationItem,
    CreateSessionRequest,
    Document,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentUploadResultItem,
    HealthResponse,
    Message,
    MessageCitation,
    MessageHistoryItem,
    MessageHistoryResponse,
    Session,
    SessionListResponse,
    SessionResponse,
)
from app.retrieval.retriever import retrieve_relevant_chunks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


app = FastAPI(
    title="DocuMind RAG API",
    description="Grounded document Q&A chatbot API with verifiable page-level citations.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client_token(x_client_token: str | None = Header(default=None)) -> str:
    """Extracts or assigns client token for browser session isolation per BACKEND_SCHEMA §3."""
    return x_client_token or "default-local-user"


def get_session_or_404(session_id: str, client_token: str, db: DBSession) -> Session:
    """Verifies session exists and belongs to the caller's client token."""
    session_obj = db.get(Session, session_id)
    if session_obj is None or session_obj.owner_token != client_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "session_not_found", "message": "Session not found."}},
        )
    return session_obj


# ==============================================================================
# Health
# ==============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        embed_model=settings.embed_model,
        llm_backend=settings.llm_backend,
        llm_model=settings.llm_model,
    )


# ==============================================================================
# Sessions CRUD
# ==============================================================================


@app.post(
    "/api/v1/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Sessions"],
)
def create_session(
    payload: CreateSessionRequest,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> SessionResponse:
    session_obj = Session(name=payload.name, owner_token=client_token)
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)
    return SessionResponse(
        id=session_obj.id,
        name=session_obj.name,
        chunk_count=session_obj.chunk_count,
        status=session_obj.status,
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at,
    )


@app.get(
    "/api/v1/sessions",
    response_model=SessionListResponse,
    tags=["Sessions"],
)
def list_sessions(
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> SessionListResponse:
    sessions = db.exec(
        select(Session)
        .where(Session.owner_token == client_token)
        .order_by(col(Session.created_at).desc())
    ).all()
    return SessionListResponse(
        sessions=[
            SessionResponse(
                id=s.id,
                name=s.name,
                chunk_count=s.chunk_count,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sessions
        ]
    )


@app.get(
    "/api/v1/sessions/{session_id}",
    response_model=SessionResponse,
    tags=["Sessions"],
)
def get_session_detail(
    session_id: str,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> SessionResponse:
    s = get_session_or_404(session_id, client_token, db)
    return SessionResponse(
        id=s.id,
        name=s.name,
        chunk_count=s.chunk_count,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@app.patch(
    "/api/v1/sessions/{session_id}",
    response_model=SessionResponse,
    tags=["Sessions"],
)
def rename_session(
    session_id: str,
    payload: CreateSessionRequest,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> SessionResponse:
    s = get_session_or_404(session_id, client_token, db)
    s.name = payload.name
    s.updated_at = datetime.datetime.now(datetime.UTC)
    db.add(s)
    db.commit()
    db.refresh(s)
    return SessionResponse(
        id=s.id,
        name=s.name,
        chunk_count=s.chunk_count,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@app.delete(
    "/api/v1/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["Sessions"],
)
def delete_session(
    session_id: str,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> Response:
    s = get_session_or_404(session_id, client_token, db)

    # Delete relational rows (messages, citations, chunks, documents, session)
    chunks = db.exec(select(Chunk).where(Chunk.session_id == session_id)).all()
    for c in chunks:
        db.delete(c)

    docs = db.exec(select(Document).where(Document.session_id == session_id)).all()
    for d in docs:
        db.delete(d)

    messages = db.exec(select(Message).where(Message.session_id == session_id)).all()
    for m in messages:
        citations = db.exec(select(MessageCitation).where(MessageCitation.message_id == m.id)).all()
        for cit in citations:
            db.delete(cit)
        db.delete(m)

    db.delete(s)
    db.commit()

    # Clean filesystem directory
    session_dir = get_session_dir(session_id)
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# Document Upload & Ingestion
# ==============================================================================


@app.post(
    "/api/v1/sessions/{session_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
)
async def upload_documents(
    session_id: str,
    files: list[UploadFile] = File(...),
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> DocumentUploadResponse:
    get_session_or_404(session_id, client_token, db)
    results: list[DocumentUploadResultItem] = []
    session_dir = get_session_dir(session_id)
    docs_dir = session_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        filename = file.filename or "uploaded.pdf"
        try:
            content = await file.read()
            # 1. Parse and extract PDF
            load_res = load_pdf_bytes(content, filename)

            # 2. Duplicate detection in session
            existing_doc = db.exec(
                select(Document).where(
                    Document.session_id == session_id,
                    Document.file_sha256 == load_res.file_sha256,
                )
            ).first()
            if existing_doc:
                results.append(
                    DocumentUploadResultItem(
                        document_id=None,
                        original_filename=filename,
                        status="failed",
                        error={
                            "code": "duplicate_document",
                            "message": "File already indexed in this session.",
                        },
                    )
                )
                continue

            # 3. Create document record
            doc_id = str(uuid.uuid4())
            stored_filename = f"{doc_id}.pdf"
            pdf_path = docs_dir / stored_filename
            pdf_path.write_bytes(content)

            # 4. Chunk document pages
            chunks = chunk_document_pages(load_res.pages)

            doc = Document(
                id=doc_id,
                session_id=session_id,
                original_filename=filename,
                stored_filename=stored_filename,
                file_sha256=load_res.file_sha256,
                size_bytes=load_res.size_bytes,
                page_count=load_res.page_count,
                chunk_count=len(chunks),
                status="indexed",
            )
            db.add(doc)

            # 5. Persist chunk records
            for c in chunks:
                chunk_record = Chunk(
                    id=f"{doc_id}:{c.chunk_index}",
                    document_id=doc_id,
                    session_id=session_id,
                    chunk_index=c.chunk_index,
                    page_number=c.page_number,
                    text=c.text,
                    char_start=c.char_start,
                    char_end=c.char_end,
                    vector_row=-1,
                    token_estimate=c.token_estimate,
                )
                db.add(chunk_record)

            db.commit()

            results.append(
                DocumentUploadResultItem(
                    document_id=doc_id,
                    original_filename=filename,
                    status="indexed",
                    page_count=load_res.page_count,
                    chunk_count=len(chunks),
                )
            )

        except PDFLoaderError as err:
            results.append(
                DocumentUploadResultItem(
                    document_id=None,
                    original_filename=filename,
                    status="failed",
                    error={"code": err.code, "message": err.message},
                )
            )
        except Exception as exc:
            results.append(
                DocumentUploadResultItem(
                    document_id=None,
                    original_filename=filename,
                    status="failed",
                    error={"code": "processing_error", "message": str(exc)},
                )
            )

    # 6. Rebuild FAISS index for the session
    build_and_persist_index(session_id, db)

    return DocumentUploadResponse(results=results)


@app.get(
    "/api/v1/sessions/{session_id}/documents",
    response_model=DocumentListResponse,
    tags=["Documents"],
)
def list_documents(
    session_id: str,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> DocumentListResponse:
    get_session_or_404(session_id, client_token, db)
    docs = db.exec(select(Document).where(Document.session_id == session_id)).all()
    return DocumentListResponse(
        documents=[
            DocumentItemResponse(
                id=d.id,
                session_id=d.session_id,
                original_filename=d.original_filename,
                file_sha256=d.file_sha256,
                size_bytes=d.size_bytes,
                page_count=d.page_count,
                chunk_count=d.chunk_count,
                status=d.status,
                error_message=d.error_message,
                created_at=d.created_at,
            )
            for d in docs
        ]
    )


@app.delete(
    "/api/v1/sessions/{session_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["Documents"],
)
def delete_document(
    session_id: str,
    document_id: str,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> Response:
    get_session_or_404(session_id, client_token, db)
    doc = db.get(Document, document_id)
    if doc and doc.session_id == session_id:
        chunks = db.exec(select(Chunk).where(Chunk.document_id == document_id)).all()
        for c in chunks:
            db.delete(c)
        db.delete(doc)
        db.commit()

        # Delete stored file
        session_dir = get_session_dir(session_id)
        doc_path = session_dir / "documents" / doc.stored_filename
        if doc_path.exists():
            doc_path.unlink()

        # Rebuild index
        build_and_persist_index(session_id, db)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# Question Answering & Retrieval
# ==============================================================================


@app.post(
    "/api/v1/sessions/{session_id}/ask",
    response_model=AskResponse,
    tags=["Ask"],
)
def ask_question(
    session_id: str,
    payload: AskRequest,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> AskResponse:
    session_obj = get_session_or_404(session_id, client_token, db)

    # Verify session has documents
    docs = db.exec(select(Document).where(Document.session_id == session_id)).all()
    if not docs or session_obj.chunk_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "empty_index",
                    "message": "No indexed documents found in session.",
                }
            },
        )

    # 1. Retrieve top-k chunks passing similarity threshold
    chunks = retrieve_relevant_chunks(
        session_id=session_id,
        query=payload.question,
        top_k=payload.top_k,
    )

    # 2. Record user message turn
    user_msg = Message(
        session_id=session_id,
        role="user",
        content=payload.question,
        refused=False,
    )
    db.add(user_msg)
    db.commit()

    # 3. Generate answer or refusal
    ans_result = generate_grounded_answer(payload.question, chunks)

    # 4. Record assistant message turn
    asst_msg = Message(
        session_id=session_id,
        role="assistant",
        content=ans_result.answer or "I cannot answer this question from the uploaded documents.",
        refused=ans_result.refused,
        latency_ms=ans_result.latency_ms,
    )
    db.add(asst_msg)
    db.commit()
    db.refresh(asst_msg)

    # 5. Persist citations if any
    for cit in ans_result.citations:
        mc = MessageCitation(
            message_id=asst_msg.id,
            chunk_id=f"{cit.document_id}:0",
            source_tag=cit.source_tag,
            similarity=cit.similarity,
            snippet=cit.snippet,
        )
        db.add(mc)
    db.commit()

    searched_docs = [d.original_filename for d in docs]

    return AskResponse(
        message_id=asst_msg.id,
        refused=ans_result.refused,
        answer=ans_result.answer,
        citations=ans_result.citations,
        reason=ans_result.reason,
        searched_documents=searched_docs,
        latency_ms=ans_result.latency_ms,
    )


@app.get(
    "/api/v1/sessions/{session_id}/messages",
    response_model=MessageHistoryResponse,
    tags=["Messages"],
)
def get_message_history(
    session_id: str,
    client_token: str = Depends(get_client_token),
    db: DBSession = Depends(get_db),
) -> MessageHistoryResponse:
    get_session_or_404(session_id, client_token, db)
    messages = db.exec(
        select(Message).where(Message.session_id == session_id).order_by(col(Message.created_at).asc())
    ).all()

    items: list[MessageHistoryItem] = []
    for m in messages:
        citations_db = db.exec(
            select(MessageCitation).where(MessageCitation.message_id == m.id)
        ).all()
        cit_items = [
            CitationItem(
                source_tag=c.source_tag,
                document_id="doc",
                filename="document.pdf",
                page_number=1,
                similarity=c.similarity,
                snippet=c.snippet,
            )
            for c in citations_db
        ]
        items.append(
            MessageHistoryItem(
                id=m.id,
                role=m.role,
                content=m.content,
                refused=m.refused,
                latency_ms=m.latency_ms,
                created_at=m.created_at,
                citations=cit_items,
            )
        )

    return MessageHistoryResponse(messages=items)

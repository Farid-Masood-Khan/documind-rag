"""Relational data models (SQLModel) and API schemas for DocuMind."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


# ==============================================================================
# SQLModel Relational Database Tables
# ==============================================================================


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    owner_token: str = SQLField(
        index=True, description="Client token for browser session isolation"
    )
    name: str = SQLField(default="Untitled session")
    chunk_count: int = SQLField(default=0)
    status: str = SQLField(default="active")  # active | indexing | error
    created_at: datetime.datetime = SQLField(default_factory=utc_now)
    updated_at: datetime.datetime = SQLField(default_factory=utc_now)


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = SQLField(foreign_key="sessions.id", index=True)
    original_filename: str = SQLField(description="User filename for display only")
    stored_filename: str = SQLField(description="Safe generated filename on disk")
    file_sha256: str = SQLField(index=True)
    size_bytes: int = SQLField(default=0)
    page_count: int = SQLField(default=0)
    chunk_count: int = SQLField(default=0)
    status: str = SQLField(
        default="uploaded"
    )  # uploaded | extracting | chunking | embedding | indexed | failed
    error_message: str | None = SQLField(default=None)
    created_at: datetime.datetime = SQLField(default_factory=utc_now)


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"

    id: str = SQLField(primary_key=True)  # document_id:chunk_index
    document_id: str = SQLField(foreign_key="documents.id", index=True)
    session_id: str = SQLField(foreign_key="sessions.id", index=True)
    chunk_index: int = SQLField()
    page_number: int = SQLField()
    text: str = SQLField()
    char_start: int = SQLField()
    char_end: int = SQLField()
    vector_row: int = SQLField()
    token_estimate: int = SQLField(default=0)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = SQLField(foreign_key="sessions.id", index=True)
    role: str = SQLField()  # user | assistant
    content: str = SQLField()
    refused: bool = SQLField(default=False)
    latency_ms: int | None = SQLField(default=None)
    created_at: datetime.datetime = SQLField(default_factory=utc_now)


class MessageCitation(SQLModel, table=True):
    __tablename__ = "message_citations"

    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    message_id: str = SQLField(foreign_key="messages.id", index=True)
    chunk_id: str = SQLField(foreign_key="chunks.id")
    source_tag: str = SQLField()  # S1, S2, ...
    similarity: float = SQLField()
    snippet: str = SQLField()


class IndexMeta(SQLModel, table=True):
    __tablename__ = "index_meta"

    session_id: str = SQLField(primary_key=True)
    embed_model: str = SQLField()
    embed_dim: int = SQLField()
    chunk_size: int = SQLField()
    chunk_overlap: int = SQLField()
    built_at: datetime.datetime = SQLField(default_factory=utc_now)
    prompt_version: str = SQLField(default="grounded-v3")


# ==============================================================================
# Pydantic Schemas for API Requests & Responses
# ==============================================================================


class CreateSessionRequest(BaseModel):
    name: str = Field(default="Untitled session", max_length=120)


class SessionResponse(BaseModel):
    id: str
    name: str
    chunk_count: int
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class DocumentUploadResultItem(BaseModel):
    document_id: str | None
    original_filename: str
    status: str  # indexed | failed
    page_count: int = 0
    chunk_count: int = 0
    error: dict[str, str] | None = None


class DocumentUploadResponse(BaseModel):
    results: list[DocumentUploadResultItem]


class DocumentItemResponse(BaseModel):
    id: str
    session_id: str
    original_filename: str
    file_sha256: str
    size_bytes: int
    page_count: int
    chunk_count: int
    status: str
    error_message: str | None
    created_at: datetime.datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentItemResponse]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class CitationItem(BaseModel):
    source_tag: str
    document_id: str
    filename: str
    page_number: int
    similarity: float
    snippet: str


class AskResponse(BaseModel):
    message_id: str
    refused: bool
    answer: str | None
    citations: list[CitationItem] = []
    reason: str | None = None
    searched_documents: list[str] = []
    latency_ms: int


class MessageHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    refused: bool
    latency_ms: int | None
    created_at: datetime.datetime
    citations: list[CitationItem] = []


class MessageHistoryResponse(BaseModel):
    messages: list[MessageHistoryItem]


class HealthResponse(BaseModel):
    status: str
    embed_model: str
    llm_backend: str
    llm_model: str

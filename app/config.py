"""Configuration settings for DocuMind RAG application."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or defaults."""

    # Models & RAG parameters
    embed_model: str = "all-MiniLM-L6-v2"
    embed_dim: int = 384
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 5
    sim_threshold: float = 0.30
    prompt_version: str = "grounded-v3"

    # LLM Service
    # 'mock' (offline deterministic for testing/CI), 'ollama', or 'openai'
    llm_backend: str = "mock"
    llm_model: str = "llama3:8b"
    llm_api_base: str = "http://localhost:11434/v1"
    llm_api_key: str = ""

    # Paths & Storage
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = Path(__file__).resolve().parent.parent / "data" / "sessions"
    database_url: str = f"sqlite:///{Path(__file__).resolve().parent.parent / 'documind.db'}"

    # Server Limits
    max_file_size_bytes: int = 25 * 1024 * 1024  # 25 MB
    max_pages_per_doc: int = 500
    max_question_length: int = 2000

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

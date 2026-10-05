from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "BRAC University Information Chatbot"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Database settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/bracu_rag"

    # Groq LLM API
    GROQ_API_KEY: str = ""
    GROQ_ANSWER_MODEL: str = "openai/gpt-oss-120b"
    GROQ_REWRITE_MODEL: str = "openai/gpt-oss-20b"
    GROQ_REASONING_EFFORT: Literal["none", "default", "low", "medium", "high"] = "medium"
    GROQ_MAX_COMPLETION_TOKENS: int = 1200

    # AI Models (Local & Hugging Face)
    HF_TOKEN: str = ""
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # RAG Retrieval Parameters
    RETRIEVAL_TOP_K: int = 10
    RETRIEVAL_DOCUMENT_LIMIT: int = 3
    RERANK_TOP_N: int = 5
    SIMILARITY_THRESHOLD: float = 0.5
    RETRIEVAL_FAISS_WEIGHT: float = 0.25
    RETRIEVAL_TEXT_WEIGHT: float = 1.0
    CHAT_HISTORY_TURNS: int = 6
    KB_SOURCE_DIR: str = ""

    # Security & Auth
    JWT_SECRET: str = "insecure_dev_secret_key_change_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7

    # CORS origins
    CORS_ORIGINS: list[str] | str = ["http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

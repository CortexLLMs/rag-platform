"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings class. Reads from .env file and environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "RAG Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ── OpenAI ───────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""

    # ── Supabase ─────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ── Qdrant ───────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    @property
    def supabase_initialized(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()

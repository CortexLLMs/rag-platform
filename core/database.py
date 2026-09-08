"""Database and vector store client initialization."""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from supabase import Client, create_client

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None
_qdrant_client: Optional[QdrantClient] = None


def init_supabase(settings: Settings | None = None) -> Client:
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    settings = settings or get_settings()
    if not settings.supabase_initialized:
        raise ValueError("Supabase credentials missing.")
    try:
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        logger.info("Supabase client initialized successfully.")
    except Exception as exc:
        logger.error("Failed to initialize Supabase client: %s", exc)
        raise
    return _supabase_client


def init_qdrant(settings: Settings | None = None) -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    settings = settings or get_settings()
    if not settings.QDRANT_URL:
        raise ValueError("QDRANT_URL is required.")
    try:
        _qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
        logger.info("Qdrant client initialized at %s.", settings.QDRANT_URL)
    except Exception as exc:
        logger.error("Failed to initialize Qdrant client: %s", exc)
        raise
    return _qdrant_client


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        return init_supabase()
    return _supabase_client


def get_qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        return init_qdrant()
    return _qdrant_client


def healthcheck() -> dict[str, bool]:
    results: dict[str, bool] = {}

    try:
        client = get_qdrant()
        client.get_collections()
        results["qdrant"] = True
    except Exception:
        results["qdrant"] = False

    try:
        client = get_supabase()
        client.table("chat_history").select("*").limit(1).execute()
        results["supabase"] = True
    except Exception:
        results["supabase"] = False

    return results

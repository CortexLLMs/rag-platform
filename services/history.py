"""Chat history persistence via Supabase PostgreSQL."""

import logging
from datetime import datetime, timezone

from core.database import get_supabase

logger = logging.getLogger(__name__)


def log_message(
    chatbot_id: str,
    session_id: str,
    role: str,
    content: str,
) -> dict | None:
    """Insert a single message into the chat_history table.

    Args:
        chatbot_id: Identifier for the chatbot instance.
        session_id: Groups messages into a conversation.
        role: Either ``"user"`` or ``"assistant"``.
        content: Message text.

    Returns:
        The inserted row dict, or ``None`` on failure.
    """
    try:
        client = get_supabase()
        result = (
            client.table("chat_history")
            .insert(
                {
                    "chatbot_id": chatbot_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                }
            )
            .execute()
        )
        logger.debug("Logged %s message for session %s", role, session_id)
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.warning("Failed to log chat message: %s", exc)
        return None


def get_history(
    chatbot_id: str,
    session_id: str,
    limit: int = 20,
) -> list[dict]:
    """Fetch recent messages for a session, ordered oldest-first.

    Returns:
        List of dicts with ``role``, ``content``, and ``created_at`` keys.
    """
    try:
        client = get_supabase()
        result = (
            client.table("chat_history")
            .select("role, content, created_at")
            .eq("chatbot_id", chatbot_id)
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning("Failed to fetch chat history: %s", exc)
        return []


def format_history_for_prompt(history: list[dict]) -> str:
    """Format chat history rows into a string for prompt injection.

    Returns:
        Multi-line string like::

            user: What is RAG?
            assistant: RAG stands for Retrieval-Augmented Generation...
    """
    lines: list[str] = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

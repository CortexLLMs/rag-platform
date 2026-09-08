"""Pydantic schemas for request / response validation."""

from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for the /health endpoint response."""

    status: str
    version: str
    dependencies: dict[str, bool]


# ── RAG Schemas ──────────────────────────────────────────────────


class IngestRequest(BaseModel):
    """Payload for document ingestion."""

    text: str = Field(..., min_length=1, description="Raw text content to ingest.")
    metadata: dict = Field(
        default_factory=dict,
        description="Optional metadata attached to each chunk (chatbot_id, source, etc.).",
    )


class IngestResponse(BaseModel):
    """Response after successful ingestion."""

    status: str = "ok"
    chunks_stored: int = Field(..., description="Number of chunks created and stored.")


class ChatRequest(BaseModel):
    """Payload for a RAG chat query."""

    query: str = Field(..., min_length=1, description="User question.")
    chatbot_id: str = Field(
        ..., min_length=1, description="Isolates retrieval scope per tenant / chatbot."
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Conversation session ID. Generated server-side if omitted.",
    )


class ChatResponse(BaseModel):
    """Response containing the generated answer and source documents."""

    answer: str
    session_id: str = Field(..., description="Conversation session ID.")
    source_documents: list[dict] = Field(
        default_factory=list,
        description="Metadata of the chunks used as context.",
    )

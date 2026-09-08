"""API route definitions for the RAG platform."""

import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import (
    ChatRequest,
    ChatResponse,
    IngestRequest,
    IngestResponse,
)
from services.history import log_message
from services.rag import generate_answer, ingest_document, stream_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    """Basic liveness probe."""
    return {"message": "pong"}


# ── Ingestion ────────────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResponse, tags=["rag"])
async def ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document into the vector store."""
    try:
        chunks = ingest_document(text=req.text, metadata=req.metadata)
    except Exception as exc:
        logger.exception("Ingestion failed")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    return IngestResponse(chunks_stored=chunks)


# ── Chat (non-streaming fallback) ──────────────────────────────


@router.post("/chat", response_model=ChatResponse, tags=["rag"])
async def chat(req: ChatRequest) -> ChatResponse:
    """Answer a user question using RAG (non-streaming)."""
    session_id = req.session_id or str(uuid.uuid4())

    log_message(
        chatbot_id=req.chatbot_id,
        session_id=session_id,
        role="user",
        content=req.query,
    )

    try:
        result = generate_answer(query=req.query, chatbot_id=req.chatbot_id)
    except Exception as exc:
        logger.exception("Chat generation failed")
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc

    log_message(
        chatbot_id=req.chatbot_id,
        session_id=session_id,
        role="assistant",
        content=result["answer"],
    )

    return ChatResponse(
        answer=result["answer"],
        session_id=session_id,
        source_documents=result["source_documents"],
    )


# ── Chat (SSE streaming) ───────────────────────────────────────


@router.post("/chat/stream", tags=["rag"])
async def chat_stream(req: ChatRequest, background_tasks: BackgroundTasks) -> StreamingResponse:
    """Stream an answer token-by-token via Server-Sent Events.

    The response format is::

        data: "token"
        data: " token"
        ...
        data: [DONE]

    After the stream completes, the full assistant response is logged to
    Supabase via a background task so the user is not blocked.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # Log user message immediately
    log_message(
        chatbot_id=req.chatbot_id,
        session_id=session_id,
        role="user",
        content=req.query,
    )

    async def _stream_with_logging() -> AsyncGenerator[str, None]:
        """Accumulate tokens, yield SSE lines, then log the full answer."""
        full_answer_parts: list[str] = []

        try:
            async for sse_chunk in stream_answer(
                query=req.query,
                chatbot_id=req.chatbot_id,
                session_id=session_id,
            ):
                # Parse the data payload to accumulate the answer text
                if sse_chunk.startswith("data: ") and not sse_chunk.startswith("data: [DONE]"):
                    try:
                        payload = json.loads(sse_chunk[6:].strip("\n"))
                        if isinstance(payload, str):
                            full_answer_parts.append(payload)
                        elif isinstance(payload, dict) and "error" in payload:
                            # Error sentinel — still forward to client
                            pass
                    except json.JSONDecodeError:
                        pass

                yield sse_chunk
        except Exception as exc:
            logger.exception("Streaming generator failed")
            error_msg = json.dumps({"error": str(exc)})
            yield f"data: {error_msg}\n\n"
            yield "data: [DONE]\n\n"

        # Log the complete assistant answer in the background
        full_answer = "".join(full_answer_parts)
        if full_answer:
            background_tasks.add_task(
                log_message,
                chatbot_id=req.chatbot_id,
                session_id=session_id,
                role="assistant",
                content=full_answer,
            )

    async def _stream_with_session() -> AsyncGenerator[str, None]:
        # Force Caddy to flush headers and establish the SSE connection instantly.
        # Without this, Caddy may buffer until the first real payload arrives,
        # causing a visible delay before the typing indicator disappears.
        yield "data:  \n\n"

        # Session metadata so the client can capture the session_id
        meta = json.dumps({"session_id": session_id})
        yield f"data: {meta}\n\n"

        async for chunk in _stream_with_logging():
            yield chunk

    return StreamingResponse(
        _stream_with_session(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

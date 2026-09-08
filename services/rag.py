"""RAG pipeline – Qdrant retrieval + OpenAI streaming generation."""

import json
import logging
from typing import Any, AsyncGenerator

from openai import OpenAI
from qdrant_client import models as qm

from core.config import get_settings
from core.database import get_qdrant
from services.history import format_history_for_prompt, get_history

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
LLM_MODEL = "gpt-4o-mini"
COLLECTION_PREFIX = "chatbot_"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
TOP_K = 5


# ── Embeddings ───────────────────────────────────────────────────


def _get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_text(text: str) -> list[float]:
    client = _get_openai_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = _get_openai_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


# ── Collection helpers ──────────────────────────────────────────


def _collection_name(chatbot_id: str) -> str:
    return f"{COLLECTION_PREFIX}{chatbot_id}"


def _ensure_collection(collection_name: str) -> None:
    """Create the Qdrant collection if it doesn't exist."""
    client = get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qm.VectorParams(
                size=EMBEDDING_DIMS,
                distance=qm.Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: %s", collection_name)


# ── Chunking ─────────────────────────────────────────────────────


def _split_text(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── Ingestion ────────────────────────────────────────────────────


def ingest_document(text: str, metadata: dict[str, Any] | None = None) -> int:
    """Chunk text, embed, and upsert into Qdrant scoped by chatbot_id."""
    metadata = metadata or {}
    chatbot_id = metadata.get("chatbot_id", "default")
    collection_name = _collection_name(chatbot_id)
    _ensure_collection(collection_name)

    chunks = _split_text(text)
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)

    points = []
    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            qm.PointStruct(
                id=i,
                vector=embedding,
                payload={
                    "content": chunk_text,
                    "metadata": {**metadata, "chatbot_id": chatbot_id},
                },
            )
        )

    client = get_qdrant()
    client.upsert(collection_name=collection_name, points=points)
    logger.info("Ingested %d chunks into Qdrant collection '%s'.", len(points), collection_name)
    return len(points)


# ── Retrieval ────────────────────────────────────────────────────


def retrieve_chunks(query: str, chatbot_id: str, k: int = TOP_K) -> list[dict]:
    """Embed the query and search Qdrant for top-k similar chunks."""
    collection_name = _collection_name(chatbot_id)
    query_embedding = embed_text(query)

    client = get_qdrant()
    results = client.query_points(
        collection_name=collection_name,
        query=query_embedding,
        limit=k,
        query_filter=qm.Filter(
            must=[
                qm.FieldCondition(
                    key="metadata.chatbot_id",
                    match=qm.MatchValue(value=chatbot_id),
                )
            ]
        ),
    )

    chunks = []
    for point in results.points:
        chunks.append({
            "content": point.payload.get("content", ""),
            "metadata": point.payload.get("metadata", {}),
            "similarity": point.score,
        })
    return chunks


# ── Prompt builder (shared by sync + stream) ────────────────────


def _build_messages(
    query: str,
    chatbot_id: str,
    session_id: str | None = None,
) -> tuple[str, list[dict]]:
    """Retrieve context, fetch history, and return the messages list.

    Returns:
        Tuple of (context_text, messages) where messages is the OpenAI-format list.
    """
    chunks = retrieve_chunks(query, chatbot_id, k=TOP_K)
    context_text = "\n\n---\n\n".join(c.get("content", "") for c in chunks)

    history_text = ""
    if session_id:
        history = get_history(chatbot_id, session_id, limit=10)
        history_text = format_history_for_prompt(history)

    system_message = (
        "You are a helpful assistant for the chatbot. "
        "Answer the user's question using ONLY the provided context. "
        "If the answer is not in the context, say you don't have enough information. "
        "Be concise and conversational."
    )

    human_parts: list[str] = []
    if history_text:
        human_parts.append(f"Recent conversation:\n{history_text}\n")
    human_parts.append(f"Context:\n{context_text}\n")
    human_parts.append(f"Question: {query}")
    human_message = "\n\n".join(human_parts)

    return context_text, [
        {"role": "system", "content": system_message},
        {"role": "user", "content": human_message},
    ]


# ── Non-streaming generation (kept for backward compat) ─────────


def generate_answer(
    query: str,
    chatbot_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve context, build prompt with chat history, and generate answer."""
    context_text, messages = _build_messages(query, chatbot_id, session_id)

    client = _get_openai_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        messages=messages,
    )

    answer = response.choices[0].message.content or ""

    chunks = retrieve_chunks(query, chatbot_id, k=TOP_K)
    source_documents = [
        {
            "content": c.get("content", "")[:500],
            "metadata": c.get("metadata", {}),
            "similarity": c.get("similarity", 0),
        }
        for c in chunks
    ]

    return {"answer": answer, "source_documents": source_documents}


# ── Streaming generation ────────────────────────────────────────


async def stream_answer(
    query: str,
    chatbot_id: str,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream the answer token-by-token as SSE ``data:`` lines.

    Yields:
        SSE-formatted strings: ``data: {token}\\n\\n``
        Final sentinel:       ``data: [DONE]\\n\\n``
    """
    context_text, messages = _build_messages(query, chatbot_id, session_id)

    client = _get_openai_client()

    # OpenAI streaming — runs in a thread since the SDK is sync
    import asyncio

    def _sync_stream():
        return client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0,
            messages=messages,
            stream=True,
        )

    stream = await asyncio.to_thread(_sync_stream)

    try:
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {json.dumps(delta.content)}\n\n"
    except Exception as exc:
        logger.exception("Streaming failed")
        error_payload = json.dumps({"error": str(exc)})
        yield f"data: {error_payload}\n\n"
    finally:
        yield "data: [DONE]\n\n"

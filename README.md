# RAG Platform & Embeddable Chatbot

A production-ready **Retrieval-Augmented Generation** platform with real-time token streaming, multi-tenant isolation, and a zero-dependency embeddable chat widget.

Built with **FastAPI**, **Qdrant** (vectors), **Supabase** (chat history), and **OpenAI** — fully containerized with Docker Compose and deployable to any VPS with one command.

---

## Features

- **RAG Pipeline** — Chunk, embed, retrieve, and generate with source attribution
- **Token-by-Token Streaming** — Server-Sent Events (SSE) for real-time response delivery
- **Multi-Tenant Isolation** — Each `chatbot_id` gets its own Qdrant collection
- **Session-Persistent Conversations** — Chat history stored in Supabase PostgreSQL
- **Embeddable Widget** — Vanilla JS, zero dependencies, Shadow DOM isolated, drop-in on any website
- **Production Ready** — Caddy reverse proxy, auto-SSL, no exposed internal ports
- **One-Command Deploy** — `./deploy.sh` handles build, restart, and cleanup

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Internet                         │
└──────────────────┬──────────────────────────────────┘
                   │ :80 / :443
          ┌────────▼────────┐
          │   Caddy (SSL)   │   Auto Let's Encrypt
          │  reverse_proxy  │   SSE flush passthrough
          └────────┬────────┘
                   │ Docker network
          ┌────────▼────────┐
          │    FastAPI       │   /api/v1/chat/stream (SSE)
          │    (uvicorn)     │   /api/v1/ingest
          └───┬─────────┬───┘
              │         │
   ┌──────────▼──┐  ┌──▼──────────┐
   │   Qdrant    │  │  Supabase   │
   │  (vectors)  │  │  (history)  │
   │  internal   │  │  external   │
   └─────────────┘  └─────────────┘
```

---

## Project Structure

```
rag-platform/
├── api/
│   └── routes.py          # FastAPI endpoints (/chat, /chat/stream, /ingest)
├── core/
│   ├── config.py           # Pydantic settings from .env
│   └── database.py         # Qdrant + Supabase client singletons
├── models/
│   └── schemas.py          # Pydantic request/response schemas
├── services/
│   ├── rag.py              # Embedding, retrieval, generation, streaming
│   └── history.py          # Chat history persistence
├── public/
│   ├── widget.js           # Embeddable chat widget (Shadow DOM)
│   └── widget.css          # Widget styles
├── scripts/
│   └── run_migration.py    # Supabase table migration helper
├── main.py                 # FastAPI app entry point
├── Dockerfile              # Multi-stage Python 3.10 build
├── docker-compose.yml      # Development (API + Qdrant)
├── docker-compose.prod.yml # Production (+ Caddy, no exposed ports)
├── Caddyfile               # Reverse proxy + SSL config
├── deploy.sh               # One-command production deploy
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── README.md
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An [OpenAI API key](https://platform.openai.com/api-keys)
- A [Supabase](https://supabase.com) project (free tier works)

### 1. Clone & Configure

```bash
git clone https://github.com/YOUR_USERNAME/rag-platform.git
cd rag-platform
cp .env.example .env
```

Edit `.env` with your keys:

```env
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJ...
```

### 2. Run (Development)

```bash
docker compose up -d --build
```

- API: `http://localhost:8000`
- Qdrant Dashboard: `http://localhost:6333/dashboard`
- Health: `http://localhost:8000/health`

### 3. Run (Production)

```bash
# Edit .env with your domain
DOMAIN_NAME=api.yourdomain.com

# Deploy
chmod +x deploy.sh
./deploy.sh
```

Caddy auto-provisions SSL via Let's Encrypt on first start.

---

## API Reference

### Ingest Documents

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your document text here...",
    "metadata": {"chatbot_id": "my-bot"}
  }'
```

**Response:**
```json
{"status": "ok", "chunks_stored": 5}
```

### Chat (Non-Streaming)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is this platform?",
    "chatbot_id": "my-bot",
    "session_id": "optional-session-id"
  }'
```

### Chat (SSE Streaming)

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Explain RAG",
    "chatbot_id": "my-bot"
  }'
```

**Stream format:**
```
data: {"session_id": "abc-123"}

data: "RAG"
data: " stands"
data: " for"
data: " Retrieval-Augmented"
data: " Generation"
...
data: [DONE]
```

### Embed the Widget

Add to any HTML page:

```html
<script
  src="https://api.yourdomain.com/public/widget.js"
  data-chatbot-id="my-bot"
  data-api-url="https://api.yourdomain.com">
</script>
```

---

## Embedding the Widget

The chat widget is a single `<script>` tag with zero dependencies. It uses Shadow DOM for style isolation.

```html
<!DOCTYPE html>
<html>
<head><title>My Site</title></head>
<body>
  <h1>Welcome</h1>

  <script
    src="https://YOUR_API_URL/public/widget.js"
    data-chatbot-id="your-bot-id"
    data-api-url="https://YOUR_API_URL">
  </script>
</body>
</html>
```

The widget:
- Auto-creates a floating chat bubble (bottom-right)
- Persists session ID in `localStorage`
- Streams responses token-by-token
- Handles network errors gracefully
- Works in any modern browser

---

## Multi-Tenant Isolation

Each `chatbot_id` gets:
- Its own Qdrant collection (`chatbot_{id}`)
- Scoped vector retrieval (search only returns own chunks)
- Independent chat history sessions

```bash
# Ingest for bot A
curl -X POST /api/v1/ingest -d '{"text": "...", "metadata": {"chatbot_id": "bot-a"}}'

# Ingest for bot B
curl -X POST /api/v1/ingest -d '{"text": "...", "metadata": {"chatbot_id": "bot-b"}}'

# Bot A can only retrieve Bot A's documents
curl -X POST /api/v1/chat -d '{"query": "...", "chatbot_id": "bot-a"}'
```

---

## Local Development (Without Docker)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Qdrant locally
docker run -d -p 6333:6333 qdrant/qdrant

# Configure .env
QDRANT_URL=http://localhost:6333

# Run API
uvicorn main:app --reload
```

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI + Uvicorn | Async API server |
| Vector DB | Qdrant | Similarity search, multi-tenant collections |
| Chat History | Supabase (PostgreSQL) | Conversation persistence |
| Embeddings | OpenAI `text-embedding-3-small` | 1536-dim vectors |
| LLM | OpenAI `gpt-4o-mini` | Answer generation |
| Reverse Proxy | Caddy | SSL termination, SSE passthrough |
| Widget | Vanilla JS (Shadow DOM) | Embeddable chat UI |
| Container | Docker Compose | Orchestration |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon/service key |
| `QDRANT_URL` | No | Qdrant URL (default: `http://localhost:6333`) |
| `QDRANT_API_KEY` | No | Qdrant API key (if auth enabled) |
| `DOMAIN_NAME` | Prod only | Domain for Caddy SSL |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

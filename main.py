"""RAG Platform – FastAPI entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from core.config import get_settings
from core.database import healthcheck, init_qdrant, init_supabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    if settings.supabase_initialized:
        try:
            init_supabase(settings)
        except Exception as exc:
            logger.warning("Supabase init failed: %s", exc)

    if settings.QDRANT_URL:
        try:
            init_qdrant(settings)
        except Exception as exc:
            logger.warning("Qdrant init failed: %s", exc)

    yield
    logger.info("Shutting down %s.", settings.APP_NAME)


app = FastAPI(
    title=get_settings().APP_NAME,
    version=get_settings().APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

_public = Path(__file__).parent / "public"
_public.mkdir(exist_ok=True)
app.mount("/public", StaticFiles(directory=str(_public)), name="public")


@app.get("/health", tags=["ops"])
async def health() -> JSONResponse:
    status = healthcheck()
    overall = all(status.values())
    return JSONResponse(
        content={
            "status": "healthy" if overall else "degraded",
            "version": get_settings().APP_VERSION,
            "dependencies": status,
        },
        status_code=200 if overall else 503,
    )

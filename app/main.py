"""FastAPI application entry point for Ground Fire Enhancement System.

Full-featured — CORS, static files (Leaflet frontend), SQLite database.
"""
from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.data.cache import cleanup_old_enhancements, init_caches, init_db

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def _cleanup_history_loop() -> None:
    """Periodically enforce the configured history retention window."""
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            await cleanup_old_enhancements()
        except Exception:
            logger.warning("Scheduled history cleanup failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Starting Ground Fire Enhancement System...")
    await init_db()
    init_caches()
    cleanup_task = asyncio.create_task(_cleanup_history_loop())
    logger.info("System ready.")
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        logger.info("Shutting down Ground Fire Enhancement System.")


app = FastAPI(
    title="地面火点增强验证系统",
    description="接收星上验证结果，集成网络数据进行增强验证和置信度修正",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]

# CORS middleware. Configure GROUND_CORS_ORIGINS for non-local deployments.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Include API router
app.include_router(router)

# Mount static files (Leaflet frontend)
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to the map UI."""
    return RedirectResponse(url="/static/map.html")

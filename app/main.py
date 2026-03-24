"""FastAPI application entry point for Ground Fire Enhancement System.

Full-featured — CORS, static files (Leaflet frontend), SQLite database.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.data.cache import init_caches, init_db

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Starting Ground Fire Enhancement System...")
    await init_db()
    init_caches()
    logger.info("System ready.")
    yield
    logger.info("Shutting down Ground Fire Enhancement System.")


app = FastAPI(
    title="地面火点增强验证系统",
    description="接收星上验证结果，集成网络数据进行增强验证和置信度修正",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware (allow all for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

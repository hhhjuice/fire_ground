"""Database and caching layer for ground fire enhancement results.

Uses:
- aiosqlite for async SQLite operations (persist enhancement results)
- In-memory TTL+LRU cache for expensive lookups (FIRMS)
"""
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple thread-safe TTL + LRU cache using OrderedDict."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """Get value by key. Returns None if missing or expired."""
        if key not in self._cache:
            return None
        ts, value = self._cache[key]
        if time.time() - ts > self._ttl:
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        """Set value with current timestamp. Evicts oldest if full."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# Global cache instances
firms_cache = TTLCache()


def init_caches() -> None:
    """Initialize cache instances with settings values."""
    settings = get_settings()
    global firms_cache
    firms_cache = TTLCache(
        max_size=settings.cache_max_size,
        ttl_seconds=settings.cache_ttl_seconds,
    )


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS enhancement_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    satellite_verdict TEXT NOT NULL,
    satellite_confidence REAL NOT NULL,
    ground_verdict TEXT NOT NULL,
    ground_confidence REAL NOT NULL,
    summary TEXT,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_enhancement_coords
ON enhancement_results(latitude, longitude);
"""


async def init_db() -> None:
    """Initialize SQLite database and create tables if needed."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.execute(_CREATE_INDEX_SQL)
        await db.commit()
    logger.info("Database initialized at %s", settings.db_path)


async def save_enhancement_result(
    latitude: float,
    longitude: float,
    satellite_verdict: str,
    satellite_confidence: float,
    ground_verdict: str,
    ground_confidence: float,
    summary: str,
    result_json: str,
) -> int:
    """Save an enhancement result to the database. Returns the row ID."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute(
            """INSERT INTO enhancement_results
               (latitude, longitude, satellite_verdict, satellite_confidence,
                ground_verdict, ground_confidence, summary, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (latitude, longitude, satellite_verdict, satellite_confidence,
             ground_verdict, ground_confidence, summary, result_json),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def get_recent_enhancements(limit: int = 50) -> list[dict]:
    """Get most recent enhancement results."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM enhancement_results ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_nearby_enhancements(
    lat: float,
    lon: float,
    radius_deg: float = 0.05,
) -> list[dict]:
    """Get previous enhancement results near a coordinate."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM enhancement_results
               WHERE latitude BETWEEN ? AND ?
               AND longitude BETWEEN ? AND ?
               ORDER BY created_at DESC LIMIT 20""",
            (lat - radius_deg, lat + radius_deg, lon - radius_deg, lon + radius_deg),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

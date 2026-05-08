"""Database and caching layer for ground fire enhancement results.

Uses:
- aiosqlite for async SQLite operations (persist enhancement results)
- In-memory TTL+LRU utility for lightweight process-local caches
"""
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple single-process TTL + LRU cache using OrderedDict."""

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


# Global cache instances retained for lightweight process-local reuse.
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
    lat_grid REAL NOT NULL,
    lon_grid REAL NOT NULL,
    satellite_verdict TEXT NOT NULL,
    satellite_confidence REAL NOT NULL,
    ground_verdict TEXT NOT NULL,
    ground_confidence REAL NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_enhancement_coords
ON enhancement_results(lat_grid, lon_grid);
"""

_CREATE_CREATED_AT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_enhancement_created_at
ON enhancement_results(created_at);
"""

_HISTORY_COLUMNS = """
id, lat_grid, lon_grid, satellite_verdict, satellite_confidence,
ground_verdict, ground_confidence, summary, created_at
"""


def _ensure_db_parent(db_path: str) -> None:
    parent = Path(db_path).expanduser().parent
    parent.mkdir(parents=True, exist_ok=True)


def _grid_coord(value: float) -> float:
    settings = get_settings()
    precision = settings.history_coord_precision_deg
    return round(round(value / precision) * precision, 4)


async def _prepare_connection(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA busy_timeout=5000")


async def _migrate_sensitive_history(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(enhancement_results)")
    columns = {row[1] for row in await cursor.fetchall()}
    if not columns:
        return
    if {"latitude", "longitude", "result_json"} & columns:
        logger.warning("Dropping legacy history table containing sensitive fields")
        await db.execute("DROP TABLE IF EXISTS enhancement_results")


async def cleanup_old_enhancements() -> None:
    """Delete history records older than the configured retention window."""
    settings = get_settings()
    _ensure_db_parent(settings.db_path)
    async with aiosqlite.connect(settings.db_path, timeout=5.0) as db:
        await _prepare_connection(db)
        await db.execute(
            "DELETE FROM enhancement_results WHERE created_at < datetime('now', ?)",
            (f"-{settings.history_retention_days} days",),
        )
        await db.commit()


async def check_db_health() -> bool:
    """Return True when SQLite is reachable and writable."""
    settings = get_settings()
    try:
        _ensure_db_parent(settings.db_path)
        async with aiosqlite.connect(settings.db_path, timeout=5.0) as db:
            await _prepare_connection(db)
            await db.execute("SELECT 1")
            await db.execute("CREATE TEMP TABLE IF NOT EXISTS health_probe (id INTEGER)")
            await db.execute("INSERT INTO health_probe (id) VALUES (1)")
            await db.execute("DELETE FROM health_probe")
            await db.commit()
        return True
    except Exception as exc:
        logger.warning("SQLite health check failed: %s", exc, exc_info=True)
        return False


async def init_db() -> None:
    """Initialize SQLite database and create tables if needed."""
    settings = get_settings()
    _ensure_db_parent(settings.db_path)
    async with aiosqlite.connect(settings.db_path, timeout=5.0) as db:
        await _prepare_connection(db)
        await db.execute("PRAGMA journal_mode=WAL")
        await _migrate_sensitive_history(db)
        await db.execute(_CREATE_TABLE_SQL)
        await db.execute(_CREATE_INDEX_SQL)
        await db.execute(_CREATE_CREATED_AT_INDEX_SQL)
        await db.commit()
    await cleanup_old_enhancements()
    logger.info("Database initialized at %s", settings.db_path)


async def save_enhancement_result(
    latitude: float,
    longitude: float,
    satellite_verdict: str,
    satellite_confidence: float,
    ground_verdict: str,
    ground_confidence: float,
    summary: str,
) -> int:
    """Save an enhancement result to the database. Returns the row ID."""
    settings = get_settings()
    _ensure_db_parent(settings.db_path)
    lat_grid = _grid_coord(latitude)
    lon_grid = _grid_coord(longitude)
    async with aiosqlite.connect(settings.db_path, timeout=5.0) as db:
        await _prepare_connection(db)
        cursor = await db.execute(
            """INSERT INTO enhancement_results
               (lat_grid, lon_grid, satellite_verdict, satellite_confidence,
                ground_verdict, ground_confidence, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lat_grid, lon_grid, satellite_verdict, satellite_confidence,
             ground_verdict, ground_confidence, summary),
        )
        await db.commit()
        await db.execute(
            "DELETE FROM enhancement_results WHERE created_at < datetime('now', ?)",
            (f"-{settings.history_retention_days} days",),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def get_recent_enhancements(limit: int = 50) -> list[dict]:
    """Get most recent enhancement results."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path, timeout=5.0) as db:
        await _prepare_connection(db)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {_HISTORY_COLUMNS} FROM enhancement_results ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_nearby_enhancements(
    lat: float,
    lon: float,
    radius_deg: float = 0.05,
    limit: int = 20,
) -> list[dict]:
    """Get previous enhancement results near a coordinate."""
    settings = get_settings()
    lat_grid = _grid_coord(lat)
    lon_grid = _grid_coord(lon)
    async with aiosqlite.connect(settings.db_path, timeout=5.0) as db:
        await _prepare_connection(db)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""SELECT {_HISTORY_COLUMNS} FROM enhancement_results
               WHERE lat_grid BETWEEN ? AND ?
               AND lon_grid BETWEEN ? AND ?
               ORDER BY created_at DESC LIMIT ?""",
            (
                lat_grid - radius_deg,
                lat_grid + radius_deg,
                lon_grid - radius_deg,
                lon_grid + radius_deg,
                limit,
            ),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

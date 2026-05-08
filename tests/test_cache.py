"""Tests for ground cache (TTLCache)."""
import aiosqlite
import pytest

from app.config import get_settings
from app.data import cache as cache_module


def test_ttlcache_set_get_basic() -> None:
    cache = cache_module.TTLCache(max_size=10, ttl_seconds=60)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None


def test_ttlcache_lru_eviction() -> None:
    cache = cache_module.TTLCache(max_size=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_ttlcache_ttl_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    current = 1000.0

    def fake_time() -> float:
        return current

    monkeypatch.setattr(cache_module.time, "time", fake_time)

    cache = cache_module.TTLCache(max_size=2, ttl_seconds=5)
    cache.set("a", 1)
    assert cache.get("a") == 1

    current = 1006.0
    assert cache.get("a") is None


def test_ttlcache_access_moves_item_to_end() -> None:
    cache = cache_module.TTLCache(max_size=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)

    assert cache.get("a") == 1
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_ttlcache_clear() -> None:
    cache = cache_module.TTLCache(max_size=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)

    cache.clear()

    assert cache.size == 0
    assert cache.get("a") is None
    assert cache.get("b") is None


@pytest.mark.asyncio
async def test_ttlcache_works_in_async_context() -> None:
    cache = cache_module.TTLCache(max_size=2, ttl_seconds=60)
    cache.set("a", "value")
    assert cache.get("a") == "value"


@pytest.mark.asyncio
async def test_history_storage_uses_sanitized_grid(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GROUND_DB_PATH", str(tmp_path / "history.db"))
    get_settings.cache_clear()

    try:
        await cache_module.init_db()
        await cache_module.save_enhancement_result(
            latitude=28.54,
            longitude=116.36,
            satellite_verdict="UNCERTAIN",
            satellite_confidence=65.0,
            ground_verdict="TRUE_FIRE",
            ground_confidence=82.0,
            summary="脱敏摘要",
        )
        rows = await cache_module.get_recent_enhancements(limit=1)
    finally:
        get_settings.cache_clear()

    assert rows[0]["lat_grid"] == pytest.approx(28.5)
    assert rows[0]["lon_grid"] == pytest.approx(116.4)
    assert "latitude" not in rows[0]
    assert "longitude" not in rows[0]
    assert "result_json" not in rows[0]


@pytest.mark.asyncio
async def test_init_db_drops_legacy_sensitive_table(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE enhancement_results (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               latitude REAL,
               longitude REAL,
               result_json TEXT,
               created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
        await db.execute(
            "INSERT INTO enhancement_results (latitude, longitude, result_json) VALUES (1.0, 2.0, '{}')"
        )
        await db.commit()

    monkeypatch.setenv("GROUND_DB_PATH", str(db_path))
    get_settings.cache_clear()
    try:
        await cache_module.init_db()
        async with aiosqlite.connect(db_path) as db:
            columns_cursor = await db.execute("PRAGMA table_info(enhancement_results)")
            columns = {row[1] for row in await columns_cursor.fetchall()}
            count_cursor = await db.execute("SELECT COUNT(*) FROM enhancement_results")
            row_count = (await count_cursor.fetchone())[0]
    finally:
        get_settings.cache_clear()

    assert {"latitude", "longitude", "result_json"}.isdisjoint(columns)
    assert {"lat_grid", "lon_grid", "summary"}.issubset(columns)
    assert row_count == 0


@pytest.mark.asyncio
async def test_cleanup_removes_records_older_than_retention_days(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GROUND_DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("GROUND_HISTORY_RETENTION_DAYS", "15")
    get_settings.cache_clear()
    try:
        await cache_module.init_db()
        async with aiosqlite.connect(get_settings().db_path) as db:
            await db.execute(
                """INSERT INTO enhancement_results
                   (lat_grid, lon_grid, satellite_verdict, satellite_confidence,
                    ground_verdict, ground_confidence, summary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '-16 days'))""",
                (28.5, 116.4, "UNCERTAIN", 65.0, "TRUE_FIRE", 82.0, "old"),
            )
            await db.commit()

        await cache_module.cleanup_old_enhancements()
        rows = await cache_module.get_recent_enhancements(limit=10)
    finally:
        get_settings.cache_clear()

    assert rows == []


@pytest.mark.asyncio
async def test_check_db_health_false_when_parent_creation_fails(monkeypatch) -> None:
    def fail_parent(_db_path: str) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(cache_module, "_ensure_db_parent", fail_parent)

    assert await cache_module.check_db_health() is False

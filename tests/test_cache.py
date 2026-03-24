"""Tests for ground cache (TTLCache)."""
import pytest

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

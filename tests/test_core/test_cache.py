"""Tests for cache manager."""

import asyncio

import pytest

from context_bridge.cache import CacheManager


def test_cache_set_and_get() -> None:
    cache = CacheManager()
    cache.set("ns", "key", value="hello")
    assert cache.get("ns", "key") == "hello"


def test_cache_miss_raises() -> None:
    cache = CacheManager()
    with pytest.raises(KeyError):
        cache.get("missing", "key")


def test_invalidation() -> None:
    cache = CacheManager()
    cache.set("ns", "a", value=1)
    cache.set("ns", "b", value=2)
    cache.invalidate("ns", "a")
    with pytest.raises(KeyError):
        cache.get("ns", "a")
    assert cache.get("ns", "b") == 2


def test_namespace_invalidation() -> None:
    cache = CacheManager()
    cache.set("ns1", "k", value=1)
    cache.set("ns2", "k", value=2)
    cache.invalidate_namespace("ns1")
    with pytest.raises(KeyError):
        cache.get("ns1", "k")
    assert cache.get("ns2", "k") == 2


@pytest.mark.asyncio
async def test_cached_decorator() -> None:
    cache = CacheManager()
    call_count = 0

    @cache.cached("test")
    async def expensive(x: int) -> int:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)
        return x * 2

    assert await expensive(5) == 10
    assert await expensive(5) == 10
    assert call_count == 1

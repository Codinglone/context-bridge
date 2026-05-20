"""TTL cache wrapper built on cachetools."""

import hashlib
import inspect
import json
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache


class CacheManager:
    """Simple TTL cache with namespaced invalidation."""

    def __init__(self) -> None:
        self._caches: dict[str, TTLCache[str, Any]] = {}
        self._default_ttl: int = 60

    def _make_key(self, *parts: Any) -> str:
        """Create a stable cache key from arbitrary arguments."""
        data = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def get(self, namespace: str, *key_parts: Any) -> Any:
        """Retrieve a cached value, or raise KeyError if missing/expired."""
        cache = self._caches.get(namespace)
        if cache is None:
            raise KeyError(namespace)
        key = self._make_key(*key_parts)
        return cache[key]

    def set(
        self,
        namespace: str,
        *key_parts: Any,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Store a value in the named cache."""
        if namespace not in self._caches:
            self._caches[namespace] = TTLCache(
                maxsize=10_000,
                ttl=ttl or self._default_ttl,
            )
        key = self._make_key(*key_parts)
        self._caches[namespace][key] = value

    def invalidate(self, namespace: str, *key_parts: Any) -> None:
        """Remove a specific entry from a namespace."""
        cache = self._caches.get(namespace)
        if cache is None:
            return
        key = self._make_key(*key_parts)
        cache.pop(key, None)

    def invalidate_namespace(self, namespace: str) -> None:
        """Drop an entire namespace."""
        self._caches.pop(namespace, None)

    def clear(self) -> None:
        """Drop every cache."""
        self._caches.clear()

    def cached(
        self,
        namespace: str,
        ttl: int | None = None,
        key_fn: Callable[..., tuple[Any, ...]] | None = None,
    ) -> Callable[..., Any]:
        """Decorator that caches a coroutine or function result."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_fn:
                    cache_key = key_fn(*args, **kwargs)
                else:
                    cache_key = (args, tuple(sorted(kwargs.items())))
                try:
                    return self.get(namespace, *cache_key)
                except KeyError:
                    result = await func(*args, **kwargs)
                    self.set(namespace, *cache_key, value=result, ttl=ttl)
                    return result

            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_fn:
                    cache_key = key_fn(*args, **kwargs)
                else:
                    cache_key = (args, tuple(sorted(kwargs.items())))
                try:
                    return self.get(namespace, *cache_key)
                except KeyError:
                    result = func(*args, **kwargs)
                    self.set(namespace, *cache_key, value=result, ttl=ttl)
                    return result

            if inspect.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator

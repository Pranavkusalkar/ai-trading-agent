"""
In-memory data cache with TTL (time-to-live).
Prevents re-fetching within the refresh interval.
Thread-safe for single-process use.
"""

import time
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


class CacheEntry:
    def __init__(self, value: Any, ttl_seconds: int):
        self.value     = value
        self.expires   = time.time() + ttl_seconds
        self.created   = time.time()

    def is_expired(self) -> bool:
        return time.time() > self.expires

    def age_seconds(self) -> float:
        return time.time() - self.created


class DataCache:
    """
    Simple key-value cache with per-entry TTL.
    Keys are strings like "candles:NIFTY:5min" or "options:NIFTY:2026-08-21"
    """

    def __init__(self, default_ttl: int = 60):
        self._store:       dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._hits         = 0
        self._misses       = 0

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None or entry.is_expired():
            if entry:
                del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = CacheEntry(value, ttl)
        log.debug(f"Cache SET {key} (ttl={ttl}s)")

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear(self) -> None:
        self._store.clear()
        log.info("Cache cleared")

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "entries":   len(self._store),
            "hits":      self._hits,
            "misses":    self._misses,
            "hit_rate":  round(self._hits / total * 100, 1) if total else 0,
        }

    def is_fresh(self, key: str) -> bool:
        return self.get(key) is not None


# Singleton cache instance shared across data modules
_cache = DataCache(default_ttl=60)

def get_cache() -> DataCache:
    return _cache

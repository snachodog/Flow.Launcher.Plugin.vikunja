from __future__ import annotations

import time
from typing import Dict, Generic, Iterator, Tuple, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(self, ttl: float = 60.0) -> None:
        self._ttl = ttl
        self._store: Dict[K, Tuple[float, V]] = {}

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None

    def get(self, key: K) -> V | None:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: K, value: V) -> None:
        self._store[key] = (time.time() + self._ttl, value)

    def pop(self, key: K, default: V | None = None) -> V | None:
        item = self._store.pop(key, None)
        if item:
            return item[1]
        return default

    def clear(self) -> None:
        self._store.clear()

    def values(self) -> Iterator[V]:
        for key in list(self._store.keys()):
            value = self.get(key)
            if value is not None:
                yield value

    def items(self) -> Iterator[Tuple[K, V]]:
        for key in list(self._store.keys()):
            value = self.get(key)
            if value is not None:
                yield key, value

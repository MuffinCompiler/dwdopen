from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from dwdopen._fileserver.listing import ListingEntry

__all__ = ["ListingCache"]


class ListingCache:
    """The cache for the directory listings, split into two separate caches:
    The `_lasting` cache contains structural information about the models, like
    model names, available parameters, and available level types and levels.
    These do only change if DWD updates its models. These are kept until a call
    to refresh().
    The `_volatile` cache contains information that changes rapidly on the server,
    like available runs and available forecast steps. These are only kept for the
    duration of a running operation (for as long as a snapshot is held).

    Data is cached by path as their key, and the listing as their value.
    The caller says which cache a path belongs to, since it is the one that knows
    what the path means.
    """

    def __init__(self) -> None:
        self._lasting: dict[str, list[ListingEntry]] = {}
        self._volatile: dict[str, list[ListingEntry]] = {}
        self._lock = threading.Lock()
        self._holders = 0

    @contextmanager
    def snapshot(self) -> Iterator[None]:
        """Keep volatile listings only until the last operation lets go.
        """
        with self._lock:
            self._holders += 1
        try:
            yield
        finally:
            with self._lock:
                self._holders -= 1
                if self._holders == 0:
                    self._volatile.clear()

    def get(self, path: str, *, volatile: bool) -> list[ListingEntry] | None:
        """The listing stored for a path, or None if there is none to reuse."""
        cache = self._volatile if volatile else self._lasting
        return cache.get(path)

    def put(self, path: str, entries: list[ListingEntry], *, volatile: bool) -> None:
        """Store a listing."""
        with self._lock:
            if volatile and not self._holders:
                return # Do not cache if noone holds a reference to it.
            cache = self._volatile if volatile else self._lasting
            cache[path] = entries

    def clear(self) -> None:
        """Clear the caches."""
        with self._lock:
            self._lasting.clear()
            self._volatile.clear()

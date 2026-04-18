"""
TurnCache — memoization for Dubins turn computations between survey lines.

Stateless about HOW turns are computed (that's the caller's job).
Stateful about WHAT has been computed already, keyed by
(from_line, to_line, to_is_reciprocal).

Phase 5 scope: create the class and ship it with tests. The dockwidget's
existing inline dict-based _get_cached_turn is NOT rewired to use this
class yet — that rewire is Phase 6's job when handle_run_simulation
gets its SimulationService.run() overhaul.

Usage sketch (Phase 6):
    cache = TurnCache()
    result = cache.get_or_compute(
        key=(from_line, to_line, reciprocal),
        compute=lambda: expensive_dubins_turn(exit_pt, exit_hdg, entry_pt, entry_hdg),
    )
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Hashable, Iterator, Tuple

log = logging.getLogger(__name__)


@dataclass
class TurnCache:
    """Memoization wrapper indexed by turn key.

    The stored value can be any hashable caller-provided object. Typical
    use stores tuples of (geometry, length_m, time_s).
    """
    _store: Dict[Hashable, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: Hashable) -> bool:
        return key in self._store

    def __iter__(self) -> Iterator[Hashable]:
        return iter(self._store)

    def clear(self) -> None:
        """Drop all cached turns. Typically called at simulation start."""
        self._store.clear()

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        """Return the cached value for `key`, or compute + cache + return.

        `compute` must be a zero-argument callable — typically a lambda
        that captures the inputs needed to compute the turn. This keeps
        the cache agnostic of Dubins, QGIS, and simulation params.
        """
        if key in self._store:
            log.debug(f"TurnCache hit: {key}")
            return self._store[key]
        log.debug(f"TurnCache miss: {key}, computing")
        value = compute()
        self._store[key] = value
        return value

    def put(self, key: Hashable, value: Any) -> None:
        """Insert a pre-computed value directly. Overwrites existing."""
        self._store[key] = value

    def get(self, key: Hashable, default: Any = None) -> Any:
        """Read without computing. Returns `default` if key not cached."""
        return self._store.get(key, default)

    def stats(self) -> Tuple[int,]:
        """Return a tuple of cache diagnostics. Currently: (size,).
        Expandable without breaking callers that unpack len-1."""
        return (len(self._store),)

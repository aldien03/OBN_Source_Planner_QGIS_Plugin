# coding=utf-8
"""Phase 5 turn-cache tests — pure Python, no QGIS.

Verifies the cache memoizes correctly without knowing anything about
Dubins or QgsGeometry. The 'compute' callable supplied by the test just
increments a counter, so we can assert hit/miss semantics directly.
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.turn_cache import TurnCache  # noqa: E402


class TurnCacheHitMissTests(unittest.TestCase):
    def setUp(self):
        self.cache = TurnCache()
        self.call_count = 0

    def _compute_marker(self, marker):
        """Return a factory that increments the counter and yields `marker`."""
        def _factory():
            self.call_count += 1
            return marker
        return _factory

    def test_miss_then_hit_for_same_key(self):
        key = (1000, 1006, False)
        v1 = self.cache.get_or_compute(key, self._compute_marker("X"))
        self.assertEqual(v1, "X")
        self.assertEqual(self.call_count, 1)

        v2 = self.cache.get_or_compute(key, self._compute_marker("Y"))
        self.assertEqual(v2, "X", "Second call must return cached value, not re-compute")
        self.assertEqual(self.call_count, 1, "Compute must not be called on hit")

    def test_different_keys_produce_separate_entries(self):
        self.cache.get_or_compute((1000, 1006, False), self._compute_marker("A"))
        self.cache.get_or_compute((1000, 1006, True),  self._compute_marker("B"))
        self.cache.get_or_compute((1012, 1018, False), self._compute_marker("C"))
        self.assertEqual(self.call_count, 3)
        self.assertEqual(len(self.cache), 3)

    def test_key_includes_reciprocal_flag(self):
        """Turns between the same two lines in different directions must
        be treated as distinct cache entries."""
        self.cache.get_or_compute((1000, 1006, False), self._compute_marker("forward"))
        self.cache.get_or_compute((1000, 1006, True),  self._compute_marker("reverse"))
        self.assertEqual(self.cache.get((1000, 1006, False)), "forward")
        self.assertEqual(self.cache.get((1000, 1006, True)),  "reverse")


class TurnCacheHousekeepingTests(unittest.TestCase):
    def test_clear_drops_all_entries(self):
        cache = TurnCache()
        cache.put(("a",), 1)
        cache.put(("b",), 2)
        self.assertEqual(len(cache), 2)
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_contains_reflects_state(self):
        cache = TurnCache()
        self.assertNotIn(("x",), cache)
        cache.put(("x",), 42)
        self.assertIn(("x",), cache)

    def test_get_returns_default_on_miss(self):
        cache = TurnCache()
        self.assertIsNone(cache.get(("not_there",)))
        self.assertEqual(cache.get(("not_there",), default="fallback"), "fallback")

    def test_put_overwrites_existing(self):
        cache = TurnCache()
        cache.put(("k",), "v1")
        cache.put(("k",), "v2")
        self.assertEqual(cache.get(("k",)), "v2")

    def test_iter_yields_keys(self):
        cache = TurnCache()
        cache.put(("a",), 1)
        cache.put(("b",), 2)
        self.assertEqual(set(cache), {("a",), ("b",)})

    def test_stats_returns_size(self):
        cache = TurnCache()
        self.assertEqual(cache.stats(), (0,))
        cache.put(("a",), 1)
        cache.put(("b",), 2)
        self.assertEqual(cache.stats(), (2,))


if __name__ == "__main__":
    unittest.main(verbosity=2)

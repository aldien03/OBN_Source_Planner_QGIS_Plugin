# coding=utf-8
"""Dubins characterization smoke tests.

Locks in the CURRENT behavior of dubins_path.dubins_path() and get_curve()
so Phase 1's refactor (removing module globals, clarifying units) can be
verified as a behavior-preserving change. These are not correctness tests of
the Dubins math — they are regression guards.

dubins_path.py is pure-Python (imports only `math`), so these tests run
without QGIS. They can be executed via `pytest test/test_dubins_smoke.py`
or `python -m unittest test.test_dubins_smoke` from the plugin root.
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import math
import os
import sys
import unittest

# Allow running this file both from the plugin root and from test/
_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

import dubins_path  # noqa: E402


class DubinsPathCharacterizationTests(unittest.TestCase):
    """Lock in the current output shape and values of dubins_path()."""

    def test_dubins_path_returns_three_tuple_for_aligned_poses(self):
        """Aligned start/end poses (heading along +x) must return a valid solution.

        start=(0, 0, 0) is at origin facing +x.
        end=(500, 0, 0) is 500m ahead, also facing +x.
        A Dubins solver must find a path for this trivial case.
        """
        result = dubins_path.dubins_path((0.0, 0.0, 0.0), (500.0, 0.0, 0.0), 50.0)
        self.assertIsNotNone(result, "dubins_path returned None for aligned trivial case")
        self.assertEqual(len(result), 3, "dubins_path should return a 3-tuple (modes, lengths, radii)")

        modes, lengths, radii = result
        # modes is a 3-char string like 'LSL', 'RSR', 'LSR', 'RSL', 'RLR', 'LRL'.
        # For aligned poses the solver usually picks something with a straight middle segment.
        self.assertIsNotNone(modes, "modes must not be None")
        self.assertEqual(len(modes), 3, f"modes must be a 3-char string, got {modes!r}")
        self.assertTrue(all(c.upper() in {'L', 'S', 'R'} for c in modes),
                        f"modes must contain only L/S/R characters, got {modes!r}")

        # lengths is a list of three segment lengths, each >= 0.
        self.assertEqual(len(lengths), 3, f"lengths must have 3 entries, got {lengths!r}")
        for i, length in enumerate(lengths):
            self.assertIsInstance(length, float, f"lengths[{i}] must be float, got {type(length).__name__}")
            self.assertGreaterEqual(length, 0.0, f"lengths[{i}] must be >= 0, got {length}")

        # radii is a list of 3 equal values == input radius.
        self.assertEqual(len(radii), 3)
        for r in radii:
            self.assertAlmostEqual(r, 50.0, places=6, msg=f"each radius should equal input 50.0, got {r}")

        # Total path length for this aligned 500m case should be within 10% of 500m.
        # Rationale: aligned poses allow a near-straight Dubins path. This is
        # a loose bound but catches a Phase 1 regression that doubled/halved output.
        total = sum(lengths)
        self.assertGreater(total, 450.0, f"total Dubins length {total:.2f} is too short for 500m case")
        self.assertLess(total, 550.0, f"total Dubins length {total:.2f} is too long for 500m case")


class DubinsGetCurveCharacterizationTests(unittest.TestCase):
    """Lock in the current output shape of get_curve() and its endpoint accuracy."""

    def test_get_curve_returns_non_empty_point_list(self):
        """get_curve must produce a list of waypoints for a trivial aligned case."""
        points = dubins_path.get_curve(
            s_x=0.0, s_y=0.0, s_head=0.0,
            e_x=500.0, e_y=0.0, e_head=0.0,
            radius=50.0, max_line_distance=10.0,
        )
        self.assertIsNotNone(points, "get_curve returned None")
        self.assertGreater(len(points), 10,
                           f"get_curve should produce many waypoints for 500m / 10m spacing, got {len(points)}")

        # Each waypoint must be a 3-element sequence [x, y, heading].
        for i, p in enumerate(points):
            self.assertEqual(len(p), 3, f"points[{i}] has {len(p)} elements, expected 3 (x, y, heading)")
            for j, val in enumerate(p):
                self.assertIsInstance(val, (int, float),
                                      f"points[{i}][{j}] must be numeric, got {type(val).__name__}")
                self.assertTrue(math.isfinite(val),
                                f"points[{i}][{j}] must be finite, got {val}")

    def test_get_curve_endpoints_match_input_poses(self):
        """First point must equal start, last point must equal end (within tolerance).

        This is the most important characterization: any Phase 1 refactor that
        changes how endpoints are computed will break this test.
        """
        start = (0.0, 0.0, 0.0)
        end = (500.0, 0.0, 0.0)
        points = dubins_path.get_curve(
            s_x=start[0], s_y=start[1], s_head=start[2],
            e_x=end[0], e_y=end[1], e_head=end[2],
            radius=50.0, max_line_distance=10.0,
        )
        self.assertGreaterEqual(len(points), 2, "need at least start and end points")

        first = points[0]
        last = points[-1]

        # Endpoint positional tolerance: 1m. Dubins projection is exact in principle;
        # float arithmetic may introduce sub-meter rounding. 1m is very loose.
        self.assertAlmostEqual(first[0], start[0], delta=1.0,
                               msg=f"first x={first[0]} differs from start x={start[0]} by >1m")
        self.assertAlmostEqual(first[1], start[1], delta=1.0,
                               msg=f"first y={first[1]} differs from start y={start[1]} by >1m")
        self.assertAlmostEqual(last[0], end[0], delta=1.0,
                               msg=f"last x={last[0]} differs from end x={end[0]} by >1m")
        self.assertAlmostEqual(last[1], end[1], delta=1.0,
                               msg=f"last y={last[1]} differs from end y={end[1]} by >1m")


if __name__ == "__main__":
    unittest.main(verbosity=2)

# coding=utf-8
"""Phase 1 Dubins tests: verify module globals are gone and that densification
parameters flow explicitly through get_projection / get_curve.

Pure-Python tests — run without QGIS.
    python3 test/test_dubins.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import math
import os
import sys
import threading
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

import dubins_path  # noqa: E402


class NoMutableGlobalsTests(unittest.TestCase):
    """Phase 1 removed MAX_LINE_DISTANCE / MAX_CURVE_DISTANCE / MAX_CURVE_ANGLE
    from the module. This test fails if any of them reappear."""

    def test_no_max_line_distance_global(self):
        self.assertFalse(
            hasattr(dubins_path, 'MAX_LINE_DISTANCE'),
            "dubins_path.MAX_LINE_DISTANCE leaked back into the module"
        )

    def test_no_max_curve_distance_global(self):
        self.assertFalse(
            hasattr(dubins_path, 'MAX_CURVE_DISTANCE'),
            "dubins_path.MAX_CURVE_DISTANCE leaked back into the module"
        )

    def test_no_max_curve_angle_global(self):
        self.assertFalse(
            hasattr(dubins_path, 'MAX_CURVE_ANGLE'),
            "dubins_path.MAX_CURVE_ANGLE leaked back into the module"
        )

    def test_decimal_round_is_preserved(self):
        """DECIMAL_ROUND is a real constant, not a mutable knob — must still exist."""
        self.assertTrue(hasattr(dubins_path, 'DECIMAL_ROUND'))
        self.assertEqual(dubins_path.DECIMAL_ROUND, 7)


class GetProjectionParameterizedTests(unittest.TestCase):
    """get_projection now takes max_line_distance and max_curve_angle as
    parameters. Varying them must change the output density predictably."""

    def _build_solution(self, start, end, radius):
        """Helper: get a valid Dubins solution tuple."""
        modes, lengths, radii = dubins_path.dubins_path(start, end, radius)
        self.assertIsNotNone(modes, "precondition: dubins_path solved the case")
        return (modes, lengths, radii)

    def test_get_projection_denser_spacing_gives_more_points(self):
        """Halving max_line_distance should roughly double the point count."""
        start = (0.0, 0.0, 0.0)
        end = (500.0, 0.0, 0.0)
        sol = self._build_solution(start, end, 50.0)

        coarse = dubins_path.get_projection(
            start=start, end=end, solution=sol,
            max_line_distance=50.0, max_curve_angle=10.0,
        )
        fine = dubins_path.get_projection(
            start=start, end=end, solution=sol,
            max_line_distance=10.0, max_curve_angle=10.0,
        )
        self.assertGreater(len(fine), len(coarse),
                           f"finer max_line_distance must produce more points: "
                           f"coarse={len(coarse)}, fine={len(fine)}")

    def test_get_projection_signature_requires_new_params(self):
        """Calling without the new parameters must raise TypeError."""
        start = (0.0, 0.0, 0.0)
        end = (500.0, 0.0, 0.0)
        sol = self._build_solution(start, end, 50.0)
        with self.assertRaises(TypeError):
            dubins_path.get_projection(start=start, end=end, solution=sol)


class GetCurveIsolationTests(unittest.TestCase):
    """get_curve must not leak state between calls. Verified by running
    it concurrently with different max_line_distance values — each thread's
    result must reflect its own parameter, not a sibling's."""

    def test_concurrent_calls_produce_independent_results(self):
        """Two threads, two different densifications — each gets its own answer."""
        results = {}

        def run(density, key):
            pts = dubins_path.get_curve(
                s_x=0.0, s_y=0.0, s_head=0.0,
                e_x=500.0, e_y=0.0, e_head=0.0,
                radius=50.0, max_line_distance=density,
            )
            results[key] = len(pts)

        t_coarse = threading.Thread(target=run, args=(100.0, 'coarse'))
        t_fine = threading.Thread(target=run, args=(5.0, 'fine'))
        t_coarse.start()
        t_fine.start()
        t_coarse.join()
        t_fine.join()

        self.assertIn('coarse', results)
        self.assertIn('fine', results)
        self.assertGreater(results['fine'], results['coarse'],
                           f"fine ({results['fine']}) should have more points than coarse "
                           f"({results['coarse']}) even when run concurrently")

    def test_sequential_calls_do_not_bleed(self):
        """A coarse call followed by a fine call must not reuse the coarse's spacing.
        Before Phase 1 this was broken because get_curve mutated module globals."""
        pts_fine_first = dubins_path.get_curve(
            s_x=0.0, s_y=0.0, s_head=0.0, e_x=500.0, e_y=0.0, e_head=0.0,
            radius=50.0, max_line_distance=5.0,
        )
        pts_coarse = dubins_path.get_curve(
            s_x=0.0, s_y=0.0, s_head=0.0, e_x=500.0, e_y=0.0, e_head=0.0,
            radius=50.0, max_line_distance=100.0,
        )
        pts_fine_again = dubins_path.get_curve(
            s_x=0.0, s_y=0.0, s_head=0.0, e_x=500.0, e_y=0.0, e_head=0.0,
            radius=50.0, max_line_distance=5.0,
        )
        # First and third calls use the same params → must produce the same count.
        self.assertEqual(len(pts_fine_first), len(pts_fine_again),
                         "same params must yield same point count regardless of call order")
        # Fine should have strictly more points than coarse.
        self.assertGreater(len(pts_fine_first), len(pts_coarse))


if __name__ == "__main__":
    unittest.main(verbosity=2)

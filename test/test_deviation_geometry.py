# coding=utf-8
"""Tests for services/deviation_geometry.py (3-arc "tight bump" construction).

Pure Python. No QGIS dependency. Run with:

    python3 test/test_deviation_geometry.py

or:

    python3 -m unittest test.test_deviation_geometry
"""

from __future__ import annotations

import math
import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.deviation_geometry import (  # noqa: E402
    build_smooth_deviation,
    DeviationTooShort,
    DeviationTooTall,
)


def Pt(x, y):
    """Simple tuple point constructor for tests."""
    return (x, y)


# ------------------------- helpers ----------------------------------------


def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 0 else (0.0, 0.0)


def _circumradius(a, b, c):
    """Circumradius through three points. Returns +inf if collinear."""
    ab = math.hypot(b[0] - a[0], b[1] - a[1])
    bc = math.hypot(c[0] - b[0], c[1] - b[1])
    ca = math.hypot(a[0] - c[0], a[1] - c[1])
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    area = 0.5 * abs(cross)
    if area < 1e-9:
        return float("inf")
    return (ab * bc * ca) / (4.0 * area)


def _disk_polygon(center, radius, n_vertices=360):
    cx, cy = center
    return [
        (cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a)))
        for a in range(0, 360, 360 // n_vertices)
    ]


# ------------------------- tests ------------------------------------------


class TestPeakHeightMatchesClearance(unittest.TestCase):
    """The defining property of the 3-arc tight-bump: peak sits at exactly
    h_clear above the chord (obstacle + safety buffer)."""

    def test_small_obstacle_peak_at_clearance(self):
        """100m disk buffer + 50m clearance -> peak at 150m."""
        R = 900.0
        buffer_r = 100.0
        clearance = 50.0
        # Entry/exit well outside detour span.
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 100.0)
        buf = _disk_polygon((0.0, 0.0), buffer_r)
        pts = build_smooth_deviation(E, X, peak, R, clearance, buf, Pt)
        max_y = max(p[1] for p in pts)
        self.assertAlmostEqual(max_y, buffer_r + clearance, delta=1.0,
            msg=f"peak {max_y:.1f} should equal h_clear={buffer_r + clearance:.1f}")

    def test_medium_obstacle(self):
        """200m disk + 100m clearance -> peak at 300m."""
        R = 900.0
        buffer_r = 200.0
        clearance = 100.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 100.0)
        buf = _disk_polygon((0.0, 0.0), buffer_r)
        pts = build_smooth_deviation(E, X, peak, R, clearance, buf, Pt)
        max_y = max(p[1] for p in pts)
        self.assertAlmostEqual(max_y, 300.0, delta=1.0)

    def test_x_span_scales_with_sqrt_h_clear(self):
        """X span of the bump = 4R sin(theta) = proportional to sqrt(h_clear)
        for small h_clear."""
        R = 900.0
        results = []
        for h_clear in (100.0, 200.0, 400.0, 800.0):
            buf = _disk_polygon((0.0, 0.0), h_clear)
            E = (-5 * R, 0.0)
            X = (5 * R, 0.0)
            pts = build_smooth_deviation(E, X, (0.0, 100.0), R, 0.0, buf, Pt)
            # X span of the BUMP portion only: find the range of x for points
            # where y > 1.0 (above the chord prefix/suffix).
            bump_xs = [p[0] for p in pts if p[1] > 1.0]
            span = max(bump_xs) - min(bump_xs) if bump_xs else 0.0
            results.append((h_clear, span))
        # For small h_clear << 2R, span ~ 4R * sqrt(h_clear / R) = 4 * sqrt(R * h_clear).
        # Check that doubling h_clear grows span by ~sqrt(2).
        ratio_2to1 = results[1][1] / results[0][1]  # h=200 vs h=100
        self.assertAlmostEqual(ratio_2to1, math.sqrt(2.0), delta=0.1,
            msg=f"span ratio {ratio_2to1:.3f} expected ~{math.sqrt(2.0):.3f}")


class TestEndpoints(unittest.TestCase):

    def test_endpoints_bit_for_bit_exact(self):
        R = 900.0
        E = (123.456, 789.012)
        X = (2500.0, 1000.0)
        peak = (1300.0, 1200.0)
        buf = _disk_polygon((1300.0, 900.0), 100.0)
        pts = build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)
        self.assertEqual(pts[0], E)
        self.assertEqual(pts[-1], X)

    def test_upstream_farther_than_detour_span_adds_prefix_suffix(self):
        """Entry/exit farther out than 2R sin(theta) -> connector extends them."""
        R = 900.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 100.0)
        buf = _disk_polygon((0.0, 0.0), 100.0)
        pts = build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)
        self.assertEqual(pts[0], E)
        self.assertEqual(pts[-1], X)
        # Early points after E should still be on the chord (y ~ 0) -- prefix straight.
        self.assertAlmostEqual(pts[1][1], 0.0, delta=1.0)
        self.assertAlmostEqual(pts[-2][1], 0.0, delta=1.0)


class TestCurvatureAndContinuity(unittest.TestCase):

    def test_curvature_never_exceeds_one_over_R(self):
        """Every consecutive triple has circumradius >= R (within sampling tolerance)."""
        R = 900.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 200.0)
        buf = _disk_polygon((0.0, 0.0), 200.0)
        pts = build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)
        min_radius = float("inf")
        for i in range(1, len(pts) - 1):
            r = _circumradius(pts[i - 1], pts[i], pts[i + 1])
            min_radius = min(min_radius, r)
        # Allow 2% slack for sampling quantization; in practice it's much less.
        self.assertGreaterEqual(
            min_radius, 0.98 * R,
            f"min circumradius {min_radius:.2f} violates turn-radius floor {R:.2f}",
        )

    def test_g1_continuity_no_kinks(self):
        """No consecutive-segment angle exceeds sampling cap + small slack."""
        R = 900.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 200.0)
        buf = _disk_polygon((0.0, 0.0), 200.0)
        pts = build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)
        max_angle_deg = 0.0
        for i in range(1, len(pts) - 1):
            v1 = _unit((pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
            v2 = _unit((pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
            cos_a = max(-1.0, min(1.0, v1[0] * v2[0] + v1[1] * v2[1]))
            angle = math.degrees(math.acos(cos_a))
            max_angle_deg = max(max_angle_deg, angle)
        self.assertLess(max_angle_deg, 6.0,
            f"max inter-segment turn {max_angle_deg:.2f} deg > 6 (likely kink)")


class TestBufferClearance(unittest.TestCase):

    def test_no_polyline_point_inside_disk_plus_clearance(self):
        R = 900.0
        buffer_r = 200.0
        clearance = 50.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 100.0)
        buf = _disk_polygon((0.0, 0.0), buffer_r)
        pts = build_smooth_deviation(E, X, peak, R, clearance, buf, Pt)
        min_dist = min(math.hypot(p[0], p[1]) for p in pts)
        # The 3-arc construction grazes the buffer at (buffer_r + clearance);
        # sampling can put a vertex slightly inside, so allow 2m tolerance.
        self.assertGreaterEqual(
            min_dist, buffer_r + clearance - 2.0,
            f"closest polyline approach {min_dist:.1f} < clearance target "
            f"{buffer_r + clearance:.1f}",
        )


class TestSideSelection(unittest.TestCase):

    def test_peak_below_line_deviation_on_minus_y(self):
        """Peak at y=-100 -> detour entirely on -y side."""
        R = 900.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, -100.0)
        buf = _disk_polygon((0.0, 0.0), 100.0)
        pts = build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)
        for p in pts[1:-1]:
            self.assertLess(p[1], 1e-6, f"interior point {p} is on +y side")


class TestSymmetry(unittest.TestCase):

    def test_bump_portion_is_symmetric(self):
        """The BUMP portion (arcs) is symmetric about the chord midpoint.

        Prefix/suffix straights may sample asymmetrically due to the
        `floor(length/step)` chain not lining up identically from both ends,
        but the arcs themselves -- sampled by angular step -- are symmetric
        by construction.
        """
        R = 900.0
        E = (-3 * R, 0.0)
        X = (3 * R, 0.0)
        peak = (0.0, 100.0)
        buf = _disk_polygon((0.0, 0.0), 150.0)
        pts = build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)
        # Restrict to the bump portion: points with y > 1.0 (above chord).
        bump = [p for p in pts if p[1] > 1.0]
        self.assertGreater(len(bump), 10, "bump portion should have multiple samples")
        # The bump should be symmetric about x = 0.
        mirrored = sorted([(-p[0], p[1]) for p in bump])
        original = sorted([(p[0], p[1]) for p in bump])
        self.assertEqual(len(mirrored), len(original))
        for mp, op in zip(mirrored, original):
            self.assertAlmostEqual(mp[0], op[0], delta=0.1)
            self.assertAlmostEqual(mp[1], op[1], delta=0.1)


class TestFailureCases(unittest.TestCase):

    def test_entry_too_close_raises_deviation_too_short(self):
        """A 200m buffer with entry/exit only 500m away from OC -> half-span
        of detour (2R sin theta) exceeds the available chord distance."""
        R = 900.0
        E = (-500.0, 0.0)
        X = (500.0, 0.0)
        peak = (0.0, 100.0)
        buf = _disk_polygon((0.0, 0.0), 200.0)
        with self.assertRaises(DeviationTooShort):
            build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)

    def test_obstacle_too_tall_raises_deviation_too_tall(self):
        """h_clear > 3R = 2700m -> unreasonable detour -> raise."""
        R = 900.0
        E = (-5 * R, 0.0)
        X = (5 * R, 0.0)
        peak = (0.0, 100.0)
        # Rectangular buffer reaching y=3000m
        buf = [(-200.0, 0.0), (200.0, 0.0), (200.0, 3000.0), (-200.0, 3000.0)]
        with self.assertRaises(DeviationTooTall):
            build_smooth_deviation(E, X, peak, R, 0.0, buf, Pt)


class TestRegressionCases(unittest.TestCase):
    """Scenarios pulled from real user-reported failures."""

    def test_line_2707_style_wide_buffer(self):
        """A scenario where the old top-hat's straight at x=+R clipped a
        laterally-wide buffer. In the 3-arc construction there are no straights
        at +/-R, so this should succeed."""
        R = 900.0
        # Simulate a line from ~4km west to ~4km east of a wide obstacle cluster.
        E = (-4200.0, 0.0)
        X = (4200.0, 0.0)
        peak = (0.0, 500.0)
        # Elongated buffer wider along chord than R=900
        buf = [
            (-1200.0, 100.0), (1200.0, 100.0),
            (1200.0, 500.0), (-1200.0, 500.0),
        ]
        pts = build_smooth_deviation(E, X, peak, R, 50.0, buf, Pt)
        # h_clear = 500 + 50 = 550m. Peak at 550m.
        max_y = max(p[1] for p in pts)
        self.assertAlmostEqual(max_y, 550.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()

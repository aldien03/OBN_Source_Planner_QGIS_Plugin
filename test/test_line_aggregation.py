# coding=utf-8
"""Phase 4 line-direction aggregation tests — pure Python, no QGIS.

    python3 test/test_line_aggregation.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from io_sps.line_aggregation import aggregate_line_direction  # noqa: E402


class UniformInputTests(unittest.TestCase):
    """When all points agree (or are within tolerance), return the mean and
    no warning."""

    def test_all_points_identical(self):
        result, warning = aggregate_line_direction([76.8, 76.8, 76.8, 76.8])
        self.assertAlmostEqual(result, 76.8, places=6)
        self.assertIsNone(warning)

    def test_within_default_tolerance(self):
        """0.05° spread is within the default 0.1° tolerance."""
        result, warning = aggregate_line_direction([76.80, 76.82, 76.85])
        # Mean of [76.80, 76.82, 76.85] = 76.823...
        self.assertAlmostEqual(result, 76.823, places=2)
        self.assertIsNone(warning)

    def test_reciprocal_direction(self):
        """Real 4D scenario: one line may shoot at 256.8° (=76.8°+180)."""
        result, warning = aggregate_line_direction([256.8, 256.8, 256.8])
        self.assertAlmostEqual(result, 256.8, places=6)
        self.assertIsNone(warning)


class NoDataTests(unittest.TestCase):
    """Files without direction data (e.g. PXGEO) yield None, None."""

    def test_empty_list(self):
        result, warning = aggregate_line_direction([])
        self.assertIsNone(result)
        self.assertIsNone(warning)

    def test_all_none(self):
        result, warning = aggregate_line_direction([None, None, None])
        self.assertIsNone(result)
        self.assertIsNone(warning)


class NonUniformInputTests(unittest.TestCase):
    """When points disagree beyond tolerance, return the mode and a
    warning message the caller can log."""

    def test_mixed_returns_mode(self):
        """4 points at 76.8°, 1 at 90.0° → mode is 76.8, warning emitted."""
        result, warning = aggregate_line_direction([76.8, 76.8, 76.8, 76.8, 90.0])
        self.assertAlmostEqual(result, 76.8, places=1)
        self.assertIsNotNone(warning)
        self.assertIn("non-uniform", warning.lower())
        self.assertIn("76.8", warning)

    def test_warning_reports_spread(self):
        """Warning text must include the spread so log readers can triage."""
        result, warning = aggregate_line_direction([76.8, 82.5])
        self.assertIsNotNone(warning)
        self.assertIn("spread", warning.lower())


class PartialNoneTests(unittest.TestCase):
    """None entries are ignored (e.g. one point missing direction data).
    Remaining non-None values drive the aggregation."""

    def test_some_none_ignored(self):
        result, warning = aggregate_line_direction([None, 76.8, None, 76.8, 76.8])
        self.assertAlmostEqual(result, 76.8, places=6)
        self.assertIsNone(warning)

    def test_single_non_none(self):
        result, warning = aggregate_line_direction([None, None, 76.8])
        self.assertAlmostEqual(result, 76.8, places=6)
        self.assertIsNone(warning)


if __name__ == "__main__":
    unittest.main(verbosity=2)

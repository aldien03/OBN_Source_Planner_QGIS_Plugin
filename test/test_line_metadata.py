# coding=utf-8
"""Phase 16a line-metadata tests — pure Python, no QGIS.

    python3 test/test_line_metadata.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-18'

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.line_metadata import (  # noqa: E402
    LineOperation,
    LineMetadata,
    DEFAULT_OPERATION,
    contiguous_runs,
    format_sub_line_label,
)


class LineOperationTests(unittest.TestCase):
    def test_enum_values_match_reference_pdf(self):
        self.assertEqual(LineOperation.PRODUCTION.value, "Production")
        self.assertEqual(LineOperation.TEST.value, "Test")
        self.assertEqual(LineOperation.RESHOOT.value, "Reshoot")
        self.assertEqual(LineOperation.INFILL.value, "Infill")

    def test_default_is_production(self):
        self.assertEqual(DEFAULT_OPERATION, LineOperation.PRODUCTION)

    def test_from_str_accepts_exact_strings(self):
        self.assertEqual(LineOperation.from_str("Infill"), LineOperation.INFILL)

    def test_from_str_passthrough_member(self):
        self.assertEqual(
            LineOperation.from_str(LineOperation.TEST), LineOperation.TEST
        )

    def test_from_str_rejects_unknown(self):
        with self.assertRaises(ValueError):
            LineOperation.from_str("Calibration")


class LineMetadataValidationTests(unittest.TestCase):
    def _make(self, fgsp, lgsp, op=LineOperation.PRODUCTION, line_num=2146):
        return LineMetadata(line_num=line_num, operation=op, fgsp=fgsp, lgsp=lgsp)

    def test_valid_forward_full_range(self):
        self._make(1001, 1999).validate(1001, 1999)

    def test_valid_reverse_full_range(self):
        self._make(1999, 1001).validate(1001, 1999)

    def test_valid_partial_range_forward(self):
        self._make(5583, 6563).validate(5001, 6999)

    def test_valid_partial_range_reverse(self):
        self._make(6563, 5583).validate(5001, 6999)

    def test_fgsp_below_lowest_raises(self):
        with self.assertRaises(ValueError):
            self._make(999, 1999).validate(1001, 1999)

    def test_lgsp_above_highest_raises(self):
        with self.assertRaises(ValueError):
            self._make(1001, 2500).validate(1001, 1999)

    def test_fgsp_equal_lgsp_raises(self):
        with self.assertRaises(ValueError):
            self._make(1500, 1500).validate(1001, 1999)

    def test_inverted_bounds_raise(self):
        with self.assertRaises(ValueError):
            self._make(1001, 1999).validate(2000, 1000)


class LineMetadataHelpersTests(unittest.TestCase):
    def _make(self, fgsp, lgsp):
        return LineMetadata(
            line_num=2146, operation=LineOperation.PRODUCTION,
            fgsp=fgsp, lgsp=lgsp,
        )

    def test_is_full_range_forward(self):
        self.assertTrue(self._make(1001, 1999).is_full_range(1001, 1999))

    def test_is_full_range_reverse(self):
        self.assertTrue(self._make(1999, 1001).is_full_range(1001, 1999))

    def test_is_full_range_partial(self):
        self.assertFalse(self._make(1500, 1800).is_full_range(1001, 1999))

    def test_is_reverse_direction_forward(self):
        self.assertFalse(self._make(1001, 1999).is_reverse_direction())

    def test_is_reverse_direction_reverse(self):
        self.assertTrue(self._make(1999, 1001).is_reverse_direction())


class ContiguousRunsTests(unittest.TestCase):
    """Phase 16d: split SP-sorted points into contiguous runs."""

    def _tba(self, *sps):
        return [{'sp': sp, 'status': 'To Be Acquired'} for sp in sps]

    def _acq(self, *sps):
        return [{'sp': sp, 'status': 'Acquired'} for sp in sps]

    def _is_tba(self, item):
        return item['status'] == 'To Be Acquired'

    def test_empty_input(self):
        self.assertEqual(contiguous_runs([], self._is_tba), [])

    def test_all_false(self):
        self.assertEqual(contiguous_runs(self._acq(1, 2, 3), self._is_tba), [])

    def test_all_true_single_run(self):
        points = self._tba(1, 2, 3, 4)
        runs = contiguous_runs(points, self._is_tba)
        self.assertEqual(len(runs), 1)
        self.assertEqual([p['sp'] for p in runs[0]], [1, 2, 3, 4])

    def test_two_runs_with_acquired_gap(self):
        points = self._tba(1, 2) + self._acq(3, 4, 5) + self._tba(6, 7, 8)
        runs = contiguous_runs(points, self._is_tba)
        self.assertEqual(len(runs), 2)
        self.assertEqual([p['sp'] for p in runs[0]], [1, 2])
        self.assertEqual([p['sp'] for p in runs[1]], [6, 7, 8])

    def test_sp_number_gaps_do_not_break_run(self):
        # 3500 and 3503 are adjacent in sort order (3501/3502 absent from
        # layer); run should stay contiguous.
        points = self._tba(3500, 3503, 3506)
        runs = contiguous_runs(points, self._is_tba)
        self.assertEqual(len(runs), 1)

    def test_single_point_runs_emitted(self):
        points = self._tba(1) + self._acq(2) + self._tba(3)
        runs = contiguous_runs(points, self._is_tba)
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(runs[0]), 1)
        self.assertEqual(len(runs[1]), 1)

    def test_trailing_tba(self):
        points = self._acq(1) + self._tba(2, 3)
        runs = contiguous_runs(points, self._is_tba)
        self.assertEqual(len(runs), 1)
        self.assertEqual([p['sp'] for p in runs[0]], [2, 3])

    def test_leading_tba(self):
        points = self._tba(1, 2) + self._acq(3)
        runs = contiguous_runs(points, self._is_tba)
        self.assertEqual(len(runs), 1)
        self.assertEqual([p['sp'] for p in runs[0]], [1, 2])


class SubLineLabelTests(unittest.TestCase):
    """Phase 16d: label format for the Generated_Survey_Lines Label field."""

    def test_full_range_returns_bare_line_num(self):
        self.assertEqual(format_sub_line_label(2146, 1000, 1500, 1000, 1500), "2146")

    def test_partial_range_returns_parenthesized(self):
        self.assertEqual(format_sub_line_label(2146, 1101, 1500, 1000, 1500), "2146 (1101-1500)")

    def test_partial_on_both_ends(self):
        self.assertEqual(format_sub_line_label(2146, 1100, 1400, 1000, 1500), "2146 (1100-1400)")

    def test_full_min_or_max_none_falls_back_to_partial(self):
        # Defensive: if full_min/full_max unknown, always render partial.
        self.assertEqual(format_sub_line_label(42, 10, 20, None, None), "42 (10-20)")
        self.assertEqual(format_sub_line_label(42, 10, 20, 10, None), "42 (10-20)")


if __name__ == '__main__':
    unittest.main()

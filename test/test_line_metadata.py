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


if __name__ == '__main__':
    unittest.main()

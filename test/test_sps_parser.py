# coding=utf-8
"""Phase 3 SPS parser tests — multi-format support + real-file bug fixes.

Pure-Python. Fixtures live in test/fixtures/.
    python3 test/test_sps_parser.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from io_sps.sps_parser import parse_sps, detect_spec, SpsRecord  # noqa: E402
from io_sps.sps_spec import (                                     # noqa: E402
    SPS_1_0, SPS_2_1, SPS_2_1_DIRECTION, SPS_SPECS, _parse_numeric_id,
)

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class NumericIdParserTests(unittest.TestCase):
    """_parse_numeric_id must accept both integer and decimal line/SP ids.

    The current _parse_sps_file_content in the dockwidget crashes on Martin
    Linge's decimal '2431.0' because it uses int() directly — this is the
    root cause Phase 3 fixes.
    """
    def test_parses_plain_integer(self):
        self.assertEqual(_parse_numeric_id("1006"), 1006)

    def test_parses_decimal_with_trailing_zero(self):
        self.assertEqual(_parse_numeric_id("2431.0"), 2431)

    def test_parses_with_surrounding_spaces(self):
        self.assertEqual(_parse_numeric_id("    2431.0"), 2431)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            _parse_numeric_id("ABCD")


class ParseFixturesTests(unittest.TestCase):
    """Each hand-crafted fixture parses cleanly with auto-detection."""

    def _path(self, name): return os.path.join(_FIXTURES, name)

    def test_parse_sps_2_1_canonical(self):
        r = parse_sps(self._path("sample_sps_2_1.sps"))
        self.assertEqual(r.spec_used.name, "SPS 2.1")
        self.assertEqual(len(r.records), 5)
        self.assertEqual(len(r.errors), 0)
        self.assertEqual(r.records[0].line_num, 2001)
        self.assertEqual(r.records[0].sp, 3100)
        self.assertAlmostEqual(r.records[0].easting, 410000.0, places=1)
        self.assertIsNone(r.records[0].direction)

    def test_parse_martin_linge_preserves_direction(self):
        """The point of Phase 3 + 4 + 6: direction data survives the parse."""
        r = parse_sps(self._path("sample_martin_linge.sps"))
        self.assertEqual(r.spec_used.name, "SPS 2.1 + direction")
        self.assertEqual(len(r.records), 5)
        # First 3 rows are line 2431 @ direction 76.8°
        for rec in r.records[:3]:
            self.assertEqual(rec.line_num, 2431)
            self.assertAlmostEqual(rec.direction, 76.8, places=1)
        # Next 2 are line 2439 @ direction 256.8°
        for rec in r.records[3:]:
            self.assertEqual(rec.line_num, 2439)
            self.assertAlmostEqual(rec.direction, 256.8, places=1)

    def test_parse_pxgeo_headerless(self):
        """PXGEO .s01 files have no H-records and use integer line/SP."""
        r = parse_sps(self._path("sample_pxgeo.s01"))
        self.assertEqual(r.spec_used.name, "SPS 2.1")
        self.assertEqual(len(r.records), 5)
        self.assertEqual(len(r.errors), 0)
        self.assertEqual(r.records[0].line_num, 1006)
        self.assertIsNone(r.records[0].direction)

    def test_parse_sps_1_0(self):
        """Original 1990 SPS001 format — 4-character line/SP fields."""
        r = parse_sps(self._path("sample_sps_1_0.sps"))
        self.assertEqual(r.spec_used.name, "SPS 1.0")
        self.assertEqual(len(r.records), 5)
        self.assertEqual(r.records[0].line_num, 1189)
        self.assertEqual(r.records[0].sp, 1588)

    def test_parse_short_lines_reports_errors_not_crash(self):
        """Truncated lines go into errors, good lines still parse."""
        r = parse_sps(self._path("sample_short_lines.sps"))
        # Fixture has 4 good + 1 truncated line (good - good - good - TRUNC - good - good actually)
        self.assertGreaterEqual(len(r.records), 4)
        self.assertGreaterEqual(len(r.errors), 1)
        # The error message should mention line number and length problem
        self.assertTrue(any("too short" in e for e in r.errors))

    def test_parse_empty_path_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            parse_sps("/nonexistent/path/that/does/not/exist.sps")


class DetectSpecTests(unittest.TestCase):
    """detect_spec picks the best-matching spec."""

    def _path(self, name): return os.path.join(_FIXTURES, name)

    def test_detect_martin_linge_prefers_direction_variant(self):
        """If a file parses cleanly with both SPS_2_1 and SPS_2_1_DIRECTION,
        the direction variant wins (because it's registered first in SPS_SPECS
        and yields equal or higher confidence)."""
        spec, conf = detect_spec(self._path("sample_martin_linge.sps"))
        self.assertEqual(spec.name, "SPS 2.1 + direction")
        self.assertGreaterEqual(conf, 0.99)

    def test_detect_pxgeo_picks_sps_2_1(self):
        """PXGEO fixture has no direction column and lines < 86 chars, so
        SPS_2_1_DIRECTION rejects it (min_length guard) and SPS_2_1 wins."""
        spec, conf = detect_spec(self._path("sample_pxgeo.s01"))
        self.assertEqual(spec.name, "SPS 2.1")
        self.assertGreaterEqual(conf, 0.99)

    def test_detect_sps_1_0_identifies_old_format(self):
        """SPS_1_0 file has SP field at chars 21-25, which SPS_2_1 sees as
        whitespace. SPS_1_0 spec is the only one that parses the SP field
        correctly → highest ratio."""
        spec, conf = detect_spec(self._path("sample_sps_1_0.sps"))
        self.assertEqual(spec.name, "SPS 1.0")
        self.assertGreaterEqual(conf, 0.99)

    def test_detect_returns_fallback_on_empty_file(self):
        """Empty file → zero confidence, default spec returned."""
        empty = os.path.join(_FIXTURES, "_test_empty.sps")
        try:
            open(empty, "w").close()
            spec, conf = detect_spec(empty)
            self.assertEqual(conf, 0.0)
            self.assertEqual(spec.name, SPS_2_1.name)  # default
        finally:
            if os.path.exists(empty):
                os.remove(empty)


class LegacyDictConversionTests(unittest.TestCase):
    """Dockwidget callers expect dicts with keys line/sp/e/n. SpsRecord
    provides to_legacy_dict() for that compatibility."""

    def test_to_legacy_dict_basic(self):
        rec = SpsRecord(line_num=2001, sp=3100, easting=410000.0, northing=7536000.0)
        d = rec.to_legacy_dict()
        self.assertEqual(d, {"line": 2001, "sp": 3100, "e": 410000.0, "n": 7536000.0})

    def test_to_legacy_dict_with_direction(self):
        rec = SpsRecord(line_num=2431, sp=3428, easting=442792.2,
                        northing=6700226.6, direction=76.8)
        d = rec.to_legacy_dict()
        self.assertEqual(d["line"], 2431)
        self.assertEqual(d["prev_direction"], 76.8)


if __name__ == "__main__":
    unittest.main(verbosity=2)

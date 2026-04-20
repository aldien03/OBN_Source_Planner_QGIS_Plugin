# coding=utf-8
"""Phase 17a pdf_export tests — pure Python, no QGIS.

    python3 test/test_pdf_export.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-20'

import os
import sys
import tempfile
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.pdf_export import (  # noqa: E402
    LookaheadRow,
    _cell_text,
    compute_output_filename,
    render_header_text,
    sanitize_filename_fragment,
)
from datetime import datetime  # noqa: E402


def _row(*, line_num=2495, sub_line_id=None, line_seq=1000):
    """Build a LookaheadRow for cell-rendering tests. Only fields
    read by _cell_text need realistic values."""
    t = datetime(2026, 4, 20, 13, 0)
    return LookaheadRow(
        seq_order=1,
        line_seq=line_seq,
        line_num=line_num,
        sub_line_id=sub_line_id,
        operation="Production",
        fgsp=3428,
        lgsp=3931,
        heading_deg=77.0,
        eta_sol=t,
        eta_eol=t,
        day_month="20-Apr",
    )


def _touch(dirpath, filename):
    full = os.path.join(dirpath, filename)
    open(full, "w").close()
    return full


class SanitizeFragmentTests(unittest.TestCase):
    def test_replaces_illegal_chars(self):
        self.assertEqual(
            sanitize_filename_fragment("a/b\\c:d*e?f\"g<h>i|j"),
            "a_b_c_d_e_f_g_h_i_j",
        )

    def test_preserves_spaces_and_dashes(self):
        self.assertEqual(sanitize_filename_fragment("4D TVD - Phase 2"),
                         "4D TVD - Phase 2")

    def test_empty_falls_back(self):
        self.assertEqual(sanitize_filename_fragment(""), "Survey")

    def test_whitespace_only_falls_back(self):
        self.assertEqual(sanitize_filename_fragment("   "), "Survey")

    def test_none_input_falls_back(self):
        self.assertEqual(sanitize_filename_fragment(None), "Survey")


class FilenameTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.date = "2026_04_20"

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_export_no_existing_files(self):
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD", self.dir),
            "2026_04_20 - 4D TVD_48hrLookahead_V1.0.pdf",
        )

    def test_first_export_with_other_surveys_present(self):
        # Other-survey V1.0 must NOT bump this survey's count.
        _touch(self.dir, f"{self.date} - Martin Linge_48hrLookahead_V1.0.pdf")
        _touch(self.dir, f"{self.date} - Martin Linge_48hrLookahead_V1.1.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD", self.dir),
            "2026_04_20 - 4D TVD_48hrLookahead_V1.0.pdf",
        )

    def test_increments_minor_when_prior_versions_exist(self):
        for n in range(5):
            _touch(self.dir, f"{self.date} - 4D TVD_48hrLookahead_V1.{n}.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD", self.dir),
            "2026_04_20 - 4D TVD_48hrLookahead_V1.5.pdf",
        )

    def test_double_digit_minor(self):
        for n in range(10):
            _touch(self.dir, f"{self.date} - 4D TVD_48hrLookahead_V1.{n}.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD", self.dir),
            "2026_04_20 - 4D TVD_48hrLookahead_V1.10.pdf",
        )

    def test_survey_name_with_spaces_and_dashes(self):
        _touch(self.dir,
               f"{self.date} - 4D TVD - Phase 2_48hrLookahead_V1.0.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD - Phase 2", self.dir),
            "2026_04_20 - 4D TVD - Phase 2_48hrLookahead_V1.1.pdf",
        )

    def test_corrupt_entries_are_ignored(self):
        _touch(self.dir, f"{self.date} - 4D TVD_48hrLookahead_V1.abc.pdf")
        _touch(self.dir, f"{self.date} - 4D TVD_48hrLookahead_vX.pdf")
        _touch(self.dir, "random_file.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD", self.dir),
            "2026_04_20 - 4D TVD_48hrLookahead_V1.0.pdf",
        )

    def test_illegal_chars_sanitized_before_scan_and_write(self):
        # A survey name containing illegal chars should be sanitized.
        # Pre-seed the dir with the sanitized form to prove the scan
        # uses the sanitized name.
        _touch(self.dir, f"{self.date} - 4D_TVD_48hrLookahead_V1.0.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D/TVD", self.dir),
            "2026_04_20 - 4D_TVD_48hrLookahead_V1.1.pdf",
        )

    def test_major_version_not_v1_does_not_bump(self):
        # A stray V2.0 on disk is not part of the V1 series and must be
        # ignored so V1.0 still computes next-slot from V1.* only.
        _touch(self.dir, f"{self.date} - 4D TVD_48hrLookahead_V2.0.pdf")
        self.assertEqual(
            compute_output_filename(self.date, "4D TVD", self.dir),
            "2026_04_20 - 4D TVD_48hrLookahead_V1.0.pdf",
        )


class RenderHeaderTextTests(unittest.TestCase):

    def test_all_placeholders_expanded(self):
        out = render_header_text(
            "{vessel} {hours}Hrs Look Ahead \u2014 {project}",
            vessel="Sanco Star",
            project="Petrobras MMBC \u2014 3D OBN",
            hours=48,
            date_str="2026_04_20",
        )
        self.assertEqual(
            out,
            "Sanco Star 48Hrs Look Ahead \u2014 Petrobras MMBC \u2014 3D OBN",
        )

    def test_unknown_placeholder_stays_literal(self):
        out = render_header_text(
            "{vessel} — {client}",  # {client} is intentionally not a valid key
            vessel="Sanco Star",
            project="P",
            hours=48,
            date_str="2026_04_20",
        )
        self.assertEqual(out, "Sanco Star — {client}")

    def test_empty_template_yields_empty_string(self):
        self.assertEqual(
            render_header_text("", vessel="V", project="P", hours=48,
                               date_str="2026_04_20"),
            "",
        )

    def test_unicode_vessel_and_date(self):
        out = render_header_text(
            "{vessel} ({date})",
            vessel="Geowave \u00d8rn",
            project="P",
            hours=24,
            date_str="2026_04_20",
        )
        self.assertEqual(out, "Geowave \u00d8rn (2026_04_20)")

    def test_survey_placeholder(self):
        out = render_header_text(
            "{survey}: {hours}h",
            vessel="V",
            project="P",
            hours=48,
            date_str="2026_04_20",
            survey="4D TVD",
        )
        self.assertEqual(out, "4D TVD: 48h")


class LineColumnCellTests(unittest.TestCase):
    """Phase 17d.1: Line column is ALWAYS the bare LineNum, even when
    the row has a SubLineId. The sub-line identity is already implicit
    in the FGSP/LGSP values; duplicating it in the Line column confuses
    the chief navigator."""

    def test_line_column_with_no_sub_line(self):
        self.assertEqual(
            _cell_text(_row(line_num=2495, sub_line_id=None), "line_num"),
            "2495",
        )

    def test_line_column_is_bare_line_num_even_with_sub_line_id(self):
        self.assertEqual(
            _cell_text(_row(line_num=2495, sub_line_id=2), "line_num"),
            "2495",
        )

    def test_line_column_with_sub_line_id_10(self):
        # Regression: previous code produced "2495-10" — confirm gone.
        self.assertEqual(
            _cell_text(_row(line_num=2495, sub_line_id=10), "line_num"),
            "2495",
        )

    def test_seq_column_uses_line_seq(self):
        self.assertEqual(
            _cell_text(_row(line_seq=1000), "line_seq"),
            "1000",
        )


if __name__ == "__main__":
    unittest.main()

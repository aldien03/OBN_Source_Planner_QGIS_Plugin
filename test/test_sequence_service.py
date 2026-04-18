# coding=utf-8
"""Phase 5 sequence-service tests — pure Python, no QGIS.

    python3 test/test_sequence_service.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.sequence_service import (  # noqa: E402
    calculate_most_common_step,
    find_closest_line_index,
    generate_racetrack_sequence,
    determine_next_line,
    LineDirection,
    assign_direction_for_line,
    _angular_diff_deg,
    _flip_direction,
)


class CalculateMostCommonStepTests(unittest.TestCase):
    def test_regular_spacing_returns_mode(self):
        self.assertEqual(calculate_most_common_step([1000, 1006, 1012, 1018, 1024]), 6)

    def test_mixed_spacing_returns_mode_if_majority(self):
        # 3 deltas of 6, 1 delta of 8 — mode wins
        self.assertEqual(calculate_most_common_step([1000, 1006, 1012, 1018, 1026]), 6)

    def test_empty_returns_zero(self):
        self.assertEqual(calculate_most_common_step([]), 0)

    def test_single_element_returns_zero(self):
        self.assertEqual(calculate_most_common_step([1000]), 0)

    def test_two_element_returns_delta(self):
        self.assertEqual(calculate_most_common_step([1000, 1006]), 6)

    def test_no_mode_falls_back_to_average(self):
        # All deltas are distinct: 6, 8, 10 -> mean = 8
        self.assertEqual(calculate_most_common_step([1000, 1006, 1014, 1024]), 8)


class FindClosestLineIndexTests(unittest.TestCase):
    def setUp(self):
        self.lines = [1000, 1006, 1012, 1018, 1024, 1030, 1036]

    def test_exact_match_at_jump_position(self):
        # current_idx=0, ideal_jump=3 -> target_idx=3 -> sorted_lines[3]=1018
        # target_line=1018 -> exact match at idx 3
        self.assertEqual(find_closest_line_index(self.lines, 1018, 0, 3), 3)

    def test_target_between_lines_picks_closer(self):
        # target=1017, closest is 1018 (idx 3) since 1018-1017=1 vs 1017-1012=5
        self.assertEqual(find_closest_line_index(self.lines, 1017, 0, 3), 3)

    def test_respects_search_window(self):
        # ideal_jump=3, search_range=5 window spans idx 0..8 (clamped to 6)
        # asking for target=1100 returns the closest within window = last element
        self.assertEqual(find_closest_line_index(self.lines, 1100, 0, 3), 6)

    def test_empty_sequence_returns_minus_one(self):
        self.assertEqual(find_closest_line_index([], 1000, 0, 3), -1)


class GenerateRacetrackSequenceTests(unittest.TestCase):
    def test_empty_lines_returns_none(self):
        self.assertIsNone(generate_racetrack_sequence([], 1000, 3))

    def test_all_lines_appear_in_sequence(self):
        lines = [1000, 1006, 1012, 1018, 1024, 1030]
        result = generate_racetrack_sequence(lines, 1000, 3)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(result), sorted(lines),
                         "Generated sequence must contain every active line exactly once")

    def test_first_line_is_at_front(self):
        lines = [1000, 1006, 1012, 1018, 1024, 1030]
        result = generate_racetrack_sequence(lines, 1012, 2)
        self.assertEqual(result[0], 1012)

    def test_start_line_not_in_list_fallback(self):
        """If first_line_num not in active set, the function logs a warning
        and uses sorted_active_lines[0] instead."""
        lines = [1000, 1006, 1012, 1018]
        result = generate_racetrack_sequence(lines, 9999, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 1000)

    def test_jump_count_zero_is_clamped_to_one(self):
        lines = [1000, 1006, 1012]
        result = generate_racetrack_sequence(lines, 1000, 0)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(result), sorted(lines))

    def test_real_world_pattern_large(self):
        """Integration-ish: 20 lines with 6-unit step, jump 6 -> sequence covers all."""
        lines = list(range(1000, 1120, 6))  # 1000, 1006, ..., 1114 -- 20 lines
        self.assertEqual(len(lines), 20)
        result = generate_racetrack_sequence(lines, 1000, 6)
        self.assertEqual(sorted(result), sorted(lines))
        self.assertEqual(result[0], 1000)


class DetermineNextLineTests(unittest.TestCase):
    def test_empty_remaining_returns_none(self):
        self.assertIsNone(determine_next_line(1000, set(), None))

    def test_picks_numerically_closest(self):
        self.assertEqual(determine_next_line(1000, {1006, 1018, 1036}, None), 1006)

    def test_tie_broken_by_lower_line_number(self):
        """Lines 994 and 1006 both 6 away from 1000. Lower wins."""
        self.assertEqual(determine_next_line(1000, {994, 1006}, None), 994)

    def test_line_data_parameter_is_optional(self):
        """line_data is accepted but unused in the current implementation."""
        self.assertEqual(determine_next_line(1000, {1006}, None), 1006)
        self.assertEqual(determine_next_line(1000, {1006}, {}), 1006)
        self.assertEqual(determine_next_line(1000, {1006}, {"anything": "here"}), 1006)


class AngularDiffTests(unittest.TestCase):
    """_angular_diff_deg must respect the 360° wrap."""

    def test_zero_when_identical(self):
        self.assertEqual(_angular_diff_deg(76.8, 76.8), 0.0)

    def test_small_positive(self):
        self.assertAlmostEqual(_angular_diff_deg(76.8, 78.3), 1.5, places=2)

    def test_wraps_at_360(self):
        """359° and 1° are 2° apart, not 358°."""
        self.assertAlmostEqual(_angular_diff_deg(359.0, 1.0), 2.0, places=2)

    def test_opposite_is_180(self):
        self.assertAlmostEqual(_angular_diff_deg(0.0, 180.0), 180.0, places=2)
        # 4D scenario: 76.8° and 256.8° are exactly opposite
        self.assertAlmostEqual(_angular_diff_deg(76.8, 256.8), 180.0, places=2)


class FlipDirectionTests(unittest.TestCase):
    def test_low_to_high_flips(self):
        self.assertEqual(_flip_direction("low_to_high"), "high_to_low")

    def test_high_to_low_flips(self):
        self.assertEqual(_flip_direction("high_to_low"), "low_to_high")


class AssignDirectionFeatureOffTests(unittest.TestCase):
    """When follow_previous=False (default), behavior is plain alternation
    regardless of prev_direction_deg."""

    def test_alternates_low_to_high(self):
        info = LineDirection(forward_heading_deg=76.8, reciprocal_heading_deg=256.8,
                             prev_direction_deg=None)
        chosen, warning = assign_direction_for_line(info, "low_to_high",
                                                     follow_previous=False)
        self.assertEqual(chosen, "high_to_low")
        self.assertIsNone(warning)

    def test_alternates_high_to_low(self):
        info = LineDirection(76.8, 256.8, None)
        chosen, warning = assign_direction_for_line(info, "high_to_low",
                                                     follow_previous=False)
        self.assertEqual(chosen, "low_to_high")
        self.assertIsNone(warning)

    def test_prev_direction_ignored_when_off(self):
        """Even with prev_direction set, feature OFF means alternate."""
        info = LineDirection(76.8, 256.8, prev_direction_deg=256.8)
        chosen, _ = assign_direction_for_line(info, "low_to_high",
                                               follow_previous=False)
        # Alternation says: was low_to_high -> now high_to_low
        # Direction match would also have said high_to_low (256.8 ~ reciprocal)
        # — but the test point is that the FEATURE didn't drive the choice.
        self.assertEqual(chosen, "high_to_low")


class AssignDirectionFeatureOnTests(unittest.TestCase):
    """The 4D-monitor-survey scenario: follow_previous=True."""

    def test_forward_match_picks_low_to_high(self):
        """Martin Linge line 2431: prev=76.8°, forward=76.8° -> low_to_high."""
        info = LineDirection(forward_heading_deg=76.8, reciprocal_heading_deg=256.8,
                             prev_direction_deg=76.8)
        chosen, warning = assign_direction_for_line(info, "high_to_low",
                                                     follow_previous=True)
        self.assertEqual(chosen, "low_to_high")
        self.assertIsNone(warning, "exact match must produce no warning")

    def test_reverse_match_picks_high_to_low(self):
        """Martin Linge line 2439: prev=256.8°, forward=76.8° -> high_to_low."""
        info = LineDirection(forward_heading_deg=76.8, reciprocal_heading_deg=256.8,
                             prev_direction_deg=256.8)
        chosen, warning = assign_direction_for_line(info, "low_to_high",
                                                     follow_previous=True)
        self.assertEqual(chosen, "high_to_low")
        self.assertIsNone(warning)

    def test_prior_direction_ignored_when_data_present(self):
        """Whatever the prior was, prev_direction wins."""
        info = LineDirection(76.8, 256.8, prev_direction_deg=76.8)
        # Whether prior was high_to_low or low_to_high, result must be low_to_high
        for prior in ("high_to_low", "low_to_high"):
            chosen, _ = assign_direction_for_line(info, prior, follow_previous=True)
            self.assertEqual(chosen, "low_to_high",
                             f"prior_direction={prior!r} should be ignored when "
                             f"follow_previous=True and data is available")

    def test_within_tolerance_no_warning(self):
        """Real-world prev_direction may have tiny noise (e.g. 76.85 vs 76.8)."""
        info = LineDirection(forward_heading_deg=76.8, reciprocal_heading_deg=256.8,
                             prev_direction_deg=76.85)
        chosen, warning = assign_direction_for_line(info, "high_to_low",
                                                     follow_previous=True,
                                                     tolerance_deg=1.0)
        self.assertEqual(chosen, "low_to_high")
        self.assertIsNone(warning)

    def test_outside_tolerance_emits_warning(self):
        """Misalignment >1° still picks the closer heading but warns."""
        info = LineDirection(forward_heading_deg=76.8, reciprocal_heading_deg=256.8,
                             prev_direction_deg=85.0)  # 8.2° from forward
        chosen, warning = assign_direction_for_line(info, "high_to_low",
                                                     follow_previous=True,
                                                     tolerance_deg=1.0)
        self.assertEqual(chosen, "low_to_high")  # still closest
        self.assertIsNotNone(warning)
        self.assertIn("spread", warning.lower())

    def test_no_data_falls_back_to_alternation_with_warning(self):
        """Feature ON but PREV_DIRECTION not in the SPS file."""
        info = LineDirection(76.8, 256.8, prev_direction_deg=None)
        chosen, warning = assign_direction_for_line(info, "low_to_high",
                                                     follow_previous=True)
        self.assertEqual(chosen, "high_to_low",
                         "must fall back to alternation when no data")
        self.assertIsNotNone(warning)
        self.assertIn("PREV_DIRECTION", warning)

    def test_wrap_around_match(self):
        """A line where forward=359° and prev_direction=1° must match forward
        (2° apart via wrap), not reciprocal=179° (178° apart)."""
        info = LineDirection(forward_heading_deg=359.0, reciprocal_heading_deg=179.0,
                             prev_direction_deg=1.0)
        chosen, warning = assign_direction_for_line(info, "high_to_low",
                                                     follow_previous=True,
                                                     tolerance_deg=5.0)
        self.assertEqual(chosen, "low_to_high")
        self.assertIsNone(warning, "2° spread is within 5° tolerance")


if __name__ == "__main__":
    unittest.main(verbosity=2)

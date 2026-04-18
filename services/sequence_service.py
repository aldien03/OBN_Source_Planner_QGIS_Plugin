"""
Acquisition-sequence generation.

Pure Python — no QGIS, no Qt. Phase 5 extracted these four functions
verbatim from obn_planner_dockwidget.py (methods at lines 8449, 8563,
8589, 8619 pre-extraction). Behavior is preserved; Phase 6 will add the
direction-following constraint on top of this module.
"""

from __future__ import annotations
import logging
from collections import Counter
from typing import List, Optional

log = logging.getLogger(__name__)


def calculate_most_common_step(sorted_lines: List[int]) -> int:
    """Most common interval between consecutive line numbers.

    Returns 0 for empty or single-element input. Falls back to the mean
    interval if no value repeats.
    """
    if len(sorted_lines) < 2:
        return 0

    diffs = [sorted_lines[i + 1] - sorted_lines[i] for i in range(len(sorted_lines) - 1)]
    counter = Counter(diffs)
    most_common = counter.most_common(1)

    if most_common and most_common[0][1] > 1:
        return most_common[0][0]

    # No clear dominant step — fall back to average.
    return int(sum(diffs) / len(diffs)) if diffs else 0


def find_closest_line_index(
    sorted_lines: List[int],
    target_line: int,
    current_idx: int,
    ideal_jump: int,
) -> int:
    """Index of the line numerically closest to target_line, searched
    within a small window around current_idx + ideal_jump.

    Returns -1 if the window is empty (shouldn't happen in practice).
    """
    search_range = 5
    min_idx = max(0, current_idx + ideal_jump - search_range)
    max_idx = min(len(sorted_lines) - 1, current_idx + ideal_jump + search_range)

    closest_idx = -1
    min_diff = float("inf")

    for idx in range(min_idx, max_idx + 1):
        diff = abs(sorted_lines[idx] - target_line)
        if diff < min_diff:
            min_diff = diff
            closest_idx = idx

    return closest_idx


def generate_racetrack_sequence(
    sorted_active_lines: List[int],
    first_line_num: int,
    ideal_jump_count: int,
) -> Optional[List[int]]:
    """Interleaved racetrack acquisition order.

    Produces a sequence where lines are visited in paired outward/return
    fashion to minimise vessel turn distance. Example pattern:
        1022 -> 1118 (1022 + 16*6)
        1028 -> 1124
        1034 -> 1130
        ...

    Returns the ordered line list, or None if inputs are unusable.
    """
    if not sorted_active_lines:
        log.error("Cannot generate sequence: no active lines provided.")
        return None

    if ideal_jump_count < 1:
        log.warning(
            f"Ideal jump count ({ideal_jump_count}) < 1. Using 1."
        )
        ideal_jump_count = 1

    n_lines = len(sorted_active_lines)
    line_to_index = {line: idx for idx, line in enumerate(sorted_active_lines)}

    try:
        start_index = line_to_index[first_line_num]
    except KeyError:
        log.warning(
            f"Start line {first_line_num} not in active list. "
            f"Using first available line."
        )
        start_index = 0
        first_line_num = sorted_active_lines[0]

    log.info(
        f"Generating Interleaved Sequence: Start={first_line_num} "
        f"(idx={start_index}), Jump Count={ideal_jump_count}, "
        f"Total Lines={n_lines}"
    )

    line_step = calculate_most_common_step(sorted_active_lines)
    if line_step <= 0:
        line_step = 6
        log.warning(f"Could not detect valid line step. Using default: {line_step}")
    else:
        log.debug(f"Detected common line number step: {line_step}")

    sequence: List[int] = []
    visited_indices: set = set()

    current_line = first_line_num
    current_idx = start_index
    target_jump_line = current_line + ideal_jump_count * line_step

    target_jump_idx = find_closest_line_index(
        sorted_active_lines, target_jump_line, current_idx, ideal_jump_count
    )

    if target_jump_idx == -1:
        target_jump_idx = min(current_idx + ideal_jump_count, n_lines - 1)
        log.warning(
            f"Could not find suitable jump line. "
            f"Using index {target_jump_idx} as fallback."
        )

    outward_idx = current_idx
    return_idx = target_jump_idx

    log.debug(
        f"Starting pair generation: Line1={current_line}(idx={current_idx}), "
        f"TargetJumpLine={target_jump_line}, JumpIdx={target_jump_idx}"
    )

    while len(visited_indices) < n_lines:
        if 0 <= outward_idx < n_lines and outward_idx not in visited_indices:
            sequence.append(sorted_active_lines[outward_idx])
            visited_indices.add(outward_idx)

        if 0 <= return_idx < n_lines and return_idx not in visited_indices:
            sequence.append(sorted_active_lines[return_idx])
            visited_indices.add(return_idx)

        outward_idx += 1
        return_idx += 1

        if outward_idx >= n_lines and return_idx >= n_lines:
            break

    if len(sequence) != n_lines:
        log.warning(
            f"Sequence generation incomplete. Expected {n_lines}, "
            f"got {len(sequence)}. Adding missing lines."
        )
        missed_lines = set(sorted_active_lines) - set(sequence)
        sequence.extend(sorted(missed_lines))

    # Guarantee the user's first_line_num is at the front
    if sequence and sequence[0] != first_line_num:
        try:
            sequence.remove(first_line_num)
        except ValueError:
            pass
        sequence.insert(0, first_line_num)

    log.info(f"Generated Racetrack Sequence (Length: {len(sequence)}): {sequence}")
    return sequence


def determine_next_line(
    current_line_num: int,
    remaining_lines,
    line_data: Optional[dict] = None,
) -> Optional[int]:
    """Teardrop greedy next-line picker.

    Returns the numerically closest line to current_line_num from the
    remaining_lines set. Ties broken by preferring the lower line number
    (for deterministic replay).

    line_data is accepted for API compatibility with the pre-extraction
    method signature but is not used by the current implementation.
    Phase 6 may start using it when the direction-following option is
    enabled.
    """
    if not remaining_lines:
        return None

    closest_line: Optional[int] = None
    min_abs_diff = float("inf")

    for line_num in remaining_lines:
        abs_diff = abs(line_num - current_line_num)
        if abs_diff < min_abs_diff or (abs_diff == min_abs_diff and line_num < closest_line):
            min_abs_diff = abs_diff
            closest_line = line_num

    log.debug(
        f"Next line after {current_line_num}: {closest_line} "
        f"(Difference: {min_abs_diff})"
    )
    return closest_line

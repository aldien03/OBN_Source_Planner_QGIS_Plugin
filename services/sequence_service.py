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
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

log = logging.getLogger(__name__)


# --- Direction-following (Phase 6a) -----------------------------------------
#
# Used by the upcoming "Follow previous shooting direction" feature for 4D
# monitor surveys (UI checkbox added in Phase 8). With the feature OFF
# (default), assign_direction_for_line just alternates the previous direction,
# preserving today's behavior. With the feature ON, it pins each line to the
# direction matching its PREV_DIRECTION value (parsed by Phase 3, aggregated
# per line by Phase 4).

@dataclass(frozen=True)
class LineDirection:
    """Direction-relevant info for a single survey line.

    forward_heading_deg / reciprocal_heading_deg describe the two
    possible vessel headings when shooting this line: forward (low SP
    to high SP) and reciprocal (high SP to low SP). They differ by 180°.

    prev_direction_deg comes from the line's PREV_DIRECTION attribute
    (aggregated from constituent SPS points). None when the source SPS
    file did not carry direction data — in that case the
    "Follow previous shooting direction" feature must fall back to
    plain alternation and warn the caller.
    """
    forward_heading_deg: float
    reciprocal_heading_deg: float
    prev_direction_deg: Optional[float] = None


def _flip_direction(direction: str) -> str:
    """Toggle between the two direction labels used throughout the plugin."""
    return "high_to_low" if direction == "low_to_high" else "low_to_high"


def _angular_diff_deg(a: float, b: float) -> float:
    """Smallest positive angular difference in degrees, accounting for
    the 360° wrap. _angular_diff_deg(359, 1) == 2, not 358."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def assign_direction_for_line(
    line_info: LineDirection,
    prior_direction: str,
    follow_previous: bool = False,
    tolerance_deg: float = 1.0,
) -> Tuple[str, Optional[str]]:
    """Decide the shoot direction for a single line.

    Args:
        line_info: forward/reciprocal headings and optional prev_direction
        prior_direction: "low_to_high" or "high_to_low" — the direction
            the previously-acquired line was shot in. Used only when
            follow_previous is False or no prev_direction data exists.
        follow_previous: when True, pin the line to the direction
            matching its PREV_DIRECTION value (4D monitor scenario).
            When False (default), alternate from prior_direction
            (existing behavior).
        tolerance_deg: how close prev_direction must be to one of the
            two headings before the choice is considered "clean".
            Outside this tolerance, a warning is emitted (caller logs).

    Returns:
        (chosen_direction, warning_or_None) where chosen_direction is
        "low_to_high" or "high_to_low".
    """
    # Default behavior: alternate. Cheap, deterministic, no warning.
    if not follow_previous:
        return _flip_direction(prior_direction), None

    # Feature ON but the source SPS file lacked a direction column.
    # Fall back to alternation and emit a warning so the caller can
    # surface "no direction data — using alternation" to the user.
    if line_info.prev_direction_deg is None:
        return _flip_direction(prior_direction), (
            "follow_previous_direction is enabled but PREV_DIRECTION is "
            "not available for this line — falling back to alternation"
        )

    # Feature ON with data: pick the heading closer to PREV_DIRECTION.
    pd = line_info.prev_direction_deg
    diff_forward = _angular_diff_deg(pd, line_info.forward_heading_deg)
    diff_reverse = _angular_diff_deg(pd, line_info.reciprocal_heading_deg)

    if diff_forward <= diff_reverse:
        chosen = "low_to_high"
        chosen_diff = diff_forward
    else:
        chosen = "high_to_low"
        chosen_diff = diff_reverse

    warning = None
    if chosen_diff > tolerance_deg:
        warning = (
            f"prev_direction={pd:.2f}° matches {chosen} heading with "
            f"{chosen_diff:.2f}° spread (> {tolerance_deg:.1f}° tolerance) — "
            f"choosing it anyway, but check whether PREV_DIRECTION matches "
            f"the survey's actual orientation"
        )
    return chosen, warning


def build_direction_override_for_sequence(
    sequence: List[int],
    line_data: dict,
    follow_previous: bool = True,
    tolerance_deg: float = 1.0,
) -> Tuple[dict, List[str]]:
    """For each line in `sequence`, compute the chosen direction based on
    its prev_direction (from line_data) and return a {line_num: direction}
    dict suitable for passing to _calculate_sequence_time(direction_override=...).

    Args:
        sequence: ordered list of line numbers
        line_data: dict {line_num: {'base_heading': float, 'prev_direction': float|None, ...}}
        follow_previous: if False, returns an empty override dict (callers
            should then pass None to _calculate_sequence_time, which keeps
            legacy alternation)
        tolerance_deg: passed to assign_direction_for_line for warning emission

    Returns:
        (override_dict, warnings_list).
        - override_dict maps each line_num to 'low_to_high' or 'high_to_low'
          when follow_previous is True. The PRIOR direction passed to
          assign_direction_for_line is each line's previous line's chosen
          direction (so even fallback-to-alternation cascades correctly).
        - warnings_list collects the per-line warning strings (caller logs).

    When follow_previous is False, returns ({}, []).
    """
    if not follow_previous or not sequence:
        return {}, []

    override: dict = {}
    warnings: List[str] = []
    # Seed prior direction with 'high_to_low' so that for the first line the
    # alternation fallback (if no prev_direction available) produces
    # 'low_to_high' — matching the legacy default start direction.
    prior = "high_to_low"

    for line_num in sequence:
        info_dict = line_data.get(line_num)
        if not info_dict:
            warnings.append(f"line {line_num}: no line_data entry, skipping direction override")
            continue
        base = info_dict.get("base_heading")
        if base is None:
            warnings.append(f"line {line_num}: no base_heading, skipping direction override")
            continue
        prev_dir = info_dict.get("prev_direction")
        line_info = LineDirection(
            forward_heading_deg=float(base),
            reciprocal_heading_deg=(float(base) + 180.0) % 360.0,
            prev_direction_deg=(float(prev_dir) if prev_dir is not None else None),
        )
        chosen, warning = assign_direction_for_line(
            line_info, prior_direction=prior, follow_previous=True,
            tolerance_deg=tolerance_deg,
        )
        override[line_num] = chosen
        if warning:
            warnings.append(f"line {line_num}: {warning}")
        prior = chosen

    return override, warnings


# --- Sequence generation (Phase 5) ------------------------------------------


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


# --- 2-opt local-search optimization (Phase 11a) ----------------------------
#
# Classic 2-opt for open-path sequences: iteratively picks two non-adjacent
# "edges" in the sequence, reverses the subsequence between them, and keeps
# the move if total cost drops. Stops when a full pass finds no improvement
# or when max_iterations is exceeded.
#
# Usage:
#
#     from services.sequence_service import optimize_sequence_2opt
#
#     def cost_fn(seq):
#         return my_simulator.compute_cost(seq)
#
#     result = optimize_sequence_2opt(
#         sequence=[1000, 1006, 1012, 1018, 1024],
#         cost_fn=cost_fn,
#         max_iterations=200,
#     )
#     print(result.optimized_sequence, result.improvement_pct)
#
# The cost_fn is called many times. The caller is responsible for ensuring
# cost_fn is deterministic given the sequence (no hidden state that depends
# on call order) and isolated (no side effects that persist between calls
# — e.g. if the caller uses a shared turn cache, it must either be safe to
# reuse or be passed as a disposable cache per call).

_TWO_OPT_COST_EPSILON = 1e-9  # strict-improvement threshold, no jitter


@dataclass(frozen=True)
class TwoOptProgress:
    """Phase 11d-1: progress report emitted after each 2-opt pass.

    Passed to the progress_callback param of optimize_sequence_2opt
    so GUI callers can update a progress dialog and keep the event
    loop alive without the optimizer itself knowing about Qt.

    Fields mirror a subset of OptimizationResult so the callback
    can compute improvement_pct on the fly for display.
    """
    pass_num: int               # 1-indexed current pass
    max_iterations: int         # the cap the caller configured
    total_improvements: int     # swaps accepted so far
    cost_evaluations: int       # cost_fn calls so far (approximate)
    original_cost: float
    best_cost: float            # best cost seen so far


@dataclass(frozen=True)
class OptimizationResult:
    """Outcome of a sequence-optimization pass.

    Fields:
        optimized_sequence: the best sequence found. Same length as input.
        original_cost: cost_fn(input_sequence) at call time.
        final_cost: cost_fn(optimized_sequence).
        improvement_pct: (original - final) / original * 100, or 0.0 if
            original was 0 or not computable.
        total_passes: how many full passes the outer loop performed.
            One pass runs through every (i, j) swap candidate.
        total_improvements: number of strict-improvement swaps accepted.
        cost_evaluations: total calls to cost_fn (excluding the initial
            baseline evaluation of the input sequence).
        stopped_reason: 'converged' (full pass with no improvement),
            'max_iterations' (cap hit), 'trivial' (input too short
            to admit any 2-opt move — length < 4), or 'cancelled'
            (Phase 11d-1: caller requested abort via cancel_fn).
    """
    optimized_sequence: List[int]
    original_cost: float
    final_cost: float
    improvement_pct: float
    total_passes: int
    total_improvements: int
    cost_evaluations: int
    stopped_reason: str


def optimize_sequence_2opt(
    sequence: List[int],
    cost_fn: Callable[[List[int]], float],
    max_iterations: int = 200,
    progress_callback: Optional[Callable[["TwoOptProgress"], None]] = None,
    cancel_fn: Optional[Callable[[], bool]] = None,
) -> OptimizationResult:
    """Classic 2-opt local search on an open-path sequence.

    Pure Python. Deterministic given the inputs — no randomness. Visits
    every (i, j) pair in (row-major, i<j) order every pass.

    Args:
        sequence: ordered list of integers (line numbers). Must contain
            at least 2 entries. Shorter inputs are returned unchanged
            with stopped_reason='trivial' and zero improvement.
        cost_fn: callable (sequence) -> float. Must be deterministic
            per call and safe to invoke many times.
            If cost_fn raises, the exception propagates — the caller
            is responsible for handling bad inputs (e.g. infeasible
            sequences). The optimizer never treats an exception as a
            "worse" score.
        max_iterations: maximum outer passes before giving up. Each
            pass examines every candidate swap. Default 200.
        progress_callback: Phase 11d-1. If provided, called AFTER each
            full pass with a TwoOptProgress snapshot. The optimizer
            never raises from a callback invocation — if the callback
            raises, the exception propagates to the caller (which is
            expected to handle GUI errors gracefully).
        cancel_fn: Phase 11d-1. If provided, called BEFORE each full
            pass. Returning True aborts the loop; the optimizer
            returns with stopped_reason='cancelled' and the best
            sequence found so far.

    Returns:
        OptimizationResult. optimized_sequence is guaranteed to be
        a new list (not the caller's), length equal to input.
    """
    # Sequences of length 3 or fewer admit no non-trivial 2-opt moves
    # (i < j with the reversed subsequence between them changing the
    # sequence requires j >= i+2 and at least one element between them).
    n = len(sequence)
    best = list(sequence)
    if n < 4:
        original_cost = cost_fn(best) if n > 0 else 0.0
        return OptimizationResult(
            optimized_sequence=best,
            original_cost=original_cost,
            final_cost=original_cost,
            improvement_pct=0.0,
            total_passes=0,
            total_improvements=0,
            cost_evaluations=1 if n > 0 else 0,
            stopped_reason="trivial",
        )

    original_cost = cost_fn(best)
    best_cost = original_cost
    cost_evaluations = 1

    total_passes = 0
    total_improvements = 0
    stopped_reason = "converged"

    log.debug(
        f"2-opt start: n={n} max_iterations={max_iterations} "
        f"original_cost={original_cost:.3f}"
    )

    while total_passes < max_iterations:
        # Phase 11d-1: honor caller cancellation BEFORE starting a new
        # pass. Abort cleanly; best-so-far has already been captured.
        if cancel_fn is not None and cancel_fn():
            stopped_reason = "cancelled"
            break

        total_passes += 1
        # "Best-improvement" 2-opt: scan every (i, j) pair in the current
        # sequence, compute the cost of each candidate reversal, and apply
        # the SINGLE best improving swap (if any) at the end of the pass.
        # This is the canonical 2-opt formulation — it avoids the "stuck
        # in a mediocre local minimum" failure mode of first-improvement,
        # at the cost of always scanning every pair per pass.
        best_swap = None  # (new_candidate, new_cost)

        for i in range(n - 1):
            # j must be at least i+2 for the reversal to actually change
            # the sequence. j=i+1 would reverse a single element (no-op).
            for j in range(i + 2, n):
                # Reverse the subsequence from index i+1 to j inclusive.
                # Before: best[0..i] + best[i+1..j] + best[j+1..n-1]
                # After:  best[0..i] + reversed(best[i+1..j]) + best[j+1..n-1]
                candidate = best[: i + 1] + best[i + 1 : j + 1][::-1] + best[j + 1 :]
                candidate_cost = cost_fn(candidate)
                cost_evaluations += 1
                if candidate_cost < best_cost - _TWO_OPT_COST_EPSILON:
                    if best_swap is None or candidate_cost < best_swap[1]:
                        best_swap = (candidate, candidate_cost)

        if best_swap is not None:
            best, best_cost = best_swap
            total_improvements += 1

        # Phase 11d-1: notify caller of progress after each pass (whether
        # improvement found or not). Caller can update a progress dialog
        # and pump events to keep the GUI responsive.
        if progress_callback is not None:
            progress_callback(TwoOptProgress(
                pass_num=total_passes,
                max_iterations=max_iterations,
                total_improvements=total_improvements,
                cost_evaluations=cost_evaluations,
                original_cost=original_cost,
                best_cost=best_cost,
            ))

        if best_swap is None:
            # Full pass with no improvement — we're at a local minimum.
            stopped_reason = "converged"
            break
    else:
        # while-loop fell through — hit max_iterations without converging
        stopped_reason = "max_iterations"

    if original_cost > 0:
        improvement_pct = (original_cost - best_cost) / original_cost * 100.0
    else:
        improvement_pct = 0.0

    log.info(
        f"2-opt done: passes={total_passes} improvements={total_improvements} "
        f"evals={cost_evaluations} cost {original_cost:.3f} -> {best_cost:.3f} "
        f"({improvement_pct:+.2f}%) stop={stopped_reason}"
    )

    return OptimizationResult(
        optimized_sequence=best,
        original_cost=original_cost,
        final_cost=best_cost,
        improvement_pct=improvement_pct,
        total_passes=total_passes,
        total_improvements=total_improvements,
        cost_evaluations=cost_evaluations,
        stopped_reason=stopped_reason,
    )

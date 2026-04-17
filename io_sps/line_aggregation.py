"""
Per-line aggregation of per-point PREV_DIRECTION values.

Pure Python, no QGIS dependency. Used during handle_generate_lines to
collapse multiple shot-point direction readings into one direction value
attached to the generated survey line.

Assumption (user-confirmed 2026-04-17): all shot points on a given line
share the same prev_direction value. Real-world files may contain minor
jitter (sub-degree). This module accepts that, picks the mode, and
emits a warning string for logging if values are non-uniform.
"""

from collections import Counter
from typing import List, Optional, Tuple


def aggregate_line_direction(
    directions: List[Optional[float]],
    tolerance_deg: float = 0.1,
    round_digits: int = 1,
) -> Tuple[Optional[float], Optional[str]]:
    """Collapse per-point direction values into one per-line value.

    Args:
        directions: per-point direction readings in degrees. Any None
            entries are ignored (e.g. points from an SPS format without
            a direction column).
        tolerance_deg: values within this spread of each other are
            treated as uniform (no warning emitted). Default 0.1°.
        round_digits: when non-uniform, values are rounded to this many
            digits for mode-counting. Default 1 (0.1° buckets).

    Returns:
        (aggregated_direction, warning_message).

        - All inputs None (e.g. old SPS file without direction column):
            (None, None) — nothing to store, no problem to report.
        - All non-None inputs within tolerance:
            (mean_of_inputs, None)
        - Non-None inputs with wider spread (bad real-world data):
            (mode_value, warning_string) — caller should log the warning
            and proceed with the mode value.

    The caller decides what to do with the warning (typically log.warning).
    This function never raises and never logs directly.
    """
    non_null = [d for d in directions if d is not None]
    if not non_null:
        return None, None

    spread = max(non_null) - min(non_null)
    if spread <= tolerance_deg:
        # Uniform enough — return the mean.
        return sum(non_null) / len(non_null), None

    # Non-uniform: find the mode (rounded) and build a diagnostic warning.
    bucketed = [round(d, round_digits) for d in non_null]
    counts = Counter(bucketed)
    mode_value, _ = counts.most_common(1)[0]
    warning = (
        f"non-uniform prev_direction across {len(non_null)} point(s), "
        f"spread={spread:.2f}°, distribution={dict(counts)} — "
        f"using mode {mode_value}°"
    )
    return mode_value, warning

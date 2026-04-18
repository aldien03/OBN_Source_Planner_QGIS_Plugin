"""
Line metadata — Operation / FGSP / LGSP per survey line.

Pure Python, no QGIS/Qt. Phase 16a introduces this module as the
single source of truth for the three new per-line attributes that
feed the daily 48-hour shooting plan PDF (Phase 17) and the
simulation's partial-range acquisition (Phase 16c).

Semantics (direction-aware):
- Operation: one of Production / Test / Reshoot / Infill. String
  values match the reference shooting-plan PDF exactly — the PDF
  template reads these strings directly, so renaming breaks Phase 17.
- FGSP: First Good Shot Point — the SP where acquisition STARTS.
- LGSP: Last Good Shot Point — the SP where acquisition STOPS.

FGSP and LGSP both lie in [lowest_sp, highest_sp] and must differ,
but FGSP > LGSP is legal and signals reverse-direction traversal
(vessel enters at the higher SP, exits at the lower).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LineOperation(str, Enum):
    PRODUCTION = "Production"
    TEST = "Test"
    RESHOOT = "Reshoot"
    INFILL = "Infill"

    @classmethod
    def from_str(cls, value):
        if isinstance(value, cls):
            return value
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown LineOperation: {value!r}")


DEFAULT_OPERATION: LineOperation = LineOperation.PRODUCTION


@dataclass(frozen=True)
class LineMetadata:
    line_num: int
    operation: LineOperation
    fgsp: int
    lgsp: int

    def is_full_range(self, lowest_sp: int, highest_sp: int) -> bool:
        return {self.fgsp, self.lgsp} == {lowest_sp, highest_sp}

    def is_reverse_direction(self) -> bool:
        return self.fgsp > self.lgsp

    def validate(self, lowest_sp: int, highest_sp: int) -> None:
        if lowest_sp > highest_sp:
            raise ValueError(
                f"lowest_sp ({lowest_sp}) must be <= highest_sp ({highest_sp})"
            )
        if not (lowest_sp <= self.fgsp <= highest_sp):
            raise ValueError(
                f"FGSP {self.fgsp} out of range [{lowest_sp}, {highest_sp}]"
            )
        if not (lowest_sp <= self.lgsp <= highest_sp):
            raise ValueError(
                f"LGSP {self.lgsp} out of range [{lowest_sp}, {highest_sp}]"
            )
        if self.fgsp == self.lgsp:
            raise ValueError(f"FGSP and LGSP must differ (got {self.fgsp})")


def contiguous_runs(points, predicate):
    """Phase 16d: split SP-sorted points into contiguous runs matching a predicate.

    Input:
      points: iterable of items in SP order (any item type). Callers are
              responsible for sorting by SP first.
      predicate: callable(item) -> bool. True items participate in runs.

    Output:
      list of lists — each inner list is a maximal run of predicate-True
      items that were adjacent in the input order. Predicate-False items
      end the current run.

    Notes:
      - Adjacency is in input order, not SP-number distance. If SP numbers
        skip (3500 → 3503 with no 3501/3502 in the layer), the run does
        NOT break — the chief cares about the sorted-list contiguity, not
        integer neighbors. This matches the UI segment picker semantics.
      - Empty input → empty list. All-False input → empty list.
      - Single-point runs are emitted; call sites may choose to reject them.
    """
    runs = []
    current = []
    for item in points:
        if predicate(item):
            current.append(item)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def format_sub_line_label(line_num, fgsp, lgsp, full_min, full_max):
    """Phase 16d: human-readable label for a generated (sub-)line.

    - Full-range sub-line on a single-run parent line → "2146"
    - Partial-range OR multi-run parent line → "2146 (1101-1500)"

    Arguments are ints. Returns the string for the Label attribute and
    the Sequence Editor's Line column.
    """
    if full_min is not None and full_max is not None and fgsp == full_min and lgsp == full_max:
        return str(line_num)
    return f"{line_num} ({fgsp}-{lgsp})"

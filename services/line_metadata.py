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

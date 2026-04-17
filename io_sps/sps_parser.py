"""
SPS file parser — pure Python, no QGIS dependency.

Primary entry points:
    parse_sps(path, spec=None) -> ParseResult
    detect_spec(path) -> (SpsColumnSpec, confidence)

The parser is defensive: encoding errors, truncated lines, and unparseable
fields are collected into the errors list rather than raising. Only file
I/O errors propagate.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from .sps_spec import SpsColumnSpec, SPS_SPECS, SPS_2_1


@dataclass(frozen=True)
class SpsRecord:
    """One parsed data row from an SPS file."""
    line_num: int
    sp: int
    easting: float
    northing: float
    depth: Optional[float] = None
    direction: Optional[float] = None      # None if the spec has no direction col
    source_code: Optional[str] = None

    def to_legacy_dict(self) -> dict:
        """Legacy dict shape expected by dockwidget callers (line/sp/e/n)."""
        d = {"line": self.line_num, "sp": self.sp,
             "e": self.easting, "n": self.northing}
        if self.direction is not None:
            d["prev_direction"] = self.direction
        if self.depth is not None:
            d["depth"] = self.depth
        if self.source_code is not None:
            d["source_code"] = self.source_code
        return d


@dataclass(frozen=True)
class ParseResult:
    records: list
    errors: list
    spec_used: SpsColumnSpec
    detection_confidence: float   # 1.0 if user-supplied spec, else 0..1 from detect


# --- Internal helpers ----------------------------------------------------

def _is_header(line: str, spec: SpsColumnSpec) -> bool:
    return bool(spec.header_markers) and line[:1] in spec.header_markers


def _is_record(line: str, spec: SpsColumnSpec) -> bool:
    return bool(spec.record_markers) and line[:1] in spec.record_markers


def _parse_record(line: str, spec: SpsColumnSpec) -> SpsRecord:
    """Parse one line into an SpsRecord. Raises ValueError on bad data."""
    return SpsRecord(
        line_num=spec.id_parser(line[spec.line_num]),
        sp=spec.id_parser(line[spec.sp]),
        easting=float(line[spec.easting].strip()),
        northing=float(line[spec.northing].strip()),
        depth=float(line[spec.depth].strip()) if spec.depth else None,
        direction=float(line[spec.direction].strip()) if spec.direction else None,
        source_code=line[spec.source_code].strip() if spec.source_code else None,
    )


# --- Public API ----------------------------------------------------------

def parse_sps(path: Union[str, Path], spec: Optional[SpsColumnSpec] = None) -> ParseResult:
    """Parse an SPS file using the given spec (or auto-detect if None).

    Returns ParseResult(records, errors, spec_used, detection_confidence).
    Does NOT raise on per-line parse errors — those go into `errors`.
    File-I/O errors (FileNotFoundError, UnicodeDecodeError for encoding
    mismatch) propagate.
    """
    if spec is None:
        spec, confidence = detect_spec(path)
    else:
        confidence = 1.0

    records = []
    errors = []
    with open(path, "r", encoding=spec.encoding) as f:
        for idx, raw in enumerate(f, start=1):
            line = raw.rstrip("\r\n")
            if not line:
                continue
            if _is_header(line, spec):
                continue
            if not _is_record(line, spec):
                # Unknown line kind (e.g. 'R' receiver record in some SPS
                # files) — silently skip; not our concern in this plugin.
                continue
            if len(line) < spec.min_length:
                errors.append(f"Line {idx}: too short ({len(line)} < {spec.min_length})")
                continue
            try:
                records.append(_parse_record(line, spec))
            except (ValueError, IndexError) as e:
                # Truncate the offending line in the error message so logs
                # don't explode on pathological inputs.
                errors.append(f"Line {idx}: {e} — '{line[:80]}...'")
    return ParseResult(records=records, errors=errors,
                       spec_used=spec, detection_confidence=confidence)


def detect_spec(path: Union[str, Path], max_sample_lines: int = 500,
                default: SpsColumnSpec = SPS_2_1) -> tuple:
    """Try each spec in SPS_SPECS; return (best_spec, confidence).

    Confidence = fraction of attempted S-records that parsed cleanly with
    that spec. In case of a tie, the first spec in SPS_SPECS wins (registry
    order is chosen to put more-specific specs first — see sps_spec.py).

    Returns (default, 0.0) if no spec achieves any successful parses.
    """
    best = default
    best_ratio = 0.0

    for spec in SPS_SPECS.values():
        ratio = _trial_parse_ratio(path, spec, max_sample_lines)
        # Strictly greater → first match wins on ties (registry order).
        if ratio > best_ratio:
            best_ratio = ratio
            best = spec

    return best, best_ratio


def _trial_parse_ratio(path: Union[str, Path], spec: SpsColumnSpec,
                       max_lines: int) -> float:
    """Return fraction of data lines cleanly parsed by the given spec.

    Also requires the line to be >= spec.min_length. A spec that expects a
    longer line than the file provides will score 0 even if the slices
    happen to hit numeric fields.
    """
    attempted = 0
    succeeded = 0
    try:
        with open(path, "r", encoding=spec.encoding) as f:
            for idx, raw in enumerate(f):
                if idx >= max_lines:
                    break
                line = raw.rstrip("\r\n")
                if not line or _is_header(line, spec) or not _is_record(line, spec):
                    continue
                attempted += 1
                if len(line) < spec.min_length:
                    continue
                try:
                    _parse_record(line, spec)
                    succeeded += 1
                except (ValueError, IndexError):
                    pass
    except (UnicodeDecodeError, FileNotFoundError):
        return 0.0

    if attempted == 0:
        return 0.0
    return succeeded / attempted

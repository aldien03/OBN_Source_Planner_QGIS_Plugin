# Phase 3 — SPS multi-format infrastructure

**Size:** medium/large
**Risk:** medium (touches the primary data-ingestion path)
**Blocks:** Phase 4 (direction parsing builds on this), Phase 8 (UI format selector needs the registry)
**Blocked by:** Phase 0 (baseline tests)

## Goal

Make SPS parsing robust to real-world format variation. Ship with a spec registry covering the formats the user actually receives, detect the format automatically when possible, let the user override when not. Fix the real-file bug that makes the current parser fail on `D1v1_MartinLindge_260410_sailline.sps`.

**This phase adds NO new user-visible feature.** Phase 4 adds the direction column; Phase 8 adds the UI selector. This phase ships robustness only.

## Evidence: current parser is broken on real files

Verified by reading `D1v1_MartinLindge_260410_sailline.sps` lines 85-87 and comparing to `obn_planner_dockwidget.py:577-588`:

| File | `line[7:12]` (current parser) | `line[5:11]` (correct) | `int(...)` on current slice |
|---|---|---|---|
| Martin Linge | `"31.0 "` — garbage | `"2431.0"` | fails — `int("31.0 ")` → `ValueError` |
| PXGEO (MT3007924) | `"1006 "` — half-correct | `"    1006"` (wider slice also valid) | works by accident |

`int()` also fails on Martin Linge's decimal line numbers (`"2431.0"`). Current parser catches the `ValueError` in a broad `except` at `:599` and logs an error per line — so the user sees every data line in their real SPS file rejected with a parse error.

## Spec registry

### `io/sps_spec.py` (new)

```python
from dataclasses import dataclass, field
from typing import Callable, Optional

def _parse_numeric_id(s: str) -> int:
    """Handle both '1006' (PXGEO) and '2431.0' (Martin Linge). int-or-float-or-int."""
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        return int(float(s))

@dataclass(frozen=True)
class SpsColumnSpec:
    name: str
    description: str
    line_num: slice
    sp: slice
    easting: slice
    northing: slice
    depth: Optional[slice] = None
    direction: Optional[slice] = None      # added in Phase 4 for direction feature
    source_code: Optional[slice] = None
    min_length: int = 65
    encoding: str = "latin-1"
    header_markers: tuple[str, ...] = ("H",)   # lines starting with these are headers
    record_markers: tuple[str, ...] = ("S",)   # lines starting with these are data
    id_parser: Callable[[str], int] = _parse_numeric_id

# Known specs
SPS_2_1_SHELL = SpsColumnSpec(
    name="SPS 2.1 (Shell reference)",
    description="Canonical SPS 2.1 per Shell-published specification. VERIFY slices against official doc.",
    line_num=slice(1, 11),     # positions 2-11, right-justified 10 chars
    sp=slice(11, 21),          # positions 12-21, 10 chars
    easting=slice(46, 56),
    northing=slice(56, 66),
    depth=slice(66, 72),
    source_code=slice(23, 26),
    min_length=65,
)

SPS_2_1_MARTIN_LINGE = SpsColumnSpec(
    name="SPS 2.1 + direction (Martin Linge)",
    description="Vendor-extended SPS 2.1 with direction column at positions 81-86",
    line_num=slice(5, 11),
    sp=slice(15, 21),
    easting=slice(48, 56),
    northing=slice(57, 66),
    depth=slice(67, 72),
    source_code=slice(23, 26),
    direction=slice(80, 86),       # used in Phase 4
    min_length=86,
)

SPS_2_1_PXGEO = SpsColumnSpec(
    name="PXGEO (.s01)",
    description="PXGEO headerless SPS. Integer line/SP. Verified against MT3007924_MMBC_SRC_20250316_combined_saillines.s01.",
    line_num=slice(7, 11),
    sp=slice(17, 21),
    easting=slice(48, 56),
    northing=slice(57, 66),
    depth=slice(67, 72),
    source_code=slice(23, 26),
    min_length=72,
    header_markers=(),             # PXGEO file starts directly with S records
)

SPS_1_0 = SpsColumnSpec(
    name="SPS 1.0 (legacy)",
    description="Original SEG SPS 1.0 format. VERIFY column positions.",
    line_num=slice(1, 5),
    sp=slice(21, 25),
    easting=slice(48, 56),
    northing=slice(57, 65),
    min_length=65,
)

SPS_TGS_VALHALL = SpsColumnSpec(
    name="TGS (.s01)",
    description="TGS variant. VERIFY against Production_SX_Preplot_Valhall_1.1.s01 — sample not yet read by planner.",
    line_num=slice(1, 11),         # placeholder — to be verified during Phase 3 execution
    sp=slice(11, 21),
    easting=slice(46, 56),
    northing=slice(56, 66),
    min_length=65,
)

SPS_SAE_HEIMDAL = SpsColumnSpec(
    name="SAE",
    description="SAE variant. VERIFY against Norway_TGS_HeimdalOBN_*.sps — sample not yet read by planner.",
    line_num=slice(1, 11),         # placeholder
    sp=slice(11, 21),
    easting=slice(46, 56),
    northing=slice(56, 66),
    min_length=65,
)

SPS_SPECS: dict[str, SpsColumnSpec] = {
    SPS_2_1_SHELL.name:       SPS_2_1_SHELL,
    SPS_2_1_MARTIN_LINGE.name: SPS_2_1_MARTIN_LINGE,
    SPS_2_1_PXGEO.name:       SPS_2_1_PXGEO,
    SPS_TGS_VALHALL.name:     SPS_TGS_VALHALL,
    SPS_SAE_HEIMDAL.name:     SPS_SAE_HEIMDAL,
    SPS_1_0.name:             SPS_1_0,
}
```

**Critical note on `VERIFY` markers:** Phase 3 execution MUST start by reading a line-ruler and 2-3 data lines from each real sample file (`Production_SX_Preplot_Valhall_1.1.s01`, `Norway_TGS_HeimdalOBN_*.sps`) before confirming the SPS_TGS / SPS_SAE slices. The placeholder slices above must not be shipped unverified.

## Parser module

### `io/sps_parser.py` (new)

```python
from __future__ import annotations
from pathlib import Path
from typing import Iterable
from dataclasses import dataclass
from .sps_spec import SpsColumnSpec, SPS_SPECS, SPS_2_1_MARTIN_LINGE

@dataclass(frozen=True)
class SpsRecord:
    line_num: int
    sp: int
    easting: float
    northing: float
    depth: float | None = None
    direction: float | None = None
    source_code: str | None = None

@dataclass(frozen=True)
class ParseResult:
    records: list[SpsRecord]
    errors: list[str]
    spec_used: SpsColumnSpec
    detection_confidence: float  # 1.0 if user-selected, 0-1 if auto-detected

def parse_sps(path: str | Path, spec: SpsColumnSpec | None = None) -> ParseResult:
    """Parse an SPS file. If spec is None, auto-detect from known specs."""
    if spec is None:
        spec, confidence = detect_spec(path)
    else:
        confidence = 1.0
    records = []
    errors = []
    with open(path, "r", encoding=spec.encoding) as f:
        for idx, raw in enumerate(f, start=1):
            line = raw.rstrip("\n").rstrip("\r")
            if not line:
                continue
            if _is_header(line, spec):
                continue
            if not _is_record(line, spec):
                continue
            if len(line) < spec.min_length:
                errors.append(f"Line {idx}: too short ({len(line)} < {spec.min_length})")
                continue
            try:
                rec = SpsRecord(
                    line_num = spec.id_parser(line[spec.line_num]),
                    sp       = spec.id_parser(line[spec.sp]),
                    easting  = float(line[spec.easting].strip()),
                    northing = float(line[spec.northing].strip()),
                    depth    = float(line[spec.depth].strip()) if spec.depth else None,
                    direction= float(line[spec.direction].strip()) if spec.direction else None,
                    source_code = line[spec.source_code].strip() if spec.source_code else None,
                )
            except (ValueError, IndexError) as e:
                errors.append(f"Line {idx}: {e}")
                continue
            records.append(rec)
    return ParseResult(records=records, errors=errors, spec_used=spec, detection_confidence=confidence)

def _is_header(line: str, spec: SpsColumnSpec) -> bool:
    return bool(spec.header_markers) and line[:1] in spec.header_markers

def _is_record(line: str, spec: SpsColumnSpec) -> bool:
    return line[:1] in spec.record_markers

def detect_spec(path: str | Path, max_sample_lines: int = 500) -> tuple[SpsColumnSpec, float]:
    """Probe each known spec; pick the one with the highest clean-parse ratio.
    Returns (best_spec, confidence). Confidence = clean_lines / attempted_lines."""
    best_spec = SPS_2_1_MARTIN_LINGE
    best_ratio = 0.0
    for spec in SPS_SPECS.values():
        ratio = _trial_parse_ratio(path, spec, max_sample_lines)
        if ratio > best_ratio:
            best_ratio = ratio
            best_spec = spec
    return best_spec, best_ratio

def _trial_parse_ratio(path: str | Path, spec: SpsColumnSpec, max_lines: int) -> float:
    """Attempt to parse up to max_lines. Return fraction cleanly parsed."""
    attempted = 0
    succeeded = 0
    try:
        with open(path, "r", encoding=spec.encoding) as f:
            for idx, raw in enumerate(f):
                if idx >= max_lines:
                    break
                line = raw.rstrip()
                if not line or _is_header(line, spec):
                    continue
                if not _is_record(line, spec):
                    continue
                attempted += 1
                if len(line) < spec.min_length:
                    continue
                try:
                    spec.id_parser(line[spec.line_num])
                    spec.id_parser(line[spec.sp])
                    float(line[spec.easting].strip())
                    float(line[spec.northing].strip())
                    succeeded += 1
                except (ValueError, IndexError):
                    pass
    except (UnicodeDecodeError, FileNotFoundError):
        return 0.0
    if attempted == 0:
        return 0.0
    return succeeded / attempted
```

## Dockwidget changes

### `obn_planner_dockwidget.py:538-604` (`_parse_sps_file_content`)

Replace body:

```python
def _parse_sps_file_content(self, sps_file_path, skip_headers=0):
    """Legacy wrapper. skip_headers is ignored (spec-driven now).
    Returns (list of dicts, list of errors) for legacy caller compat."""
    from .io.sps_parser import parse_sps
    # Later, when UI selector exists (Phase 8), pull chosen spec from UI.
    # For now, auto-detect.
    result = parse_sps(sps_file_path, spec=None)
    log.info(f"SPS parse: spec={result.spec_used.name}, confidence={result.detection_confidence:.0%}, "
             f"records={len(result.records)}, errors={len(result.errors)}")
    # Convert to legacy dict format (Phase 8 migrates callers to SpsRecord)
    legacy_records = [
        {"line": r.line_num, "sp": r.sp, "e": r.easting, "n": r.northing}
        for r in result.records
    ]
    return legacy_records, result.errors
```

The `skip_headers` parameter becomes inert — header detection is now done via `spec.header_markers`. Document this in the docstring. Phase 8 removes the parameter entirely when the UI stops passing it.

## GeoPackage writer extract

### `io/gpkg_writer.py` (new)

Move as free functions:
- `get_output_geopackage_path(parent_widget, default_dir)` from `obn_planner_dockwidget.py:606-`
- `create_sps_layer_fields()` from `:635-` — add optional `prev_direction` field (unused this phase, wired in Phase 4)
- `write_features_to_layer(writer, records, fields)`
- `load_created_layer(iface, path)`

## Tests

### `test/test_sps_parser.py` (new, pure Python)

```
test_parse_martin_linge_minimal        - uses fixtures/sample_martin_linge.sps (5 lines extracted from real file)
test_parse_pxgeo_headerless            - uses fixtures/sample_pxgeo.s01 (5 lines)
test_parse_short_line_reports_error    - truncated line, non-fatal
test_parse_empty_file                  - 0 records, 0 errors
test_numeric_id_parser_handles_both    - _parse_numeric_id("1006") → 1006, ("2431.0") → 2431
test_detect_spec_martin_linge          - detect_spec on Martin Linge fixture returns SPS_2_1_MARTIN_LINGE
test_detect_spec_pxgeo                 - detect_spec on PXGEO fixture returns SPS_2_1_PXGEO
test_detect_spec_ambiguous             - file parseable by two specs → returns the one with higher clean-parse ratio
test_spec_with_direction_column        - Martin Linge direction field parsed as float (used in Phase 4 test too)
```

### Fixtures

- `test/fixtures/sample_martin_linge.sps` — 5 data lines extracted verbatim from real file + the H00/H26 ruler headers (about 90 lines total — small enough for git)
- `test/fixtures/sample_pxgeo.s01` — 5 headerless `S` records
- `test/fixtures/sample_short_lines.sps` — 2 valid, 1 truncated, 1 valid

Fixture extraction script (run once, output committed): `scripts/extract_fixtures.py` that takes a real file path and writes a 5-record sample to `test/fixtures/`. Do not commit real files — they're large and may contain proprietary coordinates.

## Verify

1. `pytest test/test_sps_parser.py` — all tests green.
2. **Real-file smoke test in QGIS:** import `D1v1_MartinLindge_260410_sailline.sps`. Check log for spec-detection line. Expect: `spec=SPS 2.1 + direction (Martin Linge)`, `confidence≈100%`, many thousands of records, zero errors. This is the primary regression fix for Phase 3.
3. Import the PXGEO file `MT3007924_MMBC_SRC_20250316_combined_saillines.s01`. Expect: `spec=PXGEO (.s01)`, ~65000 records, 0 errors.
4. Attempt import of a hand-crafted bad file (random bytes). Expect: 0 records, error log explains why detection failed.
5. `grep _parse_sps_file_content` — only the thin wrapper remains in the dockwidget.

## VERIFY actions for executor (before shipping)

- [ ] Read `Production_SX_Preplot_Valhall_1.1.s01` first 100 lines; confirm SPS_TGS_VALHALL slices match; update if wrong.
- [ ] Read `Norway_TGS_HeimdalOBN_Opt3v3_Ditherv3_Pull_Push.sps` first 100 lines; confirm SPS_SAE_HEIMDAL slices; update if wrong.
- [ ] Find the Shell SPS 2.1 spec document and confirm SPS_2_1_SHELL slices. If unavailable, note "pending Shell spec verification" and leave the slices as best-effort.
- [ ] Confirm the `source_code` slice `[23:26]` matches what the current dockwidget uses for the `A1`/`A2` alternating-source code visible in `D1v1_MartinLindge_260410_sailline.sps:87-88`.

## Rollback

Single `git revert` of the phase commit. The `io/` subdirectory becomes orphaned. Dockwidget restores the inline broken parser — but the user is worse off, because the real file still won't import. Rollback only if Phase 3 introduces a regression on a file that currently imports cleanly.

## Risks and unknowns

- **Shell SPS 2.1 document** — I do not have the document. The SPS_2_1_SHELL spec ships with best-effort column positions based on the SEG SPS 2.1 convention (line in positions 2-11, SP in 12-21, coordinates in 46-66). Must be verified during execution.
- **Auto-detection ambiguity** — two specs could both cleanly parse the same file (e.g., Shell spec and PXGEO spec both accept integer line numbers). Detection picks the highest clean-parse ratio; ties go to the first-registered spec. Flagged as a possible user-facing confusion; Phase 8's UI selector mitigates by letting the user override.
- **Header detection edge case** — PXGEO file has NO headers (starts directly with `S`). Shell and Martin Linge may have variable header counts. The parser handles both by scanning each line's first char — no hardcoded count. VERIFY against real files.
- **Encoding variations** — all current specs use latin-1. Some vendor files may be UTF-8 or CP1252. Add encoding to the spec dataclass (done) and let auto-detect try multiple encodings per spec if first fails. Not implemented in Phase 3; add as Phase 9 stretch if needed.
- **Line/SP with leading zeros or alphanumeric** — real SPS files should have numeric line/SP, but some vendors may use alphanumeric IDs. Current `id_parser` rejects. Flag for future.
- **Performance** — `detect_spec` reads up to 500 lines × number-of-specs. For 5 specs that's 2500 line parses per import. The file is opened repeatedly per spec. Mitigation: cache the file contents or switch to a streaming strategy if Phase 3 profiling shows a user-visible delay. Not a priority for Phase 3 correctness.
- **`scripts/extract_fixtures.py`** — optional helper to generate fixtures from real files. If the executor skips this, hand-craft the fixtures carefully by copying from real file viewers.

## Hard Stop Gate

Phase 3 is complete when:
1. All Verify steps above pass.
2. You have imported `D1v1_MartinLindge_260410_sailline.sps` in QGIS 3.40 and confirmed records are created correctly.
3. You have imported `MT3007924_MMBC_SRC_20250316_combined_saillines.s01` and confirmed records are created correctly.
4. TGS and SAE specs have been verified against their respective sample files (or explicitly marked as unverified with user acknowledgment).

**Claude MUST stop after Phase 3 and await explicit "proceed to Phase 4" message from the user. Do not auto-advance even if all automated checks are green.**

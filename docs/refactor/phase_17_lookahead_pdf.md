# Phase 17 — 48-hour Lookahead PDF Export

**Size:** medium (split into 17a / 17b / 17c)
**Risk:** low (self-contained feature; no existing code paths changed)
**Blocks:** nothing
**Blocked by:** Phase 16 (consumes Operation / FGSP / LGSP fields produced in 16c).
**Status:** PLAN — contingent on Phase 16 shipping.

---

## Context / Why

Chief Navigator currently produces a daily 48-hour shooting plan PDF
by hand in QGIS's Print Layout: 5-10 minutes of repetitive
click-drag-configure work per day, per navigator, per vessel. After
Phase 16 the plugin's `Optimized_Path` layer will carry the full
schema the PDF needs — rendering that data is a one-click win.

Reference template: `Shooting_Plan_Petrobras_09-10_June_MMBC_2025.pdf`
(screenshot `/mnt/c/Users/chnav/Downloads/Shooting Plan.png`). The
reference table has 11 columns; availability against plugin data:

| Column | Data source | Ready after |
|---|---|---|
| Line | `Optimized_Path.LineNum` | today |
| Shoot As | = LineNum (v1 — Shoot As counter deferred) | today |
| Operation | `Optimized_Path.Operation` | Phase 16c |
| FGSP | `Optimized_Path.FGSP` | Phase 16c |
| LGSP | `Optimized_Path.LGSP` | Phase 16c |
| HDG° | `Optimized_Path.Heading` | today |
| 2NM Notes | empty (deferred) | future |
| 500m CPA | empty (deferred) | future |
| ETA SOL | `Optimized_Path.StartTime` | today |
| ETA EOL | `Optimized_Path.EndTime` | today |
| Day / Month | derived from StartTime | today |

User-confirmed PDF scope (`AskUserQuestion` answers, 2026-04-18):

- Multi-page PDF, "same as current 5-10 min manual, but more automated
  with more context like `2025_08_09 - 4D TVD_48hrLookahead_V1.0.pdf`".
- Pages: **Overview map** + **Sequence table with timing**.
- Template **built in Python code** (no user-editable `.qpt`).
- Filename pattern:
  `<YYYY_MM_DD> - <SurveyName>_48hrLookahead_V<major>.<minor>.pdf`.
- Date = today; Survey name = manual text field in dock; Version =
  auto-incremented by scanning output directory.
- Trigger: new **"Export PDF" button** in the dock.

## Goal

One-click PDF export producing the daily 48h lookahead, shaving
~30 min/week per navigator and producing consistent output across
vessels.

---

## Target architecture

```
obn_planner/
  services/
    pdf_export.py             # NEW — pure Python + QGIS, no Qt widgets
  obn_planner_dockwidget.py   # new handle_export_pdf() + button glue
  obn_planner_dockwidget_base.ui
                              # + QLineEdit surveyNameLineEdit
                              # + QPushButton exportPdfButton
  test/
    test_pdf_export.py        # pure-Python tests for filename logic
  docs/refactor/
    phase_17_lookahead_pdf.md # this file (updated in 17c with verified layout numbers)
```

## Key data sources (all populated by Phase 16 + earlier phases)

- `self.optimized_path_layer` — Optimized_Path memory layer with
  fields SeqOrder, LineNum, SegmentType, StartTime, EndTime,
  Duration_s, Duration_hh_mm, Heading, **Operation (Phase 16c)**,
  **FGSP (Phase 16c)**, **LGSP (Phase 16c)**. Populated by
  `_visualize_optimized_path` at `obn_planner_dockwidget.py:9849`.
- `self.last_simulation_result['seq']` — line order.
- `self.last_sim_params['start_datetime']` — basis for per-line times.
- `self.OUTPUT_GROUP_NAME = "OBN Planner Output"` — layer-tree group
  whose visible children the map page should render.

## Phase 17a — Scaffold: pdf_export.py module + pure-Python tests *(medium)*

**Files touched:**

- `services/pdf_export.py` (NEW, pure Python + qgis.core — no QtWidgets)

  Public entry points:

  ```python
  def compute_output_filename(
      date_str: str,        # "YYYY_MM_DD"
      survey_name: str,     # "4D TVD"
      output_dir: str,      # filesystem path
  ) -> str:
      """Scan output_dir for existing matching files, return the next
      version slot. First export -> V1.0; existing V1.0..V1.n -> V1.(n+1)."""
  ```

  ```python
  @dataclass(frozen=True)
  class LookaheadRow:
      seq_order: int
      line_num: int
      shoot_as: str             # = str(line_num) in v1
      operation: str            # "Production" / "Test" / "Reshoot" / "Infill"
      fgsp: int
      lgsp: int
      heading_deg: float
      notes_2nm: str            # empty in v1
      cpa_500m: str             # empty in v1
      eta_sol: datetime         # StartTime
      eta_eol: datetime         # EndTime
      day_month: str            # "dd-MMM" derived from eta_sol

  def rows_from_optimized_path_layer(
      layer: QgsVectorLayer,
  ) -> List[LookaheadRow]:
      """Filter Optimized_Path features where SegmentType='Line',
      sort by SeqOrder, read Operation/FGSP/LGSP from the features
      (populated by Phase 16c)."""
  ```

  ```python
  def build_lookahead_layout(
      project: QgsProject,
      layers: List[QgsMapLayer],
      rows: List[LookaheadRow],
      survey_name: str,
      date_str: str,
      version_str: str,
  ) -> QgsPrintLayout:
      """Assemble the two-section layout programmatically:
      Page 1 = overview map; Page 2+ = sequence table."""
  ```

  ```python
  def export_pdf(
      layout: QgsPrintLayout,
      output_path: str,
  ) -> Tuple[bool, Optional[str]]:
      """Wrap QgsLayoutExporter.exportToPdf. Returns (success, error_msg)."""
  ```

- `test/test_pdf_export.py` (NEW, pure Python)

  Coverage of `compute_output_filename` (no QGIS):
  - `test_filename_no_existing_files` → V1.0
  - `test_filename_first_export_with_other_surveys_present` → V1.0
    (only counts files matching the same survey_name)
  - `test_filename_increments_minor` → V1.5 when V1.0-V1.4 exist
  - `test_filename_double_digit_minor` → V1.10 after V1.9
  - `test_filename_survey_name_with_spaces` → correctly handles "4D TVD"
  - `test_filename_corrupt_entries_ignored` → V1.0 when only malformed
    matching-named files exist
  - `test_filename_sanitizes_illegal_chars` → strips/replaces `\`,
    `/`, `:`, `*`, `?`, `"`, `<`, `>`, `|` from survey_name before
    interpolation

  No tests for the QGIS-dependent functions in 17a — those are
  smoke-tested in 17b against the live plugin.

**Verify 17a:**
- `python3 test/test_pdf_export.py` → all filename tests green.
- Full pre-17a suite still passes.

**Commit:** `phase 17a: pdf_export module scaffold + filename tests`.

## Phase 17b — UI wiring: dock button + handle_export_pdf *(small)*

**Files touched:**

- `obn_planner_dockwidget_base.ui` — add near `editFinalizeButton`:
  - `QLineEdit surveyNameLineEdit` placeholder "Survey name (e.g. 4D TVD)"
  - `QPushButton exportPdfButton` labeled "Export 48h Lookahead PDF"

  Recompile via `python3 compile_resources.py`.

- `obn_planner_dockwidget.py` — new method `handle_export_pdf()`:
  1. Verify `self.last_simulation_result` and
     `self.optimized_path_layer` are populated (same guards as the
     Edit Sequence handler). Bail with a `QMessageBox.warning` if not.
  2. Read `survey_name = self.surveyNameLineEdit.text().strip()`.
     Default to "Survey" if empty. Sanitize filesystem-illegal chars.
  3. Prompt for output directory via
     `QFileDialog.getExistingDirectory`, remembering last-used path in
     `QSettings("obn_planner", "pdf_export_dir")`.
  4. Compute filename:
     `date_str = QDate.currentDate().toString("yyyy_MM_dd")` →
     `filename = compute_output_filename(date_str, survey_name, output_dir)`.
  5. Gather map layers: `self._get_or_create_output_group()` children,
     filter to visible.
  6. Build rows:
     `rows_from_optimized_path_layer(self.optimized_path_layer)`.
  7. Build layout: `build_lookahead_layout(...)`.
  8. Export:
     `success, err = export_pdf(layout, os.path.join(output_dir, filename))`.
  9. Success → `QMessageBox.information` with the full path + a
     "Open in default PDF viewer?" Yes/No.
     Failure → `QMessageBox.critical`.

  Button wired in `__init__` with hasattr guards (mirrors existing
  pattern for `followPreviousDirectionCheckBox`, etc.).

**Verify 17b (manual, in QGIS):**
1. Reload plugin. Confirm new "Export 48h Lookahead PDF" button
   appears. Survey-name text field visible beside it.
2. Run Simulation on Martin Linge. Click Export PDF. Enter "4D TVD".
   Pick output folder.
3. Verify output file at
   `<today_date> - 4D TVD_48hrLookahead_V1.0.pdf`.
4. Open the PDF. Verify:
   - Page 1: title block with "48-Hour Lookahead — 4D TVD", today's
     date, version V1.0, vessel name / chief navigator signature line.
     Map below fits the Optimized_Path extent, shows lines + turns.
   - Page 2+: 11-column sequence table matching the reference PDF:
     Line / Shoot As / Operation / FGSP / LGSP / HDG° / 2NM Notes /
     500m CPA / ETA SOL / ETA EOL / Day/Month. Operation / FGSP / LGSP
     values come from Phase 16c fields. Notes and CPA columns empty
     (deferred). Pagination kicks in naturally if > ~40 lines.
5. Click Export PDF a second time. Verify filename increments to V1.1.

**Commit:** `phase 17b: Export PDF button + handle_export_pdf`.

## Phase 17c — Polish: layout refinement, documentation, SMOKE_TEST *(small)*

**Files touched:**
- This file (`docs/refactor/phase_17_lookahead_pdf.md`) — update with
  any layout tuning discovered during 17b (exact font sizes, margin
  values that worked on the Martin Linge 136-line test).
- `docs/refactor/SMOKE_TEST.md` — add a "Phase 17: Export PDF"
  section with the 5-step manual verification above.
- `docs/refactor/README.md` — verify Phases 16 + 17 entries are in
  the phase index (added at Phase-16-planning time).

**Verify 17c:** reading check by user. Docs only, no code.

**Commit:** `phase 17c: docs — SMOKE_TEST entry + layout tuning notes`.

---

## Layout design (locked in this plan)

**Global (both pages):**
- Portrait A4, 210 × 297 mm.
- Title block top 30 mm:
  - Row 1: `<VesselName> <N>Hrs Look Ahead` (bold, 16 pt) — matches
    reference "Sanco Star 24Hrs Look Ahead". `<N>` is 48 by default,
    overridable via spin box if requested later; MVP = 48.
  - Row 2: `<SurveyName> — <project>` (12 pt) — matches reference
    "Petrobras MMBC – 3D OBN".
  - Row 3: Right-aligned date + local time + timezone (10 pt).
- Footer: page N of M, generation timestamp (8 pt, centred).

**Page 1 (Overview map):**
- Map frame fills remainder below title block, to ~20 mm before footer.
- Map shows all layers from the "OBN Planner Output" group visible at
  export time (Optimized_Path, Turn_Segments, Generated_Survey_Lines,
  Generated_RunIns, SPS point layer).
- Fit-to-extent with 10 % padding on Optimized_Path's bbox.
- North arrow top-right; scale bar bottom-left; legend bottom-right.

**Page 2+ (Sequence table):**
- 11 columns matching the reference PDF:
  Line | Shoot As | Operation | FGSP | LGSP | HDG° | 2NM Notes |
  500m CPA | ETA SOL | ETA EOL | Day/Month.
- Yellow header row bold (#FFF8A8) — matches reference.
- Alternating row shading (#F5F5F5 / white) for readability.
- `QgsLayoutItemManualTable.setResizeMode(RepeatUntilFinished)` to
  auto-paginate onto pages 3, 4, … as needed.
- Expected ~40 rows per page; tune empirically on Martin Linge
  136-line data during 17b, update this doc in 17c.

## Filename logic (detailed)

```python
import glob, os, re

_FILENAME_RE = re.compile(
    r"^(\d{4}_\d{2}_\d{2}) - (.+)_48hrLookahead_V(\d+)\.(\d+)\.pdf$"
)
_ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|]')

def _sanitize(survey_name: str) -> str:
    cleaned = _ILLEGAL_CHARS_RE.sub("_", survey_name).strip()
    return cleaned or "Survey"

def compute_output_filename(date_str, survey_name, output_dir):
    survey = _sanitize(survey_name)
    pattern = f"{date_str} - {survey}_48hrLookahead_V*.pdf"
    existing = glob.glob(os.path.join(output_dir, pattern))
    max_minor = -1
    for p in existing:
        m = _FILENAME_RE.match(os.path.basename(p))
        if m and m.group(1) == date_str and m.group(2) == survey:
            # Only consider major version 1 for now — bumping to V2.x
            # is a future, user-initiated concern.
            if int(m.group(3)) == 1:
                max_minor = max(max_minor, int(m.group(4)))
    next_minor = max_minor + 1 if max_minor >= 0 else 0
    return f"{date_str} - {survey}_48hrLookahead_V1.{next_minor}.pdf"
```

Contract: 1st export = V1.0, 2nd same-day same-survey = V1.1, … V1.n.
Major version stays at 1 (future phase may add "new major version"
button if users want V2.0 / V3.0 semantics).

## Risks / open questions (non-blocking)

- **QgsLayoutItemManualTable pagination on 136 rows** — API exists in
  3.40 but has known quirks with very tall tables. Fallback: manually
  splice the row list into pages of N rows each, instantiate one
  table per page. Decide at 17b implementation time.
- **Overview map layer visibility** — the map renders layers using
  their CURRENT visibility in the project's layer tree. If the user
  has turned off (e.g.) Generated_RunIns before clicking Export PDF,
  the PDF won't show run-ins. Document in the tooltip.
- **QSettings namespace** — use `"obn_planner"` / `"pdf_export_dir"`
  to avoid colliding with other plugin settings. No persistence of
  the survey_name string — user types it each time (they may be
  planning multiple concurrent surveys).
- **Today's date timezone** — `QDate.currentDate()` uses local tz on
  the workstation. Vessels in different timezones may produce
  different date_strs for the "same" planning session. Acceptable —
  matches user's expectation of "today".
- **Existing `_generate_lookahead_table` reuse** — the method at
  `obn_planner_dockwidget.py:8639` produces a dict-per-row but
  WITHOUT timing or Operation/FGSP/LGSP. Phase 17a's
  `rows_from_optimized_path_layer` is a richer replacement — we do
  NOT modify the existing `_generate_lookahead_table` (used by the
  display-table dialog); we add a new function reading directly from
  the Optimized_Path layer's attributes.

## What is NOT in Phase 17 (deferred)

- **Per-page map zooms to next 48h of lines** — user chose "same as
  current manual" (no time filter). "48hr" is filename convention.
- **Auto-export on Run Simulation** — user chose "new button" trigger.
- **QThread worker for long exports** — Phase 13b stays pending. PDF
  export is fast (~2-3 s for 136 lines + one map).
- **Shoot As counter** — v1 uses `line_num`.
- **2NM Notes / 500m CPA text columns** — empty in v1; deferred.
- **Auto-mark acquired** — Phase 18.
- **Run-outs removal** — Phase 19.
- **Deviation smoothness** — Phase 20.

## Verification after Phase 17 completes

1. Reload plugin in QGIS 3.40.5.
2. Import Martin Linge SPS, Generate Lines with default
   Operation = Production. Open Sequence Editor, change one line to
   Operation = Reshoot with FGSP/LGSP narrower than lowest/highest.
3. Run Simulation (OR-tools).
4. Enter "4D TVD" in the new survey-name text field.
5. Click "Export 48h Lookahead PDF". Pick an empty output folder.
6. Confirm file `<today> - 4D TVD_48hrLookahead_V1.0.pdf` is created.
7. Open PDF. Confirm:
   - Page 1: title block with vessel / survey / date / time /
     timezone. Map shows Optimized_Path.
   - Page 2+: 11-column sequence table. The Reshoot line shows
     Operation=Reshoot and the narrower FGSP/LGSP values correctly.
8. Click Export again → V1.1 file created alongside V1.0.
9. Re-click Export with survey name "Martin Linge" → V1.0 file
   created (independent of "4D TVD" versioning).
10. `python3 test/test_pdf_export.py` → all green.

## Hard-stop gates

1. User greenlights Phase 17a (module + tests) → implement → test →
   commit → review → approve.
2. User greenlights Phase 17b (UI + handler) → implement → compile →
   deploy → user generates one test PDF → approve.
3. User greenlights Phase 17c (docs) → commit.

Claude MUST NOT auto-advance between sub-phases.

## Rollback

Per-commit revert. Each sub-phase adds new files / methods / widgets
without touching existing code paths.

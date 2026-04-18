# Phase 16 — Line Management core (Operation + FGSP + LGSP)

**Size:** medium (split into 16a / 16b / 16c sub-phases, each independently shippable)
**Risk:** low-medium (adds per-line metadata; simulation respects new SP bounds — affects cost numbers)
**Blocks:** Phase 17 (PDF) — the PDF's Operation / FGSP / LGSP columns depend on this data.
**Blocked by:** nothing — all needed plugin infrastructure already exists.
**Status:** PLAN — awaiting user greenlight to start Phase 16a.

---

## Context / Why

Real reference template (`Shooting_Plan_Petrobras_09-10_June_MMBC_2025.pdf`,
screenshot `/mnt/c/Users/chnav/Downloads/Shooting Plan.png`) shows the
daily 48-hour shooting plan PDF's second-page table has these columns:

```
Line | Shoot As | Operation | FGSP | LGSP | HDG° | 2NM Notes | 500m CPA | ETA SOL | ETA EOL | Day/Month
```

Plugin currently has Line / HDG° / StartTime (=ETA SOL) / EndTime
(=ETA EOL) / Day. Plugin does NOT have **Operation**
(Production / Test / Reshoot / Infill), **FGSP** (First Good SP),
**LGSP** (Last Good SP), or Notes/CPA text. Without these, Phase 17's
PDF export would have columns stuck at defaults or empty — making
the automation cosmetic rather than operational.

User-confirmed scope (`AskUserQuestion` answers, 2026-04-18):

1. **Operation data source today**: "operational convention / not
   per-row". The navigator tags by time window (this week = Production,
   today = Reshoot, etc.), NOT line-by-line. Default = Production;
   per-line override is the exception not the rule.

2. **FGSP / LGSP semantics**: "No, Production can also be partial".
   FGSP and LGSP are **always separate from lowest_sp / highest_sp**.
   Default FGSP = lowest_sp, LGSP = highest_sp — but both must be
   overridable on any line (not just Reshoot / Infill). This matches
   a real filter the user showed from daily ops:

   ```
   ( "LineNum" IN (2146) AND "SP" <= 5761 )
   OR ( "LineNum" IN (2116) AND "SP" BETWEEN 4385 AND 5761 )
   OR ( "LineNum" IN (1996, 2002, 2008, 2014, ...) AND "SP" BETWEEN 5583 AND 6563 )
   ```

3. **Phase ordering**: "Line Management first, PDF second" —
   confirmed. The minimum LM that makes the PDF feature-complete
   is **Operation + FGSP/LGSP**. Auto-mark-acquired and run-outs
   removal ship as separate later phases (see `README.md` roadmap).

4. **Shoot As column**: "Skip it in v1 — use line_num". No shot-counter
   infrastructure now. Deferred.

## Goal

Give each survey line three editable attributes — **Operation**,
**FGSP**, **LGSP** — with sensible defaults (Production / lowest_sp /
highest_sp), a UI to override them, and simulation that honors them
(line length + entry/exit points computed from the actual FGSP/LGSP
range). These attributes then feed Phase 17's PDF export directly.

---

## Target architecture

```
obn_planner/
  services/
    line_metadata.py        # NEW — LineOperation enum + data model helpers
  obn_planner_dockwidget.py # new Operation dropdown + per-line override flow
  obn_planner_dockwidget_base.ui
                            # + Operation dropdown in the dock header
                            # + FGSP / LGSP spin boxes in the sequence editor
  sequence_edit_dialog.py   # extended to edit Operation/FGSP/LGSP per line
  test/
    test_line_metadata.py   # pure-Python tests for defaults + validation
```

## Phase 16a — Line-metadata schema: Operation + FGSP + LGSP fields *(small)*

**Data model on Generated_Survey_Lines layer.** Three new fields added
by `handle_generate_lines` at `obn_planner_dockwidget.py:1778-1793`:

```python
line_fields.append(QgsField("Operation", QVariant.String, len=12))   # default "Production"
line_fields.append(QgsField("FGSP", QVariant.Int))                    # default = LowestSP
line_fields.append(QgsField("LGSP", QVariant.Int))                    # default = HighestSP
```

**`services/line_metadata.py` (new, pure Python):**

```python
class LineOperation(str, Enum):
    PRODUCTION = "Production"
    TEST = "Test"
    RESHOOT = "Reshoot"
    INFILL = "Infill"

@dataclass(frozen=True)
class LineMetadata:
    line_num: int
    operation: LineOperation
    fgsp: int
    lgsp: int

    def is_full_range(self, lowest_sp: int, highest_sp: int) -> bool: ...
    def validate(self, lowest_sp: int, highest_sp: int) -> None: ...
```

**Feature-population at line-generation time** (`handle_generate_lines`,
inside the per-line loop at line ~1967):
- Operation defaults to the dock's global "Default operation" dropdown
  value (Production at first load). Per-line override happens in the
  sequence editor (Phase 16b).
- FGSP = lowest_sp, LGSP = highest_sp at generation time.

**Tests (`test/test_line_metadata.py`, pure Python):**
- `test_default_is_production`
- `test_operation_enum_values_match_reference_pdf` — strings exactly
  match "Production"/"Test"/"Reshoot"/"Infill" — PDF relies on this.
- `test_fgsp_must_not_exceed_lgsp`
- `test_fgsp_lgsp_must_stay_within_lowest_highest_sp`
- `test_is_full_range_true_when_equal_to_bounds`

**Commit:** `phase 16a: line metadata schema (Operation + FGSP + LGSP)`.

## Phase 16b — UI: dock header Operation dropdown + sequence editor per-line override *(medium)*

**Dock header additions** (`obn_planner_dockwidget_base.ui`):
- `QComboBox defaultOperationComboBox` with items
  Production / Test / Reshoot / Infill. Default "Production".
  Placed near the existing acquisition-mode controls.
- Tooltip: *"Sets Operation for all newly generated lines. Per-line
  overrides happen in the sequence editor."*

**Sequence editor** (`sequence_edit_dialog.py`): add three columns to
the existing table:
- **Operation**: QComboBox delegate per cell, values = LineOperation enum.
- **FGSP**: QSpinBox delegate, min = lowest_sp, max = LGSP.
- **LGSP**: QSpinBox delegate, min = FGSP, max = highest_sp.

Edits in the editor mutate the Generated_Survey_Lines feature
attributes via `startEditing()` → `changeAttributeValue()` →
`commitChanges()` on accept. Revert on cancel.

Validation: block commit if FGSP > LGSP on any row.

**Commit:** `phase 16b: Operation + FGSP/LGSP UI (dock dropdown + editor columns)`.

## Phase 16c — Simulation respects FGSP/LGSP *(medium)*

**Core change:** `_prepare_line_data` at
`obn_planner_dockwidget.py:6496` reads the three new fields per line
and exposes:
- `line_data[line_num]['operation']` (string)
- `line_data[line_num]['fgsp']` (int)
- `line_data[line_num]['lgsp']` (int)
- `line_data[line_num]['length']` — recomputed from the SUBSET of the
  line geometry between FGSP and LGSP points (not the full line).
- `line_data[line_num]['start_point_geom']` / `end_point_geom` — set
  to the FGSP / LGSP point geometries respectively, NOT the
  full-line geometric endpoints.

**SPS point lookup**: FGSP/LGSP are SP numbers, not vertex indices.
The plugin needs to find the SPS points for those SP numbers to get
the geometry. Source: the SPS source layer
(`self.sps_layer_combo.currentLayer()`).

**Simpler approach** chosen for 16c: `handle_generate_lines` at
line ~1940 already has `point_geometries[sp]` dict when generating
the line. Persist a serialized per-line subset of this mapping as
attributes on the Generated_Survey_Lines feature (JSON-encoded or
additional fgsp_x / fgsp_y / lgsp_x / lgsp_y columns). Use them at
simulation time to build the working line geometry.

**Run-in attachment:** start_runin attaches to FGSP point (not
lowest_sp_point); end_runin attaches to LGSP point. This is a genuine
re-anchoring — run-in geometries may need to be regenerated when
FGSP/LGSP are edited. Lightweight approach for 16c: regenerate run-ins
lazily in `_prepare_line_data` using the existing
`_calculate_runin_time` helper.

**Sequence table output in `_visualize_optimized_path`**: add
FGSP / LGSP / Operation columns to the Optimized_Path layer schema
so Phase 17's PDF can consume them directly without re-joining to
Generated_Survey_Lines.

**Tests:** pure-Python tests in `test_line_metadata.py` extended with
clamp helpers; QGIS-dependent integration verified by the manual
SMOKE_TEST.

**Verify 16c (manual):** set FGSP=5583 / LGSP=6563 on a Production
line in the editor, re-run simulation, confirm the Optimized_Path
segment for that line starts at SP 5583 point and ends at SP 6563
point — not the full line endpoints.

**Commit:** `phase 16c: simulation respects FGSP/LGSP (partial-range acquisition)`.

---

## Verification after all Phase 16 sub-phases land

1. Reload plugin in QGIS 3.40.5.
2. Import Martin Linge SPS, Generate Lines with the dock's
   "Default operation" = Reshoot. Confirm the
   Generated_Survey_Lines attribute table shows Operation="Reshoot"
   on every line.
3. Open Sequence Editor. Change 3 specific lines to
   Operation=Infill and set FGSP/LGSP = 5583 / 6563 on those 3
   lines. Save.
4. Run Simulation. Confirm:
   - Optimized_Path segments for those 3 lines are SHORTER than
     before (they now cover SP 5583-6563 only, not the full line).
   - Simulation total time drops by approximately the time saved.
5. Generated_Survey_Lines table reflects the new Operation /
   FGSP / LGSP values.
6. All pure-Python tests still pass.

## What is NOT in Phase 16 (deferred)

- **Auto-mark acquired after Run Simulation** — deferred to Phase 18.
  Separate concern from setting per-line metadata.
- **Remove run-outs** — deferred to Phase 19. Independent geometry
  change; doesn't affect the PDF's columns.
- **Shoot As column generator** — deferred. Plugin produces
  `line_num` in place of the vessel shot counter for now.
- **2NM Notes / 500m CPA text columns** — deferred. These are
  free-text operational callouts that need their own data model;
  out of scope for 16.

## Hard-stop gates

1. User greenlights Phase 16a → implement → test → commit → user
   reviews diff → approve.
2. User greenlights Phase 16b → implement → compile UI → deploy →
   user smoke-tests → approve.
3. User greenlights Phase 16c → implement → deploy → user verifies
   partial-range sim → approve.

Claude MUST NOT auto-advance between sub-phases.

## Rollback

Per sub-phase revert; each adds clearly new code paths and attributes
without mutating existing ones. If 16c rollback is needed,
`_prepare_line_data` falls back to using lowest_sp / highest_sp
exactly as it does today.

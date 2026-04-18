# Phase 16 — Line Management (revised 2026-04-18 after user interview)

**Size:** medium-large (four sub-phases; each independently shippable)
**Risk:** medium — affects the chief navigator's primary planning tool; a
bug here can cost $10,000/hour in vessel time (see
`memory/project_line_management_value.md`).
**Blocks:** Phase 17 (PDF export) — Operation / FGSP / LGSP fields
feed the 48-hour plan table directly.
**Blocked by:** nothing.
**Status:** 16a, 16b, 16b-fix shipped. 16c and 16d planned.

---

## Context

Revised scope after interviewing the user (2026-04-18). The initial plan
(manual FGSP/LGSP entry per line in the sequence editor) was partly
wrong: the chief navigator already has per-SP Status tracking on the
SPS layer (`Status` field, values Acquired / To Be Acquired / Pending)
and mutates it via the existing **Mark as Acquired / Mark as To Be
Acquired / Mark as Pending** buttons. The right design is to extend
*those* to work on a **shotpoint range** within a single line and
derive FGSP/LGSP automatically.

**Dominant operational use case:** resume an aborted line. A line
starts at SP 1000 and is aborted at SP 1100 (weather, marine mammals,
equipment failure). The next 48-hour plan must acquire SP 1101–1500
only. Chief selects line 2146 in the dock list, sets `From SP = 1000` /
`To SP = 1100`, clicks **Mark as Acquired**. The plugin sets Status=
Acquired on those 101 points, leaves SP 1101–1500 as To Be Acquired.
When `Generate Lookahead Lines` runs, it emits a sub-line
`2146 (1101–1500)` with geometry, run-in, and derived FGSP=1101 /
LGSP=1500.

**Gaps within a line are legal** (operational reality). A line can end
up with two disjoint TBA ranges (e.g., 1101–1200 and 1301–1500); the
plugin emits **two sub-lines**, one per contiguous TBA run.

## Architecture (source-of-truth diagram)

```
 SPS layer points [per-point Status]   ← source of truth
    │  (edited via Mark as X buttons, line or SP-range scope)
    ▼
 handle_generate_lines
    │  reads each parent line's per-SP Status,
    │  splits into contiguous TBA runs,
    │  emits one sub-line feature per run
    ▼
 Generated_Survey_Lines features
    · LineNum (parent)      — existing
    · SubLineId (1-based within parent)  — NEW (Phase 16d)
    · Label: "2146 (1101-1500)"  — NEW (Phase 16d, computed field)
    · Operation (user-editable, default Production)  — 16a/16b
    · FGSP, LGSP (derived — direction-aware start/stop SP)  — 16a/16b/16d
    · existing fields (geometry, Status, Heading, PrevDirection, …)
    ▼
 Simulation + Sequence Editor + Phase 17 PDF
    treat every sub-line as an independent line.
    No partial-line branching in the sim loop.
```

The FGSP/LGSP fields stay on `Generated_Survey_Lines` but become
**derived**, never user-edited — the sequence editor shows them
read-only (16b-fix). Operation remains user-editable per sub-line.

---

## Phase 16a — shipped (`eeacad8`)

`Operation`, `FGSP`, `LGSP` fields added to `Generated_Survey_Lines`
schema. `services/line_metadata.py` pure-Python module. 18 unit tests.
Defaults: Operation=Production, FGSP=lowest_sp, LGSP=highest_sp.

## Phase 16b — shipped (`f24b648`)

Sequence editor got Operation/FGSP/LGSP columns with combo + spin
widgets and a direction-aware FGSP/LGSP swap on Direction combo flip.
`_read_line_metadata_map` + `_commit_line_metadata_edits` wire the
editor to the layer.

**Note:** the original plan had a dock-header "Default Operation"
dropdown; it was removed before commit at user's request (dock space
is tight; see `memory/feedback_dock_ui_compact.md`). Operation defaults
to Production in code.

## Phase 16b-fix — shipped (`bfedfac`)

Sequence editor FGSP/LGSP spinboxes set read-only
(`setReadOnly(True)`, `NoButtons`). `valueChanged` handlers
disconnected. Editing surface for FGSP/LGSP moves to Phase 16c.

---

## Phase 16c — SP-range Mark buttons *(medium)*

**Goal.** Allow the chief to mark a partial SP range of a single line as
Acquired / TBA / Pending, reusing the three existing Mark buttons.

**UI additions** in `obn_planner_dockwidget_base.ui`, in
`horizontalLayout_7` (the Mark-buttons row) or a new row immediately
above it:

- `QSpinBox fromSpSpinBox` (label: "From SP")
- `QSpinBox toSpSpinBox`   (label: "To SP")
- Wrapped in a container widget/layout that is
  `setVisible(False)` by default.

**Visibility rule:** the container is shown only when
`lineListWidget.selectedItems()` has exactly one item. Wire via
`lineListWidget.itemSelectionChanged`. When shown, the spinboxes'
bounds auto-snap to the selected line's `[lowest_sp, highest_sp]`,
and default values reset to `(lowest_sp, highest_sp)` (i.e., full
range, matching the current whole-line behavior).

**Handler changes** — `_update_selected_lines_status` at
`obn_planner_dockwidget.py:1436`:
- Current filter when 1 line selected: `"LineNum" = N`.
- New filter when 1 line + spinboxes visible:
  `"LineNum" = N AND "SP" BETWEEN from AND to`.
- Multi-line selection: unchanged (applies to whole lines).
- Range validation: `from <= to`; both within line's
  `[lowest_sp, highest_sp]`. Block the update with a clear message
  if invalid.

**Safety reminder dialog**: because Mark buttons now modify a subset,
show a confirmation dialog with the exact range (e.g., "Mark SP
1000–1100 on line 2146 as Acquired? (101 shotpoints)") before
committing. The chief explicitly wants QC-able edits (interview Q4).

**Out-of-date indicator (staleness)** — added in 16c scaffold, wired
fully in 16d. Add a `QLabel lookaheadStaleLabel` near the
`generateLinesButton` with text:

```
  Lookahead plan needs refresh — Generate Lookahead Lines again
```

Hidden by default. Setter method `_set_lookahead_stale(True/False)`.
In 16c, any successful `Mark as X` call sets stale=True. In 16d,
`handle_generate_lines` clears it on success. UX writing: plain
English, actionable, no jargon. (User answer Q10b: "UX writing must
be intuitive".)

**Tests** (pure-Python where possible; widget interactions via
smoke-test only):
- `test_mark_range_filter_single_line_with_range`
- `test_mark_range_filter_multi_line_no_range_fallback`
- `test_range_validation_rejects_from_gt_to`
- `test_range_validation_rejects_out_of_bounds`

**Verify 16c (manual smoke test):**
1. Import SPS. Select one line. Spinboxes appear.
2. Set From=1000 / To=1100. Click Mark as Acquired. Confirmation
   dialog shows "Mark SP 1000–1100 on line ... as Acquired?".
   Confirm. Attribute table of SPS: points in that range have
   Status=Acquired; rest of the line unchanged.
3. Select two lines. Spinboxes auto-hide. Click Mark as Acquired.
   Full lines marked (current behavior preserved).
4. Select a line, leave From/To at defaults (full range). Click
   Mark as TBA. Entire line's points set to TBA (matches current).
5. "Lookahead plan needs refresh" label appears after any mark.

**Commit:** `phase 16c: SP-range Mark buttons + staleness indicator`.

---

## Phase 16d — Sub-line generation on Generate Lookahead Lines *(medium-large)*

**Goal.** `handle_generate_lines` stops emitting one feature per parent
line; emits one feature **per contiguous TBA run per parent line**.
Each sub-line has its own geometry, run-in, and derived
FGSP/LGSP/length.

**Schema changes** on `Generated_Survey_Lines`:
- NEW field: `SubLineId` (QVariant.Int). 1-based index within parent
  LineNum. `1` for a parent-line with one contiguous TBA run (the
  common case — backwards-compatible with current users who never
  edit SP-level status).
- NEW field: `Label` (QVariant.String, len=32). Computed at
  generation time. Format:
  - `"2146"` when SubLineId=1 and it covers the full parent range.
  - `"2146 (1101-1500)"` when partial range OR SubLineId>1.
  - Used by the sequence editor's Line column and by Phase 17 PDF.
- KEEP: `LineNum`, `FGSP`, `LGSP`, `Operation`. FGSP/LGSP now derived.

**Core logic** in `handle_generate_lines`
(`obn_planner_dockwidget.py:1836`):

```
for each parent line_num:
    points = ordered-by-SP list of SPS points for this line
    runs = contiguous_runs(points, predicate=lambda p: p.status == "To Be Acquired")
    for run_index, run in enumerate(runs, start=1):
        geometry = linestring connecting points in run
        fgsp = run[0].sp (direction-aware — or min; 16d uses min/max)
        lgsp = run[-1].sp
        operation = carried from parent defaults (Production)
        label = "{line_num}" if len(runs)==1 and full-range else
                f"{line_num} ({min}-{max})"
        emit feature(LineNum=line_num, SubLineId=run_index, Label=label,
                     FGSP=fgsp, LGSP=lgsp, Operation=operation,
                     geometry=geometry, …)
        emit run-ins anchored at run's first and last point
```

**Contiguous runs** definition: a run is a maximal sequence of
consecutive SPs (by SP number, not just adjacent in the list) where
every SP has Status="To Be Acquired". Pending and Acquired points
break runs.

**Edge cases:**
- Parent line with 0 TBA points → no sub-line emitted (deliberately;
  Chief can Mark as TBA first if they intend to include it).
- Parent line with all-TBA → one sub-line covering full range,
  SubLineId=1, Label="2146". Backward-compatible display.
- Parent line with single-point TBA → one sub-line with fgsp==lgsp.
  Validate: reject with warning (no meaningful geometry).
- Gaps: each run emits its own feature. Two runs on parent line
  2146 become `2146 (1101-1200)` and `2146 (1301-1500)`.

**Direction handling for FGSP/LGSP:**
- Stored on feature as direction-neutral **min/max**: `FGSP = min(SP)`,
  `LGSP = max(SP)` of the run. (Rationale: direction is decided per
  simulation run via the Direction combo / follow-previous logic, not
  baked into the feature.)
- Sequence editor's direction-swap logic (from 16b) still works:
  display-time swap for the read-only spinboxes.
- Phase 17 PDF export also picks direction from simulation state and
  swaps at render time.

**Staleness indicator** (wired from 16c):
- `handle_mark_acquired` and siblings call `_set_lookahead_stale(True)`.
- `handle_generate_lines` calls `_set_lookahead_stale(False)` on
  success.

**Run-in generation:** the existing run-in logic in
`handle_generate_lines` anchors to `lowest_sp_point` / `highest_sp_point`.
For sub-lines, it must anchor to the sub-line's own first/last points,
not the parent's.

**Simulation impact:** **none**. Each sub-line is an independent line
as far as `_prepare_line_data`, `_get_cached_turn`,
`_calculate_runin_time`, and the sequence optimizer are concerned.
This is the elegant-handling-of-gaps property from the user interview.

**Tests:**
- `test_contiguous_runs_empty` — 0 TBA points → 0 runs
- `test_contiguous_runs_full` — all TBA → 1 run covering full range
- `test_contiguous_runs_two_gaps` — ...A...T...T...A...T... → 2 runs
- `test_contiguous_runs_single_point_rejected`
- `test_label_format_full_range` — "2146"
- `test_label_format_partial` — "2146 (1101-1500)"
- `test_label_format_multiple_sub_lines` — "2146 (1101-1200)"

**Verify 16d (manual smoke test):**
1. Import SPS, Generate Lookahead Lines fresh. Confirm Label on all
   features = bare LineNum (all full-range), SubLineId=1.
2. Select line 2146. Spinboxes appear. From=1000 / To=1100. Mark
   Acquired. Staleness indicator shows.
3. Click Generate Lookahead Lines. Indicator clears. Attribute table:
   line 2146 now has one feature with Label="2146 (1101-1500)",
   SubLineId=1, FGSP=1101, LGSP=1500.
4. Mark SP 1201–1300 of line 2146 as Acquired (creating a gap).
   Regenerate. Line 2146 now has two features: Label="2146
   (1101-1200)" SubLineId=1 and Label="2146 (1301-1500)" SubLineId=2.
5. Run simulation. Sequence editor shows both sub-lines as separate
   rows with correct labels. Sim's total time accounts for turn
   between 2146-a and 2146-b.

**Commit:** `phase 16d: sub-line generation on Generate Lookahead Lines`.

---

## What is NOT in Phase 16 (deferred)

- **Auto-mark acquired after Run Simulation** — deferred. The chief
  manually marks post-acquisition (user rejected auto-mark in interview
  Q4: wants QC control).
- **Remove run-outs** — deferred to separate phase.
- **Shoot As column generator** — deferred; plugin produces LineNum
  in place of the vessel shot counter.
- **2NM Notes / 500m CPA text columns** — deferred; free-text fields
  needing their own data model.

## Hard-stop gates

1. 16b-fix → ✅ shipped (`bfedfac`).
2. 16c → user greenlights → implement → compile UI → deploy → user
   smoke-tests → approve → commit.
3. 16d → user greenlights after 16c passes smoke test → implement
   → deploy → user verifies sub-line generation → approve → commit.

Claude MUST NOT auto-advance between sub-phases.

## Rollback

Each sub-phase is a per-commit revert:
- 16c revert: removes the two spinboxes; the Mark handlers fall back
  to whole-line-only behavior (current pre-16c semantics).
- 16d revert: one feature per parent line again; SubLineId/Label
  fields left in schema but always SubLineId=1 / Label=LineNum.
  Sequence editor / PDF keep working.

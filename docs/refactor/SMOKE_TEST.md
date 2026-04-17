# Manual Smoke Test Checklist

Run this checklist after every phase merge. Compare against the Phase 0 baseline.

## Prerequisites

- A known-good SPS file (the user's real project is ideal — record the filename here: `_____________________`).
- A known-good No-Go zones polygon layer (record here: `_____________________`).
- QGIS 3 installed. Plugin deployed via `pb_tool deploy` OR `make deploy` (whichever is production).
- A "baseline snapshot" recorded after Phase 0 completes:
  - Total simulation time (hours) for Racetrack mode: `_____`
  - Total simulation time (hours) for Teardrop mode: `_____`
  - Sequence hash (e.g. MD5 of comma-joined line numbers): `_____`
  - XLSX column headers: `_____________________`

## Deploy and load

- [ ] Deploy plugin via the production path
- [ ] Open QGIS; plugin menu entry appears: **OBN Source Line Planner & Optimisation**
- [ ] Click menu entry — dock widget opens on the right
- [ ] QGIS Python console shows no errors in the dockwidget log (`obn_planner_debug.log` in plugin dir)

## Import SPS

- [ ] Click **Import SPS File...**; select known-good SPS
- [ ] GeoPackage output dialog appears; pick a destination
- [ ] Import completes; new point layer appears on canvas
- [ ] Layer has expected field names: `LINE_NUM`, `SP`, `EASTING`, `NORTHING`, plus status/heading fields
- [ ] Point count matches expected value: `_____`

## Calculate headings

- [ ] Select the SPS point layer in the dropdown
- [ ] Click **Calculate Headings**
- [ ] Progress dialog appears (if implemented post-Phase 5)
- [ ] Completes without error
- [ ] Sample a few points; `HEADING` field has values in [0, 360)

## Apply filter

- [ ] Set Start Line / End Line / Status filter
- [ ] Click **Apply Filter / Refresh List**
- [ ] Line list populates with expected line numbers

## Mark status

- [ ] Select lines in the list; click **Mark Acquired** — status field updates
- [ ] Click **Mark TBA** — status resets to "TO BE ACQUIRED"
- [ ] Click **Mark Pending** — status updates

## Generate lines

- [ ] Set turn radius, run-in length, start line, end line
- [ ] Click **Generate Lookahead Lines**
- [ ] Two layers appear: `Generated_Survey_Lines` and `Generated_RunIns`
- [ ] Geometry visually matches Phase 0 baseline
- [ ] Line count matches expected value: `_____`

## Calculate deviations

- [ ] Select No-Go layer in dropdown
- [ ] Set clearance (default 100 m)
- [ ] Click **Calculate Deviations**
- [ ] Lines intersecting no-go zones show deviated geometry
- [ ] Deviation fields populated on affected features
- [ ] Visual output matches Phase 0 baseline for the same input

## Run simulation — Racetrack

- [ ] Select Acquisition Mode: **Racetrack**
- [ ] Set First Line, First Heading, First Sequence, Start Date/Time, speeds
- [ ] Click **Run Simulation**
- [ ] Wait cursor appears
- [ ] Timing table appears with sequence
- [ ] Total time (hours): `_____`  — matches baseline to <0.01%
- [ ] Sequence order matches baseline
- [ ] `Optimized_Survey_Path` layer appears on canvas

## Run simulation — Teardrop

- [ ] Select Acquisition Mode: **Teardrop**
- [ ] Click **Run Simulation**
- [ ] Timing table appears
- [ ] Total time (hours): `_____` — matches baseline to <0.01%
- [ ] Sequence order matches baseline

## Sequence editor

- [ ] Click **Edit & Finalize Sequence**
- [ ] Dialog opens with the simulated sequence
- [ ] Reorder a row (use Up/Down buttons); table recalculates timing
- [ ] Click **Export to XLSX**; pick a path
- [ ] Open the XLSX in Excel or LibreOffice
- [ ] Column headers match baseline: `_____________________`
- [ ] Row count matches sequence length

## Plugin unload

- [ ] Close dock widget; plugin unloads without error
- [ ] QGIS Python console clean
- [ ] Reopen plugin from menu; opens cleanly without stale state

## Log review

- [ ] Open `obn_planner/obn_planner_debug.log`
- [ ] No ERROR or CRITICAL entries for normal workflow
- [ ] Workflow milestones logged (import, generate, simulate)
- [ ] Post-Phase-6: no stray `print(` output on stdout

## Automated tests

- [ ] `pytest test/` — pure-math tier all green
- [ ] (Optional) `pytest test/test_deviation_service.py test/test_obn_planner_dockwidget.py` — QGIS tier green (requires QGIS Python env)

## Regression diff (10 phases)

Keep this section updated after each phase's hard-stop gate. If any row changes unexpectedly between phases, halt and investigate before proceeding.

| Phase | Date | Racetrack hours | Teardrop hours | Sequence MD5 | Martin Linge import OK? | PXGEO import OK? | Notes |
|---|---|---|---|---|---|---|---|
| 0 baseline | 2026-04-__ | | | | N/A pre-fix | N/A pre-fix | capture here |
| 1 | | | | | N/A | N/A | expect small one-time delta from MAX_CURVE_DISTANCE fix |
| 2 | | | | | N/A | N/A | no behavior change |
| 3 | | | | | **YES** (was broken) | **YES** | SPS multi-format lands |
| 4 | | | | | yes + PREV_DIRECTION populated | yes | no sim behavior change |
| 5 | | | | | | | no behavior change (wrappers) |
| 6 (feature off) | | | | | | | matches Phase 5 baseline |
| 6 (feature on) | | | | | | | EXPECTED to differ — feature in use |
| 7 | | | | | | | matches Phase 6 (feature off) baseline |
| 8 | | | | | | | same; UI controls verified |
| 9 | | | | | | | final check; all green |

## Known-expected deltas

- **Phase 1** may produce a small one-time shift in total simulation time due to the `MAX_CURVE_DISTANCE` global-leak fix. Stable across repeat runs → expected.
- **Phase 2** zero behavioral change (only code deletion, v2 algorithm unchanged).
- **Phase 3** a FILE that previously failed to import now imports correctly — this is a fix, not a regression. For previously-working files, behavior identical.
- **Phase 4** zero behavioral change (data populated, not yet used).
- **Phases 5 and 7** zero behavioral change (extraction only).
- **Phase 6 feature OFF** must match Phase 5 baseline to <0.001%.
- **Phase 6 feature ON** expected to differ — that's the feature's purpose. Capture the with-feature numbers as a new baseline for Phases 7-9.
- **Phase 8 and 9** zero behavioral change.

## Hard-stop verification per phase

After each phase, I tell you it's complete and WAIT. Your verification steps:

1. `pytest test/` locally
2. Install the plugin (`pb_tool deploy` or `make deploy`)
3. Work through the applicable checklist items above
4. Update the regression diff table with numbers you observed
5. Reply `proceed to Phase N+1` or flag specific issues

I do not advance to the next phase without your explicit approval message.

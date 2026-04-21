# OBN Source Line Planner & Optimisation

QGIS plugin that plans, optimises, and documents source-vessel acquisition
for Ocean Bottom Node (OBN) seismic surveys. Used live on the bridge to
plan the next 48 h of shooting, re-sequence after aborts, and generate
the daily lookahead PDF.

- **Author:** Muhammad Aldien Said — aldien03@gmail.com
- **Min QGIS:** 3.40 (plugin `metadata.txt`)
- **Plugin version:** 1.0
- **Main branch:** `main` (force-pushed 2026-04-21 from local `master` —
  remote history before that was a stale September 2025 snapshot and
  should be ignored).

---

## Current status (2026-04-21)

| Phase | Scope | Status | Key commit |
|---|---|---|---|
| 0–9 | Safety net, Dubins units, SPS multi-format, services split | shipped | — |
| 10 | Performance pass | shipped | — |
| 12c | Optimized_Path / Turn_Segments at top of group | shipped | `4d88c73` |
| 13 | OR-tools sequence optimiser + log rotation | shipped | `ab37778`, `a0cb4d8` |
| 16a–d | Line Management (Operation / FGSP / LGSP + Mark buttons + sub-line generation) | shipped | `57334f0` |
| 16d-2a/b | Sub-line-aware simulation (`line_data` keyed by `(line_num, sub_line_id)`) | shipped | `bdaf48e` → `1d3e9ca` |
| 17a | PDF export module + tests | shipped | `8ed8719` |
| 17b | Create Report button + preview dialog | shipped | `b4dd0e9` |
| 17d.1–d.7 | Cartography, table, legend, grid, scale bar, line labels | shipped | `822c930` |
| **17c** | **Docs rewrite for Phase 17 (`phase_17_lookahead_pdf.md`) + SMOKE_TEST entry** | **outstanding** | — |

Phase 17 field-accepted as "good enough for seismic" by the chief navigator.

---

## Where to resume at home

### 1. Outstanding (greenlit, just not done)
- **Phase 17c docs** — rewrite `docs/refactor/phase_17_lookahead_pdf.md`
  to match what actually shipped (17a/b/d1–d7), then add a Phase 17
  entry to `docs/SMOKE_TEST.md`. The cartography knob map is already
  captured in `docs/refactor/phase_17_cartography_notes.md` — reuse it.

### 2. Deferred Phase-17 ideas (not built, not greenlit — interview user first)
- Time-of-day markers every 6 h along the route
- Rig-name labels (P-53, SS-75, …) next to safety circles
- Plan-summary info box (total km / total h / line count)
- START / END pins
- Acquisition-direction chevrons on the path
- Scale-bar units dropdown (km / NM)

### 3. Tuning hot spots
- Native `Optimized_Path` line-number labels live in
  `_apply_path_labeling` in `obn_planner_dockwidget.py` — **not** in
  `services/pdf_export.py`. Phase 17d.7 briefly added a duplicate
  overlay and reverted it (commit `822c930`); do not reintroduce.
- PDF layout lives end-to-end in `services/pdf_export.py` (1,426 lines).
- Preview dialog is `pdf_export_dialog.py`.

---

## Code map

```
obn_planner/
  obn_planner.py                    # QGIS plugin entry (232 lines)
  obn_planner_dockwidget.py         # Main dock + handlers (12,243 lines — still the god class)
  sequence_edit_dialog.py           # Sequence editor modal
  pdf_export_dialog.py              # Report preview modal (17b+)
  rrt_planner.py                    # RRT deviation algorithm
  dubins_path.py                    # Dubins curves (minimum-turn-radius paths)

  services/                         # Non-Qt business logic
    simulation_service.py           # Sequence → timing orchestration
    sequence_service.py             # Racetrack / Teardrop generators
    deviation_geometry.py           # Deviation-line construction
    line_metadata.py                # Operation / FGSP / LGSP schema
    ortools_optimizer.py            # VRP-style sequence optimiser
    ortools_task.py                 # Background OR-tools worker
    turn_cache.py                   # Memoised Dubins turns
    pdf_export.py                   # A4 landscape report renderer (Phase 17)

  io_sps/                           # SPS parsing
    sps_parser.py
    sps_spec.py
    line_aggregation.py

  test/                             # 15 test modules (pure-Python + QGIS)
  vendor/                           # Vendored ortools 9.14.6206 (numpy-pinned)
  docs/
    ARCHITECTURE.md
    SMOKE_TEST.md
    refactor/phase_*.md             # Per-phase plan docs
```

---

## Key workflow the chief runs

1. **Import SPS** → filter lines / set status (`To Be Acquired` is the
   gate for lookahead).
2. **Mark SP ranges** (Acquired / Not Acquired) on a parent line — Phase
   16c. Multiple ranges can split a parent into sub-lines.
3. **Generate Lookahead Lines** — emits `Lookahead_Lines` with run-ins
   and sub-line IDs (Phase 16d).
4. **Run Simulation** (Racetrack / Teardrop, OR-tools on by default) —
   emits `Optimized_Path` with `LineNum`, `SubLineId`, `Operation`,
   `FGSP`, `LGSP`, `Heading`, `StartTime`, `EndTime`.
5. **Edit Plan** — sequence editor lets the chief tweak per-line
   direction and metadata.
6. **Create Report** — preview dialog + one-click A4-landscape PDF
   (map page + sequence table page).

---

## Developer setup

### Onboard environment (Windows / QGIS 3.40 bundled Python)
- Plugin lives in
  `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\obn_planner\`.
- `vendor/` contains ortools 9.14.6206 (pinned below 9.15 to keep
  numpy 1.x — see memory note `project_ortools_vendor_pin.md`).
- `sitecustomize.py` + `o4w_env.bat` hand-edits are required to stop
  QGIS's bundled Python from loading the user-site numpy 2.4.4. Any
  QGIS reinstall breaks this — re-apply from memory note
  `qgis_user_site_isolation.md`.

### Tests
```
# Pure-Python (no QGIS required)
python -m pytest test/test_line_metadata.py test/test_dubins.py \
                 test/test_sequence_service.py test/test_simulation_service.py \
                 test/test_line_aggregation.py test/test_sps_parser.py \
                 test/test_ortools_optimizer.py test/test_pdf_export.py \
                 test/test_deviation_geometry.py test/test_turn_cache.py

# QGIS-dependent (run inside QGIS Python or with PYTHONPATH to qgis)
# test_obn_planner_dockwidget.py, test_resources.py, test_qgis_environment.py
```

### Git workflow used so far
- Conventional prefix + phase label in the subject:
  `phase 17d.6: group reordering, page count, smaller legend entries, slim scale bar`.
- HEREDOC body with `Co-Authored-By: Claude Opus 4.7 (1M context)` trailer.
- Git author passed per-invocation or set locally — the repo does not
  ship a committed identity.

---

## Plan docs index (`docs/refactor/`)

| File | Phase | Status |
|---|---|---|
| `phase_0_safety_net.md` | 0 | done |
| `phase_1_dubins_units.md` | 1 | done |
| `phase_2_deviation_picker.md` | 2 | done |
| `phase_3_sps_multiformat.md` | 3 | done |
| `phase_4_sps_direction.md` | 4 | done |
| `phase_5_services_lightweight.md` | 5 | done |
| `phase_6_services_orchestration.md` | 6 | done |
| `phase_7_services_qgis_heavy.md` | 7 | done |
| `phase_8_ui_split.md` | 8 | done |
| `phase_9_cleanup.md` | 9 | done |
| `phase_10_performance.md` | 10 | done |
| `phase_13_ortools.md` | 13 | done |
| `phase_16_line_management.md` | 16 (a–d, d-2a/b) | done |
| `phase_17_lookahead_pdf.md` | 17 | **stale — rewrite for 17c** |
| `phase_17_cartography_notes.md` | 17 knob map | current |

---

## Core algorithms (reference)

- **RRT** (`rrt_planner.py`) — grows a tree around No-Go zones to find a
  feasible deviation when a straight line is blocked.
- **Dubins path** (`dubins_path.py`) — shortest path between two posed
  points respecting a minimum turning radius. Used for line-to-line
  turns and as the cost function in the OR-tools optimiser.
- **OR-tools VRP** (`services/ortools_optimizer.py`) — solves the
  line-ordering problem as a vehicle-routing problem over a Dubins
  cost matrix. Default on; threaded with cost progress and
  auto-stop-on-plateau.

---

## References
- [PyQGIS Developer Cookbook](http://www.qgis.org/pyqgis-cookbook/index.html)
- [RRT](https://en.wikipedia.org/wiki/Rapidly-exploring_random_tree)
- [Dubins path](https://en.wikipedia.org/wiki/Dubins_path)
- [Google OR-tools VRP](https://developers.google.com/optimization/routing)

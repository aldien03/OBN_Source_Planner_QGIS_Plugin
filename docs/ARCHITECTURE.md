# OBN Planner Architecture

**Status:** stub — to be filled in during Phase 6 after the revamp completes.

## Current architecture (pre-revamp, 2026-04-17)

One god class holds UI + business logic + algorithm orchestration.

```
obn_planner/
  obn_planner.py                    # 230 lines — QGIS plugin entry point
  obn_planner_dockwidget.py         # 10,448 lines — EVERYTHING else
  obn_planner_dockwidget_base.ui    # Qt Designer definition
  obn_planner_dockwidget_base_ui.py # auto-generated
  obn_planner_dockwidget_ui.py      # additional compiled UI
  sequence_edit_dialog.py           # 625 lines — sequence editor dialog
  rrt_planner.py                    # 528 lines — RRT algorithm
  dubins_path.py                    # 504 lines — Dubins curves (with module globals)
  fixed_function.py                 # 289 lines — DEAD CODE, to be deleted
  test/                             # 6 tests, 1 broken, ~0 coverage of core logic
  backups/                          # churn indicator: 297 KB old dockwidget
```

Call flow (simplified):
```
handle_run_simulation
  → _gather_simulation_parameters
  → _prepare_line_data
  → (deviation call currently commented out)
  → Racetrack branch OR Teardrop branch
      → _generate_interleaved_racetrack_sequence | _determine_next_line
      → _calculate_sequence_time
          → _get_cached_turn → dubins_calc.get_curve
  → _reconstruct_path
  → _visualize_optimized_path
```

Known issues:
- `dubins_path.py:11-13` — three module-level mutable globals mutated by RRT, incompletely restored
- Two parallel deviation algorithms (v1 RRT at `:2647`, v2 Peak/Tangent at `:3422`)
- Heading units inconsistent — radians at Dubins entry, degrees inside `get_projection`, reconstructed via `atan2` in RRT
- Five `self.last_*` fields leak simulation state across handler methods
- `_parse_sps_file_content` (`:538`) hardcodes SPS column positions with no spec backing
- 25+ magic-string comparisons of acquisition mode / heading option
- `print()` statements in `rrt_planner.py` and `dubins_path.py` bypass the log infrastructure

## Target architecture (post-revamp)

*Filled in during Phase 9. Draft layout is in `docs/refactor/README.md`.*

Layered structure:
- `geometry/` — pure math, no Qt
- `io/` — file I/O, QGIS layer writing, no Qt
- `services/` — algorithm orchestration, no Qt widgets
- `ui/` — widgets, dialogs, handlers
- `obn_planner_dockwidget.py` shrinks to signal/slot wiring only (<2000 lines)

Dependency rule (enforced by review, not by tooling):
```
ui  ───────────────→ services ─→ io
 │                      │        ↓
 └──→ geometry ←────────┘      (may use qgis.core)
                  (pure math, no qgis required for geometry/dubins.py)
```

### Service DAG (draft)

```
simulation_service
  ├─→ deviation_service
  ├─→ sequence_service
  ├─→ turn_cache ─→ geometry.dubins
  ├─→ path_reconstructor
  └─→ visualization
```

No cycles. Each service is instantiated by the handler that calls it, not held as dockwidget state.

## Layering enforcement checklist

During review, reject imports that violate these rules:

- [ ] `geometry/dubins.py` does not import `qgis.*` or `PyQt*`
- [ ] `geometry/rrt.py` may import `qgis.core` only
- [ ] `io/*.py` may import `qgis.core` only (no `PyQt*.QtWidgets`)
- [ ] `services/*.py` may import `qgis.core` only (no `PyQt*.QtWidgets`)
- [ ] `ui/*.py` is the only layer that imports `PyQt*.QtWidgets` or `PyQt*.QtCore.Qt`
- [ ] No service imports from `ui/`
- [ ] No two services import each other (DAG, not graph)

## QGIS version target

- **Current:** `qgisMinimumVersion=3.0` (`metadata.txt`)
- **Target post-Phase-0:** `qgisMinimumVersion=3.40` (Bratislava LTR)

Implication: defensive `AttributeError` fallbacks for APIs that existed in 3.0 but were renamed later (e.g., `QgsWkbTypes.isSurface` block at `obn_planner_dockwidget.py:121-134`) can be replaced with direct calls in Phase 4 when those helpers move to `geometry/wkb_helpers.py`. Don't pre-simplify in Phase 0 — the bump itself is the only metadata change; code cleanup follows the layered migration.

## Deployment

Currently two deploy paths exist:
- `pb_tool deploy` — uses `pb_tool.cfg`; currently lists only 3 python files and no extra_dirs (broken for multi-module layout — Phase 4 will fix)
- `make deploy` — uses `Makefile`; typically copies the whole tree

Post-revamp both must be verified to copy the new subdirectories. See `docs/refactor/phase_4_services_extract.md` for the packaging fix.

## Testing tiers

| Tier | Location | Runs without QGIS? | When to run |
|---|---|---|---|
| Pure-math | `test/test_dubins.py`, `test_rrt_fake_obstacles.py`, `test_sps_parser.py`, `test_sequence_service.py`, `test_turn_cache.py` | Yes | Every commit |
| QGIS-dependent | `test/test_deviation_service.py`, `test_obn_planner_dockwidget.py` | No (needs `get_qgis_app`) | Before merging any phase |
| Manual smoke | `docs/refactor/SMOKE_TEST.md` checklist | Human in QGIS | Before every merge |

No CI pipeline currently. Tiers 1 can be added to CI later without touching test code.

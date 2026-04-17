# OBN Planner — Maintainability Revamp

**Status:** Planning complete, awaiting user sign-off to begin Phase 0.
**Owner:** aldien03@gmail.com
**Plan authored:** 2026-04-17

---

## Context

The OBN Planner QGIS plugin works but has accumulated severe structural debt after heavy churn. Symptoms confirmed in code:

- **Bugs in deviation / RRT paths.** v1 RRT deviation (`obn_planner_dockwidget.py:2647-2899`) produces incorrect paths (confirmed by user). Deviations disabled in `handle_run_simulation` by commented-out calls at `:6723-6741`. v2 Peak/Tangent at `:3422` is the canonical algorithm. Separately, `dubins_path.py:11-13` has three mutable globals that `rrt_planner.py:138-147` incompletely restores, causing silent run-to-run drift.
- **Hard to modify or extend.** `obn_planner_dockwidget.py` is a **10,448-line god class** with five methods over 300 lines (largest: `_calculate_and_apply_deviations_v2` at 463 lines). Five `self.last_*` fields leak implicit state across handlers.
- **Brittle SPS import.** The current parser (`:577-580`) hardcodes column slices that are **demonstrably broken** on real vendor files. `int(line_num_str)` at `:587` throws `ValueError` on Martin Linge's decimal line numbers (e.g., `"2431.0"`). The user receives SPS files from TGS, PXGEO, SAE, and others — all with inconsistent formats.

## Scope (user-confirmed)

- **Primary goal:** maintainability refactor — break up god class, remove duplication, fix unit ambiguity, add tests.
- **Added scope (2026-04-17):** multi-format SPS support (auto-detection, per-vendor specs) and "Follow previous shooting direction" feature (both Racetrack and Teardrop).
- **UI policy:** minor improvements allowed (progress bars, error dialogs, two new controls for the new features). No layout redesign.
- **Out of scope for Phases 0-9:** threading, new algorithms beyond direction-following, AIS (abandoned), general feature development.
- **Deferred to Phase 10 (post-refactor backlog):** performance improvements — spatial indexing, batch feature commits, geometry simplification for rendering, render caching, QThread for long ops, profile-driven Python wins. Added 2026-04-17 at user request. See [phase_10_performance.md](phase_10_performance.md).
- **Deliverable:** this master plan plus one markdown file per phase in `docs/refactor/`.

## Resolved decisions (2026-04-17)

1. **Deviation algorithm:** v2 Peak/Tangent survives. v1 RRT is deleted. User reason: *"RRT delivers incorrect deviation route on v1."*
2. **AIS:** `backups/ais_live_tracker.py` abandoned — deleted in Phase 9.
3. **Doc location:** `docs/refactor/` at repo root.
4. **QGIS version floor:** bump from 3.0 to **3.40.5 (Bratislava LTR)** in Phase 0.
5. **Phase structure:** 10 phases (0-9) for tight hard-stop granularity (user: *"we need to do it right"*).
6. **Multi-format SPS:** elegant spec-registry design. Ships with specs for SPS 1.0, SPS 2.1 (Shell reference), SPS 2.1+direction (Martin Linge), PXGEO, TGS, SAE. Extensible via `io/sps_spec.py` without code changes for future vendors.
7. **Direction-following:** works for **both** Racetrack and Teardrop. Assumes per-line direction uniformity in SPS data.
8. **Hard stops:** Claude stops after every phase and awaits explicit user approval before starting the next. No auto-advance even when tests pass.

## Target architecture

```
obn_planner/
  obn_planner.py                    # QGIS entry point — unchanged
  obn_planner_dockwidget.py         # UI class only — target <2000 lines
  obn_planner_dockwidget_base.ui    # Qt Designer source
  obn_planner_dockwidget_base_ui.py # auto-generated
  metadata.txt, icon.png, resources.*

  geometry/                         # pure math, no Qt, minimal qgis.core
    dubins.py                       # from dubins_path.py — no module globals
    rrt.py                          # from rrt_planner.py — (kept for future use, may delete in P9)
    angles.py                       # normalize_angle, deg<->rad
    wkb_helpers.py                  # is_surface_type / is_point_type / is_line_type

  io/                               # file I/O and layer writing; no Qt widgets
    sps_spec.py                     # SpsColumnSpec + known spec registry
    sps_parser.py                   # parse_sps() + auto-detect
    gpkg_writer.py                  # GeoPackage helpers
    xlsx_export.py                  # Sequence XLSX export via xlsxwriter

  services/                         # orchestration; qgis.core OK, no QtWidgets
    turn_cache.py                   # Phase 5
    sequence_service.py             # Phase 5 (+ direction logic in P6)
    simulation_service.py           # Phase 6 — core orchestration
    path_reconstructor.py           # Phase 7
    visualization.py                # Phase 7
    line_generator.py               # Phase 7
    deviation_service.py            # Phase 7

  ui/                               # Qt widgets allowed here only
    constants.py                    # AcquisitionMode, HeadingOption enums
    progress.py                     # QProgressDialog context manager
    error_dialog.py                 # show_error / show_warning
    dialogs/
      sequence_edit_dialog.py       # moved from repo root
    handlers/
      import_handlers.py            # handle_sps_import (with format selector)
      generate_handlers.py
      simulation_handlers.py        # handle_run_simulation (wires direction checkbox)
      status_handlers.py

  test/
    existing files kept
    test_dubins.py                  # Phase 1
    test_rrt_fake_obstacles.py      # Phase 1
    test_sps_parser.py              # Phase 3 (extended in P4 for direction)
    test_line_aggregation.py        # Phase 4
    test_sequence_service.py        # Phase 5 (extended P6)
    test_turn_cache.py              # Phase 5
    test_simulation_service.py      # Phase 6
    test_path_reconstructor.py      # Phase 7
    test_deviation_service.py       # Phase 7
    test_line_generator.py          # Phase 7
    test_ui_constants.py            # Phase 8
    fixtures/
      sample_martin_linge.sps
      sample_pxgeo.s01
      sample_short_lines.sps

  docs/
    ARCHITECTURE.md
    CHANGELOG.md                    # created in Phase 9
    refactor/
      README.md                     # this file
      phase_0_safety_net.md
      phase_1_dubins_units.md
      phase_2_deviation_picker.md
      phase_3_sps_multiformat.md
      phase_4_sps_direction.md
      phase_5_services_lightweight.md
      phase_6_services_orchestration.md
      phase_7_services_qgis_heavy.md
      phase_8_ui_split.md
      phase_9_cleanup.md
      phase_10_performance.md         # post-refactor backlog (not auto-advanced)
      SMOKE_TEST.md
```

**Layering rule (enforced by `import-linter` in Phase 9, reviewed manually before that):**
- `geometry/dubins.py` must be importable without QGIS.
- `io/` may import `qgis.core` only; no `QtWidgets`.
- `services/` may import `qgis.core` only; no `QtWidgets`; no `ui/`.
- `ui/` is the only layer that touches `QtWidgets`.

## Phase summary

| # | Phase | Size | Risk | Blocker |
|---|---|---|---|---|
| [0](phase_0_safety_net.md) | Safety net — fix broken test, Dubins golden tests, QGIS 3.40 bump | small | low | — |
| [1](phase_1_dubins_units.md) | Dubins globals removal + unit convention documentation | small/med | low | Phase 0 |
| [2](phase_2_deviation_picker.md) | Delete v1 RRT deviation; keep v2 Peak/Tangent; delete `fixed_function.py` | medium | medium | — |
| [3](phase_3_sps_multiformat.md) | **SPS multi-format infrastructure** (spec registry + auto-detect + fix real-file bugs) | medium/large | medium | Phase 0 |
| [4](phase_4_sps_direction.md) | **SPS direction column + PREV_DIRECTION field** (no behavior change yet) | small | low | Phase 3 |
| [5](phase_5_services_lightweight.md) | Services extract — turn_cache + sequence_service (pure-Python, high test coverage) | medium | low/med | Phases 0-4 |
| [6](phase_6_services_orchestration.md) | Services extract — simulation_service + dataclasses + **direction-following feature** + `self.last_*` cleanup | large | **high** | Phases 4, 5 |
| [7](phase_7_services_qgis_heavy.md) | Services extract — path_reconstructor, visualization, line_generator, deviation_service + packaging fix | large | med/high | Phase 6 |
| [8](phase_8_ui_split.md) | UI split + SPS format selector + Follow-direction checkbox + light polish | medium | medium | Phases 5-7 |
| [9](phase_9_cleanup.md) | Cleanup — no `print()`, dead code, import-linter, final docs | small | low | Phases 0-8 |
| [10](phase_10_performance.md) | **Performance backlog** — spatial indexing, batch commits, geometry simplification, render caching, QThread, profile-driven optimization. **Explicitly requested only; not auto-advanced.** | TBD | medium | Phases 0-9 complete |

Each phase is independently shippable: the plugin loads, buttons work, tests pass at the end of each. **No auto-advance — Claude stops and awaits user approval between every phase.**

## Execution protocol (hard stops)

1. I implement exactly one phase.
2. I run `pytest test/` and report results.
3. I update the phase doc's verify checklist with actual results.
4. I summarize the changes and tell you: "Phase N complete. Verify on your end. Reply 'proceed to Phase N+1' to continue."
5. **I do not touch the next phase until you reply with explicit approval.**
6. If verification fails on your side, I fix the current phase — I do not move on.

## Testing strategy

- **Framework:** `unittest` for existing tests (preserved unchanged); `pytest` as the runner. Add `pytest` to dev tools.
- **Three tiers:**
  1. **Pure-math** — runs anywhere without QGIS. Covers `geometry/dubins`, `io/sps_parser`, `services/sequence_service`, `services/turn_cache`, `ui/constants`.
  2. **QGIS-dependent** — uses `get_qgis_app()` from `test/utilities.py`. Covers `deviation_service`, `simulation_service`, `line_generator`, `path_reconstructor`.
  3. **Manual smoke** — see [SMOKE_TEST.md](SMOKE_TEST.md). You run this at every hard-stop gate.
- **Layering enforcement** — `import-linter` in Phase 9; manual review before that.

## Critical files (absolute paths)

- `obn_planner_dockwidget.py` — primary refactor target (10,448 lines → <2000)
- `dubins_path.py` → `geometry/dubins.py` (Phase 1 fixes + Phase 7 move)
- `rrt_planner.py` → `geometry/rrt.py` or deleted (Phase 7 decision)
- `fixed_function.py` — deleted in Phase 2
- `sequence_edit_dialog.py` → `ui/dialogs/sequence_edit_dialog.py` (Phase 8)
- `metadata.txt` — QGIS min version bump in Phase 0
- `pb_tool.cfg` — packaging fix in Phase 7 (`extra_dirs` must include new subdirectories)
- `Makefile` — VERIFY in Phase 7 whether it needs the same updates

## Existing utilities to reuse (do not rewrite)

- `obn_planner_dockwidget.py:121-134` — WKB type helpers → `geometry/wkb_helpers.py` (simplified in Phase 7 with 3.40 API guarantee)
- `rrt_planner.py:46-57` — `calculate_distance_euclidean`, `normalize_angle` → `geometry/angles.py`
- `sequence_edit_dialog.py` `custom_deepcopy` — moves with the dialog
- `obn_planner_dockwidget.py:38-59` — existing logging setup — extend, don't rebuild
- `test/utilities.py`, `test/qgis_interface.py` — existing QGIS test harness

## Cross-phase risks

Phase-specific risks are in each phase doc. These apply across phases:

- **Unit convention at Dubins call sites** — verify `start_heading_math` / `end_heading_math` at `:8121-8126` are radians (not degrees). Must trace computation origin before Phase 1.
- **`pb_tool.cfg` packaging reality** — only 3 python files listed; `extra_dirs` empty. Phase 7 is blocked until this is fixed and verified on both deploy paths.
- **Saved-state compatibility** — if users have saved QGIS projects with literal "Racetrack" / "Teardrop" strings, Phase 8 enum `.value` MUST match exactly.
- **SPS column positions for TGS and SAE** — Phase 3 ships placeholder slices. Must be verified against real sample files (`Production_SX_Preplot_Valhall_1.1.s01` and `Norway_TGS_HeimdalOBN_*.sps`) before Phase 3 is signed off.
- **Shell SPS 2.1 official document** — required for `SPS_2_1_SHELL` spec correctness. If not available during execution, mark as "VERIFY" and ship with best-effort slices based on the SEG SPS 2.1 convention.
- **CI availability** — no CI visible. Pure-math tier runs anywhere; QGIS tier is local-only. Consider GitHub Actions in a post-revamp task.

## Sample files referenced in this plan

- `D1v1_MartinLindge_260410_sailline.sps` — primary real-world sample, verified in plan drafting. Shows the SPS 2.1+direction variant with per-point `PREV_DIRECTION` at slice `[80:86]`.
- `MT3007924_MMBC_SRC_20250316_combined_saillines.s01` — PXGEO sample, verified. Headerless, integer line/SP.
- `Production_SX_Preplot_Valhall_1.1.s01` — TGS sample. Referenced by user but not yet read by planner. Phase 3 execution must sample the ruler and first data lines.
- `Norway_TGS_HeimdalOBN_Opt3v3_Ditherv3_Pull_Push.sps` — SAE sample. Referenced by user but not yet read by planner. Same.

## Open non-blocker items

- Shell SPS 2.1 spec doc not yet procured. Phase 3 accommodates by leaving `SPS_2_1_SHELL` slices as "VERIFY" and shipping the Martin Linge / PXGEO specs (which ARE verified) as the primary working specs.
- Documentation (`help/`) is untouched — plugin docs remain as-is. If user-facing Sphinx docs are desired, that's a separate post-revamp effort.

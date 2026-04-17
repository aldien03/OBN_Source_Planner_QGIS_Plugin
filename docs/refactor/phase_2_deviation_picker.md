# Phase 2 — Delete v1 RRT deviation; keep v2 Peak/Tangent

**Size:** medium
**Risk:** medium (large deletion; irreversible without `git revert`)
**Blocks:** Phase 4 (deviation service needs one canonical algorithm)
**Blocked by:** Phase 1 should land first (cleaner Dubins foundation); not strictly required

## Decision (resolved 2026-04-17)

**v2 survives. v1 is deleted.**

User confirmation: *"RRT delivers incorrect deviation route on v1."* v1's RRT-based approach produces wrong paths; v2's Peak/Tangent geometric approach is the canonical algorithm going forward.

## Context

Today there are **two different deviation algorithms** in the codebase:

| Version | Location | Approach | Signature | Caller | Fate |
|---|---|---|---|---|---|
| v1 | `obn_planner_dockwidget.py:2647-2899` (253 lines) | RRT via `rrt_planner.find_rrt_path` | `(line_data: dict, nogo_layer, clearance_m, turn_radius_m, vessel_turn_rate_dpm=180.0) -> dict` | Commented out at `:6735` | **DELETE** |
| v2 | `obn_planner_dockwidget.py:3422-3884` (463 lines) | Peak/Tangent (geometric) | `(lines_layer: QgsVectorLayer, nogo_layer, clearance_m, turn_radius_m, debug_mode=False) -> bool` | "Calculate Deviations" button at `:1996` | **KEEP & RENAME** |

They are not duplicates — different algorithms, different input types, different return types.

Separately, `fixed_function.py` is dead code: nothing imports it, and its `self._calculate_and_apply_deviations_rrt` reference at line 40 names a method that doesn't exist anywhere in the codebase.

## Files touched

### Deletions

- `obn_planner_dockwidget.py:2647-2899` — delete `_calculate_and_apply_deviations` (v1, 253 lines).
- `obn_planner_dockwidget.py:6723-6741` — delete the commented-out call block in `handle_run_simulation`.
- `fixed_function.py` — delete entire file.
- `CLAUDE.md:144` — remove "Fixed Functions" bullet.

### Renames

- `obn_planner_dockwidget.py:3422` — rename `_calculate_and_apply_deviations_v2` → `_calculate_and_apply_deviations`.
- Update its caller at `obn_planner_dockwidget.py:1996`.

### Keep for now

- `backups/obn_planner_dockwidget.py.bak` — leave in place (already in `backups/`).
- `backups/ais_live_tracker.py` — handled in Phase 6, not here.

## v2 helpers to preserve

These are called from v2 (`_calculate_and_apply_deviations_v2`) and must NOT be deleted:
- `_calculate_intermediate_components` (`:2035`, 353 lines)
- `_process_conflicted_lines` (`:4065`, 348 lines)
- `_complete_deviation_calculation` (`:4413`, 369 lines)
- `_merge_line_segments` (`:4782`)
- `self.all_reference_lines` / `self.all_peaks` initialization at `:3440-3441`

**VERIFY before Phase 4 extraction:** `grep all_reference_lines` and `grep all_peaks` to confirm they're only read inside v2's call chain. If read elsewhere, those readers must be rewired when v2 moves into `services/deviation_service.py`.

## RRT code disposition

v1 is deleted in this phase. `rrt_planner.py` itself is **not deleted** — it contains general-purpose RRT + Dubins infrastructure that may be reused in future, and Phase 1 fixes still apply. However after Phase 2, `rrt_planner.py` will have **zero callers in production code** (its only caller was v1 at `:2822`).

Decision needed before Phase 4: either
- (a) **Keep `rrt_planner.py`** as unused infrastructure for future use — migrate to `geometry/rrt.py` per the target architecture anyway. Tests from Phase 1 remain valid.
- (b) **Delete `rrt_planner.py`** since nothing uses it. Simpler, less dead code.

**Recommendation (a)** — the Phase 1 unit tests already cover it, and deleting working tested code just because it's currently unused is wasteful. Revisit at end of revamp if no future use emerges.

## Tests added

### `test/test_deviation_service.py` (new)

Happy-path integration test. Uses `get_qgis_app()` from `test/utilities.py`:

- Construct a `QgsVectorLayer` in memory with 3 short survey lines (2 that don't cross a no-go, 1 that does).
- Construct a `QgsVectorLayer` polygon layer with one no-go rectangle.
- Call the surviving `_calculate_and_apply_deviations`.
- Assert: the 2 non-crossing lines are unchanged, the crossing line has deviation fields populated (exact field names depend on which algorithm survives).

This is a smoke test — it does NOT assert geometric correctness in detail. Manual QA covers that.

## Verify

1. `grep _calculate_and_apply_deviations` returns exactly one definition and one caller.
2. `grep fixed_function` returns 0 matches outside `CLAUDE.md` (which this phase updates).
3. `grep _calculate_and_apply_deviations_v2` returns 0 matches.
4. `grep _calculate_and_apply_deviations_rrt` returns 0 matches.
5. QGIS smoke test: Calculate Deviations on a real project. Deviation geometry is visually identical to the Phase 1 baseline.
6. Simulation still runs (it never called the deviation code anyway).
7. `pytest test/test_deviation_service.py` green.

## Rollback

Single `git revert` restores both algorithms and `fixed_function.py`. Because the deletions span several hundred lines across a single commit, plan for this phase as one reviewable commit.

## Risks and unknowns

- **Saved project attribute dependency** — if QGIS projects already on users' disks have a field populated by v1 with a specific name not populated by v2, reopening those projects might show a "missing field" warning. Unlikely (both add similar fields) but include in smoke test.
- **`fixed_function.py` has an obsolete import chain** — confirmed nothing imports it via `grep fixed_function` (only matches: `CLAUDE.md:144` and its own contents). Deletion is safe.
- **`rrt_planner.py` becomes unused** — after this phase, nothing calls `find_rrt_path` from production code. Per recommendation above, keep the module for potential future use (move to `geometry/rrt.py` in Phase 7). Revisit at Phase 9 if it's still orphaned.

## Hard Stop Gate

Phase 2 is complete when:
1. `grep _calculate_and_apply_deviations` returns exactly one definition and one caller.
2. `grep fixed_function` returns 0 matches outside `CLAUDE.md`.
3. QGIS smoke test: Calculate Deviations on a real project — geometry output visually matches Phase 1 baseline.
4. `pytest test/test_deviation_service.py` green.

**Claude MUST stop after Phase 2 and await explicit "proceed to Phase 3" from user. Do not auto-advance.**

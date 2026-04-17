# Phase 1 — Dubins globals removal + unit clarity

**Size:** small/medium
**Risk:** low (pure parameter plumbing; no math changes)
**Blocks:** Phase 2, 3, 4, 6 benefit from this but are not strictly blocked
**Blocked by:** Phase 0 complete (need baseline smoke tests to verify no drift)

## Goal

Eliminate the three module-level mutable globals in `dubins_path.py` that are mutated by `rrt_planner.py` and incompletely restored, causing silent run-to-run drift. Document the unit convention so the degrees-vs-radians ambiguity that has produced bugs in the past becomes explicit.

## Root cause

- `dubins_path.py:11-13` declares `MAX_LINE_DISTANCE`, `MAX_CURVE_DISTANCE`, `MAX_CURVE_ANGLE` as module globals initialized to `0.0`.
- `rrt_planner.py:138-142` mutates all three before calling `dubins_path.get_projection()`.
- `rrt_planner.py:147` restores only `MAX_LINE_DISTANCE` and `MAX_CURVE_ANGLE` — `MAX_CURVE_DISTANCE` leaks permanently after any RRT call.
- `dubins_path.get_curve()` (line 470) separately mutates the same globals via `global` declaration.
- `get_projection()` and `split_*()` read the globals directly (`dubins_path.py:253, 272, 290, 308, 324`).
- `obn_planner_dockwidget.py:89-91` has a defensive block that sets `dubins_calc.MAX_LINE_DISTANCE = 10.0` if it doesn't exist — proof that this has broken in the past.

Separately, unit convention:
- `dubins_path()` (line 420) takes and returns angles in **radians**.
- `get_projection()` (line 220) outputs `[x, y, heading_deg]` — heading is in **degrees** after internal conversion (line 250, 269, 287, 305: `math.degrees(...)`).
- `split_arc` (line 105) works in degrees internally.
- `rrt_planner.py:165-173` has a comment debating which unit — the code currently ignores the projected heading and uses `atan2(dy, dx)` which is radians.

## Files touched

### `dubins_path.py`

- **Remove** module globals at lines 11-13.
- **Change** `get_projection(start, end, solution)` signature (line 220) to:
  ```
  get_projection(start, end, solution, max_line_distance, max_curve_angle, max_curve_distance)
  ```
  Replace references at lines 253, 272, 290, 308, 324 with the parameter names.
- **Change** `get_curve(s_x, s_y, s_head, e_x, e_y, e_head, radius, max_line_distance)` (line 470):
  - Remove `global` declaration at line 491.
  - Compute locally:
    ```python
    max_curve_distance = max_line_distance
    max_curve_angle = (max_curve_distance * 360) / (2 * math.pi * radius) if radius > 1e-3 else 90.0
    ```
  - Pass explicitly: `get_projection(start, end, solution, max_line_distance, max_curve_angle, max_curve_distance)`.
- **Add** module-level docstring (line 1):
  ```
  """
  Dubins path math. All PUBLIC function signatures use RADIANS for heading.
  Internal arc geometry is expressed in degrees (because circle angles are
  traditionally degrees) and converted at the boundary:
    - split_angle / split_arc / tangent_angle take degrees
    - get_projection output: [x, y, heading_DEG]
  Callers that want radians must convert get_projection output explicitly.
  """
  ```

### `rrt_planner.py`

- **Delete** lines 137-147 (the "temporarily set globals" block and the restore).
- **Replace** the call at line 144 with:
  ```python
  projected_points = dubins_path.get_projection(
      start=start_pose,
      end=end_pose_target,
      solution=solution,
      max_line_distance=proj_max_line_dist,
      max_curve_angle=proj_max_curve_angle,
      max_curve_distance=proj_max_curve_dist,
  )
  ```
- **Add** comment at line 165 documenting that `projected_points[i][2]` is `heading_deg`, and that the `atan2(dy, dx)` reconstruction at line 173 is the canonical heading in radians (robust to accumulated error and unit mismatch).

### `obn_planner_dockwidget.py`

- **Delete** lines 89-91 (the defensive `hasattr(dubins_calc, 'MAX_LINE_DISTANCE')` block). Nothing reads the module globals after this phase.

## Tests added

### `test/test_dubins.py` (new)

- `test_module_has_no_mutable_globals` — `hasattr(dubins_path, 'MAX_LINE_DISTANCE')` is False (or the attribute is missing after import).
- `test_get_curve_no_side_effects` — call `get_curve` twice with different `max_line_distance` values; the second call's output must reflect its own parameter, proving there's no shared state.
- `test_get_projection_accepts_params` — vary `max_line_distance` from 5 to 50; point count should scale inversely.
- `test_get_curve_concurrent_isolation` — spawn two threads, each calling `get_curve` with a distinct `max_line_distance`; both see their own result. Uses `threading.Thread`; no real QGIS.

### `test/test_rrt_fake_obstacles.py` (new)

- `test_rrt_no_obstacles_direct_path` — start `(0, 0, 0)`, goal `(1000, 0, 0)`, empty obstacle list, radius 50. Assert returned `QgsGeometry` is not None and has length within 10% of 1000.
- `test_rrt_avoids_simple_square_obstacle` — construct a `QgsGeometry.fromPolygonXY` forming a 200m square between start and goal. Assert returned geometry is not None and `geom.intersects(obstacle) == False`.

Note: QGIS's `QgsGeometry` can be constructed in isolation via `QgsGeometry.fromPolygonXY(...)` without a full `QgsProject` — these tests live in the pure-math tier but import `qgis.core`. If the test runner doesn't have `qgis.core` available, mark them with `pytest.importorskip("qgis.core")`.

## Verify

1. `pytest test/` — all previously green tests still green; new Dubins and RRT tests pass.
2. Phase 0 smoke test re-runs: Dubins golden values match exactly (characterization unchanged).
3. QGIS smoke test: import sample SPS, generate lines, run simulation both modes. Total time in hours matches Phase 0 baseline (the `MAX_CURVE_DISTANCE` leak may have caused minor run-to-run drift; if so, expect a one-time small delta then stable).
4. Visually confirm turn geometries look identical.

## Rollback

Single `git revert`. Globals come back. RRT returns to "temporarily mutate globals" state.

## Risks and unknowns

- **Heading unit at call sites** — `obn_planner_dockwidget.py:8121-8126` calls `dubins_calc.get_curve(s_head=start_heading_math, e_head=end_heading_math, ...)`. I did NOT trace where `start_heading_math` and `end_heading_math` are computed. Phase 1 execution must grep backwards and verify they're in radians (as `dubins_path` expects) before trusting the call.
- **`atan2` heading reconstruction** — `rrt_planner.py:173` uses `math.atan2(dy, dx)` to compute heading from consecutive projected points. This is in radians and correct regardless of what unit `get_projection` returns — which is why the code works despite the apparent mismatch. Don't change it; just document it.
- **Silent drift** — the `MAX_CURVE_DISTANCE` leak may have been causing paths to shorten/lengthen slightly between runs. If Phase 1 produces a one-time change in total simulation time, that's expected and correct (the leak is now fixed). Document the delta if it occurs.

## Hard Stop Gate

Phase 1 is complete when:
1. All Phase 0 tests still green, plus new Dubins and RRT tests pass.
2. Phase 0 Dubins golden-value smoke tests still match (no regression in characterization).
3. QGIS smoke test: import sample SPS → generate lines → run simulation both modes. Total-hours matches Phase 0 baseline (or deviates within a single documented delta from the global-leak fix).
4. `grep MAX_LINE_DISTANCE dubins_path.py` returns 0 matches (globals eliminated).

**Claude MUST stop after Phase 1 and await explicit "proceed to Phase 2" from user. Do not auto-advance.**

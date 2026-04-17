# Phase 10 — Performance (post-refactor backlog)

**Size:** TBD (profile-dependent)
**Risk:** medium (mostly additive optimizations; care with spatial indexes + threading)
**Blocks:** none
**Blocked by:** Phases 0-9 complete (clean architecture is prerequisite)
**Status:** **NOT IN CURRENT REFACTOR SCOPE.** Added 2026-04-17 at user request as future work — explicitly deferred to avoid destabilizing the maintainability revamp.

## Goal

Once the god-class breakup is done and services exist as clean seams
(Phases 5-7), measure where time is actually spent and apply standard
GIS / spatial-analysis performance techniques. **Profile first, optimize
second** — do not guess.

## Discipline

- **No optimization without a profiler.** Use `cProfile` + `snakeviz` (or
  `line_profiler` for hotspots) on real user workloads (e.g. Martin Linge's
  65,147-record SPS). Measure before AND after.
- **Pick one change, test, commit, measure.** Bundled optimizations make
  regression attribution impossible.
- **Performance targets must be numeric.** "Faster" is not a goal;
  "generate lines from 65k SPS in under 10 seconds" is.
- **Do not regress correctness.** Every commit must still pass all tests
  plus the SMOKE_TEST.md regression diff table.

## Performance techniques (prioritized by expected impact)

### 1. Spatial indexing for geometry lookups *(high impact expected)*

The deviation algorithm (`_calculate_and_apply_deviations` v2 + helpers)
does repeated geometry intersects and nearest-point queries on survey
lines vs no-go zones. These are currently O(n × m) linear scans.

- **Target:** use `QgsSpatialIndex` on the no-go layer and on
  `Generated_Survey_Lines`. Replace linear `.intersects()` loops with
  `index.intersects(bbox)` returning only candidate feature IDs, then
  precise `.intersects()` on that subset.
- **Where to look:** `_process_conflicted_lines` (Phase 2 kept), any
  loop doing `for obstacle in obstacles: if geom.intersects(obstacle)`.
- **Measurement:** time `handle_calculate_deviations` on a real project
  with 100+ no-go zones and 500+ lines before/after.

### 2. Batch feature commits *(high impact for large layers)*

`_write_features_to_layer` and similar spots add features one at a time
via `writer.addFeature(feature)`. QGIS is much faster with
`dataProvider.addFeatures([f1, f2, ...])` in batches of ~1000.

- **Target:** convert per-feature `addFeature` in hot paths to batched
  `addFeatures` with 1000-5000 feature batches.
- **Verify:** attribute order and schema match; `QgsVectorFileWriter` may
  have slightly different semantics than in-memory layer providers.

### 3. `QgsFeatureRequest` attribute subsetting *(medium impact)*

Many loops fetch the full feature (all attributes + geometry) when only
SP + LineNum + geometry are needed. `QgsFeatureRequest.setSubsetOfAttributes([indices])`
skips loading the rest.

- **Target:** the per-point pass in `handle_generate_lines` (reading
  SP, LineNum, Status, Heading, PrevDirection — not all 7 fields).
- **Expected gain:** modest at plugin data scale, but hygienic.

### 4. Geometry simplification for rendering *(medium impact)*

Optimized paths (`_visualize_optimized_path` output, moved to
`services/visualization.py` in Phase 7) are densified for vessel-path
accuracy but over-dense for display. QGIS renders every vertex.

- **Target:** maintain TWO geometries — one dense (for simulation time
  math) and one simplified via `QgsGeometry.simplify(tolerance=1.0 m)` for
  the map layer. Users see a smooth path without the ~50k-vertex cost.
- **Caveat:** only safe to simplify for *display*. Never feed a simplified
  geometry back into the simulation or sequence editor.

### 5. Render caching on memory layers *(low-medium impact)*

QGIS layer rendering has a built-in cache that redraws from pixel buffer
when nothing changed. Memory layers created by the plugin do not always
opt in.

- **Target:** after creating `generated_lines_layer` / `generated_runins_layer`
  / `optimized_path_layer`, call `layer.setCachingOnClearnessEnabled(True)`
  (check actual QGIS 3.40 API name — may be `setRenderingEnabled`).
- **Verification:** pan/zoom the canvas; CPU should stay low on repeat views.

### 6. Parallel rendering *(user-configuration, not plugin code)*

QGIS has multi-threaded rendering enabled by default since 3.x. Our
plugin doesn't control this but can ensure we don't DISABLE it:

- **Audit:** no `iface.mapCanvas().setParallelRenderingEnabled(False)`
  calls anywhere (grep before Phase 10).

### 7. QThread for long-running ops *(deferred until needed)*

`handle_generate_lines`, `_calculate_and_apply_deviations`, and
`handle_run_simulation` can freeze the UI for 10s+ on large projects.
Original plan marked threading as out-of-scope. Post-Phase-7, services
are widget-free (services layer rule) so moving them to a `QThread` is
now achievable.

- **Target:** single `QgsTask` subclass per long-running op, with progress
  callback and cancel support.
- **Risk:** QGIS layer edits MUST happen on the main thread. Services
  can do work, then marshal results back to the dockwidget for
  `addFeatures` / `commitChanges`.
- **Scope caution:** this is the most complex technique in Phase 10. Do
  last; measure user-perceived wins against maintenance cost.

### 8. Cache / memoize inside `_calculate_sequence_time` *(done — Phase 5)*

Turn time computation between identical line pairs is already cached
via `TurnCache` (added in Phase 5). Verify post-Phase-7 that the cache
survived extraction. No further work expected here.

### 9. Avoid `QgsProject.instance()` calls in tight loops *(low impact, easy)*

`QgsProject.instance()` is cheap but not free. Cache the project
reference at method entry.

- **Target:** grep for `QgsProject.instance()` inside loops; hoist.

### 10. Profile-driven Python-level wins *(whatever the profiler shows)*

- `math.hypot(dx, dy)` is faster than `sqrt(dx*dx + dy*dy)` on CPython
- `QgsPointXY.sqrDist` is faster than `.distance()` when you only need
  to compare distances (no sqrt)
- List comprehensions vs generator expressions vs plain for-loops —
  profile before choosing
- `@functools.lru_cache` on pure functions called with repeated args

These are micro-wins; only apply after 1-7 are done and the profiler
still shows a hotspot.

## Verification approach

1. **Baseline:** before any Phase 10 change, capture timings for the
   canonical workflow: SPS import → Generate Lines → Calculate Deviations
   → Run Simulation (both modes). Record wall-clock in `SMOKE_TEST.md`.
2. **Per-change verify:** each performance commit measures the specific
   op it targeted. Post-Phase-10 merge, re-run the full workflow and
   compare against baseline.
3. **No correctness regression:** `pytest test/` passes; simulation total
   hours matches Phase 9 baseline to <0.01%.

## Explicit non-goals for Phase 10

- **C extensions / Cython / numpy rewrites of Dubins or RRT.** Too
  invasive for the expected benefit at plugin data scale.
- **Database backends instead of GeoPackage.** GeoPackage is the industry
  standard for survey data exchange; do not complicate users' workflows.
- **GPU / CUDA.** Not justifiable for the size of problem we solve.

## When to start Phase 10

The recommended sequencing: ship Phases 0-9 as a "2.0" release, let users
exercise it on real surveys for a few weeks, collect a profile against
their actual workload, THEN come back and do Phase 10. Optimizing
against assumptions rather than measurements is the classic trap.

## Hard Stop Gate

Phase 10 is executed as a sequence of micro-commits, each with its own
stop-and-verify. The gate structure matches other phases:

1. User requests `proceed to Phase 10.N` with a specific technique
   (e.g. "proceed to Phase 10.1 — spatial indexing for deviations")
2. Claude profiles, proposes the change, implements, re-profiles, and
   stops for user verification
3. User reviews the diff, runs SMOKE_TEST, and approves/rejects the commit

**Claude MUST NOT pick Phase 10 tasks proactively.** They must be
explicitly requested.

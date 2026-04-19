# Phase 13 — OR-tools sequence optimizer (replaces 2-opt)

**Size:** large (split into 13a / 13b / 13c sub-phases; each independently shippable)
**Risk:** medium-high (new hard dependency, threading, new problem formulation)
**Blocks:** Phase 14 (cannot retire 2-opt until 13a validates)
**Blocked by:** nothing — Phase 12 and Phase 12a already shipped; architecture is clean enough for the new optimizer to slot in
**Status:** **PLAN ONLY.** No code to be written until the user greenlights Phase 13a.

---

## Motivation

User tested 2-opt on the full Martin Linge 4D survey (136 lines) and reported three problems in order of severity:

1. **Quality failure** — optimized output still contains long cross-survey transits (screenshot: `Long_Line_Changes_Simulation.png`). These are operationally unacceptable for OBN seismic acquisition. 2-opt cannot escape this local minimum because reversing a sequence slice can't fix wrong global topology.
2. **Performance failure** — one 2-opt pass on N=136 is ~18 k swaps × ~136 Dubins per swap = ~2.5 M Dubins calls in pure Python. Minutes per pass; hours for convergence.
3. **UX failure** — the whole QGIS UI freezes. Cancel button is unresponsive because the Python GIL is held inside the inner `i,j` loop at `services/sequence_service.py:547-559` with no intermediate yield point.

Phase 11d-4 (inner-loop poll) addresses only #3. It does nothing for #1 or #2. **A stronger algorithm is required, not a faster implementation of a weak one.**

Google OR-tools' CP-SAT routing library ships Guided Local Search, Lin-Kernighan, Simulated Annealing, and Tabu Search — all metaheuristics designed to escape the exact local-minimum class 2-opt gets trapped in. Implementation is in C++ with Python bindings; typical inner-loop speedup is 100–1000×.

User-confirmed constraints (ask_user_question thread, 2026-04-18):

- Audience: chief navigator + shift leader + peers on another vessel. Small professional team.
- Deployment: all vessels use **QGIS 3.40.5 Bratislava LTR on OSGeo4W**. No support for other versions.
- Therefore: ortools can be a **hard dependency**. No graceful-fallback code path. Users install once via `pip install ortools` in the OSGeo4W shell.

---

## Problem formulation

OBN survey sequencing is an **asymmetric TSP with line-orientation choice**:

- Each survey line has TWO possible shooting directions (low-to-high SP or high-to-low SP). These differ in the entry point, exit point, and entry/exit heading.
- Turn cost between lines is a Dubins path length — asymmetric (A→B ≠ B→A) and heading-dependent (which end of A you exit, which end of B you enter).
- The vessel must shoot every line exactly once, in exactly one direction.
- Acquisition time per line is fixed (length / shooting speed) but run-in time depends on which end you enter.
- No explicit depot — practically the vessel starts at "first_line_num" (user-pinned) or at the first natural line if unpinned.

### Mapping to OR-tools RoutingModel

Each line becomes **two nodes**: `(line_i, forward)` and `(line_i, reciprocal)`. Add a **disjunction** binding the pair with an infeasibility-grade penalty:

```
routing.AddDisjunction([node_fwd, node_rev], penalty=VERY_LARGE)
```

OR-tools then must visit exactly one of the two. Plus one **dummy depot** at node 0 with zero-cost arcs to and from every line node (open-path TSP).

For N=136 lines: 2N + 1 = **273 nodes**, **272 visits** (depot is waypoint only).

### Cost matrix

Asymmetric N×N matrix where `M[i][j]` = cost of the arc FROM node i TO node j, defined as:

| from i | to j | M[i][j] |
| --- | --- | --- |
| depot (0) | line node | run-in_time(j) + acq_time(j) |
| line node | depot (0) | 0 |
| line node | different line's node | dubins_turn_time(i.exit → j.entry) + run-in_time(j) + acq_time(j) |
| line node | same line's other-direction node | ∞ (disjunction blocks this anyway) |

Total entries: 273² = **74 529**. Each Dubins computation is currently ~1–5 ms in Python → **60 s to 5 min of precompute time on Martin Linge scale.** This is the single biggest cost; see Phase 13b for threading.

Note: folding acq_time and run-in_time into the ARC cost (not the node cost) avoids needing an OR-tools "dimension" — the model stays a pure min-cost routing problem.

### Solve parameters

```python
parameters = pywrapcp.DefaultRoutingSearchParameters()
parameters.first_solution_strategy = (
    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
)
parameters.local_search_metaheuristic = (
    routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
)
parameters.time_limit.FromSeconds(user_time_limit_s)  # default 30, UI-tunable
parameters.log_search = False  # plugin uses its own logging
```

**PATH_CHEAPEST_ARC** builds the initial tour greedily using the cheapest next-arc at each step — fast, usually within 10-20% of optimal. **GUIDED_LOCAL_SEARCH (GLS)** then iteratively penalizes frequently-used features in bad solutions, forcing exploration away from local minima.

### Pinning first_line_num (match existing UX)

If `sim_params['first_line_num']` is set, add a constraint that node `(first_line_num, first_heading_option_direction)` comes directly after the depot. OR-tools supports this via `routing.solver().Add(routing.NextVar(depot) == first_node_index)`.

If the user leaves `first_line_num` unset (future enhancement): OR-tools picks the optimal starting line. MVP matches current behavior only.

---

## Target architecture

```
obn_planner/
  services/
    ortools_optimizer.py     # NEW — pure Python, no Qt, no QGIS
    sequence_service.py      # unchanged (2-opt kept as legacy)
    simulation_service.py    # +2 fields in SimulationParams
  ui/
    optimization_worker.py   # NEW (Phase 13b) — QThread wrapping ortools solve
  obn_planner_dockwidget.py  # route dropdown → optimizer; precompute matrix;
                             # signal/slot glue for worker
  obn_planner_dockwidget_base.ui  # dropdown gains "OR-tools" option;
                                  # new "Time limit" SpinBox
  test/
    test_ortools_optimizer.py  # NEW — pure Python tests
```

---

## Phase 13a — Scaffold + optimizer module + single-thread integration *(medium)*

**Goal:** ship a working "OR-tools" option end-to-end, even if the UI freezes during solve. Proves the quality hypothesis on Martin Linge before investing in threading.

### Files touched

1. **`services/ortools_optimizer.py` (new)** — pure Python module.

    Public entry point:

    ```python
    def optimize_with_ortools(
        line_nums: List[int],
        cost_matrix: Dict[Tuple[int, int], float],
        node_meta: Dict[int, NodeMeta],
        time_limit_s: int = 30,
        pinned_first_node: Optional[int] = None,
        metaheuristic: str = "GUIDED_LOCAL_SEARCH",
        progress_callback: Optional[Callable[[OrToolsProgress], None]] = None,
        cancel_fn: Optional[Callable[[], bool]] = None,
    ) -> OptimizationResult:
        ...
    ```

    Returns the same `OptimizationResult` dataclass that `optimize_sequence_2opt` returns (already defined at `services/sequence_service.py:432`). Drop-in compatibility for the caller.

    `NodeMeta` is a small frozen dataclass per (line_num, direction) carrying whatever the caller needs to reconstruct the sequence post-solve — at minimum `(line_num, is_reciprocal)`.

    `OrToolsProgress` is a new frozen dataclass emitted by the ortools solution callback (elapsed_s, best_cost, solutions_found). Used by Phase 13b's progress dialog.

    Module docstring documents that the caller is responsible for building the cost matrix; this module neither knows nor cares where costs come from.

2. **`services/simulation_service.py`** — add two fields to `SimulationParams` (after `optimization_max_iterations` at line 96):

    ```python
    # Phase 13: OR-tools time budget (seconds). Only consulted when
    # optimization_level == "ortools". Default 30s is a good Martin-Linge
    # starting point; PM cost estimation may want 120-300.
    ortools_time_limit_s: int = 30

    # Phase 13: OR-tools local-search metaheuristic. Default GLS is the
    # strongest for TSP-like problems; Simulated Annealing is more
    # aggressive but less deterministic.
    ortools_metaheuristic: str = "GUIDED_LOCAL_SEARCH"
    ```

    Extend `to_legacy_dict` and `from_ui` accordingly. Add new valid string to the `_OPT_LABEL_TO_LEVEL` mapping: `"OR-tools"` → `"ortools"`.

3. **`obn_planner_dockwidget.py`** — new private method `_apply_ortools_optimization(...)` modeled on existing `_apply_2opt_optimization` at line 7543. Same signature pattern (mutates `best_final_sequence_info` in place). Key differences:

    - No `max_iterations` — replaced by `time_limit_s` from `sim_params`.
    - Builds the cost matrix on the main thread using existing `_calculate_dubins_turn` and the cached `_find_runin_geom` result (step 3a below).
    - Calls `optimize_with_ortools` directly (no QThread in 13a — accept UI freeze).
    - Reuses the existing QProgressDialog pattern; in 13a the dialog shows only before/after totals, no intermediate updates.

    Cost matrix precompute loop runs with `QApplication.processEvents()` every N=100 iterations so the dialog at least paints.

    Routing dispatch at the existing Phase 11b injection point (~line 6994 in `handle_run_simulation`):

    ```python
    if sim_params.get('optimization_level') == "2opt":
        self._apply_2opt_optimization(...)
    elif sim_params.get('optimization_level') == "ortools":
        self._apply_ortools_optimization(...)
    ```

4. **`obn_planner_dockwidget.py`** — Phase 13a prerequisite: extend `_prepare_line_data` at line 6329 to also cache **run-in geometries** (not just outer points) in `line_data`. Today `_calculate_sequence_time` re-queries `required_layers['runins']` every evaluation via `_find_runin_geom:1558` — a QGIS-layer scan that must not happen in a worker thread (Phase 13b) and is a perf hit even in 13a.

    Add two new keys to each `line_data[line_num]` dict (alongside existing `start_runin_point`, `end_runin_point`):

    ```python
    'start_runin_geom': QgsGeometry,  # full linestring; None if absent
    'end_runin_geom':   QgsGeometry,  # full linestring; None if absent
    ```

    Populate during the existing run-in matching loop at line 6523. Refactor `_find_runin_geom` callers (`_calculate_sequence_time:7448`, anywhere else — grep) to pull from `line_data` instead of iterating the layer. Remove `_find_runin_geom` if no callers remain.

    This is a standalone improvement that benefits 2-opt as well as ortools. Can ship as its own prep commit (Phase 13a-prep) ahead of the optimizer.

5. **`obn_planner_dockwidget_base.ui`** — dropdown value gains `"OR-tools"`:

    ```xml
    <item><property name="text"><string>Off</string></property></item>
    <item><property name="text"><string>OR-tools</string></property></item>
    <item><property name="text"><string>2-opt (legacy)</string></property></item>
    ```

    Add a new `QSpinBox name="ortoolsTimeLimitSpinBox"` with range 5–600, default 30, suffix " s", next to the existing `optimizationMaxIterationsSpinBox`. The two spinboxes are mutually relevant based on the dropdown selection — existing `_on_optimization_level_changed` slot gains a third branch to enable/disable each.

6. **`obn_planner_dockwidget.py` — ortools availability check at plugin load.** In `__init__` after the UI is set up:

    ```python
    try:
        import ortools
        self._ortools_available = True
    except ImportError:
        self._ortools_available = False
        log.warning(
            "ortools not installed — OR-tools optimization disabled. "
            "Install via: pip install ortools "
            "(run from OSGeo4W Shell on Windows)."
        )
    ```

    When the dropdown is changed to "OR-tools" and `_ortools_available` is False, revert to "Off" and show a QMessageBox with the install command.

7. **`docs/refactor/README.md`** — add Phase 13 to the phase index. Note that it supersedes the "Phase 11 — 2-opt" work (2-opt becomes legacy); the original post-refactor Phase 13 "output layer persistence" slot is renumbered to Phase 14.

### Tests added (pure Python, no QGIS)

`test/test_ortools_optimizer.py`:

- `test_known_optimal_small_instance` — 4-line problem with a hand-computed optimum. Assert ortools finds it.
- `test_asymmetric_cost_respected` — cost(A→B) ≠ cost(B→A); assert the cheaper direction is chosen.
- `test_disjunction_respected` — two nodes per line; assert only one per pair visited.
- `test_pinned_first_node` — with pinned_first_node set, first visit must be that node.
- `test_time_limit_respected` — set time_limit_s=1; assert wall-clock ≤ ~3 s (overhead tolerance).
- `test_returns_optimization_result_shape` — drop-in compatibility with 2-opt's return type.
- `test_infeasible_arc_avoided` — arcs with cost 1e12 present in matrix; assert the returned sequence uses none of them when avoidable.
- `test_module_imports_without_qgis` — meta-test: `import services.ortools_optimizer` works in a pure-Python environment.

If ortools is not installed in the test environment, all tests in this module are skipped with a clear message. Other tests unaffected.

### Verify

1. `pip install ortools` in OSGeo4W shell (one-time per dev machine).
2. `python -m unittest test/test_ortools_optimizer.py` green.
3. `python -m unittest discover -s test` green (all pre-existing pure-Python tests still pass).
4. In QGIS: import Martin Linge SPS, Generate Lines, select Optimization="OR-tools", time_limit=30. Run Simulation.
   - Expected: QGIS freezes for ~1–5 min (cost matrix precompute + 30 s solve). Result: optimized sequence with NO long cross-survey transits visible in Turn_Segments layer.
   - Baseline comparison: same survey with Optimization="Off" and with "2-opt". Log the three `total_cost_hours` values in `SMOKE_TEST.md`. Expect OR-tools ≤ 2-opt < Off by a large margin (specifically, expect the long-transit pattern in the attached screenshot to be absent in OR-tools output).

### Rollback

Single `git revert` removes the ortools dropdown option and the new method. Existing 2-opt and "Off" paths completely unaffected.

### Risks

- **Ortools dependency install fails silently for one of the vessels.** Mitigation: the availability-check dialog is mandatory, not optional. User must see the install instructions on first use.
- **Cost matrix precompute may exceed expected 5 min on unusual surveys.** Mitigation: document typical times in SMOKE_TEST; if a user reports >10 min, revisit in Phase 13b with parallelism or Dubins caching.
- **OR-tools solver occasionally produces sub-optimal tours for time-limited runs.** Mitigation: log `solutions_found` count; recommend increasing time_limit if count=1.
- **Run-in geometry extraction refactor (step 4) is invasive.** `_find_runin_geom` may be called from unexpected places. Mitigation: Explore-agent grep before starting, migrate callers one at a time in separate commits.

---

## Phase 13b — QThread worker + responsive UI *(medium-large)*

**Goal:** eliminate the UI freeze. Cost-matrix precompute and OR-tools solve both run in a background thread. Progress dialog updates in real time; cancel is responsive within ~2 s.

### Why this is separate from 13a

1. Isolates the correctness test of "does ortools solve this better than 2-opt" from the complexity of threading. If 13a proves the answer is yes, 13b is clearly worth the investment. If no, 13b never needs to ship.
2. Threading bugs are notoriously subtle. Wanting them on a commit boundary where everything else is known-good is worth it.
3. Phase 13a forces us to identify every QGIS-layer access inside the cost function (the `_find_runin_geom` refactor) — which is the prerequisite for thread safety anyway.

### Files touched

1. **`ui/optimization_worker.py` (new)** — a `QObject` subclass moved to a `QThread` via `moveToThread` (the Qt-recommended pattern, not subclassing QThread directly).

    ```python
    class OptimizationWorker(QObject):
        progress = pyqtSignal(object)    # OrToolsProgress
        finished = pyqtSignal(object)    # OptimizationResult
        failed   = pyqtSignal(str)       # error message

        def __init__(self, optimizer_fn, *args, **kwargs): ...

        def run(self):
            try:
                result = self.optimizer_fn(*self.args, **self.kwargs)
                self.finished.emit(result)
            except Exception as e:
                log.exception("Optimization worker failed")
                self.failed.emit(str(e))

        def cancel(self):
            """Sets a shared flag read by the cost_fn / ortools cancel callback.
            Does not forcibly terminate the thread."""
    ```

    The worker receives the precomputed cost matrix (pure data) and the ortools optimizer function (pure Python). It touches NO QGIS layers. Cancel is cooperative via a `threading.Event` checked in the ortools solution callback.

2. **`obn_planner_dockwidget.py` `_apply_ortools_optimization`** — rewrite to use the worker. The method becomes mostly glue:

    - Precompute cost matrix on the main thread (with progress dialog).
    - Create `QThread` and `OptimizationWorker`, wire signals.
    - Show progress dialog with Cancel button; connect Cancel to `worker.cancel()`.
    - Use a local event loop (`QEventLoop.exec_()`) or `QTimer.singleShot` polling to block `_apply_ortools_optimization` return until `finished`/`failed` — this keeps the caller's existing synchronous contract in `handle_run_simulation`.
    - Actually: **do not block the caller.** Return immediately, and route the post-solve logic (final cost recomputation, visualization) through the worker's `finished` signal. This is a bigger refactor — see "risks" below.

    **Decision locked in this plan doc:** use the local-event-loop pattern. It preserves `handle_run_simulation`'s synchronous structure and is well-documented in Qt forums. The main-thread UI stays responsive because the event loop pumps Qt events.

3. **`obn_planner_dockwidget.py`** — cost-matrix precompute extracted to a helper:

    ```python
    def _precompute_cost_matrix(
        self, line_nums, line_data, sim_params, progress_cb, cancel_cb
    ) -> Dict[Tuple[int, int], float]:
        ...
    ```

    Called on the main thread; emits progress roughly every 100 entries. Cancel yields `None`.

4. **`services/ortools_optimizer.py`** — integrate a real progress callback. OR-tools has a `SearchMonitor::AtSolution` hook; wire it to call the Python `progress_callback` (which the worker will emit as a signal). Respects a shared cancel flag by returning `False` from the monitor to end the search.

    Technical detail: OR-tools' Python bindings expose the monitor via `routing.solver().Add(...)` with a custom `LocalSearchFilter` or by using `routing.SolveFromAssignmentWithParameters` with a progress-friendly loop. The exact API has changed between ortools 9.x versions — verify against the version available in OSGeo4W's Python (likely ortools 9.7+). **VERIFY API in 13b kickoff.**

5. **Test additions** (`test/test_optimization_worker.py`, QGIS-dependent because of QThread):

    - Worker emits `finished` after normal run.
    - Worker emits `failed` when optimizer_fn raises.
    - `cancel()` causes `finished` (with partial-best `OptimizationResult`) within time_limit + grace.
    - No main-thread QGIS layer access during run — enforced by passing a layer-less cost matrix.

### Verify

1. Full Phase 13a SMOKE_TEST still green.
2. Run the Martin Linge scenario. UI remains responsive during both precompute and solve phases. Cancel button returns within ~2 s.
3. Progress dialog updates visibly at least every 5 s during solve.
4. After cancel, the result either contains the best-so-far solution (if any) or reverts cleanly to the un-optimized sequence. No exceptions, no partial UI state.

### Rollback

Per-commit revert. The 13a single-thread path remains as a fallback: flip a one-line `use_worker=True` switch to `False` and the 13a behavior returns.

### Risks

- **QThread signal/slot corruption** — passing mutable Python objects across thread boundaries is OK for immutable frozen dataclasses and dicts of primitives. Never pass `QgsGeometry` or `QgsFeature` — they are not thread-safe. The cost-matrix-only design avoids this but must be enforced by contract.
- **OR-tools cancel API instability** — the C++ solver cancel mechanism has been reworked across ortools 9.x point releases. Phase 13b opens with a 30-minute reconnaissance commit: `scripts/probe_ortools_cancel.py` that verifies the exact API works on the installed version before writing production code.
- **Local-event-loop deadlock** — if the user closes the dock widget during solve, the event loop may never exit. Mitigation: `QProgressDialog.rejected` signal also triggers `worker.cancel()`, and the worker has a hard time-limit cap (UI SpinBox value + 30 s grace).
- **Cost matrix on very large surveys** — 500+ line surveys yield 1M+ matrix entries. Precompute may exceed 30 min. If observed, add Dubins symmetry shortcuts (A→B cost often approximately equals B→A mirror) — defer to 13b-2 sub-task if needed.

---

## Phase 13c — Retire 2-opt from UI *(small)*

**Prerequisite:** Phase 13a and 13b are in production for at least one acquisition cycle (≥ 1 week of real operational use) with no ortools regression reported.

### Files touched

1. **`obn_planner_dockwidget_base.ui`** — drop the `"2-opt (legacy)"` dropdown item.
2. **`services/sequence_service.py`** — add deprecation marker to `optimize_sequence_2opt` docstring: "Retained only for historical reference; no caller remains post-Phase 13c. Will be deleted in Phase 14."
3. **`obn_planner_dockwidget.py`** — remove `_apply_2opt_optimization` call from `handle_run_simulation`. The method itself stays (see item 4).
4. **`services/sequence_service.py`** — the `optimize_sequence_2opt` function and its tests stay one more release cycle. Delete in a future Phase 14 janitorial pass.

### Verify

- Existing tests still pass (`optimize_sequence_2opt` module-level tests unchanged).
- UI dropdown has only "Off" and "OR-tools".
- No change to simulation output for runs that were using OR-tools.

### Rollback

Trivial revert; 2-opt UI option returns.

---

## Distribution and install

The plugin's `README.md` (or a new `INSTALL.md`) gains a short section:

> ## Installing OR-tools (required for sequence optimization)
>
> OR-tools is installed into a plugin-local `vendor/` directory, NOT into QGIS's site-packages. This is because ortools 9.15+ requires numpy 2.x, which is ABI-incompatible with QGIS 3.40.5's bundled numpy 1.26.4 and would crash GDAL/scipy/pandas. We pin `ortools==9.14.6206` (last release that works with numpy 1.x) and use `sys.path` injection from `services/ortools_optimizer.py`.
>
> 1. Open "OSGeo4W Shell" from the Start menu (regular user — do NOT run as Administrator; we want per-plugin install, not system-wide).
> 2. `cd` into the plugin directory, e.g. `cd "C:\Users\<you>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\obn_planner"`
> 3. Run: `pip install --target="vendor" --no-deps ortools==9.14.6206 absl-py "protobuf>=6.31,<6.32" immutabledict "typing-extensions>=4.12"`
>    - `--target="vendor"` installs into the plugin's `vendor/` folder (gitignored).
>    - `--no-deps` is CRITICAL: without it, pip would also install numpy into `vendor/`, which our `sys.path.insert(0, vendor)` would then shadow over QGIS's numpy 1.26.4 — defeating the whole point.
> 4. Restart QGIS.
> 5. Verify in QGIS Python Console:
>    ```python
>    from obn_planner.services import ortools_optimizer  # primes sys.path
>    import ortools, numpy
>    print(ortools.__version__, ortools.__file__)    # → 9.14.6206, path under vendor/
>    print(numpy.__version__, numpy.__file__)        # → 1.26.4, path under QGIS install
>    ```
> 6. In the OBN Planner dock, the "Sequence Optimization: OR-tools" option should now be selectable.

For the user's fleet: one-time install per vessel. If a vessel gets a fresh QGIS install, repeat the `pip install --target="vendor"` step — the `vendor/` folder is gitignored and NOT shipped in the plugin zip.

No changes to `metadata.txt` plugin manifest are needed — QGIS doesn't parse Python dependencies from it.

---

## Non-goals for Phase 13

- **Multi-vehicle planning** (two vessels cooperating) — OR-tools supports this natively but the plugin has no concept of multiple vessels. Out of scope.
- **Time-window constraints** (weather, daylight, crew shifts) — OR-tools supports these via Dimensions. Not requested, not MVP.
- **Alternative objectives** (minimize fuel, minimize maximum leg, etc.) — today the objective is total time. Keep as-is.
- **Auto-choose optimizer** based on survey size — user keeps explicit control.
- **Pre-3.40 QGIS compatibility** — user explicitly scoped support to QGIS 3.40.5.
- **Offline / no-ortools support** — user explicitly scoped all vessels to have ortools installed.

---

## Open questions for user (greenlight before 13a starts)

1. **Default `time_limit_s`:** plan says 30 s. Is that right for daily-ops iterative use, or should it default lower (10 s) with the PM bumping it manually for job estimates? Recommendation: 30 s, with UI hint text "raise to 120 s for final job-completion estimates."
2. **Metaheuristic choice in the UI?** Plan hard-codes GLS. Alternative: expose a dropdown "GLS / Lin-Kernighan / Simulated Annealing" for experts. Recommendation: hide it in 13a (GLS is strongest for TSP), expose if users ask for it later.
3. **Pre-Phase 13a run-in-geometry refactor (step 4 of 13a) — standalone commit or bundled with 13a?** Recommendation: standalone commit landed first (call it Phase 12b). It's a pure refactor, low risk, benefits 2-opt immediately, unblocks 13b threading.
4. **Retire 2-opt entirely at Phase 13c, or keep it forever as a debugging fallback?** Recommendation: retire at 13c. Maintainer-time is precious; two optimizers to verify is double the bug surface.
5. **QThread implementation via `moveToThread` vs `QgsTask`?** `QgsTask` is QGIS's task framework with built-in progress bars and cancel. Cleaner integration but less control. Recommendation: `QgsTask` for 13b (aligns with Phase 10's deferred "QThread for long-running ops" note which also specified `QgsTask`). VERIFY API in reconnaissance commit before locking.

---

## Effort estimate

| Sub-phase | Claude work | User verification | Wall clock (sessions) |
| --- | --- | --- | --- |
| 12b prep (run-in geom cache) | 2–3 hours | 30 min smoke test | 1 session |
| 13a (optimizer + single-thread UI) | 4–6 hours | 1 hour SMOKE_TEST + Martin-Linge comparison | 1–2 sessions |
| 13b (QThread + responsive UI) | 4–6 hours | 1 hour threading stress test | 1–2 sessions |
| 13c (retire 2-opt) | 30 min | 15 min regression check | 1 session |

**Total: 10–16 hours of focused work across 4–6 sessions.** Hard-stop gate between each sub-phase; no bundling.

---

## Hard stop gate

Phase 13 executes as discrete sub-phases, each individually reviewable:

1. User greenlights Phase 12b (run-in geom cache refactor) → Claude implements → user smoke-tests → commit.
2. User greenlights Phase 13a (optimizer scaffold) → Claude implements → user runs Martin-Linge comparison + SMOKE_TEST → commit.
3. User greenlights Phase 13b (QThread) → Claude probes ortools cancel API → implements → user threading-tests → commit.
4. User greenlights Phase 13c (retire 2-opt) → Claude implements → commit.

**Claude MUST NOT skip gates or bundle sub-phases.** Each gate is an explicit opportunity to reassess, reprioritize, or back out.

---

## Summary of key decisions locked in this plan

| Decision | Choice | Reason |
| --- | --- | --- |
| Dependency policy | Hard require `ortools` | User controls all deploys; no fallback code burden |
| Node model | 2 nodes per line + dummy depot | Clean disjunction for direction choice |
| Cost representation | Precomputed asymmetric matrix | Faster than lazy callback for GLS which touches most arcs |
| Acquisition + run-in time | Folded into arc cost | Keeps routing model pure, no Dimension needed |
| First-line pinning | Respected (mirrors existing UX) | Predictable operational behavior |
| Metaheuristic | Guided Local Search | Strongest for asymmetric TSP; solves user's long-transit complaint |
| First-solution strategy | PATH_CHEAPEST_ARC | Fast, good starting point for local search |
| Infeasibility encoding | Cost = 1e12, not arc removal | OR-tools always returns a solution; avoids false-infeasible edge cases |
| Progress reporting | OR-tools SearchMonitor → pyqtSignal | Emits best-so-far each time GLS finds improvement |
| Cancel | Cooperative via shared flag in monitor | No forcible thread termination; responsive within ~2 s |
| 2-opt fate | Kept in 13a/13b, retired in 13c | One release cycle of A/B comparison before delete |
| Thread model | `QgsTask` preferred, `moveToThread` fallback | VERIFY QgsTask API in reconnaissance commit |

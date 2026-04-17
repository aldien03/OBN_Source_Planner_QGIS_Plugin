# Phase 7 — Services: QGIS-heavy (path_reconstructor, visualization, line_generator, deviation_service)

**Size:** large
**Risk:** medium/high — these services touch QGIS layer APIs, rendering, and line-generation logic. Packaging must be fixed here.
**Blocks:** Phase 8 (UI handlers need the services)
**Blocked by:** Phase 6 (SimulationService consumes path_reconstructor)

## Goal

Finish extracting service modules from the dockwidget: path reconstruction, visualization layer creation, line generation orchestration, and the surviving deviation algorithm (from Phase 2). Apply the packaging fix for `pb_tool.cfg` so the new directory tree deploys correctly.

## Files created

### `services/path_reconstructor.py` (new)

Extract:
- `_reconstruct_path` (`obn_planner_dockwidget.py:10356`)
- `_add_line_segments` (grep for exact location)

Public API:

```python
@dataclass
class PathSegment:
    line_num: int
    direction: str              # "low_to_high" | "high_to_low"
    geometry: QgsGeometry
    length_m: float
    time_s: float
    kind: str                   # "line" | "turn" | "run_in"

def reconstruct_path(
    sequence: list[int],
    line_directions: dict[int, str],
    line_data: dict,
    turn_cache: TurnCache,
    params: SimulationParams,
) -> list[PathSegment]:
    """Rebuild full path: for each line, add run-in + line + turn segments in order."""
```

Pure function — takes all dependencies explicitly. Returns a list that the visualizer and the editor both consume. Used by `SimulationService._reconstruct_path` (the stub in Phase 6).

### `services/visualization.py` (new)

Extract:
- `_visualize_optimized_path` (`:9135`)
- Any renderer / symbol / color / width helpers (grep `QgsSymbol`, `QgsRenderer`, `QgsLineSymbol`)

Public API:

```python
class VisualizationService:
    def __init__(self, iface):
        self._iface = iface

    def show_optimized_path(self, segments: list[PathSegment], crs, layer_name: str = "Optimized_Survey_Path"):
        """Create or replace the 'Optimized_Survey_Path' memory layer and add to project."""

    def clear_path(self):
        """Remove the optimized path layer if present."""
```

### `services/line_generator.py` (new)

Extract `handle_generate_lines` body (`:1516-1938`, 423 lines). Separate the algorithm from the UI:

```python
@dataclass
class LineGenerationParams:
    sps_layer: QgsVectorLayer
    start_line: int
    end_line: int
    turn_radius_m: float
    run_in_length_m: float
    # ... other current UI parameters

@dataclass
class LineGenerationResult:
    lines_layer: QgsVectorLayer
    runins_layer: QgsVectorLayer
    stats: dict                    # counts, warnings, elapsed time

class LineGeneratorService:
    def __init__(self, iface):
        self._iface = iface

    def generate(self, params: LineGenerationParams) -> LineGenerationResult:
        """Replaces handle_generate_lines body. Thin UI wrapper in the dockwidget handles file dialogs,
        progress indication, error display."""
```

When generating per-line attributes, propagate `PREV_DIRECTION` from the SPS points (this was stubbed inline in Phase 4; now moves into the service).

### `services/deviation_service.py` (new)

Wrap the surviving v2 Peak/Tangent algorithm (renamed in Phase 2 from `_calculate_and_apply_deviations_v2` to `_calculate_and_apply_deviations`):

```python
@dataclass
class DeviationParams:
    lines_layer: QgsVectorLayer
    nogo_layer: QgsVectorLayer
    clearance_m: float
    turn_radius_m: float

@dataclass
class DeviationResult:
    success: bool
    lines_affected: int
    lines_failed: int
    warnings: list[str]

class DeviationService:
    def apply(self, params: DeviationParams) -> DeviationResult:
        """Wraps the current _calculate_and_apply_deviations. Keeps Peak/Tangent algorithm identical."""
```

Move the algorithm's ~800-line implementation (itself + 3 helpers: `_calculate_intermediate_components`, `_process_conflicted_lines`, `_complete_deviation_calculation`, `_merge_line_segments`) into this service file, preserving line-by-line behavior.

## Packaging fix — CRITICAL

Currently `pb_tool.cfg`:

```
python_files: __init__.py obn_planner.py obn_planner_dockwidget.py
extra_dirs:
```

After Phase 7, the plugin has:

```
geometry/  io/  services/  ui/  docs/
```

If deploy uses `pb_tool`, the new directories will NOT be copied and the plugin will fail with `ModuleNotFoundError`. Fix:

```
# pb_tool.cfg
python_files: __init__.py obn_planner.py obn_planner_dockwidget.py

# directories to copy recursively
extra_dirs: geometry io services ui
```

Also update `Makefile`:

```makefile
PY_DIRS = geometry io services ui

deploy:
    @cp *.py $(PLUGIN_DIR)
    @cp metadata.txt *.png *.qrc $(PLUGIN_DIR)
    @for d in $(PY_DIRS); do mkdir -p $(PLUGIN_DIR)/$$d && cp -r $$d/*.py $(PLUGIN_DIR)/$$d/; done
```

VERIFY by running `pb_tool deploy` and `make deploy` in a test location, then comparing the deployed tree against the source.

## QGIS 3.40 cleanup

With the minimum version bumped in Phase 0, simplify the defensive `AttributeError` fallbacks:

### `obn_planner_dockwidget.py:121-134` → `geometry/wkb_helpers.py`

Before:
```python
try:
    def is_surface_type(wkb):
        return QgsWkbTypes.isSurface(wkb)
except AttributeError:
    def is_surface_type(wkb):
        return wkb in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon, ...)
```

After (QGIS 3.40+ guaranteed):
```python
from qgis.core import QgsWkbTypes

def is_surface_type(wkb) -> bool:
    return QgsWkbTypes.isSurface(wkb)

def is_point_type(wkb) -> bool:
    return QgsWkbTypes.isPoint(wkb)

def is_line_type(wkb) -> bool:
    return QgsWkbTypes.isLine(wkb)
```

## Dockwidget cleanup after extraction

After Phase 7, the following helpers are deleted from `obn_planner_dockwidget.py`:
- `_reconstruct_path`
- `_add_line_segments`
- `_visualize_optimized_path`
- `_calculate_and_apply_deviations` (moved into `DeviationService`)
- `_calculate_intermediate_components`, `_process_conflicted_lines`, `_complete_deviation_calculation`, `_merge_line_segments`
- The symbol/renderer helpers
- The WKB fallback block at `:121-134`

Expected dockwidget line count after Phase 7: **~2500-3500 lines** (target <2000 by end of Phase 8).

## Tests

### `test/test_path_reconstructor.py` (new; QGIS-dependent)

- `test_reconstruct_path_simple_two_lines` — fixture with 2 survey lines + a turn between; assert 3 segments returned (line, turn, line).
- `test_reconstruct_path_with_run_in` — first line has a run-in; assert the first segment is of kind "run_in".

### `test/test_deviation_service.py` (moved/expanded from Phase 2 stub)

- `test_apply_no_intersection` — lines don't cross no-go; result.lines_affected == 0.
- `test_apply_intersection` — one line crosses a simple square no-go; result.lines_affected == 1 and line geometry is modified.
- `test_apply_with_clearance` — varying clearance affects deviation offset.

### `test/test_line_generator.py` (new; QGIS-dependent)

- `test_generate_basic` — small SPS point layer + parameters → `LineGenerationResult` with populated layers and stats.
- `test_generate_propagates_prev_direction` — SPS points with PREV_DIRECTION → generated lines have PREV_DIRECTION field populated (uses Phase 4 logic, now in service).

## Verify

1. `pytest test/` — all green, including the new test files.
2. Full QGIS smoke test: SPS → Generate Lines → Calculate Deviations → Run Simulation (both modes) → Sequence Editor → XLSX export. All work.
3. Simulation cost in hours matches Phase 6 baseline to <0.01%.
4. Deploy via `pb_tool deploy` AND `make deploy`; verify both produce identical trees under the target plugin directory.
5. `wc -l obn_planner_dockwidget.py` → ~2500-3500 lines.
6. `grep _reconstruct_path` / `grep _visualize_optimized_path` / `grep _calculate_and_apply_deviations` → 0 hits in dockwidget.

## Rollback

Per-service revert in this order (safest first):
1. Revert `visualization_service` (only cosmetic — output looks different if reverted, but sim still works)
2. Revert `line_generator` (line generation falls back to inline)
3. Revert `path_reconstructor`
4. Revert `deviation_service`
5. Revert packaging fix
6. Revert WKB helper cleanup

## Risks and unknowns

- **`pb_tool` vs `Makefile` reality** — I don't know which is production. If both work, fix both (done above). If only one is used, fix the other anyway to keep parity.
- **`deviation_service` preserves algorithm byte-for-byte** — the Peak/Tangent algorithm must not be "cleaned up" during extraction. Copy-paste verbatim; wrap in a class. Any cleanup happens in a separate commit post-Phase-7 after confirming identical output.
- **Rendering changes** — `_visualize_optimized_path` uses specific symbol styles. Copy those verbatim. If visual output differs, rollback just the visualization service.
- **`line_generator` and PREV_DIRECTION** — the Phase 4 inline edit in `handle_generate_lines` moves into the service. Verify the field is still populated after extraction.
- **`QgsWkbTypes` API in 3.40** — verify `isSurface` / `isPoint` / `isLine` exist. They should, per QGIS docs, but cheap to confirm via a quick `dir()` call in the QGIS Python console.
- **Circular import risk** — `services/path_reconstructor.py` needs `TurnCache` from `services/turn_cache.py`. No cycle if the DAG is kept: turn_cache → geometry.dubins; path_reconstructor → turn_cache. Enforce via import-linter config in Phase 9.

## Hard Stop Gate

Phase 7 is complete when:
1. All tests green.
2. Packaging fix verified: `pb_tool deploy` deploys the full directory tree; same for `make deploy`.
3. Dockwidget line count below 3500.
4. Full QGIS smoke test: baseline-equivalent output for all workflows.

**Claude MUST stop after Phase 7 and await explicit "proceed to Phase 8" from user.**

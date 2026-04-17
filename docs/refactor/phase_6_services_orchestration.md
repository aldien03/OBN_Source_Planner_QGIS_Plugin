# Phase 6 — Services: core orchestration + direction-following feature

**Size:** large
**Risk:** **high** — this is where `handle_run_simulation` is rewired and the `self.last_*` state pattern is replaced. Also where the direction-following feature becomes behavior.
**Blocks:** Phase 7 (QGIS-heavy services depend on this orchestration)
**Blocked by:** Phases 4 (direction data) and 5 (turn_cache + sequence_service)

## Goal

Extract the simulation orchestration core: `_gather_simulation_parameters`, `_prepare_line_data`, `_simulate_add_line`, `_calculate_sequence_time`, `_get_next_exit_state`, `_get_entry_details`. Introduce `SimulationParams` and `SimulationResult` dataclasses. Replace the 5 `self.last_*` fields. Wire up the direction-following feature that uses Phase 4's `PREV_DIRECTION` data.

## `services/simulation_service.py` (new)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from qgis.core import QgsVectorLayer, QgsGeometry, QgsPointXY

from .turn_cache import TurnCache
from .sequence_service import generate_racetrack_sequence, determine_next_line_teardrop

@dataclass
class SimulationParams:
    acquisition_mode: str                    # "Racetrack" | "Teardrop" (enum in Phase 8)
    first_line_num: int
    first_heading_option: str                # "Low to High SP" | "High to Low SP (Reciprocal)"
    start_sequence_number: int
    start_datetime: datetime
    avg_shooting_speed_knots: float
    avg_turn_speed_knots: float
    turn_radius_m: float
    vessel_turn_rate_dps: float
    run_in_length_m: float
    deviation_clearance_m: float
    nogo_layer: Optional[QgsVectorLayer]     # None OK
    follow_previous_direction: bool = False   # NEW in Phase 6 — wired to UI in Phase 8

    @classmethod
    def from_ui(cls, dockwidget) -> "SimulationParams":
        """Gather from UI widgets. Validates and raises ValueError with readable message."""
        ...

@dataclass
class SimulationResult:
    params: SimulationParams
    line_data: dict                          # line_num → dict of attrs
    required_layers: dict
    turn_cache: TurnCache
    sequence: list[int]
    line_directions: dict[int, str]          # line_num → "low_to_high" | "high_to_low"
    total_cost_seconds: float
    path_segments: list                      # for visualization
```

### Public API

```python
class SimulationService:
    def __init__(self, iface, *, turn_cache_factory=None):
        self._iface = iface
        self._tc_factory = turn_cache_factory or (lambda p: TurnCache(
            dubins_radius=p.turn_radius_m,
            turn_speed_mps=p.avg_turn_speed_knots * 0.514444,
            densification_m=10.0,
        ))

    def run(self, params: SimulationParams) -> SimulationResult:
        """Main entry. Replaces handle_run_simulation body."""
        line_data, required_layers = self._prepare_line_data(params)
        if not line_data:
            raise ValueError("No valid 'To Be Acquired' lines found.")
        turn_cache = self._tc_factory(params)
        if params.acquisition_mode == "Racetrack":
            sequence, line_directions, total_cost = self._run_racetrack(params, line_data, turn_cache)
        elif params.acquisition_mode == "Teardrop":
            sequence, line_directions, total_cost = self._run_teardrop(params, line_data, turn_cache)
        else:
            raise ValueError(f"Unknown mode: {params.acquisition_mode}")
        path_segments = self._reconstruct_path(sequence, line_directions, line_data, turn_cache, params)  # stub for Phase 7
        return SimulationResult(...)
```

### Extracted methods

Move into `SimulationService` as private methods, cleaned up:

| From dockwidget | To service | Notes |
|---|---|---|
| `_gather_simulation_parameters` (`:6243`) | `SimulationParams.from_ui(dw)` classmethod | reads UI widgets |
| `_prepare_line_data` (`:6346`) | `SimulationService._prepare_line_data` | reads `Generated_Survey_Lines` layer |
| `_simulate_add_line` | `SimulationService._simulate_add_line` | computes time per line |
| `_calculate_sequence_time` (`:7281`) | `SimulationService._calculate_sequence_time` | sums turns + lines |
| `_get_next_exit_state` (`:8253`) | helper function, not on the class | pure math |
| `_get_entry_details` | helper function | pure math |

## Direction-following feature

### `services/sequence_service.py` (extended from Phase 5)

Add an optional direction constraint:

```python
@dataclass
class LineDirection:
    forward_heading_deg: float         # heading when shot "low_to_high"
    reciprocal_heading_deg: float      # = forward + 180 mod 360
    prev_direction_deg: float | None   # from PREV_DIRECTION field

def assign_direction_for_line(
    line_info: LineDirection,
    prior_direction: str,                    # "low_to_high" | "high_to_low"
    follow_previous: bool,
) -> str:
    """
    Return "low_to_high" or "high_to_low" for the given line.
    If follow_previous is False: alternate from prior_direction (existing behavior).
    If follow_previous is True and prev_direction_deg is set: pick the direction whose
    heading matches prev_direction_deg within 1 degree tolerance.
    If follow_previous is True but prev_direction_deg is None: fall back to alternation
    with a log warning.
    """
```

### Racetrack with direction-following

In `generate_racetrack_sequence`, when `follow_previous=True`:
- Each line's direction is pinned to what matches its `PREV_DIRECTION`.
- The sequence ORDER remains interleaved for efficient vessel movement.
- If the pinned directions break the racetrack alternation pattern (e.g., two consecutive lines have same direction), a turn between them may be longer — this is the user's responsibility; the algorithm still returns a valid sequence.

### Teardrop with direction-following

In `determine_next_line_teardrop`, when `follow_previous=True`:
- After picking the next line by proximity, its direction is pinned to `PREV_DIRECTION` (not alternated).
- Turn time computed against the pinned direction — may make some line pairs less efficient, but matches user intent.

### Feature toggling

`SimulationParams.follow_previous_direction: bool` — default `False` to preserve existing behavior. Phase 8 adds the checkbox.

### Validation at runtime

Before running, `SimulationService.run()` checks:
- If `follow_previous_direction=True` AND all `line_data[line]['prev_direction'] is None`, raise `ValueError("Cannot follow previous direction: no PREV_DIRECTION data on any line. Import an SPS file that includes direction, or uncheck the option.")`.
- If some lines have direction and some don't, log a warning listing the lines without direction; proceed with alternation for those.

## State cleanup

Replace the 5 `self.last_*` fields (dockwidget `:154-158`):

```python
# OLD
self.last_simulation_result = None
self.last_sim_params = None
self.last_line_data = None
self.last_required_layers = None
self.last_turn_cache = {}

# NEW
self._last_run: SimulationResult | None = None
```

**~51 read/write sites** across the dockwidget need updating. Grep pattern: `self\.last_(simulation_result|sim_params|line_data|required_layers|turn_cache)`. Each becomes `self._last_run.X` where `X` is the matching attribute. Any read that happens before `handle_run_simulation` completes needs a None check.

## `handle_run_simulation` rewrite (`:6682-6976`)

Target: from 294 lines to ~35 lines.

```python
def handle_run_simulation(self):
    log.info("Run Simulation clicked.")
    QApplication.setOverrideCursor(Qt.WaitCursor)
    self._last_run = None
    if hasattr(self, 'editFinalizeButton'):
        self.editFinalizeButton.setEnabled(False)
    try:
        params = SimulationParams.from_ui(self)
        service = SimulationService(iface=self.iface)
        result = service.run(params)
        self._last_run = result
        self._display_results(result)
        if hasattr(self, 'editFinalizeButton'):
            self.editFinalizeButton.setEnabled(True)
    except ValueError as e:
        log.warning(f"Simulation parameter error: {e}")
        QMessageBox.warning(self, "Simulation failed", str(e))
    except Exception as e:
        log.exception(f"Unexpected simulation error: {e}")
        QMessageBox.critical(self, "Simulation error", f"Unexpected error: {e}\n\nSee log for details.")
    finally:
        QApplication.restoreOverrideCursor()
```

`_display_results(result)` is a thin dockwidget method that populates the timing table. Stays in the dockwidget (UI responsibility). ~30 lines — not worth extracting.

## Tests

### Extends `test/test_sequence_service.py`

- `test_racetrack_follow_previous_pins_direction` — all lines have PREV_DIRECTION 76.8 or 256.8; assert each line's assigned direction matches.
- `test_racetrack_follow_previous_missing_data_falls_back` — half the lines lack PREV_DIRECTION; assert alternation for those + warning logged.
- `test_teardrop_follow_previous_respects_direction` — similar.
- `test_assign_direction_within_tolerance` — PREV_DIRECTION 76.85 still matches expected 76.8 heading within 1°.
- `test_assign_direction_opposite_match` — PREV_DIRECTION 256.8 matches reciprocal heading within 1°.

### New `test/test_simulation_service.py` (requires `qgis.core` for layer fixtures)

- `test_run_happy_path` — minimal fixture of 3 lines; mode=Racetrack; assert result returned with non-empty sequence and positive total_cost.
- `test_run_raises_on_empty_lines` — empty `Generated_Survey_Lines` layer; assert `ValueError`.
- `test_run_raises_on_follow_previous_without_data` — `follow_previous_direction=True` but no PREV_DIRECTION field → clear error message.
- `test_result_dataclass_contains_everything_editor_needs` — all 7 fields populated after a successful run.

## Verify

1. `pytest test/` — all green (sequence + turn_cache from Phase 5, simulation_service new).
2. QGIS smoke test with `follow_previous_direction=False` (default): Racetrack and Teardrop output identical to Phase 5 baseline cost-in-hours to <0.001%.
3. QGIS smoke test with `follow_previous_direction=True` (manually toggle via `self._last_run = None; params.follow_previous_direction = True; SimulationService(self.iface).run(params)` in Python console; UI checkbox comes in Phase 8):
   - Import Martin Linge SPS. Generate lines. Run simulation with feature on.
   - Each line is shot in the direction matching its PREV_DIRECTION.
   - Total time may differ from baseline (expected; that's the feature's point).
4. `wc -l obn_planner_dockwidget.py` — dropped by at least 1500 lines (`handle_run_simulation` + the 6 extracted helpers).
5. `grep self.last_` in dockwidget → 0 matches (all migrated to `self._last_run`).

## Rollback

Per-commit revert order:
1. Revert direction-following logic in sequence_service (feature off)
2. Revert simulation_service extraction
3. Revert state cleanup (`self.last_*` → `self._last_run`)

Each sub-step is a separate commit to enable piecewise revert.

## Risks and unknowns

- **51 call sites for `self.last_*`** — grep may find more. Each needs `self._last_run` with a None check. Miss one and you get `AttributeError` at runtime — not caught by tests unless tests cover that path.
- **`_display_results` interaction with sequence editor** — the editor reads the simulation result. Verify it still works after state cleanup. The editor's `initial_sequence_info` dict at `sequence_edit_dialog.py:86` must match the new `SimulationResult` dataclass fields, or an adapter is needed.
- **Unit check at Dubins boundary** — `SimulationParams` stores turn_radius in meters, speeds in knots (converted to m/s internally). Heading is in degrees for `PREV_DIRECTION` but `TurnCache` takes radians for Dubins. The conversion site must be single and documented. Add an explicit `math.radians()` call at the boundary; never mix.
- **`follow_previous_direction` + Teardrop interaction** — Teardrop's greedy next-line picker currently alternates direction. With feature on, direction is pinned regardless of alternation, which may produce inefficient turn patterns. This is by design (user wants to match prior sequence) but may surprise users. Document in phase docs.
- **`SimulationResult` field count** — currently 7 fields; any new UI need (e.g., "which lines had PREV_DIRECTION fallbacks?") adds a field. Keep the dataclass lean.
- **`_reconstruct_path` stub** — Phase 6 ships it as a passthrough/placeholder; Phase 7 extracts the full implementation. If the stub breaks visualization, revert the `handle_run_simulation` rewrite and keep the extraction for Phase 7.

## Hard Stop Gate

Phase 6 is complete when:
1. All tests green.
2. Default behavior (feature off) matches Phase 5 baseline exactly.
3. Direction-following (feature on, via Python console) works on Martin Linge data.
4. `self.last_*` fully migrated.
5. `handle_run_simulation` is under 40 lines.

**Claude MUST stop after Phase 6 and await explicit "proceed to Phase 7" from user.**

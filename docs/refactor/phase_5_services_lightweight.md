# Phase 5 — Services: lightweight (turn_cache, sequence_service)

**Size:** medium
**Risk:** low/medium (pure extraction; no behavior change if done carefully)
**Blocks:** Phase 6 (simulation_service consumes both these services)
**Blocked by:** Phases 0-4

## Goal

Extract the two most self-contained service candidates from the god class into `services/turn_cache.py` and `services/sequence_service.py`. Both are high-cohesion, low-coupling subsystems that can be unit-tested without QGIS.

**No behavior change in this phase.** The existing dockwidget methods still work; the extracted services are parallel implementations that Phase 6 wires in.

## Why these two first

- **`turn_cache`** — currently a raw `dict` on `self.last_turn_cache` and the `_get_cached_turn` method (~line 8100 in dockwidget). Single responsibility, clear interface, no QGIS layer access.
- **`sequence_service`** — racetrack + teardrop generators. Manipulate ints and floats (line numbers, costs). Can be tested with plain Python dicts as input.

These two have the highest test-coverage-per-line ratio of any service candidate. Getting them out first means Phase 6 can rely on already-tested building blocks.

## `services/turn_cache.py` (new)

```python
from __future__ import annotations
from dataclasses import dataclass
from qgis.core import QgsGeometry, QgsPointXY

@dataclass(frozen=True)
class TurnKey:
    from_line: int
    to_line: int
    to_reciprocal: bool

@dataclass(frozen=True)
class TurnResult:
    geometry: QgsGeometry
    length_m: float
    time_s: float

class TurnCache:
    """Caches Dubins turn computations between line acquisitions."""
    def __init__(self, dubins_radius: float, turn_speed_mps: float, densification_m: float):
        self._cache: dict[TurnKey, TurnResult] = {}
        self._radius = dubins_radius
        self._speed = turn_speed_mps
        self._density = densification_m

    def get(self, key: TurnKey, exit_pt: QgsPointXY, exit_hdg_rad: float,
            entry_pt: QgsPointXY, entry_hdg_rad: float) -> TurnResult:
        if key not in self._cache:
            self._cache[key] = self._compute(exit_pt, exit_hdg_rad, entry_pt, entry_hdg_rad)
        return self._cache[key]

    def _compute(self, exit_pt, exit_hdg_rad, entry_pt, entry_hdg_rad) -> TurnResult:
        from ..geometry.dubins import get_curve    # or wherever Phase 1 placed it
        points = get_curve(
            s_x=exit_pt.x(), s_y=exit_pt.y(), s_head=exit_hdg_rad,
            e_x=entry_pt.x(), e_y=entry_pt.y(), e_head=entry_hdg_rad,
            radius=self._radius, max_line_distance=self._density,
        )
        geom, length = self._points_to_geometry(points)
        return TurnResult(geometry=geom, length_m=length, time_s=length / self._speed)

    @staticmethod
    def _points_to_geometry(points: list) -> tuple[QgsGeometry, float]:
        from qgis.core import QgsGeometry, QgsPointXY
        pts = [QgsPointXY(p[0], p[1]) for p in points]
        geom = QgsGeometry.fromPolylineXY(pts)
        return geom, geom.length()
```

## `services/sequence_service.py` (new)

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from ..ui.constants import AcquisitionMode   # created in Phase 8; for now use string

@dataclass
class LineInfo:
    line_num: int
    prev_direction: float | None = None   # used by Phase 6 direction-following

def generate_racetrack_sequence(
    active_lines: list[int],
    first_line: int,
    turn_radius_m: float,
    line_spacing_m: float,
) -> list[int]:
    """Interleaved racetrack. Extracted from
    obn_planner_dockwidget.py:8718-8830 (_generate_interleaved_racetrack_sequence)."""
    ...  # body copied verbatim then cleaned up

def determine_next_line_teardrop(
    last_line: int,
    remaining: set[int],
    line_directions: dict[int, str],
) -> int | None:
    """Teardrop greedy next-line picker. Extracted from
    obn_planner_dockwidget.py:8888 (_determine_next_line)."""
    ...  # body copied verbatim

def calculate_most_common_step(line_nums: list[int]) -> int:
    """Extracted from obn_planner_dockwidget.py:8832."""
    ...

def find_closest_line_index(target: int, sorted_lines: list[int]) -> int:
    """Extracted from obn_planner_dockwidget.py:8858."""
    ...
```

**Signatures are pure Python.** No `QgsGeometry`, no `QWidget`, no `self`. The helpers at lines 8832 and 8858 are already pure; extraction is trivial.

## Dockwidget changes

The existing `_generate_interleaved_racetrack_sequence`, `_determine_next_line`, `_calculate_most_common_step`, `_find_closest_line_index`, and `_get_cached_turn` methods are **kept as thin wrappers** that delegate to the new services. This means Phase 5 ships with zero behavior change — the existing code path still works through the old method names.

Phase 6 then rewires `handle_run_simulation` to call the services directly, and Phase 7 removes the wrapper methods.

Wrapper pattern:

```python
def _generate_interleaved_racetrack_sequence(self, active_lines, first_line, jump):
    from .services.sequence_service import generate_racetrack_sequence
    return generate_racetrack_sequence(active_lines, first_line, self._turn_radius(), self._line_spacing())
```

## Tests

### `test/test_turn_cache.py` (new, requires `qgis.core` for `QgsPointXY`)

```
test_cache_hit_returns_identical_result    — two calls with same key → one Dubins computation
test_cache_miss_on_different_key           — different keys → two computations
test_cache_key_includes_reciprocal         — same lines but different direction → different keys
```

Uses a small stub for `get_curve` (monkey-patched) that counts invocations.

### `test/test_sequence_service.py` (new, pure Python)

```
test_racetrack_4_lines_small_radius               — known interleaved order
test_racetrack_ideal_jump_respects_turn_radius    — larger radius → wider line jumps
test_racetrack_odd_line_count                     — edge: can't pair perfectly
test_teardrop_nearest_unvisited                   — greedy picks closest line by number
test_teardrop_alternates_direction                — each successive line shot in opposite direction
test_calculate_most_common_step_regular           — [1000, 1006, 1012, 1018] → 6
test_calculate_most_common_step_irregular         — mixed spacings → picks mode
test_find_closest_line_index_exact                — exact match returns that index
test_find_closest_line_index_between              — midway between two → returns lower
```

All tests run without QGIS.

## Verify

1. `pytest test/test_sequence_service.py test/test_turn_cache.py` — green.
2. QGIS smoke test: Run Simulation both modes. Output identical to Phase 4 baseline (cost in hours must match to <0.001%). **Behavior is preserved by the wrapper pattern.**
3. Inspect log: new `services/` modules should appear in `logging.getLogger(__name__)` entries (`services.sequence_service`, `services.turn_cache`).
4. `wc -l services/sequence_service.py` ≈ 250-350 lines (original `_generate_interleaved_racetrack_sequence` plus `_determine_next_line` plus 2 helpers).

## Rollback

Per-service revert. If `turn_cache` breaks, revert just that commit. The wrappers in the dockwidget can fall back to their inline behavior (restore the inline code as part of the revert).

## Risks and unknowns

- **Circular imports** — `services/sequence_service.py` imports `ui/constants.py` for `AcquisitionMode`, but `ui/constants.py` doesn't exist until Phase 8. Workaround: Phase 5 uses plain strings; Phase 8 migrates to enums in a separate commit.
- **Hidden dependencies on `self`** — the current `_generate_interleaved_racetrack_sequence` may reference `self.some_attribute` deep in its body. Grep all `self.` uses within the method before extracting. Anything that's used must become an explicit parameter.
- **Teardrop `line_directions` dict** — mutable state. Decide whether the service returns a new dict or mutates the input. Recommended: pure function, returns new data.
- **`QgsPointXY` import in `turn_cache.py`** — this keeps the module dependent on `qgis.core`. That's acceptable per the layering rule ("services may use qgis.core but not QtWidgets"). Do not abstract further in this phase.

## Hard Stop Gate

Phase 5 is complete when:
1. `pytest` green (both new test files + all previously green tests).
2. QGIS smoke test confirms zero behavioral change.
3. The two new service modules exist at `services/sequence_service.py` and `services/turn_cache.py`.
4. Dockwidget methods are thin wrappers (verify via `wc -l` — each wrapper <10 lines).

**Claude MUST stop after Phase 5 and await explicit "proceed to Phase 6" from user. Do not auto-advance.**

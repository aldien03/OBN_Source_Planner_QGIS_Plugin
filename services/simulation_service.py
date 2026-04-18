"""
SimulationService — typed contracts and orchestration entry point.

Phase 6b ships ONLY the dataclasses (SimulationParams, SimulationResult)
plus a SimulationService class skeleton with a placeholder `run()` that
raises NotImplementedError. Phase 6c fills in `run()` and rewires
handle_run_simulation in the dockwidget.

This phase is purely additive — no production code path uses any of
this module yet. Existing handle_run_simulation continues to work
exactly as before.

Layering: this module may import qgis.core (for QgsVectorLayer typing)
but MUST NOT import qgis.PyQt.QtWidgets. The TYPE_CHECKING guard keeps
qgis.core out of the module's runtime import path so pure-Python tests
work without QGIS installed.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — type-hint only
    from qgis.core import QgsVectorLayer

from .turn_cache import TurnCache

log = logging.getLogger(__name__)


# Shared knots-to-mps constant. Mirrors the dockwidget's KNOTS_TO_MPS.
# Defined here so the dataclass derived properties don't need to import
# anything from the dockwidget.
KNOTS_TO_MPS = 0.514444


@dataclass
class SimulationParams:
    """All inputs needed to run one simulation.

    Field names match the legacy `sim_params` dict keys used throughout
    the dockwidget (e.g. turn_radius_meters, not turn_radius_m). This
    is intentional — Phase 6c migrates callers gradually, and matching
    names allow `to_legacy_dict()` to be a one-liner.
    """

    # Acquisition strategy
    acquisition_mode: str                  # "Racetrack" | "Teardrop" — enum in Phase 8
    first_line_num: int
    first_heading_option: str              # "Low to High SP" | "High to Low SP (Reciprocal)"
    start_sequence_number: int
    start_datetime: datetime

    # Vessel speeds (knots — m/s exposed as derived properties)
    avg_shooting_speed_knots: float
    avg_turn_speed_knots: float

    # Geometry / kinematic constraints
    turn_radius_meters: float
    vessel_turn_rate_dps: float            # degrees per second
    run_in_length_meters: float

    # Deviation
    deviation_clearance_m: float
    nogo_layer: Optional[Any] = None       # type: Optional[QgsVectorLayer] — None OK

    # Optional RRT tunables (used by deviation when applicable)
    rrt_step_size: Optional[float] = None
    rrt_max_iterations: Optional[int] = None
    rrt_goal_bias: Optional[float] = None

    # NEW in Phase 6 — wired to UI checkbox in Phase 8.
    # When True and PREV_DIRECTION is populated on the line layer,
    # SequenceService pins each line to its prior direction (4D monitor
    # survey use case). Default False preserves existing behavior.
    follow_previous_direction: bool = False

    # --- Derived properties --------------------------------------------------

    @property
    def avg_shooting_speed_mps(self) -> float:
        return self.avg_shooting_speed_knots * KNOTS_TO_MPS

    @property
    def avg_turn_speed_mps(self) -> float:
        return self.avg_turn_speed_knots * KNOTS_TO_MPS

    # --- Legacy interop ------------------------------------------------------

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Return a dict in the shape produced by the dockwidget's
        _gather_simulation_parameters. Phase 6c migrates callers
        incrementally; this bridge keeps un-migrated code working.
        """
        d = {
            "acquisition_mode": self.acquisition_mode,
            "first_line_num": self.first_line_num,
            "first_heading_option": self.first_heading_option,
            "start_sequence_number": self.start_sequence_number,
            "start_datetime": self.start_datetime,
            "avg_shooting_speed_knots": self.avg_shooting_speed_knots,
            "avg_shooting_speed_mps": self.avg_shooting_speed_mps,
            "avg_turn_speed_knots": self.avg_turn_speed_knots,
            "avg_turn_speed_mps": self.avg_turn_speed_mps,
            "turn_radius_meters": self.turn_radius_meters,
            "vessel_turn_rate_dps": self.vessel_turn_rate_dps,
            "run_in_length_meters": self.run_in_length_meters,
            "deviation_clearance_m": self.deviation_clearance_m,
            "nogo_layer": self.nogo_layer,
            "follow_previous_direction": self.follow_previous_direction,
        }
        # Optional RRT keys: only include when set, matching legacy behavior
        # where the dockwidget's loop only added the key when the SpinBox
        # existed.
        for key in ("rrt_step_size", "rrt_max_iterations", "rrt_goal_bias"):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        return d

    def validate(self) -> None:
        """Raise ValueError on invalid combinations. Mirrors the existing
        validation in _gather_simulation_parameters."""
        if self.avg_shooting_speed_mps <= 0:
            raise ValueError("Shooting Speed must be positive.")
        if self.avg_turn_speed_mps <= 0:
            raise ValueError("Turn Speed must be positive.")
        if self.turn_radius_meters <= 0:
            raise ValueError("Turn Radius must be positive.")
        if self.vessel_turn_rate_dps <= 0:
            raise ValueError("Turn Rate must be positive.")
        if self.deviation_clearance_m <= 0:
            raise ValueError("Deviation Clearance must be positive.")


@dataclass
class SimulationResult:
    """Everything one simulation run produced. Replaces the five
    self.last_* fields on the dockwidget (handed off to Phase 6c).

    `path_segments` and `line_directions` may be empty until the run
    completes — for example, an early ValueError raises before they
    are populated, in which case SimulationService.run() does not
    return a SimulationResult at all.
    """
    params: SimulationParams
    line_data: Dict[int, Any] = field(default_factory=dict)
    required_layers: Dict[str, Any] = field(default_factory=dict)
    turn_cache: TurnCache = field(default_factory=TurnCache)
    sequence: List[int] = field(default_factory=list)
    line_directions: Dict[int, str] = field(default_factory=dict)
    total_cost_seconds: float = 0.0
    path_segments: List[Any] = field(default_factory=list)

    @property
    def total_cost_hours(self) -> float:
        return self.total_cost_seconds / 3600.0


class SimulationService:
    """Phase 6b: skeleton only. Phase 6c implements run().

    The `iface` parameter is the QGIS interface handle (used by
    visualization paths in Phase 7). It is accepted now to lock in
    the constructor signature.
    """

    def __init__(self, iface: Any = None,
                 turn_cache: Optional[TurnCache] = None) -> None:
        self._iface = iface
        self._turn_cache = turn_cache if turn_cache is not None else TurnCache()

    def run(self, params: SimulationParams) -> SimulationResult:
        """Run a full simulation. To be implemented in Phase 6c."""
        raise NotImplementedError(
            "SimulationService.run() will be wired up in Phase 6c. "
            "Until then, handle_run_simulation in the dockwidget remains "
            "the orchestrator."
        )

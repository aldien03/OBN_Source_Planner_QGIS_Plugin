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

    # NEW in Phase 11 — wired to UI dropdown in Phase 11c.
    # "none"  -> current behavior (fixed geometric racetrack, greedy teardrop)
    # "2opt"  -> apply classic best-improvement 2-opt local search on the
    #            generated sequence, using _calculate_sequence_time as the
    #            cost oracle. Each 2-opt evaluation uses a DISPOSABLE turn
    #            cache to avoid cross-evaluation pollution from the latent
    #            cache-key bug in _get_cached_turn. Default "none" preserves
    #            existing behavior exactly.
    optimization_level: str = "none"

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
            "optimization_level": self.optimization_level,
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

    # --- UI builder (Phase 6c-1) ---------------------------------------------

    @classmethod
    def from_ui(cls, dockwidget: Any) -> "SimulationParams":
        """Build a SimulationParams by reading the dockwidget's UI widgets.

        Mirrors _gather_simulation_parameters one-to-one: same widget
        names, same defaults when widgets are absent, same ValueError /
        AttributeError on bad input. Used in shadow mode in Phase 6c-1
        to cross-check; replaces the legacy dict path in Phase 6c-3.

        Note: follow_previous_direction defaults to False here. The UI
        checkbox that drives it lands in Phase 8.
        """
        dw = dockwidget

        # Acquisition mode
        if hasattr(dw, "acquisitionModeComboBox"):
            acquisition_mode = dw.acquisitionModeComboBox.currentText()
        else:
            log.warning("Acquisition Mode ComboBox not found, defaulting to Racetrack")
            acquisition_mode = "Racetrack"

        # No-go layer (None is acceptable)
        nogo_layer = dw.nogo_zone_combo.currentLayer()

        # Deviation clearance — inline validation matches legacy
        if hasattr(dw, "deviationClearanceDoubleSpinBox"):
            deviation_clearance_m = dw.deviationClearanceDoubleSpinBox.value()
            if deviation_clearance_m <= 0:
                raise ValueError("Deviation Clearance must be positive.")
        else:
            log.warning("Deviation Clearance SpinBox not found, defaulting to 100.0m")
            deviation_clearance_m = 100.0

        # Optional RRT tunables — only set if SpinBox exists, matching
        # the legacy "loop and check hasattr" pattern
        rrt_step_size = None
        rrt_max_iterations = None
        rrt_goal_bias = None
        if hasattr(dw, "rrt_step_sizeSpinBox"):
            rrt_step_size = dw.rrt_step_sizeSpinBox.value()
        if hasattr(dw, "rrt_max_iterationsSpinBox"):
            rrt_max_iterations = dw.rrt_max_iterationsSpinBox.value()
        if hasattr(dw, "rrt_goal_biasSpinBox"):
            rrt_goal_bias = dw.rrt_goal_biasSpinBox.value()

        # Sequence
        first_line_num = dw.firstLineSpinBox.value()
        first_heading_option = dw.firstHeadingComboBox.currentText()
        start_sequence_number = dw.firstSeqComboBox.value()

        # Acquisition speed — try primary widget first, then fallback,
        # mirroring legacy. AttributeError if neither exists.
        if hasattr(dw, "avgShootingSpeedDoubleSpinBox"):
            avg_shooting_speed_knots = dw.avgShootingSpeedDoubleSpinBox.value()
        elif hasattr(dw, "acqSpeedPrimaryDoubleSpinBox"):
            avg_shooting_speed_knots = dw.acqSpeedPrimaryDoubleSpinBox.value()
            log.info("Using 'acqSpeedPrimaryDoubleSpinBox' for acquisition speed.")
        else:
            raise AttributeError("Suitable acquisition speed input widget(s) not found.")

        # Turn parameters
        avg_turn_speed_knots = dw.turnSpeedDoubleSpinBox.value()
        turn_radius_meters = dw.turnRadiusDoubleSpinBox.value()

        # Vessel turn rate — default 3.0 if widget absent
        if hasattr(dw, "vesselTurnRateDoubleSpinBox"):
            vessel_turn_rate_dps = dw.vesselTurnRateDoubleSpinBox.value()
        else:
            log.warning("Vessel turn rate UI not found. Using default: 3.0 deg/sec")
            vessel_turn_rate_dps = 3.0

        run_in_length_meters = dw.maxRunInDoubleSpinBox.value()
        start_datetime = dw.startDateTimeEdit.dateTime().toPyDateTime()

        # Phase 8a: "Follow previous shooting direction" checkbox. Wired for
        # 4D monitor surveys where each line must be shot in the direction
        # stored in its PREV_DIRECTION attribute. hasattr fallback tolerates
        # older compiled UIs that predate the checkbox.
        if hasattr(dw, "followPreviousDirectionCheckBox"):
            follow_previous_direction = dw.followPreviousDirectionCheckBox.isChecked()
        else:
            log.warning(
                "followPreviousDirectionCheckBox not found — recompile resources "
                "to enable the 4D direction-following feature. Defaulting to False."
            )
            follow_previous_direction = False

        params = cls(
            acquisition_mode=acquisition_mode,
            first_line_num=first_line_num,
            first_heading_option=first_heading_option,
            start_sequence_number=start_sequence_number,
            start_datetime=start_datetime,
            avg_shooting_speed_knots=avg_shooting_speed_knots,
            avg_turn_speed_knots=avg_turn_speed_knots,
            turn_radius_meters=turn_radius_meters,
            vessel_turn_rate_dps=vessel_turn_rate_dps,
            run_in_length_meters=run_in_length_meters,
            deviation_clearance_m=deviation_clearance_m,
            nogo_layer=nogo_layer,
            rrt_step_size=rrt_step_size,
            rrt_max_iterations=rrt_max_iterations,
            rrt_goal_bias=rrt_goal_bias,
            follow_previous_direction=follow_previous_direction,
        )
        # Mirror the four post-gather ValueError checks in the legacy method
        params.validate()
        return params


# --- Shadow-mode cross-check helper (Phase 6c-1) ----------------------------

def diff_legacy_dict(legacy: Dict[str, Any], new: Dict[str, Any],
                     float_tol: float = 1e-6) -> List[str]:
    """Compare two legacy-shape params dicts. Return human-readable
    difference strings — empty list means identical (within float_tol).

    Used in Phase 6c-1 to verify SimulationParams.from_ui produces the
    same data as the legacy _gather_simulation_parameters dict. Phase 6c-3
    deletes the legacy path entirely; until then this is the safety net.

    Only checks keys present in `legacy`. Keys present only in `new`
    (e.g. follow_previous_direction added in Phase 6) are ignored.
    """
    diffs: List[str] = []
    for key in legacy:
        if key not in new:
            diffs.append(f"{key!r}: missing in new dict")
            continue
        v1 = legacy[key]
        v2 = new[key]
        # Numeric fields: compare with tolerance
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)) \
                and not isinstance(v1, bool) and not isinstance(v2, bool):
            if abs(v1 - v2) > float_tol:
                diffs.append(f"{key!r}: legacy={v1!r} new={v2!r} (Δ={v1-v2:.6g})")
            continue
        # Object identity (e.g. QgsVectorLayer) before equality
        if v1 is v2:
            continue
        if v1 != v2:
            diffs.append(f"{key!r}: legacy={v1!r} new={v2!r}")
    return diffs


@dataclass
class _LastRunShim:
    """Phase 6c-2: backward-compat container for the 5 self.last_* fields
    that used to live as bare instance attributes on the dockwidget.

    The dockwidget now holds a single self._last_run = _LastRunShim()
    instance. Five @property pairs on the dockwidget delegate
    self.last_simulation_result, self.last_sim_params, self.last_line_data,
    self.last_required_layers, self.last_turn_cache to the corresponding
    fields here. All 46 existing call sites continue to work unchanged.

    Field defaults match the legacy initial state: None for four,
    empty dict for turn_cache. This dataclass is intentionally typed
    Any — Phase 6c-3 may replace it with the typed SimulationResult,
    or keep it as a permanent legacy-name adapter. Either is fine;
    the abstraction is there.
    """
    simulation_result: Any = None
    sim_params: Any = None
    line_data: Any = None
    required_layers: Any = None
    turn_cache: Any = field(default_factory=dict)


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

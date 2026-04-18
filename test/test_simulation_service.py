# coding=utf-8
"""Phase 6b simulation_service dataclass tests — pure Python, no QGIS.

Phase 6b only delivers the data contracts. SimulationService.run() is a
NotImplementedError placeholder; Phase 6c will fill it in.

    python3 test/test_simulation_service.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import os
import sys
import unittest
from datetime import datetime

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.simulation_service import (  # noqa: E402
    SimulationParams, SimulationResult, SimulationService,
    KNOTS_TO_MPS,
)
from services.turn_cache import TurnCache  # noqa: E402


def _minimal_params(**overrides):
    """Build a SimulationParams with sensible defaults for tests.
    Override any field via kwargs."""
    base = dict(
        acquisition_mode="Racetrack",
        first_line_num=1000,
        first_heading_option="Low to High SP",
        start_sequence_number=1000,
        start_datetime=datetime(2026, 4, 17, 9, 0, 0),
        avg_shooting_speed_knots=4.5,
        avg_turn_speed_knots=4.0,
        turn_radius_meters=500.0,
        vessel_turn_rate_dps=3.0,
        run_in_length_meters=1000.0,
        deviation_clearance_m=100.0,
    )
    base.update(overrides)
    return SimulationParams(**base)


class SimulationParamsBasicTests(unittest.TestCase):
    def test_construct_with_required_fields(self):
        p = _minimal_params()
        self.assertEqual(p.acquisition_mode, "Racetrack")
        self.assertEqual(p.first_line_num, 1000)
        self.assertEqual(p.turn_radius_meters, 500.0)

    def test_optional_fields_default_correctly(self):
        p = _minimal_params()
        self.assertIsNone(p.nogo_layer)
        self.assertIsNone(p.rrt_step_size)
        self.assertIsNone(p.rrt_max_iterations)
        self.assertIsNone(p.rrt_goal_bias)
        self.assertFalse(p.follow_previous_direction,
                         "follow_previous_direction MUST default to False to "
                         "preserve existing behavior — Phase 8 UI checkbox "
                         "opts users in explicitly")


class DerivedSpeedPropertyTests(unittest.TestCase):
    def test_shooting_speed_mps(self):
        p = _minimal_params(avg_shooting_speed_knots=4.5)
        self.assertAlmostEqual(p.avg_shooting_speed_mps, 4.5 * KNOTS_TO_MPS, places=6)

    def test_turn_speed_mps(self):
        p = _minimal_params(avg_turn_speed_knots=8.0)
        self.assertAlmostEqual(p.avg_turn_speed_mps, 8.0 * KNOTS_TO_MPS, places=6)

    def test_zero_knots_zero_mps(self):
        p = _minimal_params(avg_shooting_speed_knots=0.0)
        self.assertEqual(p.avg_shooting_speed_mps, 0.0)


class LegacyDictTests(unittest.TestCase):
    """SimulationParams.to_legacy_dict() must produce the exact key set the
    dockwidget's pre-existing methods expect."""

    def test_includes_all_required_legacy_keys(self):
        p = _minimal_params()
        d = p.to_legacy_dict()
        # Keys gathered from _gather_simulation_parameters in the dockwidget
        for key in [
            "acquisition_mode", "first_line_num", "first_heading_option",
            "start_sequence_number", "start_datetime",
            "avg_shooting_speed_knots", "avg_shooting_speed_mps",
            "avg_turn_speed_knots", "avg_turn_speed_mps",
            "turn_radius_meters", "vessel_turn_rate_dps",
            "run_in_length_meters", "deviation_clearance_m",
            "nogo_layer", "follow_previous_direction",
        ]:
            self.assertIn(key, d, f"legacy dict missing required key {key!r}")

    def test_omits_rrt_keys_when_unset(self):
        """Match legacy: rrt_* keys are only present when their UI element
        existed and a value was gathered."""
        p = _minimal_params()
        d = p.to_legacy_dict()
        for key in ("rrt_step_size", "rrt_max_iterations", "rrt_goal_bias"):
            self.assertNotIn(key, d, f"unset RRT key {key!r} must not appear in legacy dict")

    def test_includes_rrt_keys_when_set(self):
        p = _minimal_params(rrt_step_size=50.0, rrt_max_iterations=20000,
                            rrt_goal_bias=0.2)
        d = p.to_legacy_dict()
        self.assertEqual(d["rrt_step_size"], 50.0)
        self.assertEqual(d["rrt_max_iterations"], 20000)
        self.assertEqual(d["rrt_goal_bias"], 0.2)

    def test_derived_mps_present_in_legacy(self):
        """Existing dockwidget code reads sim_params['avg_shooting_speed_mps']
        directly — the dict must contain the derived value, not just the
        knot input."""
        p = _minimal_params(avg_shooting_speed_knots=5.0, avg_turn_speed_knots=4.0)
        d = p.to_legacy_dict()
        self.assertAlmostEqual(d["avg_shooting_speed_mps"], 5.0 * KNOTS_TO_MPS, places=6)
        self.assertAlmostEqual(d["avg_turn_speed_mps"], 4.0 * KNOTS_TO_MPS, places=6)


class ValidationTests(unittest.TestCase):
    def test_valid_params_pass(self):
        _minimal_params().validate()  # must not raise

    def test_zero_shooting_speed_rejected(self):
        with self.assertRaisesRegex(ValueError, "Shooting Speed"):
            _minimal_params(avg_shooting_speed_knots=0).validate()

    def test_negative_turn_radius_rejected(self):
        with self.assertRaisesRegex(ValueError, "Turn Radius"):
            _minimal_params(turn_radius_meters=-1.0).validate()

    def test_zero_clearance_rejected(self):
        with self.assertRaisesRegex(ValueError, "Clearance"):
            _minimal_params(deviation_clearance_m=0).validate()


class SimulationResultShapeTests(unittest.TestCase):
    def test_default_construction(self):
        p = _minimal_params()
        r = SimulationResult(params=p)
        self.assertIs(r.params, p)
        self.assertEqual(r.line_data, {})
        self.assertEqual(r.required_layers, {})
        self.assertIsInstance(r.turn_cache, TurnCache)
        self.assertEqual(r.sequence, [])
        self.assertEqual(r.line_directions, {})
        self.assertEqual(r.total_cost_seconds, 0.0)
        self.assertEqual(r.path_segments, [])

    def test_total_cost_hours_property(self):
        r = SimulationResult(params=_minimal_params(), total_cost_seconds=3600.0)
        self.assertAlmostEqual(r.total_cost_hours, 1.0, places=6)
        r2 = SimulationResult(params=_minimal_params(), total_cost_seconds=5400.0)
        self.assertAlmostEqual(r2.total_cost_hours, 1.5, places=6)

    def test_can_carry_arbitrary_line_data(self):
        """line_data is dict[int, Any] — Phase 6c populates it with dicts
        per line. Verify free-form values pass through."""
        r = SimulationResult(params=_minimal_params(),
                             line_data={1000: {"foo": "bar"}, 1006: 42})
        self.assertEqual(r.line_data[1000]["foo"], "bar")
        self.assertEqual(r.line_data[1006], 42)


class ServiceSkeletonTests(unittest.TestCase):
    """Phase 6b ships the constructor signature; run() must raise
    NotImplementedError until Phase 6c."""

    def test_construct_with_no_iface(self):
        svc = SimulationService()
        self.assertIsNotNone(svc._turn_cache, "default TurnCache must be created")

    def test_construct_with_provided_turn_cache(self):
        cache = TurnCache()
        svc = SimulationService(iface=None, turn_cache=cache)
        self.assertIs(svc._turn_cache, cache)

    def test_run_raises_not_implemented(self):
        svc = SimulationService()
        with self.assertRaises(NotImplementedError) as ctx:
            svc.run(_minimal_params())
        # Error message must point at Phase 6c so future readers know what's missing
        self.assertIn("Phase 6c", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

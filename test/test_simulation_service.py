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
    KNOTS_TO_MPS, diff_legacy_dict, _LastRunShim,
)
from services.turn_cache import TurnCache  # noqa: E402


# --- Fake dockwidget for from_ui tests --------------------------------------

class _FakeSpinBox:
    def __init__(self, v): self._v = v
    def value(self): return self._v


class _FakeComboBox:
    """Stands in for both QComboBox (currentText) and QgsMapLayerComboBox
    (currentLayer). Returning the same _v from both is fine for tests."""
    def __init__(self, v): self._v = v
    def currentText(self): return self._v
    def currentLayer(self): return self._v


class _FakeCheckBox:
    """Stand-in for QCheckBox."""
    def __init__(self, checked=False): self._checked = checked
    def isChecked(self): return self._checked


class _FakeQDateTime:
    def __init__(self, py_dt): self._dt = py_dt
    def toPyDateTime(self): return self._dt


class _FakeDateTimeEdit:
    def __init__(self, py_dt): self._dt = py_dt
    def dateTime(self): return _FakeQDateTime(self._dt)


def _make_fake_dockwidget(**overrides):
    """Build a fake dockwidget exposing the widgets _gather_simulation_parameters
    reads. Overrides replace specific widget instances OR set them to None
    (deletes the attribute, simulating a missing widget)."""
    dw = type("FakeDockwidget", (), {})()  # blank object
    dw.acquisitionModeComboBox = _FakeComboBox("Racetrack")
    dw.nogo_zone_combo = _FakeComboBox(None)
    dw.deviationClearanceDoubleSpinBox = _FakeSpinBox(100.0)
    dw.firstLineSpinBox = _FakeSpinBox(1000)
    dw.firstHeadingComboBox = _FakeComboBox("Low to High SP")
    dw.firstSeqComboBox = _FakeSpinBox(1000)
    dw.acqSpeedPrimaryDoubleSpinBox = _FakeSpinBox(4.5)
    dw.turnSpeedDoubleSpinBox = _FakeSpinBox(4.0)
    dw.turnRadiusDoubleSpinBox = _FakeSpinBox(500.0)
    dw.vesselTurnRateDoubleSpinBox = _FakeSpinBox(3.0)
    dw.maxRunInDoubleSpinBox = _FakeSpinBox(1000.0)
    dw.startDateTimeEdit = _FakeDateTimeEdit(datetime(2026, 4, 17, 9, 0, 0))
    for name, val in overrides.items():
        if val is None and hasattr(dw, name):
            delattr(dw, name)  # simulate missing widget
        else:
            setattr(dw, name, val)
    return dw


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


class FromUiHappyPathTests(unittest.TestCase):
    """SimulationParams.from_ui builds the expected dataclass from a
    fully-populated fake dockwidget."""

    def test_all_fields_populated(self):
        dw = _make_fake_dockwidget()
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.acquisition_mode, "Racetrack")
        self.assertEqual(p.first_line_num, 1000)
        self.assertEqual(p.first_heading_option, "Low to High SP")
        self.assertEqual(p.start_sequence_number, 1000)
        self.assertEqual(p.start_datetime, datetime(2026, 4, 17, 9, 0, 0))
        self.assertEqual(p.avg_shooting_speed_knots, 4.5)
        self.assertEqual(p.avg_turn_speed_knots, 4.0)
        self.assertEqual(p.turn_radius_meters, 500.0)
        self.assertEqual(p.vessel_turn_rate_dps, 3.0)
        self.assertEqual(p.run_in_length_meters, 1000.0)
        self.assertEqual(p.deviation_clearance_m, 100.0)

    def test_follow_previous_direction_defaults_false(self):
        """from_ui must NOT enable the new feature for users who didn't
        opt in (Phase 8 adds the UI checkbox)."""
        p = SimulationParams.from_ui(_make_fake_dockwidget())
        self.assertFalse(p.follow_previous_direction)

    def test_optimization_level_defaults_none(self):
        """Phase 11b: default must be 'none' so existing users see no
        behavior change. Phase 11c adds the UI dropdown."""
        p = SimulationParams(
            acquisition_mode="Racetrack", first_line_num=1000,
            first_heading_option="Low to High SP", start_sequence_number=1000,
            start_datetime=datetime(2026, 4, 18),
            avg_shooting_speed_knots=4.5, avg_turn_speed_knots=4.0,
            turn_radius_meters=500.0, vessel_turn_rate_dps=3.0,
            run_in_length_meters=1000.0, deviation_clearance_m=100.0,
        )
        self.assertEqual(p.optimization_level, "none")

    def test_optimization_level_propagates_to_legacy_dict(self):
        """to_legacy_dict must include optimization_level so the dockwidget's
        handle_run_simulation can read it alongside other params."""
        p = SimulationParams(
            acquisition_mode="Racetrack", first_line_num=1000,
            first_heading_option="Low to High SP", start_sequence_number=1000,
            start_datetime=datetime(2026, 4, 18),
            avg_shooting_speed_knots=4.5, avg_turn_speed_knots=4.0,
            turn_radius_meters=500.0, vessel_turn_rate_dps=3.0,
            run_in_length_meters=1000.0, deviation_clearance_m=100.0,
            optimization_level="2opt",
        )
        d = p.to_legacy_dict()
        self.assertEqual(d.get("optimization_level"), "2opt")


class FromUiMissingWidgetTests(unittest.TestCase):
    """from_ui mirrors the legacy method's defaults when widgets are absent."""

    def test_missing_acquisition_combo_defaults_racetrack(self):
        dw = _make_fake_dockwidget(acquisitionModeComboBox=None)
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.acquisition_mode, "Racetrack")

    def test_missing_clearance_defaults_100(self):
        dw = _make_fake_dockwidget(deviationClearanceDoubleSpinBox=None)
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.deviation_clearance_m, 100.0)

    def test_missing_turn_rate_defaults_3(self):
        dw = _make_fake_dockwidget(vesselTurnRateDoubleSpinBox=None)
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.vessel_turn_rate_dps, 3.0)

    def test_missing_both_speed_widgets_raises_attribute_error(self):
        dw = _make_fake_dockwidget(acqSpeedPrimaryDoubleSpinBox=None)
        # avgShootingSpeedDoubleSpinBox not in fake by default, so neither exists
        with self.assertRaises(AttributeError):
            SimulationParams.from_ui(dw)

    def test_primary_speed_widget_takes_precedence(self):
        """If avgShootingSpeedDoubleSpinBox exists, it is preferred over
        acqSpeedPrimaryDoubleSpinBox."""
        dw = _make_fake_dockwidget()
        dw.avgShootingSpeedDoubleSpinBox = _FakeSpinBox(5.5)
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.avg_shooting_speed_knots, 5.5,
                         "primary widget value must win")


class FromUiValidationTests(unittest.TestCase):
    def test_zero_clearance_raises_inline(self):
        """deviation_clearance_m == 0 with widget present must raise during
        gathering (before validate()), matching legacy behavior."""
        dw = _make_fake_dockwidget(deviationClearanceDoubleSpinBox=_FakeSpinBox(0.0))
        with self.assertRaisesRegex(ValueError, "Deviation Clearance"):
            SimulationParams.from_ui(dw)

    def test_zero_shooting_speed_raises_in_validate(self):
        dw = _make_fake_dockwidget(acqSpeedPrimaryDoubleSpinBox=_FakeSpinBox(0.0))
        with self.assertRaisesRegex(ValueError, "Shooting Speed"):
            SimulationParams.from_ui(dw)

    def test_zero_turn_radius_raises_in_validate(self):
        dw = _make_fake_dockwidget(turnRadiusDoubleSpinBox=_FakeSpinBox(0.0))
        with self.assertRaisesRegex(ValueError, "Turn Radius"):
            SimulationParams.from_ui(dw)


class FromUiFollowPreviousDirectionTests(unittest.TestCase):
    """Phase 8a: SimulationParams.from_ui reads the
    followPreviousDirectionCheckBox when present. When absent (older
    compiled UI), defaults to False with a log warning — the simulation
    must never break because the checkbox hasn't been compiled in yet."""

    def test_checkbox_unchecked_default(self):
        """Default state: checkbox exists, unchecked. follow_previous_direction=False."""
        dw = _make_fake_dockwidget()
        dw.followPreviousDirectionCheckBox = _FakeCheckBox(checked=False)
        p = SimulationParams.from_ui(dw)
        self.assertFalse(p.follow_previous_direction)

    def test_checkbox_checked_enables_feature(self):
        """User ticked the checkbox (4D monitor use case): from_ui propagates True."""
        dw = _make_fake_dockwidget()
        dw.followPreviousDirectionCheckBox = _FakeCheckBox(checked=True)
        p = SimulationParams.from_ui(dw)
        self.assertTrue(p.follow_previous_direction,
                        "Checkbox True must produce follow_previous_direction=True")

    def test_checkbox_absent_falls_back_to_false(self):
        """Older compiled UI without the checkbox: no crash, feature off."""
        dw = _make_fake_dockwidget()
        # Do NOT set followPreviousDirectionCheckBox on dw
        p = SimulationParams.from_ui(dw)
        self.assertFalse(p.follow_previous_direction,
                         "Missing checkbox must default to False, not raise")


class FromUiSequenceOptimizationTests(unittest.TestCase):
    """Phase 11c: SimulationParams.from_ui reads the
    sequenceOptimizationComboBox when present. Default-if-absent keeps
    existing users on 'none' so behavior is preserved after recompile-
    less plugin updates."""

    def test_combo_absent_defaults_none(self):
        """Older compiled UI without the combobox: no crash, level='none'."""
        dw = _make_fake_dockwidget()
        # Do NOT set sequenceOptimizationComboBox on dw
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.optimization_level, "none")

    def test_combo_off_maps_to_none(self):
        dw = _make_fake_dockwidget()
        dw.sequenceOptimizationComboBox = _FakeComboBox("Off")
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.optimization_level, "none")

    def test_combo_2opt_maps_to_2opt(self):
        """User picks '2-opt' -> internal value '2opt' (stripped of the hyphen)."""
        dw = _make_fake_dockwidget()
        dw.sequenceOptimizationComboBox = _FakeComboBox("2-opt")
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.optimization_level, "2opt")

    def test_combo_unknown_label_safe_defaults_to_none(self):
        """If someone adds an unknown label to the combo (future UI), don't
        crash — default to 'none' and log a warning. Protects users from
        a malformed UI producing a crash at Run Simulation time."""
        dw = _make_fake_dockwidget()
        dw.sequenceOptimizationComboBox = _FakeComboBox("Simulated Annealing")
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.optimization_level, "none",
                         "unknown label must fall back to 'none', not raise")


class FromUiOptionalRrtTests(unittest.TestCase):
    def test_rrt_widgets_absent_means_none(self):
        p = SimulationParams.from_ui(_make_fake_dockwidget())
        self.assertIsNone(p.rrt_step_size)
        self.assertIsNone(p.rrt_max_iterations)
        self.assertIsNone(p.rrt_goal_bias)

    def test_rrt_widgets_present_populate_fields(self):
        dw = _make_fake_dockwidget()
        # Note the legacy attribute-name pattern: 'rrt_step_size' + 'SpinBox'
        setattr(dw, "rrt_step_sizeSpinBox", _FakeSpinBox(50.0))
        setattr(dw, "rrt_max_iterationsSpinBox", _FakeSpinBox(20000))
        setattr(dw, "rrt_goal_biasSpinBox", _FakeSpinBox(0.2))
        p = SimulationParams.from_ui(dw)
        self.assertEqual(p.rrt_step_size, 50.0)
        self.assertEqual(p.rrt_max_iterations, 20000)
        self.assertEqual(p.rrt_goal_bias, 0.2)


class DiffLegacyDictTests(unittest.TestCase):
    """diff_legacy_dict catches discrepancies the cross-check needs to flag."""

    def test_identical_dicts_no_diff(self):
        d = {"foo": 1, "bar": "x"}
        self.assertEqual(diff_legacy_dict(d, d.copy()), [])

    def test_missing_key_in_new(self):
        legacy = {"foo": 1, "bar": 2}
        new = {"foo": 1}
        diffs = diff_legacy_dict(legacy, new)
        self.assertEqual(len(diffs), 1)
        self.assertIn("'bar'", diffs[0])
        self.assertIn("missing", diffs[0])

    def test_extra_key_in_new_is_ignored(self):
        """new can have follow_previous_direction without flagging."""
        legacy = {"foo": 1}
        new = {"foo": 1, "follow_previous_direction": False}
        self.assertEqual(diff_legacy_dict(legacy, new), [])

    def test_float_within_tolerance_no_diff(self):
        # Default tolerance is 1e-6
        self.assertEqual(diff_legacy_dict({"x": 1.0}, {"x": 1.0000001}), [])

    def test_float_outside_tolerance_diffs(self):
        diffs = diff_legacy_dict({"x": 1.0}, {"x": 1.5})
        self.assertEqual(len(diffs), 1)
        self.assertIn("'x'", diffs[0])

    def test_int_value_diff(self):
        diffs = diff_legacy_dict({"a": 5}, {"a": 6})
        self.assertEqual(len(diffs), 1)

    def test_string_value_diff(self):
        diffs = diff_legacy_dict({"mode": "Racetrack"}, {"mode": "Teardrop"})
        self.assertEqual(len(diffs), 1)
        self.assertIn("Racetrack", diffs[0])
        self.assertIn("Teardrop", diffs[0])

    def test_object_identity_first(self):
        """Two unequal objects that ARE the same instance are equal here.
        (Used for QgsVectorLayer where object identity matters more than
        whatever __eq__ does.)"""
        class Layer:
            def __eq__(self, other): return False  # noisy __eq__
        layer = Layer()
        self.assertEqual(diff_legacy_dict({"nogo_layer": layer}, {"nogo_layer": layer}), [])

    def test_bool_treated_as_value_not_numeric(self):
        """In Python, True == 1 and False == 0, but they should diff."""
        # This guards against accidentally matching True with 1.0 numerically
        diffs = diff_legacy_dict({"x": True}, {"x": False})
        self.assertEqual(len(diffs), 1)


class FromUiToLegacyDictRoundTripTests(unittest.TestCase):
    """The full Phase 6c-1 cross-check pipeline:
    from_ui -> to_legacy_dict -> diff against a hand-built legacy dict."""

    def test_round_trip_minimal(self):
        dw = _make_fake_dockwidget()
        p = SimulationParams.from_ui(dw)
        new_dict = p.to_legacy_dict()

        # Hand-build the legacy dict shape from the same fake dockwidget
        # values (mirror what _gather_simulation_parameters would produce).
        legacy_dict = {
            "acquisition_mode": "Racetrack",
            "nogo_layer": None,
            "deviation_clearance_m": 100.0,
            "first_line_num": 1000,
            "first_heading_option": "Low to High SP",
            "start_sequence_number": 1000,
            "avg_shooting_speed_knots": 4.5,
            "avg_shooting_speed_mps": 4.5 * KNOTS_TO_MPS,
            "avg_turn_speed_knots": 4.0,
            "avg_turn_speed_mps": 4.0 * KNOTS_TO_MPS,
            "turn_radius_meters": 500.0,
            "vessel_turn_rate_dps": 3.0,
            "run_in_length_meters": 1000.0,
            "start_datetime": datetime(2026, 4, 17, 9, 0, 0),
        }
        # No legacy diffs → cross-check passes
        diffs = diff_legacy_dict(legacy_dict, new_dict)
        self.assertEqual(diffs, [],
                         f"unexpected diffs in round-trip cross-check: {diffs}")


class LastRunShimTests(unittest.TestCase):
    """Phase 6c-2: _LastRunShim is the backing storage that the dockwidget's
    legacy self.last_* @property pairs delegate to.

    These tests verify the shim's defaults and field-level read/write
    semantics. The actual property delegation is tested in
    LastRunShimPropertyDelegationTests below using a stand-in mock class
    (since the real dockwidget requires QGIS)."""

    def test_default_state_matches_legacy_initial(self):
        """Defaults must match what the dockwidget used to leave the 5
        bare attributes at: None for four, {} for turn_cache."""
        s = _LastRunShim()
        self.assertIsNone(s.simulation_result)
        self.assertIsNone(s.sim_params)
        self.assertIsNone(s.line_data)
        self.assertIsNone(s.required_layers)
        self.assertEqual(s.turn_cache, {})

    def test_each_default_turn_cache_is_independent(self):
        """default_factory=dict — instance-level dict, not shared."""
        a = _LastRunShim()
        b = _LastRunShim()
        a.turn_cache["k"] = "v"
        self.assertNotIn("k", b.turn_cache,
                         "turn_cache must NOT be shared across shim instances")

    def test_field_writes_persist(self):
        s = _LastRunShim()
        s.simulation_result = {"sequence": [1000, 1006]}
        s.sim_params = {"acquisition_mode": "Racetrack"}
        s.line_data = {1000: {"foo": 1}}
        s.required_layers = {"lines": object()}
        s.turn_cache = {("a", "b"): "result"}
        # Read back identical
        self.assertEqual(s.simulation_result, {"sequence": [1000, 1006]})
        self.assertEqual(s.sim_params, {"acquisition_mode": "Racetrack"})
        self.assertEqual(s.line_data, {1000: {"foo": 1}})
        self.assertIsNotNone(s.required_layers["lines"])
        self.assertEqual(s.turn_cache, {("a", "b"): "result"})

    def test_can_reset_to_defaults_via_assignment(self):
        """The dockwidget's existing reset code does
        `self.last_X = None` and `self.last_turn_cache = {}`. The shim
        must accept those assignments."""
        s = _LastRunShim()
        s.simulation_result = "anything"
        s.turn_cache = {"key": "val"}
        # Reset
        s.simulation_result = None
        s.sim_params = None
        s.line_data = None
        s.required_layers = None
        s.turn_cache = {}
        self.assertIsNone(s.simulation_result)
        self.assertEqual(s.turn_cache, {})


class LastRunShimPropertyDelegationTests(unittest.TestCase):
    """Verify the @property delegation pattern the dockwidget uses.

    We can't import the real OBNPlannerDockWidget without QGIS, so this
    test recreates the same pattern in a tiny stand-in class. If the
    pattern works here, the dockwidget's properties work the same way."""

    def _make_dockwidget_lookalike(self):
        """Build a small class that uses the exact same shim pattern."""
        class MiniDockwidget:
            def __init__(self):
                self._last_run = _LastRunShim()

            # Properties — mirror the exact pattern in obn_planner_dockwidget.py
            @property
            def last_simulation_result(self): return self._last_run.simulation_result
            @last_simulation_result.setter
            def last_simulation_result(self, v): self._last_run.simulation_result = v

            @property
            def last_sim_params(self): return self._last_run.sim_params
            @last_sim_params.setter
            def last_sim_params(self, v): self._last_run.sim_params = v

            @property
            def last_line_data(self): return self._last_run.line_data
            @last_line_data.setter
            def last_line_data(self, v): self._last_run.line_data = v

            @property
            def last_required_layers(self): return self._last_run.required_layers
            @last_required_layers.setter
            def last_required_layers(self, v): self._last_run.required_layers = v

            @property
            def last_turn_cache(self): return self._last_run.turn_cache
            @last_turn_cache.setter
            def last_turn_cache(self, v): self._last_run.turn_cache = v

        return MiniDockwidget()

    def test_initial_state_matches_legacy(self):
        dw = self._make_dockwidget_lookalike()
        self.assertIsNone(dw.last_simulation_result)
        self.assertIsNone(dw.last_sim_params)
        self.assertIsNone(dw.last_line_data)
        self.assertIsNone(dw.last_required_layers)
        self.assertEqual(dw.last_turn_cache, {})

    def test_writes_then_reads_round_trip(self):
        """Mirror the real handle_run_simulation pattern: write each
        field, read it back, verify identity."""
        dw = self._make_dockwidget_lookalike()
        sentinel = object()
        dw.last_sim_params = sentinel
        self.assertIs(dw.last_sim_params, sentinel,
                      "writes via property setter must be readable via getter")

    def test_reset_pattern_works(self):
        """Mirror handle_run_simulation lines 6445-6447 via the properties."""
        dw = self._make_dockwidget_lookalike()
        # Populate
        dw.last_simulation_result = "x"
        dw.last_sim_params = {"a": 1}
        dw.last_turn_cache = {"k": "v"}
        # Reset (the way handle_run_simulation does)
        dw.last_simulation_result = None
        dw.last_sim_params = None
        dw.last_line_data = None
        dw.last_required_layers = None
        dw.last_turn_cache = {}
        # All back to defaults
        self.assertIsNone(dw.last_simulation_result)
        self.assertIsNone(dw.last_sim_params)
        self.assertIsNone(dw.last_line_data)
        self.assertIsNone(dw.last_required_layers)
        self.assertEqual(dw.last_turn_cache, {})

    def test_turn_cache_clear_in_place(self):
        """Line 7289 in dockwidget: self.last_turn_cache.clear()
        Must mutate the dict in place, not raise."""
        dw = self._make_dockwidget_lookalike()
        dw.last_turn_cache = {"a": 1, "b": 2}
        dw.last_turn_cache.clear()
        self.assertEqual(dw.last_turn_cache, {},
                         ".clear() on the property must work the same as on a "
                         "raw dict attribute (dockwidget line 7289 does this)")

    def test_hasattr_returns_true_even_before_first_write(self):
        """Line 7612 in dockwidget uses hasattr(self, 'last_simulation_result').
        With @property, hasattr is always True (property exists at class level).
        This is a behavioral DIFFERENCE from the legacy bare-attribute pattern
        (where hasattr would be False before the first write) — but the only
        existing call site treats None and 'doesn't exist' the same way."""
        dw = self._make_dockwidget_lookalike()
        self.assertTrue(hasattr(dw, "last_simulation_result"))
        self.assertIsNone(dw.last_simulation_result,
                          "hasattr=True but the value is None — equivalent to "
                          "the old AttributeError check pattern")

    def test_independent_instances_dont_share_shim(self):
        """Two dockwidget instances must have independent shims."""
        dw1 = self._make_dockwidget_lookalike()
        dw2 = self._make_dockwidget_lookalike()
        dw1.last_sim_params = "for dw1 only"
        self.assertIsNone(dw2.last_sim_params,
                          "writing to dw1 must NOT affect dw2")


if __name__ == "__main__":
    unittest.main(verbosity=2)

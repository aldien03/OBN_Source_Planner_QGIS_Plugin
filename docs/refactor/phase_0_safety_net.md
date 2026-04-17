# Phase 0 — Safety net

**Size:** small
**Risk:** low
**Blocks:** none
**Blocked by:** user confirmation that this plan is accepted

## Goal

Establish a baseline from which behavioral regressions can be detected. Fix the one broken test and capture current Dubins output as golden values so Phase 1's refactor can be verified mechanically.

## Files touched

| Path | Action |
|---|---|
| `test/test_obn_planner_dockwidget.py:42` | Fix typo: `OBNPlannerDialogTest` → `OBNPlannerDockWidgetTest` (current code references an undefined class and would `NameError` if the test body were non-empty) |
| `test/test_dubins_smoke.py` | **New** — 3 golden-value tests on current Dubins output |
| `metadata.txt` | Bump `qgisMinimumVersion=3.0` → `qgisMinimumVersion=3.40` (Bratislava LTR target confirmed by user 2026-04-17). Verify exact field name via `grep qgisMinimum metadata.txt` before editing |
| `CLAUDE.md` | Update the "Code Conventions" line currently reading "Maintain compatibility with QGIS 3.0+ API" → "Maintain compatibility with QGIS 3.40+ (Bratislava LTR)" |
| `docs/refactor/README.md` | Already written as part of this plan delivery |
| (git) | Tag `refactor-baseline` at the commit completing Phase 0 (manual step by user) |

## Tests added

`test/test_dubins_smoke.py`:

- `test_dubins_straight_line_mode_is_SLS_or_straight` — given start `(0, 0, 0)` and end `(500, 0, 0)` with radius 50, assert the returned modes list is a known value (capture whatever today's code returns).
- `test_get_curve_returns_non_empty` — call `get_curve` with the same poses and `max_line_distance=10`; assert len(points) > 10 and first point is at start, last at end (within tolerance).
- `test_get_curve_point_format` — assert each point is a 3-element list `[x, y, heading_deg]` where heading is a finite float.

These are **characterization tests**: they lock in current behavior, whatever it is, so Phase 1's refactor can prove it made no accidental changes. They do NOT assert that the current behavior is correct — only that it's stable.

## Dependencies to add

- `pytest` — for running tests. Add to dev tooling docs; does not need to be a runtime dependency of the plugin.
  - `pip install pytest`
  - No code change required — pytest runs existing `unittest.TestCase` classes natively.

## Verify

1. `pytest test/` — green across all tests including the 3 new ones.
2. Load plugin in QGIS 3.40.5 Bratislava LTR via `pb_tool deploy` (or `make deploy` if pb_tool fails — see README packaging note).
3. QGIS plugin manager shows the updated minimum version.
4. Click every button that worked before: SPS Import, Calculate Headings, Apply Filter, Mark Acquired/TBA/Pending, Generate Lines, Calculate Deviations, Run Simulation (both modes), Edit & Finalize.
5. `git tag refactor-baseline` after the commit lands.

## Rollback

Single `git revert`. Nothing in production code changes in this phase — only test files and one string edit.

## Notes

- The existing `test_obn_planner_dockwidget.py:37` has `pass` as its body — leave that way. Adding real assertions here requires a QGIS test harness and is not needed to unblock later phases.
- Do not add fixtures yet — Phase 3 will set up `test/fixtures/*.sps` when they're actually needed.
- **QGIS version bump enablement**: bumping the minimum version to 3.40 means `QgsWkbTypes.isSurface` / `isPoint` / `isLine` are guaranteed to exist. The defensive `AttributeError` fallbacks at `obn_planner_dockwidget.py:121-134` can be simplified in a later phase — but DO NOT touch them in Phase 0. Phase 0 is pure infrastructure; simplification is deferred to Phase 7 when those helpers move to `geometry/wkb_helpers.py`.
- **Do not edit the Sphinx docs `help/index.rst`** — the plan treats those as untouched. `docs/refactor/` is the active documentation path.

## Hard Stop Gate

Phase 0 is complete when:
1. `pytest test/` runs green with the fixed test reference and 3 new Dubins smoke tests.
2. Plugin loads in QGIS 3.40.5 via `pb_tool deploy` (or `make deploy`).
3. Every button click-tested in QGIS — zero behavior change from pre-Phase-0 baseline.
4. `git tag refactor-baseline` applied at the Phase 0 completion commit.

**Claude MUST stop after Phase 0 and await explicit "proceed to Phase 1" from user. Do not auto-advance.**

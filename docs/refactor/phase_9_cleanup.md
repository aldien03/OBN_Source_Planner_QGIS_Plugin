# Phase 9 — Cleanup: logging, dead code, layering enforcement, final docs

**Size:** small
**Risk:** low
**Blocks:** none (final phase)
**Blocked by:** Phases 0-8

## Goal

Finish the revamp. Unify logging (no more `print()`), delete orphan code, enforce layering rules via tooling, fill in final documentation.

## Logging unification

`print(` grep today (before Phase 1):
- `rrt_planner.py`: ~14 calls (lines 93, 100, 150, 267+)
- `dubins_path.py`: ~14 calls (lines 124, 142, 150, 165, 177, 329, 405 and others)
- `obn_planner_dockwidget.py`: 1 stray (grep for location)

After Phase 1's edits, some of these may have moved. Re-grep at start of Phase 9:

```
grep -rn "print(" --include='*.py' . | grep -v test/ | grep -v __pycache__ | grep -v compile_resources.py
```

For each hit:
- Add `log = logging.getLogger(__name__)` at the top of the module (if absent)
- Replace `print(...)` with `log.debug(...)` (verbose traces), `log.info(...)` (milestones), or `log.warning(...)` (recoverable issues) based on severity

Target: zero matches after Phase 9.

## Dead code removal

- `backups/ais_live_tracker.py` — **delete**. User confirmed AIS is abandoned (2026-04-17).
- `backups/obn_planner_dockwidget.py.bak` — **keep**. Explicit backup.
- `rrt_planner.py` (or `geometry/rrt.py` if moved in Phase 7 cleanup) — **evaluate**:
  - If no production caller has emerged, delete. If you believe you may want RRT-based deviation in future, keep with a `# Unused — kept for future use` comment and a note in `docs/ARCHITECTURE.md`.
  - User context: v2 Peak/Tangent is the survivor. RRT was v1's algorithm. Unless a new feature depends on RRT, this code is dead.
- Orphan imports left by Phases 2, 5, 6, 7 — scan each touched file for unused `import` statements (ruff --select F401 catches these).
- Old `fixed_function.py` — already deleted in Phase 2; verify with `ls`.

## Layering enforcement

### `import-linter.toml` (new)

```toml
[tool.importlinter]
root_package = "obn_planner"

[[tool.importlinter.contracts]]
name = "geometry/dubins is pure-math"
type = "forbidden"
source_modules = ["obn_planner.geometry.dubins"]
forbidden_modules = ["qgis", "qgis.PyQt", "qgis.core"]

[[tool.importlinter.contracts]]
name = "io cannot import Qt widgets"
type = "forbidden"
source_modules = ["obn_planner.io"]
forbidden_modules = ["qgis.PyQt.QtWidgets"]

[[tool.importlinter.contracts]]
name = "services cannot import Qt widgets"
type = "forbidden"
source_modules = ["obn_planner.services"]
forbidden_modules = ["qgis.PyQt.QtWidgets"]

[[tool.importlinter.contracts]]
name = "services cannot import ui"
type = "forbidden"
source_modules = ["obn_planner.services"]
forbidden_modules = ["obn_planner.ui"]
```

Add to dev tooling docs: `pip install import-linter && lint-imports`.

Run in Phase 9 as a gate; failures block the phase.

### Optional: ruff

```toml
# ruff.toml
line-length = 120

[lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]  # long lines tolerated pre-revamp
```

`ruff check .` — fix low-effort wins (F401 unused imports, F841 unused variables). Don't aim for zero warnings; that's a separate effort.

## Documentation finalization

### `docs/ARCHITECTURE.md`

Fill in the stub sections:
- Final module dependency graph (ASCII or Mermaid)
- Service DAG
- Layering enforcement checklist — now backed by `import-linter`, not just review
- Deployment paths (both `pb_tool` and `Makefile` verified in Phase 7)

### `CLAUDE.md`

Update:
- "Architecture" section to reflect `geometry/`, `io/`, `services/`, `ui/` layout
- "File Structure" section
- "Fixed Functions" bullet — already removed in Phase 2; verify absent
- "Maintain compatibility with QGIS 3.0+ API" — already updated to 3.40+ in Phase 0

### Release notes

Create `docs/CHANGELOG.md` (or update existing changelog):

```markdown
# OBN Planner 2.0 — Maintainability Revamp

## Added
- Multi-format SPS support: auto-detection of SPS 1.0, SPS 2.1, SPS 2.1+direction, PXGEO, TGS, SAE variants
- SPS Format selector dropdown in UI (Auto-detect / explicit / Custom)
- "Follow previous shooting direction" option (Racetrack and Teardrop)
- Progress indication on Generate Lines and Calculate Deviations

## Changed
- Minimum QGIS version bumped from 3.0 to 3.40 (Bratislava LTR)
- SPS parser now correctly handles files with decimal line numbers (e.g., "2431.0" in Martin Linge format)
- Internal architecture: plugin logic split into geometry/, io/, services/, ui/ modules

## Fixed
- Dubins turn cache silent drift between runs (module-global leak)
- SPS import fails on real vendor files with certain column layouts (see CHANGELOG for full list of tested vendors)
- v1 RRT-based deviation algorithm (produced incorrect paths) — removed; v2 Peak/Tangent is the canonical algorithm

## Removed
- `fixed_function.py` (dead code)
- `backups/ais_live_tracker.py` (abandoned feature)
- `_calculate_and_apply_deviations` v1 (incorrect RRT-based algorithm)
```

## Tests — expansion

Expand pure-math tests with edge cases discovered during Phases 1-8:
- Dubins: zero-distance target, identical headings, degenerate cases
- RRT (if kept): obstacle touching start/goal, unreachable goal, single-obstacle funnel
- SPS parser: bad encoding with BOM, mixed line endings, very long files (regression test against detection performance)

Consider adding `test/test_import_linter.py` that invokes `lint-imports` as a subprocess — automated layering enforcement on every test run.

## Release preparation (optional, user decides)

- Bump version in `metadata.txt` from `1.0` to `2.0` (major version, justified by minimum QGIS change + feature additions).
- Fill in `metadata.txt` fields that are currently placeholders: `tracker=http://bugs`, `repository=http://repo`, `homepage=http://homepage`. Set to real URLs or remove the fields per `plugin.xml` spec.
- `make zip` or `make package VERSION=v2.0` to produce a distributable.

## Verify

1. `grep -rn "print(" --include='*.py' . | grep -v test/` → 0 matches.
2. `lint-imports` → 0 violations.
3. `ruff check .` → no new errors introduced by Phase 9 (pre-existing low-priority lint may remain).
4. `pytest test/` all green.
5. Load plugin in QGIS 3.40, run full smoke test; every workflow works.
6. `docs/refactor/README.md` updated to mark all phases complete.
7. `CLAUDE.md` reflects new architecture.

## Rollback

Trivial per-file revert. The risk here is minimal — mostly text edits and test expansion.

## Risks and unknowns

- **Log verbosity impact** — converting `print()` in tight RRT loops to `log.debug()` may slow things down when the file handler is at DEBUG level (`obn_planner_dockwidget.py:47`). If Phase 9 profiling shows >5% simulation slowdown, change to `log.info()` for loop iteration messages or suppress with `log.isEnabledFor(logging.DEBUG)` guards.
- **Log rotation** — file handler uses `mode='w'` (overwrite each session). Unchanged by Phase 9. Future maintenance: consider `logging.handlers.RotatingFileHandler` if users hit diagnostic-size issues. Not this phase.
- **`rrt_planner.py` deletion decision** — ultimately a judgment call. Recommendation: delete in Phase 9 since the user's chosen v2 Peak/Tangent is the canonical deviation algorithm. If any downstream user (e.g., a custom script) imports `rrt_planner`, that's external code, not the plugin's concern.
- **import-linter as a gate** — if the executor skips running it, layering can drift immediately. Consider a pre-commit hook (optional).

## End-of-revamp checklist

After Phase 9 ships, tick every box:

- [ ] `obn_planner_dockwidget.py` under 2000 lines
- [ ] `fixed_function.py` deleted
- [ ] Exactly one deviation algorithm (v2 Peak/Tangent, renamed to canonical name)
- [ ] Dubins module has no mutable globals
- [ ] Multi-format SPS parser handles Martin Linge, PXGEO, and at least one of TGS/SAE with auto-detection
- [ ] Direction-following feature works for both Racetrack and Teardrop
- [ ] Pure-math tests run without QGIS
- [ ] `grep print(` clean outside test/
- [ ] `import-linter` passes
- [ ] `docs/refactor/` has 10 phase docs (0-9) + README + SMOKE_TEST
- [ ] `CLAUDE.md` matches architecture
- [ ] `pb_tool deploy` and `make deploy` both work
- [ ] QGIS 3.40 minimum version in metadata.txt
- [ ] Final smoke test: full workflow baseline-equivalent output (or better) on real vendor files

## Hard Stop Gate

Phase 9 is complete when all checkboxes above are ticked. **This is the final phase. Claude reports completion and stops. User decides whether to tag `v2.0` and release.**

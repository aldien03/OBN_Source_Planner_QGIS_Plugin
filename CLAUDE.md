# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Operating Principles (Authoritative)

You are a cautious, systematic senior engineer. Measure twice, cut once.
Never guess. Never fabricate. Never improvise when uncertain.

**Tradeoff:** These rules bias toward caution over speed. For trivial one-liners, use judgment.

### WORKFLOW: READ → PLAN → CONFIRM → EXECUTE → VERIFY

Every non-trivial task MUST follow this sequence. Skipping steps is a violation.

1. **READ** — Read ALL relevant files before writing any code. Not just the target — read imports, types, adjacent modules, shared utilities. If unsure what's relevant, use `find`, `grep`, or `rg` to discover. Never assume file locations or names.
2. **PLAN** — Before writing ANY code, output a numbered plan:
   - Files to modify and what changes (one sentence each)
   - What could break
   - How to verify success
   - "I don't know" for anything uncertain — never fill gaps with guesses
3. **CONFIRM** — Do NOT execute until approved. Say "Ready to proceed. Approve?" and WAIT. Exception: user explicitly said "auto" or "just do it" for this task.
4. **EXECUTE** — Change ONLY what the plan says. Smallest diff that solves the problem. Nothing more.
5. **VERIFY** — Run type checks, linters, build, tests as appropriate. Report results. Never say "Done" unless verification passes.

### PRINCIPLE 1: THINK BEFORE CODING

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. If uncertain, ask — don't pick silently.
- If multiple interpretations exist, present them with tradeoffs.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, STOP. Name what's confusing. Ask.

### PRINCIPLE 2: SIMPLICITY FIRST

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

**Test:** Would a senior engineer say this is overcomplicated? If yes, simplify.

### PRINCIPLE 3: SURGICAL CHANGES

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Unrelated dead code: mention it — don't delete it.
- Remove only orphans YOUR changes created (unused imports, variables, functions).
- No package/dependency additions without explicit approval.
- No schema/database/migration changes without explicit approval.

**Test:** Every changed line must trace directly to the request.

### PRINCIPLE 4: GOAL-DRIVEN EXECUTION

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:
- "Add validation" → Write tests for invalid inputs, then make them pass
- "Fix the bug" → Write a test that reproduces it, then make it pass
- "Refactor X" → Ensure tests pass before and after

For multi-step tasks:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

### HARD RULES

**Honesty**
- Never fabricate data. No invented numbers, configs, API shapes, or package versions. If you don't know, say "I don't know — let me check" and actually check.
- Never claim a file exists without verifying. Use `ls`, `cat`, or `find`.
- Never claim code works without running verification. "This should work" is banned.
- Never claim credit for pre-existing work. If it worked before your change, don't list it as an achievement.

**Discipline**
- One task at a time. Don't bundle unrelated changes.
- **3-strike rule.** After 3 failed attempts on one problem, STOP. Report what you tried, what you learned, and recommend next steps. Do not enter correction loops.
- No retry without analysis. If an approach failed, explain WHY before trying a different one. Never repeat the same failed approach.

**Context Management**
- Don't re-read files already read in this session unless context was compacted.
- Be concise. No filler. No repeating the user's words back. Show diffs, not full files.
- Warn at ~40% context usage. Say: "Context getting heavy — recommend fresh session for next task." Don't wait until quality degrades.

### WORKING IF

- Fewer unnecessary changes in diffs — only requested changes appear
- Fewer rewrites due to overcomplication — simple the first time
- Clarifying questions come BEFORE implementation — not after mistakes
- Clean, minimal PRs — no drive-by refactoring
- Zero fabricated data — every claim is verified

---

## Project Overview

This is a QGIS plugin for Ocean Bottom Node (OBN) seismic survey source line planning and optimization. The plugin automates the planning process for marine seismic surveys by integrating path planning algorithms with QGIS spatial analysis capabilities.

## Development Commands

### Building and Deployment
- `make compile` - Compile resource files using pyrcc5
- `make deploy` - Deploy plugin to QGIS plugin directory
- `make zip` - Create deployable ZIP package
- `make package VERSION=<tag>` - Create versioned package from git tag
- `pb_tool deploy` - Deploy using pb_tool (recommended over make)

### Testing
- `make test` - Run test suite using nosetests with coverage
- `python -m unittest discover test/` - Run unit tests
- Individual test files are in the `test/` directory

### Code Quality
- `make pylint` - Run pylint code analysis
- `make pep8` - Run PEP8 style checking
- Note: Excludes pydev, resources.py, conf.py, third_party, ui from PEP8 checks

### Documentation
- `make doc` - Build Sphinx documentation in help/build/html
- Documentation source is in the `help/` directory

## Architecture

### Core Plugin Structure
- **Main Plugin (`obn_planner.py`)**: QGIS integration layer, handles plugin lifecycle and menu management
- **Dock Widget (`obn_planner_dockwidget.py`)**: Primary UI controller containing business logic and simulation control
- **Sequence Editor (`sequence_edit_dialog.py`)**: Specialized dialog for editing acquisition sequences with Excel export

### Algorithmic Components
- **RRT Planner (`rrt_planner.py`)**: Rapidly-exploring Random Tree algorithm for obstacle avoidance path planning
- **Dubins Path (`dubins_path.py`)**: Smooth curve generation for vessel maneuvering with turning radius constraints
- **Fixed Functions (`fixed_function.py`)**: Core simulation and processing functions

### Key Workflows
1. **SPS Data Import**: Load seismic point set files for survey planning
2. **Line Generation**: Create straight survey lines and run-ins from imported data
3. **Deviation Planning**: Use RRT + Dubins algorithms to plan paths around No-Go zones
4. **Sequence Simulation**: Simulate acquisition patterns (Racetrack, Teardrop) with vessel dynamics
5. **Export**: Generate lookahead plans and operational reports

## File Structure

### UI Components
- `obn_planner_dockwidget_base.ui` - Qt Designer UI definition
- `obn_planner_dockwidget_base_ui.py` - Compiled UI code (auto-generated)
- `resources.qrc` - Qt resource collection
- `resources.py` - Compiled resources (auto-generated)

### Configuration
- `metadata.txt` - Plugin metadata for QGIS
- `pb_tool.cfg` - Plugin Builder tool configuration
- `Makefile` - Build system configuration

### Development
- `test/` - Unit test suite
- `i18n/` - Internationalization files
- `help/` - Documentation source
- `backups/` - Backup versions of modified files

## Important Notes

### Code Conventions
- Follow existing patterns in the codebase for QGIS integration
- Use the plugin's logging system for debugging (check `obn_planner_debug.log`)
- Maintain compatibility with QGIS 3.40+ (Bratislava LTR) API

### Algorithm Integration
- RRT and Dubins algorithms are tightly coupled for optimal path planning
- Vessel dynamics (turning radius, speed) are critical parameters for path feasibility
- No-Go zones are handled as spatial constraints in the RRT algorithm

### UI Development
- Qt Designer files (.ui) should be modified through Qt Designer, not directly
- Compiled UI files are auto-generated - do not edit manually
- Resource files follow Qt's resource system conventions

### Testing Environment
- Tests require QGIS environment setup
- Use `QGIS_DEBUG=0` and `QGIS_LOG_FILE=/dev/null` for clean test runs
- Mock QGIS components may be needed for unit testing algorithmic functions

## Plugin Specifics

This plugin addresses the specialized domain of marine seismic surveys, specifically:
- Ocean Bottom Node (OBN) survey planning
- Vessel path optimization with maritime constraints
- Integration with industry-standard SPS file formats
- Real-time simulation of acquisition sequences
- Export formats suitable for offshore survey operations

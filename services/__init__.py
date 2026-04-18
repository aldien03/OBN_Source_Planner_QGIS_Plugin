"""
obn_planner.services — orchestration and domain-logic services.

Services may use qgis.core (for QgsGeometry, QgsPointXY, layer APIs) but
must NOT import from qgis.PyQt.QtWidgets. UI concerns live in ui/ (to be
created in Phase 8). This boundary is enforced by review today; Phase 9
adds an import-linter contract.

Modules (as of Phase 5):
- sequence_service: pure-Python racetrack + teardrop sequence generation
                     and helpers (no QGIS dependency at all)
- turn_cache:       TurnCache class — memoization wrapper for Dubins turn
                     computations. Pure Python; the actual Dubins call is
                     supplied as a callable by the caller.
"""

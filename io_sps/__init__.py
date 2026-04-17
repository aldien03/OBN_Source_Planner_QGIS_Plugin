"""
obn_planner.io_sps — SPS file parsing and GeoPackage I/O helpers.

Named `io_sps` rather than `io` to avoid shadowing Python's stdlib `io` module
when the plugin is imported.

Modules:
- sps_spec:   SpsColumnSpec dataclass + registry of known formats
- sps_parser: parse_sps() + detect_spec() — pure Python, no QGIS dependency
"""

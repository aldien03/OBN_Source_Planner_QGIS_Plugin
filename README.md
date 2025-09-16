# OBN Source Line Planner & Optimisation

A QGIS plugin that automates, streamlines, and optimizes the planning process for Ocean Bottom Node (OBN) seismic survey source lines. Integrates advanced path planning algorithms (RRT, Dubins paths) with QGIS spatial operations for marine seismic operations.

[![Version](https://img.shields.io/badge/version-1.0-blue.svg)](metadata.txt)
[![QGIS](https://img.shields.io/badge/QGIS-%3E%3D3.0-green.svg)](https://qgis.org)
[![License](https://img.shields.io/badge/license-GPL%202.0-orange.svg)](LICENSE)

## Architecture

### Core Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   obn_planner   │───▶│ OBNPlannerDock   │───▶│  Algorithm      │
│   (Plugin)      │    │ Widget (UI/Logic)│    │  Modules        │
│                 │    │  (10.4k lines)   │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   QGIS Core      │    │  rrt_planner    │
                       │   Integration    │    │  dubins_path    │
                       │                  │    │  sequence_edit  │
                       └──────────────────┘    └─────────────────┘
```

### Dependencies

- **Core**: QGIS 3.0+, PyQt5, Python 3.6+
- **Algorithms**: Custom RRT implementation, Dubins path calculations
- **Optional**: xlsxwriter (Excel export), openpyxl (spreadsheet operations)
- **Development**: pb_tool, pylint, nosetests

### Data Flow

1. **Input**: SPS files (seismic point survey data)
2. **Processing**: Survey line generation → Obstacle detection → Path planning
3. **Algorithms**: RRT for complex obstacle avoidance, Dubins for smooth turns
4. **Output**: Survey sequences, deviation paths, timing reports, exports

## Algorithms

### RRT (Rapidly-Exploring Random Tree)
- **Purpose**: Obstacle avoidance when survey lines intersect No-Go zones
- **Complexity**: O(n log n) average case, where n = number of iterations
- **Parameters**: 20,000 max iterations, 50m step size, 0.2 goal bias
- **Edge Cases**: Completely enclosed areas (graceful fallback), tight spaces

### Dubins Path Planning
- **Purpose**: Generate smooth vessel turns with minimum radius constraints
- **Complexity**: O(1) for single curve calculations
- **Applications**: Turn geometry between line segments, RRT path smoothing
- **Constraints**: Vessel turn radius, rate of turn limits, clearance requirements

### Survey Line Generation
- **Purpose**: Create straight-line paths connecting seismic survey points
- **Complexity**: O(n) where n = number of survey points
- **Features**: Run-in calculations, sequence optimization (racetrack/teardrop)

## Getting Started

### Prerequisites

- QGIS 3.0 or later
- Python environment with PyQt5
- Windows/Linux/macOS with QGIS installation

### Installation

```bash
# Method 1: QGIS Plugin Manager
# Search for "OBN Source Line Planner" in QGIS Plugins → Manage and Install Plugins

# Method 2: Manual Installation
git clone <repository-url>
cd obn_planner_v2
make deploy
# or
pb_tool deploy
```

### Setup

```bash
# Compile UI and resources (required after UI changes)
python compile_resources.py
# or
make compile
pb_tool compile
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QGIS_DEBUG` | Debug level for QGIS operations | `0` |
| `QGIS_LOG_FILE` | QGIS log file location | `/dev/null` |

## Usage

### Quickstart

1. Load SPS file with seismic survey points
2. Set vessel parameters (turn radius, speed)
3. Define No-Go zones (optional)
4. Generate survey lines and sequences
5. Export plans and reports

### Basic Workflow

```python
# Load plugin in QGIS
# Plugins → OBN Source Line Planner & Optimisation

# Import SPS data
click "Load SPS File" → select .sps file

# Configure parameters
Set turn radius: 500m
Set vessel speed: 5 knots
Define acquisition pattern: Racetrack

# Generate survey lines
click "Generate Lines" → creates line geometry

# Calculate deviations (if obstacles present)
click "Calculate Deviations" → applies RRT/Dubins algorithms

# Simulate acquisition sequence
click "Simulate Sequence" → generates timing and path data

# Export results
click "Export" → CSV, Excel, or shapefile formats
```

### Advanced Usage

```bash
# Custom algorithm parameters
RRT_STEP_SIZE=75.0 RRT_MAX_ITER=30000 qgis

# Batch processing mode
python batch_process.py --input-dir ./surveys --output-dir ./results

# Development with custom vessel parameters
python test_scenarios.py --vessel-config custom_vessel.json
```

## API/CLI Reference

### Core Functions

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `handle_calculate_deviations()` | lines, obstacles | deviation_paths | Calculate obstacle avoidance paths |
| `simulate_sequence()` | lines, pattern, start_pos | sequence_data | Generate acquisition sequence |
| `export_to_csv()` | data, filepath | success_bool | Export survey data to CSV |

### RRT Algorithm

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `step_size` | float | 50.0 | Tree extension distance (meters) |
| `max_iterations` | int | 20000 | Maximum planning iterations |
| `goal_bias` | float | 0.2 | Probability of sampling goal |
| `goal_distance_tolerance` | float | 25.0 | Goal proximity threshold |

### Dubins Path

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `get_curve()` | start, end, radius | geometry | Generate turn curve |
| `dubins_path()` | config | path, length | Calculate optimal path |

### Development Commands

| Command | Purpose |
|---------|---------|
| `make test` | Run test suite with coverage |
| `make pylint` | Code quality analysis |
| `make deploy` | Install to QGIS plugins directory |
| `pb_tool zip` | Create distribution package |

## Testing & QA

### Running Tests

```bash
# Prerequisites: Source QGIS environment
source scripts/run-env-linux.sh /path/to/qgis

# Full test suite with coverage
make test

# Code quality checks
make pylint
make pep8

# Algorithm-specific tests
python test_rrt.py
python test_dubins.py
```

### Test Coverage

- Unit tests: Algorithm functions, geometry calculations
- Integration tests: QGIS plugin workflow, UI interactions
- Performance tests: Large datasets, complex obstacle scenarios
- Edge case tests: Impossible paths, extreme parameters

## Troubleshooting

### Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `ImportError: No module named qgis.core` | QGIS environment not sourced | Run `source scripts/run-env-linux.sh <qgis-path>` |
| `RRT path generation failed` | Complex obstacles, insufficient iterations | Increase `max_iterations` or simplify No-Go zones |
| `UI compilation failed` | Missing PyQt5 uic/pyrcc5 | Install `pyqt5-dev-tools` package |
| `Plugin not loading` | Missing compiled resources | Run `python compile_resources.py` |
| `Dubins path calculation error` | Invalid turn radius/geometry | Check vessel parameters and line geometry |

### Debug Logging

```python
# Enable debug logging
import logging
logging.getLogger("obn_planner").setLevel(logging.DEBUG)

# Check log file
tail -f obn_planner_debug.log
```

### Performance Issues

- Large datasets (>1000 lines): Enable spatial indexing
- Complex obstacles: Reduce RRT step size, increase iterations
- Memory usage: Clear intermediate geometries, restart QGIS

## Roadmap & Limitations

### Current Limitations

- **Algorithm Performance**: RRT can be slow for very complex obstacle fields (>50 No-Go zones)
- **Memory Usage**: Large survey datasets may consume significant memory (>1GB for 10k+ lines)
- **Platform Support**: Primary testing on Windows/Linux, limited macOS testing
- **Export Formats**: Limited to CSV, Excel, Shapefile (no industry-specific formats)

### Planned Features

- **Real-time AIS Integration**: Vessel position tracking via UDP feed (Port 6789, MMSI 236483000)
- **Enhanced Maneuvering**: Intelligent line-change paths using RRT+Dubins hybrid approach
- **Performance Optimization**: Spatial indexing, parallel processing for large datasets
- **Additional Exports**: KML, GeoJSON, industry-standard navigation formats
- **Batch Processing**: Command-line interface for automated survey planning

### Technical Debt

- **RRT Implementation**: Path smoothing needs improvement, goal convergence optimization
- **UI Responsiveness**: Long calculations block UI (needs background processing)
- **Code Organization**: Main dockwidget class is large (10k+ lines), needs refactoring
- **Test Coverage**: Algorithm edge cases need more comprehensive testing

## Contributing

### Development Setup

```bash
git clone <repository-url>
cd obn_planner_v2
pip install pb_tool pylint
source scripts/run-env-linux.sh /path/to/qgis
make test
```

### Code Style

- Follow existing naming conventions
- Add docstrings for new functions
- Include unit tests for algorithm changes
- Run `make pylint` before submitting

### Pull Request Process

1. Fork repository and create feature branch
2. Implement changes with tests
3. Ensure all tests pass: `make test`
4. Update documentation if needed
5. Submit pull request with detailed description

## License

Licensed under GNU General Public License v2.0 - see LICENSE file for details.

**Copyright (C) 2025 Muhammad Aldien Said**
**Email**: aldien03@gmail.com

---

**Plugin Builder**: Generated using QGIS Plugin Builder
**QGIS Compatibility**: 3.0+
**Last Updated**: 2025-04-01
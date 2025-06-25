# OBN Source Line Planner & Optimisation (QGIS Plugin)

## Overview
This QGIS plugin automates, streamlines, and optimizes the planning process for Ocean Bottom Node (OBN) seismic survey source lines. It is designed to support survey planners by integrating data import, spatial algorithms, and interactive simulation tools directly within the QGIS environment.

---

## Key Features
- **Import and manage SPS data:** Easily load standard seismic point sets (SPS files) for survey planning.
- **Define and generate survey lines:** Automatically generate straight survey lines and run-ins based on user parameters and imported data.
- **Handle No-Go zones and deviations:** Use advanced algorithms (RRT, Dubins) to plan deviations around restricted (No-Go) areas.
- **Simulate survey sequences:** Simulate acquisition sequences (e.g., Racetrack, Teardrop), visualize the results, and edit or finalize plans interactively.
- **Export and reporting:** Export lookahead plans and manage the status of survey lines for field use.

---

## Workflow Summary
1. **Data Import:**
   - Import SPS files containing survey point data.
   - Filter and select relevant lines for planning.

2. **Line Generation:**
   - Generate straight survey lines by connecting points of the same line number.
   - Create run-in segments at the start and end of each line based on heading and user-defined lengths.

3. **Deviation Calculation:**
   - Identify lines intersecting No-Go zones (areas to avoid, such as obstacles or restricted regions).
   - Use the RRT (Rapidly-exploring Random Tree) algorithm to compute alternative paths (deviations) around obstacles.
   - Apply Dubins path logic for smooth, vessel-feasible turns, respecting minimum turning radius constraints.

4. **Simulation:**
   - Simulate acquisition sequences using different patterns (Racetrack, Teardrop).
   - Calculate headings, manage line status, and visualize the full survey path.
   - Edit and finalize the sequence interactively, including direction and timing adjustments.

5. **Export:**
   - Export finalized plans and lookahead reports for operational use.

---

## Core Algorithms
### 1. RRT (Rapidly-exploring Random Tree)
- **Purpose:** Find a feasible path for the survey vessel around No-Go zones, considering spatial constraints.
- **How it works:**
  - The algorithm grows a tree from the start point, randomly exploring the space while avoiding obstacles.
  - Each node represents a possible vessel state (position, heading).
  - The tree expands until a path to the goal (end of the survey line) is found, or a maximum number of iterations is reached.
- **Integration:** Used when a straight line would intersect a No-Go zone; the RRT computes a deviation path.

### 2. Dubins Path
- **Purpose:** Compute the shortest possible path between two points for a vehicle with a constrained turning radius (like a survey vessel).
- **How it works:**
  - Given start/end positions and headings, the algorithm computes a sequence of straight and turning segments (left/right/straight) that connect them.
  - Ensures that all turns respect the vessel's minimum turning radius.
- **Integration:** Used for generating smooth connectors and turns, both within RRT deviations and between survey lines.

---

## Main Components
- **`obn_planner.py`**: Main plugin logic, QGIS integration, and event handling.
- **`obn_planner_dockwidget.py`**: Implements the dockable UI for user interaction, data import, line generation, simulation, and visualization.
- **`rrt_planner.py`**: Contains the RRT algorithm for deviation path planning.
- **`dubins_path.py`**: Implements Dubins path logic for smooth, vessel-feasible turns.
- **`sequence_edit_dialog.py`**: Dialog for editing and finalizing survey sequences.
- **UI Files**: `.ui` and generated `_ui.py` files define the graphical interface.

---

## User Interface
- **Dock Widget:** Main control panel in QGIS for all plugin operations.
- **Buttons/Inputs:**
  - Import SPS, Generate Lines, Calculate Deviations, Run Simulation, Edit/Finalize Plan
  - Set parameters: turn radius, clearance, speeds, start time, etc.
- **Visualization:**
  - Survey lines, deviations, and simulation results are shown directly on the QGIS map canvas.

---

## Extending & Upgrading
This plugin is modular, with core algorithms separated into dedicated files. To upgrade or extend features:
- Review the main workflow in `obn_planner.py` and `obn_planner_dockwidget.py`.
- Algorithmic changes (e.g., new deviation logic) can be made in `rrt_planner.py` or `dubins_path.py`.
- UI changes can be made via Qt Designer (`.ui` files) and reflected in the corresponding Python UI files.

---

## References
- [PyQGIS Developer Cookbook](http://www.qgis.org/pyqgis-cookbook/index.html)
- [RRT Algorithm](https://en.wikipedia.org/wiki/Rapidly-exploring_random_tree)
- [Dubins Path](https://en.wikipedia.org/wiki/Dubins_path)

---

**Author:** Muhammad Aldien Said  
**Contact:** aldien03@gmail.com

For bug reports, please see the tracker URL in the plugin metadata.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a QGIS plugin called "OBN Source Line Planner & Optimisation" that automates seismic survey planning for Ocean Bottom Node (OBN) surveys. The plugin integrates with QGIS to provide spatial planning tools for marine seismic operations.

## Development Commands

### Building/Compiling Resources
- **Compile UI and resources**: `python compile_resources.py`
  - Compiles .ui files to Python using PyQt5's uic
  - Compiles .qrc resource files to Python using pyrcc5
- **Alternative compilation**: `make compile` or `pb_tool compile`

### Testing
- **Run tests**: `make test`
  - Uses nosetests with coverage reporting
  - Requires QGIS environment to be sourced first
  - Run `source scripts/run-env-linux.sh <path-to-qgis>` before testing

### Code Quality
- **Linting**: `make pylint` - Uses pylintrc configuration
- **PEP8 checking**: `make pep8` - Style checking with specific ignores

### Plugin Deployment
- **Deploy to QGIS**: `make deploy` - Copies plugin to QGIS plugin directory
- **Create plugin package**: `make package VERSION=<version>` - Creates distributable zip
- **Upload to plugin repo**: `make upload` - Uploads to QGIS plugin repository

### Using pb_tool (Recommended)
The project uses pb_tool for plugin management:
- `pb_tool deploy` - Deploy plugin to QGIS
- `pb_tool zip` - Create plugin zip package
- `pb_tool compile` - Compile resources

## Core Architecture

### Main Plugin Structure
- **obn_planner.py**: Main plugin class, handles QGIS integration and plugin lifecycle (233 lines)
- **obn_planner_dockwidget.py**: Core business logic and UI implementation (10,448 lines - complexity hotspot)
- **obn_planner_dockwidget_base.ui**: UI definition file (compiled to _ui.py)
- **sequence_edit_dialog.py**: Sequence editing dialog with Excel export capabilities

### Algorithmic Components
- **rrt_planner.py**: RRT (Rapidly-exploring Random Tree) algorithm for path planning around obstacles
- **dubins_path.py**: Dubins path calculations for smooth vessel turns with minimum radius constraints
- **sequence_edit_dialog.py**: Dialog for editing survey sequences

### Key Algorithms
1. **RRT Path Planning**: Used for obstacle avoidance - finds feasible paths around No-Go zones when survey lines intersect obstacles (obn_planner_dockwidget.py:2822)
2. **Dubins Path Calculations**: 
   - Primary use: Generate smooth turn geometries between survey line segments (obn_planner_dockwidget.py:8121)
   - Secondary use: Path planning within RRT algorithm for kinematically feasible vessel paths
3. **Survey Line Generation**: Creates straight lines and run-ins based on SPS data
4. **Sequence Simulation**: Supports Racetrack and Teardrop acquisition patterns

### Data Flow
1. Import SPS files (seismic point data)
2. Generate survey lines connecting points
3. Calculate smooth turns between line segments using Dubins geometry
4. Identify intersections with No-Go zones (if any)
5. Calculate deviations using RRT + Dubins algorithms (only when obstacles detected)
6. Simulate acquisition sequences
7. Export plans and reports

### Algorithm Usage Patterns
- **Dubins calculations**: Used in two contexts:
  - Direct geometry generation for turns via `dubins_calc.get_curve()` 
  - Internal to RRT planner for feasible path generation
- **RRT planning**: Only activated when survey lines intersect No-Go zones
- **Error handling**: Graceful fallback with dummy functions if algorithm modules fail to import

### QGIS Integration
- Uses PyQGIS API for spatial operations
- Renders results on map canvas
- Integrates with QGIS layer system
- Supports CRS transformations

## Development Notes

### Testing Environment
- Tests require QGIS environment to be properly configured
- Use test data in test/ directory for development
- Mock QGIS interface available in test/qgis_interface.py

### File Structure
- UI files (.ui) must be compiled to Python before deployment
- Resources (icons, etc.) are compiled from resources.qrc
- Plugin metadata in metadata.txt
- Help documentation in help/ directory (Sphinx-based)

### Debugging
- Logging configured to write to obn_planner_debug.log
- Both file and console logging available
- Debug information includes function names and line numbers

### Dependencies
- **Core**: PyQt5 for UI components, QGIS core libraries (qgis.core, qgis.gui)
- **Standard Libraries**: math, random, csv, datetime, logging, traceback, copy
- **Optional**: xlsxwriter (Excel export), openpyxl (spreadsheet operations)
- **Development**: pb_tool, pylint, nosetests, pep8
- **Testing**: Mock QGIS interface in test/qgis_interface.py

### Performance Characteristics
- **Main complexity hotspot**: obn_planner_dockwidget.py (10,448 lines)
- **RRT Algorithm**: O(n log n) average case, 20,000 max iterations
- **Dubins Calculations**: O(1) for single curves
- **Memory usage**: Can exceed 1GB for large datasets (10k+ survey lines)
- **Spatial operations**: Uses PyQGIS geometry functions with potential for spatial indexing

## Plugin Upgrade Methodology

### Pre-Upgrade Analysis
1. **Backup Current State**: Create git branch or backup before changes
2. **Understand Current Functionality**: Review existing features and their usage patterns
3. **Identify Integration Points**: Locate where new features will connect to existing code
4. **Check Algorithm Dependencies**: Determine if new features require RRT/Dubins or are independent

### UI Modification Workflow

#### For New UI Elements:
1. **Edit UI File**: Modify `obn_planner_dockwidget_base.ui` using Qt Designer
   - Add new buttons, inputs, or layout sections
   - Set appropriate object names and properties
2. **Compile UI**: Run `python compile_resources.py` to generate `_ui.py` files
3. **Connect UI to Logic**: In `obn_planner_dockwidget.py`, add:
   - Signal connections in `__init__()` method
   - Handler methods for new UI elements
   - UI state management (enable/disable logic)

#### UI Modification Steps:
```bash
# 1. Edit UI file (use Qt Designer or text editor)
# 2. Compile resources
python compile_resources.py
# 3. Check generated files
git diff obn_planner_dockwidget_base_ui.py obn_planner_dockwidget_ui.py
```

### Adding New Features

#### 1. Feature Planning
- **Define scope**: What specific functionality will be added?
- **Identify data flow**: How does it integrate with existing SPS/line generation pipeline?
- **UI requirements**: New buttons, dialogs, or parameter inputs needed?
- **Algorithm needs**: Will it use existing RRT/Dubins or require new algorithms?

#### 2. Implementation Approach
- **Modular addition**: Add new methods to `OBNPlannerDockWidget` class
- **Follow existing patterns**: Use similar structure to existing features
- **Error handling**: Include try/catch blocks and logging like existing code
- **UI feedback**: Provide progress indicators for long-running operations

#### 3. Code Organization
- **Main logic**: Add to `obn_planner_dockwidget.py` 
- **Algorithm modules**: Create separate `.py` files for complex algorithms (like `rrt_planner.py`)
- **Helper functions**: Add utility functions at class level or create separate module
- **UI handlers**: Follow naming pattern: `on_<buttonName>_clicked()`

### Testing Procedures

#### Development Testing
1. **Unit Testing**: Add tests to `test/` directory following existing patterns
2. **Manual Testing**: Test in QGIS environment with sample data
3. **Integration Testing**: Verify new features work with existing functionality
4. **Error Testing**: Test error conditions and edge cases

#### Testing Commands
```bash
# Source QGIS environment first
source scripts/run-env-linux.sh /path/to/qgis
# Run tests
make test
# Code quality checks
make pylint
make pep8
```

### Deployment Process

#### Version Management
1. **Update version**: Modify `metadata.txt` version field
2. **Document changes**: Update README.md or create changelog
3. **Git management**: Create meaningful commit messages
4. **Tag releases**: Use git tags for version tracking

#### Plugin Packaging
```bash
# Deploy to local QGIS for testing
make deploy
# or using pb_tool
pb_tool deploy

# Create distributable package
make package VERSION=1.1
# or create zip
make zip
```

#### Quality Assurance
1. **Pre-deployment checks**: 
   - All tests pass
   - No pylint critical issues
   - UI compiles without errors
   - Plugin loads in QGIS without errors
2. **Feature verification**: Test all new and existing functionality
3. **Documentation**: Update user-facing documentation

### Debugging Workflow

#### Log Analysis
- Check `obn_planner_debug.log` for detailed execution logs
- Use log levels: DEBUG for development, INFO for user feedback
- Add logging for new features: `log.info("Feature X executed successfully")`

#### Common Issues
- **UI not updating**: Check if resources compiled correctly (`python compile_resources.py`)
- **Import errors**: Verify module paths and dependencies - graceful fallback with dummy functions available
- **QGIS integration issues**: Check PyQGIS API compatibility, source QGIS environment first
- **Algorithm failures**: Verify RRT/Dubins modules load correctly, check obn_planner_debug.log
- **Performance degradation**: Monitor memory usage with large datasets, consider spatial indexing
- **RRT path violations**: Current known issue - paths may intersect No-Go zones despite obstacle avoidance intent

### Best Practices for Upgrades

#### Code Style
- Follow existing naming conventions and code structure
- Use comprehensive error handling with user-friendly messages
- Add docstrings for new functions
- Maintain logging consistency

#### Backward Compatibility
- Preserve existing UI element names and behaviors
- Maintain existing data file formats
- Keep existing function signatures when possible
- Add new parameters with default values

#### Performance Considerations
- Test with large datasets (1000+ survey lines can consume >1GB memory)
- Profile algorithm performance: RRT can be slow for complex obstacle fields (>50 No-Go zones)
- Consider progress indicators for long operations (RRT max 20,000 iterations)
- Optimize QGIS map rendering calls and use spatial indexing for large datasets
- Monitor background thread performance for real-time features (planned AIS integration)

## Current Known Issues

### Critical Algorithm Problems
1. **RRT Deviation Calculation Bug**: Current `handle_calculate_deviations` function has critical issues:
   - RRT paths may intersect No-Go zones despite obstacle avoidance intent
   - Generated paths create unnecessarily long deviation routes
   - Non-smooth paths with sharp angular changes unsuitable for vessel navigation
   - Poor convergence - algorithm fails to find efficient shortest paths

2. **Performance Bottlenecks**:
   - Main dockwidget class is oversized (10,448 lines) - needs refactoring
   - Memory usage can exceed 1GB for large datasets (10k+ survey lines)
   - UI blocks during long calculations - needs background processing

3. **Algorithm Parameter Issues**:
   - RRT step size not optimized for marine survey scenarios
   - Goal bias too low (0.2) causing inefficient exploration
   - Insufficient path smoothing after RRT generation

### Immediate Fixes Needed
- Enhance RRT obstacle handling and collision detection
- Implement hybrid RRT-Dubins approach for better path quality
- Add intelligent algorithm selection (geometric vs RRT based on complexity)
- Implement progress indicators for long-running operations

## Planned Feature Upgrades

### Feature 1: AIS Feed Integration

#### Overview
Integrate real-time AIS (Automatic Identification System) feed to estimate the closest first line for survey planning based on vessel position.

#### Technical Specifications
- **AIS Source**: UDP broadcast on Port 6789
- **Target Vessel**: MMSI 236483000 (Sanco Star)
- **Purpose**: Identify closest survey line to current vessel position for optimal survey sequence planning

#### Implementation Plan

##### 1. AIS Data Reception Module
- **New Module**: Create `ais_receiver.py` for UDP data handling
- **Dependencies**: Python `socket` library for UDP communication
- **Data Processing**: Parse AIS messages to extract position data (lat/lon)
- **Error Handling**: Handle network timeouts, malformed messages, connection failures

##### 2. AIS Message Parsing
- **Message Types**: Focus on Position Report messages (Types 1, 2, 3)
- **Data Extraction**: Extract latitude, longitude, course, speed from AIS payload
- **MMSI Filtering**: Filter messages specifically for MMSI 236483000
- **Coordinate System**: Convert AIS coordinates to match QGIS project CRS

##### 3. Line Proximity Calculation
- **Algorithm**: Calculate distance from vessel position to each survey line
- **Method**: Use PyQGIS geometry functions for point-to-line distance calculations
- **Optimization**: Consider using spatial indexing for large line datasets
- **Result**: Identify closest line and recommend as starting point

##### 4. UI Integration
- **New UI Elements**:
  - AIS connection status indicator
  - Current vessel position display
  - Closest line information panel
  - "Start from Vessel Position" button
- **Real-time Updates**: Update vessel position and closest line in real-time
- **Visual Feedback**: Show vessel position on map canvas with icon/marker

##### 5. Integration with Line Planning
- **Sequence Optimization**: Use closest line as starting point for survey sequence
- **Planning Logic**: Modify existing sequence simulation to begin from vessel-proximate line
- **Route Optimization**: Consider vessel heading and course for optimal sequence direction

#### Development Workflow

##### Phase 1: AIS Reception Infrastructure
1. Create `ais_receiver.py` module with UDP socket handling
2. Implement AIS message parsing and MMSI filtering
3. Add error handling and connection management
4. Create unit tests for AIS parsing functions

##### Phase 2: Proximity Calculation Engine
1. Implement distance calculation between vessel position and survey lines
2. Create line ranking algorithm based on proximity
3. Add coordinate system conversion utilities
4. Test with various vessel positions and line configurations

##### Phase 3: UI Development
1. Design AIS status panel in Qt Designer
2. Add vessel position display controls
3. Implement real-time update mechanisms
4. Create vessel position map visualization

##### Phase 4: Integration with Planning Logic
1. Modify sequence simulation to accept vessel-based starting point
2. Update line ordering algorithms to optimize from vessel position
3. Integrate AIS data into existing planning workflow
4. Add user controls for AIS-based planning mode

#### Technical Considerations

##### Threading and Real-time Updates
- **Background Processing**: Run AIS reception in separate thread to avoid UI blocking
- **Thread Safety**: Use Qt signals/slots for thread-safe UI updates
- **Update Frequency**: Balance between real-time updates and performance

##### Error Handling and Robustness
- **Network Failures**: Graceful handling of UDP connection issues
- **Data Validation**: Validate AIS position data before use in calculations
- **Fallback Mode**: Allow manual vessel position input if AIS unavailable

##### Performance Optimization
- **Efficient Distance Calculation**: Use appropriate spatial algorithms for line proximity
- **Data Caching**: Cache parsed AIS data to avoid repeated processing
- **Map Updates**: Optimize vessel position rendering on map canvas

#### Testing Strategy

##### Unit Testing
- Test AIS message parsing with sample UDP data
- Verify distance calculation accuracy
- Test coordinate system conversions

##### Integration Testing
- Test AIS data flow from UDP to UI display
- Verify line proximity calculations with real survey data
- Test sequence planning with vessel-based starting points

##### Field Testing
- Test with actual AIS feed from Port 6789
- Verify MMSI filtering for Sanco Star (236483000)
- Validate proximity calculations with known vessel positions

#### UI Mockup Requirements
- AIS connection status (Connected/Disconnected/Error)
- Current vessel position (Lat/Lon display)
- Closest line information (Line ID, Distance, Bearing)
- Vessel position marker on map canvas
- Toggle for AIS-based vs manual planning mode

### Feature 2: Safe Maneuvering During Line Changes

#### Overview
Implement intelligent maneuvering path generation for line changes that intersect with No-Go zones, using RRT and Dubins path algorithms to create safe, efficient transitions while respecting vessel maneuvering constraints.

#### Technical Specifications
- **Objective**: Generate safe maneuvering paths for line-to-line transitions that cross No-Go zones
- **Algorithms**: Utilize existing RRT and Dubins path modules for optimal path planning
- **Constraints**: Respect vessel turn radius, rate of turn, and minimum maneuvering distances
- **Optimization Goal**: Shortest possible safe path while maintaining vessel operational limits

#### Implementation Plan

##### 1. Line Change Detection and Analysis
- **Transition Identification**: Detect all line-to-line transitions in survey sequence
- **No-Go Zone Intersection**: Check if direct line-change path intersects No-Go zones
- **Transition Types**: Handle different transition scenarios:
  - End of line to start of next line
  - Line reversals (racetrack patterns)
  - Skip patterns (non-sequential line changes)
- **Geometry Analysis**: Calculate transition vectors and required maneuver distances

##### 2. Intersection Detection Engine
- **Spatial Analysis**: Use PyQGIS geometry intersection functions
- **Buffer Analysis**: Consider vessel dimensions and safety margins around No-Go zones
- **Path Validation**: Verify direct paths vs safe alternative requirements
- **Priority Scoring**: Rank intersections by severity and maneuvering complexity

##### 3. Safe Maneuvering Path Generation
- **Algorithm Selection Logic**:
  - **Simple Cases**: Use Dubins path for basic turn maneuvers without obstacles
  - **Complex Cases**: Deploy RRT algorithm when multiple obstacles or complex geometry
- **Path Optimization**: Generate multiple candidate paths and select optimal solution
- **Constraint Validation**: Ensure all generated paths respect vessel limitations

##### 4. RRT Integration for Complex Maneuvers
- **Enhanced RRT Parameters**: Optimize RRT settings for line-change scenarios
- **Goal-Oriented Planning**: Direct RRT growth toward next line start point
- **Obstacle-Aware Generation**: Configure RRT to avoid all No-Go zone geometries
- **Path Smoothing**: Apply Dubins path smoothing to RRT-generated waypoints

##### 5. Dubins Path Integration for Efficient Turns
- **Turn Radius Optimization**: Calculate minimum safe turn radius for vessel
- **Rate of Turn Compliance**: Ensure generated curves respect maximum ROT limits
- **Path Efficiency**: Prioritize shortest path solutions within safety constraints
- **Smooth Transitions**: Generate continuous, smooth curves for operational efficiency

#### Development Workflow

##### Phase 1: Intersection Detection Infrastructure
1. Implement line-change transition detection in sequence simulation
2. Create No-Go zone intersection analysis functions
3. Develop spatial buffer analysis for vessel safety margins
4. Add intersection severity classification system

##### Phase 2: Algorithm Integration and Coordination
1. Extend existing RRT module for line-change scenarios
2. Enhance Dubins path module for transition-specific calculations
3. Implement algorithm selection logic (Dubins vs RRT based on complexity)
4. Create path optimization and comparison functions

##### Phase 3: Maneuvering Path Generation
1. Develop path generation workflow for different transition types
2. Implement constraint validation for all generated paths
3. Create path smoothing and optimization routines
4. Add multiple candidate path generation and selection

##### Phase 4: Integration with Sequence Planning
1. Modify sequence simulation to include maneuvering paths
2. Update line-change visualization to show safe maneuvering routes
3. Integrate maneuvering time calculations into sequence timing
4. Add user controls for maneuvering parameter adjustment

#### Technical Considerations

##### Algorithm Selection Criteria
- **Use Dubins Path When**:
  - Simple line-to-line transitions without obstacle interference
  - Clear turning space available around No-Go zones
  - Standard vessel maneuvers (typical racetrack turns)
- **Use RRT Algorithm When**:
  - Multiple No-Go zones create complex obstacle fields
  - Tight maneuvering spaces require exploration-based planning  
  - Non-standard transitions with multiple constraint violations

##### Vessel Maneuvering Constraints
- **Turn Radius**: Minimum turning radius based on vessel specifications
- **Rate of Turn**: Maximum angular velocity limits for safe operations
- **Speed Considerations**: Adjust path planning based on operational speeds
- **Safety Margins**: Additional clearance distances from No-Go zones

##### Path Optimization Strategies
- **Distance Minimization**: Shortest path while respecting all constraints
- **Time Optimization**: Consider vessel speed profiles for time-efficient routes
- **Fuel Efficiency**: Factor in course changes and speed variations
- **Operational Practicality**: Ensure generated paths are operationally feasible

#### Enhanced Algorithm Functionality

##### RRT Enhancements for Line Changes
- **Biased Sampling**: Increase sampling probability toward target line start point
- **Obstacle Awareness**: Enhanced obstacle avoidance for No-Go zone clusters
- **Path Pruning**: Remove unnecessary waypoints for smoother final paths
- **Convergence Optimization**: Faster convergence for line-change scenarios

##### Dubins Path Optimization
- **Multi-Segment Paths**: Handle complex transitions with multiple curve segments
- **Clearance Optimization**: Maximize clearance from No-Go zones while minimizing path length
- **Heading Continuity**: Ensure smooth heading transitions between line segments
- **Reversibility**: Support for reverse maneuvers in racetrack patterns

#### Integration with Existing Systems

##### Sequence Simulation Enhancement
- **Maneuvering Time Calculation**: Add time estimates for generated maneuvering paths
- **Path Visualization**: Display safe maneuvering routes on map canvas
- **Sequence Optimization**: Consider maneuvering efficiency in line sequencing
- **Real-time Updates**: Update maneuvering paths when survey parameters change

##### UI Integration Requirements
- **Maneuvering Path Display**: Visual representation of generated safe paths
- **Algorithm Selection Controls**: User options for algorithm preference/forcing
- **Constraint Parameter Inputs**: Vessel-specific maneuvering parameter settings
- **Path Analysis Panel**: Display path statistics (length, time, clearances)

#### Testing Strategy

##### Algorithm Validation
- **Constraint Compliance**: Verify all paths respect turn radius and ROT limits
- **Obstacle Avoidance**: Confirm no generated paths intersect No-Go zones
- **Path Efficiency**: Compare path lengths against theoretical minimums
- **Convergence Testing**: Ensure algorithms reliably find solutions

##### Scenario Testing
- **Simple Transitions**: Test basic line-to-line changes without obstacles
- **Complex Obstacle Fields**: Validate performance with multiple No-Go zones
- **Edge Cases**: Test tight maneuvering spaces and extreme constraint scenarios
- **Performance Testing**: Measure algorithm execution times for real-time usage

##### Integration Testing
- **Sequence Integration**: Verify maneuvering paths integrate properly with line sequences
- **Visualization Testing**: Confirm proper display of generated paths on map
- **Parameter Sensitivity**: Test response to different vessel constraint parameters
- **Real-time Updates**: Validate path regeneration when parameters change

#### Performance Optimization

##### Computational Efficiency
- **Spatial Indexing**: Use spatial indexes for fast No-Go zone intersection queries
- **Caching Strategies**: Cache frequently used calculations and path segments
- **Parallel Processing**: Consider multi-threading for multiple path generation
- **Memory Management**: Efficient handling of complex geometry calculations

##### User Experience
- **Progress Indicators**: Show calculation progress for complex maneuvering problems
- **Interactive Adjustment**: Allow real-time parameter adjustment with path updates
- **Path Comparison**: Enable comparison of different maneuvering solutions
- **Export Functionality**: Export maneuvering paths for external navigation systems

### Bug Fix: handle_calculate_deviations Algorithm Issues

#### Problem Statement
The current `handle_calculate_deviations` function has critical issues with both QGIS-based and RRT-based deviation calculations:

##### Current QGIS-Based Issues:
- **Non-smooth deviation paths**: Generated paths lack smooth curves suitable for vessel navigation
- **Sharp angular changes**: Abrupt direction changes that violate vessel maneuvering constraints
- **No consideration of vessel dynamics**: Paths ignore turn radius and rate of turn limitations

##### Current RRT Implementation Issues:
- **No-Go zone constraint violation**: RRT paths intersect with No-Go zones despite obstacle avoidance intent
- **Excessive path length**: Generated paths overshoot and create unnecessarily long deviation routes
- **Poor convergence**: Algorithm fails to find efficient shortest paths to reconnect with original line
- **Inadequate smoothing**: RRT waypoints create jagged paths unsuitable for vessel navigation

#### Root Cause Analysis

##### RRT Algorithm Configuration Issues:
1. **Obstacle Representation**: No-Go zones may not be properly represented in RRT's collision detection
2. **Step Size Problems**: RRT step size not optimized for marine survey line deviations
3. **Goal Bias Issues**: Insufficient goal bias causing inefficient exploration away from target
4. **Smoothing Deficiency**: Lack of proper path smoothing after RRT path generation

##### Algorithm Selection Issues:
1. **Wrong Tool for Task**: RRT may be overkill for simple obstacle avoidance scenarios
2. **Missing Hybrid Approach**: No intelligent selection between simple geometric methods and complex RRT
3. **Constraint Integration**: Poor integration of vessel maneuvering constraints into path planning

#### Systematic Fix Implementation Plan

##### Phase 1: Problem Diagnosis and Algorithm Audit
1. **Current RRT Implementation Review**:
   - Analyze RRT parameter settings in `rrt_planner.py`
   - Review obstacle representation and collision detection logic
   - Examine goal bias and convergence criteria
   - Assess path smoothing implementation

2. **QGIS Method Analysis**:
   - Review current QGIS-based deviation calculation methods
   - Identify specific smoothness and constraint violation issues
   - Analyze geometric calculation approaches

3. **Test Case Development**:
   - Create standardized test scenarios with known optimal solutions
   - Design test cases with varying No-Go zone complexity
   - Establish performance benchmarks for path quality metrics

##### Phase 2: Enhanced RRT Algorithm Implementation

###### 1. Improved Obstacle Handling
- **Enhanced Collision Detection**:
  - Implement proper No-Go zone buffer handling with safety margins
  - Add multi-geometry obstacle support for complex No-Go zone clusters
  - Ensure collision detection accounts for vessel beam width and safety clearances

- **Obstacle Representation Optimization**:
  - Convert No-Go zones to appropriate data structures for fast collision queries
  - Implement spatial indexing for efficient obstacle intersection testing
  - Add obstacle boundary smoothing to prevent path oscillation near edges

###### 2. RRT Parameter Optimization
- **Step Size Tuning**:
  - Implement adaptive step size based on obstacle density and line geometry
  - Use smaller steps near obstacles, larger steps in open water
  - Configure step size relative to vessel turn radius for realistic maneuvers

- **Goal Bias Enhancement**:
  - Increase goal bias for deviation scenarios (target: 0.3-0.5 vs current 0.2)
  - Implement distance-based goal bias (higher bias when closer to reconnection point)
  - Add informed sampling toward optimal reconnection zones

- **Convergence Criteria Improvement**:
  - Reduce goal distance tolerance for more precise path termination
  - Add heading angle consideration in goal reaching criteria
  - Implement early termination when acceptable solution found

###### 3. Path Quality Optimization
- **Path Smoothing Enhancement**:
  - Implement comprehensive Dubins path smoothing on RRT waypoints
  - Add path simplification to remove unnecessary intermediate points
  - Ensure smooth heading transitions throughout deviation path

- **Length Minimization**:
  - Implement path pruning algorithms to remove redundant segments
  - Add post-processing optimization to minimize total deviation distance
  - Consider multiple RRT runs and select shortest valid path

##### Phase 3: Hybrid Algorithm Approach

###### 1. Intelligent Algorithm Selection
- **Complexity Assessment**:
  - Simple cases: Single convex No-Go zone → Use enhanced geometric methods
  - Complex cases: Multiple/concave obstacles → Use improved RRT
  - Medium cases: Limited obstacles → Use constrained Dubins path planning

- **Geometric Method Enhancement**:
  - Implement tangent-based deviation around single obstacles
  - Add vessel constraint integration to geometric calculations
  - Create smooth arc-based paths for simple obstacle avoidance

###### 2. Constrained Dubins Path Planning
- **Obstacle-Aware Dubins Planning**:
  - Develop Dubins path variants that respect No-Go zone boundaries
  - Implement clearance-optimized curve generation
  - Add multi-segment Dubins paths for complex obstacles

- **Hybrid RRT-Dubins Approach**:
  - Use RRT for initial waypoint generation around complex obstacles
  - Apply Dubins path smoothing between all waypoint pairs
  - Validate final path against all constraints and obstacles

##### Phase 4: Advanced Path Optimization

###### 1. Multi-Objective Optimization
- **Path Quality Metrics**:
  - Minimize total deviation distance
  - Maximize clearance from No-Go zones
  - Minimize course changes and heading variations
  - Optimize for vessel operational efficiency

- **Genetic Algorithm Integration**:
  - Implement GA for path optimization when RRT provides multiple solutions
  - Use fitness function combining distance, smoothness, and clearance
  - Generate population of candidate paths and evolve optimal solution

###### 2. Constraint Integration Framework
- **Vessel Dynamics Integration**:
  - Embed turn radius constraints directly into path generation
  - Add rate of turn limitations to curve generation
  - Include speed profile considerations for realistic maneuvering

- **Safety Margin Management**:
  - Implement configurable safety buffers around No-Go zones
  - Add dynamic safety margins based on environmental conditions
  - Ensure minimum clearance requirements throughout deviation path

#### Implementation Workflow

##### Step 1: Enhanced RRT Implementation (2-3 weeks)
1. **Week 1**: Fix obstacle handling and collision detection
   - Review and fix No-Go zone representation in RRT
   - Implement proper buffer handling and collision testing
   - Add comprehensive debugging and logging for RRT path generation

2. **Week 2**: Optimize RRT parameters and convergence
   - Tune step size, goal bias, and iteration limits
   - Implement adaptive parameters based on scenario complexity
   - Add multiple solution generation and selection logic

3. **Week 3**: Implement path smoothing and optimization
   - Integrate Dubins path smoothing into RRT output
   - Add path simplification and redundancy removal
   - Implement path quality metrics and validation

##### Step 2: Hybrid Algorithm Development (2-3 weeks)
1. **Week 1**: Develop algorithm selection logic
   - Implement complexity assessment for deviation scenarios
   - Create decision tree for algorithm selection
   - Develop enhanced geometric methods for simple cases

2. **Week 2**: Implement constrained Dubins planning
   - Create obstacle-aware Dubins path variants
   - Implement multi-segment path generation
   - Add clearance optimization to curve generation

3. **Week 3**: Integration and testing
   - Integrate hybrid approach into existing deviation calculation
   - Comprehensive testing with various obstacle configurations
   - Performance optimization and parameter tuning

#### Testing and Validation Strategy

##### Algorithm Performance Testing
1. **Benchmark Scenarios**:
   - Simple single obstacle avoidance
   - Complex multi-obstacle navigation
   - Tight maneuvering space scenarios
   - Large-scale survey line deviations

2. **Quality Metrics Validation**:
   - Path length efficiency comparison
   - Smoothness analysis (heading change rates)
   - Clearance verification (minimum distances to No-Go zones)
   - Constraint compliance verification (turn radius, ROT)

3. **Comparative Analysis**:
   - Current QGIS method vs enhanced RRT
   - Enhanced RRT vs hybrid approach
   - Performance metrics: execution time, path quality, success rate

##### Integration Testing
1. **End-to-End Workflow Testing**:
   - Test deviation calculation within complete survey planning workflow
   - Verify integration with existing sequence simulation
   - Validate visualization and user interaction

2. **Edge Case Testing**:
   - Impossible deviation scenarios (completely enclosed lines)
   - Minimal clearance situations
   - Performance with large numbers of No-Go zones

#### Expected Outcomes

##### Immediate Improvements
- **Smooth deviation paths**: All generated paths will respect vessel maneuvering constraints
- **No constraint violations**: Guaranteed clearance from all No-Go zones
- **Optimal path length**: Significantly shorter deviation paths compared to current RRT

##### Long-term Benefits
- **Reliable algorithm performance**: Consistent successful path generation across scenarios
- **Operational efficiency**: Deviation paths suitable for real vessel navigation
- **Scalable solution**: Algorithm performance maintained with complex obstacle configurations

## Development Priorities

### Immediate (Week 1-2)
1. **Fix RRT deviation calculation bugs** - Critical for operational use
2. **Add comprehensive logging** to RRT path generation for debugging
3. **Implement progress indicators** for long-running operations

### Short-term (Month 1-2)
1. **Implement hybrid RRT-Dubins approach** for better path quality
2. **Add spatial indexing** for performance with large datasets
3. **Refactor main dockwidget class** - break into smaller modules

### Medium-term (Month 3-6)
1. **AIS feed integration** for real-time vessel position tracking
2. **Enhanced maneuvering paths** for line-change scenarios
3. **Background processing** to prevent UI blocking

### Long-term (6+ months)
1. **Command-line interface** for batch processing
2. **Advanced export formats** (KML, GeoJSON, navigation-specific)
3. **Performance optimization** with parallel processing

## Code Quality Metrics

### Current State
- **Main file**: 10,448 lines (excessive - target: <3,000 per module)
- **Test coverage**: Basic unit tests exist, need algorithm-specific coverage
- **Algorithm complexity**: RRT O(n log n), Dubins O(1)
- **Memory usage**: 1GB+ for large datasets (needs optimization)

### Target Improvements
- **Modularization**: Break dockwidget into 3-4 focused modules
- **Test coverage**: 80%+ for algorithm functions
- **Performance**: <500MB for 10k survey lines
- **Documentation**: API docs for all public functions
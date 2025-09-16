import os
import sys
import importlib
from qgis.core import (
    QgsPointXY, QgsGeometry, QgsVectorLayer, QgsFeature, QgsProject,
    QgsFields, QgsField, QgsLineString, QgsWkbTypes # Add others as needed
)
from qgis.PyQt.QtCore import QVariant
import math
from qgis.PyQt.QtGui import QColor

# --- IMPORTANT: Make rrt_planner.py accessible ---
# Ensure the plugin directory is in the Python path
plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.append(plugin_dir)

# Import required modules with proper error handling
try:
    import rrt_planner
    print("Imported rrt_planner successfully.")
    
    # Reload the module if you make changes to rrt_planner.py without restarting QGIS
    try:
        importlib.reload(rrt_planner)
        print("Reloaded rrt_planner.")
    except NameError:
        # This happens when rrt_planner was just imported for the first time
        print("First import of rrt_planner, no reload needed.")
    except Exception as e:
        print(f"Warning: Could not reload rrt_planner: {str(e)}")
        
except ImportError as e:
    print(f"ERROR: Failed to import rrt_planner: {str(e)}")
    print("RRT functionality will not work!")

# ----- Test Configuration -----

class RRTTestConfig:
    """Configuration class for RRT tests"""
    def __init__(self):
        # Default start and end poses
        self.start_x, self.start_y, self.start_h_deg = 10, 10, 0   # Start at (10, 10) heading East (0 deg)
        self.end_x, self.end_y, self.end_h_deg = 190, 10, 0      # End at (190, 10) heading East
        self.turn_radius = 20.0
        
        # RRT parameters
        self.step_size = 15.0
        self.max_iter = 3000
        self.goal_bias = 0.15
        self.bounds = None  # Optional (min_x, max_x, min_y, max_y)
        
        # Coordinate Reference System - Use EPSG:31984 for better distance calculations
        self.crs = "EPSG:31984"
        
        # Obstacle list - initialized empty
        self.obstacles_list = []
        
    def get_start_pose(self):
        """Returns the start pose as a tuple (x, y, heading_radians)"""
        return (self.start_x, self.start_y, math.radians(self.start_h_deg))
    
    def get_end_pose(self):
        """Returns the end pose as a tuple (x, y, heading_radians)"""
        return (self.end_x, self.end_y, math.radians(self.end_h_deg))
    
    def add_obstacle_from_wkt(self, wkt):
        """Add an obstacle from a WKT string"""
        if not wkt or not isinstance(wkt, str):
            print("ERROR: Invalid WKT string provided")
            return False
            
        try:
            obstacle_geom = QgsGeometry.fromWkt(wkt)
            if obstacle_geom is None or obstacle_geom.isEmpty():
                print(f"ERROR: Could not create geometry from WKT: {wkt}")
                return False
                
            # Check if geometry is valid - different QGIS versions have different methods
            is_valid = True  # Assume valid initially
            if hasattr(obstacle_geom, 'isValid'):
                is_valid = obstacle_geom.isValid()
            elif hasattr(obstacle_geom, 'isGeosValid'):
                is_valid = obstacle_geom.isGeosValid()
                
            if not is_valid:
                print(f"WARNING: Invalid obstacle geometry from WKT: {wkt}")
                return False
                
            self.obstacles_list.append(obstacle_geom)
            return True
            
        except Exception as e:
            print(f"ERROR in add_obstacle_from_wkt: {str(e)}")
            return False
    
    def clear_obstacles(self):
        """Clear all obstacles"""
        self.obstacles_list = []
        
    def print_config(self):
        """Print the current test configuration"""
        print("\n----- RRT Test Configuration -----")
        print(f"Start: ({self.start_x}, {self.start_y}, {self.start_h_deg}°)")
        print(f"End: ({self.end_x}, {self.end_y}, {self.end_h_deg}°)")
        print(f"Turn Radius: {self.turn_radius}")
        print(f"Step Size: {self.step_size}")
        print(f"Max Iterations: {self.max_iter}")
        print(f"Goal Bias: {self.goal_bias}")
        print(f"Bounds: {self.bounds}")
        print(f"Obstacles: {len(self.obstacles_list)}")
        print("----------------------------------\n")

# ----- RRT Test Execution & Visualization -----
        
class RRTTestRunner:
    """Class for running and visualizing RRT tests"""
    def __init__(self, config=None):
        self.config = config if config else RRTTestConfig()
        self.path_geom = None  # Stores the result path geometry
        self.layers = {}  # Dictionary to keep track of visualization layers
        
    def run_test(self):
        """Run the RRT path finding algorithm with the current configuration"""
        self.config.print_config()
        
        # Get parameters from config
        start_pose = self.config.get_start_pose()
        end_pose = self.config.get_end_pose()
        obstacles = self.config.obstacles_list
        
        # Validate geometries
        if not all(g.isValid() for g in obstacles if g):
            print("WARNING: One or more obstacle geometries are invalid!")
        
        # Execute the find_rrt_path function
        print(f"Running RRT with step={self.config.step_size}, iter={self.config.max_iter}, bias={self.config.goal_bias}...")
        self.path_geom = rrt_planner.find_rrt_path(
            start_pose=start_pose,
            end_pose=end_pose,
            obstacles=obstacles,
            turn_radius=self.config.turn_radius,
            step_size=self.config.step_size,
            max_iterations=self.config.max_iter,
            goal_bias=self.config.goal_bias,
            search_bounds=self.config.bounds
        )
        
        # Check the result
        if self.path_geom:
            print("RRT SUCCESS: Path found!")
            if not self.path_geom.isValid():
                print("WARNING: Found path geometry is invalid.")
            if self.path_geom.isEmpty():
                print("WARNING: Found path geometry is empty.")
            print(f"  Path Length (approx): {self.path_geom.length():.2f}") # Use length() for planar CRS
            return True
        else:
            print("RRT FAILED: No path found within iterations.")
            return False
    
    def visualize_result(self, clear_existing=True):
        """Add visualization layers to QGIS"""
        try:
            # Clear existing test layers if requested
            if clear_existing:
                # Get all layers in the project
                project = QgsProject.instance()
                layer_ids_to_remove = []
                
                # Find layers with our test names
                for layer_id, layer in project.mapLayers().items():
                    if layer.name() in ["rrt_obstacles", "rrt_points", "rrt_path"]:
                        layer_ids_to_remove.append(layer_id)
                
                # Remove the layers
                for layer_id in layer_ids_to_remove:
                    project.removeMapLayer(layer_id)
                
                # Clear our layer references
                self.layers = {}
            
            # Base CRS - using projected CRS for better distance calculations
            crs = self.config.crs
            
            # Create new layers
            obstacles_layer = QgsVectorLayer(f"Polygon?crs={crs}", "rrt_test_obstacles", "memory")
            points_layer = QgsVectorLayer(f"Point?crs={crs}", "rrt_test_points", "memory")
            
            # Set up fields
            for layer in [obstacles_layer, points_layer]:
                provider = layer.dataProvider()
                provider.addAttributes([QgsField("Type", QVariant.String)])
                layer.updateFields()
            
            # Style obstacles layer (red semi-transparent)
            if obstacles_layer.renderer() and obstacles_layer.renderer().symbol():
                fill_symbol = obstacles_layer.renderer().symbol()
                fill_symbol.setColor(QColor(255, 0, 0, 50))
                fill_symbol.setOpacity(0.5)
            
            # Add obstacle features
            if self.config.obstacles_list:
                features = []
                for i, obs_geom in enumerate(self.config.obstacles_list):
                    feature = QgsFeature(obstacles_layer.fields())
                    feature.setGeometry(obs_geom)
                    feature.setAttributes([f"Obstacle_{i+1}"])
                    features.append(feature)
                
                obstacles_layer.dataProvider().addFeatures(features)
            
            # Add start/end points
            start_pose = self.config.get_start_pose()
            end_pose = self.config.get_end_pose()
            
            start_feature = QgsFeature(points_layer.fields())
            start_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(start_pose[0], start_pose[1])))
            start_feature.setAttributes(["Start"])
            
            end_feature = QgsFeature(points_layer.fields())
            end_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(end_pose[0], end_pose[1])))
            end_feature.setAttributes(["End"])
            
            points_layer.dataProvider().addFeatures([start_feature, end_feature])
            
            # Add path layer if a path was found
            path_layer = None
            if self.path_geom and not self.path_geom.isEmpty():
                path_layer = QgsVectorLayer(f"LineString?crs={crs}", "rrt_test_path", "memory")
                path_layer.dataProvider().addAttributes([QgsField("Type", QVariant.String)])
                path_layer.updateFields()
                
                # Style path layer (blue line)
                if path_layer.renderer() and path_layer.renderer().symbol():
                    line_symbol = path_layer.renderer().symbol()
                    line_symbol.setColor(QColor(0, 0, 255))
                    line_symbol.setWidth(0.8)
                
                # Add path feature
                path_feature = QgsFeature(path_layer.fields())
                path_feature.setGeometry(self.path_geom)
                path_feature.setAttributes(["Path"])
                path_layer.dataProvider().addFeatures([path_feature])
                
                # Add to project
                QgsProject.instance().addMapLayer(path_layer)
            
            # Add layers to project
            QgsProject.instance().addMapLayer(obstacles_layer)
            QgsProject.instance().addMapLayer(points_layer)
            
            # Store references
            self.layers = {
                'obstacles': obstacles_layer,
                'points': points_layer
            }
            if path_layer:
                self.layers['path'] = path_layer
            
            print("Visualization layers added to QGIS.")
            return True
            
        except Exception as e:
            import traceback
            print(f"Error in visualization: {e}")
            traceback.print_exc()
            return False

    def run_and_visualize(self) -> bool:
        """Run test and visualize in a single call"""
        success = self.run_test()
        self.visualize_result()
        return success


# ----- Predefined Test Scenarios -----

class TestScenarios:
    """Class containing predefined test scenarios for RRT"""
    
    @staticmethod
    def setup_no_obstacle() -> RRTTestConfig:
        """Scenario 1: No obstacles - should find direct Dubins path"""
        config = RRTTestConfig()
        config.clear_obstacles()  # Make sure no obstacles
        return config
    
    @staticmethod
    def setup_simple_blocking_obstacle() -> RRTTestConfig:
        """Scenario 2: Simple blocking obstacle - should find path around"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # Add rectangle blocking direct path
        obstacle_wkt = 'POLYGON((80 -20, 120 -20, 120 40, 80 40, 80 -20))'
        config.add_obstacle_from_wkt(obstacle_wkt)
        return config
    
    @staticmethod
    def setup_different_headings() -> RRTTestConfig:
        """Scenario 3: Different start/end headings"""
        config = RRTTestConfig()
        config.clear_obstacles()
        config.start_h_deg = 90  # Start heading North
        config.end_h_deg = 270   # End heading South
        return config
    
    @staticmethod
    def setup_concave_obstacle() -> RRTTestConfig:
        """Scenario 4: U-shaped (concave) obstacle"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # U-shaped polygon blocking direct path
        u_shape_wkt = 'POLYGON((80 -40, 120 -40, 120 60, 100 60, 100 0, 80 0, 80 -40))'
        config.add_obstacle_from_wkt(u_shape_wkt)
        return config
    
    @staticmethod
    def setup_multiple_obstacles() -> RRTTestConfig:
        """Scenario 5: Multiple obstacles"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # First obstacle
        obstacle1_wkt = 'POLYGON((60 -20, 90 -20, 90 40, 60 40, 60 -20))'
        config.add_obstacle_from_wkt(obstacle1_wkt)
        # Second obstacle
        obstacle2_wkt = 'POLYGON((120 -40, 150 -40, 150 20, 120 20, 120 -40))'
        config.add_obstacle_from_wkt(obstacle2_wkt)
        return config
    
    @staticmethod
    def setup_narrow_gap() -> RRTTestConfig:
        """Scenario 6: Narrow gap between obstacles"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # Two obstacles with narrow gap between
        obstacle1_wkt = 'POLYGON((80 -40, 95 -40, 95 5, 80 5, 80 -40))'
        obstacle2_wkt = 'POLYGON((105 -40, 120 -40, 120 5, 105 5, 105 -40))'
        config.add_obstacle_from_wkt(obstacle1_wkt)
        config.add_obstacle_from_wkt(obstacle2_wkt)
        # Use smaller step size for better chance to find gap
        config.step_size = 5.0
        config.max_iter = 5000  # More iterations if needed
        return config
    
    @staticmethod
    def setup_no_path() -> RRTTestConfig:
        """Scenario 7: No path possible (enclosed start point)"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # Create a wall around start point
        enclosing_wkt = 'POLYGON((0 0, 30 0, 30 30, 0 30, 0 0))'
        config.add_obstacle_from_wkt(enclosing_wkt)
        # Ensure start point is inside obstacle
        config.start_x, config.start_y = 15, 15
        return config
    
    @staticmethod
    def setup_tight_turns() -> RRTTestConfig:
        """Scenario 8: Path requiring tight turns - test with small turn radius"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # Create a zigzag-requiring obstacle arrangement
        obstacle1_wkt = 'POLYGON((40 -40, 70 -40, 70 0, 40 0, 40 -40))'
        obstacle2_wkt = 'POLYGON((70 20, 100 20, 100 60, 70 60, 70 20))'
        obstacle3_wkt = 'POLYGON((120 -40, 150 -40, 150 0, 120 0, 120 -40))'
        config.add_obstacle_from_wkt(obstacle1_wkt)
        config.add_obstacle_from_wkt(obstacle2_wkt)
        config.add_obstacle_from_wkt(obstacle3_wkt)
        # Use smaller turn radius
        config.turn_radius = 5.0
        return config
    
    @staticmethod
    def setup_zero_turn_radius() -> RRTTestConfig:
        """Scenario 9: Test with zero turn radius (should use fallback)"""
        config = RRTTestConfig()
        config.clear_obstacles()
        # Add one obstacle
        obstacle_wkt = 'POLYGON((80 -20, 120 -20, 120 40, 80 40, 80 -20))'
        config.add_obstacle_from_wkt(obstacle_wkt)
        # Set turn radius to zero
        config.turn_radius = 0.0
        return config

# ----- Main Testing Interface -----

# Global runner instance
rrt_runner = RRTTestRunner()

def run_test_scenario(scenario_num: int) -> bool:
    """Run a predefined test scenario"""
    # Create a fresh runner instance to avoid issues with stale references
    global rrt_runner
    rrt_runner = RRTTestRunner()
    
    scenario_methods = {
        1: TestScenarios.setup_no_obstacle,
        2: TestScenarios.setup_simple_blocking_obstacle,
        3: TestScenarios.setup_different_headings,
        4: TestScenarios.setup_concave_obstacle,
        5: TestScenarios.setup_multiple_obstacles,
        6: TestScenarios.setup_narrow_gap,
        7: TestScenarios.setup_no_path,
        8: TestScenarios.setup_tight_turns,
        9: TestScenarios.setup_zero_turn_radius
    }
    
    if scenario_num not in scenario_methods:
        print(f"Error: Scenario {scenario_num} not found. Available scenarios: {list(scenario_methods.keys())}")
        return False
    
    print(f"\n=== Running Test Scenario {scenario_num} ===\n")
    config = scenario_methods[scenario_num]()
    rrt_runner.config = config
    
    # First try to run the RRT algorithm without visualization
    try:
        success = rrt_runner.run_test()
        if success:
            print("RRT algorithm successful, now visualizing...")
        else:
            print("RRT algorithm failed to find a path.")
        
        # Try to visualize regardless of path finding success
        try:
            rrt_runner.visualize_result()
        except Exception as viz_error:
            import traceback
            print(f"Visualization error: {viz_error}")
            traceback.print_exc()
        
        return success
    except Exception as e:
        import traceback
        print(f"Error running scenario {scenario_num}: {e}")
        traceback.print_exc()
        return False

# Simple test function that doesn't use QGIS visualization
def simple_test_rrt(scenario_num: int) -> bool:
    """Run a test scenario without QGIS visualization.
    Just reports if a path was found and basic path information."""
    # Create test configuration
    scenario_methods = {
        1: TestScenarios.setup_no_obstacle,
        2: TestScenarios.setup_simple_blocking_obstacle,
        3: TestScenarios.setup_different_headings,
        4: TestScenarios.setup_concave_obstacle,
        5: TestScenarios.setup_multiple_obstacles,
        6: TestScenarios.setup_narrow_gap,
        7: TestScenarios.setup_no_path,
        8: TestScenarios.setup_tight_turns,
        9: TestScenarios.setup_zero_turn_radius
    }
    
    if scenario_num not in scenario_methods:
        print(f"Error: Scenario {scenario_num} not found. Available scenarios: {list(scenario_methods.keys())}")
        return False
    
    print(f"\n=== Simple Test of Scenario {scenario_num} ===\n")
    config = scenario_methods[scenario_num]()
    
    # Get configuration parameters
    start_pose = config.get_start_pose()
    end_pose = config.get_end_pose()
    turn_radius = config.turn_radius
    obstacles = config.obstacles_list
    step_size = config.step_size
    
    # Use default values for these parameters if not present in config
    max_iterations = getattr(config, 'max_iterations', 3000)  # Default: 3000
    goal_bias = getattr(config, 'goal_bias', 0.15)  # Default: 0.15
    
    # Print configuration
    print(f"----- RRT Test Configuration -----")
    print(f"Start: ({start_pose[0]}, {start_pose[1]}, {math.degrees(start_pose[2]):.0f}°)")
    print(f"End: ({end_pose[0]}, {end_pose[1]}, {math.degrees(end_pose[2]):.0f}°)")
    print(f"Turn Radius: {turn_radius}")
    print(f"Step Size: {step_size}")
    print(f"Max Iterations: {max_iterations}")
    print(f"Goal Bias: {goal_bias}")
    print(f"Bounds: None")
    print(f"Obstacles: {len(obstacles)}")
    print(f"----------------------------------")
    
    # Run RRT planner directly
    print(f"Running direct RRT path finding test...")
    try:
        # Directly call the RRT path finding function
        path_geom = rrt_planner.find_rrt_path(
            start_pose=start_pose,
            end_pose=end_pose,
            obstacles=obstacles,
            turn_radius=turn_radius,
            step_size=step_size,
            max_iterations=max_iterations,
            goal_bias=goal_bias
        )
        
        # Check if a path was found
        if path_geom and not path_geom.isEmpty():
            print("SUCCESS: Path found!")
            try:
                # Try to get basic path info
                length = path_geom.length()
                vertices = list(path_geom.vertices())
                print(f"Path length: {length:.2f}")
                print(f"Path vertices: {len(vertices)}")
                return True
            except Exception as e:
                print(f"Error getting path details: {e}")
                return True  # Still successful even if we can't get details
        else:
            print("FAILED: No path found.")
            return False
    except Exception as e:
        import traceback
        print(f"Error in RRT path finding: {e}")
        traceback.print_exc()
        return False

def run_dubins_test(start_x: float = 10, start_y: float = 10, start_h_deg: float = 0, 
                   target_x: float = 100, target_y: float = 50, target_h_deg: float = 45,
                   turn_radius: float = 25.0, target_dist: float = 15.0, crs: str = "EPSG:31984") -> bool:
    """Test the Dubins path steering function directly"""
    # Create start node and target state
    start_node = rrt_planner.RRTNode(start_x, start_y, math.radians(start_h_deg))
    target_state = (target_x, target_y, math.radians(target_h_deg))
    
    print("\n=== Testing Dubins Path Steering ===\n")
    print(f"Start: ({start_x}, {start_y}, {start_h_deg}°)")
    print(f"Target: ({target_x}, {target_y}, {target_h_deg}°)")
    print(f"Turn Radius: {turn_radius}")
    print(f"Target Distance: {target_dist}")
    
    # Execute steering function
    new_node, path_geom, seg_len = rrt_planner.get_dubins_path_segment(
        start_node, target_state, turn_radius, target_dist
    )
    
    # Check result
    if new_node and path_geom and seg_len is not None:
        print("Steer SUCCESS:")
        print(f"  New Node State: ({new_node.x:.2f}, {new_node.y:.2f}, {math.degrees(new_node.heading):.1f}°)")
        print(f"  Segment Length: {seg_len:.2f} (Target was: {target_dist:.2f})")
        print(f"  Path Geom Valid: {path_geom.isValid()}, Empty: {path_geom.isEmpty()}")
        
        # Visualize the result
        crs = crs  # Use configured CRS (EPSG:31984 for better distance calculations)
        
        # Create a layer for the RRT path
        vl_path = QgsVectorLayer(f"LineString?crs={crs}", "rrt_test_path", "memory")
        pr_path = vl_path.dataProvider()
        f = QgsFeature()
        f.setGeometry(path_geom)
        pr_path.addFeatures([f])
        
        # Create start/end points layer
        vl_pts = QgsVectorLayer(f"Point?crs={crs}", "rrt_test_points", "memory")
        pr_pts = vl_pts.dataProvider()
        pr_pts.addAttributes([QgsField("Type", QVariant.String)])
        vl_pts.updateFields()
        
        # Add start and new end points
        f_start = QgsFeature(vl_pts.fields())
        f_start.setGeometry(QgsGeometry.fromPointXY(start_node.point()))
        f_start.setAttributes(["Start"])
        
        f_target = QgsFeature(vl_pts.fields())
        f_target.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(target_state[0], target_state[1])))
        f_target.setAttributes(["Target"])
        
        f_new = QgsFeature(vl_pts.fields())
        f_new.setGeometry(QgsGeometry.fromPointXY(new_node.point()))
        f_new.setAttributes(["New Node"])
        
        pr_pts.addFeatures([f_start, f_target, f_new])
        
        # Add layers to map
        QgsProject.instance().addMapLayer(vl_path)
        QgsProject.instance().addMapLayer(vl_pts)
        
        print("Visualization layers added to QGIS.")
        return True
    else:
        print("Steer FAILED.")
        return False


# Print available test functions
print("\n=== RRT Testing Module Loaded ===\n")
print("Available functions:")
print("  run_test_scenario(scenario_num) - Run a predefined test scenario (1-9)")
print("  run_dubins_test() - Test the Dubins path steering function directly")
print("\nTest scenario descriptions:")
print("  1: No obstacles - direct path")
print("  2: Simple blocking obstacle")
print("  3: Different start/end headings")
print("  4: Concave (U-shaped) obstacle")
print("  5: Multiple obstacles")
print("  6: Narrow gap between obstacles")
print("  7: No path possible (enclosed start)")
print("  8: Path requiring tight turns")
print("  9: Zero turn radius test")
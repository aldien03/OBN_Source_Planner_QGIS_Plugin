import math
import random
from typing import List, Tuple, Optional, Union
from qgis.core import (
    QgsPointXY,
    QgsGeometry,
    QgsLineString,
    QgsWkbTypes,
    QgsPoint,
    QgsGeometryUtils, # For combining lines
)

# Import dubins_path module using relative import for QGIS plugin structure
from . import dubins_path

# --- Constants (can be adjusted or passed as parameters) ---
DEFAULT_STEP_SIZE = 50.0         # How far to extend the tree in one step (meters) - increased for larger survey areas
DEFAULT_MAX_ITERATIONS = 20000   # Max attempts to find a path - increased for complex obstacle avoidance
DEFAULT_GOAL_BIAS = 0.2          # Probability (0-1) of sampling the goal state directly - increased for faster convergence
DEFAULT_GOAL_DIST_TOLERANCE = 25.0 # How close in distance (meters) to the goal is acceptable - increased for faster success
DEFAULT_GOAL_ANGLE_TOLERANCE = math.radians(15.0) # How close in angle (radians) is acceptable - increased for faster success

# --- Data Structures ---

class RRTNode:
    """ Represents a node in the RRT tree """
    def __init__(self, x: float, y: float, heading: float, parent_index: Optional[int] = None,
                 cost_from_start: float = 0.0, path_segment_geom: Optional[QgsGeometry] = None):
        self.x = x
        self.y = y
        self.heading = heading  # In radians
        self.parent_index = parent_index  # Index of the parent node in the tree list
        self.cost_from_start = cost_from_start  # Typically path length from the root node
        self.path_segment_geom = path_segment_geom  # Geometry of the path segment from parent to this node

    def state(self) -> Tuple[float, float, float]:
        """ Returns the state as a tuple (x, y, heading_radians) """
        return (self.x, self.y, self.heading)

    def point(self) -> QgsPointXY:
        """ Returns the location as a QgsPointXY """
        return QgsPointXY(self.x, self.y)

# --- Helper Functions ---

def calculate_distance_euclidean(p1: QgsPointXY, p2: QgsPointXY) -> float:
    """ 
    Calculates simple Euclidean distance. Assumes points are in a projected CRS.
    
    Args:
        p1: First point
        p2: Second point
        
    Returns:
        Euclidean distance between points
    """
    return math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)

def normalize_angle(angle_rad: float) -> float:
    """
    Normalizes an angle to be within [-pi, pi].
    
    Args:
        angle_rad: Angle in radians
        
    Returns:
        Normalized angle in radians
    """
    while angle_rad > math.pi:
        angle_rad -= 2.0 * math.pi
    while angle_rad <= -math.pi:
        angle_rad += 2.0 * math.pi
    return angle_rad

def get_dubins_path_segment(from_node: RRTNode, to_state: Tuple[float, float, float],
                           turn_radius: float, target_dist: float) -> Tuple[Optional[RRTNode], Optional[QgsGeometry], Optional[float]]:
    """
    Uses Dubins path logic to find a new node approximately target_dist away
    from from_node towards to_state, respecting turn radius.

    Returns:
        - new_node: The RRTNode at the end of the segment (or None if error).
        - path_geom: The QgsGeometry of the path segment (or None).
        - segment_length: The actual length of the generated Dubins segment (or None).
    """
    start_pose = from_node.state()
    # Dubins calculation needs a target pose, not just point.
    # For simplicity now, use the target point's coords and the 'to_state' heading.
    # More advanced: calculate heading towards the target point.
    end_pose_target = to_state # Use the heading from the sampled state

    if not all(map(math.isfinite, start_pose + end_pose_target)):
         print(f"WARN: Invalid start or end pose for Dubins: {start_pose}, {end_pose_target}")
         return None, None, None

    try:
        # 1. Calculate the full Dubins path solution
        # Ensure turn radius is positive and not too small
        if turn_radius <= 1e-6:
            print("WARN: Turn radius is too small for Dubins calculation.")
            # Fallback: straight line segment (ignoring heading constraints)
            start_pt = from_node.point()
            end_pt_target = QgsPointXY(end_pose_target[0], end_pose_target[1])
            dist_to_target = calculate_distance_euclidean(start_pt, end_pt_target)
            if dist_to_target < 1e-6: 
                print("WARN: Target is too close to start point")
                return None, None, None  # Too close

            actual_dist = min(target_dist, dist_to_target)
            # Protect against division by zero
            if dist_to_target > 1e-6:
                interp_pt = start_pt + (end_pt_target - start_pt) * (actual_dist / dist_to_target)
            else:
                # If points are too close, just use the target point
                interp_pt = end_pt_target
            line_geom = QgsGeometry.fromPolylineXY([start_pt, interp_pt])
            new_heading = math.atan2(interp_pt.y() - start_pt.y(), interp_pt.x() - start_pt.x())
            new_node = RRTNode(interp_pt.x(), interp_pt.y(), new_heading)
            return new_node, line_geom, actual_dist

        # Proceed with Dubins
        modes, lengths, radii = dubins_path.dubins_path(start_pose, end_pose_target, turn_radius)
        solution = (modes, lengths, radii)

        # 2. Get projected points along the path
        # Use small angle/dist for projection to get enough detail
        proj_max_line_dist = max(target_dist / 5.0, 0.1) # Smaller step for projection, minimum 0.1
        proj_max_curve_dist = max(target_dist / 5.0, 0.1) # Minimum 0.1 to avoid very small values
        
        # Extra protection against division by zero or very small values
        if turn_radius > 1e-3:  # Increased threshold for safety
            proj_max_curve_angle = (proj_max_curve_dist * 360) / (2 * math.pi * turn_radius)
        else:
            # Default angle if turn radius is too small
            proj_max_curve_angle = 90.0

        # Temporarily set global vars for get_projection (ugly, consider refactoring dubins_path later)
        original_globals = dubins_path.MAX_LINE_DISTANCE, dubins_path.MAX_CURVE_ANGLE
        dubins_path.MAX_LINE_DISTANCE = proj_max_line_dist
        dubins_path.MAX_CURVE_ANGLE = proj_max_curve_angle
        # Ensure get_projection has access to MAX_CURVE_DISTANCE if needed
        dubins_path.MAX_CURVE_DISTANCE = proj_max_curve_dist

        projected_points = dubins_path.get_projection(start=start_pose, end=end_pose_target, solution=solution)

        # Restore original globals
        dubins_path.MAX_LINE_DISTANCE, dubins_path.MAX_CURVE_ANGLE = original_globals

        if not projected_points:
            # print("WARN: Dubins projection returned no points.")
            return None, None, None

        # 3. Find the point approximately target_dist away
        path_vertices = [from_node.point()] # Start with the from_node's point
        accumulated_dist = 0.0
        final_node = None
        final_segment_length = 0.0

        prev_pt = from_node.point()
        prev_head = from_node.heading

        for i, p_data in enumerate(projected_points):
            current_pt = QgsPointXY(p_data[0], p_data[1])
            # Dubins get_projection seems to return heading in degrees, need radians
            current_head_deg = p_data[2] # Assuming this is heading in degrees
            current_head_rad = math.radians(current_head_deg)
            # --- DEBUG ---
            # Convert the angle based on tangent calculation in split_arc/split_line if needed
            # The third element might need interpretation based on L/R/S modes
            # Let's tryatan2 from previous point for heading estimation
            dx = current_pt.x() - prev_pt.x()
            dy = current_pt.y() - prev_pt.y()
            segment_heading_rad = math.atan2(dy, dx) if (abs(dx)>1e-6 or abs(dy)>1e-6) else prev_head


            segment_dist = calculate_distance_euclidean(prev_pt, current_pt)

            if accumulated_dist + segment_dist >= target_dist:
                # This segment crosses the target distance
                remaining_dist = target_dist - accumulated_dist
                fraction = remaining_dist / segment_dist if segment_dist > 1e-6 else 0.0
                interp_pt = prev_pt + (current_pt - prev_pt) * fraction

                # Interpolate heading? Or use heading at end of segment? Use segment heading.
                final_heading = segment_heading_rad # Use heading of the segment leading to interpolated point

                path_vertices.append(interp_pt)
                final_node = RRTNode(interp_pt.x(), interp_pt.y(), final_heading)
                final_segment_length = target_dist
                break # Found our point
            else:
                # Add the whole segment
                accumulated_dist += segment_dist
                path_vertices.append(current_pt)
                prev_pt = current_pt
                prev_head = segment_heading_rad # Update heading for next segment calc if needed

        if final_node is None:
            # Reached the end of the projected path before reaching target_dist
            # Use the last point of the projection
            last_p_data = projected_points[-1]
            last_pt = QgsPointXY(last_p_data[0], last_p_data[1])
            #last_head_deg = last_p_data[2]
            #last_head_rad = math.radians(last_head_deg)
            dx = last_pt.x() - prev_pt.x()
            dy = last_pt.y() - prev_pt.y()
            last_segment_heading_rad = math.atan2(dy, dx) if (abs(dx)>1e-6 or abs(dy)>1e-6) else prev_head

            final_node = RRTNode(last_pt.x(), last_pt.y(), last_segment_heading_rad)
            final_segment_length = accumulated_dist # Actual length is the accumulated dist

        # 4. Create the path geometry
        if len(path_vertices) < 2:
            return None, None, None # Not enough points for a line

        path_geom = QgsGeometry.fromPolylineXY(path_vertices)
        return final_node, path_geom, final_segment_length

    except Exception as e:
        print(f"ERROR in get_dubins_path_segment: {e}")
        import traceback
        traceback.print_exc()  # This will print the stack trace
        return None, None, None


# --- Core RRT Function ---

def find_rrt_path(start_pose: tuple[float, float, float],
                   end_pose: tuple[float, float, float],
                   obstacles: list[QgsGeometry],
                   turn_radius: float,
                   step_size: float = DEFAULT_STEP_SIZE,
                   max_iterations: int = DEFAULT_MAX_ITERATIONS,
                   goal_bias: float = DEFAULT_GOAL_BIAS,
                   goal_tolerance_dist: float = DEFAULT_GOAL_DIST_TOLERANCE,
                   goal_tolerance_angle: float = DEFAULT_GOAL_ANGLE_TOLERANCE,
                   search_bounds: tuple | None = None) -> QgsGeometry | None:
    """
    Attempts to find a collision-free, kinematically feasible path using the RRT algorithm.

    Args:
        start_pose: (x, y, heading_radians)
        end_pose: (x, y, heading_radians)
        obstacles: List of QgsGeometry objects representing obstacles
        turn_radius: Minimum turning radius of the vehicle
        step_size: Maximum distance to extend the tree in each iteration
        max_iterations: Maximum number of iterations to attempt
        goal_bias: Probability (0-1) of sampling the goal state directly
        goal_tolerance_dist: How close in distance (meters) to the goal is acceptable
        goal_tolerance_angle: How close in angle (radians) to the goal is acceptable
        search_bounds: Optional (min_x, max_x, min_y, max_y) to constrain the search space
    
    Returns:
        QgsGeometry representing the path if found, None otherwise
    """
    # --- Initialization ---
    # Initialize tree with start node
    start_node = RRTNode(start_pose[0], start_pose[1], start_pose[2])
    tree = [start_node]
    
    # End point for distance calculations
    end_point = QgsPointXY(end_pose[0], end_pose[1])
    
    # Special case: No obstacles and direct path might be possible
    # Try a direct Dubins path first before going into the RRT algorithm
    if not obstacles:
        print("No obstacles detected. Attempting direct Dubins path...")
        try:
            # Try a simple straight-line path first (for the case of aligned headings)
            if abs(normalize_angle(start_pose[2] - end_pose[2])) < 0.1:  # Nearly same heading
                print("Start and end headings are aligned, trying a straight line path...")
                # Create a straight line between start and end
                start_point = QgsPointXY(start_pose[0], start_pose[1])
                end_point = QgsPointXY(end_pose[0], end_pose[1])
                points = [start_point, end_point]
                straight_path = QgsGeometry.fromPolylineXY(points)
                if not straight_path.isEmpty():
                    print("Direct straight-line path found!")
                    return straight_path
            
            # If straight-line doesn't work or headings are different, try Dubins path
            print("Calculating Dubins path...")
            # Calculate direct Dubins path
            modes, lengths, radii = dubins_path.dubins_path(start_pose, end_pose, turn_radius)
            solution = (modes, lengths, radii)
            
            # Get projection points for the direct path
            projected_points = dubins_path.get_projection(start=start_pose, end=end_pose, solution=solution)
            
            if projected_points and len(projected_points) > 1:
                # Convert to a QgsGeometry
                path_vertices = [QgsPointXY(p[0], p[1]) for p in projected_points]
                direct_path_geom = QgsGeometry.fromPolylineXY(path_vertices)
                if not direct_path_geom.isEmpty():
                    print("Direct Dubins path found!")
                    return direct_path_geom
            else:
                print("Dubins path calculation succeeded but returned no points. Creating a simple path.")
                # Create a simple path as fallback
                simple_start = QgsPointXY(start_pose[0], start_pose[1])
                simple_end = QgsPointXY(end_pose[0], end_pose[1])
                simple_path = QgsGeometry.fromPolylineXY([simple_start, simple_end])
                return simple_path
                
        except Exception as e:
            print(f"Direct Dubins path attempt failed: {e}")
            print("Creating a simple direct path as fallback...")
            # Create a simple direct path as fallback
            try:
                simple_start = QgsPointXY(start_pose[0], start_pose[1])
                simple_end = QgsPointXY(end_pose[0], end_pose[1])
                simple_path = QgsGeometry.fromPolylineXY([simple_start, simple_end])
                return simple_path
            except Exception as e2:
                print(f"Even simple path creation failed: {e2}")
            # Continue with RRT if direct path fails
    
    # Set search bounds if provided
    if search_bounds:
        min_x, max_x, min_y, max_y = search_bounds
    else:
        # Default bounds based on start/end with some margin
        min_x = min(start_pose[0], end_pose[0]) - 100  # Increased margin
        max_x = max(start_pose[0], end_pose[0]) + 100
        min_y = min(start_pose[1], end_pose[1]) - 100
        max_y = max(start_pose[1], end_pose[1]) + 100
    
    # Pre-process obstacles (optional but recommended for complex geometries)
    prepared_obstacles = []
    for obs in obstacles:
        if obs and not obs.isEmpty():
             # obs.prepareGeometry() # Use if QgsGeometry supports it and needed
             prepared_obstacles.append(obs)
    obstacles = prepared_obstacles # Use the potentially prepared list

    # --- RRT Main Loop ---
    for iteration in range(max_iterations):
        # 1. Sample State
        if random.random() < goal_bias:
            # Sample goal state directly
            sampled_state = end_pose
        else:
            # Sample random state within bounds (if provided)
            if search_bounds:
                min_x, max_x, min_y, max_y = search_bounds
                rand_x = random.uniform(min_x, max_x)
                rand_y = random.uniform(min_y, max_y)
            else:
                # Heuristic: Sample somewhat around start/end points if no bounds
                # This needs improvement for robust unbounded sampling
                sample_center_x = (start_pose[0] + end_pose[0]) / 2
                sample_center_y = (start_pose[1] + end_pose[1]) / 2
                sample_range = max(abs(start_pose[0]-end_pose[0]), abs(start_pose[1]-end_pose[1])) * 2 + 100 # Heuristic range
                rand_x = random.uniform(sample_center_x - sample_range/2, sample_center_x + sample_range/2)
                rand_y = random.uniform(sample_center_y - sample_range/2, sample_center_y + sample_range/2)

            # Sample random heading (or keep it simple: use heading towards goal?)
            rand_heading = random.uniform(-math.pi, math.pi)
            sampled_state = (rand_x, rand_y, rand_heading)

        # 2. Find Nearest Node in tree
        nearest_node_index = -1
        min_dist = float('inf')
        sampled_point = QgsPointXY(sampled_state[0], sampled_state[1])

        for i, node in enumerate(tree):
            dist = calculate_distance_euclidean(node.point(), sampled_point)
            if dist < min_dist:
                min_dist = dist
                nearest_node_index = i

        if nearest_node_index == -1: continue # Should not happen if tree has start node

        nearest_node = tree[nearest_node_index]

        # 3. Steer from Nearest Node towards Sampled State
        new_node_candidate, path_segment_geom, segment_len = get_dubins_path_segment(
            nearest_node, sampled_state, turn_radius, step_size
        )

        if new_node_candidate is None or path_segment_geom is None or segment_len is None:
            continue # Steer function failed

        # 4. Collision Check
        is_safe = True
        if path_segment_geom and not path_segment_geom.isEmpty():
            for obstacle in obstacles:
                if path_segment_geom.intersects(obstacle):
                    is_safe = False
                    break # Collision detected

        # 5. Add to Tree if Safe
        if is_safe:
            new_node_candidate.parent_index = nearest_node_index
            new_node_candidate.path_segment_geom = path_segment_geom
            new_node_candidate.cost_from_start = nearest_node.cost_from_start + segment_len # Use actual segment len
            tree.append(new_node_candidate)
            new_node_index = len(tree) - 1

            # 6. Goal Check
            final_node = new_node_candidate
            dist_to_goal = calculate_distance_euclidean(final_node.point(), end_point)
            angle_diff = abs(normalize_angle(final_node.heading - end_pose[2]))
            
            # Periodically try to connect directly to goal
            if iteration % 50 == 0 and dist_to_goal < step_size * 3:
                # Try to connect directly to the goal
                goal_node, goal_path_geom, goal_segment_len = get_dubins_path_segment(
                    final_node, end_pose, turn_radius, dist_to_goal * 1.5
                )
                
                if goal_node and goal_path_geom and goal_segment_len is not None:
                    # Check if this direct path to goal is collision-free
                    direct_to_goal_safe = True
                    for obstacle in obstacles:
                        if goal_path_geom.intersects(obstacle):
                            direct_to_goal_safe = False
                            break
                    
                    if direct_to_goal_safe:
                        # We found a direct path to goal!
                        print(f"RRT: Direct connection to goal found at iteration {iteration + 1}")
                        # Add the goal node to the tree
                        goal_node.parent_index = new_node_index
                        goal_node.path_segment_geom = goal_path_geom
                        goal_node.cost_from_start = final_node.cost_from_start + goal_segment_len
                        tree.append(goal_node)
                        new_node_index = len(tree) - 1
                        
                        # Skip to path reconstruction
                        print(f"RRT: Path found in {iteration + 1} iterations.")
                        path_geometries = [goal_path_geom]  # Start with the direct goal connection
                        current_index = final_node.parent_index
                        while current_index is not None:
                            node = tree[current_index]
                            if node.path_segment_geom and node.parent_index is not None:
                                path_geometries.insert(0, node.path_segment_geom)
                            current_index = node.parent_index
                        
                        # Combine path segments
                        all_vertices = []
                        if path_geometries:
                            # Process all path segments
                            for i, geom in enumerate(path_geometries):
                                if geom.type() == QgsWkbTypes.LineGeometry:
                                    vertices = list(geom.vertices())
                                    if i == 0:
                                        # Convert QgsPoint to QgsPointXY for all vertices
                                        all_vertices.extend([QgsPointXY(v.x(), v.y()) for v in vertices])  # Include all vertices from first segment
                                    elif len(vertices) > 1:
                                        # Convert QgsPoint to QgsPointXY for subsequent vertices
                                        all_vertices.extend([QgsPointXY(v.x(), v.y()) for v in vertices[1:]])  # Skip first vertex of subsequent segments
                        
                        if len(all_vertices) < 2: return None  # Not enough points
                        
                        final_path_geom = QgsGeometry.fromPolylineXY(all_vertices)
                        if final_path_geom and not final_path_geom.isEmpty() and final_path_geom.isGeosValid():
                            return final_path_geom
            
            # Regular goal check
            if dist_to_goal <= goal_tolerance_dist and angle_diff <= goal_tolerance_angle:
                print(f"RRT: Path found in {iteration + 1} iterations.")
                # --- Path Reconstruction ---
                path_geometries = []
                current_index: int | None = new_node_index
                while current_index is not None:
                    node = tree[current_index]
                    if node.path_segment_geom and node.parent_index is not None:
                        # Insert at beginning to get correct order
                        path_geometries.insert(0, node.path_segment_geom)
                    current_index = node.parent_index

                if not path_geometries: return None # Should not happen if goal node has parent

                # Combine path segments
                # combined_geom = QgsGeometryUtils.combineLines(path_geometries) # Check if this works robustly
                # Manual combination as fallback:
                all_vertices = []
                if path_geometries:
                     # Add vertices from the first segment
                     if path_geometries[0].type() == QgsWkbTypes.LineGeometry:
                          vertices = list(path_geometries[0].vertices())
                          # Convert QgsPoint to QgsPointXY
                          all_vertices.extend([QgsPointXY(v.x(), v.y()) for v in vertices])
                     # Add vertices from subsequent segments (skip first vertex of each)
                     for geom in path_geometries[1:]:
                          if geom.type() == QgsWkbTypes.LineGeometry:
                              vertices = list(geom.vertices())
                              if len(vertices)>1:
                                   # Convert QgsPoint to QgsPointXY
                                   all_vertices.extend([QgsPointXY(v.x(), v.y()) for v in vertices[1:]]) # Avoid duplicating connection points

                if len(all_vertices)<2: return None # Not enough points

                final_path_geom = QgsGeometry.fromPolylineXY(all_vertices)
                # Use isGeosValid() instead of isValid() for compatibility with different QGIS versions
                try:
                    # Check if geometry is valid using available method
                    is_valid = False
                    if final_path_geom is None:
                        return None
                    
                    if hasattr(final_path_geom, 'isValid'):
                        is_valid = final_path_geom.isValid()
                    elif hasattr(final_path_geom, 'isGeosValid'):
                        is_valid = final_path_geom.isGeosValid()
                    else:
                        # Assume valid if we can't check
                        is_valid = True
                    
                    if not final_path_geom.isEmpty() and is_valid:
                        return final_path_geom
                    else:
                        print("RRT: Failed to combine path segments into valid geometry.")
                        # Try returning the first segment as fallback
                        if path_geometries and path_geometries[0] and not path_geometries[0].isEmpty():
                            print("RRT: Using first path segment as fallback")
                            return path_geometries[0]
                        return None  # Failed to combine
                except Exception as e:
                    print(f"RRT: Error validating path geometry: {e}")
                    # Fallback: return the first segment if available
                    if path_geometries and len(path_geometries) > 0:
                        return path_geometries[0]
                    return None

    # --- End of Loop ---
    print(f"RRT: Failed to find path within {max_iterations} iterations.")
    return None # Path not found within iterations
# --- START OF FILE dubins_path.py ---

"""
Dubins functionality.
"""

import math

# Define locally instead of importing from easydubins
DECIMAL_ROUND = 7
MAX_LINE_DISTANCE = 0.0
MAX_CURVE_DISTANCE = 0.0
MAX_CURVE_ANGLE = 0.0


def mod2pi(theta):
    """
    Some mathematics formula
    :param theta: angle in radians
    :return:result
    """
    return theta - 2.0 * math.pi * math.floor(theta / 2.0 / math.pi)


def calculate_angle(point_1, point_2):
    """
    Calculates angle between two points
    :param point_1:first point
    :type point_1:list
    :param point_2:second point
    :type point_2:list
    """
    delta_x = point_2[0] - point_1[0]
    delta_y = point_2[1] - point_1[1]
    angle = math.degrees(math.atan2(delta_y, delta_x))
    return angle


def calculate_distance(x_1, y_1, x_2, y_2):
    """
    Calculate distance between two points
    :param x_1: X-Coord of point-1
    :param y_1: Y-Coord of point-1
    :param x_2: X-Coord of point-2
    :param y_2: Y-Coord of point-2
    :return: Distance (integer)
    """
    return math.sqrt(math.pow((x_2 - x_1), 2) + math.pow((y_2 - y_1), 2))


def tangent_angle(center, x_coord, y_coord):
    """
    Calculates tangent angle for a point on circle.
    :param center: center point of a circle
    :type center:tuple
    :param x_coord: X-Coord of tangent point on circle
    :type x_coord:float
    :param y_coord: X-Coord of tangent point on circle
    :type y_coord:float
    :return: angle
    """
    delta_x = x_coord - center[0]
    delta_y = y_coord - center[1]
    tan_deg = math.degrees(math.atan2(delta_y, delta_x))
    if delta_x < 0:
        angle1 = 180 - tan_deg
        angle2 = (angle1 + 180) % 360
    else:
        angle1 = -tan_deg if delta_y < 0 else (360 - tan_deg)
        angle2 = (angle1 + 180) % 360
    return angle1, angle2


def split_angle(start, end, max_curve_angle):
    """
    Split arc into parts to get multiple points on arc.
    :param start: starting angle
    :param end: ending angle
    :param max_curve_angle: maximum difference between two points.
    :return: list of angles
    """
    # Ensure max_curve_angle is positive and not too small
    max_curve_angle = max(0.1, abs(max_curve_angle))  # Minimum value to prevent infinite loops
    
    angles = [start]  # Always include the start angle
    
    # Handle angle wrapping (when end < start)
    if end <= start:
        # We need to go through the 0/360 point
        end += 360.0
    
    # Calculate intermediate angles
    current = start
    while current + max_curve_angle < end:
        current += max_curve_angle
        angles.append(current)
    
    # Only add end angle if it's not already the last one
    if abs(angles[-1] - end) > 1e-6:  # Use small epsilon for float comparison
        angles.append(end)
        
    return angles


def split_arc(center, theta1, theta2, radius, max_curve_angle, direction):
    """
     Find the multiple points on curved path
    :param center:Center of a dubin circle.
    :param theta1:starting angle of a curve
    :type theta1:float
    :param theta2:ending angle of a curve
    :type theta2:float
    :param radius:turning radius of vehicle
    :type radius:float
    :param max_curve_angle:max angle difference between two points on circle
    :type max_curve_angle:float
    :param direction:"R" is right and "L" is left
    :type direction:str
    :return: List of points along the arc, or None on error
    """
    try:
        # Input validation and error handling
        if center is None or not isinstance(center, (list, tuple)) or len(center) < 2:
            print("ERROR in split_arc: Invalid center point")
            return []
            
        # Ensure radius is positive and not too small
        radius = max(0.001, abs(radius))  # Minimum radius to prevent calculation issues
        
        # Ensure max_curve_angle is positive and reasonable
        max_curve_angle = max(0.1, abs(max_curve_angle))  # Minimum angle to prevent infinite loops
        
        # Handle equal angles case - return a single point
        if abs(theta1 - theta2) < 1e-6:  # Use small epsilon for float comparison
            p = theta1  # Just use theta1 since they're essentially equal
            x_coord = round(center[0] + radius * math.cos(math.radians(p)), DECIMAL_ROUND)
            y_coord = round(center[1] + radius * math.sin(math.radians(p)), DECIMAL_ROUND)
            try:
                heading1, heading2 = tangent_angle(center, x_coord, y_coord)
                return [[x_coord, y_coord, heading2 if direction == 'R' else heading1]]
            except Exception as e:
                print(f"Warning in split_arc: Tangent angle calculation failed: {e}")
                # Fallback: estimate heading directly from angle
                heading = (p + (90 if direction == 'R' else 270)) % 360
                return [[x_coord, y_coord, heading]]
        
        # Get angle points with improved split_angle function
        points = split_angle(theta1, theta2, max_curve_angle)
        if not points:
            print("ERROR in split_arc: No angle points generated")
            return []
            
        arc_points = []
        if direction == 'R':
            points.reverse()
        
        # Process each point along the arc
        for p in points:
            x_coord = round(center[0] + radius * math.cos(math.radians(p)), DECIMAL_ROUND)
            y_coord = round(center[1] + radius * math.sin(math.radians(p)), DECIMAL_ROUND)
            try:
                heading1, heading2 = tangent_angle(center, x_coord, y_coord)
                arc_points.append([x_coord, y_coord, heading2 if direction == 'R' else heading1])
            except Exception as e:
                print(f"Warning in split_arc: Tangent angle calculation failed for point {p}: {e}")
                # Fallback: estimate heading directly from angle
                heading = (p + (90 if direction == 'R' else 270)) % 360
                arc_points.append([x_coord, y_coord, heading])
                
        # Remove first point only if there are multiple points
        if len(arc_points) > 1:
            arc_points.pop(0)  # First value already in the path
            
        return arc_points
        
    except Exception as e:
        print(f"ERROR in split_arc: {e}")
        # Return an empty list as fallback
        return []


def split_line(x_1, y_1, x_2, y_2, dividing_factor):
    """
    It calculate the points between a line.
    :param x_1: X-Coord of point-1
    :param y_1: Y-Coord of point-1
    :param x_2: X-Coord of point-2
    :param y_2: Y-Coord of point-2
    :param dividing_factor: Maximum distance between two consecutive points.
    :return: List. List of points between a line.
    """
    parts = []
    distance = calculate_distance(x_1, y_1, x_2, y_2)
    count = int(distance / dividing_factor)
    prev_x = x_1
    prev_y = y_1
    angle = calculate_angle([prev_x, prev_y], [x_2, y_2])
    modified_angle = (90 - angle) % 360
    if (round(x_1, DECIMAL_ROUND) == round(x_2, DECIMAL_ROUND)) and (
            round(y_1, DECIMAL_ROUND) == round(y_2, DECIMAL_ROUND)):
        return []
    elif count == 0:
        # parts.append([round(x_1, DECIMAL_ROUND), round(y_1, DECIMAL_ROUND), modified_angle])
        parts.append([round(x_2, DECIMAL_ROUND), round(y_2, DECIMAL_ROUND), modified_angle])
    else:
        step = dividing_factor / distance
        increment = step
        while increment < 1:
            x = (1 - increment) * x_1 + increment * x_2
            y = (1 - increment) * y_1 + increment * y_2
            # angle = calculate_angle([prev_x, prev_y], [x, y])
            # modified_angle = (90 - angle) % 360
            parts.append([round(x, DECIMAL_ROUND), round(y, DECIMAL_ROUND), modified_angle])
            increment += step
        parts.append([round(x_2, DECIMAL_ROUND), round(y_2, DECIMAL_ROUND), modified_angle])
    # parts[0][2] = (90 - math.degrees(first_heading)) % 360
    return parts


def get_projection(start, end, solution):
    """
    Get projected path into multiple points and stored it in PROJECTIONS list variable.
    :param start:start/first point
    :type start:tuple
    :param end:end/second point
    :type end:tuple
    :param solution:solution provided by dubins function
    :type solution:tuple
    """
    global PROJECTIONS
    projection_points = list()
    # print(start, end, solution)
    cur_pos = start

    for i in range(3):
        mode = solution[0][i]
        length = solution[1][i]
        radius = solution[2][i]
        parts = list()
        # print('mode:', mode, 'length:', length, 'radius:', radius)

        if mode == 'L':
            # print('left')
            center = (
                cur_pos[0] + math.cos(cur_pos[2] + math.pi / 2.0) * radius,
                cur_pos[1] + math.sin(cur_pos[2] + math.pi / 2.0) * radius,
            )

            circumference = math.pi * radius
            theta1 = math.degrees(cur_pos[2]) - 90
            theta2 = theta1 + (180 * length / circumference)

            parts = split_arc(center, theta1, theta2, radius, MAX_CURVE_ANGLE, 'L')

            new_pos = (
                center[0] + math.cos(math.radians(theta2)) * radius,
                center[1] + math.sin(math.radians(theta2)) * radius,
                math.radians(theta2 + 90)
            )

        elif mode == 'l':
            # print('left, reverse')
            center = (
                cur_pos[0] + math.cos(cur_pos[2] + math.pi / 2.0) * radius,
                cur_pos[1] + math.sin(cur_pos[2] + math.pi / 2.0) * radius,
            )

            circumference = math.pi * radius
            theta1 = math.degrees(cur_pos[2]) - 90
            theta2 = theta1 + (180 * length / circumference)

            parts = split_arc(center, theta1, theta2, radius, MAX_CURVE_ANGLE, 'l')

            new_pos = (
                center[0] + math.cos(math.radians(theta2)) * radius,
                center[1] + math.sin(math.radians(theta2)) * radius,
                math.radians(theta2 + 90)
            )

        elif mode == 'R':
            # print('right')
            center = (
                cur_pos[0] + math.cos(cur_pos[2] - math.pi / 2.0) * radius,
                cur_pos[1] + math.sin(cur_pos[2] - math.pi / 2.0) * radius,
            )
            circumference = math.pi * radius
            theta2 = math.degrees(cur_pos[2]) + 90
            theta1 = theta2 - (180 * length / circumference)

            parts = split_arc(center, theta1, theta2, radius, MAX_CURVE_ANGLE, 'R')

            new_pos = (
                center[0] + math.cos(math.radians(theta1)) * radius,
                center[1] + math.sin(math.radians(theta1)) * radius,
                math.radians(theta1 - 90)
            )

        elif mode == 'r':
            # print('right, reverse')
            center = (
                cur_pos[0] + math.cos(cur_pos[2] - math.pi / 2.0) * radius,
                cur_pos[1] + math.sin(cur_pos[2] - math.pi / 2.0) * radius,
            )
            circumference = math.pi * radius
            theta1 = math.degrees(cur_pos[2]) + 90
            theta2 = theta1 + (180 * length / circumference)

            parts = split_arc(center, theta1, theta2, radius, MAX_CURVE_ANGLE, 'r')

            new_pos = (
                center[0] + math.cos(math.radians(theta1)) * radius,
                center[1] + math.sin(math.radians(theta1)) * radius,
                math.radians(theta1 - 90)
            )

        elif mode == 'S':
            # print('straight')
            new_pos = (
                cur_pos[0] + math.cos(cur_pos[2]) * length,
                cur_pos[1] + math.sin(cur_pos[2]) * length,
                cur_pos[2],
            )

            parts = split_line(cur_pos[0], cur_pos[1], new_pos[0], new_pos[1], MAX_LINE_DISTANCE)
            # for part in parts:
            #     PROJECTIONS.append(part)

        else:
            print("[ERROR][DUBINS-ROUTE] Unknown mode: %s" % mode)

        cur_pos = new_pos
        projection_points.extend(parts)
    return projection_points


def general_planner(planner, alpha, beta, d):
    """
    This function calculates the best solution or best path to go from source to destination.
    """
    sa = math.sin(alpha)
    sb = math.sin(beta)
    ca = math.cos(alpha)
    cb = math.cos(beta)
    c_ab = math.cos(alpha - beta)
    mode = list(planner)

    planner_uc = planner.upper()

    if planner_uc == 'LSL':
        tmp0 = d + sa - sb
        p_squared = 2 + (d * d) - (2 * c_ab) + (2 * d * (sa - sb))
        if p_squared < 0:
            return None
        tmp1 = math.atan2((cb - ca), tmp0)
        t = mod2pi(-alpha + tmp1)
        p = math.sqrt(p_squared)
        q = mod2pi(beta - tmp1)

    elif planner_uc == 'RSR':
        tmp0 = d - sa + sb
        p_squared = 2 + (d * d) - (2 * c_ab) + (2 * d * (sb - sa))
        if p_squared < 0:
            return None
        tmp1 = math.atan2((ca - cb), tmp0)
        t = mod2pi(alpha - tmp1)
        p = math.sqrt(p_squared)
        q = mod2pi(-beta + tmp1)

    elif planner_uc == 'LSR':
        p_squared = -2 + (d * d) + (2 * c_ab) + (2 * d * (sa + sb))
        if p_squared < 0:
            return None
        p = math.sqrt(p_squared)
        tmp2 = math.atan2((-ca - cb), (d + sa + sb)) - math.atan2(-2.0, p)
        t = mod2pi(-alpha + tmp2)
        q = mod2pi(-mod2pi(beta) + tmp2)

    elif planner_uc == 'RSL':
        p_squared = (d * d) - 2 + (2 * c_ab) - (2 * d * (sa + sb))
        if p_squared < 0:
            return None
        p = math.sqrt(p_squared)
        tmp2 = math.atan2((ca + cb), (d - sa - sb)) - math.atan2(2.0, p)
        t = mod2pi(alpha - tmp2)
        q = mod2pi(beta - tmp2)

    elif planner_uc == 'RLR':
        tmp_rlr = (6.0 - d * d + 2.0 * c_ab + 2.0 * d * (sa - sb)) / 8.0
        if abs(tmp_rlr) > 1.0:
            return None

        p = mod2pi(2 * math.pi - math.acos(tmp_rlr))
        t = mod2pi(alpha - math.atan2(ca - cb, d - sa + sb) + mod2pi(p / 2.0))
        q = mod2pi(alpha - beta - t + mod2pi(p))

    elif planner_uc == 'LRL':
        tmp_lrl = (6. - d * d + 2 * c_ab + 2 * d * (- sa + sb)) / 8.
        if abs(tmp_lrl) > 1:
            return None
        p = mod2pi(2 * math.pi - math.acos(tmp_lrl))
        t = mod2pi(-alpha - math.atan2(ca - cb, d + sa - sb) + p / 2.)
        q = mod2pi(mod2pi(beta) - alpha - t + mod2pi(p))

    else:
        print("[ERROR][DUBINS-ROUTE] bad planner: ", planner)

    path = [t, p, q]

    # Lowercase directions are driven in reverse.
    for i in [0, 2]:
        if planner[i].islower():
            path[i] = (2 * math.pi) - path[i]
    # This will screw up whatever is in the middle.

    cost = sum(map(abs, path))

    return path, mode, cost


def dubins_path(start, end, radius):
    """
    Main entry function which find the path using dubins algorithm.
    :param start:start/first point
    :type start:tuple
    :param end:end/second point
    :type end:tuple
    :param radius:Turing radius
    :type radius:float
    :return:best mode and some parameter which is used later in this algorithm
    """
    (s_x, s_y, s_yaw) = start
    (e_x, e_y, e_yaw) = end
    c = radius

    e_x = e_x - s_x
    e_y = e_y - s_y

    lex = math.cos(s_yaw) * e_x + math.sin(s_yaw) * e_y
    ley = - math.sin(s_yaw) * e_x + math.cos(s_yaw) * e_y
    leyaw = e_yaw - s_yaw
    D = math.sqrt(lex ** 2.0 + ley ** 2.0)
    d = D / c

    theta = mod2pi(math.atan2(ley, lex))
    alpha = mod2pi(- theta)
    beta = mod2pi(leyaw - theta)

    # planners = ['RSr', 'rSR', 'rSr', 'LSL', 'RSR', 'LSR', 'RSL', 'RLR', 'LRL']
    planners = ['LSL', 'RSR', 'LSR', 'RSL', 'RLR', 'LRL']

    b_cost = float("inf")
    bt, bp, bq, b_mode = None, None, None, None

    for planner in planners:
        solution = general_planner(planner, alpha, beta, d)

        if solution is None:
            continue

        (path, mode, cost) = solution
        (t, p, q) = path
        if b_cost > cost:
            # best cost
            bt, bp, bq, b_mode = t, p, q, mode
            b_cost = cost

    return b_mode, [bt * c, bp * c, bq * c], [c] * 3


def get_curve(s_x, s_y, s_head, e_x, e_y, e_head, radius, max_line_distance):
    """
    Function calculates the curve path between two points.
    :param s_x:X-coordinate of first point
    :type s_x:float
    :param s_y:X-coordinate of first point
    :type s_y:float
    :param s_head:
    :type s_head:float
    :param e_x:X-coordinate of second point
    :type e_x:float
    :param e_y:X-coordinate of second point
    :type e_y:float
    :param e_head:
    :type e_head:float
    :param radius:turning radius of a vehicle
    :type radius:float
    :param max_line_distance:distance between two consecutive points in projection point list
    :type max_line_distance:float
    :return:None
    """
    global MAX_LINE_DISTANCE, MAX_CURVE_DISTANCE, MAX_CURVE_ANGLE
    MAX_LINE_DISTANCE = max_line_distance
    MAX_CURVE_DISTANCE = MAX_LINE_DISTANCE
    MAX_CURVE_ANGLE = (MAX_CURVE_DISTANCE * 360) / (2 * math.pi * (float(radius)))

    start = (s_x, s_y, math.radians(s_head))
    end = (e_x, e_y, math.radians(e_head))

    # Calculate the best solution or path to go from source to destination.
    solution = dubins_path(start=start, end=end, radius=radius)

    # Get the projected points of the calculated path.
    projection = get_projection(start=start, end=end, solution=solution)
    return projection

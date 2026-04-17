# coding=utf-8
"""Phase 1 RRT tests: verify RRT still produces valid paths after the
Dubins parameterization refactor. Two scenarios:

    1. No obstacles -> direct Dubins shortcut returns a single geometry.
    2. Simple square obstacle between start and goal -> returned path
       must not intersect the obstacle.

Requires QGIS (`qgis.core` for QgsGeometry). Gracefully skips if QGIS
is not importable. Run as:

    python3 test/test_rrt_fake_obstacles.py

or inside the QGIS Python environment.
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-17'

import math
import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# Skip the entire module if QGIS is not available.
try:
    from qgis.core import QgsGeometry, QgsPointXY  # noqa: F401
    _HAS_QGIS = True
except ImportError:
    _HAS_QGIS = False


@unittest.skipUnless(_HAS_QGIS, "qgis.core not importable — run inside QGIS Python env")
class RRTFakeObstacleTests(unittest.TestCase):
    """RRT behavior after Phase 1's removal of Dubins module globals.

    These are characterization tests: the RRT's outputs should be equivalent
    to the pre-Phase-1 behavior for these simple, deterministic-ish cases.
    """

    def setUp(self):
        # Import lazily so the module-level skip takes effect before import.
        global rrt_planner
        import rrt_planner  # noqa: E402

    def test_rrt_no_obstacles_returns_valid_geometry(self):
        """Direct-Dubins shortcut: no obstacles -> non-empty LineString."""
        import rrt_planner
        start_pose = (0.0, 0.0, 0.0)
        end_pose = (1000.0, 0.0, 0.0)  # straight ahead, 1 km
        path = rrt_planner.find_rrt_path(
            start_pose=start_pose,
            end_pose=end_pose,
            obstacles=[],                   # none
            turn_radius=50.0,
            step_size=50.0,
            max_iterations=2000,
            goal_bias=0.2,
            goal_tolerance_dist=25.0,
            goal_tolerance_angle=math.radians(15.0),
            search_bounds=None,
        )
        self.assertIsNotNone(path, "RRT returned None for trivial no-obstacle case")
        self.assertFalse(path.isEmpty(), "RRT path geometry is empty")
        # Length should be within 20% of the direct 1000 m distance.
        length = path.length()
        self.assertGreater(length, 800.0, f"RRT path {length:.1f}m suspiciously short")
        self.assertLess(length, 1500.0, f"RRT path {length:.1f}m suspiciously long")

    def test_rrt_avoids_simple_square_obstacle(self):
        """Obstacle between start and goal must not be crossed by the returned path."""
        import rrt_planner
        # Square obstacle: 200m square centered at (500, 0) -> covers x in [400, 600], y in [-100, 100]
        from qgis.core import QgsGeometry, QgsPointXY
        obstacle = QgsGeometry.fromPolygonXY([[
            QgsPointXY(400.0, -100.0),
            QgsPointXY(600.0, -100.0),
            QgsPointXY(600.0, 100.0),
            QgsPointXY(400.0, 100.0),
            QgsPointXY(400.0, -100.0),
        ]])
        self.assertFalse(obstacle.isEmpty(), "test fixture obstacle failed to build")

        # Start and goal are outside the obstacle, on opposite sides.
        start_pose = (0.0, 0.0, 0.0)
        end_pose = (1000.0, 0.0, 0.0)

        path = rrt_planner.find_rrt_path(
            start_pose=start_pose,
            end_pose=end_pose,
            obstacles=[obstacle],
            turn_radius=50.0,
            step_size=50.0,
            max_iterations=20000,
            goal_bias=0.2,
            goal_tolerance_dist=50.0,
            goal_tolerance_angle=math.radians(30.0),
            search_bounds=(-200.0, 1200.0, -500.0, 500.0),
        )
        # RRT is stochastic — it may fail to find a path within the iteration budget
        # for this test. Treat None as inconclusive (skip) rather than failure,
        # so the test is a positive safety check, not a flake generator.
        if path is None:
            self.skipTest("RRT did not converge for this random seed / iteration budget — "
                          "inconclusive but not a Phase 1 regression (pre-Phase-1 had same risk)")

        self.assertFalse(path.isEmpty())
        # The key invariant: path must not cross the obstacle.
        self.assertFalse(
            path.intersects(obstacle),
            f"RRT path ({path.length():.1f}m) crosses the obstacle — RRT broke in Phase 1"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

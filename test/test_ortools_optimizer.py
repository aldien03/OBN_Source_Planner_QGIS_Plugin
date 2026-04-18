# coding=utf-8
"""Phase 13a tests for services/ortools_optimizer.py.

Pure Python — no QGIS, no Qt. Tests are skipped automatically when
ortools is not installed, so the existing test suite keeps working
on machines without the dependency.

    python3 test/test_ortools_optimizer.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-18'

import os
import sys
import time
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.ortools_optimizer import (  # noqa: E402
    optimize_with_ortools,
    is_ortools_available,
    NodeMeta,
    OrToolsProgress,
    INFEASIBLE_ARC_COST,
)
from services.sequence_service import OptimizationResult  # noqa: E402


_ORTOOLS_REQUIRED = "ortools not installed; skipping OR-tools tests"


# --- Problem builders --------------------------------------------------------

def _build_simple_asymmetric_problem(num_lines, forward_cheaper=True):
    """Build a canonical problem: `num_lines` survey lines, 2 directions each,
    asymmetric costs.

    Returns (cost_matrix, node_meta, disjunction_pairs).

    Node layout:
      node 0          -> depot
      node 2k-1       -> line k forward     (k = 1..num_lines)
      node 2k         -> line k reciprocal
    """
    num_nodes = 1 + 2 * num_lines  # depot + 2 per line
    node_meta = [NodeMeta(line_num=None, is_reciprocal=False, is_depot=True)]
    for k in range(1, num_lines + 1):
        node_meta.append(NodeMeta(line_num=k, is_reciprocal=False))
        node_meta.append(NodeMeta(line_num=k, is_reciprocal=True))

    disjunction_pairs = [(2 * k - 1, 2 * k) for k in range(1, num_lines + 1)]

    cost_matrix = {}
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i == j:
                continue
            if i == 0 or j == 0:
                # depot arcs — cheap / free to encourage depot at the ends
                cost_matrix[(i, j)] = 1.0 if j != 0 else 0.0
            else:
                # line-to-line: forward→forward is cheap, reciprocal→
                # reciprocal is expensive (to exercise asymmetry)
                i_is_fwd = (i % 2 == 1)
                j_is_fwd = (j % 2 == 1)
                if forward_cheaper:
                    cost_matrix[(i, j)] = 10.0 if (i_is_fwd and j_is_fwd) else 100.0
                else:
                    cost_matrix[(i, j)] = 100.0 if (i_is_fwd and j_is_fwd) else 10.0
    return cost_matrix, node_meta, disjunction_pairs


# --- Tests --------------------------------------------------------------


class OrtoolsAvailabilityTests(unittest.TestCase):
    """Meta-tests that must run regardless of ortools availability."""

    def test_module_imports_without_ortools(self):
        """The module must load even when ortools is absent — the import
        check / scaffolding paths need to work on un-set-up machines."""
        # Already imported at top of file; if import fails the whole
        # module fails to load and this test never runs. That's fine —
        # the unittest runner reports the import failure separately.
        self.assertTrue(hasattr(optimize_with_ortools, "__call__"))
        self.assertTrue(callable(is_ortools_available))

    def test_is_ortools_available_returns_bool(self):
        self.assertIsInstance(is_ortools_available(), bool)

    def test_optimize_raises_clear_error_when_ortools_missing(self):
        """If ortools is genuinely missing, the ImportError must carry
        the install hint the dockwidget will show to the user."""
        if is_ortools_available():
            self.skipTest("ortools IS available — cannot exercise the missing-dep path")
        try:
            optimize_with_ortools(
                cost_matrix={(0, 1): 1.0, (1, 0): 0.0},
                node_meta=[
                    NodeMeta(line_num=None, is_reciprocal=False, is_depot=True),
                    NodeMeta(line_num=1, is_reciprocal=False),
                ],
                disjunction_pairs=[(1, 1)],
            )
        except ImportError as e:
            self.assertIn("pip install ortools", str(e))
            return
        self.fail("expected ImportError")


@unittest.skipUnless(is_ortools_available(), _ORTOOLS_REQUIRED)
class OrtoolsSolveTests(unittest.TestCase):
    """Core solver behavior. Only runs when ortools is installed."""

    def test_returns_optimization_result_shape(self):
        cost, meta, pairs = _build_simple_asymmetric_problem(3)
        result = optimize_with_ortools(cost, meta, pairs, time_limit_s=2)
        self.assertIsInstance(result, OptimizationResult)
        self.assertEqual(len(result.optimized_sequence), 3)  # 3 lines visited
        self.assertGreater(result.final_cost, 0)
        self.assertIn(result.stopped_reason, ("converged", "time_limit"))

    def test_disjunction_respected_exactly_one_direction_per_line(self):
        """For each line, exactly one of its two direction-nodes must
        be visited (the disjunction guarantee)."""
        cost, meta, pairs = _build_simple_asymmetric_problem(4)
        result = optimize_with_ortools(cost, meta, pairs, time_limit_s=2)
        visited_lines = set()
        for node_idx in result.optimized_sequence:
            m = meta[node_idx]
            self.assertFalse(m.is_depot, "depot must not appear in visited sequence")
            self.assertNotIn(
                m.line_num, visited_lines,
                f"line {m.line_num} visited twice — disjunction violated",
            )
            visited_lines.add(m.line_num)
        # All lines must be visited
        self.assertEqual(visited_lines, {1, 2, 3, 4})

    def test_asymmetric_cost_respected_prefers_forward(self):
        """Forward arcs cost 10, reverse arcs cost 100 — solver must
        pick forward-direction nodes for every line."""
        cost, meta, pairs = _build_simple_asymmetric_problem(5, forward_cheaper=True)
        result = optimize_with_ortools(cost, meta, pairs, time_limit_s=3)
        for node_idx in result.optimized_sequence:
            m = meta[node_idx]
            self.assertFalse(
                m.is_reciprocal,
                f"line {m.line_num}: solver picked reciprocal despite forward being cheaper",
            )

    def test_asymmetric_cost_respected_prefers_reciprocal(self):
        """Mirror of the above — when reciprocal is cheaper, solver
        must pick it."""
        cost, meta, pairs = _build_simple_asymmetric_problem(5, forward_cheaper=False)
        result = optimize_with_ortools(cost, meta, pairs, time_limit_s=3)
        for node_idx in result.optimized_sequence:
            m = meta[node_idx]
            self.assertTrue(
                m.is_reciprocal,
                f"line {m.line_num}: solver picked forward despite reciprocal being cheaper",
            )

    def test_pinned_first_node_respected(self):
        cost, meta, pairs = _build_simple_asymmetric_problem(4)
        # Pin line 3's forward direction (node index 5 = 2*3 - 1)
        pinned = 5
        result = optimize_with_ortools(
            cost, meta, pairs, time_limit_s=2, pinned_first_node=pinned
        )
        self.assertEqual(
            result.optimized_sequence[0], pinned,
            f"first visit should be pinned node {pinned}, got {result.optimized_sequence[0]}",
        )

    def test_time_limit_respected(self):
        """A 1-second time limit on a small problem should complete in
        well under 5s (1s solve + model build + solver overhead)."""
        cost, meta, pairs = _build_simple_asymmetric_problem(5)
        t0 = time.time()
        optimize_with_ortools(cost, meta, pairs, time_limit_s=1)
        wall = time.time() - t0
        self.assertLess(
            wall, 5.0,
            f"solve took {wall:.2f}s with time_limit=1s — solver ignoring limit?",
        )

    def test_infeasible_arc_avoided(self):
        """Arcs with INFEASIBLE_ARC_COST must be avoided if any feasible
        alternative exists."""
        cost, meta, pairs = _build_simple_asymmetric_problem(3)
        # Make the forward→forward arc from line1 to line2 infeasible.
        # Solver should route via reciprocal nodes instead.
        cost[(1, 3)] = INFEASIBLE_ARC_COST  # 1 = line1 fwd, 3 = line2 fwd
        cost[(3, 1)] = INFEASIBLE_ARC_COST  # symmetric — disable both dirs
        result = optimize_with_ortools(cost, meta, pairs, time_limit_s=3)
        # Verify no infeasible arc appears in the chosen tour
        prev_node = 0  # start at depot
        for node in result.optimized_sequence:
            arc_cost = cost.get((prev_node, node))
            self.assertLess(
                arc_cost, INFEASIBLE_ARC_COST,
                f"tour uses infeasible arc ({prev_node}, {node}) with cost {arc_cost}",
            )
            prev_node = node

    def test_rejects_missing_depot(self):
        """node_meta[0] must be the depot; other layouts must raise."""
        cost, meta, pairs = _build_simple_asymmetric_problem(2)
        bad_meta = [
            NodeMeta(line_num=1, is_reciprocal=False),  # NOT depot
            NodeMeta(line_num=1, is_reciprocal=True),
            NodeMeta(line_num=2, is_reciprocal=False),
            NodeMeta(line_num=2, is_reciprocal=True),
            NodeMeta(line_num=None, is_reciprocal=False, is_depot=True),
        ]
        with self.assertRaises(ValueError):
            optimize_with_ortools(cost, bad_meta, pairs, time_limit_s=1)

    def test_rejects_bad_metaheuristic(self):
        cost, meta, pairs = _build_simple_asymmetric_problem(2)
        with self.assertRaises(ValueError):
            optimize_with_ortools(
                cost, meta, pairs, time_limit_s=1,
                metaheuristic="NOT_A_REAL_ALGORITHM",
            )

    def test_rejects_nonpositive_time_limit(self):
        cost, meta, pairs = _build_simple_asymmetric_problem(2)
        with self.assertRaises(ValueError):
            optimize_with_ortools(cost, meta, pairs, time_limit_s=0)


if __name__ == "__main__":
    unittest.main()

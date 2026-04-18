# coding=utf-8
"""Phase 11a 2-opt local search tests — pure Python, no QGIS.

Uses canned cost functions (dict lookup, or callable closures) so the
optimizer's behavior can be verified without involving Dubins or QGIS.

    python3 test/test_sequence_optimization.py
"""

__author__ = 'aldien03@gmail.com'
__date__ = '2026-04-18'

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

from services.sequence_service import (  # noqa: E402
    optimize_sequence_2opt,
    OptimizationResult,
)


# --- Cost function builders -------------------------------------------------

def _make_call_counter(cost_fn):
    """Wrap a cost_fn to count calls. Returns (wrapped, counter_attr)."""
    counter = {"n": 0}

    def wrapped(seq):
        counter["n"] += 1
        return cost_fn(seq)

    wrapped.counter = counter
    return wrapped


def _edge_sum_cost(edge_weights):
    """Build a cost_fn that sums 'edge weights' for the sequence.

    edge_weights: dict[(from, to)] -> float. Asymmetric allowed —
    (a, b) and (b, a) can differ, mimicking Dubins turn asymmetry.
    Missing edges contribute a large penalty so the optimizer prefers
    sequences whose consecutive pairs are all in the dict.
    """
    BIG = 1e9

    def cost_fn(seq):
        total = 0.0
        for i in range(len(seq) - 1):
            w = edge_weights.get((seq[i], seq[i + 1]), BIG)
            total += w
        return total

    return cost_fn


# --- Trivial-input behavior -------------------------------------------------

class TrivialInputTests(unittest.TestCase):
    """Sequences of length < 4 admit no 2-opt moves."""

    def test_empty_sequence(self):
        res = optimize_sequence_2opt([], lambda s: 0.0)
        self.assertEqual(res.optimized_sequence, [])
        self.assertEqual(res.stopped_reason, "trivial")
        self.assertEqual(res.total_passes, 0)
        self.assertEqual(res.total_improvements, 0)
        self.assertEqual(res.cost_evaluations, 0,
                         "empty input should not invoke cost_fn at all")

    def test_single_element_sequence(self):
        cost_fn = _make_call_counter(lambda s: 42.0)
        res = optimize_sequence_2opt([1000], cost_fn)
        self.assertEqual(res.optimized_sequence, [1000])
        self.assertEqual(res.stopped_reason, "trivial")
        self.assertEqual(res.original_cost, 42.0)
        self.assertEqual(res.final_cost, 42.0)
        self.assertEqual(cost_fn.counter["n"], 1,
                         "should evaluate input once to report its cost, but "
                         "never attempt any swaps")

    def test_two_element_sequence(self):
        cost_fn = _make_call_counter(lambda s: 10.0)
        res = optimize_sequence_2opt([1000, 1006], cost_fn)
        self.assertEqual(res.optimized_sequence, [1000, 1006])
        self.assertEqual(res.stopped_reason, "trivial")
        self.assertEqual(cost_fn.counter["n"], 1)

    def test_three_element_sequence_no_moves(self):
        """Length 3: the only 'swap' would move one element — not a valid
        2-opt edge reversal. Returns as-is."""
        cost_fn = _make_call_counter(lambda s: 99.0)
        res = optimize_sequence_2opt([1000, 1006, 1012], cost_fn)
        self.assertEqual(res.optimized_sequence, [1000, 1006, 1012])
        self.assertEqual(res.stopped_reason, "trivial")
        self.assertEqual(cost_fn.counter["n"], 1)


# --- Returns-new-list contract ----------------------------------------------

class DoesNotMutateInputTests(unittest.TestCase):
    """optimize_sequence_2opt must not mutate caller's list."""

    def test_input_list_unchanged(self):
        original = [1000, 1006, 1012, 1018, 1024]
        snapshot = list(original)
        optimize_sequence_2opt(original, lambda s: 0.0)
        self.assertEqual(original, snapshot,
                         "caller's list must not be mutated")

    def test_returned_list_is_new_object(self):
        original = [1000, 1006, 1012, 1018]
        res = optimize_sequence_2opt(original, lambda s: 0.0)
        # Even when no swaps happen (cost is constant), the returned list
        # must be a different object so the caller can safely mutate it.
        self.assertIsNot(res.optimized_sequence, original)


# --- No-improvement scenarios -----------------------------------------------

class NoImprovementTests(unittest.TestCase):
    """When no swap can reduce cost, return the original sequence."""

    def test_constant_cost_no_swaps_accepted(self):
        """cost_fn returns the same value regardless of sequence order.
        2-opt should make exactly one pass, find no improvement, stop."""
        original = [1000, 1006, 1012, 1018, 1024]
        call_count = _make_call_counter(lambda s: 100.0)
        res = optimize_sequence_2opt(original, call_count, max_iterations=10)
        self.assertEqual(res.optimized_sequence, original)
        self.assertEqual(res.final_cost, 100.0)
        self.assertEqual(res.improvement_pct, 0.0)
        self.assertEqual(res.total_improvements, 0)
        self.assertEqual(res.stopped_reason, "converged")
        self.assertEqual(res.total_passes, 1,
                         "converged after one full pass with no improvement")

    def test_cost_strictly_monotonic_in_position_returns_original(self):
        """When the input is already optimal (sorted matches minimum),
        2-opt must not worsen it."""
        edges = {
            (1, 2): 1.0, (2, 3): 1.0, (3, 4): 1.0, (4, 5): 1.0,
            # Any out-of-order edge is expensive
            (1, 3): 10.0, (1, 4): 10.0, (1, 5): 10.0,
            (2, 1): 10.0, (2, 4): 10.0, (2, 5): 10.0,
            (3, 1): 10.0, (3, 2): 10.0, (3, 5): 10.0,
            (4, 1): 10.0, (4, 2): 10.0, (4, 3): 10.0,
            (5, 1): 10.0, (5, 2): 10.0, (5, 3): 10.0, (5, 4): 10.0,
        }
        res = optimize_sequence_2opt([1, 2, 3, 4, 5], _edge_sum_cost(edges))
        self.assertEqual(res.optimized_sequence, [1, 2, 3, 4, 5])
        self.assertEqual(res.final_cost, 4.0,
                         "1->2->3->4->5 = 4 cheap edges = 4.0")
        self.assertEqual(res.total_improvements, 0)


# --- Strict-improvement scenarios -------------------------------------------

class ImprovementTests(unittest.TestCase):
    """2-opt must find a provably better sequence when one exists."""

    def test_reversed_input_improves_first_element_fixed(self):
        """Input is reverse-sorted, cheap edges only on ascending adjacencies.

        IMPORTANT: 2-opt on an OPEN PATH cannot change the first vertex
        (all reversals are of sub-segments starting at index i+1 where
        i >= 0). So from [5,4,3,2,1] we cannot reach [1,2,3,4,5] — the
        first element stays 5. The global minimum REACHABLE from this
        start is [5,1,2,3,4] with cost 100 (expensive first edge) + 1+1+1
        (ascending cheap edges) = 103.
        """
        edges = {}
        for a, b in [(1, 2), (2, 3), (3, 4), (4, 5)]:
            edges[(a, b)] = 1.0
        for a in [1, 2, 3, 4, 5]:
            for b in [1, 2, 3, 4, 5]:
                if a != b and (a, b) not in edges:
                    edges[(a, b)] = 100.0
        cost_fn = _edge_sum_cost(edges)

        res = optimize_sequence_2opt([5, 4, 3, 2, 1], cost_fn)
        self.assertEqual(res.optimized_sequence, [5, 1, 2, 3, 4],
                         "optimal sequence reachable from [5,...] is [5,1,2,3,4]")
        self.assertEqual(res.final_cost, 103.0)
        self.assertLess(res.final_cost, res.original_cost)
        self.assertGreater(res.improvement_pct, 0)
        self.assertGreaterEqual(res.total_improvements, 1)
        self.assertEqual(res.optimized_sequence[0], 5,
                         "2-opt on open path preserves first vertex")

    def test_single_misplaced_element_gets_swapped(self):
        """One element is clearly out of place; 2-opt should fix it."""
        # Optimal order is 1,2,3,4,5 but input has 4 before 2 (they're swapped)
        edges = {}
        for a, b in [(1, 2), (2, 3), (3, 4), (4, 5)]:
            edges[(a, b)] = 1.0
        for a in [1, 2, 3, 4, 5]:
            for b in [1, 2, 3, 4, 5]:
                if a != b and (a, b) not in edges:
                    edges[(a, b)] = 50.0
        cost_fn = _edge_sum_cost(edges)

        res = optimize_sequence_2opt([1, 4, 3, 2, 5], cost_fn)
        # The optimizer might find [1, 2, 3, 4, 5] (cost 4) or another
        # equal-cost configuration. Must strictly improve over input.
        self.assertLess(res.final_cost, res.original_cost)
        self.assertEqual(res.final_cost, 4.0,
                         "optimal cost is 4 (1->2->3->4->5 = 4 cheap edges)")

    def test_asymmetric_costs_respected(self):
        """(a,b) != (b,a). 2-opt should pick the cheaper direction among
        what's REACHABLE from a given start (first element is fixed)."""
        # Cheap forward path; expensive reverse direction; other pairs medium.
        edges = {
            (10, 20): 1.0, (20, 30): 1.0, (30, 40): 1.0,
            (40, 30): 100.0, (30, 20): 100.0, (20, 10): 100.0,
        }
        for a in [10, 20, 30, 40]:
            for b in [10, 20, 30, 40]:
                if a != b and (a, b) not in edges:
                    edges[(a, b)] = 20.0
        cost_fn = _edge_sum_cost(edges)

        res = optimize_sequence_2opt([40, 30, 20, 10], cost_fn)
        # Original cost: (40,30)+(30,20)+(20,10) = 100+100+100 = 300
        # First element pinned at 40. Global-min reachable is [40,10,20,30]
        # with cost (40,10)+(10,20)+(20,30) = 20+1+1 = 22.
        self.assertEqual(res.optimized_sequence, [40, 10, 20, 30],
                         "optimal path from [40,...] is 40 -> 10 -> 20 -> 30 "
                         "(one medium edge to enter the ascending chain)")
        self.assertAlmostEqual(res.final_cost, 22.0, places=6)
        self.assertAlmostEqual(res.original_cost, 300.0, places=6)
        self.assertEqual(res.optimized_sequence[0], 40,
                         "2-opt preserves first vertex")


# --- Iteration budget -------------------------------------------------------

class IterationLimitTests(unittest.TestCase):
    def test_max_iterations_respected(self):
        """If max_iterations=1 and more passes would help, we stop anyway."""
        # Construct a problem that needs multiple passes to fully optimize.
        # Cheap edges only on specific non-trivial pattern.
        edges = {
            (1, 2): 1.0, (2, 3): 1.0, (3, 4): 1.0, (4, 5): 1.0, (5, 6): 1.0,
        }
        for a in range(1, 7):
            for b in range(1, 7):
                if a != b and (a, b) not in edges:
                    edges[(a, b)] = 50.0
        cost_fn = _edge_sum_cost(edges)

        # Start from a reversed sequence. With max_iterations=1, we get one
        # pass of improvements; may or may not reach full optimum in one pass,
        # but stopped_reason must reflect the cap if we hit it.
        res = optimize_sequence_2opt([6, 5, 4, 3, 2, 1], cost_fn, max_iterations=1)
        self.assertEqual(res.total_passes, 1)
        # Either converged on pass 1 or hit the cap — both are valid. The
        # test is that we STOPPED, and total_passes didn't exceed cap.
        self.assertIn(res.stopped_reason, ("converged", "max_iterations"))

    def test_max_iterations_zero_returns_input_untouched(self):
        original = [1, 2, 3, 4, 5]
        # max_iterations=0 → while loop body never runs → return as-is with
        # stopped_reason 'max_iterations' (the else branch triggered).
        res = optimize_sequence_2opt(original, lambda s: 100.0, max_iterations=0)
        self.assertEqual(res.optimized_sequence, original)
        self.assertEqual(res.total_passes, 0)
        self.assertEqual(res.total_improvements, 0)
        self.assertEqual(res.stopped_reason, "max_iterations")


# --- Determinism ------------------------------------------------------------

class DeterminismTests(unittest.TestCase):
    """Two runs with the same inputs must produce identical results."""

    def test_same_input_same_output(self):
        # Non-trivial case where many swaps matter
        edges = {(a, b): abs(a - b) * 1.0 for a in range(10) for b in range(10) if a != b}
        cost_fn = _edge_sum_cost(edges)
        seq = [3, 7, 1, 9, 4, 6, 0, 8, 2, 5]

        res1 = optimize_sequence_2opt(seq, cost_fn)
        res2 = optimize_sequence_2opt(seq, cost_fn)

        self.assertEqual(res1.optimized_sequence, res2.optimized_sequence)
        self.assertEqual(res1.final_cost, res2.final_cost)
        self.assertEqual(res1.total_passes, res2.total_passes)
        self.assertEqual(res1.total_improvements, res2.total_improvements)


# --- Result-dataclass shape -------------------------------------------------

class OptimizationResultShapeTests(unittest.TestCase):
    def test_improvement_pct_calculation(self):
        """improvement_pct = (original - final) / original * 100."""
        # Force a known improvement
        edges = {(1, 2): 1.0, (2, 3): 1.0, (3, 1): 100.0, (2, 1): 100.0,
                 (3, 2): 100.0, (1, 3): 100.0}
        cost_fn = _edge_sum_cost(edges)
        # Length-3 won't swap (trivial) — need length-4
        # Add a 4th element with its edges
        edges.update({
            (1, 4): 1.0, (4, 3): 100.0, (3, 4): 1.0, (4, 1): 100.0,
            (2, 4): 100.0, (4, 2): 100.0,
        })
        cost_fn = _edge_sum_cost(edges)
        res = optimize_sequence_2opt([1, 4, 3, 2], cost_fn)
        # Check improvement_pct math is consistent
        if res.original_cost > 0:
            expected_pct = (res.original_cost - res.final_cost) / res.original_cost * 100.0
            self.assertAlmostEqual(res.improvement_pct, expected_pct, places=6)

    def test_result_dataclass_is_frozen(self):
        """Cannot accidentally mutate after return."""
        res = optimize_sequence_2opt([], lambda s: 0.0)
        with self.assertRaises(Exception):  # FrozenInstanceError (dataclass)
            res.final_cost = 999.0

    def test_zero_original_cost_gives_zero_improvement_pct(self):
        """Avoid division by zero when original cost is 0 (degenerate but legal)."""
        res = optimize_sequence_2opt([1, 2, 3, 4, 5], lambda s: 0.0)
        self.assertEqual(res.improvement_pct, 0.0)


# --- Smoke test on realistic-shaped input -----------------------------------

class RealisticShapeTests(unittest.TestCase):
    """Mimic the Martin Linge scenario: ~20 lines, asymmetric turn costs.
    Not a correctness test — just verifies the algorithm runs to completion
    in reasonable time."""

    def test_20_lines_completes(self):
        # 20 lines spaced by 6, edges priced by |delta| (wider jumps cost more)
        lines = list(range(1000, 1120, 6))  # 20 lines
        edges = {}
        for a in lines:
            for b in lines:
                if a != b:
                    edges[(a, b)] = abs(a - b)
        cost_fn = _edge_sum_cost(edges)

        # Start from a suboptimal order: reverse + inject some wrong indices
        seq = list(reversed(lines[:10])) + lines[10:]
        res = optimize_sequence_2opt(seq, cost_fn, max_iterations=50)

        # Should have improved SOMETHING
        self.assertLessEqual(res.final_cost, res.original_cost)
        # Must not exceed cap
        self.assertLessEqual(res.total_passes, 50)
        # Output is a permutation of input
        self.assertEqual(sorted(res.optimized_sequence), sorted(seq))


if __name__ == "__main__":
    unittest.main(verbosity=2)

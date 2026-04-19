"""
OR-tools based sequence optimizer.

Pure Python — no Qt, no QGIS. Caller must have ortools installed
(`pip install ortools` in the OSGeo4W Shell on Windows). The module
itself imports without ortools; calling optimize_with_ortools without
the dependency raises ImportError with the install hint.

Phase 13a scaffolding. The UI integration and QThread worker
(Phase 13b) are layered on top and are NOT in this module.

Problem formulation (docs/refactor/phase_13_ortools.md for the full
design doc):

- Each survey line has TWO possible shooting directions. To let the
  solver choose, each line becomes a pair of nodes: one for forward
  (low_to_high SP), one for reciprocal (high_to_low). A disjunction
  binds the pair so exactly one of the two is visited.

- Node 0 is a dummy depot. Arcs depot → any_line_node have the first
  line's acquisition + run-in cost. Arcs any_line_node → depot are
  zero (open-path TSP; depot is visited exactly twice — start + end).

- Turn cost (asymmetric Dubins) between lines is folded into arc cost
  along with the destination line's run-in + acquisition time.
  Keeps the routing model a pure min-cost problem with no Dimensions.

Returns the same OptimizationResult dataclass optimize_sequence_2opt
returns so callers can swap the two optimizers behind a dropdown.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

# Vendored ortools 9.14 lives in <plugin>/vendor to dodge the QGIS-numpy-1.26 vs ortools-9.15-numpy-2.x ABI conflict.
_VENDOR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

from .sequence_service import OptimizationResult

log = logging.getLogger(__name__)


# --- Constants ----------------------------------------------------------

# Cost of an "infeasible" arc. OR-tools must still find a complete tour;
# by setting the cost very high (but finite) the solver naturally avoids
# these arcs if any feasible alternative exists. 1e12 fits in int64 even
# when summed over thousands of arcs (int32 would overflow).
INFEASIBLE_ARC_COST = int(1e12)

# Cost of NOT visiting a line (disjunction drop penalty). Must exceed any
# realistic tour cost by a wide margin so the solver never drops a line
# when a feasible tour exists. 1e15 is comfortably larger than the
# INFEASIBLE_ARC_COST * N product for N up to ~1000 lines.
DROP_LINE_PENALTY = int(1e15)

# Multiplier for the float→int conversion of cost-matrix entries.
# OR-tools requires integer arc costs; we multiply by 1000 to preserve
# millisecond precision on time-in-seconds costs. 1000 * 1e6 = 1e9 total
# tour cost ceiling before int64 overflow risk — plenty of headroom for
# tours up to ~11 days (9.5e5 seconds) at 1e6 arcs.
FLOAT_TO_INT_SCALE = 1000


_VALID_METAHEURISTICS = (
    "GUIDED_LOCAL_SEARCH",
    "SIMULATED_ANNEALING",
    "TABU_SEARCH",
    "GENERIC_TABU_SEARCH",
    "AUTOMATIC",
)


# --- Public dataclasses -------------------------------------------------


@dataclass(frozen=True)
class NodeMeta:
    """Per-node metadata. Indexed by solver node number.

    Node 0 MUST be the depot (is_depot=True, line_num=None).
    Nodes 1..N MUST be line-direction alternates: for line k (1-indexed
    in the caller's node_meta list), the caller chooses the pairing
    (e.g. nodes 2k-1 and 2k) and passes the indices in
    `disjunction_pairs`.
    """
    line_num: Optional[int]     # None iff is_depot=True
    is_reciprocal: bool          # ignored when is_depot=True
    is_depot: bool = False


@dataclass(frozen=True)
class OrToolsProgress:
    """Emitted (in Phase 13b, via SearchMonitor hook) when the solver
    finds a new best solution. Phase 13a scaffolding accepts a
    progress_callback arg but does not yet fire it — the single-thread
    call blocks until the solve finishes. Kept in the signature so
    Phase 13b threading can wire it without breaking callers.
    """
    elapsed_s: float
    best_cost: float
    solutions_found: int


# --- Availability check -------------------------------------------------


def is_ortools_available() -> bool:
    """Return True iff ortools can be imported in the current env.

    Called by the dockwidget at plugin-init time to decide whether to
    enable the "OR-tools" dropdown option. Does NOT raise — just
    returns False when the dependency is missing.
    """
    try:
        import ortools  # noqa: F401
        return True
    except ImportError:
        return False


# --- Main entry point ---------------------------------------------------


def optimize_with_ortools(
    cost_matrix: Dict[Tuple[int, int], float],
    node_meta: List[NodeMeta],
    disjunction_pairs: List[Tuple[int, int]],
    time_limit_s: int = 30,
    pinned_first_node: Optional[int] = None,
    metaheuristic: str = "GUIDED_LOCAL_SEARCH",
    progress_callback: Optional[Callable[[OrToolsProgress], None]] = None,
    cancel_fn: Optional[Callable[[], bool]] = None,
    started_callback: Optional[Callable[[object], None]] = None,
) -> OptimizationResult:
    """Run the OR-tools routing solver on an asymmetric TSP with
    direction disjunctions.

    Args:
        cost_matrix: dict keyed by (from_node, to_node) -> float seconds.
            Must be DENSE — every (i, j) pair with i != j needs an entry.
            Arcs that are structurally infeasible should use
            INFEASIBLE_ARC_COST (not a missing entry).
        node_meta: list indexed by node number. Length = number of
            nodes in the model. Entry 0 must have is_depot=True.
        disjunction_pairs: list of (node_a, node_b) tuples, one per
            survey line whose direction is NOT pre-pinned. Each pair is
            wrapped in an AddDisjunction so the solver picks exactly one
            direction per line. May be empty — happens in 4D-monitor-
            survey mode where every line's direction is pre-pinned by
            its PREV_DIRECTION attribute, making the problem a plain
            asymmetric TSP with no direction choice.
        time_limit_s: hard wall-clock cap in seconds. OR-tools honors
            this via its internal clock; the returned solution is the
            best found by the deadline.
        pinned_first_node: if set, the solver is constrained so the
            first visit after the depot is exactly this node. Matches
            existing sim_params['first_line_num'] UX. None = solver
            chooses freely.
        metaheuristic: local-search meta-algorithm name. See
            _VALID_METAHEURISTICS. Default GUIDED_LOCAL_SEARCH.
        progress_callback: invoked each time the solver finds an improved
            solution (via AddAtSolutionCallback). Receives an OrToolsProgress
            with elapsed_s / best_cost / solutions_found. Fires from whatever
            thread SolveWithParameters is running on — the OrToolsTask worker
            in production.
        cancel_fn: reserved for Phase 13c. Phase 13b uses started_callback +
            external FinishCurrentSearch() call instead.
        started_callback: invoked once, immediately before SolveWithParameters,
            with the RoutingModel as its single argument. Lets the caller (e.g.
            OrToolsTask) obtain a handle on the live solver so it can call
            routing.solver().FinishCurrentSearch() from another thread to
            stop the solve early. SolveWithParameters then returns with the
            best-so-far assignment, which this function extracts normally.

    Returns:
        OptimizationResult with optimized_sequence containing the node
        indices visited in order (caller uses node_meta to map back to
        (line_num, direction) tuples). Depot is NOT included. If the
        solver finds no solution within time_limit, raises RuntimeError.

    Raises:
        ImportError: if ortools is not installed.
        ValueError: if inputs are malformed.
        RuntimeError: if the solver returns no solution within the time
            limit (rare — DROP_LINE_PENALTY is set large enough to
            prevent this except in genuinely infeasible problems).
    """
    # Lazy import: module must load without ortools so the Phase 13a
    # availability check + UI dropdown wiring works on machines that
    # haven't installed the dependency yet.
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError as e:
        raise ImportError(
            "OR-tools is not installed. To enable OR-tools optimization, "
            "run `pip install ortools` in the OSGeo4W Shell (Windows) or "
            "your QGIS Python environment, then restart QGIS."
        ) from e

    # --- Input validation ------------------------------------------------

    if not node_meta or not node_meta[0].is_depot:
        raise ValueError("node_meta[0] must be the depot (is_depot=True)")

    num_nodes = len(node_meta)
    if num_nodes < 3:
        raise ValueError(
            f"need at least 1 depot + 2 line-direction nodes "
            f"(i.e. 1 line); got {num_nodes} nodes total"
        )

    if metaheuristic not in _VALID_METAHEURISTICS:
        raise ValueError(
            f"metaheuristic must be one of {_VALID_METAHEURISTICS}, "
            f"got {metaheuristic!r}"
        )

    if time_limit_s <= 0:
        raise ValueError(f"time_limit_s must be positive, got {time_limit_s}")

    # Phase 13a hotfix: disjunction_pairs is allowed to be empty. That
    # happens in 4D-monitor-survey mode (follow_previous_direction=True):
    # each line's direction is pinned by its PREV_DIRECTION attribute, so
    # the caller creates ONE node per line — no pair to bind. OR-tools'
    # RoutingModel handles a plain asymmetric TSP (no disjunctions) fine.

    # --- Model construction ---------------------------------------------

    manager = pywrapcp.RoutingIndexManager(num_nodes, 1, 0)  # 1 vehicle, depot=node 0
    routing = pywrapcp.RoutingModel(manager)

    def transit_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if from_node == to_node:
            return 0
        raw_cost = cost_matrix.get((from_node, to_node))
        if raw_cost is None:
            # Undefined arc — treat as infeasible. Caller should have
            # populated INFEASIBLE_ARC_COST explicitly; a missing entry
            # is a contract bug but we fail safely rather than crash.
            log.warning(
                f"cost_matrix missing arc ({from_node}, {to_node}); "
                f"treating as infeasible."
            )
            return INFEASIBLE_ARC_COST
        return int(raw_cost * FLOAT_TO_INT_SCALE)

    transit_index = routing.RegisterTransitCallback(transit_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    # Disjunctions: for each survey line, exactly one of its two
    # direction-nodes must be visited. OR-tools "drops" both only if
    # the DROP_LINE_PENALTY is cheaper than visiting — we set it very
    # high so that never happens in practice.
    for node_a, node_b in disjunction_pairs:
        routing.AddDisjunction(
            [manager.NodeToIndex(node_a), manager.NodeToIndex(node_b)],
            DROP_LINE_PENALTY * FLOAT_TO_INT_SCALE,
        )

    # Optional pin: force the first visit after the depot.
    if pinned_first_node is not None:
        if pinned_first_node <= 0 or pinned_first_node >= num_nodes:
            raise ValueError(
                f"pinned_first_node={pinned_first_node} out of range "
                f"(must be 1..{num_nodes - 1})"
            )
        start_var = routing.NextVar(routing.Start(0))
        pinned_idx = manager.NodeToIndex(pinned_first_node)
        routing.solver().Add(start_var == pinned_idx)

    # --- Search parameters ----------------------------------------------

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = getattr(
        routing_enums_pb2.LocalSearchMetaheuristic, metaheuristic
    )
    search_params.time_limit.FromSeconds(time_limit_s)
    search_params.log_search = False  # plugin uses its own logging

    # --- Solve ----------------------------------------------------------

    log.info(
        f"OR-tools solve starting: {num_nodes} nodes, "
        f"{len(disjunction_pairs)} line pairs, "
        f"metaheuristic={metaheuristic}, time_limit={time_limit_s}s, "
        f"pinned_first={pinned_first_node}"
    )
    solve_start = time.time()

    # Progress wiring: AddAtSolutionCallback fires a no-arg Python callback on
    # every local-search candidate, which for GLS includes non-improving moves
    # (GLS accepts temporary regressions to escape local optima). We filter here
    # to only emit progress_callback on strict improvements over best-so-far —
    # gives the caller a clean monotonically-decreasing cost stream with one
    # event per genuine improvement (~50/solve instead of ~8000/solve).
    # Runs in whatever thread SolveWithParameters is called from (OrToolsTask
    # worker in production); Qt signal emissions are thread-safe.
    if progress_callback is not None:
        _improvement_count = [0]
        _best_cost_scaled = [float("inf")]

        def _at_solution():
            cost_scaled = routing.CostVar().Value()
            if cost_scaled >= _best_cost_scaled[0]:
                return  # non-improving candidate; GLS internal exploration
            _best_cost_scaled[0] = cost_scaled
            _improvement_count[0] += 1
            progress_callback(OrToolsProgress(
                elapsed_s=time.time() - solve_start,
                best_cost=cost_scaled / FLOAT_TO_INT_SCALE,
                solutions_found=_improvement_count[0],
            ))

        routing.AddAtSolutionCallback(_at_solution)

    # Hand the live routing model to the caller BEFORE we block in
    # SolveWithParameters. OrToolsTask stores this so the UI thread can call
    # routing.solver().FinishCurrentSearch() to stop the solve early; the
    # solver then returns with its best-so-far assignment, which extracts
    # below exactly like a normal completion.
    if started_callback is not None:
        started_callback(routing)

    # Blocking call — the caller (services.ortools_task.OrToolsTask) runs
    # this on a QgsTask worker thread so QGIS stays responsive.
    solution = routing.SolveWithParameters(search_params)
    solve_elapsed = time.time() - solve_start

    if solution is None:
        raise RuntimeError(
            f"OR-tools found no solution within {time_limit_s}s. This "
            f"usually indicates a contract bug (missing arcs in "
            f"cost_matrix, or pinned_first_node conflicting with a "
            f"disjunction). Check plugin logs for warnings."
        )

    # --- Extract tour ---------------------------------------------------

    ordered_nodes: List[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != 0:  # skip depot
            ordered_nodes.append(node)
        index = solution.Value(routing.NextVar(index))

    # Solver-reported total cost, in scaled-int units; convert back to
    # seconds for the OptimizationResult.
    final_cost_scaled = solution.ObjectiveValue()
    final_cost_seconds = final_cost_scaled / FLOAT_TO_INT_SCALE

    log.info(
        f"OR-tools solve done in {solve_elapsed:.2f}s: "
        f"{len(ordered_nodes)} nodes visited, cost={final_cost_seconds:.2f}s"
    )

    # --- Build OptimizationResult ---------------------------------------

    # original_cost: recompute what the SEQUENCE would have cost if we
    # hadn't optimized. Without a pre-existing sequence, this is
    # ill-defined — we use final_cost as a stand-in so improvement_pct
    # comes out as 0%. The caller (dockwidget) computes a proper
    # before/after comparison against the un-optimized racetrack /
    # teardrop sequence outside this function.
    return OptimizationResult(
        optimized_sequence=ordered_nodes,
        original_cost=final_cost_seconds,
        final_cost=final_cost_seconds,
        improvement_pct=0.0,
        total_passes=0,  # not meaningful for ortools' meta-heuristic search
        total_improvements=0,  # not meaningful
        cost_evaluations=0,  # ortools doesn't expose this cleanly
        stopped_reason="time_limit" if solve_elapsed >= time_limit_s * 0.95 else "converged",
    )

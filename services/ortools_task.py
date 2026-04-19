"""QgsTask wrapper around optimize_with_ortools (Phase 13b incremental UX).

Why this exists: Phase 13a called optimize_with_ortools synchronously from
the main UI thread. A 30–120 s solve froze QGIS with no progress feedback.
This module wraps the solve in a QgsTask so the dockwidget can run a local
QEventLoop that keeps the Qt event loop spinning (dialog paints, timer
ticks, Stop button fires) while the solver works in a background thread.

The public sync API in services.ortools_optimizer is unchanged; tests keep
calling optimize_with_ortools directly. Only the dockwidget uses the task.

Stop semantics: request_stop() calls routing.solver().FinishCurrentSearch()
on the live solver. This is safe to call from the main thread while the
worker thread is inside SolveWithParameters — OR-tools' C++ solver checks
the stop flag at yield points (between iterations, after each solution)
and returns with the best-so-far assignment, typically within a few hundred
ms of the request. The caller then extracts and applies that assignment
normally; if no solution had been found yet, SolveWithParameters returns
None and optimize_with_ortools raises RuntimeError, which the caller
catches and falls back to the pre-optimization sequence.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from .ortools_optimizer import (
    NodeMeta,
    OptimizationResult,
    OrToolsProgress,
    optimize_with_ortools,
)

log = logging.getLogger(__name__)


class OrToolsTask(QgsTask):
    """Runs optimize_with_ortools on a background thread.

    After taskCompleted fires, the caller reads:
      - self.result: OptimizationResult on success, None if canceled or error
      - self.error: Exception raised by the solver, or None
      - self.start_time: time.time() at which run() entered (for elapsed calc)

    Emits solutionFound(best_cost_seconds, solutions_found) each time the
    solver finds an improved solution. Emitted from the worker thread;
    Qt uses QueuedConnection automatically for cross-thread slots, so
    main-thread UI code can safely update widgets from the slot.

    The caller is responsible for checking isCanceled() and error before
    consuming result. finished() is intentionally a no-op — the caller
    drives the post-solve flow via a QEventLoop, not via an override here.
    """

    solutionFound = pyqtSignal(float, int)

    def __init__(
        self,
        cost_matrix: Dict[Tuple[int, int], float],
        node_meta: List[NodeMeta],
        disjunction_pairs: List[Tuple[int, int]],
        time_limit_s: int,
        pinned_first_node: Optional[int],
        metaheuristic: str,
    ):
        super().__init__("OR-tools sequence optimization", QgsTask.CanCancel)
        self._cost_matrix = cost_matrix
        self._node_meta = node_meta
        self._disjunction_pairs = disjunction_pairs
        self._time_limit_s = time_limit_s
        self._pinned_first_node = pinned_first_node
        self._metaheuristic = metaheuristic

        self._routing = None  # Set by _on_started when the solver boots.
        self.result: Optional[OptimizationResult] = None
        self.error: Optional[BaseException] = None
        self.start_time: float = 0.0

    def _on_progress(self, progress: OrToolsProgress) -> None:
        self.solutionFound.emit(progress.best_cost, progress.solutions_found)

    def _on_started(self, routing) -> None:
        """Called from worker thread when SolveWithParameters is about to start."""
        self._routing = routing

    def request_stop(self) -> None:
        """Ask the solver to stop early and return its best-so-far.

        Safe to call from the main thread while run() is blocked in
        SolveWithParameters (FinishCurrentSearch is a cross-thread atomic
        flag write per OR-tools' design). No-op if the solver hasn't
        entered SolveWithParameters yet — in that case the task's natural
        run() flow will proceed to a normal (short) solve.
        """
        if self._routing is not None:
            self._routing.solver().FinishCurrentSearch()

    def run(self) -> bool:
        """Executes in worker thread — must not touch Qt/QGIS UI."""
        self.start_time = time.time()
        try:
            self.result = optimize_with_ortools(
                cost_matrix=self._cost_matrix,
                node_meta=self._node_meta,
                disjunction_pairs=self._disjunction_pairs,
                time_limit_s=self._time_limit_s,
                pinned_first_node=self._pinned_first_node,
                metaheuristic=self._metaheuristic,
                progress_callback=self._on_progress,
                started_callback=self._on_started,
            )
            return True
        except Exception as e:
            log.exception(f"OR-tools solve raised in worker thread: {e}")
            self.error = e
            return False

    def finished(self, result: bool) -> None:
        """No-op. Caller drives post-solve flow via QEventLoop + signals."""
        pass

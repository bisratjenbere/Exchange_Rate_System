import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from typing import List, Dict, Any

from db.manager import DatabaseManager
from scheduler.runner import Scheduler
from pipeline.runs import reap_stuck_runs
from infrastructure.rate_source_repository import RateSourceRepository
from scheduler.workload_balancer import (
    calculate_optimal_workers,
    balance_workload_smart,
)

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {
    "cbe_api": 1,
    "cbe_html": 1,
    "dashen_html": 2,
    "awash_api": 3,
    "wegagen_api": 4,
    "boa_html": 5,

    "abyssinia_html": 10,
    "nib_html": 11,
    "oromia_html": 12,
    "zemen_api": 13,
    "hibret_html": 14,
    "berhan_html": 15,

    "abay_html": 20,
    "bunna_html": 21,
    "enat_html": 22,
    "rammis_api": 23,
    "tsehay_html": 24,
}


class ParallelScheduler:

    def __init__(
        self,
        max_workers: int = 5,
        timeout_budget: float = 300.0,
        scheduler: Scheduler = None,
    ):
        self.scheduler = scheduler or Scheduler()
        self.max_workers = max_workers
        self.timeout_budget = timeout_budget

    def run_all_parallel(self, conn) -> List[Dict[str, Any]]:
        reap_stuck_runs(conn, threshold_minutes=5)

        sources = self._prioritize_sources(RateSourceRepository(conn).get_enabled_sources())
        num_workers, plan = self._plan_workload(sources)

        logger.info(
            "Starting parallel collection: sources=%d, workers=%d, timeout_budget=%ss",
            len(sources), num_workers, self.timeout_budget,
        )

        start_time = time.time()
        results = self._execute_plan(plan, sources, num_workers)

        logger.info(
            "Parallel collection finished: total=%d, completed=%d, elapsed=%.1fs",
            len(sources), len(results), time.time() - start_time,
        )
        return results

    def _plan_workload(self, sources: list) -> tuple:
        optimal_workers = calculate_optimal_workers(sources)
        num_workers = min(optimal_workers, self.max_workers)
        plan = balance_workload_smart(sources, num_workers)
        logger.info(
            "Dynamic worker calculation: %d workers for %d sources (max=%d)",
            num_workers, len(sources), self.max_workers,
        )
        logger.info("Workload distribution: %s", plan.summary())
        return num_workers, plan

    def _execute_plan(self, plan, sources: list, num_workers: int) -> List[Dict[str, Any]]:
        results = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_worker = {
                executor.submit(self._process_worker_queue, worker_id, queue): (worker_id, queue)
                for worker_id, queue in enumerate(plan.queues)
                if queue
            }

            try:
                for future in as_completed(future_to_worker.keys(), timeout=self.timeout_budget):
                    results.extend(self._collect_future(future, future_to_worker, start_time))
            except FutureTimeoutError:
                results.extend(self._handle_timeout(future_to_worker, sources, start_time))

        return results

    def _collect_future(
        self, future, future_to_worker: dict, start_time: float
    ) -> List[Dict[str, Any]]:
        worker_id, queue = future_to_worker[future]
        try:
            worker_results = future.result()
            logger.info(
                "Worker %d completed: %d sources, elapsed=%.1fs",
                worker_id, len(worker_results), time.time() - start_time,
            )
            return worker_results
        except Exception as exc:  # worker must not crash — catch all adapter/DB errors
            logger.error("Worker %d exception: %s", worker_id, exc, exc_info=True)
            return [{
                'source_id': source.id,
                'status': 'error',
                'detail': str(exc),
                'error': 'worker_exception',
            } for source in queue]

    def _handle_timeout(
        self, future_to_worker: dict, sources: list, start_time: float
    ) -> List[Dict[str, Any]]:
        logger.error(
            "Timeout budget exceeded: elapsed=%.1fs, budget=%ss, completed=%d/%d",
            time.time() - start_time, self.timeout_budget,
            sum(1 for f in future_to_worker if f.done()), len(sources),
        )
        results = []
        for future, (worker_id, queue) in future_to_worker.items():
            if not future.done():
                future.cancel()
                logger.warning("Cancelled worker %d", worker_id)
                results.extend([{
                    'source_id': source.id,
                    'status': 'timeout',
                    'detail': 'timeout budget exceeded',
                    'adapter_key': source.adapter_key,
                } for source in queue])
        return results


    def _process_worker_queue(
        self,
        worker_id: int,
        queue: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Process a queue of sources sequentially in one worker.
        
        Each worker gets a pre-balanced queue of sources.
        Uses connection pool for database access.
        """
        results = []
        
        try:
            with DatabaseManager.connection() as conn:
                logger.debug("Worker %d: acquired connection from pool", worker_id)

                for source in queue:
                    try:
                        result = self.scheduler.run_source(conn, source.id)
                        results.append(result)
                        logger.debug(
                            "Worker %d: %s -> %s", worker_id, source.adapter_key, result.get('status')
                        )
                    except Exception as exc:  # worker must not crash — catch all adapter/DB errors
                        logger.error(
                            "Worker %d: %s failed: %s", worker_id, source.adapter_key, exc,
                            exc_info=True
                        )
                        results.append({
                            'source_id': source.id,
                            'status': 'error',
                            'detail': str(exc),
                            'adapter_key': source.adapter_key,
                        })
            return results

        except Exception as exc:  # worker must not crash — catch connection pool errors
            logger.error(
                "Worker %d: failed to acquire connection from pool: %s", worker_id, exc,
                exc_info=True
            )
            return [{
                'source_id': source.id,
                'status': 'error',
                'detail': 'connection pool error',
                'adapter_key': source.adapter_key,
            } for source in queue]

    def _prioritize_sources(self, sources: list) -> list:
        return sorted(sources, key=lambda s: PRIORITY_ORDER.get(s.adapter_key, 999))

def run_all_parallel(conn, max_workers: int = 5, timeout_budget: float = 300.0) -> List[Dict]:
    scheduler = ParallelScheduler(
        max_workers=max_workers,
        timeout_budget=timeout_budget,
    )
    return scheduler.run_all_parallel(conn)

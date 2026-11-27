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

        repo = RateSourceRepository(conn)
        sources = repo.get_enabled_sources()
        
        sources = self._prioritize_sources(sources)

        optimal_workers = calculate_optimal_workers(sources)
        logger.info(
            f"Dynamic worker calculation: {optimal_workers} workers "
            f"for {len(sources)} sources (was fixed at {self.max_workers})"
        )

        num_workers = min(optimal_workers, self.max_workers)

        plan = balance_workload_smart(sources, num_workers)

        logger.info(f"Workload distribution: {plan.summary()}")

        logger.info(
            f"Starting parallel collection: sources={len(sources)}, "
            f"workers={num_workers}, timeout_budget={self.timeout_budget}s"
        )

        results = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_worker = {}

            for worker_id, queue in enumerate(plan.queues):
                if not queue:
                    continue

                future = executor.submit(
                    self._process_worker_queue,
                    worker_id,
                    queue
                )
                future_to_worker[future] = (worker_id, queue)
            
            # Wait for all workers to complete
            try:
                for future in as_completed(
                    future_to_worker.keys(),
                    timeout=self.timeout_budget
                ):
                    worker_id, queue = future_to_worker[future]
                    
                    try:
                        worker_results = future.result()
                        results.extend(worker_results)
                        
                        elapsed = time.time() - start_time
                        logger.info(
                            f"Worker {worker_id} completed: {len(worker_results)} sources, "
                            f"elapsed={elapsed:.1f}s"
                        )
                        
                    except Exception as exc:  # worker must not crash — catch all adapter/DB errors
                        logger.error(
                            "Worker %d exception: %s", worker_id, exc,
                            exc_info=True
                        )
                        for source in queue:
                            results.append({
                                'source_id': source.id,
                                'status': 'error',
                                'detail': str(exc),
                                'error': 'worker_exception'
                            })
            
            except FutureTimeoutError:
                elapsed = time.time() - start_time
                logger.error(
                    f"Timeout budget exceeded: elapsed={elapsed:.1f}s, "
                    f"budget={self.timeout_budget}s, "
                    f"completed={len(results)}/{len(sources)}"
                )
                
                # Cancel pending workers
                for future, (worker_id, queue) in future_to_worker.items():
                    if not future.done():
                        future.cancel()
                        logger.warning(f"Cancelled worker {worker_id}")
                        
                        for source in queue:
                            results.append({
                                'source_id': source.id,
                                'status': 'timeout',
                                'detail': 'timeout budget exceeded',
                                'adapter_key': source.adapter_key
                            })

        elapsed = time.time() - start_time
        logger.info(
            f"Parallel collection finished: "
            f"total={len(sources)}, completed={len(results)}, "
            f"elapsed={elapsed:.1f}s"
        )

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
            # Use connection pool instead of direct connect
            with DatabaseManager.connection() as conn:
                logger.debug(f"Worker {worker_id}: acquired connection from pool")
                
                for source in queue:
                    try:
                        result = self.scheduler.run_source(conn, source.id)
                        results.append(result)
                        
                        logger.debug(
                            f"Worker {worker_id}: {source.adapter_key} -> {result.get('status')}"
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
                            'adapter_key': source.adapter_key
                        })
            
            return results
            
        except Exception as exc:  # worker must not crash — catch connection pool errors
            logger.error(
                "Worker %d: failed to acquire connection from pool: %s", worker_id, exc,
                exc_info=True
            )
            # Return error results for all sources in queue
            return [{
                'source_id': source.id,
                'status': 'error',
                'detail': 'connection pool error',
                'adapter_key': source.adapter_key
            } for source in queue]

    def _prioritize_sources(self, sources: list) -> list:
        return sorted(sources, key=lambda s: PRIORITY_ORDER.get(s.adapter_key, 999))

def run_all_parallel(conn, max_workers: int = 5, timeout_budget: float = 300.0) -> List[Dict]:
    scheduler = ParallelScheduler(
        max_workers=max_workers,
        timeout_budget=timeout_budget,
    )
    return scheduler.run_all_parallel(conn)

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from typing import List, Dict, Any, Optional

import psycopg2

from scheduler.runner import Scheduler
from pipeline.runs import reap_stuck_runs
from infrastructure.config import Config
from infrastructure.rate_source_repository import RateSourceRepository

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

class ParallelScheduler(Scheduler):

    def __init__(
        self,
        max_workers: int = 5,
        timeout_budget: float = 300.0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.max_workers = max_workers
        self.timeout_budget = timeout_budget

    def run_all_parallel(self, conn) -> List[Dict[str, Any]]:
        reap_stuck_runs(conn, threshold_minutes=5)
        dsn = self._get_dsn(conn)

        repo = RateSourceRepository(conn)
        sources = repo.get_enabled_sources()
        sources = self._prioritize_sources(sources)

        logger.info(
            "Starting parallel collection: sources=%d, max_workers=%d, timeout_budget=%ds",
            len(sources), self.max_workers, self.timeout_budget
        )

        results = []
        skipped = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_source = {
                executor.submit(
                    self._run_source_with_connection,
                    dsn,
                    source["id"]
                ): source
                for source in sources
            }

            try:
                for future in as_completed(
                    future_to_source,
                    timeout=self.timeout_budget
                ):
                    source = future_to_source[future]

                    try:
                        result = future.result()
                        results.append(result)

                        elapsed = time.time() - start_time
                        logger.info(
                            "Completed %d/%d: source=%s status=%s elapsed=%.1fs",
                            len(results),
                            len(sources),
                            source["adapter_key"],
                            result.get("status"),
                            elapsed
                        )

                        if elapsed > self.timeout_budget * 0.9:
                            logger.warning(
                                "Approaching timeout budget: elapsed=%.1fs budget=%ds",
                                elapsed,
                                self.timeout_budget
                            )

                    except Exception as exc:
                        logger.error(
                            "Collection exception: source=%s error=%s",
                            source["adapter_key"],
                            exc
                        )
                        results.append({
                            "source_id": source["id"],
                            "status": "error",
                            "detail": str(exc),
                            "error": "parallel_execution_error"
                        })

            except FutureTimeoutError:
                elapsed = time.time() - start_time
                logger.error(
                    "Timeout budget exceeded: elapsed=%.1fs budget=%ds completed=%d/%d",
                    elapsed,
                    self.timeout_budget,
                    len(results),
                    len(sources)
                )

                for future, source in future_to_source.items():
                    if not future.done():
                        future.cancel()
                        skipped.append({
                            "source_id": source["id"],
                            "status": "timeout",
                            "detail": "timeout budget exceeded",
                            "adapter_key": source["adapter_key"]
                        })

                results.extend(skipped)

        elapsed = time.time() - start_time
        logger.info(
            "Parallel collection finished: total=%d completed=%d skipped=%d elapsed=%.1fs",
            len(sources),
            len(results) - len(skipped),
            len(skipped),
            elapsed
        )

        return results

    def _run_source_with_connection(
        self,
        dsn: str,
        source_id: int
    ) -> Dict[str, Any]:
        conn = None
        try:
            conn = psycopg2.connect(dsn)

            result = self.run_source(conn, source_id)

            return result

        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _prioritize_sources(self, sources: List[Dict]) -> List[Dict]:
        def get_priority(source):
            adapter_key = source.get("adapter_key", "")
            return PRIORITY_ORDER.get(adapter_key, 999)

        return sorted(sources, key=get_priority)

    def _get_dsn(self, conn) -> str:
        try:
            info = conn.info
            if hasattr(info, 'dsn'):
                return info.dsn
        except Exception:
            pass

        config = Config()
        return config.DATABASE_URL

def run_all_parallel(conn, max_workers: int = 5, timeout_budget: float = 300.0) -> List[Dict]:
    scheduler = ParallelScheduler(
        max_workers=max_workers,
        timeout_budget=timeout_budget
    )
    return scheduler.run_all_parallel(conn)

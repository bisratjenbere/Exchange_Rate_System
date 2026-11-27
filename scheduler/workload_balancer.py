import logging
from typing import List, Tuple

from domain.source import RateSource
from infrastructure.timeout_config import get_timeout_config
from scheduler.workload_plan import WorkloadPlan

logger = logging.getLogger(__name__)

_BROWSER_ADAPTERS = {'anbesa_browser', 'cbe_html', 'dashen_html', 'boa_html', 'goh_betoch_html'}
_API_ADAPTERS = {'rammis_api', 'zemen_api', 'awash_api', 'wegagen_api'}


def calculate_optimal_workers(sources: List[RateSource]) -> int:
    if not sources:
        return 1

    browser_count = 0
    api_count = 0
    html_count = 0

    for source in sources:
        key = source.adapter_key
        if 'browser' in key or key in _BROWSER_ADAPTERS:
            browser_count += 1
        elif 'api' in key or key in _API_ADAPTERS:
            api_count += 1
        else:
            html_count += 1

    total = min(browser_count, 3) + min(api_count, 15) + min(html_count, 10)
    optimal = min(total, 20)

    logger.info(
        f"Calculated optimal workers: {optimal} "
        f"(browser={browser_count}, api={api_count}, html={html_count})"
    )

    return max(optimal, 1)


def estimate_source_duration(source: RateSource) -> float:
    key = source.adapter_key
    config = get_timeout_config(key)

    estimated = config['connect_timeout'] + config['read_timeout'] * 0.7 + 2.0

    if 'browser' in key or key in _BROWSER_ADAPTERS:
        estimated += 0.5

    max_retries = config.get('max_retries', 2)
    if max_retries > 0:
        estimated += config['connect_timeout'] * 0.2

    logger.debug(f"Estimated duration for {key}: {estimated:.1f}s")

    return estimated


def balance_workload_smart(
    sources: List[RateSource],
    num_workers: int,
) -> WorkloadPlan:
    if num_workers <= 0:
        logger.warning(f"Invalid num_workers={num_workers}, using 1")
        num_workers = 1

    if not sources:
        return WorkloadPlan(queues=[[] for _ in range(num_workers)], worker_times=[0.0] * num_workers)

    source_durations: List[Tuple[RateSource, float]] = sorted(
        [(s, estimate_source_duration(s)) for s in sources],
        key=lambda x: x[1],
        reverse=True,
    )

    worker_queues: List[List[RateSource]] = [[] for _ in range(num_workers)]
    worker_times = [0.0] * num_workers

    for source, duration in source_durations:
        idx = worker_times.index(min(worker_times))
        worker_queues[idx].append(source)
        worker_times[idx] += duration

    plan = WorkloadPlan(queues=worker_queues, worker_times=worker_times)

    max_duration = max(worker_times) if worker_times else 0
    total_duration = sum(worker_times)
    efficiency = total_duration / (max_duration * num_workers) * 100 if max_duration > 0 else 0
    logger.info(f"Workload balanced across {num_workers} workers: efficiency={efficiency:.1f}%")

    for i, (queue, total_time) in enumerate(zip(worker_queues, worker_times)):
        logger.info(
            f"Worker {i}: {len(queue)} sources, estimated {total_time:.1f}s, "
            f"sources={[s.adapter_key for s in queue]}"
        )

    return plan


def get_workload_summary(worker_queues) -> dict:
    if isinstance(worker_queues, WorkloadPlan):
        return worker_queues.summary()
    # compatibility: accept raw List[List] from tests
    times = [sum(estimate_source_duration(s) for s in q) for q in worker_queues]
    max_time = max(times) if times else 0.0
    min_time = min(times) if times else 0.0
    avg_time = sum(times) / len(times) if times else 0.0
    imbalance = (max_time - min_time) / max_time if max_time > 0 else 0.0
    return {
        "num_workers": len(worker_queues),
        "total_sources": sum(len(q) for q in worker_queues),
        "max_worker_time": round(max_time, 1),
        "min_worker_time": round(min_time, 1),
        "avg_worker_time": round(avg_time, 1),
        "imbalance_ratio": round(imbalance, 3),
        "balance_quality": (
            "excellent" if imbalance < 0.1
            else "good" if imbalance < 0.2
            else "fair"
        ),
    }

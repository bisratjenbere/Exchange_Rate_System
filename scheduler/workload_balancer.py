"""
Smart workload balancing for parallel collection.

Implements bin-packing algorithm to distribute sources across workers
in a way that minimizes maximum completion time.
"""

import logging
from typing import List, Dict, Tuple
from infrastructure.timeout_config import get_timeout_config

logger = logging.getLogger(__name__)


def calculate_optimal_workers(sources: List[Dict]) -> int:
    """
    Calculate optimal worker count based on source characteristics.
    
    Rules:
    - Browser sources: max 3 concurrent (CPU-intensive, memory-heavy)
    - API sources: max 15 concurrent (I/O-bound, lightweight)
    - HTML sources: max 10 concurrent (mixed characteristics)
    
    Args:
        sources: List of source dictionaries with adapter_key
    
    Returns:
        Optimal number of workers (capped at 20 for GitHub Actions)
    """
    if not sources:
        return 1
    
    # Categorize sources
    browser_count = 0
    api_count = 0
    html_count = 0
    
    for source in sources:
        adapter_key = source.get('adapter_key', '')
        
        # Check for browser-based adapters
        if 'browser' in adapter_key or adapter_key in [
            'anbesa_browser',
            'cbe_html',  # Uses browser despite name
            'dashen_html',
            'boa_html',
            'goh_betoch_html',
        ]:
            browser_count += 1
        
        # API sources (fastest)
        elif 'api' in adapter_key or adapter_key in [
            'rammis_api', 'zemen_api', 'awash_api', 'wegagen_api'
        ]:
            api_count += 1
        
        # HTML sources (medium speed)
        else:
            html_count += 1
    
    # Calculate worker allocation
    browser_workers = min(browser_count, 3)  # Limit concurrent browsers
    api_workers = min(api_count, 15)         # APIs can run more concurrently
    html_workers = min(html_count, 10)       # Moderate concurrency
    
    total = browser_workers + api_workers + html_workers
    
    # Cap at reasonable maximum (GitHub Actions has resource limits)
    optimal = min(total, 20)
    
    logger.info(
        f"Calculated optimal workers: {optimal} "
        f"(browser={browser_count}, api={api_count}, html={html_count})"
    )
    
    return max(optimal, 1)  # At least 1 worker


def estimate_source_duration(source: Dict) -> float:
    """
    Estimate collection duration for a source.
    
    Based on:
    - Configured timeouts
    - Fetch method (browser adds overhead)
    - Historical performance (if available)
    
    Args:
        source: Source dictionary
    
    Returns:
        Estimated duration in seconds
    """
    adapter_key = source.get('adapter_key', '')
    config = get_timeout_config(adapter_key)
    
    # Base estimate: connect + read timeout
    # Use 70% of read timeout (sources usually finish before timeout)
    estimated = (
        config['connect_timeout'] +
        config['read_timeout'] * 0.7
    )
    
    # Add parsing overhead
    estimated += 2.0
    
    # Adjust for fetch method
    if 'browser' in adapter_key or adapter_key in [
        'anbesa_browser', 'cbe_html', 'dashen_html', 'boa_html', 'goh_betoch_html'
    ]:
        # Browser sources: add startup overhead
        # (reduced from 3s to 0.5s with browser pooling)
        estimated += 0.5
    
    # Add retry overhead (probabilistic)
    max_retries = config.get('max_retries', 2)
    if max_retries > 0:
        # Assume 20% chance of needing one retry
        estimated += config['connect_timeout'] * 0.2
    
    logger.debug(f"Estimated duration for {adapter_key}: {estimated:.1f}s")
    
    return estimated


def balance_workload_smart(
    sources: List[Dict],
    num_workers: int
) -> List[List[Dict]]:
    """
    Distribute sources across workers using bin-packing algorithm.
    
    Algorithm:
    1. Estimate duration for each source
    2. Sort sources by duration (longest first)
    3. Use greedy bin-packing: assign each source to worker with minimum load
    
    This minimizes the maximum completion time (makespan).
    
    Args:
        sources: List of source dictionaries
        num_workers: Number of workers to distribute across
    
    Returns:
        List of worker queues (each queue is list of sources)
    """
    if not sources:
        return [[] for _ in range(num_workers)]
    
    if num_workers <= 0:
        logger.warning(f"Invalid num_workers={num_workers}, using 1")
        num_workers = 1
    
    # Estimate duration for each source
    source_durations: List[Tuple[Dict, float]] = []
    for source in sources:
        duration = estimate_source_duration(source)
        source_durations.append((source, duration))
    
    # Sort by duration (longest first) for greedy bin-packing
    source_durations.sort(key=lambda x: x[1], reverse=True)
    
    # Initialize worker queues
    worker_queues = [[] for _ in range(num_workers)]
    worker_times = [0.0] * num_workers
    
    # Assign each source to worker with minimum current load
    for source, duration in source_durations:
        # Find worker with minimum load
        min_worker_idx = worker_times.index(min(worker_times))
        
        # Assign source to this worker
        worker_queues[min_worker_idx].append(source)
        worker_times[min_worker_idx] += duration
    
    # Log allocation for debugging
    total_duration = sum(worker_times)
    max_duration = max(worker_times) if worker_times else 0
    efficiency = (
        total_duration / (max_duration * num_workers) * 100
        if max_duration > 0
        else 0
    )
    
    logger.info(
        f"Workload balanced across {num_workers} workers: "
        f"efficiency={efficiency:.1f}%"
    )
    
    for i, (queue, total_time) in enumerate(zip(worker_queues, worker_times)):
        adapter_keys = [s.get('adapter_key') for s in queue]
        logger.info(
            f"Worker {i}: {len(queue)} sources, "
            f"estimated {total_time:.1f}s, "
            f"sources={adapter_keys}"
        )
    
    return worker_queues


def get_workload_summary(worker_queues: List[List[Dict]]) -> Dict:
    """
    Generate summary of workload distribution.
    
    Useful for monitoring and optimization.
    """
    total_sources = sum(len(queue) for queue in worker_queues)
    
    worker_times = []
    for queue in worker_queues:
        total_time = sum(estimate_source_duration(s) for s in queue)
        worker_times.append(total_time)
    
    max_time = max(worker_times) if worker_times else 0
    min_time = min(worker_times) if worker_times else 0
    avg_time = sum(worker_times) / len(worker_times) if worker_times else 0
    
    # Calculate balance metric (lower is better)
    # 0 = perfectly balanced, 1 = completely unbalanced
    if max_time > 0:
        imbalance = (max_time - min_time) / max_time
    else:
        imbalance = 0
    
    return {
        'num_workers': len(worker_queues),
        'total_sources': total_sources,
        'max_worker_time': round(max_time, 1),
        'min_worker_time': round(min_time, 1),
        'avg_worker_time': round(avg_time, 1),
        'imbalance_ratio': round(imbalance, 3),
        'balance_quality': 'excellent' if imbalance < 0.1 else 'good' if imbalance < 0.2 else 'fair',
    }

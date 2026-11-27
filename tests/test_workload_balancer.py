import pytest
from scheduler.workload_balancer import (
    calculate_optimal_workers,
    estimate_source_duration,
    balance_workload_smart,
    get_workload_summary
)


class TestCalculateOptimalWorkers:
    
    def test_empty_sources(self):
        assert calculate_optimal_workers([]) == 1
    
    def test_browser_sources_limited(self):
        """Browser sources should be limited to 3 concurrent"""
        sources = [
            {'adapter_key': 'cbe_html'},
            {'adapter_key': 'dashen_html'},
            {'adapter_key': 'boa_html'},
            {'adapter_key': 'anbesa_browser'},
            {'adapter_key': 'goh_betoch_html'},
        ]
        workers = calculate_optimal_workers(sources)
        assert workers == 3
    
    def test_api_sources_high_concurrency(self):
        """API sources can run with higher concurrency"""
        sources = [{'adapter_key': f'bank{i}_api'} for i in range(20)]
        workers = calculate_optimal_workers(sources)
        assert workers == 15  # Capped at API limit
    
    def test_mixed_sources(self):
        """Mixed sources should balance appropriately"""
        sources = [
            {'adapter_key': 'cbe_html'},        # browser
            {'adapter_key': 'dashen_html'},     # browser
            {'adapter_key': 'awash_api'},       # api
            {'adapter_key': 'zemen_api'},       # api
            {'adapter_key': 'abay_html'},       # html
            {'adapter_key': 'hibret_html'},     # html
        ]
        workers = calculate_optimal_workers(sources)
        # 2 browser + 2 api + 2 html = 6 workers
        assert workers == 6
    
    def test_caps_at_20(self):
        """Should not exceed GitHub Actions limits"""
        sources = [{'adapter_key': f'bank{i}_api'} for i in range(50)]
        workers = calculate_optimal_workers(sources)
        assert workers <= 20


class TestEstimateSourceDuration:
    
    def test_fast_api_source(self):
        """Fast API sources should have low estimate"""
        source = {'adapter_key': 'rammis_api'}
        duration = estimate_source_duration(source)
        assert 10 <= duration <= 15  # 3s connect + 7s read + 2s parse + retry
    
    def test_slow_browser_source(self):
        """Browser sources should have higher estimate"""
        source = {'adapter_key': 'cbe_html'}
        duration = estimate_source_duration(source)
        assert 20 <= duration <= 30  # Longer timeout + browser overhead
    
    def test_default_config(self):
        """Unknown sources should use default config"""
        source = {'adapter_key': 'unknown_bank'}
        duration = estimate_source_duration(source)
        assert duration > 0


class TestBalanceWorkloadSmart:
    
    def test_empty_sources(self):
        """Should handle empty source list"""
        queues = balance_workload_smart([], 3)
        assert len(queues) == 3
        assert all(len(q) == 0 for q in queues)
    
    def test_single_worker(self):
        """Should handle single worker"""
        sources = [
            {'adapter_key': 'cbe_html'},
            {'adapter_key': 'awash_api'},
        ]
        queues = balance_workload_smart(sources, 1)
        assert len(queues) == 1
        assert len(queues[0]) == 2
    
    def test_balances_slow_sources(self):
        """Slow sources should be distributed across workers"""
        sources = [
            {'adapter_key': 'cbe_html'},        # ~25s
            {'adapter_key': 'dashen_html'},     # ~20s
            {'adapter_key': 'rammis_api'},      # ~12s
            {'adapter_key': 'zemen_api'},       # ~12s
        ]
        queues = balance_workload_smart(sources, 2)
        
        # Should be relatively balanced
        assert len(queues) == 2
        assert all(len(q) == 2 for q in queues)
    
    def test_sorts_by_duration(self):
        """Should assign longest sources first (greedy bin-packing)"""
        sources = [
            {'adapter_key': 'rammis_api'},      # fast
            {'adapter_key': 'cbe_html'},        # slow
            {'adapter_key': 'zemen_api'},       # fast
            {'adapter_key': 'dashen_html'},     # slow
        ]
        queues = balance_workload_smart(sources, 2)
        
        # First source in each queue should be a slow one
        for queue in queues:
            if queue:
                first_source = queue[0]['adapter_key']
                assert 'html' in first_source  # Slow sources
    
    def test_handles_zero_workers(self):
        """Should handle edge case of 0 workers"""
        sources = [{'adapter_key': 'cbe_html'}]
        queues = balance_workload_smart(sources, 0)
        assert len(queues) == 1  # Defaults to 1
    
    def test_more_workers_than_sources(self):
        """Should handle more workers than sources"""
        sources = [
            {'adapter_key': 'cbe_html'},
            {'adapter_key': 'awash_api'},
        ]
        queues = balance_workload_smart(sources, 5)
        assert len(queues) == 5
        # Only 2 queues should have sources
        filled = [q for q in queues if q]
        assert len(filled) == 2


class TestGetWorkloadSummary:
    
    def test_summary_metrics(self):
        """Should provide comprehensive metrics"""
        worker_queues = [
            [{'adapter_key': 'cbe_html'}],
            [{'adapter_key': 'rammis_api'}, {'adapter_key': 'zemen_api'}],
        ]
        summary = get_workload_summary(worker_queues)
        
        assert summary['num_workers'] == 2
        assert summary['total_sources'] == 3
        assert summary['max_worker_time'] > 0
        assert 0 <= summary['imbalance_ratio'] <= 1
        assert summary['balance_quality'] in ['excellent', 'good', 'fair']
    
    def test_perfect_balance(self):
        """Perfectly balanced workload should have low imbalance"""
        worker_queues = [
            [{'adapter_key': 'rammis_api'}],
            [{'adapter_key': 'zemen_api'}],
        ]
        summary = get_workload_summary(worker_queues)
        
        # Both sources have similar duration
        assert summary['imbalance_ratio'] < 0.1
        assert summary['balance_quality'] == 'excellent'
    
    def test_empty_queues(self):
        """Should handle empty queues gracefully"""
        worker_queues = [[], []]
        summary = get_workload_summary(worker_queues)
        
        assert summary['num_workers'] == 2
        assert summary['total_sources'] == 0
        assert summary['max_worker_time'] == 0

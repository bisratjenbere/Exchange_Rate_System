import pytest
from domain.source import RateSource
from scheduler.workload_balancer import (
    calculate_optimal_workers,
    estimate_source_duration,
    balance_workload_smart,
)


def _src(adapter_key: str) -> RateSource:
    return RateSource(
        id=0,
        adapter_key=adapter_key,
        source_url="https://example.com",
        ssl_verify=True,
        is_enabled=True,
        schema_fingerprint=None,
        default_category="cash",
        consecutive_failures=0,
        last_failure_code=None,
        last_failure_at=None,
        last_success_at=None,
        adapter_config=None,
    )


class TestCalculateOptimalWorkers:

    def test_empty_sources(self):
        assert calculate_optimal_workers([]) == 1

    def test_browser_sources_limited(self):
        sources = [_src(k) for k in ('cbe_html', 'dashen_html', 'boa_html', 'anbesa_browser', 'goh_betoch_html')]
        assert calculate_optimal_workers(sources) == 3

    def test_api_sources_high_concurrency(self):
        sources = [_src(f'bank{i}_api') for i in range(20)]
        assert calculate_optimal_workers(sources) == 15

    def test_mixed_sources(self):
        sources = [_src(k) for k in ('cbe_html', 'dashen_html', 'awash_api', 'zemen_api', 'abay_html', 'hibret_html')]
        assert calculate_optimal_workers(sources) == 6

    def test_caps_at_20(self):
        sources = [_src(f'bank{i}_api') for i in range(50)]
        assert calculate_optimal_workers(sources) <= 20


class TestEstimateSourceDuration:

    def test_fast_api_source(self):
        assert 10 <= estimate_source_duration(_src('rammis_api')) <= 15

    def test_slow_browser_source(self):
        assert 20 <= estimate_source_duration(_src('cbe_html')) <= 30

    def test_default_config(self):
        assert estimate_source_duration(_src('unknown_bank')) > 0


class TestBalanceWorkloadSmart:

    def test_empty_sources(self):
        plan = balance_workload_smart([], 3)
        assert len(plan) == 3
        assert all(len(q) == 0 for q in plan)

    def test_single_worker(self):
        plan = balance_workload_smart([_src('cbe_html'), _src('awash_api')], 1)
        assert len(plan) == 1
        assert len(plan[0]) == 2

    def test_balances_slow_sources(self):
        sources = [_src(k) for k in ('cbe_html', 'dashen_html', 'rammis_api', 'zemen_api')]
        plan = balance_workload_smart(sources, 2)
        assert len(plan) == 2
        assert all(len(q) == 2 for q in plan)

    def test_sorts_by_duration(self):
        sources = [_src(k) for k in ('rammis_api', 'cbe_html', 'zemen_api', 'dashen_html')]
        plan = balance_workload_smart(sources, 2)
        for queue in plan:
            if queue:
                assert 'html' in queue[0].adapter_key

    def test_handles_zero_workers(self):
        plan = balance_workload_smart([_src('cbe_html')], 0)
        assert len(plan) == 1

    def test_more_workers_than_sources(self):
        plan = balance_workload_smart([_src('cbe_html'), _src('awash_api')], 5)
        assert len(plan) == 5
        assert len([q for q in plan if q]) == 2


class TestWorkloadPlanSummary:

    def test_summary_metrics(self):
        plan = balance_workload_smart(
            [_src('cbe_html'), _src('rammis_api'), _src('zemen_api')], 2
        )
        summary = plan.summary()
        assert summary['num_workers'] == 2
        assert summary['total_sources'] == 3
        assert summary['max_worker_time'] > 0
        assert 0 <= summary['imbalance_ratio'] <= 1
        assert summary['balance_quality'] in ('excellent', 'good', 'fair')

    def test_perfect_balance(self):
        plan = balance_workload_smart([_src('rammis_api'), _src('zemen_api')], 2)
        summary = plan.summary()
        assert summary['imbalance_ratio'] < 0.1
        assert summary['balance_quality'] == 'excellent'

    def test_empty_queues(self):
        plan = balance_workload_smart([], 2)
        summary = plan.summary()
        assert summary['num_workers'] == 2
        assert summary['total_sources'] == 0
        assert summary['max_worker_time'] == 0

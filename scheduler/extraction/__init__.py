"""
Extracted modules from scheduler/runner.py for behavior-preserving refactoring.

This package contains the extracted seams from the monolithic run_source() method:
- input_parser: Pre-flight checks, source validation, circuit breaker logic
- fetcher: Adapter loading, HTTP fetching, schema checking (TODO)
- decision: Record classification as zero/stale/normal (TODO)
- recorder: Transaction ownership and outcome recording (TODO)
- orchestrator: Top-level coordination (TODO)

Each module preserves exact behavior from the original implementation.
See docs/runner-refactoring-plan-corrected.md for details.
"""

__all__ = [
    "input_parser",
]

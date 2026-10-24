"""
infrastructure/circuit_breaker.py — Circuit breaker pattern for failing sources.

Prevents wasting time on repeatedly failing banks by temporarily stopping
collection attempts after consecutive failures. Automatically retries after
a recovery timeout period.

Pattern: CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN)
- CLOSED: Normal operation, attempts allowed
- OPEN: Too many failures, block all attempts
- HALF_OPEN: Recovery period, allow one test attempt

Benefits:
- Reduces wasted collection time on down/broken banks
- Faster overall collection runs
- Automatic recovery when banks come back online
"""
import time
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal: attempts allowed
    OPEN = "open"           # Failed: attempts blocked
    HALF_OPEN = "half_open" # Testing: one attempt allowed


@dataclass
class CircuitStatus:
    """Status of a circuit breaker."""
    state: CircuitState
    failure_count: int
    last_failure_time: Optional[float]
    opened_at: Optional[float]
    
    def __str__(self):
        if self.state == CircuitState.OPEN:
            age = time.time() - self.opened_at if self.opened_at else 0
            return f"OPEN (failures={self.failure_count}, age={age:.0f}s)"
        return f"{self.state.value.upper()} (failures={self.failure_count})"


class CircuitBreaker:
    """
    Circuit breaker for collection sources.
    
    Tracks failures per source and blocks attempts when threshold exceeded.
    Automatically transitions to recovery after timeout period.
    
    Example:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
        
        if cb.should_attempt("cbe_html"):
            result = collect_from_bank()
            if result.success:
                cb.record_success("cbe_html")
            else:
                cb.record_failure("cbe_html")
        else:
            print("Circuit breaker open - skipping")
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 300.0,  # 5 minutes
        half_open_timeout: float = 60.0   # 1 minute for test
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_timeout: Seconds to wait in half-open before retrying
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_timeout = half_open_timeout
        
        # Track state per adapter_key
        self._circuits: Dict[str, CircuitStatus] = {}
    
    def should_attempt(self, adapter_key: str) -> bool:
        """
        Check if collection should be attempted for this source.
        
        Args:
            adapter_key: Source adapter key
        
        Returns:
            True if attempt should proceed, False if blocked by circuit breaker
        """
        status = self._get_status(adapter_key)
        
        if status.state == CircuitState.CLOSED:
            # Normal operation - allow
            return True
        
        if status.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if status.opened_at is None:
                # Should not happen, but recover gracefully
                self._transition_to_half_open(adapter_key)
                return True
            
            elapsed = time.time() - status.opened_at
            if elapsed >= self.recovery_timeout:
                # Try recovery - transition to half-open
                self._transition_to_half_open(adapter_key)
                return True
            
            # Still in timeout period - block
            return False
        
        if status.state == CircuitState.HALF_OPEN:
            # Allow one test attempt
            return True
        
        return False
    
    def record_success(self, adapter_key: str):
        """
        Record successful collection.
        
        Resets failure counter and closes circuit if open.
        
        Args:
            adapter_key: Source adapter key
        """
        status = self._get_status(adapter_key)
        
        # Reset on success
        self._circuits[adapter_key] = CircuitStatus(
            state=CircuitState.CLOSED,
            failure_count=0,
            last_failure_time=None,
            opened_at=None
        )
    
    def record_failure(self, adapter_key: str):
        """
        Record failed collection attempt.
        
        Increments failure counter and opens circuit if threshold exceeded.
        
        Args:
            adapter_key: Source adapter key
        """
        status = self._get_status(adapter_key)
        now = time.time()
        
        new_count = status.failure_count + 1
        
        if status.state == CircuitState.HALF_OPEN:
            # Failed during recovery test - reopen circuit
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.OPEN,
                failure_count=new_count,
                last_failure_time=now,
                opened_at=now
            )
            return
        
        # Update failure count
        if new_count >= self.failure_threshold:
            # Threshold exceeded - open circuit
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.OPEN,
                failure_count=new_count,
                last_failure_time=now,
                opened_at=now
            )
        else:
            # Still below threshold
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.CLOSED,
                failure_count=new_count,
                last_failure_time=now,
                opened_at=None
            )
    
    def get_status(self, adapter_key: str) -> CircuitStatus:
        """
        Get current circuit breaker status.
        
        Args:
            adapter_key: Source adapter key
        
        Returns:
            Current circuit status
        """
        return self._get_status(adapter_key)
    
    def get_open_circuits(self) -> Dict[str, CircuitStatus]:
        """
        Get all currently open circuits.
        
        Returns:
            Dict mapping adapter_key to status for open circuits
        """
        return {
            key: status
            for key, status in self._circuits.items()
            if status.state == CircuitState.OPEN
        }
    
    def reset(self, adapter_key: str):
        """
        Manually reset a circuit (for administrative override).
        
        Args:
            adapter_key: Source adapter key
        """
        if adapter_key in self._circuits:
            del self._circuits[adapter_key]
    
    def reset_all(self):
        """Clear all circuit breaker state."""
        self._circuits.clear()
    
    def _get_status(self, adapter_key: str) -> CircuitStatus:
        """Get or create status for adapter."""
        if adapter_key not in self._circuits:
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.CLOSED,
                failure_count=0,
                last_failure_time=None,
                opened_at=None
            )
        return self._circuits[adapter_key]
    
    def _transition_to_half_open(self, adapter_key: str):
        """Transition circuit to half-open state for recovery test."""
        status = self._get_status(adapter_key)
        self._circuits[adapter_key] = CircuitStatus(
            state=CircuitState.HALF_OPEN,
            failure_count=status.failure_count,
            last_failure_time=status.last_failure_time,
            opened_at=None
        )
    
    def get_summary(self) -> str:
        """
        Get human-readable summary of circuit breaker state.
        
        Returns:
            Formatted string with status of all circuits
        """
        if not self._circuits:
            return "No circuit breaker state (all circuits closed)"
        
        lines = ["=== CIRCUIT BREAKER STATUS ===", ""]
        
        open_circuits = []
        half_open_circuits = []
        closed_with_failures = []
        
        for key, status in self._circuits.items():
            if status.state == CircuitState.OPEN:
                open_circuits.append((key, status))
            elif status.state == CircuitState.HALF_OPEN:
                half_open_circuits.append((key, status))
            elif status.failure_count > 0:
                closed_with_failures.append((key, status))
        
        if open_circuits:
            lines.append(f"OPEN CIRCUITS ({len(open_circuits)}):")
            for key, status in open_circuits:
                age = time.time() - status.opened_at if status.opened_at else 0
                remaining = self.recovery_timeout - age
                lines.append(f"  • {key}: {status.failure_count} failures, recovery in {remaining:.0f}s")
            lines.append("")
        
        if half_open_circuits:
            lines.append(f"HALF-OPEN CIRCUITS ({len(half_open_circuits)} - testing recovery):")
            for key, status in half_open_circuits:
                lines.append(f"  • {key}: {status.failure_count} failures")
            lines.append("")
        
        if closed_with_failures:
            lines.append(f"CLOSED WITH FAILURES ({len(closed_with_failures)}):")
            for key, status in closed_with_failures:
                lines.append(f"  • {key}: {status.failure_count}/{self.failure_threshold} failures")
            lines.append("")
        
        return "\n".join(lines)


# Module-level singleton for shared state across scheduler runs
_default_breaker: Optional[CircuitBreaker] = None


def get_default_circuit_breaker() -> CircuitBreaker:
    """
    Get shared circuit breaker instance.
    
    Uses module-level singleton to maintain state across scheduler runs.
    
    Returns:
        Shared CircuitBreaker instance
    """
    global _default_breaker
    if _default_breaker is None:
        _default_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=300.0,  # 5 minutes
            half_open_timeout=60.0
        )
    return _default_breaker

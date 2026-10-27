import time
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitStatus:
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

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 300.0,
        half_open_timeout: float = 60.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_timeout = half_open_timeout

        self._circuits: Dict[str, CircuitStatus] = {}

    def should_attempt(self, adapter_key: str) -> bool:
        status = self._get_status(adapter_key)

        if status.state == CircuitState.CLOSED:
            return True

        if status.state == CircuitState.OPEN:
            if status.opened_at is None:
                self._transition_to_half_open(adapter_key)
                return True

            elapsed = time.time() - status.opened_at
            if elapsed >= self.recovery_timeout:
                self._transition_to_half_open(adapter_key)
                return True

            return False

        if status.state == CircuitState.HALF_OPEN:
            return True

        return False

    def record_success(self, adapter_key: str):
        status = self._get_status(adapter_key)

        self._circuits[adapter_key] = CircuitStatus(
            state=CircuitState.CLOSED,
            failure_count=0,
            last_failure_time=None,
            opened_at=None
        )

    def record_failure(self, adapter_key: str):
        status = self._get_status(adapter_key)
        now = time.time()

        new_count = status.failure_count + 1

        if status.state == CircuitState.HALF_OPEN:
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.OPEN,
                failure_count=new_count,
                last_failure_time=now,
                opened_at=now
            )
            return

        if new_count >= self.failure_threshold:
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.OPEN,
                failure_count=new_count,
                last_failure_time=now,
                opened_at=now
            )
        else:
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.CLOSED,
                failure_count=new_count,
                last_failure_time=now,
                opened_at=None
            )

    def get_status(self, adapter_key: str) -> CircuitStatus:
        return self._get_status(adapter_key)

    def get_open_circuits(self) -> Dict[str, CircuitStatus]:
        return {
            key: status
            for key, status in self._circuits.items()
            if status.state == CircuitState.OPEN
        }

    def reset(self, adapter_key: str):
        if adapter_key in self._circuits:
            del self._circuits[adapter_key]

    def reset_all(self):
        self._circuits.clear()

    def _get_status(self, adapter_key: str) -> CircuitStatus:
        if adapter_key not in self._circuits:
            self._circuits[adapter_key] = CircuitStatus(
                state=CircuitState.CLOSED,
                failure_count=0,
                last_failure_time=None,
                opened_at=None
            )
        return self._circuits[adapter_key]

    def _transition_to_half_open(self, adapter_key: str):
        status = self._get_status(adapter_key)
        self._circuits[adapter_key] = CircuitStatus(
            state=CircuitState.HALF_OPEN,
            failure_count=status.failure_count,
            last_failure_time=status.last_failure_time,
            opened_at=None
        )

    def get_summary(self) -> str:
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

_default_breaker: Optional[CircuitBreaker] = None

def get_default_circuit_breaker() -> CircuitBreaker:
    global _default_breaker
    if _default_breaker is None:
        _default_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=300.0,
            half_open_timeout=60.0
        )
    return _default_breaker

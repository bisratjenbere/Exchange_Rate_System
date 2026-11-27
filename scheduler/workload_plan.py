from dataclasses import dataclass
from typing import List

from domain.source import RateSource


@dataclass(frozen=True)
class WorkloadPlan:
    queues: List[List[RateSource]]
    worker_times: List[float]

    # Sequence protocol so tests can do len(plan) and plan[i]
    def __len__(self) -> int:
        return len(self.queues)

    def __getitem__(self, idx):
        return self.queues[idx]

    def __iter__(self):
        return iter(self.queues)

    @property
    def num_workers(self) -> int:
        return len(self.queues)

    @property
    def total_sources(self) -> int:
        return sum(len(q) for q in self.queues)

    def summary(self) -> dict:
        times = self.worker_times
        max_time = max(times) if times else 0.0
        min_time = min(times) if times else 0.0
        avg_time = sum(times) / len(times) if times else 0.0
        imbalance = (max_time - min_time) / max_time if max_time > 0 else 0.0
        return {
            "num_workers": self.num_workers,
            "total_sources": self.total_sources,
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

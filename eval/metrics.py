"""Evaluation metrics with mandatory conditioning (spec §43).

Every metric must state its measurement condition (REQ-EVAL-001):
``E2E`` / ``|mention`` / ``|candidate`` / ``|commit``. Conformance is
reported as a *failure count*, never merged into coverage percentages
(REQ-LVL-003, §3.5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

CONDITIONS = {"E2E", "|mention", "|candidate", "|commit"}


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (§43.8)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


@dataclass
class Metric:
    name: str
    conditioning: str
    hits: int
    total: int

    @property
    def value(self) -> float:
        return self.hits / self.total if self.total else 0.0

    @property
    def ci95(self) -> tuple[float, float]:
        return wilson_interval(self.hits, self.total)

    def to_dict(self) -> dict:
        lo, hi = self.ci95
        return {
            "name": self.name,
            "conditioning": self.conditioning,
            "value": round(self.value, 4),
            "hits": self.hits,
            "total": self.total,
            "ci95": [round(lo, 4), round(hi, 4)],
        }


@dataclass
class EvalReport:
    metrics: list[Metric] = field(default_factory=list)
    # §3.5: conformance is failure-count based, kept apart from coverage
    conformance: dict = field(default_factory=dict)
    slices: dict[str, list[Metric]] = field(default_factory=dict)

    def add_metric(self, name: str, conditioning: str, hits: int, total: int,
                   slice_key: str | None = None) -> Metric:
        if conditioning not in CONDITIONS:
            raise ValueError(
                f"metric {name!r}: conditioning must be one of {sorted(CONDITIONS)} "
                f"(REQ-EVAL-001), got {conditioning!r}"
            )
        if "conformance" in name.lower():
            raise ValueError(
                "conformance is failure-count based and must not be reported "
                "as a coverage metric (REQ-LVL-003); use set_conformance()"
            )
        m = Metric(name, conditioning, hits, total)
        if slice_key is None:
            self.metrics.append(m)
        else:
            self.slices.setdefault(slice_key, []).append(m)
        return m

    def set_conformance(self, total: int, failed: int,
                        failures: list | None = None) -> None:
        self.conformance = {
            "total_fixtures": total,
            "failure_count": failed,  # target: 0 (REQ-LVL-002)
            "failures": failures or [],
        }

    def to_dict(self) -> dict:
        return {
            "conformance": self.conformance,
            "metrics": [m.to_dict() for m in self.metrics],
            "slices": {k: [m.to_dict() for m in v]
                       for k, v in self.slices.items()},
        }

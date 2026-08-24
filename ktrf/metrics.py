"""Runtime observability (spec §46.1).

A lightweight metrics registry: counters and bounded-reservoir latency
observations, exposed as a snapshot dict for scraping. Logging follows the
§46.3 privacy defaults — nothing here ever stores document text; only
counts, latencies and version identifiers.
"""

from __future__ import annotations

import random
from threading import Lock

_RESERVOIR = 512


class RuntimeMetrics:
    def __init__(self):
        self._counters: dict[str, int] = {}
        self._observations: dict[str, list[float]] = {}
        self._seen: dict[str, int] = {}
        self._lock = Lock()
        self._rng = random.Random(0)

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + by

    def observe(self, name: str, value: float) -> None:
        """Reservoir-sampled observation (bounded memory)."""
        with self._lock:
            lst = self._observations.setdefault(name, [])
            self._seen[name] = self._seen.get(name, 0) + 1
            if len(lst) < _RESERVOIR:
                lst.append(value)
            else:
                i = self._rng.randrange(self._seen[name])
                if i < _RESERVOIR:
                    lst[i] = value

    def record_resolve(self, mode: str, latency_ms: float, response: dict,
                       trace: dict | None = None) -> None:
        """§46.1: per-mode request counts/latency, degraded and Pass-2 rate."""
        self.incr(f"resolve.{mode}.requests")
        self.observe(f"resolve.{mode}.latency_ms", latency_ms)
        if response.get("degraded"):
            self.incr(f"resolve.{mode}.degraded")
        self.incr("mentions.returned", len(response.get("mentions", [])))
        for m in response.get("mentions", []):
            link = m.get("link_decision")
            if link:
                self.incr(f"link_decision.{link}")
        if trace and trace.get("pass2_executed"):
            self.incr("pass2.executed")

    def to_dict(self) -> dict:
        with self._lock:
            out: dict = {"counters": dict(self._counters), "latency": {}}
            for name, lst in self._observations.items():
                if not lst:
                    continue
                s = sorted(lst)
                out["latency"][name] = {
                    "count": self._seen[name],
                    "p50": round(s[len(s) // 2], 2),
                    "p95": round(s[int(len(s) * 0.95)], 2),
                }
            return out

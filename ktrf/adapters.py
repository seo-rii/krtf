"""Tenant adapter GPU residency (spec §32.3, docs/GPU_PLAN.md Phase G3).

Tenant adapters (LoRA and future per-tenant modules, §48.4) are CPU-resident
by default; a bounded number of GPU slots is managed with LRU replacement.
The movement itself is delegated to ``to_gpu`` / ``to_cpu`` callables (for a
torch adapter: ``lambda a: a.to("cuda")``), so the policy layer stays
dependency-free and testable. An adapter referenced by an in-flight request
is refcount-protected and never demoted mid-use — the same protection
contract as snapshot tiers (REQ-MEM-002 analog).

The shared base model is out of scope here (§12: one copy across tenants;
candidate/result isolation is enforced elsewhere).
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from threading import RLock


class AdapterResidencyManager:
    def __init__(self, max_gpu_slots: int = 2, to_gpu=None, to_cpu=None,
                 metrics=None):
        self.max_gpu_slots = max_gpu_slots
        self._to_gpu = to_gpu or (lambda a: a)
        self._to_cpu = to_cpu or (lambda a: a)
        self.metrics = metrics
        self._cpu: dict[str, object] = {}
        self._gpu: OrderedDict[str, object] = OrderedDict()
        self._refcounts: dict[str, int] = {}
        self._pinned: set[str] = set()
        self._lock = RLock()
        self.stats = {"promotions": 0, "demotions": 0,
                      "demotion_skipped_refcount": 0}

    def register(self, tenant_id: str, adapter) -> None:
        """Adapters enter at the CPU tier (§32.3 기본 CPU 상주)."""
        with self._lock:
            self._cpu[tenant_id] = adapter

    def unregister(self, tenant_id: str) -> None:
        with self._lock:
            if self._refcounts.get(tenant_id, 0) > 0:
                raise RuntimeError(
                    f"adapter {tenant_id!r} is in use and cannot be removed")
            self._cpu.pop(tenant_id, None)
            self._gpu.pop(tenant_id, None)

    def pin(self, tenant_id: str) -> None:
        with self._lock:
            self._pinned.add(tenant_id)

    def tier_of(self, tenant_id: str) -> str:
        with self._lock:
            if tenant_id in self._gpu:
                return "gpu"
            if tenant_id in self._cpu:
                return "cpu"
            return "absent"

    @contextmanager
    def acquire(self, tenant_id: str):
        """Yield the tenant's adapter promoted to a GPU slot.

        While held, the adapter is refcount-protected against demotion.
        Promotion failure is not possible policy-side: when every slot is
        protected, the manager over-subscribes rather than fail the request
        (mirrors the snapshot-tier overflow rule).
        """
        adapter = self._promote(tenant_id)
        try:
            yield adapter
        finally:
            with self._lock:
                self._refcounts[tenant_id] -= 1

    def _promote(self, tenant_id: str):
        with self._lock:
            if tenant_id in self._gpu:
                self._gpu.move_to_end(tenant_id)
            else:
                if tenant_id not in self._cpu:
                    raise KeyError(f"no adapter registered for {tenant_id!r}")
                self._evict_for_slot()
                self._gpu[tenant_id] = self._to_gpu(self._cpu[tenant_id])
                self.stats["promotions"] += 1
                if self.metrics is not None:
                    self.metrics.incr("adapter.promotions")
            self._refcounts[tenant_id] = self._refcounts.get(tenant_id, 0) + 1
            return self._gpu[tenant_id]

    def _evict_for_slot(self) -> None:
        while len(self._gpu) >= self.max_gpu_slots:
            victim = None
            for tid in self._gpu:  # LRU order
                if tid in self._pinned:
                    continue
                if self._refcounts.get(tid, 0) > 0:
                    self.stats["demotion_skipped_refcount"] += 1
                    continue
                victim = tid
                break
            if victim is None:
                return  # all protected: over-subscribe
            self._cpu[victim] = self._to_cpu(self._gpu.pop(victim))
            self.stats["demotions"] += 1
            if self.metrics is not None:
                self.metrics.incr("adapter.demotions")

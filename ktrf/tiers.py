"""Snapshot memory tiers: hot / warm(cold-on-disk) residency (spec §32).

Python analog of the §32.1 tier model:

- **hot**: fully compiled snapshot resident in memory (LRU-bounded);
- **cold**: artifact bundle on disk (`ktrf.artifacts`), recompiled on demand
  (cold start is measured and exposed, §46.1/OQ-004).

Eviction is LRU, but a snapshot referenced by an active request is refcount-
protected and never evicted (REQ-MEM-002). ``warm()`` is the §32.4 best-
effort promotion API. The distinct mmap-backed "warm" tier of the production
spec collapses into the disk tier here (REQ-MEM-001 is Rust-core scope).
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from .artifacts import load_snapshot, save_snapshot
from .errors import KtrfApiError
from .snapshot import Snapshot


class TieredSnapshotStore:
    def __init__(self, cold_dir: str | Path, max_hot: int = 8, metrics=None,
                 model_resolver=None):
        """``model_resolver(manifest) -> (encoder, reranker)`` supplies the
        neural backends a cold load needs.

        A bundle carrying entity vectors cannot be loaded without the encoder
        that produced them (§11.3), and the cold path called ``load_snapshot``
        with none. A dense tenant therefore activated fine, served fine, and
        raised SNAPSHOT_UNAVAILABLE the first time it was evicted and asked
        for again — the eviction turned a working tenant into a broken one.

        Two ways in, because there are two cold starts. Within a process the
        store already saw the live objects at ``activate`` and remembers them.
        Across a restart there is nothing to remember, and the manifest names
        model ids rather than holding models, so a resolver has to map them.
        """
        self.cold_dir = Path(cold_dir)
        self.max_hot = max_hot
        self.metrics = metrics
        self.model_resolver = model_resolver
        self._hot: OrderedDict[str, Snapshot] = OrderedDict()
        self._models: dict[str, tuple] = {}
        self._cold: dict[str, Path] = {}
        self._refcounts: dict[str, int] = {}
        self._pinned: set[str] = set()
        self._lock = RLock()
        self.stats = {"cold_starts": 0, "evictions": 0,
                      "eviction_skipped_refcount": 0}

    # -- activation ----------------------------------------------------------

    def activate(self, snapshot: Snapshot) -> None:
        """Persist the bundle (cold layer) and promote to hot atomically."""
        bundle = self.cold_dir / snapshot.tenant_id
        save_snapshot(snapshot, bundle)
        with self._lock:
            self._cold[snapshot.tenant_id] = bundle
            # keep the live backends: they are what a later cold load needs,
            # and this is the only moment the store is holding them
            encoder = snapshot.dense.encoder if snapshot.dense else None
            if encoder is not None or snapshot.reranker is not None:
                self._models[snapshot.tenant_id] = (encoder, snapshot.reranker)
            self._put_hot(snapshot.tenant_id, snapshot)

    def pin(self, tenant_id: str) -> None:
        """Operator pin: tenant never leaves the hot tier (§32.1)."""
        with self._lock:
            self._pinned.add(tenant_id)

    def warm(self, tenant_id: str) -> bool:
        """§32.4 warm-up: best-effort hot promotion; failure is not an error."""
        try:
            with self.acquire(tenant_id):
                return True
        except KtrfApiError:
            return False

    # -- access --------------------------------------------------------------

    @contextmanager
    def acquire(self, tenant_id: str):
        """Yield the tenant's active snapshot with refcount protection.

        While held, the snapshot cannot be evicted (REQ-MEM-002).
        """
        snap = self._checkout(tenant_id)
        try:
            yield snap
        finally:
            with self._lock:
                self._refcounts[snap.snapshot_id] -= 1

    def _checkout(self, tenant_id: str) -> Snapshot:
        with self._lock:
            snap = self._hot.get(tenant_id)
            if snap is not None:
                self._hot.move_to_end(tenant_id)  # LRU touch
            else:
                bundle = self._cold.get(tenant_id)
                if bundle is None:
                    raise KtrfApiError("GLOSSARY_NOT_FOUND",
                                       f"no snapshot for tenant {tenant_id!r}")
                t0 = time.perf_counter()
                encoder, reranker = self._backends_for(tenant_id, bundle)
                snap = load_snapshot(bundle, encoder=encoder,
                                     reranker=reranker)
                self.stats["cold_starts"] += 1
                if self.metrics is not None:
                    self.metrics.observe(
                        "cold_start_ms", 1000 * (time.perf_counter() - t0))
                self._put_hot(tenant_id, snap)
            self._refcounts[snap.snapshot_id] = \
                self._refcounts.get(snap.snapshot_id, 0) + 1
            return snap

    def _backends_for(self, tenant_id: str, bundle: Path) -> tuple:
        """(encoder, reranker) for a cold load, or (None, None) if the bundle
        does not need any."""
        remembered = self._models.get(tenant_id)
        if remembered is not None:
            return remembered
        if self.model_resolver is None:
            return (None, None)
        try:
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return (None, None)
        resolved = self.model_resolver(manifest)
        return resolved if resolved else (None, None)

    def tier_of(self, tenant_id: str) -> str:
        with self._lock:
            if tenant_id in self._hot:
                return "hot"
            if tenant_id in self._cold:
                return "cold"
            return "absent"

    # -- eviction -------------------------------------------------------------

    def _put_hot(self, tenant_id: str, snap: Snapshot) -> None:
        self._hot[tenant_id] = snap
        self._hot.move_to_end(tenant_id)
        while len(self._hot) > self.max_hot:
            victim = self._pick_victim()
            if victim is None:
                break  # every candidate is pinned or in use: allow overflow
            evicted = self._hot.pop(victim)
            self.stats["evictions"] += 1
            if self.metrics is not None:
                self.metrics.incr("tier_evictions")
            del evicted

    def _pick_victim(self) -> str | None:
        for tenant_id, snap in self._hot.items():  # LRU order
            if tenant_id in self._pinned:
                continue
            if self._refcounts.get(snap.snapshot_id, 0) > 0:
                # REQ-MEM-002: active requests protect the snapshot
                self.stats["eviction_skipped_refcount"] += 1
                continue
            return tenant_id
        return None

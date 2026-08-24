"""Adapter GPU residency tests (spec §32.3, GPU_PLAN Phase G3)."""

import pytest

from ktrf.adapters import AdapterResidencyManager
from ktrf.metrics import RuntimeMetrics


class FakeAdapter:
    def __init__(self, name):
        self.name = name
        self.device = "cpu"


def _mgr(slots=2):
    def to_gpu(a):
        a.device = "cuda"
        return a

    def to_cpu(a):
        a.device = "cpu"
        return a

    return AdapterResidencyManager(max_gpu_slots=slots, to_gpu=to_gpu,
                                   to_cpu=to_cpu, metrics=RuntimeMetrics())


def test_register_starts_cpu_resident():
    m = _mgr()
    m.register("t1", FakeAdapter("a1"))
    assert m.tier_of("t1") == "cpu"


def test_acquire_promotes_and_moves_device():
    m = _mgr()
    m.register("t1", FakeAdapter("a1"))
    with m.acquire("t1") as a:
        assert a.device == "cuda"
        assert m.tier_of("t1") == "gpu"
    assert m.stats["promotions"] == 1


def test_lru_demotion_under_slot_pressure():
    m = _mgr(slots=2)
    for t in ("a", "b", "c"):
        m.register(t, FakeAdapter(t))
        with m.acquire(t):
            pass
    # 'a' is LRU -> demoted back to CPU with device moved
    assert m.tier_of("a") == "cpu"
    assert m.tier_of("b") == "gpu" and m.tier_of("c") == "gpu"
    assert m.stats["demotions"] == 1


def test_refcount_blocks_demotion():
    # in-flight adapters are never demoted (REQ-MEM-002 analog)
    m = _mgr(slots=1)
    m.register("a", FakeAdapter("a"))
    m.register("b", FakeAdapter("b"))
    with m.acquire("a") as held:
        with m.acquire("b"):  # pressure while 'a' is held -> over-subscribe
            assert m.tier_of("a") == "gpu"
            assert held.device == "cuda"
        assert m.stats["demotion_skipped_refcount"] >= 1
    # over-subscription sheds lazily on the next promotion
    m.register("c", FakeAdapter("c"))
    with m.acquire("c"):
        pass
    assert "cpu" in (m.tier_of("a"), m.tier_of("b"))


def test_pinned_adapter_never_demoted():
    m = _mgr(slots=1)
    m.register("vip", FakeAdapter("vip"))
    with m.acquire("vip"):
        pass
    m.pin("vip")
    m.register("x", FakeAdapter("x"))
    with m.acquire("x"):
        pass
    assert m.tier_of("vip") == "gpu"


def test_unregister_in_use_refused():
    m = _mgr()
    m.register("t", FakeAdapter("t"))
    with m.acquire("t"):
        with pytest.raises(RuntimeError):
            m.unregister("t")
    m.unregister("t")
    assert m.tier_of("t") == "absent"


def test_unknown_tenant():
    m = _mgr()
    with pytest.raises(KeyError):
        with m.acquire("ghost"):
            pass

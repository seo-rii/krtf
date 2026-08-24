"""M3 tests: async job API (§28), memory tiers (§32), observability (§46.1).

REQ-API-006/INV-017 (single snapshot pin per job), REQ-MEM-002 (refcount-
protected eviction).
"""

import pytest

from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.jobs import ResolveJobManager, _chunk_boundaries
from ktrf.metrics import RuntimeMetrics
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot
from ktrf.tiers import TieredSnapshotStore


def _glossary(version="1"):
    return load_glossary({
        "glossary_id": "org-a", "version": version, "schema_version": "3",
        "entities": [{"entity_id": "E1", "canonical": "한국전력공사",
                      "description": "전력 공기업"}],
        "alias_families": [{"family_id": "F1", "representative": "한전",
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "A1", "family_id": "F1",
                            "entity_id": "E1", "surface": "한전"}],
    })


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(_glossary(), tenant_id="t1")


# ---------------------------------------------------------------------------
# async jobs (§28)
# ---------------------------------------------------------------------------


def test_chunk_boundaries_prefer_sentences():
    text = ("한전은 계획을 발표했다. " * 200)
    chunks = _chunk_boundaries(text, max_chunk_bytes=1024)
    assert len(chunks) > 3
    assert chunks[0][0] == 0 and chunks[-1][1] == len(text)
    for (s1, e1), (s2, e2) in zip(chunks, chunks[1:]):
        assert e1 == s2  # contiguous
    # cuts land after sentence breaks, not mid-word
    for _, e in chunks[:-1]:
        assert text[e - 1] in ". \n"


def test_job_lifecycle_and_global_offsets(snap):
    text = "한전은 계획을 발표했다. 이어서 한전 담당자가 브리핑했다. " * 120
    mgr = ResolveJobManager(max_chunk_bytes=512)
    sub = mgr.submit(snap, text, mode="commit")
    assert sub["status"] == "QUEUED"
    st = mgr.process(sub["job_id"])
    assert st["status"] == "SUCCEEDED"
    assert st["progress"]["chunks_done"] == st["progress"]["chunks_total"] > 1
    # paginate and verify global offsets (INV-002 on the full document)
    token = None
    got = 0
    while True:
        page = mgr.results(sub["job_id"], page_token=token, page_size=50)
        for m in page["mentions"]:
            cp = m["span"]["codepoint"]
            assert text[cp["start"]:cp["end"]] == m["surface"]
            got += 1
        token = page["next_page_token"]
        if token is None:
            break
    assert got == 2 * 120  # every 한전 across every chunk, no duplicates


def test_job_pins_snapshot_across_activation(snap):
    # INV-017/REQ-API-006: chunks after a new activation still use the pin
    text = "한전은 발표했다. " * 300
    mgr = ResolveJobManager(max_chunk_bytes=512)
    sub = mgr.submit(snap, text)
    mgr.process(sub["job_id"], max_chunks=1)
    v2 = compile_snapshot(_glossary("2"), tenant_id="t1")  # new active version
    assert v2.snapshot_id != snap.snapshot_id
    st = mgr.process(sub["job_id"])
    assert st["status"] == "SUCCEEDED"
    assert st["snapshot"]["snapshot_id"] == snap.snapshot_id
    assert st["snapshot"]["glossary_version"] == "1"


def test_job_cancel_between_chunks(snap):
    mgr = ResolveJobManager(max_chunk_bytes=256)
    sub = mgr.submit(snap, "한전 관련 문장. " * 500)
    mgr.process(sub["job_id"], max_chunks=1)
    st = mgr.cancel(sub["job_id"])
    assert st["status"] == "CANCELLED"
    st = mgr.process(sub["job_id"])  # no-op on terminal status
    assert st["status"] == "CANCELLED"


def test_job_input_limit(snap):
    mgr = ResolveJobManager(async_max_input_bytes=1024)
    with pytest.raises(KtrfApiError) as e:
        mgr.submit(snap, "가" * 1000)
    assert e.value.code == "INPUT_TOO_LARGE"


# ---------------------------------------------------------------------------
# memory tiers (§32)
# ---------------------------------------------------------------------------


def _mini_snap(tenant):
    g = load_glossary({
        "glossary_id": f"g-{tenant}", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "E1", "canonical": "한국전력공사"}],
        "alias_families": [{"family_id": "F1", "representative": "한전",
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "A1", "family_id": "F1",
                            "entity_id": "E1", "surface": "한전"}],
    })
    return compile_snapshot(g, tenant_id=tenant, run_conformance=False)


def test_tier_lru_eviction_and_cold_start(tmp_path):
    store = TieredSnapshotStore(tmp_path, max_hot=2)
    for t in ("a", "b", "c"):
        store.activate(_mini_snap(t))
    # LRU: 'a' evicted to cold
    assert store.tier_of("a") == "cold"
    assert store.tier_of("c") == "hot"
    with store.acquire("a") as s:  # cold start reload
        assert s.glossary.glossary_id == "g-a"
        r = resolve(s, "한전은 발표했다.", mode="fast")
        assert r["mentions"]
    assert store.stats["cold_starts"] == 1
    assert store.tier_of("a") == "hot"


def test_refcount_blocks_eviction(tmp_path):
    # REQ-MEM-002: an acquired snapshot survives eviction pressure
    store = TieredSnapshotStore(tmp_path, max_hot=1)
    store.activate(_mini_snap("a"))
    with store.acquire("a"):
        store.activate(_mini_snap("b"))  # pressure while 'a' is referenced
        assert store.tier_of("a") == "hot"  # protected
        assert store.stats["eviction_skipped_refcount"] >= 1
    store.activate(_mini_snap("c"))  # 'a' released now -> evictable
    assert store.tier_of("a") == "cold"


def test_pinned_tenant_never_evicted(tmp_path):
    store = TieredSnapshotStore(tmp_path, max_hot=1)
    store.activate(_mini_snap("vip"))
    store.pin("vip")
    for t in ("x", "y"):
        store.activate(_mini_snap(t))
    assert store.tier_of("vip") == "hot"


def test_warm_is_best_effort(tmp_path):
    store = TieredSnapshotStore(tmp_path, max_hot=4)
    store.activate(_mini_snap("a"))
    assert store.warm("a") is True
    assert store.warm("ghost") is False  # §32.4: failure is not an error


# ---------------------------------------------------------------------------
# metrics (§46.1)
# ---------------------------------------------------------------------------


def test_metrics_record_resolve(snap):
    m = RuntimeMetrics()
    resolve(snap, "한전은 발표했다.", mode="commit", metrics=m)
    resolve(snap, "한전 담당자 문의", mode="fast", metrics=m)
    d = m.to_dict()
    assert d["counters"]["resolve.commit.requests"] == 1
    assert d["counters"]["resolve.fast.requests"] == 1
    assert d["counters"]["mentions.returned"] >= 2
    assert "resolve.commit.latency_ms" in d["latency"]
    assert d["latency"]["resolve.commit.latency_ms"]["count"] == 1
    # privacy (§46.3): no document text anywhere in the metrics dump
    assert "한전" not in str(d)

"""Concurrency, hot-swap and rollback (§11.4, INV-014).

`SnapshotRegistry.activate` documents an atomic swap in which "the previous
snapshot always survives failures", and snapshots are shared by every request
for a tenant. None of that was covered: the registry had no test that ran two
threads at once, and no test that a *refused* activation leaves the tenant
serving what it was serving before.

These are correctness tests, not throughput tests. Under the GIL more threads
do not mean more parallelism, but they do mean interleaving — which is what a
torn read would need.
"""

import threading

import pytest

from eval.synthetic import build_synthetic_glossary
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import SnapshotRegistry, compile_snapshot


def _snapshot(seed, tenant_id="default"):
    doc, _meta = build_synthetic_glossary(120, seed=seed)
    return compile_snapshot(load_glossary(doc), tenant_id=tenant_id,
                            run_conformance=False)


@pytest.fixture(scope="module")
def pair():
    """Two snapshots whose entity ids overlap but whose *content* differs, so
    an answer can be traced back to the snapshot that produced it."""
    return _snapshot(1), _snapshot(2)


def _texts(snap, n=40):
    return [f"{b.surface}에 대해 확인했다"
            for b in snap.glossary.alias_bindings[:n]]


def _entity_ids(snap):
    return {e.entity_id for e in snap.glossary.entities}


def _answers(snap, texts):
    out = []
    for t in texts:
        r = resolve(snap, t, mode="commit")
        out.append(tuple((m["surface"], m.get("link_decision"))
                         for m in r["mentions"]))
    return out


# ---------------------------------------------------------------- concurrency


def test_the_same_snapshot_answers_the_same_way_on_many_threads(pair):
    """A sealed snapshot carries no per-request state, so sharing it across
    threads must not change a single answer."""
    snap, _ = pair
    texts = _texts(snap)
    expected = _answers(snap, texts)

    results, errors = {}, []

    def worker(i):
        try:
            results[i] = _answers(snap, texts)
        except Exception as exc:  # a crash is the interesting failure here
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(results) == 4
    for got in results.values():
        assert got == expected


# ------------------------------------------------------------------ hot swap


def test_a_hot_swap_never_hands_out_a_mixed_answer(pair):
    """Readers take a reference and keep it; the swap replaces the registry
    entry, not the object. An answer must therefore name entities from the
    snapshot that produced it and never a mixture of the two."""
    a, b = pair
    reg = SnapshotRegistry()
    reg.activate(a, allow_unverified=True)
    ids = {a.snapshot_id: _entity_ids(a), b.snapshot_id: _entity_ids(b)}
    texts = _texts(a, 12) + _texts(b, 12)

    stop = threading.Event()
    violations, errors = [], []

    def reader():
        try:
            while not stop.is_set():
                snap = reg.get_active("default")
                for t in texts:
                    r = resolve(snap, t, mode="commit")
                    for m in r["mentions"]:
                        for c in m.get("candidates") or []:
                            if c["entity_id"] not in ids[snap.snapshot_id]:
                                violations.append((snap.snapshot_id,
                                                   c["entity_id"]))
        except Exception as exc:
            errors.append(exc)

    def swapper():
        try:
            for i in range(12):
                reg.activate(b if i % 2 == 0 else a, allow_unverified=True)
        except Exception as exc:
            errors.append(exc)
        finally:
            stop.set()

    readers = [threading.Thread(target=reader) for _ in range(3)]
    swap = threading.Thread(target=swapper)
    for t in readers:
        t.start()
    swap.start()
    swap.join()
    for t in readers:
        t.join(timeout=30)

    assert not errors, errors
    assert not violations, violations[:5]


def test_the_registry_always_holds_a_complete_snapshot(pair):
    """`get_active` during a storm of swaps must never return None or a
    half-built object — the swap is one assignment, under the lock."""
    a, b = pair
    reg = SnapshotRegistry()
    reg.activate(a, allow_unverified=True)
    seen, errors = set(), []
    stop = threading.Event()

    def reader():
        try:
            while not stop.is_set():
                snap = reg.get_active("default")
                assert snap.snapshot_id and snap.glossary is not None
                seen.add(snap.snapshot_id)
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=reader)
    t.start()
    for i in range(200):
        reg.activate(b if i % 2 == 0 else a, allow_unverified=True)
    stop.set()
    t.join(timeout=30)
    assert not errors, errors
    assert seen <= {a.snapshot_id, b.snapshot_id}


# ------------------------------------------------- INV-014 and rollback


def test_a_refused_activation_leaves_the_tenant_serving_what_it_served(pair):
    """INV-014. The registry's own docstring claims this and nothing checked
    it — including for the integrity refusal added with `verify_integrity`."""
    a, b = pair
    reg = SnapshotRegistry()
    reg.activate(a, allow_unverified=True)

    bad = _snapshot(3)
    bad.glossary.entities[0].canonical = "TAMPERED"
    with pytest.raises(KtrfApiError, match="no longer matches its id"):
        reg.activate(bad, allow_unverified=True)
    assert reg.get_active("default").snapshot_id == a.snapshot_id

    unverified = _snapshot(4)
    with pytest.raises(KtrfApiError, match="conformance"):
        reg.activate(unverified)          # no conformance record, no escape
    assert reg.get_active("default").snapshot_id == a.snapshot_id


def test_rollback_is_just_activating_the_previous_snapshot(pair):
    """Nothing about a swap consumes the snapshot it replaced, so rolling
    back is the same operation in the other direction."""
    a, b = pair
    reg = SnapshotRegistry()
    reg.activate(a, allow_unverified=True)
    reg.activate(b, allow_unverified=True)
    assert reg.get_active("default").snapshot_id == b.snapshot_id
    reg.activate(a, allow_unverified=True)
    assert reg.get_active("default").snapshot_id == a.snapshot_id
    assert _answers(reg.get_active("default"), _texts(a, 5)) == \
        _answers(a, _texts(a, 5))


def test_tenants_do_not_see_each_other_across_a_swap():
    """§12.1: activation is per tenant; swapping one must not move another.

    Built fresh rather than retagged: a sealed snapshot's tenant is not
    something a caller may change, which is the point of the seal.
    """
    a, b = _snapshot(1, "t1"), _snapshot(2, "t2")
    reg = SnapshotRegistry()
    reg.activate(a, allow_unverified=True)
    reg.activate(b, allow_unverified=True)
    assert reg.get_active("t1").snapshot_id == a.snapshot_id
    assert reg.get_active("t2").snapshot_id == b.snapshot_id
    with pytest.raises(KtrfApiError, match="no active snapshot"):
        reg.get_active("t3")

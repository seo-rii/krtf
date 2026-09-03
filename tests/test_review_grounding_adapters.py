"""Two more defects from the external review: a grounding gate that let a
fabricated mention through, and an adapter tier that kept serving a
superseded copy."""

import pytest

from ktrf.adapters import AdapterResidencyManager
from ktrf.context import build_context_pack, validate_llm_grounding
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def pack():
    snap = compile_snapshot(load_glossary("examples/realorg_glossary.yaml"))
    return build_context_pack(snap, resolve(snap, "금융감독원이 조사했다",
                                            mode="commit"))


def test_a_surface_the_pack_never_offered_is_a_violation(pack):
    """The entity-id check passed, and the surface checks only constrained a
    surface already in the pack — so a fabricated mention carrying a real
    entity id produced no violation at all. That is the shape this gate
    exists to catch: an LLM asserting it grounded a span nobody gave it.
    """
    eid = pack["resolved_terms"][0]["entity_id"]
    res = validate_llm_grounding(
        {"selections": [{"surface": "전혀없는표면", "entity_id": eid}]}, pack)
    assert not res["valid"]
    assert [v["kind"] for v in res["violations"]] == ["unknown_surface"]


def test_a_surface_the_pack_did_offer_still_passes(pack):
    card = pack["resolved_terms"][0]
    surface = card["mentions"][0]["surface"]
    res = validate_llm_grounding(
        {"selections": [{"surface": surface,
                         "entity_id": card["entity_id"]}]}, pack)
    assert res["valid"], res["violations"]


def test_a_fabricated_entity_id_is_still_reported_as_such(pack):
    res = validate_llm_grounding(
        {"selections": [{"surface": "전혀없는표면",
                         "entity_id": "ORG_DOES_NOT_EXIST"}]}, pack)
    assert [v["kind"] for v in res["violations"]] == ["unknown_entity_id"]


# ---------------------------------------------------------------- adapters


def test_re_registering_replaces_the_resident_copy():
    """`register` wrote only to the CPU tier, so a tenant with a resident GPU
    copy kept being served the previous adapter — and every use refreshed its
    LRU position, so under steady traffic it never aged out."""
    mgr = AdapterResidencyManager()
    mgr.register("t1", "adapter-v1")
    with mgr.acquire("t1") as first:
        assert first == "adapter-v1"
    mgr.register("t1", "adapter-v2")
    with mgr.acquire("t1") as second:
        assert second == "adapter-v2"


def test_a_live_request_keeps_the_adapter_it_started_with():
    """Replacement must not demote an adapter out from under an in-flight
    request — the protection contract the refcount exists for."""
    moved = []
    mgr = AdapterResidencyManager(to_cpu=lambda a: moved.append(a) or a)
    mgr.register("t1", "adapter-v1")
    with mgr.acquire("t1") as held:
        mgr.register("t1", "adapter-v2")
        assert held == "adapter-v1"
        assert moved == [], "the in-use copy was moved off the GPU"
    with mgr.acquire("t1") as after:
        assert after == "adapter-v2"


def test_replacing_a_resident_copy_does_not_evict_another_tenant():
    mgr = AdapterResidencyManager(max_gpu_slots=2)
    mgr.register("t1", "v1")
    mgr.register("t2", "other")
    with mgr.acquire("t1"):
        pass
    with mgr.acquire("t2"):
        pass
    mgr.register("t1", "v2")
    with mgr.acquire("t1") as a:
        assert a == "v2"
    assert mgr.tier_of("t2") == "gpu", "an unrelated tenant lost its slot"

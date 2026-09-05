"""One bad request must not end the session, and eviction must not break a
tenant.

The sidecar's dispatch was documented as "never raises" and did: the handler
lookup sat outside the try, and a dict lookup on an unhashable key raises. A
line carrying `"method": []` took the process down, and the `health` request
on the next line was never answered.

The tier store loaded cold bundles with no encoder. A dense tenant activated,
served, was evicted under LRU pressure, and then raised SNAPSHOT_UNAVAILABLE
for every later request — the eviction turned a working tenant into a broken
one, and nothing about the tenant had changed.
"""

import io
import json

import pytest

from ktrf.encoders import HashEncoder
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot
from ktrf.tiers import TieredSnapshotStore

GLOSSARY = "examples/realorg_glossary.yaml"


def _small_glossary(eid="E_ONE"):
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": eid, "canonical": "한국전력공사",
                      "description": "전력 공기업"}],
        "alias_families": [{"family_id": "F", "representative": "한전",
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "A", "family_id": "F",
                            "entity_id": eid, "surface": "한전"}],
    })


# ------------------------------------------------------------- the sidecar

def _serve(lines):
    from ktrf.integrations import pi_stdio

    out = io.StringIO()
    pi_stdio.serve(stdin=io.StringIO("".join(l + "\n" for l in lines)),
                   stdout=out)
    return [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]


@pytest.mark.parametrize("method", ["[]", "{}", "5", "null", "true"])
def test_a_non_string_method_is_answered_not_raised(method):
    replies = _serve([f'{{"id":1,"method":{method}}}',
                      '{"id":2,"method":"health"}'])
    assert len(replies) == 2
    assert replies[0]["error"]["code"] == "INVALID_REQUEST"
    # the whole point: the next request still gets served
    assert replies[1]["id"] == 2
    assert "result" in replies[1]


def test_non_object_params_are_answered_not_raised():
    replies = _serve(['{"id":1,"method":"health","params":[]}',
                      '{"id":2,"method":"health"}'])
    assert replies[0]["error"]["code"] == "INVALID_REQUEST"
    assert "result" in replies[1]


def test_an_unhashable_id_does_not_break_the_reply():
    replies = _serve(['{"id":[1,2],"method":"health"}'])
    assert len(replies) == 1
    assert replies[0]["id"] is None
    assert "result" in replies[0]


def test_a_malformed_line_is_still_isolated():
    replies = _serve(["not json at all", '{"id":2,"method":"health"}'])
    assert replies[0]["error"]["code"] == "MALFORMED_REQUEST"
    assert "result" in replies[1]


def test_an_unknown_method_still_lists_the_known_ones():
    replies = _serve(['{"id":1,"method":"no_such_method"}'])
    assert replies[0]["error"]["code"] == "UNKNOWN_METHOD"
    assert "health" in replies[0]["error"]["known"]


def test_an_oversize_line_is_rejected_and_the_next_one_is_served():
    from ktrf.integrations.pi_stdio import MAX_REQUEST_BYTES

    huge = '{"id":1,"method":"health","params":{"x":"' \
           + "a" * (MAX_REQUEST_BYTES + 100) + '"}}'
    replies = _serve([huge, '{"id":2,"method":"health"}'])
    assert replies[0]["error"]["code"] == "INPUT_TOO_LARGE"
    assert replies[1]["id"] == 2


# ------------------------------------------------------------ the tiers

def test_a_dense_tenant_survives_being_evicted(tmp_path):
    store = TieredSnapshotStore(tmp_path, max_hot=1)
    store.activate(compile_snapshot(_small_glossary(), encoder=HashEncoder(),
                                    tenant_id="t1"))
    store.activate(compile_snapshot(load_glossary(GLOSSARY), tenant_id="t2"))
    assert store.tier_of("t1") == "cold", "fixture must actually evict"
    with store.acquire("t1") as snap:
        assert snap.dense is not None
    assert store.stats["cold_starts"] >= 1


def test_a_symbolic_tenant_still_cold_starts_without_any_backend(tmp_path):
    store = TieredSnapshotStore(tmp_path, max_hot=1)
    store.activate(compile_snapshot(_small_glossary(), tenant_id="t1"))
    store.activate(compile_snapshot(load_glossary(GLOSSARY), tenant_id="t2"))
    with store.acquire("t1") as snap:
        assert snap.dense is None


def test_a_resolver_supplies_backends_the_store_never_saw(tmp_path):
    # the restart case: nothing was activated in this process, so there is
    # nothing to remember and the manifest names ids rather than objects
    seeding = TieredSnapshotStore(tmp_path, max_hot=8)
    seeding.activate(compile_snapshot(_small_glossary(), encoder=HashEncoder(),
                                      tenant_id="t1"))
    seen = {}

    def resolver(manifest):
        seen["encoder_hash"] = manifest.get("entity_encoder_hash")
        return (HashEncoder(), None)

    fresh = TieredSnapshotStore(tmp_path, max_hot=8, model_resolver=resolver)
    fresh._cold["t1"] = tmp_path / "t1"
    with fresh.acquire("t1") as snap:
        assert snap.dense is not None
    assert seen["encoder_hash"] is not None


def test_without_a_resolver_the_restart_case_still_fails_loudly(tmp_path):
    seeding = TieredSnapshotStore(tmp_path, max_hot=8)
    seeding.activate(compile_snapshot(_small_glossary(), encoder=HashEncoder(),
                                      tenant_id="t1"))
    fresh = TieredSnapshotStore(tmp_path, max_hot=8)
    fresh._cold["t1"] = tmp_path / "t1"
    with pytest.raises(KtrfApiError) as e:
        with fresh.acquire("t1"):
            pass
    assert e.value.to_dict()["error"]["code"] == "SNAPSHOT_UNAVAILABLE"

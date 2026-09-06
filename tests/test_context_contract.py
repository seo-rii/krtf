"""A pack has to be able to say what produced it (§16.8).

`pack_id` is the cache key and the audit record. It was a hash of the pack's
content and the pack carried `policy_version` — a hand-written constant that
did not move when the policy did. So a pack built with `allow_degraded_
resolved=True` and one built without it came back with the same id whenever
their content happened to coincide, and nothing in either could tell them
apart afterwards.
"""

import dataclasses

import pytest

from ktrf.context import ContextPolicy, build_context_pack
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"
TEXT = ("금융감독원이 조사에 착수했다. 한국전력공사는 입장을 냈다. "
        "금감원은 추가 검토가 필요하다고 밝혔다.")


@pytest.fixture(scope="module")
def snapshot():
    return compile_snapshot(load_glossary(GLOSSARY))


@pytest.fixture(scope="module")
def response(snapshot):
    return resolve(snapshot, TEXT, mode="commit",
                   options={"return_all_mentions": True})


def _pack(snapshot, response, **kw):
    return build_context_pack(snapshot, response, query="금감원은 무엇인가",
                              policy=ContextPolicy(**kw))


# --------------------------------------------------------------- policy id

@pytest.mark.parametrize("change", [
    {"max_entities": 30},
    {"max_description_chars": 90},
    {"max_candidates_per_mention": 5},
    {"allow_degraded_resolved": True},
    {"include_numeric_probabilities": True},
    {"classification_clearance": "public"},
    {"ambiguity_scope": "all"},
    {"include_unknown_mentions": True},
    {"query_aware": False},
    {"expose_entity_ids": False},
    {"max_tokens": 4000},
    {"profile": "summarization"},
])
def test_a_different_policy_is_a_different_pack(snapshot, response, change):
    """Every field, not the ones that happen to change the body."""
    assert _pack(snapshot, response)["pack_id"] != _pack(
        snapshot, response, **change)["pack_id"], change


def test_the_same_policy_is_the_same_pack(snapshot, response):
    assert _pack(snapshot, response)["pack_id"] == _pack(
        snapshot, response)["pack_id"]


def test_the_pack_names_the_policy_that_built_it(snapshot, response):
    policy = ContextPolicy(allow_degraded_resolved=True)
    pack = build_context_pack(snapshot, response, policy=policy)
    assert pack["policy_id"] == policy.policy_id
    assert pack["policy_id"].startswith(policy.version + "-")
    assert pack["policy_id"] != ContextPolicy().policy_id


def test_every_field_is_in_the_policy_id():
    """A field added later is covered without anyone remembering to add it."""
    base = ContextPolicy()
    for name, f in ContextPolicy.__dataclass_fields__.items():
        current = getattr(base, name)
        other = {"profile": "summarization", "ambiguity_scope": "all",
                 "classification_clearance": "public",
                 "version": "ctxpol-test"}.get(
                     name,
                     (not current) if isinstance(current, bool)
                     else (current + 1 if isinstance(current, int) else None))
        if other is None or other == current:
            continue
        changed = dataclasses.replace(base, **{name: other})
        assert changed.policy_id != base.policy_id, name


# ----------------------------------------------------------- bad requests

def test_an_unknown_option_is_refused_the_way_every_other_one_is():
    with pytest.raises(KtrfApiError) as e:
        ContextPolicy.from_options({"max_tokens": 400, "clearence": "public"})
    assert e.value.code == "INVALID_REQUEST"
    assert "clearence" in str(e.value)


def test_a_known_option_still_builds():
    assert ContextPolicy.from_options({"max_tokens": 400}).max_tokens == 400
    assert ContextPolicy.from_options(None) == ContextPolicy()


def test_options_that_are_not_an_object_are_refused():
    with pytest.raises(KtrfApiError):
        ContextPolicy.from_options(["max_tokens", 400])


@pytest.mark.parametrize("bad", [0, -5, 1.5, True, "800", None])
def test_an_unusable_budget_is_an_api_error(bad):
    with pytest.raises(KtrfApiError):
        ContextPolicy(max_tokens=bad)

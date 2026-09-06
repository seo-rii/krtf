"""Properties a ContextPack has to hold for any text and any policy (§16.7).

The fixed-input tests pin the cases someone thought of. These pin the shape
of the contract itself: whatever the document says and whatever the policy
asks for, the pack parses, hashes the same twice, stays inside its budget,
invents no entity, repeats none, keeps every span inside the text, and
records whatever it dropped. A field added next quarter is covered by the
structural ones without anyone editing this file.
"""

import json
import xml.etree.ElementTree as ET

import pytest

from ktrf.context import (
    ContextPolicy,
    PROFILES,
    build_context_pack,
    render_context_pack,
)
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")
from hypothesis import given, settings  # noqa: E402

GLOSSARY = "examples/realorg_glossary.yaml"

# The snapshot is fetched inside the tests rather than drawn: hypothesis
# reprs its arguments on failure and a whole snapshot buries the one value
# that broke.
_SNAP = None


def _snap():
    global _SNAP
    if _SNAP is None:
        _SNAP = compile_snapshot(load_glossary(GLOSSARY))
    return _SNAP


# Real surfaces, so most documents actually resolve something; arbitrary
# unicode alongside, so the sanitizer is exercised rather than bypassed.
#
# The near-misses and the definition are not decoration. Drawn from clean
# surfaces alone, 300 documents produced 243 packs with resolved terms and
# not one ambiguous mention, unknown mention or document definition — so
# every property about those branches passed without reaching them.
# `test_the_documents_reach_every_branch` keeps that honest.
_SURFACES = ["한국전력공사", "한전", "금융감독원", "금감원", "과기정통부",
             "한전노조", "금감원장", "국토교통부"]
_NEAR_MISSES = ["한국전려공사", "금유감독원", "과기정통부처", "국토교퉁부"]
_DEFINITIONS = ['한국전력공사(이하 "한전")가 발표했다',
                "금융감독원(이하 금감원)이 조사했다"]
_FRAGMENT = (st.sampled_from(_SURFACES) | st.sampled_from(_NEAR_MISSES)
             | st.sampled_from(_DEFINITIONS) | st.text(max_size=30))
_TEXT = st.lists(_FRAGMENT, max_size=8).map(lambda xs: " ".join(xs))

_POLICY = st.builds(
    ContextPolicy,
    profile=st.sampled_from(PROFILES),
    max_tokens=st.integers(min_value=1, max_value=2000),
    max_entities=st.integers(min_value=1, max_value=30),
    max_candidates_per_mention=st.integers(min_value=1, max_value=5),
    max_description_chars=st.integers(min_value=1, max_value=300),
    include_ambiguous=st.booleans(),
    include_unknown_mentions=st.booleans(),
    query_aware=st.booleans(),
    ambiguity_scope=st.sampled_from(["query", "all"]),
    expose_entity_ids=st.booleans(),
    include_numeric_probabilities=st.booleans(),
    allow_degraded_resolved=st.booleans(),
    classification_clearance=st.sampled_from(["public", "internal",
                                              "restricted"]),
)


def _build(text, policy, query=None):
    snap = _snap()
    resp = resolve(snap, text, mode="commit",
                   options={"return_all_mentions": True,
                            "max_prediction_set": 50})
    return resp, build_context_pack(snap, resp, query=query, policy=policy)


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_the_render_is_always_a_document(text, policy):
    _resp, pack = _build(text, policy)
    xml = render_context_pack(pack, "xml")
    assert ET.fromstring(xml).tag == "terminology_context"
    assert xml.count("</terminology_context>") == 1
    # and the JSON form survives a round trip unchanged
    assert json.loads(json.dumps(pack, ensure_ascii=False)) == pack


@settings(max_examples=80, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_the_same_input_is_the_same_pack(text, policy):
    snap = _snap()
    resp = resolve(snap, text, mode="commit",
                   options={"return_all_mentions": True,
                            "max_prediction_set": 50})
    first = build_context_pack(snap, resp, policy=policy)
    second = build_context_pack(snap, resp, policy=policy)
    assert first["pack_id"] == second["pack_id"]
    assert first == second


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_the_pack_invents_no_entity(text, policy):
    """Every id in the pack came from the resolver's own answer."""
    resp, pack = _build(text, policy)
    offered = {member["entity_id"]
               for m in resp["mentions"]
               for member in m.get("prediction_set", {}).get("members", [])
               if member.get("entity_id")}
    offered |= {m["resolved_entity"]["entity_id"]
                for m in resp["mentions"] if m.get("resolved_entity")}
    in_pack = {c["entity_id"] for c in pack["resolved_terms"]}
    in_pack |= {c["entity_id"] for a in pack["ambiguous_mentions"]
                for c in a["candidates"]}
    in_pack |= {d["entity_id"] for d in pack["document_definitions"]}
    assert in_pack <= offered, in_pack - offered


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_an_entity_appears_once(text, policy):
    _resp, pack = _build(text, policy)
    ids = [c["entity_id"] for c in pack["resolved_terms"]]
    assert len(ids) == len(set(ids))
    definitions = [(d["surface"], d["entity_id"])
                   for d in pack["document_definitions"]]
    assert len(definitions) == len(set(definitions))


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_every_span_points_into_the_text(text, policy):
    _resp, pack = _build(text, policy)
    spans = [m["span"] for c in pack["resolved_terms"] for m in c["mentions"]]
    spans += [a["span"] for a in pack["ambiguous_mentions"]]
    spans += [u["span"] for u in pack["unknown_mentions"]]
    spans += [d["source_span"] for d in pack["document_definitions"]]
    for span in spans:
        if span is None:
            continue
        assert 0 <= span["start"] <= span["end"] <= len(text), span


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_the_pack_reports_what_it_dropped(text, policy):
    """`complete` is a claim about the pack, and it has to be earned."""
    _resp, pack = _build(text, policy)
    coverage = pack["coverage"]
    if coverage["complete"]:
        assert pack["omissions"] == []
        assert not coverage["budget_truncated"]
    if pack["omissions"]:
        assert not coverage["complete"]
        assert all(o.get("reason") for o in pack["omissions"])


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_the_budget_is_a_budget(text, policy):
    _resp, pack = _build(text, policy)
    coverage = pack["coverage"]
    rendered = coverage["rendered_tokens"]
    assert rendered is not None
    # over budget is allowed only when the pack says so and says it is empty
    # of what it could still have cut
    if rendered > policy.max_tokens:
        assert coverage["budget_exceeded"], (rendered, policy.max_tokens)
    else:
        assert not coverage["budget_exceeded"]


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_no_string_escapes_the_ingestion_cap(text, policy):
    from ktrf.context import _MAX_FIELD_CHARS
    _resp, pack = _build(text, policy)
    assert all(len(s) <= _MAX_FIELD_CHARS for s in _strings(pack))


@settings(max_examples=120, deadline=None)
@given(text=_TEXT, policy=_POLICY)
def test_a_mention_is_a_fact_or_a_question_never_both(text, policy):
    """The invariant the state separation exists for.

    An *entity* may legitimately be resolved at one mention and a candidate
    at another — 한전 in one sentence, an ambiguous 한전 in the next. A
    *mention* may not: if it is listed under an entity card it is being
    presented as fact, and it must not also be offered as a choice.
    """
    _resp, pack = _build(text, policy)
    as_fact = {m["mention_id"] for c in pack["resolved_terms"]
               for m in c["mentions"]}
    as_question = {a["mention_id"] for a in pack["ambiguous_mentions"]}
    as_unknown = {u["mention_id"] for u in pack["unknown_mentions"]}
    assert not as_fact & as_question
    assert not as_fact & as_unknown
    assert not as_question & as_unknown
    assert all(a.get("set_valid") in (True, False)
               for a in pack["ambiguous_mentions"])


# --------------------------------------------------------------- the meta

def test_the_documents_reach_every_branch():
    """A property that never reaches a branch is not testing it.

    Drawn from registered surfaces alone, the generated documents produced
    resolved terms and nothing else — no ambiguity, no unknown mention, no
    document definition — so half the properties above were passing over
    packs that could not have violated them. This asserts the strategy still
    reaches each state, deterministically, so a later edit to `_FRAGMENT`
    cannot quietly hollow them out.
    """
    import random

    rng = random.Random(20260906)
    fragments = _SURFACES + _NEAR_MISSES + _DEFINITIONS + ["가나다", ""]
    seen = {"resolved": 0, "ambiguous": 0, "unknown": 0, "definitions": 0,
            "omissions": 0, "budget_truncated": 0, "empty": 0}
    for _ in range(200):
        text = " ".join(rng.choice(fragments)
                        for _ in range(rng.randint(0, 6)))
        policy = ContextPolicy(max_tokens=rng.randint(1, 2000),
                               max_entities=rng.randint(1, 30),
                               include_unknown_mentions=True)
        _resp, pack = _build(text, policy)
        seen["resolved"] += bool(pack["resolved_terms"])
        seen["ambiguous"] += bool(pack["ambiguous_mentions"])
        seen["unknown"] += bool(pack["unknown_mentions"])
        seen["definitions"] += bool(pack["document_definitions"])
        seen["omissions"] += bool(pack["omissions"])
        seen["budget_truncated"] += pack["coverage"]["budget_truncated"]
        seen["empty"] += pack["coverage"]["empty"]
    missing = [k for k, n in seen.items() if n == 0]
    assert not missing, f"never generated: {missing} ({seen})"

"""The pack has to be honest about what it cut and what it costs.

Two ways a context pack said one thing and contained another:

* the pack cuts candidates itself — `max_candidates_per_mention`, and the
  clearance check — and only the *resolver's* truncation was reflected in
  `set_valid`. A pack that had dropped one of two senses still reported a
  valid set and complete coverage, which is exactly the claim an automated
  grounding gate reads;
* the token budget reduced hints, definitions, candidates, ambiguous mentions
  and resolved terms, and never touched `document_definitions` or
  `unknown_mentions`. A document that defines its own abbreviations rendered
  416 tokens against a budget of 100 — the budget had no way to reach the
  block that was costing the tokens.
"""

import pytest

from ktrf.context import (
    CharTokenCounter,
    ContextPolicy,
    build_context_pack,
    render_context_pack,
)
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"


def _two_sense_glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_AP_NET", "canonical": "Access Point",
             "description": "wireless network device", "domain_ids": ["NET"]},
            {"entity_id": "E_AP_WF", "canonical": "Approval Process",
             "description": "approval workflow", "domain_ids": ["WF"]},
        ],
        "alias_families": [
            {"family_id": "F_AP", "representative": "AP",
             "normalization_profile": "latin_acronym"},
        ],
        "alias_bindings": [
            {"alias_id": "A_AP1", "family_id": "F_AP",
             "entity_id": "E_AP_NET", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
            {"alias_id": "A_AP2", "family_id": "F_AP",
             "entity_id": "E_AP_WF", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
        ],
    })


@pytest.fixture(scope="module")
def ambiguous_response():
    snap = compile_snapshot(_two_sense_glossary())
    return snap, resolve(snap, "AP 확인 부탁드립니다", mode="commit",
                         options={"return_all_mentions": True})


# ------------------------------------------------------- candidate cutting

def test_showing_one_of_two_senses_invalidates_the_set(ambiguous_response):
    snap, resp = ambiguous_response
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_candidates_per_mention=1, ambiguity_scope="all"))
    amb = pack["ambiguous_mentions"]
    assert amb, "fixture must produce an ambiguous mention"
    assert len(amb[0]["candidates"]) == 1
    assert amb[0]["set_valid"] is False
    assert pack["coverage"]["complete"] is False


def test_the_cut_is_recorded_with_what_it_dropped(ambiguous_response):
    snap, resp = ambiguous_response
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_candidates_per_mention=1, ambiguity_scope="all"))
    cut = [o for o in pack["omissions"]
           if o["reason"] == "candidates_truncated"]
    assert cut, pack["omissions"]
    assert cut[0]["offered"] == 2 and cut[0]["shown"] == 1


def test_showing_every_sense_leaves_the_set_valid(ambiguous_response):
    snap, resp = ambiguous_response
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_candidates_per_mention=5, ambiguity_scope="all"))
    amb = pack["ambiguous_mentions"]
    assert len(amb[0]["candidates"]) == 2
    assert amb[0]["set_valid"] is True
    assert not [o for o in pack["omissions"]
                if o["reason"] == "candidates_truncated"]


# ------------------------------------------------------------ token budget

@pytest.fixture(scope="module")
def defining_document():
    """A document that defines its own abbreviations and then uses them."""
    snap = compile_snapshot(load_glossary(GLOSSARY))
    pairs = [("한국전력공사", "한전"), ("금융감독원", "금감원"),
             ("공정거래위원회", "공정위"), ("기획재정부", "기재부"),
             ("국토교통부", "국토부"), ("보건복지부", "복지부")]
    parts = []
    for full, short in pairs:
        parts.append(f'{full}(이하 "{short}")는 관련 대책을 발표했다.')
        parts.append(f"{short}는 이어 후속 조치를 설명했다. "
                     f"{short} 관계자는 추가 검토가 필요하다고 밝혔다.")
    text = " ".join(parts)
    return snap, resolve(snap, text, mode="commit",
                         options={"return_all_mentions": True,
                                  "detect_unregistered_mentions": True})


@pytest.mark.parametrize("budget", [100, 200, 400])
def test_the_rendered_pack_fits_the_budget(defining_document, budget):
    snap, resp = defining_document
    counter = CharTokenCounter()
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_tokens=budget), token_counter=counter)
    assert counter.count(render_context_pack(pack, "xml")) <= budget


def test_definitions_are_inside_the_reduction_order(defining_document):
    snap, resp = defining_document
    counter = CharTokenCounter()
    generous = build_context_pack(snap, resp, policy=ContextPolicy(
        max_tokens=4000), token_counter=counter)
    tight = build_context_pack(snap, resp, policy=ContextPolicy(
        max_tokens=100), token_counter=counter)
    assert len(generous["document_definitions"]) > \
           len(tight["document_definitions"])


def test_the_pack_reports_what_it_actually_costs(defining_document):
    snap, resp = defining_document
    counter = CharTokenCounter()
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_tokens=200), token_counter=counter)
    rendered = counter.count(render_context_pack(pack, "xml"))
    assert pack["coverage"]["rendered_tokens"] == rendered


def test_an_unreachable_budget_is_reported_rather_than_missed(
        defining_document):
    # a budget below the fixed header cannot be met by dropping content. The
    # pack says so instead of quietly overshooting.
    snap, resp = defining_document
    counter = CharTokenCounter()
    pack = build_context_pack(snap, resp, policy=ContextPolicy(max_tokens=1),
                              token_counter=counter)
    assert pack["coverage"]["budget_exceeded"] is True
    assert any(o["reason"] == "token_budget_unreachable"
               for o in pack["omissions"])
    assert pack["coverage"]["rendered_tokens"] > 1


def test_coverage_counts_describe_the_pack_that_came_back(defining_document):
    snap, resp = defining_document
    counter = CharTokenCounter()
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_tokens=120), token_counter=counter)
    cov = pack["coverage"]
    assert cov["entities_injected"] == len(pack["resolved_terms"])
    assert cov["ambiguous_mentions"] == len(pack["ambiguous_mentions"])
    assert cov["document_definitions"] == len(pack["document_definitions"])
    assert cov["omitted"] == len(pack["omissions"])


def test_a_generous_budget_changes_nothing(defining_document):
    snap, resp = defining_document
    counter = CharTokenCounter()
    pack = build_context_pack(snap, resp, policy=ContextPolicy(
        max_tokens=100000), token_counter=counter)
    assert pack["coverage"]["budget_truncated"] is False
    assert pack["coverage"]["budget_exceeded"] is False
    assert pack["coverage"]["rendered_tokens"] > 0

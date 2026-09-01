"""Contract tests for the variant-family evaluation axis.

The suites in ``eval/`` decide what the project believes about itself, so
their construction needs the same scrutiny as the resolver. These tests
pin the properties that, if they broke, would leave a *passing* evaluation
measuring nothing:

- the gold contract comes from the plan document, not from the catalog the
  resolver reads (otherwise it is a conformance test wearing a disguise);
- a decoy that the corpus can actually match is not a decoy;
- macro is not micro, and the difference has to survive the aggregation.
"""

import random

import pytest

from eval.confusion import build_confusion_glossary
from eval.run_variant_recall import _macro, _micro, score_case
from eval.variants import (ARTIFACT_ENDINGS, BY_KEY, CONDITIONAL,
                           DERIVATIVE_ORG_ENDINGS, DERIVATIVE_ROLE_ENDINGS,
                           FORBIDDEN, FORMATIONS, ORG_UNIT_ENDINGS, SAME,
                           VariantCase, build_cases, place)
from ktrf.glossary import load_glossary
from ktrf.morphology import SUFFIX_CLASSES

CORPUS = [{"text": f"어제 발표된 자료에 따르면 항목 {i}은 그대로 유지되었다."}
          for i in range(400)]

GLOSSARY_DICT = {
    "glossary_id": "vtest", "version": "1", "schema_version": "3",
    "entities": [
        {"entity_id": "E_A", "canonical": "한국전력공사"},
        {"entity_id": "E_B", "canonical": "금융감독원"},
    ],
    "alias_families": [
        {"family_id": "F_A", "representative": "한국전력공사",
         "normalization_profile": "korean_org_name"},
        {"family_id": "F_A2", "representative": "한전",
         "normalization_profile": "korean_org_name"},
        {"family_id": "F_B", "representative": "금융감독원",
         "normalization_profile": "korean_org_name"},
    ],
    "alias_bindings": [
        {"alias_id": "A1", "family_id": "F_A", "entity_id": "E_A",
         "surface": "한국전력공사", "kind": "name"},
        {"alias_id": "A2", "family_id": "F_A2", "entity_id": "E_A",
         "surface": "한전", "kind": "abbreviation"},
        {"alias_id": "A3", "family_id": "F_B", "entity_id": "E_B",
         "surface": "금융감독원", "kind": "name"},
    ],
}


@pytest.fixture
def glossary():
    return load_glossary(dict(GLOSSARY_DICT))


# ---------------------------------------------------------------------------
# The gold contract must not come from the implementation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,endings", [
    ("derivative_org", DERIVATIVE_ORG_ENDINGS),
    ("derivative_role", DERIVATIVE_ROLE_ENDINGS),
    ("org_unit", ORG_UNIT_ENDINGS),
    ("artifact", ARTIFACT_ENDINGS),
])
def test_forbidden_endings_straddle_the_resolver_catalog(name, endings):
    """Each FORBIDDEN list must reach both a typed and an unknown residual.

    If every ending were already in ``SUFFIX_CLASSES``, the suite would only
    ask whether the resolver agrees with its own table. If none were, a
    catalog change could never show up here at all — which is exactly what
    the first paired M3 run found: the suite came back byte-identical
    because its endings were all outside. Both halves have to stay
    non-empty, and this notices when a catalog change empties one.
    """
    known = {e for e in endings if e in SUFFIX_CLASSES}
    assert known, f"{name}: nothing here is typed; the suite cannot see catalog work"
    assert set(endings) - known, (
        f"{name}: every ending is now in SUFFIX_CLASSES; add one the catalog "
        "does not know or this stops testing unknown residuals")


def test_every_formation_carries_a_contract_and_a_tier():
    for f in FORMATIONS:
        assert f.commit in (SAME, CONDITIONAL, FORBIDDEN), f.key
        assert f.tier in ("A", "B"), f.key
        assert f.contract_row, f.key


# ---------------------------------------------------------------------------
# Case construction
# ---------------------------------------------------------------------------

def test_cases_cover_every_family_and_record_a_truthful_core_span(glossary):
    cases = build_cases(CORPUS, glossary, per_cell=1, seed=7)
    assert {c.entity_id for c in cases} == {"E_A", "E_B"}
    for c in cases:
        s, e = c.core_span
        assert c.text[s:e] == c.core, (c.formation, c.token, c.text)
        fs, fe = c.full_span
        assert fs <= s and e <= fe


def test_derivative_cases_are_wider_than_their_core(glossary):
    cases = [c for c in build_cases(CORPUS, glossary, per_cell=1, seed=7)
             if BY_KEY[c.formation].commit == FORBIDDEN]
    assert cases
    for c in cases:
        assert len(c.token) > len(c.core)
        assert c.token.startswith(c.core)


def test_inapplicable_cells_are_absent_not_zero(glossary):
    """A Latin surface has no 중성 to perturb; it must not score as a miss."""
    latin = load_glossary({
        **GLOSSARY_DICT,
        "alias_bindings": [{"alias_id": "L1", "family_id": "F_A",
                            "entity_id": "E_A", "surface": "KEPCO",
                            "kind": "abbreviation"}],
        "alias_families": [GLOSSARY_DICT["alias_families"][0]],
    })
    keys = {c.formation for c in build_cases(CORPUS, latin, per_cell=1, seed=7)}
    assert "typo" not in keys and "keyboard" not in keys
    assert "fullwidth" in keys and "bare" in keys


def test_place_keeps_the_token_off_position_zero():
    text, start = place("한전", "정부는 어제 발표했다")
    assert text[start:start + 2] == "한전"
    assert start > 0


# ---------------------------------------------------------------------------
# Scoring: the layers must stay apart
# ---------------------------------------------------------------------------

def _case(formation="derivative_org", core_span=(0, 3)):
    return VariantCase(entity_id="E_A", formation=formation, registered="한전",
                       text="x", token="한전노조", core="한전",
                       core_span=core_span, full_span=(0, 4))


def _mention(span, link="AMBIGUOUS", entity="E_A", full_surface=None):
    m = {"span": {"codepoint": {"start": span[0], "end": span[1]}},
         "link_decision": link,
         "prediction_set": {"members": [{"kind": "ENTITY", "entity_id": entity}]},
         "core_link": {"relation": "DERIVED_FROM"}}
    if link == "RESOLVED":
        m["resolved_entity"] = {"entity_id": entity}
    if full_surface:
        m["full_surface"] = full_surface
    return m


def test_withholding_a_commit_is_not_a_candidate_miss():
    rec = score_case(_case(), [_mention((0, 3))])
    assert rec["gold_in_set"] is True      # |candidate succeeded
    assert rec["commit_gold"] is False     # |commit withheld — not a miss
    assert rec["violation"] is None


def test_parent_taking_the_whole_derivative_is_a_violation():
    rec = score_case(_case(), [_mention((0, 4), link="RESOLVED")])
    assert rec["violation"] == "parent_took_full_surface"


def test_declaring_the_derivative_identical_is_a_violation():
    rec = score_case(_case(), [_mention(
        (0, 3), link="RESOLVED",
        full_surface={"surface": "한전노조", "identity": "SAME_AS_CORE"})])
    assert rec["violation"] == "full_surface_declared_same"


def test_committing_only_the_core_of_a_derivative_is_allowed():
    """Invariant ④: the core stays a candidate even when the whole does not."""
    rec = score_case(_case(), [_mention(
        (0, 3), link="RESOLVED",
        full_surface={"surface": "한전노조", "identity": "DISTINCT_FROM_CORE"})])
    assert rec["violation"] is None
    assert rec["commit_gold"] is True


def test_a_mention_at_the_wrong_boundary_is_not_recall():
    """`대한민국` read as core `대한` is a span error, not a hit."""
    rec = score_case(_case(formation="bare", core_span=(0, 4)),
                     [_mention((0, 2))])
    assert rec["gold_in_set"] is False
    assert rec["core_span_wrong"] is True
    assert rec["gold_in_set_any_span"] is True  # kept, as a diagnostic only


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_macro_gives_a_rare_family_the_same_weight_as_a_common_one():
    records = ([{"entity_id": "BIG", "gold_in_set": True}] * 99
               + [{"entity_id": "BIG", "gold_in_set": False}]
               + [{"entity_id": "RARE", "gold_in_set": False}])
    assert _micro(records, "gold_in_set") == pytest.approx(99 / 101)
    # BIG scores 0.99, RARE scores 0.0 — one term, one vote
    assert _macro(records, "gold_in_set") == pytest.approx(0.495)


# ---------------------------------------------------------------------------
# Confusion glossary
# ---------------------------------------------------------------------------

def test_decoys_present_in_the_corpus_are_dropped():
    """A "false positive" on a decoy the text really contains proves nothing."""
    texts = ["한국전력공사가 오늘 발표했다.", "한전은 어제 밝혔다."]
    # plant a decoy that the corpus does contain, by handing the builder a
    # glossary whose near-miss lands on a real string
    g, meta = build_confusion_glossary(
        {**GLOSSARY_DICT, "alias_bindings": list(GLOSSARY_DICT["alias_bindings"])},
        texts, seed=3)
    surfaces = {b["surface"] for b in g["alias_bindings"]
                if b["entity_id"] in meta.decoy_entities}
    joined = chr(10).join(texts)
    for s in surfaces:
        if s in meta.collisions:
            continue  # collisions are meant to occur — that is the point
        assert s not in joined, f"decoy {s} occurs in the corpus"


def test_collision_decoys_share_a_surface_with_a_real_entity():
    texts = ["한전은 어제 밝혔다."] * 5
    g, meta = build_confusion_glossary(dict(GLOSSARY_DICT), texts, seed=3)
    assert meta.collisions, "no collision was planted"
    for ab, eids in meta.collisions.items():
        owners = {b["entity_id"] for b in g["alias_bindings"]
                  if b["surface"] == ab}
        assert len(owners) >= 2, f"{ab} has only one sense: {owners}"
        assert set(eids) <= owners


def test_base_glossary_is_not_mutated():
    before = len(GLOSSARY_DICT["alias_bindings"])
    build_confusion_glossary(dict(GLOSSARY_DICT), ["무관한 문장이다."], seed=3)
    assert len(GLOSSARY_DICT["alias_bindings"]) == before


def test_decoys_are_anchored_to_frequent_terms():
    """Budget spent on a term the corpus never says can never be exercised."""
    texts = ["한국전력공사가 밝혔다."] * 20 + ["금융감독원이 밝혔다."]
    _, meta = build_confusion_glossary(dict(GLOSSARY_DICT), texts, seed=3,
                                       near_miss_n=1, collision_n=0,
                                       prefix_n=0)
    assert list(meta.near_miss.values()) == ["E_A"]

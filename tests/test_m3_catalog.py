"""M3 coverage: tail taxonomy, punctuation classes, confusion costs, signatures.

Every catalog entry here changes what the resolver *says*, and two of them
change what it is allowed to *commit*, so each gets a test that names the
sentence it was added for. The census counts these entries were drawn from
live in `docs/VARIANTS_PLAN.md`; what is pinned here is the behaviour.
"""

import dataclasses

import pytest

from ktrf.abbrev import AbbrevAligner
from ktrf.fuzzy import CONFUSION_CLASSES, weighted_edit_distance
from ktrf.glossary import load_glossary
from ktrf.hangul import to_jamo_seq
from ktrf.morphology import (CONTEXTUAL_SUFFIX_CLASSES, SUFFIX_CLASSES,
                             TOKEN_FINAL_PARTICLES, ParticleFST,
                             analyze_residual, classify_suffix)
from ktrf.normalization import DEFAULT_PROFILES, HYPHEN_CLASS, normalize_alias
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = {
    "glossary_id": "m3", "version": "1", "schema_version": "3",
    "entities": [
        {"entity_id": "E_KEPCO", "canonical": "한국전력공사"},
        {"entity_id": "E_JEJU", "canonical": "제주도"},
        {"entity_id": "E_BOK", "canonical": "한국은행"},
        {"entity_id": "E_NIS", "canonical": "국가정보원"},
        {"entity_id": "E_HYNIX", "canonical": "SK하이닉스"},
    ],
    "alias_families": [
        {"family_id": f"F{i}", "representative": s,
         "normalization_profile": "korean_org_name"}
        for i, s in enumerate(["한국전력공사", "한국전력", "제주도", "한국은행",
                               "국가정보원", "국정원", "SK하이닉스"])
    ],
    "alias_bindings": [
        {"alias_id": "A0", "family_id": "F0", "entity_id": "E_KEPCO",
         "surface": "한국전력공사", "kind": "name"},
        {"alias_id": "A1", "family_id": "F1", "entity_id": "E_KEPCO",
         "surface": "한국전력", "kind": "name"},
        {"alias_id": "A2", "family_id": "F2", "entity_id": "E_JEJU",
         "surface": "제주도", "kind": "name"},
        {"alias_id": "A3", "family_id": "F3", "entity_id": "E_BOK",
         "surface": "한국은행", "kind": "name"},
        {"alias_id": "A4", "family_id": "F4", "entity_id": "E_NIS",
         "surface": "국가정보원", "kind": "name"},
        {"alias_id": "A5", "family_id": "F5", "entity_id": "E_NIS",
         "surface": "국정원", "kind": "abbreviation"},
        {"alias_id": "A6", "family_id": "F6", "entity_id": "E_HYNIX",
         "surface": "SK하이닉스", "kind": "name"},
    ],
}


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary(dict(GLOSSARY)))


def _mention(snap, text, surface):
    for m in resolve(snap, text, mode="commit")["mentions"]:
        if m["surface"] == surface:
            return m
    return None


# ---------------------------------------------------------------------------
# Tail taxonomy
# ---------------------------------------------------------------------------

def test_multisyllable_org_endings_denote_the_same_organisation():
    """`한국전력` + `공사` is 한국전력공사, not one of its subsidiaries.

    M2 documented this as the gap that made SAME unreachable in practice:
    NAME_PART held only single syllables, so every full official name read
    as UNKNOWN.
    """
    assert analyze_residual("공사").full_identity == "SAME"
    assert analyze_residual("공단").full_identity == "SAME"
    assert analyze_residual("공사").relation == "IDENTITY"


def test_bank_endings_stay_distinct():
    """신한은행 and 신한카드 are siblings, so `은행` may not say SAME.

    Getting a class wrong is asymmetric: SAME permits a commit on the whole
    surface, DISTINCT only withholds. `은행` is arguable — a holding company
    and its bank share a name — so it sits with 증권/카드/생명.
    """
    assert SUFFIX_CLASSES["은행"] == SUFFIX_CLASSES["카드"]
    assert analyze_residual("은행").full_identity == "DISTINCT"


def test_a_province_makes_지사_a_person(snap):
    """제주도지사 is 知事; 한국전력지사 is 支社. The core's ending tells them apart."""
    assert classify_suffix("지사", "도") == "ROLE"
    assert classify_suffix("지사", "력") == "ORG_UNIT"
    assert classify_suffix("지사") == "ORG_UNIT"  # no context: the safe default
    m = _mention(snap, "제주도지사가 어제 밝혔다.", "제주도")
    assert m["core_link"]["relation"] == "ROLE_OF"


def test_contextual_class_applies_only_to_the_leftmost_part():
    """Only the leftmost part touches the core; a later part sees its neighbour."""
    assert list(CONTEXTUAL_SUFFIX_CLASSES) == ["지사"]
    r = analyze_residual("지사장", "도")
    assert r.parts == ("지사", "장")
    assert r.classes[0] == "ROLE"          # 지사 behind 도
    assert r.full_identity == "DISTINCT"


def test_law_is_an_artifact_not_the_organisation(snap):
    m = _mention(snap, "한국은행법에 따르면 그렇다.", "한국은행")
    assert m["full_surface"]["surface"] == "한국은행법"
    assert m["full_surface"]["identity"] == "DISTINCT_FROM_CORE"
    assert m["core_link"]["relation"] == "ARTIFACT_OF"


# ---------------------------------------------------------------------------
# The `서` particle and its constraint
# ---------------------------------------------------------------------------

def test_headline_서_is_a_particle_at_the_end_of_an_어절(snap):
    m = _mention(snap, "국정원서 어제 발표했다.", "국정원")
    assert m is not None
    assert m["tail"]["particles"] == ["서"]


def test_서_is_not_a_particle_when_more_hangul_follows():
    """Otherwise `서울본부` reads as a particle and every 서-word loosens."""
    fst = ParticleFST()
    assert "서" in TOKEN_FINAL_PARTICLES
    assert fst.accepts_prefix("서 발표했다")
    assert not fst.accepts_prefix("서울본부")
    assert not fst.parse_full("서울")


# ---------------------------------------------------------------------------
# Punctuation classes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dash", HYPHEN_CLASS)
def test_every_dash_in_the_class_is_ignorable(dash):
    p = DEFAULT_PROFILES["korean_org_name"]
    assert normalize_alias(f"한국전력{dash}공사", p) == normalize_alias("한국전력공사", p)


def test_semantic_punctuation_has_no_class():
    """`&`, `/`, `+`, `#` can be part of a name, so no profile inherits them."""
    for ch in "&/+#":
        assert ch not in HYPHEN_CLASS
    assert "&" not in DEFAULT_PROFILES["korean_org_name"].ignore_punctuation


# ---------------------------------------------------------------------------
# Confusion cost table
# ---------------------------------------------------------------------------

def test_phonological_confusion_is_cheaper_than_an_unrelated_swap():
    """`다르다`/`타르다` is the slip people make; `다르다`/`하르다` is not.

    Neither pair is keyboard-adjacent (e/x and e/g), so the only rule that
    can separate them is the 평음·격음 series — which is the point.
    """
    near = weighted_edit_distance(to_jamo_seq("다다"), to_jamo_seq("타다"))
    far = weighted_edit_distance(to_jamo_seq("다다"), to_jamo_seq("하다"))
    assert near < far


def test_confusion_groups_are_well_formed():
    for name, spec in CONFUSION_CLASSES.items():
        assert 0.0 < spec["cost"] < 1.0, name
        for group in spec["groups"]:
            assert len(set(group)) == len(group), (name, group)
            assert len(group) >= 2, (name, group)


def test_no_confusion_entry_is_unreachable():
    """A group naming a compound vowel is coverage that does not exist.

    ``to_jamo_seq`` splits ㅚ into ㅗㅣ before the distance function ever
    runs, so such an entry would sit in the table looking like a rule and
    never fire once.
    """
    for name, spec in CONFUSION_CLASSES.items():
        for group in spec["groups"]:
            for jamo in group:
                assert to_jamo_seq(jamo) == jamo, (name, group, jamo)


# ---------------------------------------------------------------------------
# Abbreviation signature index
# ---------------------------------------------------------------------------

def test_abbreviation_aligns_against_registered_names_not_only_canonicals():
    """A tenant that registers a second name should get coverage from it."""
    al = AbbrevAligner(load_glossary(dict(GLOSSARY)))
    hits = {c.target for c in al.align_token("한전", (0, 2))}
    assert "한국전력" in hits


def test_mixed_script_tokens_align():
    """`SK하닉` is neither all-Hangul nor all-Latin and used to match nothing.

    Unit-level only. ``resolve`` splits at script boundaries and never hands
    this module the whole token, so passing here is not evidence that a
    mixed-script mention resolves — see the module docstring, and
    :func:`test_mixed_script_does_not_reach_the_resolver_yet` below.
    """
    al = AbbrevAligner(load_glossary(dict(GLOSSARY)))
    got = al.align_token("SK하닉", (0, 5))
    assert [c.entity_id for c in got] == ["E_HYNIX"]


def test_mixed_script_does_not_reach_the_resolver_yet(snap):
    """Pins the gap so it is a known limit, not a silent one."""
    surfaces = {m["surface"]
                for m in resolve(snap, "어제 SK하닉 발표", mode="commit")["mentions"]}
    assert "SK하닉" not in surfaces


def test_two_letter_latin_does_not_align_as_a_subsequence(snap):
    """`KB` inside `KB S` must not out-compete the spaced `KBS` (§4.6).

    Two letters are found inside almost any longer name, and the winner is
    a *shorter* mention at the wrong boundary. The variant suite saw this
    as a jump in `core_span_wrong` on the `spaced` formation.
    """
    al = AbbrevAligner(load_glossary(dict(GLOSSARY)))
    assert al.align_token("한전", (0, 2))       # 2 Hangul still aligns
    assert not al.align_token("SK", (0, 2))     # 2 Latin does not


def test_one_candidate_per_entity():
    """Three registered spellings of one name are not three votes."""
    al = AbbrevAligner(load_glossary(dict(GLOSSARY)))
    got = al.align_token("한전", (0, 2))
    assert len({c.entity_id for c in got}) == len(got)


def test_signature_index_prunes_without_losing_reach():
    al = AbbrevAligner(load_glossary(dict(GLOSSARY)))
    stats = al.signature_stats()
    assert stats["buckets"] > 1
    assert stats["largest_bucket"] < stats["entries"]


def test_an_abbreviation_may_drop_the_leading_morpheme():
    """`고용노동부` -> `노동부`, `보건복지부` -> `복지부`.

    Indexing by the target's *first* syllable looks like a free shortlist
    and is not: Korean abbreviations routinely start partway into the name.
    That premise cost 3pp of unseen-abbreviation recall until the neural
    track measured it, so the reachable condition is "contains the token's
    first character", which a subsequence match already requires.
    """
    g = load_glossary({
        **GLOSSARY, "entities": [{"entity_id": "E_MOEL",
                                  "canonical": "고용노동부"}],
        "alias_families": [{"family_id": "FX", "representative": "고용노동부",
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "AX", "family_id": "FX",
                            "entity_id": "E_MOEL", "surface": "고용노동부",
                            "kind": "name"}],
    })
    al = AbbrevAligner(g)
    assert [c.entity_id for c in al.align_token("노동부", (0, 3))] == ["E_MOEL"]


# ---------------------------------------------------------------------------
# Invariant ⑥: every catalog above is part of snapshot identity
# ---------------------------------------------------------------------------

def test_snapshot_identity_covers_the_m3_catalogs(snap):
    for key in ("morphology_rules_hash", "fuzzy_confusion_hash",
                "abbrev_signature_hash", "normalization_profiles_hash"):
        assert snap.manifest[key], key

    import ktrf.fuzzy as fz
    import ktrf.morphology as mo
    import ktrf.snapshot as sn

    before = snap.snapshot_id
    saved = dict(fz.CONFUSION_CLASSES)
    try:
        fz.CONFUSION_CLASSES["obstruent_series"] = {
            "cost": 0.9, "groups": ("ㄱㅋㄲ",)}
        after = compile_snapshot(load_glossary(dict(GLOSSARY)))
        assert after.snapshot_id != before
    finally:
        fz.CONFUSION_CLASSES.clear()
        fz.CONFUSION_CLASSES.update(saved)

    before2 = compile_snapshot(load_glossary(dict(GLOSSARY))).snapshot_id
    assert before2 == before
    saved_ctx = dict(mo.CONTEXTUAL_SUFFIX_CLASSES)
    try:
        mo.CONTEXTUAL_SUFFIX_CLASSES["본부"] = (("도",), "ROLE", "ORG_UNIT")
        assert compile_snapshot(
            load_glossary(dict(GLOSSARY))).snapshot_id != before
    finally:
        mo.CONTEXTUAL_SUFFIX_CLASSES.clear()
        mo.CONTEXTUAL_SUFFIX_CLASSES.update(saved_ctx)
    before3 = compile_snapshot(load_glossary(dict(GLOSSARY))).snapshot_id
    assert before3 == before
    import ktrf.normalization as nr
    saved_prof = nr.DEFAULT_PROFILES["korean_org_name"]
    try:
        # widening a punctuation class makes surfaces match that used to
        # miss; the artifact is not the same one (invariant ⑥)
        nr.DEFAULT_PROFILES["korean_org_name"] = dataclasses.replace(
            saved_prof, ignore_punctuation=saved_prof.ignore_punctuation + ("~",))
        assert compile_snapshot(
            load_glossary(dict(GLOSSARY))).snapshot_id != before
    finally:
        nr.DEFAULT_PROFILES["korean_org_name"] = saved_prof
    assert sn  # the hash lives there; keep the import meaningful

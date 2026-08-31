"""core_link / full_surface separation and registered compositions.

VARIANTS_PLAN §2 invariants ② (no parent full-span overcommit) and ③
(registered relations first), realised as M2's typed tail grammar.

The contract these tests pin down: ``span`` is the core, ``full_span`` is the
raw token, and ``full_surface`` says — in the response, not in a consumer's
head — whether the whole thing still means what the core means.
"""

import pytest

from ktrf.glossary import load_glossary
from ktrf.morphology import analyze_residual
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary("examples/demo_glossary.yaml"))


def _mention(resp, surface):
    for m in resp["mentions"]:
        if m["surface"] == surface:
            return m
    return None


# --- typed tail grammar ----------------------------------------------------

@pytest.mark.parametrize("residual,cls,identity,relation", [
    ("부", "NAME_PART", "SAME", "IDENTITY"),          # 교육 + 부
    ("측", "REFERENTIAL", "SAME", "REFERS_TO"),        # 한전 + 측
    ("장", "ROLE", "DISTINCT", "ROLE_OF"),             # 금감원 + 장 = a person
    ("노조", "DERIVED_ORG", "DISTINCT", "DERIVED_FROM"),
    ("본부", "ORG_UNIT", "DISTINCT", "PART_OF"),
    ("그룹", "AFFILIATE", "DISTINCT", "AFFILIATE_OF"),
    ("시스템", "ARTIFACT", "DISTINCT", "ARTIFACT_OF"),
])
def test_suffix_classes_decide_full_identity(residual, cls, identity, relation):
    r = analyze_residual(residual)
    assert r.head_class == cls
    assert r.full_identity == identity
    assert r.relation == relation


def test_a_leading_modifier_always_makes_a_distinct_name():
    # 서울본부 is a unit even though 본부 alone would already say so; the rule
    # has to hold for a NAME_PART head too (서울부 is not 부)
    assert analyze_residual("서울본부").full_identity == "DISTINCT"
    assert analyze_residual("서울부").full_identity == "DISTINCT"
    assert analyze_residual("서울부").relation == "NAMED_VARIANT"


def test_an_unanalysed_remainder_is_unknown_not_same():
    r = analyze_residual("읭읭")
    assert (r.kind, r.full_identity) == ("UNKNOWN", "UNKNOWN")


# --- response contract -----------------------------------------------------

def test_no_surface_record_when_the_core_is_the_whole_surface(snap):
    # `한전은` is core + 조사: a particle is grammar, not part of a name, so
    # there is nothing to separate and the keys stay absent
    m = _mention(resolve(snap, "한전은 오늘 발표했다.", mode="commit"), "한전")
    assert m["link_decision"] == "RESOLVED"
    assert "core_link" not in m and "full_surface" not in m


def test_role_tail_separates_the_person_from_the_organisation(snap):
    resp = resolve(snap, "과학기술정보통신부장관이 참석했다.", mode="commit")
    m = _mention(resp, "과학기술정보통신부")
    assert m["core_link"]["relation"] == "ROLE_OF"
    fs = m["full_surface"]
    assert fs["identity"] == "DISTINCT_FROM_CORE"
    assert fs["tail_class"] == "ROLE"
    assert fs["surface"] == "과학기술정보통신부장관"
    # the entity is committed on the core span only; the full surface carries
    # no entity of its own because no relation is registered for 장관
    assert "composes_to" not in fs


def test_full_surface_span_excludes_the_particle(snap):
    resp = resolve(snap, "한전노조가 파업을 예고했다.", mode="commit")
    m = _mention(resp, "한전")
    assert m["span"]["codepoint"] == {"start": 0, "end": 2}          # 한전
    assert m["full_surface"]["span"]["codepoint"] == {"start": 0, "end": 4}
    assert m["full_span"]["codepoint"] == {"start": 0, "end": 5}     # +가
    assert m["full_surface"]["surface"] == "한전노조"


def test_registered_composition_names_the_derivative(snap):
    # invariant ③: the glossary declares 한전 + 노조 -> 전국전력노동조합, so the
    # answer comes from the declaration, not from an inference about the core
    m = _mention(resolve(snap, "한전노조가 파업을 예고했다.", mode="commit"),
                 "한전")
    comp = m["full_surface"]["composes_to"]
    assert comp["entity_id"] == "ORG_KEPCO_UNION"
    assert comp["canonical"] == "전국전력노동조합"
    assert comp["from_entity_id"] == "ORG_KEPCO"
    assert comp["relation_id"] == "REL_KEPCO_UNION"


def test_the_parent_never_takes_the_full_surface(snap):
    # invariant ②: even with a registered composition the *core* mention
    # stays scoped to the core span — the parent must not spread over 노조
    m = _mention(resolve(snap, "한전노조가 파업을 예고했다.", mode="commit"),
                 "한전")
    cp = m["span"]["codepoint"]
    assert (cp["start"], cp["end"]) == (0, 2)
    if m["link_decision"] == "RESOLVED":
        assert m["resolved_entity"]["entity_id"] == "ORG_KEPCO"
    assert m["full_surface"]["identity"] == "DISTINCT_FROM_CORE"


def test_fast_mode_also_reports_the_separation(snap):
    # a registered relation is deterministic, so §26.1 fast mode gets it too
    m = _mention(resolve(snap, "한전노조가 파업을 예고했다.", mode="fast"),
                 "한전")
    assert m["full_surface"]["composes_to"]["entity_id"] == "ORG_KEPCO_UNION"


def test_every_level_b_channel_faces_the_guard(snap):
    """A channel that skips the guard can *lift* another channel's block.

    ``CandidatePool.add`` merges evidence for one entity and clears
    ``commit_blocked`` as soon as some evidence arrives unblocked — which is
    right for Level A, and a hole for any Level B channel that never
    consulted the guard. Pass-2 abbreviation alignment was such a channel:
    it re-allowed a commit the jamo channel had blocked on the same span.
    """
    resp = resolve(snap, "과학기술정보통신붑장관이 참석했다.", mode="commit")
    m = _mention(resp, "과학기술정보통신")
    member = next(x for x in m["prediction_set"]["members"]
                  if x.get("entity_id") == "ORG_MSIT")
    assert "abbrev" in member["generation_channels"]  # the merging channel
    assert member["commit_blocked"] == "typed_derivative"
    assert m["link_decision"] != "RESOLVED"


def test_snapshot_id_tracks_the_suffix_classification():
    # invariant ⑥: reclassifying a suffix changes what the resolver commits,
    # so it has to change artifact identity — the classes are hashed, not
    # just the surfaces
    from ktrf import morphology
    from ktrf.snapshot import _morphology_hash

    before = _morphology_hash()
    original = morphology.SUFFIX_CLASSES["노조"]
    morphology.SUFFIX_CLASSES["노조"] = morphology.NAME_PART
    try:
        assert _morphology_hash() != before
    finally:
        morphology.SUFFIX_CLASSES["노조"] = original
    assert _morphology_hash() == before


# --- the LLM-facing path ---------------------------------------------------

def test_context_pack_marks_a_derivative_occurrence(snap):
    """A pack aggregates occurrences into `observed_as`, which is exactly
    where a derivative would vanish: 한국전력공사 observed_as 한전 reads as a
    plain occurrence even when the text said 한전노조."""
    from ktrf.context import build_context_pack, render_context_pack

    resp = resolve(snap, "한전노조가 파업을 예고했다. 한전은 침묵했다.",
                   mode="commit")
    pack = build_context_pack(snap, resp)

    derivative = next(a for a in pack["ambiguous_mentions"]
                      if a.get("appears_inside"))
    assert derivative["appears_inside"]["surface"] == "한전노조"
    assert derivative["appears_inside"]["is_the_same_entity"] is False
    assert derivative["appears_inside"]["refers_to_entity_id"] == \
        "ORG_KEPCO_UNION"

    # and it has to survive rendering, or the model never sees it
    xml = render_context_pack(pack, "xml")
    assert 'appears_inside="한전노조"' in xml and 'same_entity="false"' in xml
    assert "한전노조" in render_context_pack(pack, "text")


def test_a_role_anywhere_in_the_tail_wins_over_a_name_part_head():
    """`은행장과` decomposes as 장 + 과 with a NAME_PART head, so a head-only
    rule reports the bank; the 장 already made it a person. Found by
    `eval.run_composition_audit` on real text, not by construction."""
    r = analyze_residual("장과")
    assert r.classes == ("ROLE", "NAME_PART")
    assert r.full_identity == "DISTINCT"
    assert r.relation == "ROLE_OF"
    # 본부장 is a person too, not the 본부
    assert analyze_residual("본부장").relation == "ROLE_OF"


def test_a_temporal_prefix_is_named_not_silently_identified(snap):
    """`전 한전` is 한전 at another time. VARIANTS_PLAN §2 calls identifying
    the whole with the core *conditional* for a base modifier, so the record
    names the modifier instead of asserting bare identity."""
    m = _mention(resolve(snap, "전 한전 직원이 말했다.", mode="commit"), "한전")
    fs = m["full_surface"]
    assert fs["surface"] == "전 한전"
    assert fs["prefix_kind"] == "TEMPORAL"
    assert "tail_class" not in fs  # nothing followed the core


# --- review findings: the guard's reach and the verdict's consistency ------

@pytest.fixture(scope="module")
def dense_snap():
    """The same glossary with Pass-2 dense retrieval switched on.

    Every guard test above runs on a Level A-only snapshot, which is exactly
    why the dense channel could skip the guard unnoticed: with no encoder
    compiled in, `dense_enrich` returns before it adds anything.
    """
    from ktrf.encoders import HashEncoder
    return compile_snapshot(load_glossary("examples/demo_glossary.yaml"),
                            encoder=HashEncoder())


def test_dense_retrieval_does_not_lift_the_guard(dense_snap):
    """Turning dense on must not turn invariant ② off.

    Dense is Level B and merges into the same pool, so an unguarded dense
    hit clears `commit_blocked` for an entity the tail already refused —
    the abbrev hole again, in the other Pass-2 channel. Measured before the
    fix: identical input, `typed_derivative` with dense off, None with it on.
    """
    resp = resolve(dense_snap, "과학기술정보통신붑장관이 참석했다.", mode="commit")
    m = _mention(resp, "과학기술정보통신붑") or _mention(resp, "과학기술정보통신")
    member = next(x for x in m["prediction_set"]["members"]
                  if x.get("entity_id") == "ORG_MSIT")
    assert "dense" in member["generation_channels"]  # the merging channel
    assert member["commit_blocked"] == "typed_derivative"
    assert m["link_decision"] != "RESOLVED"


def test_no_dense_candidate_escapes_the_guard_on_a_distinct_tail(dense_snap):
    """Not just the entity another channel proposed: every dense hit on a
    span whose tail says DISTINCT has to carry the block too."""
    resp = resolve(dense_snap, "한국전력공사노조가 성명을 냈다.", mode="commit")
    m = _mention(resp, "한국전력공사")
    assert m["full_surface"]["identity"] == "DISTINCT_FROM_CORE"
    dense_only = [x for x in m["prediction_set"]["members"]
                  if x.get("generation_channels") == ["dense"]]
    assert dense_only, "expected dense-only candidates on this span"
    assert all(x["commit_blocked"] == "typed_derivative" for x in dense_only)


@pytest.mark.parametrize("residual,tail_class,relation", [
    ("투자증권", "AFFILIATE", "AFFILIATE_OF"),   # 한국 + 투자증권
    ("아트센터", "ORG_UNIT", "PART_OF"),         # 두산 + 아트센터
    ("서울지사장", "ROLE", "ROLE_OF"),            # a person, not a variant
    ("서울부", "MODIFIER", "NAMED_VARIANT"),      # nothing to the right objects
])
def test_a_modifier_does_not_erase_the_relation(residual, tail_class,
                                                relation):
    """A leading modifier says the *name* differs; the suffix after it still
    says how the two relate, and that is the more specific answer.

    Short-circuiting the modifier to NAMED_VARIANT made `한국투자증권` report
    `tail_class=AFFILIATE` beside `relation=NAMED_VARIANT` — the same
    self-contradiction the governing class removed from `identity`, left
    behind in `relation`. 8.2% of records on real text.
    """
    r = analyze_residual(residual)
    assert r.governing_class == tail_class
    assert r.full_identity == "DISTINCT"     # a modifier is still distinct
    assert r.relation == relation


def test_snapshot_id_tracks_the_class_verdict_table():
    """invariant ⑥ again, for the table rather than the catalog.

    Turning ROLE from DISTINCT to SAME rewrites every verdict while touching
    no suffix surface. Hashing only the catalog left that change resting on
    someone remembering to bump TAIL_GRAMMAR_VERSION by hand.
    """
    from ktrf import morphology
    from ktrf.snapshot import _morphology_hash

    before = _morphology_hash()
    original = morphology.TAIL_CLASSES[morphology.ROLE]
    morphology.TAIL_CLASSES[morphology.ROLE] = (morphology.SAME, "IDENTITY")
    try:
        assert _morphology_hash() != before
    finally:
        morphology.TAIL_CLASSES[morphology.ROLE] = original
    assert _morphology_hash() == before

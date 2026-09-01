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


def test_a_leading_unknown_chunk_always_makes_a_distinct_name():
    """An unknown chunk in front establishes *that* the name differs.

    That much a chunk the catalog cannot read really does settle: 서울부 is
    not 부. What it cannot settle is *how* the two relate, so the relation
    stays UNKNOWN while the identity is firm — the safe half of the claim
    survives and the unsupported half does not.
    """
    # 서울본부 is a unit even though 본부 alone would already say so; the rule
    # has to hold for a NAME_PART head too (서울부 is not 부)
    assert analyze_residual("서울본부").full_identity == "DISTINCT"
    assert analyze_residual("서울본부").relation == "PART_OF"
    assert analyze_residual("서울부").full_identity == "DISTINCT"
    assert analyze_residual("서울부").relation == "UNKNOWN"


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


# --- an attached Latin run is a residual, not a boundary --------------------

def test_an_attached_latin_run_is_reported_as_a_wider_surface(snap):
    """`한전KDN` is another company whose name starts with a registered one.

    (The fixture uses `한국전력공사ICT` because the demo glossary registers
    `한전KDN` itself, so the exact channel would match the whole thing and
    the branch under test would never run.)

    `_is_token_boundary` calls a script change a clean break, so the parser
    never looked to the right of a Hangul core followed by Latin and no
    `full_surface` was emitted at all. That is worse than `농협카드`, where
    the field exists to carry the warning — here a consumer highlighting the
    committed span had nothing telling it the span was part of a longer name.
    """
    m = _mention(resolve(snap, "한국전력공사ICT가 발표했다.", mode="commit"),
                 "한국전력공사")
    assert m is not None
    assert m["full_surface"]["surface"] == "한국전력공사ICT"
    # the catalog has nothing to say about KDN, and says so
    assert m["full_surface"]["identity"] == "UNKNOWN"
    assert m["link_decision"] != "RESOLVED"


def test_a_particle_after_a_latin_run_is_not_part_of_the_name(snap):
    """M2 kept 조사 out of `full_surface`; this path has to honour that too.

    `_right_run` walks to the next space, so the first version of this branch
    reported `한국전력공사ICT가` — a name ending in a subject marker.
    """
    m = _mention(resolve(snap, "한국전력공사ICT가 발표했다.", mode="commit"),
                 "한국전력공사")
    assert m["tail"]["residual"] == "ICT"
    assert m["tail"]["particles"] == ["가"]
    assert m["full_surface"]["surface"].endswith("ICT")


def test_a_run_that_is_another_registered_surface_is_a_boundary(snap):
    """`한전KDN` and `한전AP` differ by whether the run is a name we know.

    Korean headlines drop the punctuation between two organisations
    (`산업부KOTRA`, `삼성전자SKT`), and treating the second one as an
    unexplained residual withheld both commits. The matcher has already found
    the second surface, so the parser only had to ask.

    `eval/run_wild.py` has excluded exactly these from its tail census since
    M0 under the same rule — the evaluation knew and the resolver did not.
    """
    both = resolve(snap, "한전AP가 보도했다.", mode="commit")["mentions"]
    assert {m["surface"] for m in both} == {"한전", "AP"}
    # what the rule governs is the *boundary*: neither surface swallowed the
    # other as a residual. `AP` carries two senses in this glossary and stays
    # ambiguous for that reason, which is a different question.
    assert all("full_surface" not in m for m in both)
    assert _mention(resolve(snap, "한전AP가 보도했다.", mode="commit"),
                    "한전")["link_decision"] == "RESOLVED"


def test_an_attached_digit_run_is_not_a_name_fragment(snap):
    """`과학기술정보통신부2024년` is a year that lost its space, not a company.

    The names this branch exists for append *letters* (KDN, ICT, GRS). The
    first version took any Latin-class run, digits included, and withheld a
    commit the ministry had earned.
    """
    m = _mention(resolve(snap, "과학기술정보통신부2024년 예산", mode="commit"),
                 "과학기술정보통신부")
    assert m["link_decision"] == "RESOLVED"
    assert "full_surface" not in m


def test_a_spaced_latin_word_is_still_a_boundary(snap):
    """`한국전력공사 ICT` is two tokens; only an *attached* run is a residual."""
    m = _mention(resolve(snap, "한국전력공사 ICT가 발표했다.", mode="commit"),
                 "한국전력공사")
    assert m["link_decision"] == "RESOLVED"
    assert "full_surface" not in m


# --- what a tail costs the core -------------------------------------------

def test_an_explained_tail_does_not_cost_the_core_its_commit(snap):
    """`한국전력공사` is the same mention alone and inside `한국전력공사사장`.

    A SOFT boundary asks whether the Hangul running past the core is still
    this name; a residual that decomposes wholly into catalog suffixes has
    answered it, and ``_RESIDUAL_BASE`` already priced how confident that
    answer is. Charging a further 0.6 on top held the core at 0.645 against
    a 0.70 threshold while the bare surface sat at 0.943 — the same entity,
    the same channel, the same span, withheld for a doubt already counted.
    """
    bare = _mention(resolve(snap, "한국전력공사가 오늘 발표했다.", mode="commit"),
                    "한국전력공사")
    with_tail = _mention(
        resolve(snap, "한국전력공사사장이 오늘 발표했다.", mode="commit"),
        "한국전력공사")
    assert bare["link_decision"] == "RESOLVED"
    assert with_tail["link_decision"] == "RESOLVED"
    # and the response still says the wider surface is somebody else
    assert with_tail["full_surface"]["identity"] == "DISTINCT_FROM_CORE"
    assert with_tail["core_link"]["relation"] == "ROLE_OF"


def test_an_unexplained_tail_still_costs_the_core_its_commit(snap):
    """The relaxation is for *explained* tails only.

    `민공원` decomposes as 민 + 원 and reads as SUFFIX_WITH_MODIFIER, which
    looks like an explanation and is not: ``classify_suffix`` hands MODIFIER
    to anything the catalog does not know, so the leading chunk is unknown
    by construction. Accepting that kind committed `부산시` inside
    `부산시민공원`, which is a park.
    """
    from ktrf.morphology import ParticleFST
    from ktrf.segmentation import enumerate_tails

    assert enumerate_tails("민공원", "시", ParticleFST())[0].residual_kind == \
        "SUFFIX_WITH_MODIFIER"
    m = _mention(resolve(snap, "한전민공원에서 모였다.", mode="commit"), "한전")
    assert m is not None and m["link_decision"] != "RESOLVED"


# --- the LLM-facing path ---------------------------------------------------

def test_context_pack_marks_a_derivative_occurrence(snap):
    """A pack aggregates occurrences into `observed_as`, which is exactly
    where a derivative would vanish: 한국전력공사 observed_as 한전 reads as a
    plain occurrence even when the text said 한전노조."""
    from ktrf.context import build_context_pack, render_context_pack

    resp = resolve(snap, "한전노조가 파업을 예고했다. 한전은 침묵했다.",
                   mode="commit")
    pack = build_context_pack(snap, resp)

    # Look in both sections. Whether the core commits is a calibration
    # question and it has already changed once; whether the derivative is
    # *marked* is the contract, and that holds either way. Pinning the
    # section would fail this test for a reason it does not care about — and
    # the committed side matters more, because that is where a consumer is
    # most likely to highlight or substitute the whole surface.
    occurrences = [o for group in (pack["resolved_terms"],
                                   pack["ambiguous_mentions"])
                   for entry in group
                   for o in (entry.get("mentions") or [entry])]
    derivative = next(o for o in occurrences if o.get("appears_inside"))
    assert derivative["appears_inside"]["surface"] == "한전노조"
    assert derivative["appears_inside"]["is_the_same_entity"] is False
    assert derivative["appears_inside"]["refers_to_entity_id"] == \
        "ORG_KEPCO_UNION"

    # and it has to survive rendering, or the model never sees it. Assert on
    # what the render must *say*, not on which syntax says it — the resolved
    # section spells this as an `<appears_inside>` element and the ambiguous
    # one as an attribute, and either is fine for a reader.
    xml = render_context_pack(pack, "xml")
    assert "한전노조" in xml and 'same_entity="false"' in xml
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
    span whose tail says DISTINCT has to carry the block too.

    The core carries a typo on purpose. With a clean `한국전력공사노조` the
    exact channel now commits the core, and a committed mention reports only
    the winner — the dense candidates are still blocked, but the response
    stops showing them, so the assertion below would pass on an empty list.
    A test that can only see what it guards through a prediction set has to
    keep the mention unresolved.
    """
    resp = resolve(dense_snap, "한국전력공삽노조가 성명을 냈다.", mode="commit",
                   options={"return_all_mentions": True,
                            "max_prediction_set": 50})
    m = _mention(resp, "한국전력공삽")
    assert m["link_decision"] != "RESOLVED"
    assert m["full_surface"]["identity"] == "DISTINCT_FROM_CORE"
    dense_only = [x for x in m["prediction_set"]["members"]
                  if x.get("generation_channels") == ["dense"]]
    assert dense_only, "expected dense-only candidates on this span"
    assert all(x["commit_blocked"] == "typed_derivative" for x in dense_only)


@pytest.mark.parametrize("residual,tail_class,relation", [
    ("투자증권", "AFFILIATE", "AFFILIATE_OF"),   # 한국 + 투자증권
    ("아트센터", "ORG_UNIT", "PART_OF"),         # 두산 + 아트센터
    ("서울지사장", "ROLE", "ROLE_OF"),            # a person, not a variant
    ("서울부", "UNKNOWN_PART", "UNKNOWN"),        # nothing to the right objects
])
def test_an_unknown_chunk_does_not_erase_the_relation(residual, tail_class,
                                                      relation):
    """An unknown leading chunk says the *name* differs; a suffix after it
    still says how the two relate, and that is the more specific answer.

    Short-circuiting the chunk to NAMED_VARIANT made `한국투자증권` report
    `tail_class=AFFILIATE` beside `relation=NAMED_VARIANT` — the same
    self-contradiction the governing class removed from `identity`, left
    behind in `relation`. 8.2% of records on real text.

    The last row is the case where the chunk *is* the answer: nothing to its
    right objects, so the whole is a different name and nothing says what
    kind. It used to read NAMED_VARIANT, which is a finding the resolver
    cannot support — DISTINCT is kept, the relation is not asserted.
    """
    r = analyze_residual(residual)
    assert r.governing_class == tail_class
    assert r.full_identity == "DISTINCT"     # an unknown chunk is still distinct
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

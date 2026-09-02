"""What the miner may claim, and what it must refuse to (VARIANTS_PLAN M4).

The miner turns responses into a backlog. Everything here is about the line
it must not cross: it says a name is *there*, never what it means, and it
never writes to a catalog or a glossary.
"""

import pytest

from ktrf.glossary import load_glossary
from ktrf.mining import NameGap, VariantMiner
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary("examples/realorg_glossary.yaml"))


def _mine(snap, texts, **kw):
    miner = VariantMiner(**kw)
    for i, t in enumerate(texts):
        miner.observe(resolve(snap, t, mode="commit"), i, t)
    return miner.report()


# --- the two findings are not the same evidence ----------------------------

def test_a_name_behind_a_registered_core_is_mined(snap):
    """`카카오톡` recurs behind `카카오`, which is a registered surface."""
    report = _mine(snap, ["카카오톡으로 보냈다.", "카카오톡 알림이 왔다.",
                          "카카오톡을 켰다."])
    gaps = {g.surface: g for g in report.name_gaps}
    assert "카카오톡" in gaps
    g = gaps["카카오톡"]
    assert g.entity_id == "ORG_KAKAO"
    assert (g.occurrences, g.documents) == (3, 3)


def test_a_coincidental_prefix_is_not_mined_however_often_it_recurs(snap):
    """`해수욕장` is a beach, not a body of 해양수산부.

    The abbreviation channel reaches `해수` as a subsequence of 해양수산부,
    and the match recurs perfectly because the *word* is common — nine
    documents held it in the census. Recurrence alone therefore cannot be
    the gate; the core has to be a surface the exact channel matched.
    """
    report = _mine(snap, ["해수욕장이 개장했다.", "해수욕장에 갔다.",
                          "해수욕장은 붐볐다.", "해수욕장 근처 숙소."])
    assert not [g for g in report.name_gaps if g.surface == "해수욕장"]
    # and the mention really was there to be mined — this is a gate, not a
    # silence about an input the miner never saw
    assert report.wider_surfaces >= 4


def test_an_ending_behind_several_entities_is_a_suffix_not_a_name(snap):
    """One residual, many entities: the finding is a catalog gap.

    A coincidence would have to repeat across unrelated names, which is why
    this is the *stronger* of the two findings even though it is the one M4
    did not ask for.
    """
    report = _mine(snap, ["경기도교육청과 서울시교육청이 협의했다.",
                          "부산시교육청이 발표했다.",
                          "인천시교육청 담당자가 말했다."],
                   min_entities=2)
    assert any(g.residual == "교육청" for g in report.suffix_gaps)
    gap = next(g for g in report.suffix_gaps if g.residual == "교육청")
    assert gap.entity_count >= 2
    # it is reported *because* the catalog cannot read it
    from ktrf.morphology import SUFFIX_CLASSES
    assert "교육청" not in SUFFIX_CLASSES


def test_an_ending_the_catalog_already_reads_is_not_a_gap(snap):
    """`장관` is classified, so it is not backlog however often it appears."""
    report = _mine(snap, ["기획재정부장관과 국방부장관이 만났다.",
                          "외교부장관이 출국했다.",
                          "법무부장관 임명이 있었다."], min_entities=2)
    assert not [g for g in report.suffix_gaps if g.residual == "장관"]


def test_a_residual_is_reported_as_one_finding_or_the_other(snap):
    """The two findings partition; a cross-entity ending is never a name."""
    report = _mine(snap, ["경기도교육청이 발표했다.", "서울시교육청이 발표했다.",
                          "부산시교육청이 발표했다.", "인천시교육청이 발표했다."],
                   min_entities=2, min_occurrences=1, min_documents=1)
    suffixes = {g.residual for g in report.suffix_gaps}
    names = {g.residual for g in report.name_gaps}
    assert not (suffixes & names)


# --- what the miner refuses ------------------------------------------------

def test_a_mined_name_cannot_become_a_proposal_without_a_reviewer():
    """The miner has evidence, not meaning.

    `canonical` and `short_definition` are keyword-only with no default, and
    blank is refused, so the one thing this loop exists to prevent — a name
    entering a glossary with a meaning nobody supplied — cannot be reached
    by forgetting an argument.
    """
    gap = NameGap("ORG_KAKAO", "톡", "카카오톡", "UNKNOWN", "UNKNOWN",
                  10, 10, ("카카오톡으로 보냈다.",), ("3",))
    with pytest.raises(TypeError):
        gap.to_proposal()                      # type: ignore[call-arg]
    with pytest.raises(ValueError):
        gap.to_proposal(canonical="  ", short_definition="메신저")
    with pytest.raises(ValueError):
        gap.to_proposal(canonical="카카오톡", short_definition="")


def test_a_mined_proposal_never_auto_activates():
    """Origin is `deterministic_detector`, which admission treats as inferred.

    Strong evidence is still not a decision: the surface was *observed*,
    which is more than an LLM proposal can say, and it still routes to a
    state that requires someone to say yes.
    """
    from ktrf.registry.proposals import (TermAdmissionPolicy, TermProposal,
                                         decide_admission)

    gap = NameGap("ORG_KAKAO", "톡", "카카오톡", "UNKNOWN", "UNKNOWN",
                  10, 10, ("카카오톡으로 보냈다.",), ("3",))
    kwargs = gap.to_proposal(canonical="카카오톡", short_definition="메신저")
    assert kwargs["origin"] == "deterministic_detector"
    policy = TermAdmissionPolicy()
    for scope in ("session", "project", "global"):
        proposal = TermProposal(
            proposal_id="tp-x", surface=kwargs["surface"],
            canonical=kwargs["canonical"],
            short_definition=kwargs["short_definition"],
            requested_scope=scope, origin=kwargs["origin"])
        state, _ = decide_admission(proposal, policy, project_trusted=True,
                                    evidence_count=99, distinct_sessions=99)
        assert state != "ACTIVE", f"{scope} auto-activated a mined name"


def test_mined_evidence_cites_documents_rather_than_asserting_the_surface():
    """`surface_present` here is a reading of the corpus, not a claim.

    `validate_term_proposal` requires evidence whose surface was actually
    present. For an LLM proposal that flag is the model's word; for a mined
    one it is the miner's own observation, and the document ids say where.
    """
    gap = NameGap("ORG_KAKAO", "톡", "카카오톡", "UNKNOWN", "UNKNOWN",
                  10, 10, ("카카오톡으로 보냈다.",), ("3", "7"))
    refs = gap.to_proposal(canonical="카카오톡",
                           short_definition="메신저")["evidence_refs"]
    assert [r.entry_id for r in refs] == ["3", "7"]
    assert all(r.surface_present for r in refs)


def test_the_miner_writes_to_no_catalog():
    """§5 forbids adding wild tails to the global catalog unreviewed.

    That is kept structurally, not by intention: a `SuffixGap` has no path
    to a `SUFFIX_CLASSES` entry, and mining a whole corpus leaves the
    catalog byte-identical.
    """
    from ktrf import mining
    from ktrf.morphology import SUFFIX_CLASSES

    before = dict(SUFFIX_CLASSES)
    miner = mining.VariantMiner()
    miner.observe({"mentions": [{
        "surface": "경기도", "generation_channels": ["exact"],
        "core_link": {"surface": "경기도", "relation": "UNKNOWN"},
        "full_surface": {"surface": "경기도교육청", "identity": "UNKNOWN"},
        "resolved_entity": {"entity_id": "ORG_X"}}]}, 0, "경기도교육청")
    miner.report()
    assert dict(SUFFIX_CLASSES) == before
    assert not hasattr(mining.SuffixGap, "to_proposal")


# --- the miner reads only what a response promises -------------------------

def test_an_ambiguous_core_is_not_a_lead():
    """Two candidate entities on one span points two ways; naming either
    would be the guess the loop exists to avoid."""
    miner = VariantMiner(min_occurrences=1, min_documents=1)
    miner.observe({"mentions": [{
        "surface": "AP", "generation_channels": ["exact"],
        "core_link": {"surface": "AP", "relation": "UNKNOWN"},
        "full_surface": {"surface": "AP통신", "identity": "UNKNOWN"},
        "prediction_set": {"members": [{"entity_id": "E1"},
                                       {"entity_id": "E2"}]}}]}, 0, "AP통신")
    assert miner.report().slots == 0


def test_a_surface_the_glossary_already_names_is_not_backlog():
    """invariant ③: a registered COMPOSES_TO already answered it."""
    miner = VariantMiner(min_occurrences=1, min_documents=1)
    miner.observe({"mentions": [{
        "surface": "한전", "generation_channels": ["exact"],
        "core_link": {"surface": "한전", "relation": "DERIVED_FROM"},
        "full_surface": {"surface": "한전노조", "identity": "DISTINCT_FROM_CORE",
                         "composes_to": {"entity_id": "ORG_KEPCO_UNION"}},
        "resolved_entity": {"entity_id": "ORG_KEPCO"}}]}, 0, "한전노조가")
    report = miner.report()
    assert report.already_named == 1
    assert report.name_gaps == []


def test_a_longer_spelling_of_the_same_org_is_not_a_missing_name():
    """`SAME_AS_CORE` is an alias question, not a backlog entry."""
    miner = VariantMiner(min_occurrences=1, min_documents=1)
    miner.observe({"mentions": [{
        "surface": "기획재정", "generation_channels": ["exact"],
        "core_link": {"surface": "기획재정", "relation": "IDENTITY"},
        "full_surface": {"surface": "기획재정부", "identity": "SAME_AS_CORE"},
        "resolved_entity": {"entity_id": "ORG_MOEF"}}]}, 0, "기획재정부가")
    assert miner.report().slots == 0


# --- the loop closes -------------------------------------------------------

def test_an_approved_mined_name_stops_being_backlog(snap):
    """Mine → propose → validate → approve → register → the gap is gone.

    The whole point of the loop is that the backlog *shrinks*. Registering
    the mined name as a standalone entity would not do that: the surface
    would still arrive with nothing relating it to the core, and the next
    pass would mine it again. The `COMPOSES_TO` is what makes invariant ③
    answer it by name.
    """
    import yaml

    from ktrf.registry.proposals import TermProposalStore

    texts = ["카카오톡으로 보냈다.", "카카오톡 알림이 왔다.", "카카오톡을 켰다."]
    gap = next(g for g in _mine(snap, texts).name_gaps
               if g.surface == "카카오톡")

    # a reviewer supplies the meaning the miner refused to invent
    store = TermProposalStore()
    proposal = store.submit(**gap.to_proposal(
        canonical="카카오톡", short_definition="카카오가 운영하는 메신저"))
    assert store.validate(proposal.proposal_id, snap).status == "VALIDATED"
    assert store.route(proposal.proposal_id).status == "VALIDATED"  # not ACTIVE
    assert store.approve(proposal.proposal_id, "reviewer").status == "ACTIVE"

    # register the approved name beside its core, keeping the relation
    doc = yaml.safe_load(open("examples/realorg_glossary.yaml",
                              encoding="utf-8"))
    doc["entities"].append({"entity_id": "ORG_KAKAOTALK",
                            "canonical": "카카오톡",
                            "description": "카카오가 운영하는 메신저",
                            "domain_ids": doc["entities"][0].get("domain_ids")})
    doc.setdefault("entity_relations", []).append(
        gap.to_composition("ORG_KAKAOTALK"))
    # No alias binding for the whole surface, on purpose. That is the shape
    # the shipped `한전`+`노조` case uses: the derivative is named *through*
    # the relation, so invariant ③ is what answers it. Binding the surface
    # too would make the exact channel match the whole thing and the
    # question would never reach the tail.


    from ktrf.glossary import load_glossary as _lg
    import json
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True)
        wider = compile_snapshot(_lg(path))
    finally:
        os.unlink(path)

    after = _mine(wider, texts)
    assert not [g for g in after.name_gaps if g.surface == "카카오톡"]
    assert after.already_named == after.wider_surfaces == len(texts)
    assert json.dumps(after.to_dict())  # the report stays serialisable

    # and the response now *names* it rather than leaving it unexplained
    fs = resolve(wider, texts[0], mode="commit")["mentions"][0]["full_surface"]
    assert fs["composes_to"]["entity_id"] == "ORG_KAKAOTALK"

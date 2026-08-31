"""Shared segmentation, match evidence and Level B guards (VARIANTS_PLAN M1).

The regression these pin: before M1 the exact channel decomposed 조사 and
suffixes while the fuzzy/abbreviation channels queried whole raw tokens, so
``한국전려`` was recoverable and ``한국전려에서도`` was not, and a fuzzy
mention span could cover a particle nothing had analysed.
"""

import pytest

from ktrf.glossary import load_glossary
from ktrf.morphology import ParticleFST
from ktrf.resolver import resolve
from ktrf.segmentation import (
    BARE,
    LATIN_TAIL,
    PARTICLE,
    SUFFIX_PARTICLE,
    MatchEvidence,
    ResolutionGuard,
    StructuralPath,
    distinct_cores,
    enumerate_tails,
    segment_token,
)
from ktrf.snapshot import RuntimePolicy, compile_snapshot

FST = ParticleFST()


def seg(token, start=0, **kw):
    return segment_token(token, (start, start + len(token)), FST, **kw)


def cores(paths):
    return [p.core for p in paths]


# ---------------------------------------------------------------------------
# segment_token
# ---------------------------------------------------------------------------


def test_bare_reading_is_always_present_and_first():
    paths = seg("한국전력")
    assert paths[0].core == "한국전력"
    assert paths[0].kind == BARE
    assert paths[0].core_span == (0, 4)


def test_particle_chain_is_stripped_to_the_core():
    paths = seg("한국전려에서도")
    assert "한국전려" in cores(paths)
    p = next(p for p in paths if p.core == "한국전려")
    assert p.kind == PARTICLE
    assert p.particles == ("에서", "도")
    assert p.core_span == (0, 4)
    assert p.strips_tail is True


def test_core_span_is_absolute_not_token_relative():
    paths = seg("한국전려에서도", start=17)
    p = next(p for p in paths if p.core == "한국전려")
    assert p.core_span == (17, 21)
    assert p.full_span == (17, 24)


def test_suffix_and_particle_decompose_together():
    paths = seg("한국전력본부가")
    p = next(p for p in paths if p.core == "한국전력")
    assert p.kind == SUFFIX_PARTICLE
    assert p.residual == "본부"
    assert p.residual_kind == "SUFFIX"
    assert p.particles == ("가",)


def test_unanalysable_remainder_is_not_a_segmentation():
    # 읭읭 is in no catalog and 읭 is not a particle: `한전읭읭` must not
    # silently become the core `한전` plus junk (invariant 2)
    paths = seg("한전읭읭")
    assert cores(paths) == ["한전읭읭"]


def test_a_typed_derivative_segments_but_denies_full_identity():
    # M2: 노조 *is* a catalog suffix, so `한전노조` does decompose — the
    # safety is no longer "refuse to segment" but "segment and say the whole
    # is a different organisation" (invariant 2)
    p = next(p for p in seg("한전노조") if p.core == "한전")
    assert p.residual == "노조"
    assert p.full_identity == "DISTINCT"
    assert p.relation == "DERIVED_FROM"
    assert p.residual_classes == ("DERIVED_ORG",)


def test_a_referential_tail_keeps_full_identity():
    # `한전측` still refers to 한전 — a REFERENTIAL tail must not be swept
    # into the derivative rule with 노조 and 장
    p = next(p for p in seg("한전측") if p.core == "한전")
    assert p.full_identity == "SAME"
    assert p.relation == "REFERS_TO"


def test_surface_span_excludes_particles_but_keeps_the_residual():
    # a 조사 is grammar, not part of a name: `금감원장이` spells 금감원장
    p = next(p for p in seg("금감원장이") if p.core == "금감원")
    assert p.core_span == (0, 3)
    assert p.surface_span == (0, 4)   # 금감원장
    assert p.full_span == (0, 5)      # 금감원장이


def test_a_core_reached_past_an_unanalysed_tail_must_be_identifying():
    # `셀트루온에서` must not yield the 2-syllable core `셀트`: nothing
    # analysed `루온`, so the core has to stand on its own
    assert all(len(p.core) >= 3 for p in seg("셀트루온에서")
               if p.residual_kind == "UNKNOWN")


def test_ungrammatical_attachment_parses_but_is_marked():
    # 은 requires 받침; 하나 has none, so the reading exists but is flagged
    paths = seg("삼성전자은")
    p = next((p for p in paths if p.core == "삼성전자"), None)
    assert p is not None
    assert p.particles == ("은",)
    assert p.grammatical is False


def test_latin_plural_tail_is_a_path():
    paths = seg("APIs")
    p = next(p for p in paths if p.core == "API")
    assert p.kind == LATIN_TAIL
    assert p.latin_tail == "s"


def test_prefix_modifier_comes_from_left_context():
    paths = seg("한국전력", start=2, left_context="구 ")
    assert paths[0].prefix == "구"
    assert paths[0].prefix_kind == "TEMPORAL"
    assert paths[0].full_span[0] == 0


def test_short_cores_are_not_proposed():
    # a 2-syllable minimum keeps `정도` from becoming core `정` + particle `도`
    assert all(len(p.core) >= 2 for p in seg("정도"))


def test_paths_are_deterministic_and_deduplicated():
    a, b = seg("한국전려에서도"), seg("한국전려에서도")
    assert [p.core_span for p in a] == [p.core_span for p in b]
    spans = [p.core_span for p in distinct_cores(a)]
    assert len(spans) == len(set(spans))


def test_path_budget_of_one_reproduces_pre_m1_behaviour():
    assert cores(seg("한국전려에서도", max_paths=1)) == ["한국전려에서도"]


def test_tail_enumeration_has_one_implementation():
    from ktrf import tailparser

    assert tailparser.TailAnalysis.__module__ == "ktrf.segmentation"
    assert (enumerate_tails("에서도", "려", FST)
            == tailparser.analyze_tail("에서도", "려", FST))


# ---------------------------------------------------------------------------
# MatchEvidence / ResolutionGuard
# ---------------------------------------------------------------------------


def _path(**kw):
    base = dict(token="X", token_span=(0, 1), core="X", core_span=(0, 1))
    base.update(kw)
    return StructuralPath(**base)


def test_guard_never_touches_level_a_evidence():
    guard = ResolutionGuard()
    ev = MatchEvidence.from_path(
        "exact", _path(core="한", residual_kind="UNKNOWN"))
    verdict = guard.evaluate(ev)
    assert verdict.commit_allowed and verdict.score_factor == 1.0


def test_guard_blocks_a_core_too_short_to_carry_identity():
    v = ResolutionGuard().evaluate(
        MatchEvidence.from_path("jamo", _path(core="한", core_span=(0, 1))))
    assert v.commit_allowed is False
    assert "short_core" in v.reasons


def test_guard_blocks_commit_on_an_unanalysable_remainder():
    v = ResolutionGuard().evaluate(MatchEvidence.from_path(
        "abbrev", _path(core="한국전력", core_span=(0, 4),
                        residual="읭읭", residual_kind="UNKNOWN")))
    assert v.commit_allowed is False
    assert v.blocked_reason == "unknown_residual_derivative"
    assert v.score_factor < 1.0


def test_ungrammatical_particle_damps_but_does_not_block():
    v = ResolutionGuard().evaluate(MatchEvidence.from_path(
        "jamo", _path(core="삼성전자", core_span=(0, 4),
                      particles=("은",), grammatical=False)))
    assert v.commit_allowed is True
    assert v.score_factor < 1.0


def test_inferred_tail_ranks_below_an_observed_bare_match():
    guard = ResolutionGuard()
    bare = guard.evaluate(MatchEvidence.from_path(
        "jamo", _path(token="한국전려", core="한국전려",
                      core_span=(0, 4))))
    stripped = guard.evaluate(MatchEvidence.from_path(
        "jamo", _path(token="한국전려에서도", core="한국전려",
                      core_span=(0, 4), particles=("에서", "도"))))
    assert stripped.score_factor < bare.score_factor
    assert stripped.commit_allowed is True


def test_guard_rules_are_configurable():
    guard = ResolutionGuard(rules=["short_core"])
    v = guard.evaluate(MatchEvidence.from_path(
        "jamo", _path(core="한국전력", core_span=(0, 4),
                      residual_kind="UNKNOWN")))
    assert v.commit_allowed is True


def test_evidence_serialises_for_provenance():
    d = MatchEvidence.from_path(
        "jamo", _path(token="한국전려에서도", core="한국전려", core_span=(0, 4),
                      kind=PARTICLE, particles=("에서", "도"))).as_dict()
    assert d["channel"] == "jamo" and d["core"] == "한국전려"
    assert d["tail_stripped"] is True and d["particles"] == ["에서", "도"]


# ---------------------------------------------------------------------------
# End-to-end: every channel reads one decomposition
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def glossary():
    return load_glossary({
        "glossary_id": "seg-test", "version": "1",
        "entities": [
            {"entity_id": "ORG_KEPCO", "canonical": "한국전력공사"},
            {"entity_id": "ORG_MSIT", "canonical": "과학기술정보통신부"},
        ],
        "alias_families": [
            {"family_id": "F_KEPCO", "representative": "한국전력",
             "normalization_profile": "korean_org_name"},
            {"family_id": "F_MSIT", "representative": "과학기술정보통신부",
             "normalization_profile": "korean_org_name"},
        ],
        "alias_bindings": [
            {"alias_id": "A_KEPCO_FULL", "family_id": "F_KEPCO",
             "entity_id": "ORG_KEPCO", "surface": "한국전력"},
            {"alias_id": "A_MSIT_FULL", "family_id": "F_MSIT",
             "entity_id": "ORG_MSIT", "surface": "과학기술정보통신부"},
        ],
    })


@pytest.fixture(scope="module")
def snap(glossary):
    return compile_snapshot(glossary)


def _entities(mention):
    return {m.get("entity_id") for m in mention["prediction_set"]["members"]}


def _find(resp, entity_id):
    for m in resp["mentions"]:
        if entity_id in _entities(m):
            return m
    return None


def test_typo_alone_was_already_recoverable(snap):
    m = _find(resolve(snap, "한국전려 부채가 늘었다."), "ORG_KEPCO")
    assert m is not None


def test_typo_with_a_particle_is_recoverable_after_m1(snap):
    """The M1 headline case: this returned no mention at all before."""
    m = _find(resolve(snap, "한국전려에서도 부채가 늘었다."), "ORG_KEPCO")
    assert m is not None
    cp = m["span"]["codepoint"]
    assert (cp["start"], cp["end"]) == (0, 4)  # the particle is not in the span
    assert m["surface"] == "한국전려"


def test_the_control_setting_still_fails_the_same_case(glossary):
    """Guards the A/B control arm: paths=1 must reproduce pre-M1 behaviour."""
    control = compile_snapshot(glossary,
                               policy=RuntimePolicy(max_segmentation_paths=1))
    assert _find(resolve(control, "한국전려에서도 부채가 늘었다."),
                 "ORG_KEPCO") is None


def test_fuzzy_span_never_swallows_the_particle(snap):
    resp = resolve(snap, "한국전려는 부채가 늘었다.")
    m = _find(resp, "ORG_KEPCO")
    assert m is not None
    assert m["surface"] == "한국전려"


def test_abbreviation_alignment_uses_the_same_decomposition(snap):
    m = _find(resolve(snap, "과기정통부에서도 발표했다."), "ORG_MSIT")
    assert m is not None
    assert m["surface"] == "과기정통부"


def test_level_b_candidates_carry_typed_evidence(snap):
    resp = resolve(snap, "한국전려에서도 부채가 늘었다.",
                   options={"return_features": True})
    m = _find(resp, "ORG_KEPCO")
    assert m["generation_channels"] == ["jamo"]


def test_exact_path_is_unchanged_by_the_guard(snap):
    m = _find(resolve(snap, "한국전력에서도 부채가 늘었다."), "ORG_KEPCO")
    assert m["link_decision"] == "RESOLVED"
    assert m["surface"] == "한국전력"


def test_eval_trace_exposes_the_pre_threshold_ranking(snap):
    """M0 item 3: a number that moves must be diagnosable without a rerun."""
    resp = resolve(snap, "한국전려에서도 부채가 늘었다.",
                   options={"return_eval_trace": True})
    tr = resp["mentions"][0]["eval_trace"]
    assert tr["pool"]["non_exact"] >= 1
    assert tr["prediction_set_truncated"] is False
    top = tr["ranked"][0]
    assert top["rank"] == 0 and top["in_prediction_set"] is True
    # the decomposition that produced the candidate is on the record
    assert top["evidence"]["path_kind"] == "PARTICLE"
    assert top["evidence"]["particles"] == ["에서", "도"]
    assert top["evidence"]["core_span"] == [0, 4]


def test_eval_trace_is_off_by_default(snap):
    resp = resolve(snap, "한국전력이 발표했다.")
    assert "eval_trace" not in resp["mentions"][0]


def test_a_guarded_candidate_is_reported_as_blocked(snap):
    """`과기정통` + an unanalysed `갱` aligns to MSIT but must not commit."""
    resp = resolve(snap, "과기정통갱은 발표했다.",
                   options={"return_all_mentions": True})
    blocked = [mem for m in resp["mentions"]
               for mem in m["prediction_set"]["members"]
               if mem.get("commit_blocked")]
    assert blocked, "expected a guard-blocked member"
    assert blocked[0]["commit_blocked"] == "unknown_residual_derivative"
    assert all(m["link_decision"] != "RESOLVED" for m in resp["mentions"])


def test_explain_names_the_guard_that_withheld_a_commit():
    from ktrf.explain import _blocking_reason
    from ktrf.snapshot import RuntimePolicy

    mention = {
        "link_decision": "AMBIGUOUS", "mention_decision": "TERM",
        "prediction_set": {"members": [
            {"kind": "ENTITY", "entity_id": "E", "calibrated_probability": 0.9,
             "commit_blocked": "unknown_residual_derivative"},
        ]},
    }
    reason = _blocking_reason(mention, RuntimePolicy())
    assert reason["reason"] == "guard_blocked"
    assert reason["guard"] == "unknown_residual_derivative"


def test_guard_config_changes_snapshot_identity(glossary):
    """Invariant 6: a resolution-affecting knob is part of the artifact id."""
    a = compile_snapshot(glossary)
    b = compile_snapshot(glossary, guard=ResolutionGuard(rules=["short_core"]))
    assert a.snapshot_id != b.snapshot_id
    assert a.manifest["segmentation_guard_hash"] \
        != b.manifest["segmentation_guard_hash"]


def test_blocked_commit_keeps_the_candidate_in_the_prediction_set(snap):
    """Invariant 4: generation and commit are separate decisions."""
    from ktrf.candidates import Candidate, CandidatePool
    from ktrf.snapshot import CandidateBudget

    pool = CandidatePool(CandidateBudget())
    pool.add(Candidate(entity_id="ORG_KEPCO", alias_id=None, family_id=None,
                       commit_blocked="unknown_residual_derivative"))
    assert len(pool.all_candidates()) == 1
    assert pool.all_candidates()[0].commit_blocked is not None


def test_unblocked_evidence_for_the_same_entity_lifts_the_block():
    from ktrf.candidates import Candidate, CandidatePool
    from ktrf.snapshot import CandidateBudget

    pool = CandidatePool(CandidateBudget())
    pool.add(Candidate(entity_id="E", alias_id=None, family_id=None,
                       generation_channels={"abbrev"},
                       commit_blocked="unknown_residual_derivative"))
    pool.add(Candidate(entity_id="E", alias_id=None, family_id=None,
                       generation_channels={"jamo"}))
    assert pool.all_candidates()[0].commit_blocked is None

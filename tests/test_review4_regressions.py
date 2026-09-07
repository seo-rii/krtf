"""REVIEW_4 (2026-09-07) — the two findings that reproduced against HEAD.

The review was made against `origin/main` (cb953cd), 66 commits behind this
tree, and seven of its nine finding groups no longer reproduce here: the
prediction-set truncation no longer feeds the commit decision (F01), bundles
refuse a missing or tampered artifact and round-trip a custom guard (F02),
`compile_snapshot` detaches its glossary (F03), the calibrator reports a
non-disjoint split and the resolver voids coverage for it (F04), the pack
reports its own candidate cuts, reduces document definitions under the token
budget and recomputes its stats afterwards (F05), the grounding validator
rejects a surface the pack never offered (F06), and chunked jobs globalise
every span record including `full_surface` (F07).

These two did reproduce, and are what this file pins.
"""

import pytest

from ktrf.glossary import load_glossary
from ktrf.registry import proposals as P
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot


def _snapshot():
    return compile_snapshot(load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "ORG_KEPCO", "canonical": "한국전력공사",
                      "description": "전력 공기업"}],
        "alias_bindings": [
            {"alias_id": "A1", "family_id": "F1", "entity_id": "ORG_KEPCO",
             "surface": "한전", "kind": "abbreviation",
             "boundary_policy": {"left": "hangul_token_boundary"}}],
    }), strict=False)


def _evidence(n=3):
    return tuple(P.EvidenceRef(entry_id=f"e{i}", surface_present=True,
                               definition_pattern=True, session_id=f"s{i}",
                               trusted_source=True) for i in range(n))


def _validated(store, snapshot, **kw):
    kw.setdefault("canonical", "신규용어 정식명칭")
    kw.setdefault("short_definition", "사내 신규 용어")
    kw.setdefault("origin", "user_explicit")
    kw.setdefault("evidence_refs", _evidence())
    p = store.submit(**kw)
    return store.validate(p.proposal_id, snapshot)


# --------------------------------------------------------------------- F08
def test_a_colliding_alias_is_refused_like_a_colliding_surface():
    """`한전` is bound to ORG_KEPCO. Proposing it as the main surface was
    already refused; hiding it in `aliases` validated cleanly, and
    `active_terms_doc` then exported it as one of the term's surfaces."""
    snap = _snapshot()
    store = P.TermProposalStore()

    control = _validated(store, snap, surface="한전")
    assert control.validation_report["checks"]["no_alias_collision"] is False

    hidden = _validated(store, snap, surface="신규용어", aliases=("한전",))
    checks = hidden.validation_report["checks"]
    assert checks["no_alias_collision"] is False, (
        "an alias colliding with a registered surface passed validation")
    assert any("한전" in r for r in hidden.validation_report["reasons"])


def test_every_alias_faces_the_checks_the_surface_faces():
    snap = _snapshot()
    store = P.TermProposalStore()

    blank = _validated(store, snap, surface="정상용어", aliases=("   ",))
    assert blank.validation_report["checks"]["surface_nonempty"] is False

    ctrl = _validated(store, snap, surface="정상용어", aliases=("나쁜\x07별칭",))
    assert ctrl.validation_report["checks"]["no_control_chars"] is False

    long = _validated(store, snap, surface="정상용어",
                      aliases=("가" * (P.MAX_CANONICAL_CHARS + 1),))
    assert long.validation_report["checks"]["length_limits"] is False


def test_an_alias_repeating_the_surface_is_not_a_second_surface():
    snap = _snapshot()
    store = P.TermProposalStore()
    dup = _validated(store, snap, surface="정상용어",
                     aliases=("정상용어", "정상용어"))
    assert dup.validation_report["checks"]["aliases_distinct"] is False


def test_a_clean_alias_still_validates():
    """The check must not simply refuse every alias."""
    snap = _snapshot()
    store = P.TermProposalStore()
    ok = _validated(store, snap, surface="제타파이프",
                    aliases=("제타파이프라인",))
    assert ok.status == "VALIDATED", ok.validation_report["reasons"]


# --------------------------------------------------------------------- F09
def test_active_means_resolvable_or_it_does_not_say_active():
    """PLAN_PI.md §ACTIVE: "승인 정책을 통과해 실제 glossary snapshot에
    포함된 상태". The store reached ACTIVE while `resolve` still found
    nothing and the snapshot id was unchanged."""
    snap = _snapshot()
    store = P.TermProposalStore()
    p = _validated(store, snap, surface="제타파이프",
                   canonical="제타파이프라인", requested_scope="project")
    p = store.route(p.proposal_id, project_trusted=True, evidence_count=3,
                    distinct_sessions=2)
    if p.status != "ACTIVE":
        p = store.approve(p.proposal_id, "user")

    if p.status == "ACTIVE":
        active = store.active_snapshot()
        assert active is not None, (
            "status is ACTIVE but the store exposes no snapshot containing it")
        found = [m["surface"] for m in
                 resolve(active, "제타파이프가 오늘 정산을 마쳤다.")["mentions"]]
        assert found, "ACTIVE term is not resolvable in the active snapshot"
    else:
        assert p.status == "APPROVED", (
            f"approval without activation must not read as ACTIVE; got "
            f"{p.status!r}")


def test_approval_without_an_activation_target_does_not_claim_active():
    """A store with nowhere to compile into cannot honestly report ACTIVE."""
    snap = _snapshot()
    store = P.TermProposalStore()
    p = _validated(store, snap, surface="제타파이프",
                   canonical="제타파이프라인", requested_scope="project")
    p = store.route(p.proposal_id, project_trusted=True, evidence_count=3,
                    distinct_sessions=2)
    if p.status != "ACTIVE":
        p = store.approve(p.proposal_id, "user")
    assert p.status != "ACTIVE" or store.active_snapshot() is not None


def test_active_terms_doc_only_lists_terms_that_are_really_active():
    snap = _snapshot()
    store = P.TermProposalStore()
    p = _validated(store, snap, surface="제타파이프",
                   canonical="제타파이프라인", requested_scope="project")
    p = store.route(p.proposal_id, project_trusted=True, evidence_count=3,
                    distinct_sessions=2)
    if p.status != "ACTIVE":
        p = store.approve(p.proposal_id, "user")
    listed = store.active_terms_doc("project")["terms"]
    if p.status != "ACTIVE":
        assert not listed, (
            f"status {p.status!r} but the term is exported as active")



def test_activate_compiles_the_term_and_then_it_resolves():
    """The other half of F09: stopping at APPROVED is only honest if there
    is a step that really does make the term live."""
    from ktrf.registry.layers import TermLayer

    snap = _snapshot()
    store = P.TermProposalStore()
    p = _validated(store, snap, surface="제타파이프",
                   canonical="제타파이프라인", requested_scope="project")
    p = store.route(p.proposal_id, project_trusted=True, evidence_count=3,
                    distinct_sessions=2)
    if p.status != "ACTIVE":
        p = store.approve(p.proposal_id, "user")
    assert p.status == "APPROVED"
    assert store.active_snapshot() is None
    assert store.active_terms_doc("project")["terms"] == []

    base = TermLayer(scope="global", doc={
        "schema_version": 1,
        "terms": [{"key": "kepco", "canonical": "한국전력공사",
                   "surfaces": ["한국전력공사", "한전"],
                   "short_definition": "전력 공기업"}]}, trusted=True)
    report = store.activate("project", base_layers=[base])

    assert store.get(p.proposal_id).status == "ACTIVE"
    active = store.active_snapshot()
    assert active is not None
    assert report["snapshot_id"] == active.snapshot_id
    found = [m["surface"] for m in
             resolve(active, "제타파이프가 오늘 정산을 마쳤다.")["mentions"]]
    assert "제타파이프" in found, found
    assert [t["canonical"] for t in
            store.active_terms_doc("project")["terms"]] == ["제타파이프라인"]


def test_a_failed_activation_leaves_every_status_alone():
    snap = _snapshot()
    store = P.TermProposalStore()
    p = _validated(store, snap, surface="제타파이프",
                   canonical="제타파이프라인", requested_scope="project")
    p = store.route(p.proposal_id, project_trusted=True, evidence_count=3,
                    distinct_sessions=2)
    if p.status != "ACTIVE":
        p = store.approve(p.proposal_id, "user")

    class Boom:
        scope = "global"
        doc = {"schema_version": 1, "terms": [{"nonsense": True}]}
        trusted = True

    with pytest.raises(Exception):
        store.activate("project", base_layers=[Boom()])
    assert store.get(p.proposal_id).status == "APPROVED"
    assert store.active_snapshot() is None

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_the_sidecar_can_activate_what_it_approved():
    """F09 end to end through the PI runtime: the review's own path.

    Propose ZXQ, validate, route, approve — and then the term still is not
    resolvable until `activate_proposals` compiles it, at which point the
    runtime answers from the snapshot that was just proved to contain it."""
    from ktrf.integrations.pi_stdio import PiRuntime

    rt = PiRuntime()
    rt.initialize({})
    rt.load_layers({"sources": {"global": {
        "schema_version": 1,
        "terms": [{"key": "kepco", "canonical": "한국전력공사",
                   "surfaces": ["한국전력공사", "한전"],
                   "short_definition": "전력 공기업"}]}},
        "trusted_scopes": ["global"]})
    before_id = rt.snapshot.snapshot_id

    p = rt.propose_term({
        "surface": "제타파이프", "canonical": "제타파이프라인",
        "short_definition": "야간 배치 정산 사내 파이프라인",
        "scope": "project", "origin": "user_explicit",
        "evidence_refs": [{"entry_id": "e1", "surface_present": True,
                           "definition_pattern": True, "session_id": "s1",
                           "trusted_source": True}]})
    pid = p["proposal_id"]
    rt.validate_proposal({"proposal_id": pid})
    routed = rt.route_proposal({"proposal_id": pid, "project_trusted": True,
                                "evidence_count": 3, "distinct_sessions": 2})
    approved = routed if routed["status"] == "APPROVED" else         rt.approve_proposal({"proposal_id": pid, "approver": "user"})
    assert approved["status"] == "APPROVED"
    assert rt.snapshot.snapshot_id == before_id
    assert not rt.resolve({"text": "제타파이프가 정산을 마쳤다."})["mentions"]

    report = rt.activate_proposals({"scope": "project"})
    assert rt.snapshot.snapshot_id == report["snapshot_id"] != before_id
    found = [m["surface"] for m in
             rt.resolve({"text": "제타파이프가 정산을 마쳤다."})["mentions"]]
    assert "제타파이프" in found, found

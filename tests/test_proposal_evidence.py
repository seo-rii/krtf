"""Proposal evidence is established by the sidecar, not asserted by the proposer.

`propose_term` used to build `EvidenceRef`s straight from request fields, with
`trusted_source` defaulting to True, and `route_proposal` took
`project_trusted`, `evidence_count` and `distinct_sessions` as parameters. The
model proposing a term could therefore write `surface_present: true` for a
surface nobody typed, and the call asking for project auto-promotion said how
much evidence it had. PLAN_PI's `ktrf_propose_term` names only
`evidence_entry_ids`; what those entries say is the host's to record.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ktrf.errors import ERROR_TABLE, KtrfApiError
from ktrf.integrations.pi_stdio import PiRuntime, handle_request

TERM = {"surface": "제타파이프", "canonical": "제타파이프라인",
        "short_definition": "야간 배치 정산 사내 파이프라인",
        "scope": "project", "origin": "user_explicit"}
DEFINING = "제타파이프는 제타파이프라인을 줄여 부르는 말이다."
GLOBAL = {"schema_version": 1,
          "terms": [{"key": "kepco", "canonical": "한국전력공사",
                     "surfaces": ["한국전력공사", "한전"],
                     "short_definition": "전력 공기업"}]}


def _rt(trusted=("global", "project"), **policy):
    rt = PiRuntime()
    rt.initialize({"admission_policy": policy})
    rt.load_layers({"sources": {"global": GLOBAL},
                    "trusted_scopes": list(trusted)})
    return rt


def _call(rt, method, params):
    return handle_request(rt, {"id": 1, "method": method, "params": params})


def _propose_validate(rt, ids):
    p = rt.propose_term({**TERM, "evidence_entry_ids": ids})
    return rt.validate_proposal({"proposal_id": p["proposal_id"]})


# ------------------------------------------------------------ propose_term
@pytest.mark.parametrize("field", ["surface_present", "trusted_source",
                                   "definition_pattern", "session_id"])
def test_a_proposer_cannot_assert_evidence(field):
    rt = _rt()
    r = _call(rt, "propose_term", {**TERM, "evidence_refs": [
        {"entry_id": "m-1", field: True}]})
    assert "error" in r and "record_entry" in r["error"]["message"]


def test_citing_an_entry_nobody_recorded_proves_nothing():
    v = _propose_validate(_rt(), ["m-404"])
    assert v["status"] == "REJECTED"
    assert v["validation_report"]["checks"]["evidence_surface_present"] is False


def test_an_entry_that_does_not_contain_the_surface_proves_nothing():
    rt = _rt()
    rt.record_entry({"entry_id": "m-1", "trusted": True,
                     "text": "정산 배치가 오늘도 늦게 끝났다."})
    assert _propose_validate(rt, ["m-1"])["status"] == "REJECTED"


def test_untrusted_text_containing_the_surface_proves_nothing():
    """A tool result or a fetched web page can say anything — including the
    exact definition a prompt injection wants registered."""
    rt = _rt()
    rt.record_entry({"entry_id": "tool-1", "trusted": False,
                     "text": DEFINING})
    assert _propose_validate(rt, ["tool-1"])["status"] == "REJECTED"


def test_recorded_trusted_evidence_validates_and_is_computed():
    rt = _rt()
    rt.record_entry({"entry_id": "m-1", "session_id": "s1", "trusted": True,
                     "text": DEFINING})
    p = rt.propose_term({**TERM, "evidence_entry_ids": ["m-1"]})
    ref = p["evidence_refs"][0]
    assert ref == {"entry_id": "m-1", "surface_present": True,
                   "definition_pattern": True, "session_id": "s1",
                   "trusted_source": True}
    v = rt.validate_proposal({"proposal_id": p["proposal_id"]})
    assert v["status"] == "VALIDATED", v["validation_report"]


def test_surface_matching_uses_the_matcher_fold():
    """Fullwidth/case variants are the same string to the matcher, so they are
    the same evidence here; a bespoke rule would drift from what resolves."""
    rt = _rt()
    rt.record_entry({"entry_id": "m-1", "trusted": True,
                     "text": "ＰＤＡＦ는 Project Data Access Framework다."})
    p = rt.propose_term({**TERM, "surface": "PDAF",
                         "canonical": "Project Data Access Framework",
                         "evidence_entry_ids": ["m-1"]})
    assert p["evidence_refs"][0]["surface_present"] is True


# ------------------------------------------------------------ record_entry
def test_recorded_evidence_cannot_be_rewritten():
    rt = _rt()
    rt.record_entry({"entry_id": "m-1", "trusted": False, "text": "무관한 글"})
    r = _call(rt, "record_entry", {"entry_id": "m-1", "trusted": True,
                                   "text": DEFINING})
    assert r["error"]["code"] == "INVALID_REQUEST"
    # an identical re-record is idempotent, not an error
    assert "result" in _call(rt, "record_entry", {
        "entry_id": "m-1", "trusted": False, "text": "무관한 글"})


def test_entries_are_bounded():
    rt = _rt()
    r = _call(rt, "record_entry", {"entry_id": "big", "text": "가" * 70_000})
    assert r["error"]["code"] == "INVALID_REQUEST"


# ---------------------------------------------------------- route_proposal
@pytest.mark.parametrize("field", ["project_trusted", "evidence_count",
                                   "distinct_sessions"])
def test_routing_facts_are_not_request_parameters(field):
    rt = _rt()
    rt.record_entry({"entry_id": "m-1", "trusted": True, "text": DEFINING})
    p = rt.propose_term({**TERM, "evidence_entry_ids": ["m-1"]})
    rt.validate_proposal({"proposal_id": p["proposal_id"]})
    r = _call(rt, "route_proposal", {"proposal_id": p["proposal_id"],
                                     field: 99})
    assert "error" in r and field in r["error"]["message"]


def _route(rt, entries):
    for i, (session, trusted, text) in enumerate(entries):
        rt.record_entry({"entry_id": f"m-{i}", "session_id": session,
                         "trusted": trusted, "text": text})
    p = rt.propose_term({**TERM, "evidence_entry_ids": ["m-0"]})
    rt.validate_proposal({"proposal_id": p["proposal_id"]})
    return rt.route_proposal({"proposal_id": p["proposal_id"]})


AUTO = dict(allow_project_auto=True)


def test_project_auto_promotion_counts_the_ledger():
    routed = _route(_rt(**AUTO), [("s1", True, DEFINING),
                                  ("s1", True, DEFINING + " 다시."),
                                  ("s2", True, "참고로 " + DEFINING)])
    assert routed["status"] == "APPROVED", routed
    assert routed["evidence_support"]["evidence_count"] == 3
    assert routed["evidence_support"]["distinct_sessions"] == 2


def test_one_session_repeating_itself_is_not_two():
    routed = _route(_rt(**AUTO), [("s1", True, DEFINING)] + [
        ("s1", True, f"{DEFINING} ({i})") for i in range(5)])
    assert routed["status"] == "VALIDATED"
    assert routed["evidence_support"]["distinct_sessions"] == 1


def test_untrusted_repetitions_do_not_count_toward_promotion():
    routed = _route(_rt(**AUTO), [("s1", True, DEFINING)] + [
        (f"web-{i}", False, f"{DEFINING} ({i})") for i in range(5)])
    assert routed["status"] == "VALIDATED"
    assert routed["evidence_support"]["evidence_count"] == 1


def test_mentions_without_the_expansion_are_not_definitions():
    routed = _route(_rt(**AUTO), [("s1", True, DEFINING),
                                  ("s2", True, "제타파이프가 또 멈췄다."),
                                  ("s3", True, "제타파이프 재시작 요청")])
    assert routed["status"] == "VALIDATED"
    assert routed["evidence_support"]["evidence_count"] == 1


def test_project_trust_comes_from_load_layers():
    entries = [(f"s{i}", True, f"{DEFINING} ({i})") for i in range(3)]
    assert _route(_rt(trusted=("global",), **AUTO),
                  entries)["status"] == "VALIDATED"


def test_a_sidecar_with_no_layers_does_not_assume_a_trusted_project():
    rt = PiRuntime()
    rt.initialize({"admission_policy": AUTO})
    assert rt.trusted_scopes == set()


# ------------------------------------------------------------- error codes
def test_an_unknown_proposal_is_a_bad_request_not_a_retryable_500():
    r = _call(_rt(), "validate_proposal", {"proposal_id": "tp-nope"})
    assert r["error"]["code"] == "INVALID_REQUEST"


def test_every_raised_error_code_is_registered():
    """`KtrfApiError` coerces an unregistered code to INTERNAL — a retryable
    500 — so a typo'd or invented code is a silent wrong answer to the host.
    `NOT_FOUND` had been one since the proposal store was written."""
    root = Path(__file__).resolve().parent.parent / "ktrf"
    raised = set()
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        raised |= set(re.findall(r'KtrfApiError\(\s*"([A-Z_]+)"', src))
    assert raised and raised <= set(ERROR_TABLE), raised - set(ERROR_TABLE)
    assert KtrfApiError("NO_SUCH_CODE", "x").code == "INTERNAL"


# ------------------------------------------------------------------ origin
def _session(rt, text, origin="user_explicit"):
    rt.record_entry({"entry_id": "m-1", "trusted": True, "text": text})
    p = rt.propose_term({**TERM, "scope": "session", "origin": origin,
                         "evidence_entry_ids": ["m-1"]})
    rt.validate_proposal({"proposal_id": p["proposal_id"]})
    return rt.route_proposal({"proposal_id": p["proposal_id"]})["status"]


def test_an_explicit_origin_needs_a_definition_in_the_evidence():
    """The user typed the surface but never defined it; the model labelled
    its own expansion `user_explicit`. That is an inference, not a
    definition, and it must not auto-approve."""
    assert _session(_rt(), DEFINING) == "APPROVED"            # control
    assert _session(_rt(), "제타파이프 로그 좀 봐줘.") != "APPROVED"


def test_the_ledger_is_bounded(monkeypatch):
    import ktrf.registry.proposals as P

    monkeypatch.setattr(P, "MAX_ENTRIES", 3)
    rt = _rt()
    for i in range(3):
        rt.record_entry({"entry_id": f"m-{i}", "text": "글"})
    r = _call(rt, "record_entry", {"entry_id": "m-3", "text": "글"})
    assert r["error"]["code"] == "RATE_LIMITED"
    # re-recording an existing entry is not growth
    assert "result" in _call(rt, "record_entry",
                             {"entry_id": "m-0", "text": "글"})


def test_routing_does_not_renormalise_the_ledger(monkeypatch):
    """Each entry's matcher view is computed once, when it is recorded."""
    import ktrf.registry.proposals as P

    rt = _rt(**AUTO)
    for i in range(5):
        rt.record_entry({"entry_id": f"m-{i}", "session_id": f"s{i}",
                         "trusted": True, "text": DEFINING * 50})
    p = rt.propose_term({**TERM, "evidence_entry_ids": ["m-0"]})
    rt.validate_proposal({"proposal_id": p["proposal_id"]})
    seen = []
    real = P._collation_key
    monkeypatch.setattr(P, "_collation_key",
                        lambda s: (seen.append(len(s)), real(s))[1])
    routed = rt.route_proposal({"proposal_id": p["proposal_id"]})
    assert routed["evidence_support"]["evidence_count"] == 5
    assert max(seen) < len(DEFINING), "an entry's text was re-normalised"

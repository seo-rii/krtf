"""Resolve API contract tests (spec §26, §27; §21.5; §12.4).

REQ-API-001..005, REQ-CAND-001/002, REQ-TEN-003/004, REQ-TRM-001,
INV-002, INV-004, INV-005, INV-011, INV-016, INV-019, REQ-GRPH-001.
"""

import pytest

from ktrf.candidates import CandidateBudget
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import RuntimePolicy, compile_snapshot


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary("examples/demo_glossary.yaml"))


REFERENCE = "한전KDN은 AP 장애 내용을 QMS에 등록했다."


def _mention(resp, surface):
    for m in resp["mentions"]:
        if m["surface"] == surface:
            return m
    return None


def test_reference_sentence_spans(snap):
    # §13.4 + §27.3: byte/codepoint/utf16 offsets, INV-002
    resp = resolve(snap, REFERENCE, mode="commit")
    kdn = _mention(resp, "한전KDN")
    assert kdn["span"] == {
        "byte": {"start": 0, "end": 9},
        "codepoint": {"start": 0, "end": 5},
        "utf16": {"start": 0, "end": 5},
    }
    ap = _mention(resp, "AP")
    assert ap["span"]["byte"] == {"start": 13, "end": 15}
    qms = _mention(resp, "QMS")
    assert qms["span"]["byte"] == {"start": 33, "end": 36}
    for m in resp["mentions"]:
        cp = m["span"]["codepoint"]
        assert REFERENCE[cp["start"]:cp["end"]] == m["surface"]


def test_reference_sentence_decisions(snap):
    resp = resolve(snap, REFERENCE, mode="commit")
    assert _mention(resp, "한전KDN")["link_decision"] == "RESOLVED"
    ap = _mention(resp, "AP")
    assert ap["link_decision"] == "AMBIGUOUS"
    # INV-004: both AP senses preserved
    ids = {x.get("entity_id") for x in ap["prediction_set"]["members"]}
    assert {"NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS"} <= ids
    assert _mention(resp, "QMS")["link_decision"] == "RESOLVED"
    # snapshot provenance always present (§27.5)
    assert resp["snapshot"]["snapshot_id"].startswith("snap-")


def test_marginal_probabilities_not_normalized(snap):
    # §7.12/INV-019: marginals may sum past 1.0; each in (0,1)
    resp = resolve(snap, "AP 처리가 지연되고 있습니다.", mode="commit")
    ap = _mention(resp, "AP")
    ps = [x["calibrated_probability"] for x in ap["prediction_set"]["members"]
          if x["kind"] == "ENTITY"]
    assert all(0.0 < p < 1.0 for p in ps)
    # ranking_score is a separate field (INV-011)
    assert all("ranking_score" in x for x in ap["prediction_set"]["members"]
               if x["kind"] == "ENTITY")


def test_fast_mode_contract(snap):
    # §26.1/REQ-API-001: no calibration, single-sense RESOLVED, multi AMBIGUOUS
    resp = resolve(snap, REFERENCE, mode="fast")
    kdn = _mention(resp, "한전KDN")
    assert kdn["link_decision"] == "RESOLVED"
    assert "calibrated_probability" not in kdn.get("resolved_entity", {})
    ap = _mention(resp, "AP")
    assert ap["link_decision"] == "AMBIGUOUS"
    for member in ap["prediction_set"]["members"]:
        assert "calibrated_probability" not in member


def test_fast_mode_no_pass2(snap):
    # REQ-CAND-005: 과기정통부 needs abbreviation alignment (Pass 2)
    fast = resolve(snap, "과기정통부에서 발표했다.", mode="fast",
                   options={"return_trace": True})
    assert not fast["mentions"]
    assert fast["trace"]["pass2_executed"] is False
    commit = resolve(snap, "과기정통부에서 발표했다.", mode="commit",
                     options={"return_trace": True})
    assert commit["trace"]["pass2_executed"] is True
    m = _mention(commit, "과기정통부")
    assert m is not None
    ids = {x.get("entity_id") for x in m["prediction_set"]["members"]}
    assert "ORG_MSIT" in ids


def test_input_too_large(snap):
    # §27.2/REQ-API-003: 64KB sync limit
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, "가" * 30000, mode="commit")  # 90KB in UTF-8
    assert e.value.code == "INPUT_TOO_LARGE"
    assert e.value.http_status == 413


def test_invalid_utf8_not_repaired(snap):
    # §13.6/REQ-OFF-004
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, b"\xff\xfe" + "한전".encode("utf-8"), mode="commit")
    assert e.value.code == "INVALID_UTF8"


def test_invalid_mode(snap):
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, "한전", mode="warp")
    assert e.value.code == "INVALID_REQUEST"


def test_error_schema_shape(snap):
    try:
        resolve(snap, "가" * 30000)
    except KtrfApiError as e:
        d = e.to_dict()["error"]
        assert set(d) == {"code", "message", "retryable", "details"}
        assert d["retryable"] is False


def test_exact_pool_budget_exempt(snap):
    # INV-005/REQ-CAND-001: zero non-exact budget cannot cut exact senses
    policy = RuntimePolicy(candidate_budget=CandidateBudget(
        max_non_exact_candidates=0))
    tight = compile_snapshot(load_glossary("examples/demo_glossary.yaml"),
                             policy=policy)
    resp = resolve(tight, "AP 확인 요청", mode="commit")
    ap = _mention(resp, "AP")
    ids = {x.get("entity_id") for x in ap["prediction_set"]["members"]}
    assert {"NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS"} <= ids


def test_exact_overflow_degrades_to_ambiguous(snap):
    # §21.5/REQ-CAND-003: beyond max_exact_senses -> AMBIGUOUS + degraded,
    # senses never dropped
    policy = RuntimePolicy(candidate_budget=CandidateBudget(max_exact_senses=1))
    tight = compile_snapshot(load_glossary("examples/demo_glossary.yaml"),
                             policy=policy)
    resp = resolve(tight, "AP 확인 요청", mode="commit")
    ap = _mention(resp, "AP")
    assert ap["link_decision"] == "AMBIGUOUS"
    assert resp["degraded"] is True
    ids = {x.get("entity_id") for x in ap["prediction_set"]["members"]}
    assert {"NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS"} <= ids


def test_scope_deny_hard_only_at_verified_trust(snap):
    # §12.4/REQ-TEN-004: build glossary with a deny scope on one AP sense
    data = load_glossary("examples/demo_glossary.yaml")
    raw = {
        "glossary_id": "t2", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_A", "canonical": "Alpha", "description": "a"},
            {"entity_id": "E_B", "canonical": "Beta", "description": "b"},
        ],
        "alias_families": [
            {"family_id": "F", "representative": "XY",
             "normalization_profile": "latin_acronym"},
        ],
        "alias_bindings": [
            {"alias_id": "XA", "family_id": "F", "entity_id": "E_A",
             "surface": "XY",
             "boundary_policy": {"left": "latin_token_boundary"},
             "scope": {"deny": {"departments": ["finance"]}}},
            {"alias_id": "XB", "family_id": "F", "entity_id": "E_B",
             "surface": "XY",
             "boundary_policy": {"left": "latin_token_boundary"}},
        ],
    }
    snap2 = compile_snapshot(load_glossary(raw))
    ctx_hard = {"department": {"value": "finance", "trust": "AUTH_CLAIM"}}
    resp = resolve(snap2, "XY 검토", mode="commit", context=ctx_hard)
    ids = {x.get("entity_id") for x in
           _mention(resp, "XY")["prediction_set"]["members"]}
    assert "E_A" not in ids and "E_B" in ids  # hard removal
    ctx_soft = {"department": {"value": "finance", "trust": "USER_PROVIDED"}}
    resp = resolve(snap2, "XY 검토", mode="commit", context=ctx_soft)
    ids = {x.get("entity_id") for x in
           _mention(resp, "XY")["prediction_set"]["members"]}
    assert "E_A" in ids  # soft only: candidate preserved


def test_allow_mismatch_always_soft(snap):
    # REQ-TEN-003: AP network sense has allow: departments [network]
    ctx = {"department": {"value": "finance", "trust": "SERVER_VERIFIED"}}
    resp = resolve(snap, "AP 확인", mode="commit", context=ctx)
    ids = {x.get("entity_id") for x in
           _mention(resp, "AP")["prediction_set"]["members"]}
    assert "NETWORK_ACCESS_POINT" in ids  # never hard-filtered


def test_uncertain_mention_never_resolved(snap):
    # INV-016/REQ-TRM-001: keyboard-only evidence -> UNCERTAIN mention
    resp = resolve(snap, "gkswjs 문의드립니다", mode="aggressive")
    m = _mention(resp, "gkswjs")
    assert m is not None
    assert m["mention_decision"] == "UNCERTAIN"
    assert m["link_decision"] != "RESOLVED"


def test_primary_vs_all_mentions(snap):
    # §20.4: nested 한전 suppressed from primary; available via all_mentions
    resp = resolve(snap, "한전KDN은 발표했다.", mode="commit")
    assert {m["surface"] for m in resp["mentions"]} == {"한전KDN"}
    resp_all = resolve(snap, "한전KDN은 발표했다.", mode="commit",
                       options={"return_all_mentions": True})
    assert {m["surface"] for m in resp_all["mentions"]} == {"한전KDN", "한전"}


def test_determinism(snap):
    # REQ-GRPH-001: identical snapshot+input -> identical output
    a = resolve(snap, REFERENCE, mode="commit")
    b = resolve(snap, REFERENCE, mode="commit")
    assert a == b


def test_doclocal_boost_without_overwrite(snap):
    # §18.3/INV-009: 한국전력공사(이하 AP): global AP senses survive
    text = "한국전력공사(이하 AP)는 공고했다. AP 점검을 마쳤다."
    resp = resolve(snap, text, mode="commit")
    aps = [m for m in resp["mentions"] if m["surface"] == "AP"]
    late = [m for m in aps if m["span"]["codepoint"]["start"] > 20]
    assert late
    ids = {x.get("entity_id") for x in late[0]["prediction_set"]["members"]}
    assert "ORG_KEPCO" in ids  # doc-local candidate added
    assert {"NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS"} <= ids  # kept


# ---------------------------------------------------------------------------
# REQ-BUD-001 / REQ-API-005: what was cut, and whether it mattered
# ---------------------------------------------------------------------------


def _long_document(snapshot, chars: int) -> str:
    """Enough varied text to exhaust `max_fuzzy_windows` (96 core queries),
    with registered surfaces spread through it so mentions land on both sides
    of the cutoff.

    The filler clauses are distinct on purpose — repeating one would be
    answered out of the caches and never reach the budget.
    """
    surfaces = [b.surface for b in snapshot.glossary.alias_bindings]
    parts = []
    for i in range(chars // 18 + 2):
        parts.append(f"{i}번째 사안에 관하여 협의가 이어졌다고 한다.")
        parts.append(f"{surfaces[i % len(surfaces)]}은 이에 관해 밝혔다.")
    return " ".join(parts)[:chars]


def test_the_response_names_the_stage_it_omitted(snap):
    """REQ-BUD-001 asks for the omitted stage to be exposed. The reasons were
    collected into an internal trace and dropped, so a consumer could see
    that something had been cut and never what."""
    short = resolve(snap, "한전이 발표했다", mode="commit")
    assert short["limits"] == []
    assert short["degraded"] is False

    long_doc = resolve(snap, _long_document(snap, 4000), mode="commit")
    assert long_doc["degraded"] is True
    assert "fuzzy_window_budget" in long_doc["limits"]


def test_a_mention_says_when_a_channel_was_not_offered_to_it(snap):
    """The fuzzy budget stops the scan partway through the text, so mentions
    after that point are exact-only. That is a property of those mentions,
    not of the whole response."""
    resp = resolve(snap, _long_document(snap, 4000), mode="commit")
    bounded = [m for m in resp["mentions"] if m.get("channels_bounded")]
    unbounded = [m for m in resp["mentions"] if not m.get("channels_bounded")]
    assert bounded and unbounded, "expected the cutoff to fall inside the text"
    # and it falls in text order: everything after the cutoff is bounded
    last_free = max(m["span"]["codepoint"]["start"] for m in unbounded)
    first_bounded = min(m["span"]["codepoint"]["start"] for m in bounded)
    assert first_bounded > last_free


def test_a_capped_level_b_channel_does_not_veto_a_level_a_commit(snap):
    """§27.8/REQ-API-005 downgrades a mention whose candidate generation was
    incomplete. A missing fuzzy pass is not that when the answer rests on an
    exact match — Level A is complete by construction and fuzzy is additive
    recall. Lifting the budget changed 0 of 207 decisions in the wild, while
    downgrading everything past the cutoff cost 26 of 31 commits."""
    resp = resolve(snap, _long_document(snap, 4000), mode="commit")
    for m in resp["mentions"]:
        if m.get("channels_bounded") and m["link_decision"] == "RESOLVED":
            # allowed precisely because an exact candidate anchors it
            assert "exact" in m.get("generation_channels", []), m["surface"]
            assert not m.get("degraded")


def test_a_mention_resting_on_the_cut_channel_is_downgraded(snap):
    """The other half: no exact anchor plus a cut channel means candidate
    generation really was incomplete for that answer."""
    resp = resolve(snap, _long_document(snap, 4000), mode="commit")
    for m in resp["mentions"]:
        if m.get("degraded"):
            assert m["link_decision"] != "RESOLVED"

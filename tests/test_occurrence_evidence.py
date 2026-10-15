"""Hand-authored development checks, independent of the held-out fixture."""

from dataclasses import FrozenInstanceError, asdict

import pytest

from ktrf.occurrence_evidence import assess_assertion, select_evidence


CANDIDATES = [
    {"entity_id": "global:network", "canonical": "통신 장애 복구팀",
     "aliases": ["새길"],
     "short_definition": "사내 통신 장애를 복구하고 접속 문의를 처리하는 팀"},
    {"entity_id": "global:welfare", "canonical": "생활 복지 상담팀",
     "aliases": ["새길"],
     "short_definition": "임직원의 생활 지원과 복지 신청을 담당하는 팀"},
]


def span(text, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index("새길", start + 1)
    return start, start + 2


def select(text, mode="scoped", occurrence=0, **kwargs):
    return select_evidence(text, span(text, occurrence), CANDIDATES,
                           mode=mode, **kwargs)


def assess(text, occurrence=0):
    return assess_assertion(text, span(text, occurrence), CANDIDATES)


def test_paragraph_control_is_verbatim_and_ungated():
    text = "서문을 확인한다.\n\n새길에 보낸다는 안내는 취소했다.\n\n다른 기록이다."
    result = select(text, mode="paragraph")
    assert result.rendered_query == "[TARGET]새길[/TARGET]에 보낸다는 안내는 취소했다."
    assert result.gate_allowed
    assert result.assertion.allowed is False
    assert len(result.spans) == 1
    assert result.spans[0].reason == "TARGET_PARAGRAPH"


def test_scoped_veto_preserves_query_for_an_identical_ungated_ablation():
    text = "문구는 “새길은 통신 장애 복구팀이다.”이다."
    result = select(text)
    assert not result.gate_allowed
    assert result.abstain_reason == "QUOTED_ASSERTION"
    assert "[TARGET]새길[/TARGET]" in result.rendered_query
    assert text[slice(result.spans[0].start, result.spans[0].end)] == result.spans[0].quote


def test_remote_clue_and_source_offsets_are_preserved():
    text = ("새길로 이번 문의를 보낸다.\n\n"
            + "접수 번호와 날짜를 기록해 보관한다. " * 12
            + "\n\n사내 통신 장애를 복구하고 접속 문의를 처리한다.\n\n"
            "참석자가 작성 시간을 확인했다.")
    result = select(text)
    assert result.gate_allowed
    assert result.spans[-1].start - span(text)[1] > 150
    assert "사내 통신 장애를 복구" in result.rendered_query
    assert "접수 번호와 날짜" not in result.rendered_query
    assert [item.start for item in result.spans] == sorted(item.start for item in result.spans)
    for item in result.spans:
        assert text[item.start:item.end] == item.quote
    restored = result.rendered_query.replace("[TARGET]", "").replace("[/TARGET]", "")
    assert restored == "\n\n".join(item.quote for item in result.spans)


def test_support_is_candidate_symmetric_and_not_a_winner_filter():
    text = ("새길을 검토한다.\n\n사내 통신 장애를 복구하고 접속 문의를 처리한다.\n\n"
            "임직원의 생활 지원과 복지 신청을 담당한다.")
    first = select_evidence(text, span(text), CANDIDATES, mode="scoped")
    second = select_evidence(text, span(text), list(reversed(CANDIDATES)), mode="scoped")
    assert first == second
    assert "통신 장애" in first.rendered_query and "복지 신청" in first.rendered_query
    assert "chosen_entity_id" not in asdict(first)
    assert "probability" not in asdict(first)


def test_multitarget_scope_stays_with_the_designated_paragraph():
    text = ("첫 요청은 새길에 보낸다. 접속 문의를 처리한다.\n\n"
            "둘째 요청은 새길에 보낸다. 생활 복지 신청을 맡는다.")
    first, second = select(text), select(text, occurrence=1)
    assert "생활 복지" not in first.rendered_query
    assert "접속 문의" not in second.rendered_query
    assert len(first.spans) == len(second.spans) == 1
    assert first.rendered_query.count("[TARGET]") == second.rendered_query.count("[TARGET]") == 1


def test_explicit_heading_prevents_cross_section_support():
    text = ("# 첫째 요청\n\n새길로 보낸다.\n\n접수 시각을 기록한다.\n\n"
            "# 다른 업무\n\n사내 통신 장애를 복구하고 접속 문의를 처리한다.")
    result = select(text)
    assert "통신 장애" not in result.rendered_query
    assert result.gate_allowed


def test_quote_decoy_is_not_remote_support():
    text = ("새길로 요청을 보낸다.\n\n"
            "예전 기록에는 “새길은 생활 복지 상담팀이다.”라고 적혀 있다.\n\n"
            "사내 통신 장애를 복구하고 접속 문의를 처리한다.")
    result = select(text)
    assert result.gate_allowed
    assert "생활 복지 상담팀" not in result.rendered_query
    assert "통신 장애" in result.rendered_query


def test_negated_decoy_elsewhere_does_not_veto_affirmed_target():
    text = ("생활 복지 상담팀은 이번 담당이 아니다. 해당 팀에 전달하라는 안내는 취소했다.\n\n"
            "이번 요청은 새길에 보낸다. 통신 장애를 복구하고 접속 문의를 처리한다.")
    result = select(text)
    assert result.gate_allowed
    assert "생활 복지 상담팀" not in result.rendered_query


@pytest.mark.parametrize("text", [
    "새길에는 문제가 없다. 문의를 전달했다.",
    "새길의 장비 점검에 이상이 없다. 접속 문의를 처리한다.",
    "새길은 실제 담당 이름이며, 예시가 아니다.",
    "새길로 보낸다. 이 설명은 명칭 선언이며, 예시가 아니다.",
    "새길로 보낸다. 이 설명은 실제 예시가 아니다.",
    "새길로 보낸다. 이 이름은 상표가 아니다.",
    "새길로 보낸다. 이 문장은 틀린 예문이 아니다.",
    "새길에 보낸다. 담당자는 확인한 사실과 아직 정하지 못한 사항을 나눠 적는다.",
])
def test_benign_absence_and_negated_nonmention_are_not_global_vetoes(text):
    assert assess(text).allowed


@pytest.mark.parametrize("text", [
    "새길에 요청을 보내지 않는다.",
    "새길은 통신 장애 복구팀이 아니다.",
    "새길이라는 후보 이름을 적었지만 그 안은 폐기했다.",
    "새길로 연결하지 말아야 한다.",
])
def test_explicit_target_denial_abstains(text):
    result = assess(text)
    assert not result.allowed
    assert result.abstain_reason == "NEGATED_OR_REJECTED_TARGET"


@pytest.mark.parametrize("text", [
    "“새길은 통신 장애 복구팀이다.”",
    '시험지는 "새길은 통신 장애 복구팀이다"라는 문장이다.',
    "문구는 ‘새길에 요청을 보내라’이다.",
])
def test_whole_assertion_quotes_abstain(text):
    assert assess(text).abstain_reason == "QUOTED_ASSERTION"


@pytest.mark.parametrize("text", [
    '"새길에 요청을 보낸다.',
    "새길로 보낸다.”",
    "‘새길에 보낸다.”",
])
def test_uncertain_quotation_fails_closed(text):
    assert assess(text).abstain_reason == "UNCERTAIN_QUOTATION"


@pytest.mark.parametrize("text", [
    "수신처는 ‘새길’이다. 접속 문의를 처리한다.",
    '"새길"에 요청을 보낸다.',
    "새길은 “통신 장애 복구팀”이다.",
])
def test_quoted_alias_or_name_with_assertion_outside_is_allowed(text):
    assert assess(text).allowed


@pytest.mark.parametrize("tail", [
    "앞의 설명은 사실과 다르므로 철회한다.",
    "이 문장은 가짜 정의의 문자열 예시다.",
    "이번 이름은 조명 상품에 붙은 상표다.",
    "이 대상은 사전에 등록되지 않았다.",
])
def test_next_paragraph_scoped_retraction_or_nil_abstains(tail):
    text = "새길은 통신 장애 복구팀이다.\n\n" + tail
    result = select(text)
    assert not result.gate_allowed
    assert result.abstain_reason == "SCOPED_RETRACTION_OR_UNREGISTERED"
    assert result.assertion.support_spans[-1].quote == tail


def test_remote_explicit_ambiguity_abstains_for_a_unique_target():
    text = ("새길에 보낸다고 적었다.\n\n접수 번호는 서기가 관리한다.\n\n"
            "어느 쪽으로 보내야 할지 알 수 없다.")
    result = assess(text)
    assert not result.allowed
    assert result.abstain_reason == "EXPLICITLY_UNRESOLVED_TARGET"


def test_other_target_ambiguity_does_not_veto_first_target():
    text = ("첫 요청은 새길에 보낸다. 접속 문의를 맡는다.\n\n"
            "둘째 요청은 새길이라고만 적었다. 어느 쪽인지 알 수 없다.")
    assert assess(text).allowed
    assert not assess(text, occurrence=1).allowed


@pytest.mark.parametrize("text", [
    "독서등 새길의 사진을 보냈다.",
    "단편 영화 새길의 상영 포스터를 만들었다.",
])
def test_explicit_named_objects_are_not_organization_proposals(text):
    assert assess(text).abstain_reason == "EXPLICIT_UNREGISTERED_OBJECT"


def test_distinct_role_surface_is_blocked_separately_from_ranking():
    text = "새길팀장의 서명을 받는다."
    assert assess(text).abstain_reason == "DISTINCT_ROLE_SURFACE"
    assert select(text, mode="paragraph").gate_allowed


def test_budget_counts_markers_and_fails_without_clipping_passages():
    text = "새길에 보낸다."
    result = select(text, mode="paragraph")
    exact = len(result.rendered_query)
    assert select(text, mode="paragraph", max_chars=exact).gate_allowed
    short = select(text, mode="paragraph", max_chars=exact - 1)
    assert not short.gate_allowed and short.rendered_query == ""
    assert short.abstain_reason == "CONTEXT_BUDGET_EXCEEDED"
    assert short.spans[0].quote == text


def test_support_budget_overflow_does_not_drop_one_competitor():
    text = ("새길을 검토한다.\n\n사내 통신 장애를 복구하고 접속 문의를 처리한다.\n\n"
            "임직원의 생활 지원과 복지 신청을 담당한다.")
    result = select(text, max_chars=40)
    assert not result.gate_allowed
    assert result.abstain_reason == "CONTEXT_BUDGET_EXCEEDED"
    assert len(result.spans) == 3 and result.rendered_query == ""


@pytest.mark.parametrize("bad_span", [(-1, 2), (0, 99), (2, 2), (True, 2), (0,), None])
def test_invalid_spans_are_explicit_refusals(bad_span):
    result = select_evidence("새길에 보낸다.", bad_span, CANDIDATES, mode="scoped")
    assert not result.gate_allowed and not result.rendered_query
    assert result.abstain_reason == "INVALID_TARGET_SPAN"


def test_catalog_alias_detects_wrong_slice():
    result = assess_assertion("새길에 보낸다.", (1, 3), CANDIDATES)
    assert result.abstain_reason == "TARGET_SURFACE_NOT_REGISTERED"


@pytest.mark.parametrize("budget", [0, -1, True, 1.5])
def test_invalid_budget_fails_closed(budget):
    result = select("새길에 보낸다.", max_chars=budget)
    assert result.abstain_reason == "INVALID_CONTEXT_BUDGET"


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="mode"):
        select("새길에 보낸다.", mode="oracle")


def test_metadata_labels_cannot_change_selection():
    text = "새길로 보낸다.\n\n사내 통신 장애를 복구하고 접속 문의를 처리한다."
    marked = [dict(candidate, gold=index, stratum="arbitrary", expected_entity_id="other")
              for index, candidate in enumerate(CANDIDATES)]
    assert select_evidence(text, span(text), CANDIDATES, mode="scoped") == select_evidence(
        text, span(text), marked, mode="scoped")


def test_evidence_dataclasses_are_frozen_and_do_not_mutate_candidates():
    text = "새길로 보낸다."
    before = repr(CANDIDATES)
    result = select(text)
    with pytest.raises(FrozenInstanceError):
        result.gate_allowed = False
    with pytest.raises(FrozenInstanceError):
        result.spans[0].start = 1
    assert repr(CANDIDATES) == before
    assert result.status == result.assertion.status == "EXPERIMENTAL_HEURISTIC"

"""Independent affirmative and refusal examples for lexical context evidence."""

from dataclasses import asdict

import pytest

from ktrf.context_resolution import assess_context


ALIAS = "새길"
CANDIDATES = [
    {"entity_id": "global:network", "canonical": "접속 장애 복구지원팀",
     "definition": "사내 통신 장애를 복구하고 접속 문의를 처리하는 지원팀",
     "examples": ["새길에 문의했다."]},
    {"entity_id": "global:welfare", "canonical": "직원 생활 복지지원팀",
     "definition": "임직원 생활 지원과 복지 신청을 담당하는 상담팀",
     "examples": ["새길에 문의했다."]},
]
DEFINITION = CANDIDATES[0]["definition"]
CANONICAL = CANDIDATES[0]["canonical"]


def assess(text, policy=None, candidates=None, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(ALIAS, start + 1)
    return assess_context(text, (start, start + len(ALIAS)), ALIAS,
                          candidates if candidates is not None else CANDIDATES,
                          policy if policy is not None else {"enabled": True})


def test_disabled_by_default_and_evidence_has_no_probability():
    text = f"새길은 {CANONICAL}이다."
    result = assess_context(text, (0, 2), ALIAS, CANDIDATES)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "DISABLED"
    assert "probability" not in asdict(assess(text))
    assert assess(text).status == "EXPERIMENTAL_HEURISTIC"


@pytest.mark.parametrize("anchor", [CANONICAL, DEFINITION])
def test_explicit_identity_uses_full_registered_anchor(anchor):
    text = f"새길은 {anchor}이다."
    result = assess(text)
    assert result.chosen_entity_id == "global:network"
    assert anchor in result.support_quote
    assert text[slice(*result.anchor_span)] == anchor
    assert text[slice(*result.support_span)] == result.support_quote
    assert result.evidence_type.startswith("DIRECT_REGISTERED_DEFINITION")


def test_adjacent_definition_has_no_verified_antecedent():
    text = ("담당자는 새길을 먼저 확인한다. 변경 사항은 기록한다.\n\n"
            f"{DEFINITION}이다. 처리 현황을 확인한다.")
    result = assess(text)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "NO_EXPLICIT_REGISTERED_DEFINITION"


def test_normalized_spacing_preserves_original_quote_offsets():
    canonical = CANONICAL.replace(" ", "  ")
    text = f"새길은 “{canonical}”이다."
    result = assess(text)
    assert result.chosen_entity_id == "global:network"
    assert result.support_quote == text
    assert text[slice(*result.support_span)] == text
    assert text[slice(*result.anchor_span)] == canonical


@pytest.mark.parametrize("text", [
    f"새길은 {CANONICAL}이 아니다.",
    f"새길은 {CANONICAL}이다. 여기서는 담당 팀장의 개인 직함을 뜻한다.",
    f"새길은 {CANONICAL}이다. 이 이름은 미등록 상품명이다.",
    f"새길은 {CANONICAL}이다. 이 낱말은 비유로 썼다.",
    f"새길은 {CANONICAL}이다. 다른 조직과 무관한 입력 견본이다.",
    f"새길은 {CANONICAL}이다?",
    f"만약 새길은 {CANONICAL}이다.",
    f"새길은 {CANONICAL}이다. 이 문장은 추정이다.",
])
def test_negative_role_nil_and_nonmention_contexts_abstain(text):
    result = assess(text)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "UNSUPPORTED_OR_NEGATED_CONTEXT"


def test_competing_anchor_is_preserved_even_with_first_direct_definition():
    text = (f"새길은 {CANONICAL}이다. "
            f"참고 목록에는 {CANDIDATES[1]['canonical']}도 적혀 있다.")
    result = assess(text)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "COMPETING_REGISTERED_ANCHORS"


@pytest.mark.parametrize("text", [
    f"새길에 기록을 보냈다. 담당자는 {CANONICAL}에 근무한다.",
    f"새길에 기록을 보냈다. 안내문에 “{DEFINITION}”이라는 문장을 인용했다.",
    f"“새길은 {CANONICAL}이다.”",
    f"새길에 기록을 보냈다. 다른 시스템은 {CANONICAL}이다.",
    f"새길에 기록을 보냈다.\n\n다른 시스템은 {CANONICAL}이다.",
    f"새길에 기록을 보냈다.\n\n접수 일정을 확인했다.\n\n{DEFINITION}이다.",
])
def test_unrelated_or_quoted_registered_anchor_does_not_select(text):
    assert assess(text).chosen_entity_id is None
    assert assess(text, {"enabled": True,
                         "allow_document_scope": True}).chosen_entity_id is None


def test_far_reference_is_not_authorization_even_when_document_scope_requested():
    text = ("새길을 이번 운영에 사용한다.\n\n공통 접수 시각을 확인한다.\n\n"
            f"이번에 사용하는 것은 {DEFINITION}이다.")
    assert assess(text).chosen_entity_id is None
    result = assess(text, {"enabled": True, "allow_document_scope": True})
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "NO_EXPLICIT_REGISTERED_DEFINITION"


def test_second_alias_occurrence_prevents_distant_reference_reuse():
    text = ("새길을 이번 운영에 사용한다.\n\n새길에 접수 기록을 보낸다.\n\n"
            f"이번에 사용하는 것은 {DEFINITION}이다.")
    result = assess(text, {"enabled": True, "allow_document_scope": True})
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "REPEATED_TARGET_IN_CONTEXT"


def test_shared_definition_does_not_break_collision():
    candidates = [dict(record, definition=DEFINITION) for record in CANDIDATES]
    result = assess(f"새길은 {DEFINITION}이다.", candidates=candidates)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "COMPETING_REGISTERED_ANCHORS"


def test_short_anchors_examples_and_partial_definitions_are_insufficient():
    candidates = [dict(record, canonical="지원팀", definition="지원 팀",
                       examples=[f"새길은 {DEFINITION}이다."])
                  for record in CANDIDATES]
    assert assess(f"새길은 {DEFINITION}이다.",
                  candidates=candidates).chosen_entity_id is None
    assert assess("새길은 사내 통신 장애를 복구하는 팀이다.").chosen_entity_id is None


def test_context_budget_refuses_instead_of_truncating_into_a_choice():
    text = f"새길은 {CANONICAL}이다."
    result = assess(text, {"enabled": True, "max_context_chars": 10})
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "CONTEXT_BUDGET_EXCEEDED"


def test_invalid_raw_span_and_noncollision_are_explicit_refusals():
    result = assess_context("새길은 팀이다.", (1, 3), ALIAS, CANDIDATES,
                            {"enabled": True})
    assert result.abstention_reason == "INVALID_TARGET_SPAN"
    result = assess(f"새길은 {CANONICAL}이다.", candidates=CANDIDATES[:1])
    assert result.abstention_reason == "NO_EXACT_COLLISION"


@pytest.mark.parametrize("text", [
    f"새길에 요청을 보낸다. 다른 업무를 맡은 조직도 있다. 이는 {DEFINITION}이다.",
    f"새길에 요청을 보낸다. 이어서 별도의 조직을 소개한다.\n\n{DEFINITION}이다.",
    f"새길을 확인한다. 이는 {DEFINITION}이다.",
    f"새길을 확인한다. 이 용어는 {DEFINITION}이다.",
])
def test_pronouns_and_bare_definitions_never_authorize_a_target(text):
    assert assess(text).chosen_entity_id is None
    assert assess(text, {"enabled": True,
                         "allow_document_scope": True}).chosen_entity_id is None


@pytest.mark.parametrize("text", [
    f"문구는 다음과 같다: “새길은 {DEFINITION}이다.”",
    f'"새길은 {DEFINITION}이다."',
    f"새길은 “{DEFINITION}이다.”",
    f"새길은 「{DEFINITION}이다.」",
    f"‘새길은 {DEFINITION}이다.’",
    f'새길은 "{DEFINITION}이다.',
    f"새길은 {DEFINITION}이다.”",
])
def test_quoted_assertions_and_malformed_quoting_abstain(text):
    assert assess(text).chosen_entity_id is None


@pytest.mark.parametrize("left,right", [("“", "”"), ("'", "'"), ("「", "」")])
def test_quoted_names_are_allowed_when_the_assertion_is_outside_quotes(left, right):
    text = f"{left}새길{right}은 {left}{DEFINITION}{right}이다."
    result = assess(text)
    assert result.chosen_entity_id == "global:network"
    assert result.support_quote == text
    assert text[slice(*result.anchor_span)] == DEFINITION


@pytest.mark.parametrize("text", [
    f"틀린 주장: 새길은 {DEFINITION}이다.",
    f"새길은 {DEFINITION}이다. 그 설명은 틀렸다.",
    f"새길은 {DEFINITION}이다. 이 정의는 허위다.",
    f"새길은 {DEFINITION}이다. 그 정의는 오류다.",
    f"새길은 {DEFINITION}이다. 정의를 정정한다.",
    f"새길은 {DEFINITION}이다. 이 진술은 사실과 다르다.",
])
def test_false_claims_and_retrospective_denials_veto_the_bounded_scope(text):
    result = assess(text)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "UNSUPPORTED_OR_NEGATED_CONTEXT"


def test_definition_containing_error_is_a_valid_affirmative_statement():
    definition = "월별 청구 오류를 검토하고 지출 내역을 확인하는 조직"
    candidates = [dict(record, definition=definition if index == 0 else record["definition"])
                  for index, record in enumerate(CANDIDATES)]
    assert assess(f"새길은 {definition}이다.", candidates=candidates).chosen_entity_id == "global:network"


def test_direct_parenthetical_canonical_name_and_competing_anchor():
    text = f"새길({CANONICAL})."
    result = assess(text)
    assert result.chosen_entity_id == "global:network"
    assert result.evidence_type == "DIRECT_REGISTERED_NAME:canonical"
    assert text[slice(*result.anchor_span)] == CANONICAL
    competing = f"새길({CANONICAL})과 {CANDIDATES[1]['canonical']}이 회의에 참석했다."
    assert assess(competing).chosen_entity_id is None


def test_embedded_identity_statement_requires_a_target_subject_at_sentence_start():
    assert assess(f"문서에서는 새길은 {DEFINITION}이다.").chosen_entity_id is None


@pytest.mark.parametrize("suffix", [")", ").", ")이다.", ")입니다."])
def test_parenthetical_identity_requires_a_complete_name_or_copular_annotation(suffix):
    text = f"새길({CANONICAL}{suffix}"
    assert assess(text).chosen_entity_id == "global:network"


@pytest.mark.parametrize("suffix", [
    ") 대신 외부 물품을 가리킨다.",
    ")와 다른 조직을 가리킨다.",
    ")과 비교하려는 표현이다.",
    ")를 위한 입력이다.",
    ")에 접수 기록을 보낸다.",
])
def test_parenthetical_name_with_a_trailing_clause_is_not_an_identity_assertion(suffix):
    text = f"새길({CANONICAL}{suffix}"
    result = assess(text)
    assert result.chosen_entity_id is None
    assert result.abstention_reason == "NO_EXPLICIT_REGISTERED_DEFINITION"

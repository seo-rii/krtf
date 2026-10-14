"""Matched control facts, frozen model inputs and guarded outputs stay distinct."""
from copy import deepcopy
import json

import pytest

from eval import definition_control as suite
from ktrf.context import ContextPolicy, prepare_llm_context
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.snapshot import RuntimePolicy, compile_snapshot


def family_fixture():
    terms = [
        {"key": "e_71ad", "canonical": "청구조정센터", "surfaces": ["조센"],
         "short_definition": "청구 차액의 검증과 조정을 담당하는 센터"},
        {"key": "e_92bc", "canonical": "조달지원센터", "surfaces": ["조센"],
         "short_definition": "물품 조달과 납기 조정을 담당하는 센터"},
    ]
    knowledge = ("업무 참고 사전\n\n청구조정센터의 별칭은 조센이다. ID: global:e_71ad. "
        "정의: 청구 차액의 검증과 조정을 담당하는 센터\n\n"
        "요청 기록은 담당자가 보관한다.\n\n조달지원센터의 별칭은 조센이다. ID: global:e_92bc. "
        "정의: 물품 조달과 납기 조정을 담당하는 센터\n\n센터와 센터장은 구별한다.")
    source = ("검토 기록\n\n조센에 검토를 요청했다.\n\n오전 회의 기록이다.\n\n"
        "내부 기록 분류는 별도다.\n\n대상 업무는 청구 차액 검증이다.\n\n검토를 마쳤다.")
    return {"family_id": "definition-test", "domain": "test", "annotation_origin": "AI_AUTHORED_SYNTHETIC",
        "human_verified": False, "terms": terms, "knowledge_document": {"document_id": "kb-test", "text": knowledge},
        "documents": [
            {"document_id": "test-link", "text": source, "target_surface": "조센", "stratum": "distant_context",
             "gold": {"label": "LINK", "entity_ref": "global:e_71ad"},
             "expected_answer": terms[0]["short_definition"], "rationale": "청구 문맥이 청구조정센터를 뜻한다.",
             "decisive_evidence": [{"document": "source", "quote": "대상 업무는 청구 차액 검증이다."}]},
            {"document_id": "test-negative", "text": "회의 자료\n\n미등록별명을 확인했다.\n\n아직 정의가 없다.",
             "target_surface": "미등록별명", "stratum": "nil", "gold": {"label": "NIL", "entity_ref": None},
             "expected_answer": None, "rationale": "등록된 항목이 없다.",
             "decisive_evidence": [{"document": "source", "quote": "아직 정의가 없다."}]},
        ]}


def write_family(path, family=None):
    path.write_text(json.dumps(family or family_fixture(), ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def envelope(tmp_path_factory):
    return suite.build_envelope(write_family(tmp_path_factory.mktemp("definition-control") / "families.jsonl"))


def choose(envelope, condition, task="document_qa", document="test-link"):
    return next(row for row in envelope["requests"] if row["condition"] == condition
        and row["task"] == task and row["document_id"] == document)


def output(row, response, **fields):
    return {"case_id": row["case_id"], "condition": row["condition"], "response": response, **fields}


def selection(row, entity_id):
    return {"selections": [{"surface": row["target_surface"], "entity_id": entity_id}]}


def test_complete_matrix_keeps_original_source_gold_and_inventory(envelope):
    rows = envelope["requests"]
    assert len(rows) == 2 * 6 * 2
    assert len({(row["case_id"], row["condition"]) for row in rows}) == len(rows)
    assert envelope["provenance"]["human_verified"] is False
    for document in ("test-link", "test-negative"):
        group = [row for row in rows if row["document_id"] == document]
        assert {row["condition"] for row in group} == set(suite.CONDITIONS)
        for field in ("source_text", "knowledge_text", "gold", "expected_answer", "definition_inventory"):
            assert len({json.dumps(row[field], sort_keys=True) for row in group}) == 1
        assert all(row["source_text"] in row["user"] for row in group)
        assert all(row["source_text"][slice(*row["target_span"])] == row["target_surface"] for row in group)


def test_prose_and_json_cards_preserve_every_catalog_fact_and_exact_definition(envelope):
    prose, cards = [choose(envelope, condition) for condition in ("prose_all", "cards_all")]
    assert prose["candidate_cards"] == cards["candidate_cards"] == prose["glossary_catalog"]
    assert prose["system"] == cards["system"] == suite.BASE_SYSTEM
    for card in cards["candidate_cards"]:
        assert "<exact_definition>" + card["definition"] + "</exact_definition>" in prose["prompt_fragment"]
        assert json.dumps(card, ensure_ascii=False, sort_keys=True) in cards["prompt_fragment"]
        facts = {key: value for key, value in card.items() if key != "definition"}
        assert json.dumps(facts, ensure_ascii=False, sort_keys=True) in prose["prompt_fragment"]
    assert prose["user"].split("원문 전체:", 1)[1] == cards["user"].split("원문 전체:", 1)[1]
    assert "부연 설명을 덧붙이지 않는다" in cards["user"]


def test_gold_labels_do_not_affect_any_retrieval_pack_or_model_input(tmp_path, envelope):
    family = family_fixture()
    family["documents"][0].update(gold={"label": "NIL", "entity_ref": None}, expected_answer=None)
    changed = suite.build_envelope(write_family(tmp_path / "changed.jsonl", family))
    for before, after in zip(envelope["requests"], changed["requests"]):
        for field in ("system", "user", "pack", "candidate_cards", "knowledge_retrieval", "runtime_policy"):
            assert before[field] == after[field]


def test_retrieved_cards_require_both_complete_id_and_definition(envelope):
    row = choose(envelope, "cards_retrieved")
    retrieved = suite.retrieve_paragraphs(row["knowledge_text"], row["knowledge_document_id"],
        row["target_surface"], visible_source=row["source_text"])
    assert row["knowledge_retrieval"] == retrieved
    expected = [card for card in row["glossary_catalog"]
        if card["entity_id"] in retrieved["text"] and card["definition"] in retrieved["text"]]
    assert row["candidate_cards"] == expected
    assert row["candidate_entity_ids"] == sorted(card["entity_id"] for card in expected)


@pytest.mark.parametrize("condition", ["ktrf_execution_cards", "ktrf_contextual_execution_cards"])
@pytest.mark.parametrize("task,profile", [("document_qa", "qa_grounding"), ("structured_routing", "automation")])
def test_production_arms_use_actual_task_specific_context_profiles(envelope, condition, task, profile):
    row = choose(envelope, condition, task)
    family = family_fixture()
    glossary = load_glossary(compile_simple_terms({"terms": family["terms"]}, scope="global", glossary_id=family["family_id"]))
    snapshot = compile_snapshot(glossary, run_conformance=False, tenant_id=family["family_id"],
        policy=RuntimePolicy(contextual_exact_resolution=condition == "ktrf_contextual_execution_cards"))
    prepared = prepare_llm_context(snapshot, row["source_text"], query=row["target_surface"],
        context_policy=ContextPolicy(profile=profile, **suite.CONTEXT_BUDGET))
    assert row["pack"] == prepared.context_pack
    assert row["pack"]["profile"] == row["context_policy"]["profile"] == profile
    assert row["prompt_fragment"] == prepared.prompt_fragment
    assert row["policy_fragment"] == prepared.policy_fragment
    assert row["injected"] == prepared.should_inject
    assert row["runtime_policy"] == {"contextual_exact_resolution": condition == "ktrf_contextual_execution_cards"}


def test_qa_candidate_cards_are_neutral_proposals_without_execution_authority(envelope):
    row = choose(envelope, "ktrf_qa_cards", "structured_routing")
    assert row["pack"]["profile"] == "qa_grounding"
    assert row["system"] == suite.BASE_SYSTEM
    assert row["policy_fragment"] == ""
    assert row["execution_validation"] == "membership_proposal"
    assert row["prompt_fragment"] == suite._render_cards(row["candidate_cards"])


def test_empty_actual_ktrf_context_does_not_leak_complete_grading_inventory(envelope):
    for condition in suite.CONDITIONS[3:]:
        row = choose(envelope, condition, document="test-negative")
        assert row["injected"] is False and row["candidate_cards"] == []
        assert row["system"] == suite.BASE_SYSTEM
        for card in row["definition_inventory"]:
            assert card["entity_id"] not in row["system"] + row["user"]
            assert card["definition"] not in row["system"] + row["user"]


def test_exact_qa_and_bounded_normalization_have_separate_scores(envelope):
    row = choose(envelope, "cards_all")
    result = suite.grade_outputs([row], [output(row, {"answer": row["expected_answer"] + "이다."})])
    case = result["cases"][0]
    assert case["exact_match"] is case["correct"] is False
    assert case["semantic_match"] is True and case["semantic_status"] == "MATCH"
    assert result["overall"]["exact_match"] == 0 and result["overall"]["semantic_match"] == 1
    assert case["operational_correct"] is False


@pytest.mark.parametrize("answer_kind,status", [("wrong_definition", "MISMATCH"), ("extra_claim", "UNASSESSED"),
    ("paraphrase", "UNASSESSED"), ("negative", "UNASSESSED"), ("string_null", "UNASSESSED")])
def test_normalized_qa_never_credits_other_definitions_extra_claims_or_paraphrases(envelope, answer_kind, status):
    row = choose(envelope, "cards_all")
    answer = {"wrong_definition": row["definition_inventory"][1]["definition"] + "입니다.",
        "extra_claim": row["expected_answer"] + "이며 전체 결재 권한도 가진다.",
        "paraphrase": "고객 청구액을 확인하는 조직", "negative": row["expected_answer"] + "가 아니다.",
        "string_null": "null"}[answer_kind]
    case = suite.grade_outputs([row], [output(row, {"answer": answer})])["cases"][0]
    assert case["semantic_status"] == status
    assert case["semantic_match"] is case["exact_match"] is False


def test_missing_malformed_null_and_true_abstention_remain_distinct(envelope):
    positive = choose(envelope, "prose_all")
    missing = choose(envelope, "cards_all")
    malformed = choose(envelope, "cards_retrieved", document="test-negative")
    negative = choose(envelope, "prose_all", document="test-negative")
    result = suite.grade_outputs([positive, missing, malformed, negative], [
        output(positive, {"answer": None}), output(malformed, {}), output(negative, {"answer": None})])
    counts = result["overall"]
    assert counts["missing"] == counts["malformed"] == counts["positive_null"] == counts["safe_null"] == 1
    assert counts["exact_match"] == counts["semantic_match"] == 1
    assert result["cases"][2]["semantic_status"] == "UNASSESSED"


def test_transport_malformed_null_never_gains_safe_abstention_credit(envelope):
    row = choose(envelope, "cards_all", document="test-negative")
    case = suite.grade_outputs([row], [output(row, {"answer": None}, status="MALFORMED")])["cases"][0]
    assert case["malformed"] is True and case["semantic_status"] == "UNASSESSED"
    assert case["exact_match"] is case["semantic_match"] is case["safe_null"] is False


def test_correct_proposal_cannot_bypass_production_execution_guard(envelope):
    neutral = choose(envelope, "cards_all", "structured_routing")
    production = choose(envelope, "ktrf_execution_cards", "structured_routing")
    result = suite.grade_outputs([neutral, production], [output(row, selection(row, row["expected_entity_id"]))
        for row in (neutral, production)])
    a, b = result["cases"]
    assert a["semantic_match"] is b["semantic_match"] is True
    assert a["operational_correct"] is True
    assert production["resolver_authorized_entity_id"] is None
    assert b["operational_correct"] is False and b["denied_nonnull"] is True


def test_mixed_raw_response_is_passed_whole_to_execution_guard(envelope, monkeypatch):
    row = choose(envelope, "ktrf_execution_cards", "structured_routing")
    response = {**selection(row, row["expected_entity_id"]), "answer": row["expected_answer"]}
    seen = []
    original = suite.validate_llm_grounding

    def observe(raw, pack, *, purpose):
        seen.append(raw)
        return original(raw, pack, purpose=purpose)

    monkeypatch.setattr(suite, "validate_llm_grounding", observe)
    case = suite.grade_outputs([row], [output(row, response)])["cases"][0]
    assert seen == [response] and seen[0] is response
    assert case["malformed"] is True
    assert case["semantic_match"] is case["operational_correct"] is case["operational_valid"] is False


@pytest.mark.parametrize("change", ["prompt", "catalog", "gold", "retrieval", "policy", "span"])
def test_frozen_request_tampering_is_rejected(envelope, change):
    rows = deepcopy([choose(envelope, "cards_all"), choose(envelope, "cards_retrieved")])
    if change == "prompt":
        rows[0]["user"] += "追加の回答指示"
    elif change == "catalog":
        rows[0]["glossary_catalog"][0]["definition"] = "changed"
    elif change == "gold":
        rows[0].update(gold={"label": "NIL", "entity_ref": None}, expected_entity_id=None, expected_answer=None)
    elif change == "retrieval":
        rows[1]["knowledge_retrieval"]["text"] += "hidden evidence"
    elif change == "policy":
        rows[0]["runtime_policy"]["contextual_exact_resolution"] = True
    else:
        rows[0]["target_span"][0] += 1
    with pytest.raises(ValueError):
        suite.validate_requests(rows)


def test_loader_preserves_frozen_envelope_and_checks_protocol(tmp_path, envelope):
    path = tmp_path / "requests.json"
    path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    rows, protocol, provenance = suite.load_request_file(path)
    assert (rows, protocol, provenance) == (envelope["requests"], envelope["protocol"], envelope["provenance"])
    with pytest.raises(ValueError, match="frozen"):
        suite.load_request_file(path, track="document_context")
    changed = deepcopy(envelope)
    changed["protocol"]["human_verified"] = True
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen"):
        suite.load_request_file(path)


def test_outputs_keep_condition_identity_and_reject_unknown_or_duplicate_records(envelope):
    a, b = [choose(envelope, condition) for condition in ("prose_all", "cards_all")]
    result = suite.grade_outputs([a, b], [output(a, {"answer": None}), output(b, {"answer": b["expected_answer"]})])
    assert result["by_condition"]["prose_all"]["overall"]["semantic_match"] == 0
    assert result["by_condition"]["cards_all"]["overall"]["semantic_match"] == 1
    with pytest.raises(ValueError, match="duplicate"):
        suite.grade_outputs([a, b], [output(a, {"answer": None})] * 2)
    with pytest.raises(ValueError, match="unknown"):
        suite.grade_outputs([a], [output(b, {"answer": None})])

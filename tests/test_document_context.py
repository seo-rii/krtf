"""The factorial changes visible evidence without changing world gold or questions."""
from copy import deepcopy
import json

import pytest

from eval import document_context as suite
from ktrf.context import ContextPolicy, prepare_llm_context
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.snapshot import compile_snapshot


def family_fixture():
    terms = [
        {"key": "e_71ad", "canonical": "청구조정센터", "surfaces": ["조센"],
         "short_definition": "청구 차액의 검증과 조정을 담당하는 센터"},
        {"key": "e_92bc", "canonical": "조달지원센터", "surfaces": ["조센"],
         "short_definition": "물품 조달과 납기 조정을 담당하는 센터"},
    ]
    kb = ("업무 참고 사전\n\n청구조정센터의 별칭은 조센이다. ID: global:e_71ad. "
          "정의: 청구 차액의 검증과 조정을 담당하는 센터\n\n"
          "모든 요청은 담당자가 기록한다.\n\n조달지원센터의 별칭은 조센이다. ID: global:e_92bc. "
          "정의: 물품 조달과 납기 조정을 담당하는 센터\n\n역할과 센터는 서로 다른 대상이다.")
    text = ("기록 제목\n\n조센에 검토를 요청했다.\n\n오전 회의 기록이다.\n\n"
            "내부 기록 분류는 별도다.\n\n대상 업무는 청구 차액 검증이다.\n\n검토를 마쳤다.")
    return {"family_id": "test_family", "domain": "test", "annotation_origin": "AI_AUTHORED_SYNTHETIC",
        "human_verified": False, "terms": terms, "knowledge_document": {"document_id": "kb-test", "text": kb},
        "documents": [
            {"document_id": "test-link", "text": text, "target_surface": "조센", "stratum": "remote_context",
             "gold": {"label": "LINK", "entity_ref": "global:e_71ad"},
             "expected_answer": terms[0]["short_definition"], "rationale": "청구 문맥이 첫 센터를 뜻한다.",
             "decisive_evidence": [{"document": "source", "quote": "대상 업무는 청구 차액 검증이다."}]},
            {"document_id": "test-negative", "text": "회의 자료\n\n미등록별명을 확인했다.\n\n아직 정의가 없다.",
             "target_surface": "미등록별명", "stratum": "nil", "gold": {"label": "NIL", "entity_ref": None},
             "expected_answer": None, "rationale": "등록된 항목이 없다.",
             "decisive_evidence": [{"document": "source", "quote": "아직 정의가 없다."}]},
        ]}


@pytest.fixture(scope="module")
def envelope(tmp_path_factory):
    path = tmp_path_factory.mktemp("document-context") / "families.jsonl"
    path.write_text(json.dumps(family_fixture(), ensure_ascii=False) + "\n")
    return suite.build_document_context_envelope(path)


def choose(envelope, condition, task="document_qa", document="test-link"):
    return next(row for row in envelope["requests"] if row["condition"] == condition and row["task"] == task and row["document_id"] == document)


def output(row, response, **fields):
    return {"case_id": row["case_id"], "condition": row["condition"], "response": response, **fields}


def selection(row, entity_id):
    return {"selections": [{"surface": row["target_surface"], "entity_id": entity_id}]}


def test_factorial_is_complete_and_world_gold_never_changes(envelope):
    rows = envelope["requests"]
    assert len(rows) == 2 * 4 * 3 * 2
    assert len({(row["case_id"], row["condition"]) for row in rows}) == len(rows)
    for document in ("test-link", "test-negative"):
        group = [row for row in rows if row["document_id"] == document]
        assert {row["condition"] for row in group} == set(suite.CONDITIONS)
        assert len({json.dumps(row["gold"], sort_keys=True) for row in group}) == 1
        assert len({row["expected_answer"] for row in group}) == 1
    assert envelope["provenance"]["human_verified"] is False


def test_no_context_prompt_reveals_only_question_and_target(envelope):
    row = choose(envelope, "none__none")
    assert row["user"] == suite._question(row["target_surface"], row["task"])
    assert row["system"] == suite.BASE_SYSTEM
    assert row["visible_source"] == row["visible_knowledge"] == ""
    for secret in (row["expected_answer"], row["expected_entity_id"], "대상 업무는 청구 차액 검증이다."):
        assert secret not in row["system"] + row["user"]
    assert row["source_gold_visible"] is False
    assert row["definition_visible"] is row["entity_id_visible"] is False
    assert row["visible_entity_ids"] == []


def test_full_original_and_knowledge_documents_are_unabridged(envelope):
    row = choose(envelope, "full__full")
    assert row["visible_source"] == row["source_text"]
    assert row["visible_knowledge"] == row["knowledge_text"]
    assert row["source_text"] in row["user"] and row["knowledge_text"] in row["user"]
    for prefix in ("source", "knowledge"):
        for chunk in row[prefix + "_chunks"]:
            assert chunk["text"] == row[prefix + "_text"][chunk["start"]:chunk["end"]]
    assert row["source_gold_visible"] is row["definition_visible"] is row["entity_id_visible"] is True


def test_retrieval_is_deterministic_not_gold_aware_and_can_miss_distant_evidence(envelope):
    row = choose(envelope, "retrieved__retrieved")
    source = suite.retrieve_paragraphs(row["source_text"], row["document_id"], row["target_surface"])
    assert source == suite.retrieve_paragraphs(row["source_text"], row["document_id"], row["target_surface"])
    assert source["selected_paragraph"] == 1
    assert [chunk["paragraph_index"] for chunk in source["chunks"]] == [0, 1, 2]
    assert row["source_gold_visible"] is False
    assert "대상 업무는 청구 차액 검증이다." not in row["visible_source"]
    kb = suite.retrieve_paragraphs(row["knowledge_text"], row["knowledge_document_id"], row["target_surface"], visible_source=source["text"])
    assert row["visible_knowledge"] == kb["text"]
    assert row["knowledge_retrieval"]["query_sha256"] == suite._sha(row["target_surface"] + "\n" + row["visible_source"])


def test_gold_changes_do_not_change_retrieval_or_prompts(tmp_path, envelope):
    family = family_fixture()
    family["documents"][0].update(gold={"label": "NIL", "entity_ref": None}, expected_answer=None)
    path = tmp_path / "family.jsonl"
    path.write_text(json.dumps(family, ensure_ascii=False) + "\n")
    changed = suite.build_document_context_envelope(path)
    for a, b in zip(envelope["requests"], changed["requests"]):
        assert (a["system"], a["user"], a["pack"]) == (b["system"], b["user"], b["pack"])
        assert a["source_chunks"] == b["source_chunks"] and a["knowledge_chunks"] == b["knowledge_chunks"]


def test_neutral_control_system_and_question_are_identical(envelope):
    for task in suite.TASKS:
        rows = [row for row in envelope["requests"] if row["task"] == task and row["document_id"] == "test-link"]
        controls = [row for row in rows if row["knowledge_mode"] != "ktrf"]
        assert {row["system"] for row in controls} == {suite.BASE_SYSTEM}
        for row in rows:
            assert row["user"].endswith(suite._question(row["target_surface"], task))


def test_ktrf_receives_only_visible_original_or_target(envelope):
    family = family_fixture()
    compiled = compile_simple_terms({"terms": family["terms"]}, scope="global", glossary_id=family["family_id"])
    snapshot = compile_snapshot(load_glossary(compiled), run_conformance=False, tenant_id=family["family_id"])
    for source in suite.SOURCE_MODES:
        for task in suite.TASKS:
            row = choose(envelope, "ktrf__" + source, task)
            resolver_input = row["visible_source"] or row["target_surface"]
            prepared = prepare_llm_context(snapshot, resolver_input, query=row["target_surface"], context_policy=ContextPolicy(**row["context_policy"]))
            assert row["pack"] == prepared.context_pack
            assert row["prompt_fragment"] == prepared.prompt_fragment
            assert row["injected"] == prepared.should_inject
            assert row["resolver_input"] == resolver_input
    nil = choose(envelope, "ktrf__none", document="test-negative")
    assert nil["injected"] is False
    assert nil["system"] == suite.BASE_SYSTEM
    assert nil["prompt_fragment"] not in nil["user"]


def test_primary_semantic_and_execution_guard_metrics_are_separate(envelope):
    baseline = choose(envelope, "full__full", "structured_routing")
    ktrf = choose(envelope, "ktrf__full", "structured_routing")
    result = suite.grade_document_context_outputs([baseline, ktrf],
        [output(row, selection(row, row["expected_entity_id"])) for row in (baseline, ktrf)])
    assert [case["semantic_match"] for case in result["cases"]] == [True, True]
    assert result["cases"][0]["operational_correct"] is True
    assert result["cases"][1]["operational_correct"] is False
    assert result["cases"][1]["denied_nonnull"] is True
    assert result["cases"][1]["authorized_id"] is None


def test_complete_raw_execution_response_reaches_guard(envelope, monkeypatch):
    row = choose(envelope, "ktrf__full", "structured_routing")
    mixed = {**selection(row, row["expected_entity_id"]), "answer": row["expected_answer"]}
    seen = []
    original = suite.validate_llm_grounding
    def observe(response, pack, *, purpose):
        seen.append(response)
        return original(response, pack, purpose=purpose)
    monkeypatch.setattr(suite, "validate_llm_grounding", observe)
    result = suite.grade_document_context_outputs([row], [output(row, mixed)])
    assert seen[0] is mixed
    assert result["cases"][0]["malformed"] is True
    assert result["cases"][0]["semantic_match"] is False
    assert result["cases"][0]["operational_valid"] is False


def test_cross_condition_outputs_never_overwrite_each_other(envelope):
    a, b = [choose(envelope, condition) for condition in ("none__none", "full__full")]
    result = suite.grade_document_context_outputs([a, b], [output(a, {"answer": None}), output(b, {"answer": b["expected_answer"]})])
    assert result["by_condition"]["none__none"]["by_task"]["document_qa"]["correct"] == 0
    assert result["by_condition"]["full__full"]["by_task"]["document_qa"]["correct"] == 1
    with pytest.raises(ValueError, match="duplicate"):
        suite.grade_document_context_outputs([a, b], [output(a, {"answer": None})] * 2)


def test_missing_malformed_null_and_correct_are_distinct(envelope):
    rows = [choose(envelope, condition) for condition in ("none__none", "full__full", "retrieved__none")]
    negative = choose(envelope, "full__full", document="test-negative")
    result = suite.grade_document_context_outputs([*rows, negative], [output(rows[0], {"answer": None}), output(rows[1], {}), output(negative, {"answer": None})])
    assert result["overall"]["missing"] == result["overall"]["malformed"] == result["overall"]["positive_null"] == result["overall"]["safe_null"] == 1
    assert result["overall"]["correct"] == 1


def test_no_knowledge_execution_cannot_accept_even_guessed_correct_id(envelope):
    row = choose(envelope, "none__none", "structured_routing")
    result = suite.grade_document_context_outputs([row], [output(row, selection(row, row["expected_entity_id"]))])
    case = result["cases"][0]
    assert case["semantic_match"] is True and case["operational_valid"] is False
    assert case["denied_nonnull"] is True


def test_visible_id_requires_complete_identifier_not_prefix(envelope):
    row = deepcopy(choose(envelope, "none__none", "structured_routing"))
    row["glossary_entity_ids"] = ["global:e_7", "global:e_71ad"]
    row["visible_knowledge"] = "ID: global:e_71ad."
    assert suite._evidence(row)["visible_entity_ids"] == ["global:e_71ad"]
    row["visible_knowledge"] = "등록 ID는 global:e_71ad이다."
    assert suite._evidence(row)["visible_entity_ids"] == ["global:e_71ad"]


@pytest.mark.parametrize("change", ["prompt", "visible_source", "chunk", "gold"])
def test_tampering_or_cross_condition_gold_drift_is_rejected(envelope, change):
    rows = deepcopy([choose(envelope, "none__none"), choose(envelope, "full__full")])
    if change == "prompt":
        rows[0]["user"] += rows[0]["source_text"]
    elif change == "visible_source":
        rows[0]["visible_source"] = rows[0]["source_text"]
    elif change == "chunk":
        rows[1]["source_chunks"][0]["start"] = 1
    else:
        rows[0]["gold"] = {"label": "NIL", "entity_ref": None}
        rows[0]["expected_entity_id"] = rows[0]["expected_answer"] = None
    with pytest.raises(ValueError):
        suite.validate_document_context_requests(rows)


def test_frozen_policy_regrading_and_envelope_loading(envelope, tmp_path, monkeypatch):
    path = tmp_path / "requests.json"
    path.write_text(json.dumps(envelope, ensure_ascii=False))
    rows, protocol, provenance = suite.load_document_context_request_file(path)
    assert rows == envelope["requests"] and protocol == envelope["protocol"] and provenance == envelope["provenance"]
    row = choose(envelope, "ktrf__full")
    monkeypatch.setattr(suite, "QA_CONTEXT_POLICY", "later policy revision")
    with pytest.raises(ValueError, match="policy"):
        suite.validate_document_context_requests([row])
    assert suite.grade_document_context_outputs([row], [output(row, {"answer": row["expected_answer"]})])["cases"][0]["correct"] is True


@pytest.mark.parametrize("protocol", [None, {}, {**suite.PROTOCOL, "conditions": ["full__full"]}])
def test_invalid_envelope_protocol_is_rejected(envelope, tmp_path, protocol):
    broken = {**envelope, "protocol": protocol}
    path = tmp_path / "requests.json"
    path.write_text(json.dumps(broken, ensure_ascii=False))
    with pytest.raises(ValueError, match="envelope"):
        suite.load_document_context_request_file(path)

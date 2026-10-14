"""Definition-only normalization never grants containment or malformed-null credit."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import semantic_qa as semantic
from eval.document_context import build_document_context_envelope, grade_document_context_outputs
from eval.report_document_context import ARTIFACTS, _json_bytes

DEFINITIONS = {
    "global:billing": "과금 내역을 검토하고 청구 오류를 정정하는 내부 콘솔",
    "global:access": "외부 방문자의 출입 권한을 방문 전에 승인하는 절차",
}
EXPECTED = DEFINITIONS["global:billing"]


@pytest.mark.parametrize("suffix", ["", ".", "이다", "이다.", "다", "다.", "입니다", "입니다.", " 입니다."])
def test_exact_definition_with_only_copula_and_period_is_credited(suffix):
    answer = EXPECTED + suffix
    result = semantic.assess_qa_answer(answer, EXPECTED, DEFINITIONS, "global:billing")
    assert result["status"] == "MATCH"
    assert result["reason"] == ("exact_definition" if not suffix else "whitespace_copula_or_period_only")
    assert result["matched_entity_ids"] == ["global:billing"]


def test_whitespace_normalization_preserves_words():
    answer = "  " + EXPECTED.replace(" ", "\n\t ") + "입니다.  "
    assert semantic.assess_qa_answer(answer, EXPECTED, DEFINITIONS)["status"] == "MATCH"
    assert semantic.assess_qa_answer(EXPECTED.replace(" ", ""), EXPECTED, DEFINITIONS)["status"] == "UNASSESSED"


@pytest.mark.parametrize("answer", [
    EXPECTED + "이며 모든 변경을 자동 승인한다.",
    "이것은 " + EXPECTED + "이다.",
    EXPECTED + "이다. " + DEFINITIONS["global:access"] + "이기도 하다.",
    EXPECTED + "이 아니다.", EXPECTED + "이 아닙니다.",
    EXPECTED + "이지만 청구 오류를 정정하지 않는다.",
    "과금 화면", EXPECTED + "..", EXPECTED + "이다이다.",
])
def test_paraphrases_additional_claims_negation_and_multiple_definitions_need_review(answer):
    result = semantic.assess_qa_answer(answer, EXPECTED, DEFINITIONS, "global:billing")
    assert result["status"] == "UNASSESSED"


def test_other_registered_definition_is_a_mismatch_even_with_copula():
    result = semantic.assess_qa_answer(DEFINITIONS["global:access"] + "입니다.", EXPECTED, DEFINITIONS)
    assert result["status"] == "MISMATCH"
    assert result["reason"] == "different_registered_definition"
    assert result["matched_entity_ids"] == ["global:access"]


def test_actual_null_is_distinct_from_null_string_and_positive_abstention():
    assert semantic.assess_qa_answer(None, None, DEFINITIONS)["status"] == "NULL_CORRECT"
    assert semantic.assess_qa_answer(None, EXPECTED, DEFINITIONS)["status"] == "MISMATCH"
    for nonnull in ("null", "", "unknown", EXPECTED):
        assert semantic.assess_qa_answer(nonnull, None, DEFINITIONS)["status"] == "MISMATCH"
    assert semantic.assess_qa_answer({"answer": None}, None, DEFINITIONS)["status"] == "UNASSESSED"


def test_inventory_disagreement_is_rejected():
    with pytest.raises(ValueError, match="disagree"):
        semantic.assess_qa_answer(EXPECTED, EXPECTED, DEFINITIONS, "global:access")
    with pytest.raises(ValueError, match="nonempty"):
        semantic.assess_qa_answer(EXPECTED, EXPECTED, {"global:x": ""})


@pytest.fixture(scope="module")
def envelope(tmp_path_factory):
    path = tmp_path_factory.mktemp("qa-diagnostic-fixture") / "families.jsonl"
    terms = [{"key": eid.split(":", 1)[1], "canonical": "콘솔" if i == 0 else "절차",
              "surfaces": ["ABC"], "short_definition": definition}
             for i, (eid, definition) in enumerate(DEFINITIONS.items())]
    documents = []
    for index, (eid, definition) in enumerate([*DEFINITIONS.items(), (None, None)]):
        target = "ABC" if eid else "ZZZ"
        cue = ("처리하는 대상은 " + terms[index]["canonical"] + "이다." if eid else "이 표현은 아직 등록하지 않은 물품이다.")
        documents.append({"document_id": f"doc-{index}", "text": f"{target}를 확인했다.\n\n" + cue,
            "target_surface": target, "stratum": "LINK" if eid else "NIL",
            "gold": {"label": "LINK" if eid else "NIL", "entity_ref": eid}, "expected_answer": definition,
            "decisive_evidence": [{"document": "source", "quote": cue}], "rationale": "Authored test world."})
    family = {"family_id": "qa-test", "domain": "test", "annotation_origin": "AI_AUTHORED_SYNTHETIC",
        "human_verified": False, "terms": terms, "documents": documents,
        "knowledge_document": {"document_id": "kb-qa-test", "text": "\n\n".join(
            f"{term['canonical']} ABC global:{term['key']}\n{term['short_definition']}" for term in terms)}}
    path.write_bytes(_json_bytes(family))
    return build_document_context_envelope(path)


def frozen_run(tmp_path, envelope):
    run = tmp_path / "run"
    run.mkdir()
    requests, protocol = deepcopy(envelope["requests"]), deepcopy(envelope["protocol"])
    responses = []
    for row in requests:
        if (row["document_id"], row["condition"], row["task"]) == ("doc-2", "none__none", "document_qa"):
            continue
        qa = row["task"] == "document_qa"
        response = {"answer": row["expected_answer"]} if qa else {"selections": [{
            "surface": row["target_surface"], "entity_id": row["expected_entity_id"]}]}
        status = "RECEIVED"
        if qa and row["document_id"] == "doc-0" and row["condition"] == "retrieved__full":
            response["answer"] += "입니다."
        if qa and row["document_id"] == "doc-0" and row["condition"] == "full__full":
            response["answer"] += "이며 모든 업무를 자동 처리한다."
        if qa and row["document_id"] == "doc-2" and row["condition"] == "full__full":
            response["entity_id"] = None
            status = "MALFORMED"
        responses.append({"case_id": row["case_id"], "condition": row["condition"], "status": status,
                          "response": response, "error": None, "latency_ms": 1, "usage": None})
    for name, rows in (("requests.jsonl", requests), ("responses.jsonl", responses)):
        (run / name).write_bytes(b"".join(_json_bytes(row) for row in rows))
    graded = grade_document_context_outputs(requests, responses)
    graded["limitations"] = protocol["limitations"]
    (run / "graded.json").write_bytes(_json_bytes({"model_results": graded}))
    hashes = {name: hashlib.sha256((run / name).read_bytes()).hexdigest() for name in ARTIFACTS}
    manifest = {"track": "document_context", "protocol": protocol["kind"], "declared_protocol": protocol,
        "requested_model": "test-model", "code_revision": "frozen-code", "request_count": len(requests),
        "received_count": len(responses), "missing_count": 1, "error_count": 0, "malformed_count": 1,
        "status": "INCOMPLETE", "artifact_sha256": hashes, "request_corpus_sha256": hashes["requests.jsonl"]}
    manifest["seal_sha256"] = hashlib.sha256(_json_bytes(manifest)).hexdigest()
    (run / "run_manifest.json").write_bytes(_json_bytes(manifest))
    return run


def test_frozen_diagnostic_leaves_exact_scores_and_artifacts_unchanged(tmp_path, envelope, monkeypatch):
    run = frozen_run(tmp_path, envelope)
    before = {path.name: path.read_bytes() for path in run.iterdir()}
    monkeypatch.setattr("eval.document_context.build_document_context_envelope",
                        lambda *a, **k: pytest.fail("frozen diagnostic must not load contemporary fixtures"))
    summary = semantic.prepare_diagnostic(run)
    assert {path.name: path.read_bytes() for path in run.iterdir()} == before
    cell = summary["by_condition"]["retrieved__full"]
    assert cell["strict_exact_correct"] == 2
    assert cell["diagnostic_credited"] == 3
    assert cell["additional_normalized_matches"] == 1
    assert summary["by_condition"]["full__full"]["UNASSESSED"] == 2
    assert summary["by_condition"]["none__none"]["NULL_CORRECT"] == 0
    assert summary["overall"]["reasons"]["missing_response"] == 1
    assert summary["overall"]["reasons"]["malformed_response"] == 1
    assert summary["candidate_definitions_by_family"] == {"qa-test": DEFINITIONS}
    assert len(summary["review_queue"]) == 3


def test_frozen_diagnostic_rejects_modified_original_artifact(tmp_path, envelope):
    run = frozen_run(tmp_path, envelope)
    with (run / "responses.jsonl").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        semantic.prepare_diagnostic(run)


def test_frozen_definition_inventory_requires_all_candidates(envelope):
    rows = deepcopy(envelope["requests"])
    for row in rows:
        row["pack"] = None
        if row["expected_entity_id"] == "global:access":
            row["expected_entity_id"] = None
            row["expected_answer"] = None
    with pytest.raises(ValueError, match="every family glossary ID"):
        semantic._candidate_definitions(rows)


def test_cli_writes_separate_diagnostic_and_never_overwrites(tmp_path, envelope, capsys):
    run = frozen_run(tmp_path, envelope)
    output = tmp_path / "diagnostic"
    semantic.main(["--run-dir", str(run), "--out-dir", str(output)])
    assert (output / "diagnostic.json").is_file()
    assert "Original exact scores" in (output / "RESULTS.md").read_text()
    assert json.loads(capsys.readouterr().out)["additional_normalized_matches"] == 1
    with pytest.raises(FileExistsError):
        semantic.main(["--run-dir", str(run), "--out-dir", str(output)])

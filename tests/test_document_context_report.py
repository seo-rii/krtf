"""Frozen factorial reports distinguish information, meaning and execution permission."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import report_document_context as report
from eval.document_context import build_document_context_envelope, grade_document_context_outputs


def _seal(run_dir, manifest):
    manifest = deepcopy(manifest)
    manifest.pop("seal_sha256", None)
    manifest["artifact_sha256"] = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
                                  for name in report.ARTIFACTS}
    manifest["request_corpus_sha256"] = manifest["artifact_sha256"]["requests.jsonl"]
    manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
    (run_dir / "run_manifest.json").write_bytes(report._json_bytes(manifest))


def _rows(run_dir, name):
    return [json.loads(line) for line in (run_dir / name).read_text().splitlines()]


def _write_rows(run_dir, name, rows):
    (run_dir / name).write_bytes(b"".join(report._json_bytes(row) for row in rows))


def _grade(run_dir, rows, records, protocol):
    grades = grade_document_context_outputs(rows, [record for record in records if "response" in record])
    grades["limitations"] = list(protocol["limitations"])
    (run_dir / "graded.json").write_bytes(report._json_bytes({"model_results": grades}))


@pytest.fixture(scope="module")
def envelope(tmp_path_factory):
    path = tmp_path_factory.mktemp("report-fixture") / "families.jsonl"
    terms = [
        {"key": "opaque-c7", "canonical": "과금 관리 콘솔", "surfaces": ["ABC"],
         "short_definition": "월별 과금 상태를 관리하는 콘솔"},
        {"key": "opaque-d9", "canonical": "출입 승인 절차", "surfaces": ["ABC"],
         "short_definition": "방문자의 출입을 승인하는 절차"},
    ]
    documents = []
    for name, index in (("billing", 0), ("access", 1), ("nil", None)):
        target = "ABC" if index is not None else "ZZZ"
        cue = ("오늘의 대상은 " + terms[index]["canonical"] + "이다." if index is not None else
               "오늘의 대상은 사전에 등록되지 않은 임시 물품이다.")
        text = f"업무 기록: {target}를 확인했다.\n\n처리자는 오전 근무자다.\n\n" + cue + "\n\n검토는 오후에 끝났다."
        documents.append({"document_id": name, "target_surface": target, "text": text,
            "stratum": "contextual_collision" if index is not None else "NIL",
            "gold": {"label": "LINK" if index is not None else "NIL",
                     "entity_ref": "global:" + terms[index]["key"] if index is not None else None},
            "expected_answer": terms[index]["short_definition"] if index is not None else None,
            "decisive_evidence": [{"document": "source", "quote": cue}],
            "rationale": "Authored report test world with distinct target meanings."})
    family = {"family_id": "report-world", "domain": "test", "annotation_origin": "AI_AUTHORED_SYNTHETIC",
        "human_verified": False, "terms": terms, "documents": documents,
        "knowledge_document": {"document_id": "knowledge-report-world", "text": "\n\n".join(
            f"{term['canonical']} / ABC / global:{term['key']}\n{term['short_definition']}" for term in terms)}}
    path.write_bytes(report._json_bytes(family))
    return build_document_context_envelope(path)


def _frozen_run(tmp_path, envelope, *, name="run"):
    run_dir = tmp_path / name
    run_dir.mkdir()
    rows, protocol = deepcopy(envelope["requests"]), deepcopy(envelope["protocol"])
    records = []
    for row in rows:
        document, condition, task = row["document_id"], row["condition"], row["task"]
        if (document, condition, task) == ("access", "retrieved__full", "document_qa"):
            continue  # An unattempted request differs from a failed request.
        qa = task == "document_qa"
        response = {"answer": row["expected_answer"]} if qa else {"selections": [
            {"surface": row["target_surface"], "entity_id": row["expected_entity_id"]}]}
        record = {"case_id": row["case_id"], "condition": condition, "status": "RECEIVED",
            "response": response, "error": None, "latency_ms": 100.001, "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
        if qa and document == "billing":
            if condition == "none__none":
                response["answer"] = None
            elif condition == "retrieved__none":
                response["answer"] = "잘못된 정의"
            elif condition == "full__full":
                response.update(answer=None, entity_id="global:opaque-c7")
                record["status"] = "MALFORMED"
            elif condition == "retrieved__full":
                record.update(status="TRANSPORT_ERROR", error={"type": "TimeoutError"}, usage=None)
                record.pop("response")
        if document == "nil":
            if qa and condition == "none__full":
                response["answer"] = "근거 없는 정의"
            elif not qa and condition == "full__full":
                response["selections"][0]["entity_id"] = "global:opaque-c7"
        records.append(record)
    _write_rows(run_dir, "requests.jsonl", rows)
    _write_rows(run_dir, "responses.jsonl", records)
    _grade(run_dir, rows, records, protocol)
    received = sum("response" in record for record in records)
    manifest = {"track": "document_context", "protocol": protocol["kind"], "declared_protocol": protocol,
        "request_provenance": envelope["provenance"], "code_revision": "frozen-code", "requested_model": "model-b",
        "served_models": {"data": [{"id": "model-b"}]}, "endpoint": "http://127.0.0.1/v1",
        "started_at": "2026-10-14T00:00:00Z", "finished_at": "2026-10-14T00:01:00Z",
        "decoding": {"max_tokens": 128, "temperature": 0}, "request_count": len(rows), "received_count": received,
        "missing_count": len(rows) - received, "error_count": 1, "malformed_count": 1, "status": "INCOMPLETE"}
    _seal(run_dir, manifest)
    return run_dir


def test_report_keeps_semantics_visibility_and_arm_specific_permission_separate(tmp_path, envelope, monkeypatch):
    run_dir = _frozen_run(tmp_path, envelope)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("eval.document_context.build_document_context_envelope",
                        lambda *a, **k: pytest.fail("report must not rebuild current fixtures"))
    monkeypatch.setattr("eval.document_context.QA_CONTEXT_POLICY", "a future policy")
    summary = report.prepare_report(run_dir)
    assert {path.name: path.read_bytes() for path in run_dir.iterdir()} == before
    assert summary["counts"] == {"request_count": 72, "received_count": 70, "missing_count": 2,
        "error_count": 1, "malformed_count": 1, "attempted_count": 71, "not_attempted_count": 1,
        "documents": 3, "conditions": 12, "families": 1}
    cells = summary["by_condition"]
    qa = cells["none__none"]["by_task"]["document_qa"]
    assert qa["semantic"]["semantic_match"] == 2 and qa["semantic"]["positive_null"] == 1
    assert qa["semantic"]["safe_null"] == 1 and qa["semantic"]["positive_planned"] == 2
    assert qa["evidence"]["source_gold_visible"] == qa["evidence"]["gold_definition_visible"] == 0
    routing = cells["none__none"]["by_task"]["structured_routing"]["semantic"]
    assert routing["semantic_match"] == 3 and routing["operational_correct"] == 1
    assert cells["none__none"]["routing_acceptance"]["rejected_correct_nonnull"] == 2
    assert cells["full__full"]["routing_acceptance"]["accepted_wrong_nonnull"] == 1
    assert cells["full__full"]["by_task"]["document_qa"]["semantic"]["malformed"] == 1
    assert cells["full__full"]["by_task"]["document_qa"]["semantic"]["safe_null"] == 1
    assert cells["retrieved__full"]["by_task"]["document_qa"]["semantic"]["missing"] == 2
    evidence = cells["full__full"]["by_task"]["document_qa"]["evidence"]
    assert evidence["source_gold_visible"] == 3 and evidence["gold_entity_id_visible"] == 2
    assert evidence["definition_recall"] == evidence["entity_id_recall"] == 1
    assert summary["annotation_origin"] == "AI_AUTHORED_SYNTHETIC"
    assert summary["human_verified"] is summary["quality_claim"] is False
    markdown = report.render_markdown(summary)
    for phrase in ("no pooled primary score", "before", "Source changes at fixed knowledge",
                   "Knowledge changes at fixed source", "Accepted wrong ID", "authored documents", "historical C"):
        assert phrase in markdown


def test_factorial_contrasts_hold_other_axis_fixed_and_preserve_incomplete_pairs(tmp_path, envelope):
    summary = report.prepare_report(_frozen_run(tmp_path, envelope))
    knowledge = summary["factorial_comparisons"]["knowledge_at_fixed_source"]
    value = knowledge["none"]["none_to_full"]["by_task"]["document_qa"]
    assert value["helpful"] == 1 and value["harmful"] == 0
    assert value["helpful_case_ids"] == ["billing:document_qa"]
    value = knowledge["none"]["full_to_retrieved"]["by_task"]["document_qa"]
    assert value["harmful"] == 1 and value["helpful"] == 0
    value = knowledge["full"]["full_to_retrieved"]["by_task"]["document_qa"]
    assert value["comparable"] == 1 and value["incomplete"] == 2
    source = summary["factorial_comparisons"]["source_at_fixed_knowledge"]
    value = source["none"]["none_to_full"]["by_task"]["document_qa"]
    assert value["helpful"] == value["harmful"] == 1
    assert "overall" not in source["none"]["none_to_full"]
    assert knowledge["full"]["full_to_ktrf"]["baseline_condition"] == "full__full"
    assert source["ktrf"]["full_to_retrieved"]["current_condition"] == "ktrf__retrieved"


@pytest.mark.parametrize("artifact", report.ARTIFACTS)
def test_rejects_modified_sealed_artifact(tmp_path, envelope, artifact):
    run_dir = _frozen_run(tmp_path, envelope)
    with (run_dir / artifact).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        report.prepare_report(run_dir)


def test_rejects_unsealed_manifest_edit(tmp_path, envelope):
    run_dir = _frozen_run(tmp_path, envelope)
    path = run_dir / "run_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["requested_model"] = "different-model"
    path.write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match="manifest seal"):
        report.prepare_report(run_dir)


@pytest.mark.parametrize("mutation,match", [
    ("grade", "frozen regrading"), ("counts", "manifest counts"),
    ("duplicate", "unknown or duplicate"), ("unknown", "unknown or duplicate"),
    ("schema", "task schema"), ("missing_response", "presence disagrees"),
    ("error_status", "error disagrees"), ("missing_cell", "complete condition/task matrix"),
    ("changed_facts", "frozen source facts"), ("changed_visibility", "visibility or deterministic"),
    ("protocol_origin", "gold origin"), ("corpus_hash", "request corpus hash"),
    ("artifact_set", "all three run artifacts"), ("complete", "completion status"),
    ("human_gold", "authored factorial identity"), ("condition_grid", "authored factorial identity"),
])
def test_rejects_resealed_inconsistency(tmp_path, envelope, mutation, match):
    run_dir = _frozen_run(tmp_path, envelope)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if mutation == "grade":
        path = run_dir / "graded.json"
        graded = json.loads(path.read_text())
        graded["model_results"]["cases"][0]["semantic_match"] = True
        path.write_bytes(report._json_bytes(graded))
    elif mutation == "counts":
        manifest["received_count"] += 1
    elif mutation == "complete":
        manifest["status"] = "COMPLETE"
    elif mutation == "protocol_origin":
        manifest["declared_protocol"].pop("gold_origin")
    elif mutation == "human_gold":
        manifest["declared_protocol"]["human_verified"] = True
    elif mutation == "condition_grid":
        manifest["declared_protocol"]["conditions"].pop()
    elif mutation in {"duplicate", "unknown", "schema", "missing_response", "error_status"}:
        records = _rows(run_dir, "responses.jsonl")
        if mutation == "duplicate":
            records.append(records[0])
        elif mutation == "unknown":
            records[0]["case_id"] = "unknown"
        elif mutation == "schema":
            records[0]["response"]["extra"] = "disallowed"
        elif mutation == "missing_response":
            records[0].pop("response")
        else:
            records[0]["error"] = {"type": "bad"}
        _write_rows(run_dir, "responses.jsonl", records)
    elif mutation in {"missing_cell", "changed_facts", "changed_visibility"}:
        rows = _rows(run_dir, "requests.jsonl")
        if mutation == "missing_cell":
            rows.pop()
        elif mutation == "changed_facts":
            rows[0]["stratum"] = "forged-stratum"
        else:
            rows[0]["visible_source"] = rows[0]["source_text"]
        _write_rows(run_dir, "requests.jsonl", rows)
    _seal(run_dir, manifest)
    if mutation in {"corpus_hash", "artifact_set"}:
        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        manifest.pop("seal_sha256")
        if mutation == "corpus_hash":
            manifest["request_corpus_sha256"] = "wrong-hash"
        else:
            manifest["artifact_sha256"].pop("graded.json")
        manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
        (run_dir / "run_manifest.json").write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match=match):
        report.prepare_report(run_dir)


def test_model_comparison_requires_same_requests_protocol_and_decoding(tmp_path, envelope):
    baseline = _frozen_run(tmp_path, envelope, name="baseline")
    current = _frozen_run(tmp_path, envelope, name="current")
    records = _rows(current, "responses.jsonl")
    record = next(record for record in records if record["case_id"] == "billing:document_qa"
                  and record["condition"] == "none__none")
    row = next(row for row in envelope["requests"] if row["case_id"] == record["case_id"])
    record["response"]["answer"] = row["expected_answer"]
    _write_rows(current, "responses.jsonl", records)
    manifest = json.loads((current / "run_manifest.json").read_text())
    manifest["requested_model"] = "model-c"
    _grade(current, envelope["requests"], records, manifest["declared_protocol"])
    _seal(current, manifest)
    summary = report.prepare_report(current, compare=baseline)
    comparison = summary["comparison"]
    assert comparison["baseline_model"] == "model-b" and comparison["current_model"] == "model-c"
    assert comparison["by_condition"]["none__none"]["by_task"]["document_qa"]["helpful"] == 1
    assert comparison["by_condition"]["none__none"]["by_task"]["structured_routing"]["helpful"] == 0
    assert comparison["by_condition"]["retrieved__full"]["by_task"]["document_qa"]["incomplete"] == 2
    assert "Paired model comparison" in report.render_markdown(summary)
    manifest["decoding"]["max_tokens"] = 256
    _seal(current, manifest)
    with pytest.raises(ValueError, match="identical frozen requests, protocol and decoding"):
        report.prepare_report(current, compare=baseline)


def test_missing_source_annotation_is_not_counted_as_failed_visibility():
    cases = [{"positive_gold": True, "source_gold_visible": None, "definition_visible": False,
              "entity_id_visible": False}]
    evidence = report._evidence(cases)
    assert evidence["source_evidence_applicable"] == 0
    assert evidence["source_evidence_presence_rate"] is None
    assert evidence["definition_recall"] == 0


def test_report_cli_adds_outputs_without_mutating_sealed_inputs(tmp_path, envelope, monkeypatch):
    run_dir = _frozen_run(tmp_path, envelope)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir)])
    assert report.main() == 0
    assert {name: (run_dir / name).read_bytes() for name in before} == before
    assert json.loads((run_dir / "summary.json").read_text())["counts"]["documents"] == 3
    assert (run_dir / "RESULTS.md").read_text().startswith("# Knowledge and source document context")

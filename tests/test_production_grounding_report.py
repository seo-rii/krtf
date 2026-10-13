"""Sealed production reports preserve semantic, execution and response-contract distinctions."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import report_production_grounding as report
from eval.product_utility import swap_worlds
from eval.production_grounding import PROTOCOL, build_document_requests, grade_production_outputs


def _seal(run_dir, manifest):
    manifest = deepcopy(manifest)
    manifest.pop("seal_sha256", None)
    manifest["artifact_sha256"] = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
                                  for name in report.ARTIFACTS}
    manifest["request_corpus_sha256"] = manifest["artifact_sha256"]["requests.jsonl"]
    manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
    (run_dir / "run_manifest.json").write_bytes(report._json_bytes(manifest))


def _write_grades(run_dir, requests, records, protocol):
    grades = grade_production_outputs(requests, [record for record in records if "response" in record])
    grades["limitations"] = list(protocol["limitations"])
    (run_dir / "graded.json").write_bytes(report._json_bytes({"model_results": grades}))


def _read_rows(run_dir, name):
    return [json.loads(line) for line in (run_dir / name).read_text().splitlines()]


@pytest.fixture(scope="module")
def frozen_requests():
    worlds = {name: snapshot for name, snapshot, _ in swap_worlds()}
    rows = []
    definitions = {"billing": "청구 상태를 관리하는 시스템", "access": "출입 요청을 승인하는 절차"}
    for name in ("left", "right", "allowed", "nil", "malformed", "wrong-authorized"):
        expected = (None if name in {"nil", "wrong-authorized"} else "project:access" if name == "right"
                    else "project:billing" if name == "left" else "global:billing")
        world = "ambiguous" if name in {"left", "right"} else "missing" if name == "nil" else "tenant-a"
        text = "ABC는 출입 요청을 승인합니다." if name == "right" else "ABC는 청구 상태를 관리합니다."
        rows.extend(build_document_requests(worlds[world], document_id=name, family_id="fixture",
            domain="test", stratum="contextual_collision" if name in {"left", "right"} else name,
            text=text, target_surface="ABC", target_span=[0, 3],
            gold={"label": "LINK" if expected else "NIL", "entity_ref": expected},
            expected_answer=definitions[expected.split(":")[1]] if expected else None,
            provenance={"source": "report-test-fixture", "annotation_origin": "AI_SYNTHETIC", "human_verified": False},
            contrast_pair_id="contrast" if name in {"left", "right"} else None,
            contrast_member=("original" if name == "left" else "contrast") if name in {"left", "right"} else None))
    return rows


def _frozen_run(tmp_path, requests, *, name="run", real=False):
    run_dir = tmp_path / name
    run_dir.mkdir()
    requests = deepcopy(requests)
    records = []
    for row in requests:
        document, qa = row["document_id"], row["task"] == "document_qa"
        response = {"answer": row["expected_answer"]} if qa else {"selections": [
            {"surface": row["target_surface"], "entity_id": row["expected_entity_id"]}]}
        if not qa and document == "left":
            response["selections"][0]["entity_id"] = None
        if not qa and document == "wrong-authorized":
            response["selections"][0]["entity_id"] = "global:billing"
        record = {"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
            "response": response, "error": None, "latency_ms": 100, "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
        if qa and document == "malformed":
            record["response"]["entity_id"] = row["expected_entity_id"]
            record["status"] = "MALFORMED"
        if not qa and document == "nil":
            record.update(status="TRANSPORT_ERROR", error={"type": "TimeoutError"}, usage=None)
            record.pop("response")
        records.append(record)
    for filename, values in (("requests.jsonl", requests), ("responses.jsonl", records)):
        (run_dir / filename).write_bytes(b"".join(report._json_bytes(row) for row in values))
    protocol = deepcopy(PROTOCOL)
    if real:
        protocol.update(kind="production_grounding_real_holdout_v1", gold_origin="AI_ANNOTATED_REAL_DOCUMENTS",
                        limitations=["Previously unused real source documents; AI annotations are not human gold."])
    _write_grades(run_dir, requests, records, protocol)
    manifest = {"track": "production_real" if real else "production_synthetic", "protocol": protocol["kind"],
        "declared_protocol": protocol, "request_provenance": {"fixture": "report-test"},
        "code_revision": "frozen-code", "requested_model": "frozen-model",
        "endpoint": "http://127.0.0.1/v1", "started_at": "2026-10-14T00:00:00Z",
        "finished_at": "2026-10-14T00:01:00Z", "decoding": {"max_tokens": 128, "temperature": 0},
        "request_count": 12, "received_count": 11, "missing_count": 1, "error_count": 1,
        "malformed_count": 1, "status": "INCOMPLETE"}
    _seal(run_dir, manifest)
    return run_dir


def test_report_separates_explanation_execution_authority_and_errors(tmp_path, frozen_requests, monkeypatch):
    run_dir = _frozen_run(tmp_path, frozen_requests)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("eval.production_grounding.load_balanced_families",
                        lambda: pytest.fail("reports must not read current corpus fixtures"))
    summary = report.prepare_report(run_dir)
    assert {path.name: path.read_bytes() for path in run_dir.iterdir()} == before
    assert summary["counts"]["documents"] == 6
    assert summary["counts"]["missing_count"] == summary["counts"]["malformed_count"] == 1
    assert summary["counts"]["error_count"] == 1 and summary["counts"]["not_attempted_count"] == 0
    assert summary["annotation_origin"] == "AI_SYNTHETIC" and summary["human_verified"] is False
    assert summary["metrics"]["contextual_pairs"]["both_correct"] == 1
    qa = summary["metrics"]["by_task"]["document_qa"]
    assert qa["correct"] == 5 and qa["malformed"] == qa["qa_unexpected_ids"] == 1
    route = summary["routing_diagnostics"]
    assert route["policy_compliant_null_on_guard_blocked_positive"] == 1
    assert route["correct_id_blocked"] == route["wrong_id_accepted"] == 1
    assert summary["metrics"]["by_task"]["structured_routing"]["accepted_wrong_id"] == 1
    assert summary["operational"]["overall"]["latency_ms"]["observations"] == 12
    assert summary["operational"]["overall"]["actual_usage"]["total_tokens"]["observations"] == 11
    markdown = report.render_markdown(summary)
    assert "6000-token" in markdown and "800-token" in markdown
    assert "Wrong routing ID accepted" in markdown and "No deployment-risk guarantee" in markdown
    assert "Policy-compliant null" in markdown


def test_real_document_origin_and_limitations_come_from_frozen_protocol(tmp_path, frozen_requests):
    run_dir = _frozen_run(tmp_path, frozen_requests, real=True)
    summary = report.prepare_report(run_dir)
    assert summary["annotation_origin"] == "AI_ANNOTATED_REAL_DOCUMENTS"
    assert summary["human_verified"] is False
    assert summary["metrics"]["limitations"] == summary["declared_protocol"]["limitations"]
    assert "not human gold" in summary["limitations"][0]


@pytest.mark.parametrize("artifact", report.ARTIFACTS)
def test_report_rejects_unsealed_artifact_changes(tmp_path, frozen_requests, artifact):
    run_dir = _frozen_run(tmp_path, frozen_requests)
    with (run_dir / artifact).open("ab") as output:
        output.write(b" ")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        report.prepare_report(run_dir)


def test_report_rejects_manifest_tampering(tmp_path, frozen_requests):
    run_dir = _frozen_run(tmp_path, frozen_requests)
    path = run_dir / "run_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["requested_model"] = "replacement-model"
    path.write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match="manifest seal"):
        report.prepare_report(run_dir)


@pytest.mark.parametrize("mutation, match", [
    ("grade", "frozen regrading"), ("duplicate", "duplicate response"),
    ("unknown", "unknown or duplicate response"), ("status", "task schema"),
    ("counts", "manifest counts"), ("corpus_hash", "request corpus hash"),
    ("missing_task", "separate QA and execution"), ("gold", "frozen source facts"),
    ("protocol_origin", "gold origin"), ("artifact_set", "all three run artifacts"),
])
def test_report_rejects_resealed_inconsistent_runs(tmp_path, frozen_requests, mutation, match):
    run_dir = _frozen_run(tmp_path, frozen_requests)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if mutation == "grade":
        path = run_dir / "graded.json"
        graded = json.loads(path.read_text())
        graded["model_results"]["by_task"]["document_qa"]["correct"] += 1
        path.write_bytes(report._json_bytes(graded))
    elif mutation == "counts":
        manifest["received_count"] += 1
    elif mutation == "protocol_origin":
        manifest["declared_protocol"].pop("gold_origin")
    elif mutation in {"duplicate", "unknown", "status"}:
        rows = _read_rows(run_dir, "responses.jsonl")
        if mutation == "duplicate":
            rows.append(rows[0])
        elif mutation == "unknown":
            rows[0]["case_id"] = "not-a-request"
        else:
            rows[0]["response"]["entity_id"] = "forbidden-extra-ID"
        (run_dir / "responses.jsonl").write_bytes(b"".join(report._json_bytes(row) for row in rows))
    elif mutation in {"missing_task", "gold"}:
        rows = _read_rows(run_dir, "requests.jsonl")
        if mutation == "missing_task":
            rows.pop()
        else:
            rows[0]["expected_answer"] = "changed source answer"
        (run_dir / "requests.jsonl").write_bytes(b"".join(report._json_bytes(row) for row in rows))
    _seal(run_dir, manifest)
    if mutation in {"corpus_hash", "artifact_set"}:
        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        manifest.pop("seal_sha256")
        if mutation == "corpus_hash":
            manifest["request_corpus_sha256"] = "not-the-artifact-hash"
        else:
            manifest["artifact_sha256"].pop("graded.json")
        manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
        (run_dir / "run_manifest.json").write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match=match):
        report.prepare_report(run_dir)


def test_paired_model_comparison_uses_same_inputs_and_counts_missing_separately(tmp_path, frozen_requests):
    baseline = _frozen_run(tmp_path, frozen_requests, name="baseline")
    current = _frozen_run(tmp_path, frozen_requests, name="current")
    records = _read_rows(baseline, "responses.jsonl")
    next(record for record in records if record["case_id"] == "left:document_qa")["response"]["answer"] = None
    (baseline / "responses.jsonl").write_bytes(b"".join(report._json_bytes(row) for row in records))
    manifest = json.loads((baseline / "run_manifest.json").read_text())
    manifest["requested_model"] = "baseline-model"
    _write_grades(baseline, frozen_requests, records, manifest["declared_protocol"])
    _seal(baseline, manifest)
    result = report.prepare_report(current, compare=baseline)
    paired = result["comparison"]
    assert paired["baseline_model"] == "baseline-model"
    assert paired["by_task"]["document_qa"]["helpful"] == 1
    assert paired["by_task"]["document_qa"]["harmful"] == 0
    assert paired["by_task"]["structured_routing"]["incomplete"] == 1
    assert paired["by_task"]["document_qa"]["both_incorrect"] == 1
    assert "Paired model comparison" in report.render_markdown(result)
    manifest = json.loads((current / "run_manifest.json").read_text())
    manifest["decoding"]["max_tokens"] = 256
    _seal(current, manifest)
    with pytest.raises(ValueError, match="identical frozen requests, protocol and decoding"):
        report.prepare_report(current, compare=baseline)


def test_report_cli_preserves_sealed_inputs(tmp_path, frozen_requests, monkeypatch):
    run_dir = _frozen_run(tmp_path, frozen_requests)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir)])
    assert report.main() == 0
    assert {name: (run_dir / name).read_bytes() for name in before} == before
    assert json.loads((run_dir / "summary.json").read_text())["counts"]["documents"] == 6
    assert (run_dir / "RESULTS.md").read_text().startswith("# Production QA and execution")

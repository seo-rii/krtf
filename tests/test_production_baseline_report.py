"""B/C comparisons verify both sealed runs and keep semantic and guard outcomes separate."""
from copy import deepcopy
import hashlib
import json
import math

import pytest

from eval import production_baseline as baseline
from eval import report_production_baseline as report
from eval.product_utility import swap_worlds
from eval.production_grounding import PROTOCOL, build_document_requests, grade_production_outputs


def _rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def _write_rows(path, rows):
    path.write_bytes(b"".join(report._json_bytes(row) for row in rows))


def _seal(path, manifest):
    manifest = deepcopy(manifest)
    manifest.pop("seal_sha256", None)
    manifest["artifact_sha256"] = {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                                   for name in report.ARTIFACTS}
    manifest["request_corpus_sha256"] = manifest["artifact_sha256"]["requests.jsonl"]
    manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
    (path / "run_manifest.json").write_bytes(report._json_bytes(manifest))
    return manifest


def _grades(path, requests, records, protocol, *, production=False):
    grader = grade_production_outputs if production else baseline.grade_baseline_outputs
    graded = grader(requests, [row for row in records if "response" in row])
    graded["limitations"] = list(protocol["limitations"])
    (path / "graded.json").write_bytes(report._json_bytes({"model_results": graded}))


@pytest.fixture(scope="module")
def source_rows():
    worlds = {name: snapshot for name, snapshot, _ in swap_worlds()}
    rows, catalogs = [], {}
    definitions = {"billing": "청구 상태를 관리하는 시스템", "access": "출입 요청을 승인하는 절차"}
    for name in ("left", "right", "allowed", "nil", "malformed", "wrong-authorized"):
        eid = (None if name in {"nil", "wrong-authorized"} else "project:access" if name == "right"
               else "project:billing" if name == "left" else "global:billing")
        world = "ambiguous" if name in {"left", "right"} else "missing" if name == "nil" else "tenant-a"
        text = "ABC는 출입 요청을 승인합니다." if name == "right" else "ABC는 청구 상태를 관리합니다."
        rows.extend(build_document_requests(worlds[world], document_id=name, family_id="fixture",
            domain="test", stratum="contextual_collision" if name in {"left", "right"} else name,
            text=text, target_surface="ABC", target_span=[0, 3],
            gold={"label": "LINK" if eid else "NIL", "entity_ref": eid},
            expected_answer=definitions[eid.split(":")[1]] if eid else None,
            provenance={"source": "baseline-report-test", "annotation_origin": "AI_SYNTHETIC", "human_verified": False},
            contrast_pair_id="contrast" if name in {"left", "right"} else None,
            contrast_member=("original" if name == "left" else "contrast") if name in {"left", "right"} else None))
        catalogs[name] = baseline._catalog(worlds[world].glossary)
    return rows, catalogs


def _records(requests, *, production):
    records = []
    for row in requests:
        name, qa = row["document_id"], row["task"] == "document_qa"
        response = {"answer": row["expected_answer"]} if qa else {"selections": [
            {"surface": row["target_surface"], "entity_id": row["expected_entity_id"]}]}
        if name == "left":
            if qa and not production:
                response["answer"] = None
            elif not qa and production:
                response["selections"][0]["entity_id"] = None
        if not qa and name == "wrong-authorized":
            response["selections"][0]["entity_id"] = "global:billing"
        record = {"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
            "response": response, "error": None, "latency_ms": 100.001, "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
        if qa and name == "malformed":
            response["entity_id"] = row["expected_entity_id"]
            record["status"] = "MALFORMED"
        if (not qa and name == "nil") or (qa and name == "allowed" and not production):
            record.update(status="TRANSPORT_ERROR", error={"type": "TimeoutError"}, usage=None)
            record.pop("response")
        records.append(record)
    return records


def _write_run(path, requests, *, model, protocol, production=False, real=False):
    path.mkdir(parents=True)
    records = _records(requests, production=production)
    _write_rows(path / "requests.jsonl", requests)
    _write_rows(path / "responses.jsonl", records)
    _grades(path, requests, records, protocol, production=production)
    received = sum("response" in record for record in records)
    manifest = {"track": ("production_" if production else "baseline_") + ("real" if real else "synthetic"),
        "protocol": protocol["kind"], "declared_protocol": deepcopy(protocol),
        "request_provenance": {"fixture": "baseline-report"} if production else {
            "reference_root": protocol["reference_root"], "reference_runs": deepcopy(protocol["reference_runs"])},
        "code_revision": "frozen-source-code", "requested_model": model,
        "endpoint": "http://127.0.0.1/v1", "started_at": "2026-10-14T00:00:00Z",
        "finished_at": "2026-10-14T00:01:00Z", "decoding": {"max_tokens": 128, "temperature": 0},
        "request_count": len(requests), "received_count": received, "missing_count": len(requests) - received,
        "error_count": len(requests) - received, "malformed_count": 1, "status": "INCOMPLETE"}
    return _seal(path, manifest)


def _paired_runs(tmp_path, source_rows, *, real=False):
    requests, catalogs = source_rows
    corpus = "real" if real else "synthetic"
    root, references = tmp_path / "production", {}
    protocol = deepcopy(PROTOCOL)
    if real:
        protocol.update(kind="production_grounding_real_holdout_v1", gold_origin="AI_AUTHORED_NOT_HUMAN")
    for model in ("gemma12b", "qwen27b"):
        stage = corpus + "_" + model
        path = root / stage
        manifest = _write_run(path, requests, model=model, protocol=protocol, production=True, real=real)
        references[model] = {"run_dir": str(path), "stage_id": stage,
            "run_manifest_sha256": hashlib.sha256((path / "run_manifest.json").read_bytes()).hexdigest(),
            "manifest_seal_sha256": manifest["seal_sha256"],
            "request_corpus_sha256": manifest["request_corpus_sha256"],
            "requested_model": model, "decoding": manifest["decoding"], "code_revision": manifest["code_revision"]}
    b_requests = [baseline._build_row(row, catalogs[row["document_id"]]) for row in requests]
    b_protocol = {"kind": report.PROTOCOLS["baseline_" + corpus], "gold_origin": protocol["gold_origin"],
        "human_verified": False, "limitations": ["AI gold; no deployment guarantee."],
        "reference_root": str(root), "reference_runs": references}
    result = {}
    for model in references:
        path = tmp_path / ("baseline_" + model)
        _write_run(path, b_requests, model=model, protocol=b_protocol, real=real)
        result[model] = path
    return result


def test_report_uses_semantic_changes_and_separate_execution_validators(tmp_path, source_rows):
    run = _paired_runs(tmp_path, source_rows)["gemma12b"]
    before = {path.name: path.read_bytes() for path in run.iterdir()}
    summary = report.prepare_report(run)
    assert {path.name: path.read_bytes() for path in run.iterdir()} == before
    assert summary["counts"]["documents"] == 6
    assert summary["counts"]["missing_count"] == 2
    assert summary["counts"]["malformed_count"] == 1
    comparison = summary["production_comparison"]
    assert comparison["paired_changes"]["by_task"]["document_qa"]["helpful_case_ids"] == ["left:document_qa"]
    assert comparison["paired_changes"]["by_task"]["document_qa"]["incomplete"] == 1
    assert comparison["paired_changes"]["by_task"]["structured_routing"]["harmful_case_ids"] == ["left:structured_routing"]
    # C returns the correct ambiguous ID for 'right', but its execution guard blocks it.
    assert comparison["routing_acceptance"]["C"]["rejected_correct_nonnull"] == 1
    assert comparison["routing_acceptance"]["B"]["rejected_correct_nonnull"] == 0
    assert comparison["routing_acceptance"]["B"]["accepted_wrong_nonnull"] == 1
    assert comparison["routing_acceptance"]["C"]["accepted_wrong_nonnull"] == 1
    assert comparison["candidate_recall"]["B"]["document_qa"]["gold_retrieved"] == 4
    assert comparison["candidate_recall"]["C"]["document_qa"]["gold_retrieved"] == 4
    assert comparison["candidate_recall"]["B"]["document_qa"]["candidate_count"]["observations"] == 6
    assert comparison["cost"]["B"]["overall"]["latency_ms"]["total"] == math.fsum([100.001] * 12)
    assert comparison["cost"]["B"]["overall"]["actual_usage"]["total_tokens"]["total"] == 1100
    markdown = report.render_markdown(summary)
    assert "before" in markdown and "B is never passed through C's guard" in markdown
    assert "Median candidates" in markdown and "Accepted wrong ID" in markdown
    assert "Helpful for C" in markdown and "Missing pairs are incomplete" in markdown


def test_real_origin_and_frozen_prompts_survive_current_policy_changes(tmp_path, source_rows, monkeypatch):
    run = _paired_runs(tmp_path, source_rows, real=True)["gemma12b"]
    expected = report.prepare_report(run)
    monkeypatch.setattr(baseline, "SYSTEM", "a changed future policy")
    monkeypatch.setattr(baseline, "_question", lambda row: "a changed future question")
    monkeypatch.setattr(baseline, "load_balanced_families", lambda: pytest.fail("frozen report read live corpus"))
    result = report.prepare_report(run)
    assert result == expected
    assert result["annotation_origin"] == "AI_AUTHORED_NOT_HUMAN" and result["human_verified"] is False


@pytest.mark.parametrize("artifact", report.ARTIFACTS)
def test_rejects_unsealed_artifact_change(tmp_path, source_rows, artifact):
    run = _paired_runs(tmp_path, source_rows)["gemma12b"]
    with (run / artifact).open("ab") as output:
        output.write(b" ")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        report.prepare_report(run)


def test_rejects_unsealed_manifest_change(tmp_path, source_rows):
    run = _paired_runs(tmp_path, source_rows)["gemma12b"]
    manifest = json.loads((run / "run_manifest.json").read_bytes())
    manifest["requested_model"] = "different-model"
    (run / "run_manifest.json").write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match="manifest seal"):
        report.prepare_report(run)


@pytest.mark.parametrize("mutation, match", [
    ("grade", "frozen regrading"), ("duplicate", "duplicate response"), ("unknown", "unknown or duplicate"),
    ("status", "task schema"), ("counts", "manifest counts"), ("missing_task", "separate QA and execution"),
    ("artifact_set", "all three"), ("corpus_hash", "request corpus hash"),
    ("completion", "completion status"), ("protocol_origin", "gold origin"),
])
def test_rejects_resealed_internal_inconsistency(tmp_path, source_rows, mutation, match):
    run = _paired_runs(tmp_path, source_rows)["gemma12b"]
    manifest = json.loads((run / "run_manifest.json").read_bytes())
    if mutation == "grade":
        path = run / "graded.json"
        value = json.loads(path.read_bytes())
        value["model_results"]["by_task"]["document_qa"]["correct"] += 1
        path.write_bytes(report._json_bytes(value))
    elif mutation in {"duplicate", "unknown", "status"}:
        records = _rows(run / "responses.jsonl")
        if mutation == "duplicate":
            records.append(records[0])
        elif mutation == "unknown":
            records[0]["case_id"] = "unknown"
        else:
            records[0]["response"]["entity_id"] = "forbidden"
        _write_rows(run / "responses.jsonl", records)
    elif mutation == "missing_task":
        _write_rows(run / "requests.jsonl", _rows(run / "requests.jsonl")[:-1])
    elif mutation == "counts":
        manifest["received_count"] += 1
    elif mutation == "completion":
        manifest["status"] = "COMPLETE"
    elif mutation == "protocol_origin":
        manifest["declared_protocol"].pop("gold_origin")
    manifest = _seal(run, manifest)
    if mutation in {"artifact_set", "corpus_hash"}:
        manifest.pop("seal_sha256")
        if mutation == "artifact_set":
            manifest["artifact_sha256"].pop("graded.json")
        else:
            manifest["request_corpus_sha256"] = "not-the-artifact-hash"
        manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
        (run / "run_manifest.json").write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match=match):
        report.prepare_report(run)


@pytest.mark.parametrize("mutation, match", [
    ("model", "matching-model"), ("decoding", "decoding"), ("reference_hash", "manifest file hash"),
    ("reference_seal", "seal, model"), ("reference_code", "source identity"),
    ("reference_path", "directory differs"), ("reference_stage", "stage identity"),
    ("provenance", "protocol and provenance"), ("source_provenance", "document, target, gold"),
    ("source_hash", "document, target, gold"), ("gold_origin", "gold origin differs"),
])
def test_rejects_mismatched_production_reference(tmp_path, source_rows, mutation, match):
    run = _paired_runs(tmp_path, source_rows)["gemma12b"]
    manifest = json.loads((run / "run_manifest.json").read_bytes())
    protocol = manifest["declared_protocol"]
    ref = protocol["reference_runs"]["gemma12b"]
    if mutation == "model":
        manifest["requested_model"] = "another-model"
    elif mutation == "decoding":
        manifest["decoding"]["max_tokens"] = 256
    elif mutation == "reference_hash":
        ref["run_manifest_sha256"] = "0" * 64
    elif mutation == "reference_seal":
        ref["manifest_seal_sha256"] = "0" * 64
    elif mutation == "reference_code":
        ref["code_revision"] = "unrelated-code"
    elif mutation == "reference_path":
        ref["run_dir"] += "-other"
    elif mutation == "reference_stage":
        ref["stage_id"] = "real_gemma12b"
    elif mutation == "gold_origin":
        protocol["gold_origin"] = "HUMAN"
    elif mutation in {"source_provenance", "source_hash"}:
        requests = _rows(run / "requests.jsonl")
        if mutation == "source_provenance":
            requests[0]["provenance"]["source"] = "invented source"
        else:
            requests[0]["reference_request_sha256"] = "0" * 64
        _write_rows(run / "requests.jsonl", requests)
        _grades(run, requests, _rows(run / "responses.jsonl"), protocol)
    if mutation != "provenance":
        manifest["request_provenance"]["reference_runs"] = deepcopy(protocol["reference_runs"])
    else:
        manifest["request_provenance"]["reference_root"] += "-other"
    _seal(run, manifest)
    with pytest.raises(ValueError, match=match):
        report.prepare_report(run)


def test_matching_b_models_and_cli_preserve_sealed_inputs(tmp_path, source_rows, monkeypatch):
    runs = _paired_runs(tmp_path, source_rows)
    before = {path.name: path.read_bytes() for path in runs["qwen27b"].iterdir()}
    result = report.prepare_report(runs["qwen27b"], compare=runs["gemma12b"])
    assert result["comparison"]["baseline_model"] == "gemma12b"
    assert result["comparison"]["by_task"]["document_qa"]["incomplete"] == 1
    assert result["comparison"]["overall"]["helpful"] == result["comparison"]["overall"]["harmful"] == 0
    assert "Paired B-model comparison" in report.render_markdown(result)
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(runs["qwen27b"]), "--compare", str(runs["gemma12b"])])
    assert report.main() == 0
    assert {name: (runs["qwen27b"] / name).read_bytes() for name in before} == before
    assert json.loads((runs["qwen27b"] / "summary.json").read_bytes()) == result
    assert (runs["qwen27b"] / "RESULTS.md").read_text().startswith("# Plain glossary retrieval")


def test_paired_b_model_comparison_rejects_different_frozen_prompts(tmp_path, source_rows):
    runs = _paired_runs(tmp_path, source_rows)
    run = runs["qwen27b"]
    requests = _rows(run / "requests.jsonl")
    requests[0]["system"] += " "
    requests[0]["estimated_input_tokens"] = baseline.CharTokenCounter().count(requests[0]["system"] + requests[0]["user"])
    _write_rows(run / "requests.jsonl", requests)
    manifest = json.loads((run / "run_manifest.json").read_bytes())
    _grades(run, requests, _rows(run / "responses.jsonl"), manifest["declared_protocol"])
    _seal(run, manifest)
    with pytest.raises(ValueError, match="identical requests"):
        report.prepare_report(run, compare=runs["gemma12b"])

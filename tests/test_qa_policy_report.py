"""Frozen policy reports distinguish useful QA from execution authority."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import report_qa_policy_probe as report
from eval.qa_policy_probe import grade_policy_outputs


def _seal(run_dir, manifest):
    manifest = deepcopy(manifest)
    manifest.pop("seal_sha256", None)
    manifest["artifact_sha256"] = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
                                  for name in report.ARTIFACTS}
    manifest["request_corpus_sha256"] = manifest["artifact_sha256"]["requests.jsonl"]
    manifest["seal_sha256"] = hashlib.sha256(report._json_bytes(manifest)).hexdigest()
    (run_dir / "run_manifest.json").write_bytes(report._json_bytes(manifest))


def _frozen_run(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    requests, records = [], []
    definitions = {"global:a": "과금을 관리하는 창구", "global:b": "출입을 승인하는 절차"}
    cards = [{"entity_id": eid, "definition": definition, "status": "AMBIGUOUS"}
             for eid, definition in definitions.items()]
    for document in ("left", "right", "allowed", "nil", "malformed"):
        expected_id = None if document == "nil" else "global:b" if document == "right" else "global:a"
        pack = {"resolved_terms": [], "ambiguous_mentions": []}
        if document == "allowed":
            pack["resolved_terms"] = [{"entity_id": eid, "resolution": {"degraded": False},
                                       "mentions": [{"surface": "ABC"}]} for eid in ("global:b",)]
        for task in report.TASKS:
            for condition in report.CONDITIONS:
                row = {"case_id": document + ":" + task, "document_id": document,
                    "family_id": "collision" if document in {"left", "right"} else document,
                    "world": "world", "condition": condition, "task": task,
                    "stratum": "contextual_collision" if document in {"left", "right"} else document,
                    "source_condition": "surface_only", "expected_entity_id": expected_id,
                    "expected_answer": definitions.get(expected_id), "target_surface": "ABC",
                    "gold": {"label": "NIL" if document == "nil" else "LINK"},
                    "pack": deepcopy(pack), "cards": deepcopy(cards), "candidate_hash": "same-candidates",
                    "document_sha256": "document-" + document, "estimated_input_tokens": 100}
                if document in {"left", "right"}:
                    row.update(contrast_pair_id="pair", contrast_member="original" if document == "left" else "contrast")
                answer = row["expected_answer"]
                if document in {"left", "right"} and condition == "strict":
                    answer = None
                if document == "nil" and condition == "qa_context":
                    answer = "없는 정의를 만들어 낸 답변"
                entity_id = expected_id if document == "allowed" else None
                if task == "document_qa" and condition == "qa_context":
                    entity_id = "global:b" if document == "allowed" else expected_id
                record = {"case_id": row["case_id"], "condition": condition,
                    "status": "RECEIVED", "response": {"answer": answer, "entity_id": entity_id},
                    "error": None, "latency_ms": 100, "finish_reason": "stop",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
                if document == "malformed" and task == "document_qa" and condition == "qa_context":
                    record.update(status="MALFORMED", response={})
                if document == "nil" and task == "structured_routing" and condition == "qa_context":
                    record.update(status="TRANSPORT_ERROR", error={"type": "TimeoutError"}, usage=None)
                    record.pop("response")
                requests.append(row)
                records.append(record)
    for name, values in (("requests.jsonl", requests), ("responses.jsonl", records)):
        (run_dir / name).write_bytes(b"".join(report._json_bytes(row) for row in values))
    graded = grade_policy_outputs(requests, [record for record in records if "response" in record])
    (run_dir / "graded.json").write_bytes(report._json_bytes({"model_results": graded}))
    manifest = {"track": "qa_policy_probe", "protocol": "qa_policy_separation_v1",
        "code_revision": "frozen-code-sha", "requested_model": "frozen-model",
        "endpoint": "http://127.0.0.1/v1", "started_at": "2026-10-14T00:00:00Z",
        "finished_at": "2026-10-14T00:10:00Z", "decoding": {"max_tokens": 128},
        "request_count": 20, "received_count": 19, "missing_count": 1, "error_count": 1,
        "malformed_count": 1, "status": "INCOMPLETE"}
    _seal(run_dir, manifest)
    return run_dir


def test_report_keeps_answer_quality_incidental_ids_and_execution_distinct(tmp_path, monkeypatch):
    run_dir = _frozen_run(tmp_path)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("eval.synthetic_grounding_v2.load_balanced_families",
                        lambda: pytest.fail("must not read mutable fixtures"))
    result = report.prepare_report(run_dir)
    assert {path.name: path.read_bytes() for path in run_dir.iterdir()} == before
    assert result["counts"]["request_count"] == 20
    assert result["counts"]["missing_count"] == result["counts"]["malformed_count"] == 1
    qa = result["policy_diagnostics"]["by_condition"]["qa_context"]
    assert qa["contextual_pairs"]["both_correct"] == qa["contextual_pairs"]["planned"] == 1
    assert qa["by_stratum"]["contextual_collision"]["document_qa"]["correct"] == 2
    ids = result["supplementary"]["qa_context"]["qa_incidental_id_semantics"]
    assert ids["correct_blocked"] == ids["answer_correct_with_blocked_id"] == 2
    assert ids["wrong_authorized"] == 1
    negative = result["supplementary"]["qa_context"]["negative_qa_controls"]["nil"]
    assert negative["nonnull"] == 1 and negative["nonnull_rate_planned"] == 1
    paired = result["policy_diagnostics"]["paired_changes"]["by_task"]
    assert paired["document_qa"]["helpful"] == paired["document_qa"]["harmful"] == 2
    assert paired["structured_routing"]["incomplete"] == 1
    assert result["operational"]["qa_context"]["actual_usage"]["total_tokens"]["observations"] == 9
    assert result["operational"]["qa_context"]["latency_ms"]["observations"] == 10
    markdown = report.render_markdown(result)
    assert "AI synthetic" in markdown and "Incidental QA IDs" in markdown
    assert "Correct but blocked" in markdown and "Wrong and guard-accepted" in markdown
    assert "not a causal policy effect" in markdown


@pytest.mark.parametrize("artifact", report.ARTIFACTS)
def test_report_rejects_artifact_tampering(tmp_path, artifact):
    run_dir = _frozen_run(tmp_path)
    with (run_dir / artifact).open("ab") as output:
        output.write(b" ")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        report.prepare_report(run_dir)


def test_report_rejects_changed_manifest_and_wrong_track(tmp_path):
    run_dir = _frozen_run(tmp_path)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    manifest["requested_model"] = "edited"
    (run_dir / "run_manifest.json").write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match="manifest seal"):
        report.prepare_report(run_dir)
    manifest["track"] = "synthetic_expansion_v2"
    _seal(run_dir, manifest)
    with pytest.raises(ValueError, match="requires qa_policy_probe"):
        report.prepare_report(run_dir)


@pytest.mark.parametrize("mutation, match", [
    ("grade", "frozen regrading"), ("duplicate_response", "duplicate response"),
    ("candidate", "same case, candidate facts"), ("missing_task", "both tasks and both conditions"),
    ("manifest_count", "manifest counts"), ("response_status", "malformed task field"),
])
def test_report_rejects_resealed_inconsistent_runs(tmp_path, mutation, match):
    run_dir = _frozen_run(tmp_path)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if mutation == "grade":
        path = run_dir / "graded.json"
        grade = json.loads(path.read_text())
        grade["model_results"]["policy_diagnostics"]["by_condition"]["strict"]["by_task"]["document_qa"]["correct"] += 1
        path.write_bytes(report._json_bytes(grade))
    elif mutation == "manifest_count":
        manifest["received_count"] += 1
    else:
        name = "responses.jsonl" if mutation in {"duplicate_response", "response_status"} else "requests.jsonl"
        path = run_dir / name
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if mutation == "duplicate_response":
            rows.append(rows[0])
        elif mutation == "candidate":
            rows[0]["cards"][0]["definition"] = "changed"
        elif mutation == "missing_task":
            rows.pop()
        else:
            rows[0]["response"] = {"answer": []}
        path.write_bytes(b"".join(report._json_bytes(row) for row in rows))
    _seal(run_dir, manifest)
    with pytest.raises(ValueError, match=match):
        report.prepare_report(run_dir)


def test_report_cli_preserves_inputs(tmp_path, monkeypatch):
    run_dir = _frozen_run(tmp_path)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir)])
    assert report.main() == 0
    assert {name: (run_dir / name).read_bytes() for name in before} == before
    assert (run_dir / "RESULTS.md").read_text().startswith("# QA and execution policy separation")
    assert json.loads((run_dir / "summary.json").read_text())["counts"]["documents"] == 5


def test_malformed_qa_still_audits_incidental_id_without_counting_answer_success(tmp_path):
    run_dir = _frozen_run(tmp_path)
    requests = [json.loads(line) for line in (run_dir / "requests.jsonl").read_text().splitlines()]
    path = run_dir / "responses.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    record = next(record for record in records if record["status"] == "MALFORMED")
    record["response"] = {"answer": [], "entity_id": "global:a"}
    path.write_bytes(b"".join(report._json_bytes(row) for row in records))
    grade = grade_policy_outputs(requests, [row for row in records if "response" in row])
    (run_dir / "graded.json").write_bytes(report._json_bytes({"model_results": grade}))
    _seal(run_dir, json.loads((run_dir / "run_manifest.json").read_text()))
    result = report.prepare_report(run_dir)
    ids = result["supplementary"]["qa_context"]["qa_incidental_id_semantics"]
    assert ids["nonnull"] == 4 and ids["correct_blocked"] == 3
    assert ids["answer_correct_with_blocked_id"] == 2
    diagnostics = result["policy_diagnostics"]["by_condition"]["qa_context"]
    assert diagnostics["qa_incidental_ids"]["nonnull"] == ids["nonnull"]
    assert diagnostics["by_stratum"]["malformed"]["document_qa"]["correct"] == 0
    assert diagnostics["by_stratum"]["malformed"]["document_qa"]["malformed"] == 1

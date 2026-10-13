"""A frozen report keeps model failures, semantic errors and guard results distinct."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import report_synthetic_grounding as report
from eval.synthetic_grounding import grade_expanded_outputs


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
    pack = {"resolved_terms": [{"entity_id": "global:meter", "resolution": {"degraded": False},
             "mentions": [{"surface": "비용계"}]}], "ambiguous_mentions": []}
    requests, records = [], []
    for index, (task, positive) in enumerate((("document_qa", True), ("structured_routing", True),
                                            ("document_qa", False), ("structured_routing", False))):
        for position, condition in enumerate(report.CONDITIONS):
            row = {"case_id": f"case-{index}", "condition": condition, "task": task,
                "world": "test:world", "family_id": "test", "document_id": f"doc-{index}",
                "stratum": "exact" if positive else "nil", "target_surface": "비용계",
                "expected_answer": "비용을 측정하는 계기" if positive else None,
                "expected_entity_id": "global:meter" if positive else None,
                "pack": deepcopy(pack), "estimated_input_tokens": 90,
                "gold": {"label": "LINK" if positive else "NIL"}}
            value = row["expected_answer"] if task == "document_qa" else row["expected_entity_id"]
            if index == 0 and condition == "original":
                value = None
            if index == 1 and condition == "both":
                value = "global:wrong"
            field = "answer" if task == "document_qa" else "entity_id"
            record = {"case_id": row["case_id"], "condition": condition, "status": "RECEIVED",
                "response": {field: value}, "error": None, "finish_reason": "stop",
                "latency_ms": (index + 1) * 100 + position,
                "usage": {"prompt_tokens": 100, "completion_tokens": 15, "total_tokens": 115}}
            if index == 2 and condition == "schema_only":
                record.update(status="MALFORMED", response={})
            if index == 3 and condition == "full_pack":
                record.update(status="TRANSPORT_ERROR", error={"type": "TimeoutError"},
                              finish_reason=None, usage=None)
                record.pop("response")
            requests.append(row)
            records.append(record)
    (run_dir / "requests.jsonl").write_bytes(b"".join(report._json_bytes(r) for r in requests))
    (run_dir / "responses.jsonl").write_bytes(b"".join(report._json_bytes(r) for r in records))
    graded = {"model_results": grade_expanded_outputs(requests, [r for r in records if "response" in r])}
    (run_dir / "graded.json").write_bytes(report._json_bytes(graded))
    manifest = {"track": "synthetic_expansion", "protocol": "synthetic_grounding_expansion_v1",
        "code_revision": "frozen-code-sha", "requested_model": "frozen-model",
        "endpoint": "http://127.0.0.1/v1", "started_at": "2026-10-13T00:00:00Z",
        "finished_at": "2026-10-13T00:10:00Z", "decoding": {"max_tokens": 128},
        "request_count": 20, "received_count": 19, "missing_count": 1, "error_count": 1,
        "malformed_count": 1, "status": "INCOMPLETE"}
    _seal(run_dir, manifest)
    return run_dir


def test_frozen_report_pairs_failures_and_operational_evidence(tmp_path, monkeypatch):
    run_dir = _frozen_run(tmp_path)
    before = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    monkeypatch.setattr("eval.synthetic_grounding.load_families", lambda: pytest.fail("mutable fixture read"))
    summary = report.prepare_report(run_dir)
    assert {p.name: p.read_bytes() for p in run_dir.iterdir()} == before
    assert summary["status"] == "INCOMPLETE"
    assert summary["counts"]["malformed_count"] == summary["counts"]["missing_count"] == 1
    assert summary["paired_vs_original"]["surface_only"]["helpful_flip"] == 1
    assert summary["paired_vs_original"]["both"]["harmful_flip"] == 1
    assert summary["paired_vs_original"]["full_pack"]["missing_pairs"] == 1
    routing = summary["expanded_diagnostics"]["both"]["by_task"]["structured_routing"]
    assert routing["wrong_ids"] == routing["guard_rejections"] == 1
    assert routing["accepted_unauthorized_ids"] == 0
    op = summary["operational"]["full_pack"]
    assert op["latency_ms"]["observations"] == 4
    assert op["latency_ms"]["p50"] == 254
    assert op["actual_usage"]["total_tokens"]["observations"] == 3
    assert op["actual_usage"]["total_tokens"]["total"] == 345
    markdown = report.render_markdown(summary)
    assert "AI synthetic" in markdown and "128 tokens" in markdown
    assert "separate from the isolated 2×2" in markdown
    assert "family macro is descriptive over observed outputs" in markdown
    assert "correct paraphrases" in markdown


@pytest.mark.parametrize("artifact", report.ARTIFACTS)
def test_report_rejects_unsealed_artifact_changes(tmp_path, artifact):
    run_dir = _frozen_run(tmp_path)
    with (run_dir / artifact).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        report.prepare_report(run_dir)


def test_report_rejects_changed_manifest_and_other_track(tmp_path):
    run_dir = _frozen_run(tmp_path)
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["requested_model"] = "changed-model"
    manifest_path.write_bytes(report._json_bytes(manifest))
    with pytest.raises(ValueError, match="invalid manifest seal"):
        report.prepare_report(run_dir)
    manifest["track"] = "contract_probe"
    _seal(run_dir, manifest)
    with pytest.raises(ValueError, match="requires the synthetic_expansion track"):
        report.prepare_report(run_dir)


def test_report_rejects_resealed_inconsistent_grade(tmp_path):
    run_dir = _frozen_run(tmp_path)
    graded_path = run_dir / "graded.json"
    graded = json.loads(graded_path.read_text())
    graded["model_results"]["expanded_diagnostics"]["original"]["overall"]["success"] += 1
    graded_path.write_bytes(report._json_bytes(graded))
    _seal(run_dir, json.loads((run_dir / "run_manifest.json").read_text()))
    with pytest.raises(ValueError, match="success count disagrees"):
        report.prepare_report(run_dir)


def test_report_cli_writes_summary_and_markdown_from_verified_run(tmp_path, monkeypatch):
    run_dir = _frozen_run(tmp_path)
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir)])
    assert report.main() == 0
    assert json.loads((run_dir / "summary.json").read_text())["counts"]["request_count"] == 20
    assert (run_dir / "RESULTS.md").read_text().startswith("# Expanded synthetic grounding experiment")

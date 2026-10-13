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
    assert summary["semantic_oracle_ceiling"]["success_ceiling"] == 4
    assert summary["observed_semantic_oracle_ceiling"]["full_pack"]["planned"] == 3
    assert summary["contextual_collision_shortcuts"]["documents"] == 0
    assert "Policy-compliant null" in markdown and "Text-blind candidate bias" in markdown


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


def test_supplement_cli_preserves_original_reports_seals_and_experiment_revision(tmp_path, monkeypatch):
    run_dir = _frozen_run(tmp_path)
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir)])
    assert report.main() == 0
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir),
                                    "--supplement", "--analysis-revision", "analysis-code-sha"])
    assert report.main() == 0
    assert {name: (run_dir / name).read_bytes() for name in before} == before
    assert {path.name for path in run_dir.iterdir()} - set(before) == {
        "reviewed_summary.json", "REVIEWED_RESULTS.md"}
    summary = json.loads((run_dir / "reviewed_summary.json").read_text())
    assert summary["report_mode"] == "supplement"
    assert summary["code_revision"] == "frozen-code-sha"
    assert summary["reporting_code_revision"] == "analysis-code-sha"
    markdown = (run_dir / "REVIEWED_RESULTS.md").read_text()
    assert "Experiment code revision: `frozen-code-sha`" in markdown
    assert "reporting code revision: `analysis-code-sha`" in markdown
    assert "[summary](reviewed_summary.json)" in markdown
    assert "[summary](summary.json)" not in markdown


@pytest.mark.parametrize("flags", [
    ["--supplement"], ["--supplement", "--analysis-revision", " "],
    ["--analysis-revision", "unused-code-sha"],
])
def test_supplement_cli_requires_explicit_reporting_revision(tmp_path, monkeypatch, flags):
    run_dir = _frozen_run(tmp_path)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}
    monkeypatch.setattr("sys.argv", ["report", "--run-dir", str(run_dir), *flags])
    with pytest.raises(SystemExit) as exc:
        report.main()
    assert exc.value.code == 2
    assert {path.name: path.read_bytes() for path in run_dir.iterdir()} == before


def _case(case_id, task, expected="global:main", *, authorized=False):
    pack = {"resolved_terms": [], "ambiguous_mentions": []}
    if authorized:
        pack["resolved_terms"] = [{"entity_id": expected, "resolution": {"degraded": False},
                                   "mentions": [{"surface": "별칭"}]}]
    return {"case_id": case_id + ":" + task, "document_id": case_id,
            "family_id": "family-" + case_id, "task": task, "condition": "original",
            "stratum": "contextual_collision", "target_surface": "별칭", "pack": pack,
            "expected_entity_id": expected, "expected_answer": "정의-" + expected,
            "cards": []}


def test_semantic_oracle_is_capped_by_guard_without_relabeling_gold():
    rows = [_case("blocked", "document_qa"), _case("blocked", "structured_routing"),
            _case("allowed", "document_qa", authorized=True),
            _case("allowed", "structured_routing", authorized=True)]
    rows += [{**_case("nil", "structured_routing"), "expected_entity_id": None,
              "expected_answer": None}]
    before = deepcopy(rows)
    ceiling = report._oracle_ceiling(rows)
    assert rows == before
    assert ceiling["by_task"]["document_qa"]["success_ceiling"] == 2
    assert ceiling["by_task"]["structured_routing"]["success_ceiling"] == 2
    assert ceiling["success_ceiling"] == 4 and ceiling["planned"] == 5
    assert ceiling["rate"] == .8
    assert ceiling["family_macro_ceiling"] == pytest.approx((.5 + 1 + 1) / 3)
    assert ceiling["guard_blocked_gold_case_ids"] == ["blocked:structured_routing"]


def test_corpus_only_export_uses_original_requests_without_model_outputs():
    original = _case("blocked", "structured_routing")
    other = {**_case("not-counted", "structured_routing", authorized=True), "condition": "both"}
    diagnostics = report.analyze_frozen_requests(iter([original, other]))
    assert diagnostics["semantic_oracle_ceiling"]["planned"] == 1
    assert diagnostics["semantic_oracle_ceiling"]["success_ceiling"] == 0
    assert diagnostics["contextual_collision_shortcuts"]["documents"] == 1
    with pytest.raises(ValueError, match="original-condition"):
        report.analyze_frozen_requests([other])


def test_policy_null_and_avoidable_null_exclude_missing_and_malformed():
    rows = [_case(name, "structured_routing", authorized=name == "allowed")
            for name in ("blocked", "allowed", "malformed", "missing")]
    records = {(row["case_id"], "original"): {
        "status": "RECEIVED", "response": {"entity_id": None}}
        for row in rows if not row["case_id"].startswith("missing:")}
    records[("malformed:structured_routing", "original")] = {
        "status": "MALFORMED", "response": {"entity_id": []}}
    result = report._routing_abstentions(rows, records, "original")
    assert result == {"positive_planned": 4, "positive_observed": 3,
        "gold_guard_authorized": 1, "gold_guard_blocked": 3,
        "policy_compliant_null_on_guard_blocked_positive": 1,
        "avoidable_null_on_guard_authorized_positive": 1,
        "missing_positive": 1, "malformed_positive": 1}


def test_text_blind_suffix_and_order_baselines_keep_guard_distinct():
    rows = []
    for name, ids, expected, authorized in (
            ("suffix", ["global:f.main", "global:f.rival"], "global:f.rival", False),
            ("reverse", ["global:g.rival", "global:g.main"], "global:g.main", True),
            ("opaque", ["global:e_914", "global:e_626"], "global:e_914", True)):
        for task in ("document_qa", "structured_routing"):
            row = _case(name, task, expected, authorized=authorized)
            row["cards"] = [{"entity_id": eid, "definition": "정의-" + eid} for eid in ids]
            if name == "suffix":
                row["cards"].append({"entity_id": ids[0], "definition": "later repeated card"})
            if name == "opaque":
                row.update(corpus_version="v2", contrast_pair_id="pair-opaque", contrast_member="contrast")
            rows.append(row)
    result = report._shortcut_diagnostics(rows)
    assert result["documents"] == 3 and result["uses_model_outputs"] is False
    assert result["original_target_candidate_positions"] == {"1": 1, "2": 2}
    suffix = result["rules"]["non_main_suffix"]
    assert suffix["support"] == 2
    assert suffix["qa_exact_matches"] == suffix["semantic_id_matches"] == 1
    assert suffix["semantic_id_accuracy_all_cases"] == pytest.approx(1 / 3)
    assert suffix["guard_accepted_semantic_id_matches"] == 0
    assert suffix["guard_rejected_nonnull_ids"] == 2
    assert result["rules"]["first_candidate"]["qa_exact_matches"] == 1
    assert result["rules"]["last_candidate"]["qa_exact_matches"] == 2
    assert result["rules"]["last_candidate"]["guard_accepted_semantic_id_matches"] == 1
    case = next(case for case in result["cases"] if case["document_id"] == "opaque")
    assert case["contrast_pair_id"] == "pair-opaque" and case["contrast_member"] == "contrast"
    assert case["selected_ids"]["non_main_suffix"] is None
    assert case["original_target_candidate_position"] == 1


@pytest.mark.parametrize("track,protocol,valid", [
    ("synthetic_expansion_v2", "synthetic_grounding_expansion_v2", True),
    ("synthetic_expansion_v2", "synthetic_grounding_expansion_v1", False),
    ("synthetic_expansion", "synthetic_grounding_expansion_v2", False),
])
def test_report_accepts_only_matching_versioned_protocols(tmp_path, track, protocol, valid):
    run_dir = _frozen_run(tmp_path)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    manifest.update(track=track, protocol=protocol)
    _seal(run_dir, manifest)
    if valid:
        summary = report.prepare_report(run_dir)
        assert summary["track"] == track and summary["protocol"] == protocol
    else:
        with pytest.raises(ValueError, match="matching v2 track/protocol"):
            report.prepare_report(run_dir)

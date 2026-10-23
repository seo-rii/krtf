"""Publish outcomes without private payloads or duplicated recovery calls."""
import gzip
import hashlib
import json
import shutil

import pytest

from eval.export_backup_evidence import export, observation, verified_stage
from eval.hf_qa import canonical
from eval.report_followup_llm import prepare_report
from test_followup_llm import envelope, execute


def identity(manifest, summary):
    return {**{key: manifest[key] for key in (
        "artifact_sha256", "request_count", "request_corpus_sha256",
        "frozen_request_file_sha256", "code_revision", "requested_model", "experiment")},
        "source_manifest_seal_sha256": manifest["seal_sha256"], "counts": summary["counts"]}


def test_projection_preserves_clusters_and_tri_state_without_payloads():
    request = {"case_id": "private-case", "family_id": "private-family", "system": "secret-system",
        "user": "secret-prompt", "source_text": "secret-source", "expected_answers": ["secret-gold"],
        "condition": "baseline", "human_verified": False,
        "prompt_tokens": {"gemma12b": 100, "qwen27b": 90},
        "source_tokens": {"gemma12b": 50, "qwen27b": 40},
        "prompt_budget_utilization": {"gemma12b": .5, "qwen27b": .4},
        "pipeline_trace": {"exact_core_detected": False, "gold_in_candidates": None,
                           "candidate_entity_ids": [], "resolved_entity_id": None}}
    grade = {"correct": False, "malformed": True, "guard_violations": [{"detail": "secret-detail"}],
             "server_added_segments": ["secret-segment"]}
    record = {"latency_ms": 1.5, "finish_reason": "length", "raw_text": "secret-output",
              "usage": {"completion_tokens": 768, "total_tokens": 900}}
    row = observation(request, grade, record)
    serialized = json.dumps(row)
    assert "secret" not in serialized and "private-" not in serialized
    assert row["pipeline"]["gold_in_candidates"] is None
    assert row["human_verified"] is False and "independent_validation" not in row
    assert row["malformed"] is True and row["usage"]["completion_tokens"] == 768
    assert row["prepared_prompt_tokens"] == {"gemma12b": 100, "qwen27b": 90}
    assert row["prepared_source_tokens"]["qwen27b"] == 40
    assert row["prepared_prompt_budget_utilization"]["gemma12b"] == .5
    assert row["server_added_segment_count"] == row["guard_violations_count"] == 1
    repeated = observation(request | {"condition": "pack"}, grade, record)
    assert repeated["family_id_sha256"] == row["family_id_sha256"]
    assert repeated["case_id_sha256"] == row["case_id_sha256"]


def test_private_string_in_typed_metric_is_rejected():
    with pytest.raises(ValueError, match="boolean"):
        observation({"system": "s", "user": "u"}, {"correct": "private-answer"}, None)


def test_manifest_and_artifact_tampering_are_rejected(tmp_path, monkeypatch):
    _, root, manifest, _ = execute(tmp_path, monkeypatch, data=envelope("retrieval"))
    summary = prepare_report(root)
    pin = identity(manifest, summary)
    _, rows = verified_stage(root, pin, summary)
    assert len(rows) == 4 and all(row["exact_match"] for row in rows)
    with pytest.raises(ValueError, match="published manifest"):
        verified_stage(root, pin | {"code_revision": "changed"}, summary)
    with (root / "graded.json").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="artifact hash"):
        verified_stage(root, pin, summary)


def test_export_deduplicates_recovery_aliases_and_checks_every_reference(tmp_path, monkeypatch):
    _, root, manifest, _ = execute(tmp_path, monkeypatch, data=envelope("retrieval"))
    summary = prepare_report(root)
    pin = identity(manifest, summary)
    backup, repo = tmp_path / "backup", tmp_path / "repo"
    target = backup / "data/data/one/mil_llm_refusal/ktrf/experiments/run/results/stage"
    shutil.copytree(root, target)
    for name in ("original", "recovery"):
        folder = repo / "reports" / name / "stage"
        folder.mkdir(parents=True)
        (folder / "manifest_identity.json").write_bytes(canonical(pin))
        (folder / "summary.json").write_bytes(canonical(summary))
    metadata = backup / "metadata"
    metadata.mkdir()
    (metadata / "retained-manifest.json").write_bytes(canonical({"fixture": True}))
    (metadata / "public-model-reproduction.json").write_bytes(canonical([]))
    (metadata / "shared-runtime-and-model-identities.json").write_bytes(canonical({
        "platform": "test", "system_python": "test", "shared_model_files": [],
        "runtime_packages": {"/home/private/.venvs/vllm/bin/python": {
            "exit_code": 0, "packages": [{"name": "vllm", "version": "fixture"}]}}}))
    out = tmp_path / "public"
    result = export(backup, repo, out)
    assert result["stage_count"] == 1 and result["planned_observations"] == 4
    assert result["reused_report_references_deduplicated"] == 1
    stage = result["stages"][0]
    data = (out / stage["file"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == stage["sha256"]
    rows = [json.loads(line) for line in gzip.decompress(data).splitlines()]
    assert len(rows) == 4 and all(row["observed"] for row in rows)
    assert all(b"authored-private" not in p.read_bytes() for p in out.rglob("*.json"))
    altered = repo / "reports/recovery/stage/manifest_identity.json"
    altered.write_bytes(canonical(pin | {"code_revision": "changed"}))
    with pytest.raises(ValueError, match="published manifest"):
        export(backup, repo, tmp_path / "invalid-public")
    assert not (tmp_path / "invalid-public").exists()

"""Reuse one sealed Qwen stage without changing its original environment."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval import collect_followup_queue as collector
from eval import run_followup_queue as queue
from eval.hf_qa import canonical
from eval.run_followup_llm import ARTIFACTS


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def recovery_inputs(tmp_path):
    from eval import recover_followup_queue as recovery

    reports = Path(__file__).resolve().parents[1] / "reports/closure_queue_20261023"
    original = json.loads((reports / "queue_plan.json").read_text())
    original_terminal = json.loads((reports / "queue_status.json").read_text())
    plan = deepcopy(original)
    run_root = tmp_path / "remote/recovery"
    plan.update(run_id="closure_missing_gemma_recovery", run_root=str(run_root), port=18123,
                status_path=str(run_root / "logs/queue.status.json"),
                log_dir=str(run_root / "logs"), log_path=str(run_root / "logs/queue.log"),
                driver_code_revision="b" * 40)
    plan["models"]["gemma12b"]["gpu_memory_utilization"] = .75
    plan["launch_environment"] = {"TMPDIR": str(run_root / "tmp"),
                                  "VLLM_RPC_BASE_PATH": str(tmp_path / "ipc")}
    plan["startup_preflight"] = {"path": str(run_root / "logs/ipc.status.json"),
                                 "sha256": "d" * 64}
    origin_plan_pin = write_json(tmp_path / "origin/queue_plan.json", original)
    origin_status_pin = write_json(tmp_path / "origin/queue_status.json", original_terminal)
    plan["retry_from"] = {"plan_path": origin_plan_pin["path"],
                          "plan_sha256": origin_plan_pin["sha256"],
                          "status_path": origin_status_pin["path"],
                          "status_sha256": origin_status_pin["sha256"]}
    original_collector = {"run_id": original["run_id"], "pid": 111,
        "status": "FAILED", "phase": "FINISHED", "exit_code": 1,
        "publication_complete": True, "verified_reports": [original["stages"][1]["id"]],
        "missing_stages": [original["stages"][0]["id"]], "remote": original_terminal}
    original_exit = {"pid": 222, "child_pid": 111, "status": "FAILED", "exit_code": 1}
    status_pin = write_json(tmp_path / "origin/collector.status.json", original_collector)
    exit_pin = write_json(tmp_path / "origin/collector.exit.json", original_exit)
    artifact_bytes = {name: canonical({"fixture": name}) for name in (
        *ARTIFACTS, "run_manifest.json", "environment.json", "summary.json")}
    specification = {"kind": "ktrf_closure_missing_stage_recovery_v1",
        "driver_code_revision": plan["driver_code_revision"],
        "driver_source": str(tmp_path / "driver"),
        "driver_source_archive": str(tmp_path / "driver.tar.gz"),
        "driver_archive_sha256": "c" * 64,
        "original_collector_status": status_pin, "original_collector_exit": exit_pin,
        "reused_stage_artifacts_sha256": {name: hashlib.sha256(value).hexdigest()
                                           for name, value in artifact_bytes.items()},
        "ipc_dir": str(tmp_path / "ipc")}
    spec_pin = write_json(tmp_path / "recovery_spec.json", specification)
    context = recovery.validate_recovery_origin(plan, original, original_terminal)
    terminal = {"kind": plan["kind"], "run_id": plan["run_id"],
        "code_revision": plan["code_revision"], "driver_code_revision": plan["driver_code_revision"],
        "driver_archive_sha256": specification["driver_archive_sha256"],
        "retry_from": plan["retry_from"],
        "recovery_spec_sha256": spec_pin["sha256"],
        "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
        "status": "COMPLETE", "phase": "FINISHED", "exit_code": 0,
        "stages": [{**original_terminal["stages"][1], "id": plan["stages"][0]["id"]},
                   recovery.reused_stage_state(context)]}
    repo = tmp_path / "repo"
    (repo / "reports").mkdir(parents=True)
    (repo / "eval/out").mkdir(parents=True)
    config = {"plan": plan, "recovery_spec": spec_pin, "repo": str(repo),
        "private_dir": "eval/out/recovery", "report_dir": "reports/recovery",
        "local_status": str(tmp_path / "collector.status.json"),
        "workspace": str(tmp_path), "staging_id": "recovery", "host": "fixture-host"}
    private = tmp_path / "copied"
    private.mkdir()

    def copy(source, target):
        target.write_bytes(Path(source).read_bytes())

    return SimpleNamespace(plan=plan, original=original, original_terminal=original_terminal,
        terminal=terminal, specification=specification, config=config, private=private,
        copy=copy, artifact_bytes=artifact_bytes)


def test_recovery_provenance_binds_exact_origin_and_reused_stage(recovery_inputs):
    item = recovery_inputs
    context = collector.collect_recovery_provenance(
        item.plan, item.terminal, item.config, item.private, item.copy)
    report = context["overview"]
    assert report["new_generation_requests"] == report["reused_generation_requests"] == 480
    assert report["inference_policy_changed"] is False
    assert report["runtime_change"] == {"model_key": "gemma12b", "setting": "gpu_memory_utilization",
                                        "before": .45, "after": .75}
    for stage, result in zip(item.plan["stages"], item.terminal["stages"], strict=True):
        source, original_stage, source_plan = collector.stage_collection_source(
            item.plan, stage, result, context)
        if stage["model_key"] == "qwen27b":
            assert source_plan == item.original
            assert source_plan != item.plan
            assert source == str(Path(item.original["run_root"]) / "results" / stage["id"])
            assert original_stage == item.original["stages"][1]
        else:
            assert source_plan is item.plan
            assert source == str(Path(item.plan["run_root"]) / "results" / stage["id"])


@pytest.mark.parametrize("pin_name", ["plan_path", "status_path"])
def test_recovery_rejects_origin_file_hash_tampering(recovery_inputs, pin_name):
    item = recovery_inputs
    path = Path(item.plan["retry_from"][pin_name])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="frozen hash"):
        collector.collect_recovery_provenance(
            item.plan, item.terminal, item.config, item.private, item.copy)


@pytest.mark.parametrize("mutation", [
    lambda item: item.config.pop("recovery_spec"),
    lambda item: item.config["recovery_spec"].update(sha256="0" * 64),
    lambda item: item.terminal.update(recovery_spec_sha256="0" * 64),
    lambda item: item.terminal.update(driver_code_revision="0" * 40),
    lambda item: item.terminal.update(driver_archive_sha256="0" * 64),
    lambda item: item.terminal.update(retry_from={}),
    lambda item: item.terminal["stages"][1]["reused_from"].update(result_path="/foreign/results"),
    lambda item: item.terminal["stages"][1].update(received_count=479),
    lambda item: item.terminal["stages"][0].update(reused_from={"run_id": "foreign"}),
])
def test_recovery_rejects_unpinned_or_foreign_reuse(recovery_inputs, mutation):
    item = recovery_inputs
    mutation(item)
    with pytest.raises(ValueError):
        collector.collect_recovery_provenance(
            item.plan, item.terminal, item.config, item.private, item.copy)


@pytest.mark.parametrize("field", ["original_collector_status", "original_collector_exit"])
def test_recovery_rejects_unpublished_or_unpinned_collector(recovery_inputs, field):
    item = recovery_inputs
    pin = item.specification[field]
    source = Path(pin["path"])
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="frozen hash"):
        collector.collect_recovery_provenance(
            item.plan, item.terminal, item.config, item.private, item.copy)


@pytest.mark.parametrize("field,mutation", [
    ("original_collector_status", lambda value: value.update(publication_complete=False)),
    ("original_collector_status", lambda value: value.update(verified_reports=[])),
    ("original_collector_status", lambda value: value.update(status="COMPLETE", exit_code=0)),
    ("original_collector_exit", lambda value: value.update(child_pid=999)),
])
def test_recovery_rejects_semantically_invalid_publication_even_when_repinned(
        recovery_inputs, field, mutation):
    item = recovery_inputs
    pin = item.specification[field]
    value = json.loads(Path(pin["path"]).read_text())
    mutation(value)
    item.specification[field] = write_json(Path(pin["path"]), value)
    item.config["recovery_spec"] = write_json(
        Path(item.config["recovery_spec"]["path"]), item.specification)
    item.terminal["recovery_spec_sha256"] = item.config["recovery_spec"]["sha256"]
    with pytest.raises(ValueError, match="fully collected"):
        collector.collect_recovery_provenance(
            item.plan, item.terminal, item.config, item.private, item.copy)


def test_original_environment_cannot_be_relabelled_as_new_queue(recovery_inputs, monkeypatch):
    item = recovery_inputs
    root = item.private
    stage = item.original["stages"][1]
    summary = {"counts": {"received_count": 480, "missing_count": 0,
                           "error_count": 0, "malformed_count": 0},
               "decoding": {"seed": 0}, "schema_transport": "json_schema"}
    manifest = {"code_revision": item.original["code_revision"], "experiment": stage["experiment"],
        "request_count": 480, "request_corpus_sha256": stage["requests_sha256"],
        "frozen_request_file_sha256": stage["envelope_sha256"],
        "requested_model": item.original["models"]["qwen27b"]["served_name"],
        "seal_sha256": "a" * 64, "artifact_sha256": {name: "b" * 64 for name in ARTIFACTS}}
    environment = {"code_revision": item.original["code_revision"],
        "source_archive_sha256": item.original["archive_sha256"],
        "queue_plan_sha256": hashlib.sha256(canonical(item.original)).hexdigest()}
    for name, value in (("run_manifest.json", manifest), ("environment.json", environment),
                        ("summary.json", summary)):
        write_json(root / name, value)
    from eval import report_extended_suite
    monkeypatch.setattr(report_extended_suite, "prepare_report", lambda path: summary)
    assert collector.verify_stage(root, stage, item.original)[2] == environment
    with pytest.raises(ValueError, match="environment differs"):
        collector.verify_stage(root, stage, item.plan)


def test_normal_collector_rejects_unpinned_reuse_before_stage_copy(tmp_path):
    plan = {"run_root": str(tmp_path), "stages": [{"id": "first", "model_key": "gemma12b"}]}
    stage = plan["stages"][0]
    terminal = {"stages": [{"reused_from": {"run_id": "foreign"}}]}
    with pytest.raises(ValueError, match="pinned recovery"):
        collector.collect_recovery_provenance(plan, terminal, {}, tmp_path,
                                              lambda *args: pytest.fail("must not copy"))
    with pytest.raises(ValueError, match="unpinned"):
        collector.stage_collection_source(plan, stage, terminal["stages"][0], None)
    assert collector.collect_recovery_provenance(
        plan, {"stages": [{}]}, {}, tmp_path, lambda *args: pytest.fail("must not copy")) is None
    assert collector.stage_collection_source(plan, stage, {}, None) == (
        str(tmp_path / "results/first"), stage, plan)


@pytest.mark.parametrize("failure", [None, "qwen_raw", "original_gemma"])
def test_collector_reuses_bytes_and_original_plan_without_new_qwen_inference(
        recovery_inputs, monkeypatch, failure):
    item = recovery_inputs
    plan = item.plan
    reports = Path(__file__).resolve().parents[1] / "reports/closure_queue_20261023"
    actions, verified_plans, copied = [], [], []
    original_qwen = str(Path(item.original["run_root"]) / "results" / plan["stages"][1]["id"])

    def check_output(command, **kwargs):
        if command[0] == "ssh":
            if failure == "original_gemma" and "os.path.lexists" in command[-1]:
                raise collector.subprocess.CalledProcessError(1, command)
            return json.dumps(item.terminal)
        if command[:3] == ["git", "branch", "--show-current"]:
            return "main\n"
        if command[:2] == ["git", "rev-parse"]:
            return plan["code_revision"] + "\n"
        raise AssertionError(command)

    def run(command, **kwargs):
        actions.append(command)
        if command[0] == "scp":
            source, target = command[-2].split(":", 1)[1], Path(command[-1])
            copied.append(source)
            proof_name = next((name for name, spec in plan["proofs"].items()
                               if spec["path"] == source), None)
            if proof_name:
                target.write_bytes((reports / (proof_name + "_proof.json")).read_bytes())
            elif source.startswith(original_qwen + "/"):
                name = Path(source).name
                value = item.artifact_bytes[name]
                target.write_bytes(value + (b" " if failure == "qwen_raw" and name == "responses.jsonl" else b""))
            elif source.startswith(str(Path(plan["run_root"]) / "results") + "/"):
                target.write_text("{}")
            else:
                target.write_bytes(Path(source).read_bytes())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(collector.subprocess, "check_output", check_output)
    monkeypatch.setattr(collector.subprocess, "run", run)

    def verify(root, stage, source_plan):
        verified_plans.append((stage["model_key"], source_plan))
        return {"counts": {"received_count": 480, "missing_count": 0,
                           "error_count": 0, "malformed_count": 0}, "status": "COMPLETE"}, {}, {}

    monkeypatch.setattr(collector, "verify_stage", verify)
    monkeypatch.setattr(collector, "compare_models", lambda *args: {})
    from eval import report_extended_suite
    monkeypatch.setattr(report_extended_suite, "render_markdown", lambda summary: "# Verified\n")
    result = collector.collect(item.config)
    assert result == int(failure is not None)
    public = Path(item.config["repo"]) / item.config["report_dir"]
    if failure is not None:
        assert verified_plans == ([] if failure == "original_gemma" else [("gemma12b", plan)])
        assert not public.exists()
        assert not any(command[:2] == ["git", "push"] for command in actions)
    else:
        assert verified_plans == [("gemma12b", plan), ("qwen27b", item.original)]
        summary = json.loads((public / "summary.json").read_text())
        assert summary["new_generation_requests"] == summary["reused_generation_requests"] == 480
        assert "480 reused Qwen requests" in (public / "RESULTS.md").read_text()
        private = Path(item.config["repo"]) / item.config["private_dir"] / plan["stages"][1]["id"]
        assert all((private / name).read_bytes() == value for name, value in item.artifact_bytes.items())
        for name in ("summary.json", "environment.json"):
            assert (public / plan["stages"][1]["id"] / name).read_bytes() == item.artifact_bytes[name]
    assert not any(source.startswith(str(Path(plan["run_root"]) / "results" /
                                            plan["stages"][1]["id"])) for source in copied)

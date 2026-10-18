"""Fail-closed frozen queue inputs, owned runtimes and private publication."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

from eval import collect_followup_queue as collector
from eval import run_followup_queue as queue
from eval.hf_qa import canonical


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


@pytest.fixture
def frozen_plan(tmp_path, monkeypatch):
    source = tmp_path / "source"
    worker = source / "eval/run_followup_queue.py"
    worker.parent.mkdir(parents=True)
    worker.write_bytes(Path(queue.__file__).read_bytes())
    helper = source / "eval/run_followup_llm.py"
    helper.write_text("# frozen dependency\n")
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(worker, arcname="eval/run_followup_queue.py")
        stream.add(helper, arcname="eval/run_followup_llm.py")
    monkeypatch.setattr(queue, "__file__", str(worker))
    models = {}
    for key in ("gemma12b", "qwen27b"):
        model_path = tmp_path / key
        model_path.mkdir()
        write_json(model_path / "config.json", {"authored": True})
        models[key] = {"path": str(model_path), "served_name": key + "-authored", "gpu_memory_utilization": .4}
    rows = {name: [{"authored_index": i} for i in range(count)]
            for name, count in (("retrieval", 512), ("stability", 1536))}
    stages = []
    for experiment, model in queue.ORDER:
        envelope = tmp_path / (experiment + ".json")
        write_json(envelope, {"experiment": experiment})
        stages.append({"id": experiment + "_" + model, "experiment": experiment, "model_key": model,
            "requests_file": str(envelope), "request_count": len(rows[experiment]),
            "envelope_sha256": queue.file_hash(envelope),
            "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows[experiment])).hexdigest()})
    monkeypatch.setattr(queue, "load_request_file", lambda path: (
        rows[Path(path).stem], {"experiment": Path(path).stem}, {"authored": True}))
    revision = "a" * 40
    preparation = {"code_revision": revision, "experiments": {}}
    for stage in stages[:2]:
        exp = stage["experiment"]
        preparation["experiments"][exp] = {key: stage[key] for key in (
            "request_count", "requests_sha256", "envelope_sha256")}
        preparation["experiments"][exp]["models"] = {key: {
            "path": model["path"], "request_count": stage["request_count"],
            "max_prompt_tokens": 8064, "overflow_count": 0} for key, model in models.items()}
    proofs = {}
    for name, value in {"unit": {"exit_code": 0, "code_revision": revision},
        "blind_document": {"exit_code": 0, "code_revision": revision}, "preparation": preparation}.items():
        path = tmp_path / (name + "-proof.json")
        write_json(path, value)
        proofs[name] = {"path": str(path), "sha256": queue.file_hash(path)}
    return {"kind": queue.KIND, "run_id": "authored_queue", "code_revision": revision,
        "source": str(source), "source_archive": str(archive), "archive_sha256": queue.file_hash(archive),
        "stages": stages, "models": models, "proofs": proofs, "port": 18113,
        "resource_wait_seconds": 600, "status_path": str(tmp_path / "queue.status.json"),
        "run_root": str(tmp_path / "runtime"), "python": "/authored/python", "model_python": "/authored/model-python",
        "hf_home": str(tmp_path / "hf-cache")}


def rewrite_proof(plan, name, mutate):
    spec = plan["proofs"][name]
    path = Path(spec["path"])
    proof = json.loads(path.read_text())
    mutate(proof)
    write_json(path, proof)
    spec["sha256"] = queue.file_hash(path)


def test_precheck_verifies_all_frozen_inputs(frozen_plan):
    assert queue.verify_inputs(frozen_plan)["unit"]["exit_code"] == 0


@pytest.mark.parametrize("mutation,message", [
    (lambda p: p["stages"].reverse(), "expected matched"),
    (lambda p: p["stages"][2].update(requests_sha256="0" * 64), "identical frozen"),
    (lambda p: p["stages"][0].update(request_count=511), "128-question matrix"),
    (lambda p: p.update(resource_wait_seconds=0), "resource deadline"),
    (lambda p: p["models"]["gemma12b"].update(gpu_memory_utilization=1), "GPU fraction"),
])
def test_plan_rejects_matrix_or_resource_drift(frozen_plan, mutation, message):
    mutation(frozen_plan)
    with pytest.raises(ValueError, match=message):
        queue.validate_plan(frozen_plan)


@pytest.mark.parametrize("target,message", [("archive", "source archive hash"),
                                           ("worker", "running worker"),
                                           ("dependency", "frozen source file")])
def test_precheck_rejects_source_drift(frozen_plan, target, message):
    path = (Path(frozen_plan["source_archive"]) if target == "archive" else
            Path(frozen_plan["source"]) / ("eval/run_followup_queue.py" if target == "worker" else "eval/run_followup_llm.py"))
    with path.open("ab") as stream:
        stream.write(b"# changed\n")
    with pytest.raises(ValueError, match=message):
        queue.verify_inputs(frozen_plan)


@pytest.mark.parametrize("mutation,message", [
    (lambda p: p.update(code_revision="b" * 40), "frozen code revision"),
    (lambda p: p["experiments"]["retrieval"].update(requests_sha256="0" * 64), "exact frozen corpus"),
    (lambda p: p["experiments"]["stability"]["models"]["qwen27b"].update(overflow_count=1), "tokenizer proof"),
    (lambda p: p["experiments"]["retrieval"]["models"]["gemma12b"].update(max_prompt_tokens=8065), "tokenizer proof"),
    (lambda p: p["experiments"]["stability"]["models"]["qwen27b"].update(path="/different/checkpoint"), "tokenizer proof"),
])
def test_precheck_binds_token_proof_to_matrix_and_checkpoint(frozen_plan, mutation, message):
    rewrite_proof(frozen_plan, "preparation", mutation)
    with pytest.raises(ValueError, match=message):
        queue.verify_inputs(frozen_plan)


def test_precheck_refuses_failed_unit_proof(frozen_plan):
    rewrite_proof(frozen_plan, "unit", lambda p: p.update(exit_code=1))
    with pytest.raises(ValueError, match="successful tests"):
        queue.verify_inputs(frozen_plan)


class OwnedProcess:
    def __init__(self, code=0):
        self.returncode = code

    def poll(self):
        return self.returncode


def mock_runtime(monkeypatch, plan, *, startup_failure=False, failed_stage=None):
    calls, stopped, servers = [], [], []
    monkeypatch.setattr(queue, "verify_inputs", lambda plan: {})
    def start(runtime_plan, model, stage, command, environment, runtime, update):
        if startup_failure and model["served_name"].startswith("gemma"):
            raise RuntimeError("owned model startup failed")
        server = OwnedProcess()
        servers.append(server)
        assert command[command.index("--host") + 1] == "127.0.0.1"
        return server, 50000, "http://127.0.0.1:18113/v1"
    monkeypatch.setattr(queue, "start_model_runtime", start)
    def popen(command, **options):
        out = Path(command[command.index("--out-dir") + 1])
        stage = next(s for s in plan["stages"] if s["id"] == out.name)
        assert out.name not in calls
        calls.append(out.name)
        code = int(out.name == failed_stage)
        manifest = {"request_corpus_sha256": stage["requests_sha256"],
            "frozen_request_file_sha256": stage["envelope_sha256"], "request_count": stage["request_count"],
            "code_revision": plan["code_revision"], "experiment": stage["experiment"],
            "requested_model": plan["models"][stage["model_key"]]["served_name"],
            "received_count": stage["request_count"] - code, "missing_count": 0, "error_count": code,
            "malformed_count": 0}
        write_json(out / "run_manifest.json", manifest)
        return OwnedProcess(code)
    monkeypatch.setattr(queue.subprocess, "Popen", popen)
    monkeypatch.setattr(queue.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    def stop(process):
        assert process is None or isinstance(process, OwnedProcess)
        if process is not None:
            stopped.append(process)
    monkeypatch.setattr(queue, "stop_owned", stop)
    return calls, stopped, servers


def test_queue_reuses_one_owned_runtime_per_model(frozen_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, frozen_plan)
    assert queue.run_queue(frozen_plan) == 0
    assert calls == [s["id"] for s in frozen_plan["stages"]]
    assert len(servers) == 2 and all(server in stopped for server in servers)
    state = json.loads(Path(frozen_plan["status_path"]).read_text())
    assert state["status"] == "COMPLETE"
    assert all(stage["benchmark_started"] for stage in state["stages"])
    with pytest.raises(ValueError, match="exclusive queue status"):
        queue.run_queue(frozen_plan)
    assert len(calls) == 4


def test_api_errors_do_not_skip_later_independent_stages(frozen_plan, monkeypatch):
    failed = frozen_plan["stages"][0]["id"]
    calls, _, _ = mock_runtime(monkeypatch, frozen_plan, failed_stage=failed)
    assert queue.run_queue(frozen_plan) == 1
    assert calls == [s["id"] for s in frozen_plan["stages"]]
    state = json.loads(Path(frozen_plan["status_path"]).read_text())
    assert [s["status"] for s in state["stages"]] == ["FAILED", "COMPLETE", "COMPLETE", "COMPLETE"]


def test_startup_failure_never_launches_benchmark_for_that_model(frozen_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, frozen_plan, startup_failure=True)
    assert queue.run_queue(frozen_plan) == 1
    assert calls == [s["id"] for s in frozen_plan["stages"][2:]]
    assert len(servers) == 1 and servers[0] in stopped
    state = json.loads(Path(frozen_plan["status_path"]).read_text())
    assert all(not s["benchmark_started"] for s in state["stages"][:2])


def test_existing_stage_outputs_are_not_rerun(frozen_plan, monkeypatch):
    first = frozen_plan["stages"][0]["id"]
    (Path(frozen_plan["run_root"]) / "results" / first).mkdir(parents=True)
    calls, _, _ = mock_runtime(monkeypatch, frozen_plan)
    assert queue.run_queue(frozen_plan) == 1
    assert first not in calls


@pytest.fixture
def collect_config(tmp_path, frozen_plan):
    repo = tmp_path / "local-repo"
    (repo / "reports").mkdir(parents=True)
    (repo / "eval/out").mkdir(parents=True)
    return {"plan": frozen_plan, "repo": str(repo), "report_dir": "reports/followup",
        "private_dir": "eval/out/followup", "local_status": str(tmp_path / "collector.status.json"),
        "host": "authored-host", "workspace": str(tmp_path), "staging_id": "authored"}


@pytest.mark.parametrize("path_kind", ["private_escape", "private_symlink", "public_escape", "status_public", "status_private"])
def test_collector_rejects_unsafe_paths_before_network(collect_config, monkeypatch, tmp_path, path_kind):
    config = collect_config
    if path_kind == "private_escape":
        config["private_dir"] = "eval/out/../../private-leak"
    elif path_kind == "private_symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (Path(config["repo"]) / "eval/out/link").symlink_to(outside, target_is_directory=True)
        config["private_dir"] = "eval/out/link/private"
    elif path_kind == "public_escape":
        config["report_dir"] = "reports/../../outside"
    else:
        target = config["report_dir"] if path_kind == "status_public" else config["private_dir"]
        config["local_status"] = str(Path(config["repo"]) / target / "status.json")
    monkeypatch.setattr(collector.subprocess, "check_output", lambda *a, **k: pytest.fail("network not allowed"))
    with pytest.raises(ValueError, match="new public report"):
        collector.collect(config)


def terminal_state(plan):
    return {"kind": plan["kind"], "run_id": plan["run_id"], "code_revision": plan["code_revision"],
        "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(), "phase": "FINISHED", "status": "COMPLETE", "exit_code": 0,
        "stages": [{"id": s["id"], "experiment": s["experiment"], "request_count": s["request_count"],
            "status": "COMPLETE", "exit_code": 0, "benchmark_started": True,
            "benchmark_exit_code": 0, "report_exit_code": 0, "received_count": s["request_count"],
            "missing_count": 0, "error_count": 0, "malformed_count": 0} for s in plan["stages"]]}


def mock_collect_io(config, monkeypatch, *, terminal=None, corrupt_proof=False):
    plan = config["plan"]
    terminal = terminal or terminal_state(plan)
    actions = []
    monkeypatch.setattr(collector.subprocess, "check_output", lambda *a, **k: json.dumps(terminal))
    def run(command, **kwargs):
        actions.append(command)
        if command[0] == "scp":
            source = Path(command[-2].split(":", 1)[1])
            target = Path(command[-1])
            if source.exists():
                target.write_bytes(source.read_bytes() + (b" " if corrupt_proof else b""))
            else:
                target.write_text("{}")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(collector.subprocess, "run", run)
    return actions


@pytest.mark.parametrize("failure", ["proof_hash", "raw_regrade", "terminal_identity"])
def test_collector_fails_before_any_public_writes(collect_config, monkeypatch, failure):
    terminal = terminal_state(collect_config["plan"])
    if failure == "terminal_identity":
        terminal["code_revision"] = "b" * 40
    actions = mock_collect_io(collect_config, monkeypatch, terminal=terminal, corrupt_proof=failure == "proof_hash")
    def reject_raw(*args):
        raise ValueError("raw artifact hash or local regrade mismatch")
    monkeypatch.setattr(collector, "verify_stage", reject_raw)
    assert collector.collect(collect_config) == 1
    assert not (Path(collect_config["repo"]) / collect_config["report_dir"]).exists()
    assert not any(command[:2] in (["git", "add"], ["git", "commit"], ["git", "push"]) for command in actions)
    state = json.loads(Path(collect_config["local_status"]).read_text())
    assert state["status"] == "FAILED" and state["error_type"] == "ValueError"


def test_comparison_rejects_different_frozen_corpora(frozen_plan):
    stages = [s for s in frozen_plan["stages"] if s["experiment"] == "retrieval"]
    summaries = {s["id"]: {"request_corpus_sha256": str(index), "code_revision": "same", "decoding": {}}
                 for index, s in enumerate(stages)}
    with pytest.raises(ValueError, match="identical inputs"):
        collector.compare_models(summaries, frozen_plan)


@pytest.fixture
def combined_plan(frozen_plan, monkeypatch):
    plan = copy.deepcopy(frozen_plan)
    plan["kind"] = queue.COMBINED_KIND
    plan["run_id"] = "authored_combined_queue"
    plan["stages"] = [stage for stage in plan["stages"] if stage["experiment"] == "stability"]
    for stage in plan["stages"]:
        stage.update(id="combined_" + stage["model_key"], experiment="combined")
    del plan["proofs"]["blind_document"]
    rewrite_proof(plan, "preparation", lambda proof: proof.update(
        experiments={"combined": proof["experiments"]["stability"]}))
    rows = [{"authored_index": i} for i in range(1536)]
    monkeypatch.setattr(queue, "load_request_file", lambda path: (
        rows, {"experiment": "combined"}, {"authored": True}))
    return plan


def test_combined_precheck_verifies_matched_matrix_without_blind_proof(combined_plan):
    assert queue.verify_inputs(combined_plan)["unit"]["exit_code"] == 0


@pytest.mark.parametrize("mutation,message", [
    (lambda plan: plan["stages"].reverse(), "expected matched combined"),
    (lambda plan: plan["stages"][0].update(request_count=512), "128-question matrix"),
    (lambda plan: plan["stages"][1].update(envelope_sha256="0" * 64), "identical frozen"),
    (lambda plan: plan["stages"][0].update(experiment="stability"), "expected matched combined"),
    (lambda plan: plan.update(kind=queue.KIND), "expected matched retrieval/stability"),
    (lambda plan: plan["proofs"].pop("preparation"), "tokenizer preparation proofs"),
])
def test_combined_plan_rejects_matrix_or_protocol_drift(combined_plan, mutation, message):
    mutation(combined_plan)
    with pytest.raises(ValueError, match=message):
        queue.validate_plan(combined_plan)


def test_combined_precheck_rejects_different_preparation_corpus(combined_plan):
    rewrite_proof(combined_plan, "preparation", lambda proof:
                  proof["experiments"]["combined"].update(requests_sha256="0" * 64))
    with pytest.raises(ValueError, match="exact frozen corpus"):
        queue.verify_inputs(combined_plan)


def test_combined_queue_runs_two_serial_owned_model_stages(combined_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, combined_plan)
    assert queue.run_queue(combined_plan) == 0
    assert calls == [stage["id"] for stage in combined_plan["stages"]]
    assert len(servers) == 2 and all(server in stopped for server in servers)
    state = json.loads(Path(combined_plan["status_path"]).read_text())
    assert state["kind"] == queue.COMBINED_KIND and state["status"] == "COMPLETE"
    assert state["responses_completed"] == 1536


def test_combined_startup_failure_still_runs_second_model(combined_plan, monkeypatch):
    calls, _, _ = mock_runtime(monkeypatch, combined_plan, startup_failure=True)
    assert queue.run_queue(combined_plan) == 1
    assert calls == [combined_plan["stages"][1]["id"]]
    state = json.loads(Path(combined_plan["status_path"]).read_text())
    assert [stage["status"] for stage in state["stages"]] == ["FAILED", "COMPLETE"]


@pytest.mark.parametrize("external_storage", [False, True])
def test_combined_collector_publishes_only_verified_aggregates(
        collect_config, combined_plan, monkeypatch, tmp_path, external_storage):
    config = {**collect_config, "plan": combined_plan}
    if external_storage:
        storage = tmp_path / "external-private"
        storage.mkdir(mode=0o700)
        logical_run = Path(config["repo"]) / "eval/out/external-run"
        logical_run.symlink_to(storage, target_is_directory=True)
        config.update(private_storage_root=str(storage), private_dir="eval/out/external-run/collected")
    actions = mock_collect_io(config, monkeypatch)
    terminal = terminal_state(combined_plan)

    def check_output(command, **kwargs):
        if command[0] == "ssh":
            return json.dumps(terminal)
        if command[:3] == ["git", "branch", "--show-current"]:
            return "main\n"
        assert command[:2] == ["git", "rev-parse"]
        return combined_plan["code_revision"] + "\n"

    monkeypatch.setattr(collector.subprocess, "check_output", check_output)

    def verify(root, stage, plan):
        summary = {"request_corpus_sha256": stage["requests_sha256"],
            "code_revision": plan["code_revision"], "decoding": {"seed": 0},
            "model": plan["models"][stage["model_key"]]["served_name"], "questions": 128,
            "status": "COMPLETE", "by_variant": {"bm25_pack__json_schema": {
                "positive_exact_rate": 0.5, "article_no_answer_null_rate": 0.9, "malformed": 0}},
            "counts": {"received_count": 1536, "missing_count": 0, "error_count": 0, "malformed_count": 0}}
        return summary, {"verified": True}, {"authored": True}

    monkeypatch.setattr(collector, "verify_stage", verify)
    monkeypatch.setattr(collector, "render_markdown", lambda summary: "# Verified aggregate\n")
    assert collector.collect(config) == 0
    public = Path(config["repo"]) / config["report_dir"]
    summary = json.loads((public / "summary.json").read_text())
    assert summary["kind"] == queue.COMBINED_KIND
    assert summary["planned_generation_requests"] == 3072
    assert set(json.loads((public / "model_comparison.json").read_text())) == {"combined"}
    assert "adaptive combined followup" in " ".join(summary["limitations"])
    assert not (public / "blind_document_proof.json").exists()
    markdown = (public / "RESULTS.md").read_text()
    assert "combined BM25, pack and JSON" in markdown and "blind-document evaluation" not in markdown
    assert sum(command[:2] == ["git", "push"] for command in actions) == 3
    state = json.loads(Path(config["local_status"]).read_text())
    assert state["publication_complete"] and state["exit_code"] == 0
    if external_storage:
        assert (storage / "collected/unit_proof.json").is_file()
        assert not (public / "requests.jsonl").exists()


@pytest.mark.parametrize("failure", [
    "implicit_redirect", "old_queue", "outside_storage", "logical_escape", "storage_root_output", "existing_output",
])
def test_external_private_storage_rejects_unauthorized_or_existing_paths(
        collect_config, combined_plan, monkeypatch, tmp_path, failure):
    config = {**collect_config, "plan": combined_plan}
    storage = tmp_path / "external-private"
    storage.mkdir(mode=0o700)
    logical_run = Path(config["repo"]) / "eval/out/external-run"
    logical_run.symlink_to(storage, target_is_directory=True)
    config.update(private_storage_root=str(storage), private_dir="eval/out/external-run/collected")
    if failure == "implicit_redirect":
        del config["private_storage_root"]
    elif failure == "old_queue":
        config["plan"] = collect_config["plan"]
    elif failure == "outside_storage":
        other_storage = tmp_path / "other-private"
        other_storage.mkdir()
        config["private_storage_root"] = str(other_storage)
    elif failure == "logical_escape":
        config["private_dir"] = str(storage / "collected")
    elif failure == "storage_root_output":
        config["private_dir"] = "eval/out/external-run"
    else:
        (storage / "collected").mkdir()
    monkeypatch.setattr(collector.subprocess, "check_output", lambda *a, **k: pytest.fail("network not allowed"))
    with pytest.raises(ValueError, match="paths required|only for combined"):
        collector.collect(config)

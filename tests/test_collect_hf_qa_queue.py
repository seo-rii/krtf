"""Collector ownership and privacy contracts with mocked SSH, SCP and Git."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from eval import collect_hf_qa_queue as collector


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(collector.canonical(value))


def _fixture(tmp_path):
    repo, remote = tmp_path / "repo", tmp_path / "remote"
    repo.mkdir()
    request_blob = collector.canonical({"case_id": "authored", "text": "PRIVATE SOURCE SENTINEL"})
    envelope_blob = collector.canonical({"requests": [json.loads(request_blob)]})
    stages = [{"id": "hf_qa_" + key, "track": "hf_qa", "model_key": key,
               "requests_file": str(remote / "requests.json"), "request_count": 1,
               "requests_sha256": hashlib.sha256(request_blob).hexdigest(),
               "envelope_sha256": hashlib.sha256(envelope_blob).hexdigest()}
              for key in ("gemma12b", "qwen27b")]
    plan = {"schema_version": 5, "stages": stages, "port": 18104, "run_id": "authored-hf-queue",
            "models": {key: {"gpu_memory_utilization": .5, "path": str(remote / key), "served_name": key}
                       for key in ("gemma12b", "qwen27b")},
            "run_root": str(remote), "status_path": str(remote / "status.json"),
            "code_revision": "c" * 40, "source_archive": str(remote / "source.tar"),
            "archive_sha256": "a" * 64, "unit_status": str(remote / "unit.json"),
            "token_status": str(remote / "tokens.json")}
    plan_hash = hashlib.sha256(collector.canonical(plan)).hexdigest()
    terminal = {"run_id": plan["run_id"], "code_revision": plan["code_revision"],
                "plan_sha256": plan_hash, "status": "COMPLETE", "phase": "FINISHED", "exit_code": 0,
                "stages": [{"id": stage["id"], "status": "COMPLETE", "exit_code": 0,
                            "request_count": 1, "received_count": 1, "malformed_count": 0} for stage in stages]}
    _save(Path(plan["unit_status"]), {"exit_code": 0, "code_revision": plan["code_revision"]})
    _save(Path(plan["token_status"]), {
        "exit_code": 0, "code_revision": plan["code_revision"],
        "models": {stage["model_key"]: {"requests_sha256": stage["requests_sha256"], "request_count": 1,
                                       "model_path": plan["models"][stage["model_key"]]["path"],
                                       "max_prompt_tokens": 1000} for stage in stages}})
    summaries = {}
    for stage in stages:
        target = remote / "results" / stage["id"]
        target.mkdir(parents=True)
        (target / "requests.jsonl").write_bytes(request_blob)
        _save(target / "responses.jsonl", {"response": {"answer": "PRIVATE RESPONSE SENTINEL"}})
        _save(target / "graded.json", {"cases": [{"answer": "PRIVATE RESPONSE SENTINEL"}]})
        manifest = {"request_corpus_sha256": stage["requests_sha256"],
                    "frozen_request_file_sha256": stage["envelope_sha256"], "request_count": 1,
                    "received_count": 1, "missing_count": 0, "error_count": 0, "malformed_count": 0,
                    "code_revision": plan["code_revision"], "track": "hf_qa", "protocol": collector.PROTOCOL,
                    "requested_model": stage["model_key"],
                    "artifact_sha256": {name: hashlib.sha256((target / name).read_bytes()).hexdigest()
                                        for name in collector.RAW_ARTIFACTS}}
        manifest["seal_sha256"] = hashlib.sha256(collector.canonical(manifest)).hexdigest()
        _save(target / "run_manifest.json", manifest)
        _save(target / "environment.json", {"code_revision": plan["code_revision"],
              "queue_plan_sha256": plan_hash, "source_archive_sha256": plan["archive_sha256"]})
        summaries[stage["id"]] = {"kind": "aggregate-hf-qa", "requested_model": stage["model_key"],
                                  "counts": {"request_count": 1, "received_count": 1}}
        _save(target / "summary.json", summaries[stage["id"]])
        (target / "RESULTS.md").write_text("PRIVATE REMOTE MARKDOWN SENTINEL")
    config = {"repo": str(repo), "host": "authored-host", "workspace": str(tmp_path),
              "report_dir": "reports/hf-qa-owned", "private_dir": "eval/out/hf-qa-private",
              "local_status": str(tmp_path / "collector-status.json"), "plan": plan,
              "staging_id": "authored-staging-unit"}
    return config, terminal, summaries


def _mocks(monkeypatch, config, terminal, summaries):
    commands, report_calls = [], []

    def prepare(path, *, compare=None):
        path = Path(path)
        report_calls.append((path, None if compare is None else Path(compare)))
        if compare is not None:
            return {"comparison": {"baseline_model": Path(compare).name, "current_model": path.name},
                    "counts": {"paired_questions": 1}}
        return deepcopy(summaries[path.name])

    def module(name):
        assert name == "eval.report_hf_qa"
        return SimpleNamespace(prepare_report=prepare, render_markdown=lambda value: "# Aggregate QA report\n")

    def check_output(command, **kwargs):
        commands.append(command)
        if command[0] == "ssh":
            assert command[-1].startswith("cat ")
            return json.dumps(terminal)
        if command == ["git", "branch", "--show-current"]:
            return "main\n"
        if command[:2] == ["git", "rev-parse"]:
            return "f" * 40 + "\n"
        raise AssertionError(command)

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "scp":
            shutil.copyfile(command[-2].split(":", 1)[1], command[-1])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(collector, "import_module", module)
    monkeypatch.setattr(collector.subprocess, "check_output", check_output)
    monkeypatch.setattr(collector.subprocess, "run", run)
    return commands, report_calls


def test_collector_keeps_raw_artifacts_private_and_commits_only_exact_public_files(tmp_path, monkeypatch):
    config, terminal, summaries = _fixture(tmp_path)
    commands, report_calls = _mocks(monkeypatch, config, terminal, summaries)
    unrelated = Path(config["repo"]) / "already-staged-user-work.txt"
    unrelated.write_text("unrelated active work")
    assert collector.collect(config) == 0
    repo = Path(config["repo"])
    public, private = repo / config["report_dir"], repo / config["private_dir"]
    stages = config["plan"]["stages"]
    assert report_calls == [(private / stage["id"], None) for stage in stages] + [
        (private / stages[1]["id"], private / stages[0]["id"])]
    for stage in stages:
        assert {path.name for path in (public / stage["id"]).iterdir()} == set(collector.PUBLIC_STAGE_FILES)
        for name in collector.RAW_ARTIFACTS:
            assert (private / stage["id"] / name).is_file()
            assert not (public / stage["id"] / name).exists()
            assert (private / stage["id"] / name).stat().st_mode & 0o777 == 0o600
    public_files = [path for path in public.rglob("*") if path.is_file()]
    assert not any("SENTINEL" in path.read_text() for path in public_files)
    assert all(Path(command[-1]).is_relative_to(private) for command in commands if command[0] == "scp")
    commits = [command for command in commands if command[:2] == ["git", "commit"]]
    assert len(commits) == 3 and all("--only" in command for command in commits)
    owned = [name for command in commits for name in command[command.index("--") + 1:]]
    assert set(owned) == {str(path.relative_to(repo)) for path in public_files}
    assert all((repo / name).is_file() for name in owned)  # Exact files, never recursive directory staging.
    first_commit = next(index for index, command in enumerate(commands) if command[:2] == ["git", "commit"])
    assert all(index < first_commit for index, command in enumerate(commands) if command[0] == "scp")
    assert [command for command in commands if command[:2] == ["git", "push"]] == [
        ["git", "push", "origin", "main"]] * 3
    assert commands[-1] == ["python3", "scripts/staging_md.py", "done", "--id", config["staging_id"]]
    assert unrelated.read_text() == "unrelated active work"
    assert json.loads(Path(config["local_status"]).read_text())["status"] == "COMPLETE"


@pytest.mark.parametrize("schema_version", [1, 2, 3, 4, 6, 5.0, None])
def test_collector_rejects_unsupported_schemas_before_network(monkeypatch, schema_version):
    def unexpected(*args, **kwargs):
        pytest.fail("unsupported plans must fail before imports, network or Git")

    monkeypatch.setattr(collector, "import_module", unexpected)
    monkeypatch.setattr(collector.subprocess, "run", unexpected)
    with pytest.raises(ValueError, match="schema_version 5"):
        collector.collect({"plan": {"schema_version": schema_version}})


@pytest.mark.parametrize("payload", [
    {"text": "source"}, {"metrics": [{"raw_text": "response"}]},
    {"declared_protocol": {"question_text": "question"}}, {"metrics": {"cases": []}},
    {"nested": {"source-text": "source"}}, {"messages": [{"content": "source"}]},
    {"expected_answers": ["individual gold"]},
])
def test_public_validator_rejects_nested_raw_payloads(payload):
    with pytest.raises(ValueError, match="raw source/answer"):
        collector.validate_public_json(payload)


def test_public_validator_accepts_aggregate_counts_hashes_and_protocol_descriptions():
    value = {"protocol": collector.PROTOCOL, "counts": {"questions": 12, "no_answer_questions": 3},
             "actual_usage": {"prompt_tokens": {"total": 1234}}, "request_corpus_sha256": "a" * 64,
             "limitations": ["Not an entity-linking benchmark."], "human_verified": True}
    assert collector.validate_public_json(value) is value


def test_collector_refuses_public_path_for_private_source_storage(tmp_path, monkeypatch):
    config, _, _ = _fixture(tmp_path)
    config["private_dir"] = "reports/raw-sources"

    def unexpected(*args, **kwargs):
        pytest.fail("unsafe private paths must fail before network or publication")

    monkeypatch.setattr(collector.subprocess, "run", unexpected)
    with pytest.raises(ValueError, match="ignored repository eval/out"):
        collector.collect(config)


@pytest.mark.parametrize("tamper", ["queue_identity", "artifact_hash", "remote_summary", "public_manifest",
                                   "stage_counts", "stage_status"])
def test_collector_never_publishes_when_terminal_or_local_reverification_fails(tmp_path, monkeypatch, tamper):
    config, terminal, summaries = _fixture(tmp_path)
    stage = config["plan"]["stages"][1]
    remote = Path(config["plan"]["run_root"]) / "results" / stage["id"]
    if tamper == "queue_identity":
        terminal["code_revision"] = "different-revision"
    elif tamper == "artifact_hash":
        (remote / "responses.jsonl").write_text("altered raw response")
    elif tamper == "remote_summary":
        _save(remote / "summary.json", {"counts": {"received_count": 0}})
    elif tamper == "stage_counts":
        terminal["stages"][1]["received_count"] = 0
    elif tamper == "stage_status":
        terminal["stages"][1]["exit_code"] = 1
    else:
        manifest = json.loads((remote / "run_manifest.json").read_text())
        manifest["source_text"] = "PRIVATE SOURCE SENTINEL"
        manifest.pop("seal_sha256")
        manifest["seal_sha256"] = hashlib.sha256(collector.canonical(manifest)).hexdigest()
        _save(remote / "run_manifest.json", manifest)
    commands, _ = _mocks(monkeypatch, config, terminal, summaries)
    assert collector.collect(config) == 1
    assert not (Path(config["repo"]) / config["report_dir"]).exists()
    assert not any(command[:2] in (["git", "commit"], ["git", "push"]) for command in commands)
    status = json.loads(Path(config["local_status"]).read_text())
    assert status["status"] == "FAILED" and status["phase"] == "FINISHED" and status["exit_code"] == 1

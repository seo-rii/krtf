"""Collect schema-5 HF QA runs privately and publish only verified aggregates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

from eval.run_production_queue import canonical, save_json, validate_plan as _validate_run_plan

PROTOCOL = "hf_qa_generation_v1"
RAW_ARTIFACTS = ("requests.jsonl", "responses.jsonl", "graded.json")
PRIVATE_FILES = (*RAW_ARTIFACTS, "run_manifest.json", "environment.json", "summary.json")
PUBLIC_STAGE_FILES = ("summary.json", "RESULTS.md", "run_manifest.json", "environment.json", "job_status.json")
_RAW_KEYS = frozenset({
    "text", "source_text", "source_passages", "document_plaintext", "question", "question_text",
    "answer", "answers", "expected_answer", "expected_answers", "gold_answers", "answer_text", "passage_text",
    "annotation_answers", "ner_annotations", "source_spans", "answer_spans", "answer_passage_spans",
    "selected_text", "system", "user", "messages", "content", "raw_text", "raw_response",
    "response", "responses", "requests", "cases", "stdout", "stderr", "log_tail", "traceback",
})


def validate_run_plan(plan):
    if (not isinstance(plan, dict) or type(plan.get("schema_version")) is not int
            or plan["schema_version"] != 5):
        raise ValueError("HF QA collector requires queue schema_version 5")
    return _validate_run_plan(plan)


def validate_public_json(value):
    """Refuse source/answer payload fields anywhere in an aggregate artifact."""
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower().replace("-", "_") in _RAW_KEYS:
                raise ValueError("public artifact contains a raw source/answer field")
            validate_public_json(child)
    elif isinstance(value, list):
        for child in value:
            validate_public_json(child)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("public artifact must be JSON data")
    return value


def _paths(config):
    repo = Path(config["repo"]).resolve(strict=True)
    public = (repo / config["report_dir"]).resolve()
    private = (repo / config["private_dir"]).resolve()
    if not public.is_relative_to(repo / "reports") or public == repo / "reports":
        raise ValueError("public report_dir must be a new directory inside repository reports")
    if not private.is_relative_to(repo / "eval/out") or private == repo / "eval/out":
        raise ValueError("private_dir must be inside ignored repository eval/out")
    status = Path(config["local_status"]).resolve()
    if status.is_relative_to(public):
        raise ValueError("collector status must stay outside the public report directory")
    if public.exists() or private.exists() or status.exists():
        raise ValueError("collector outputs already exist; refusing to overwrite")
    return repo, public, private, status


def _verify_stage(path, stage, plan):
    manifest = json.loads((path / "run_manifest.json").read_text())
    expected = {"request_corpus_sha256": stage["requests_sha256"],
                "frozen_request_file_sha256": stage["envelope_sha256"],
                "request_count": stage["request_count"], "code_revision": plan["code_revision"],
                "track": "hf_qa", "protocol": PROTOCOL,
                "requested_model": plan["models"][stage["model_key"]]["served_name"]}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("collected manifest differs from the frozen HF QA plan")
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(canonical(unsealed)).hexdigest() != seal:
        raise ValueError("collected manifest seal mismatch")
    hashes = {name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in RAW_ARTIFACTS}
    if manifest.get("artifact_sha256") != hashes or hashes["requests.jsonl"] != stage["requests_sha256"]:
        raise ValueError("collected run artifact hashes differ from sealed artifacts")
    environment = json.loads((path / "environment.json").read_text())
    if any(environment.get(key) != value for key, value in {
            "code_revision": plan["code_revision"], "source_archive_sha256": plan["archive_sha256"],
            "queue_plan_sha256": hashlib.sha256(canonical(plan)).hexdigest()}.items()):
        raise ValueError("collected environment differs from the frozen queue")
    return manifest, environment


def collect(config):
    plan = validate_run_plan(config["plan"])
    validate_public_json(plan)
    repo, public, private, status_path = _paths(config)
    report_module = import_module("eval.report_hf_qa")
    state = {"pid": os.getpid(), "status": "RUNNING", "phase": "WAITING_FOR_QUEUE", "exit_code": None,
             "run_id": plan["run_id"], "started_at": datetime.now(timezone.utc).isoformat(),
             "pushed_commits": [], "remote_status": plan["status_path"]}

    def update(**values):
        state.update(values)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(status_path, state)

    def remote(command):
        return subprocess.check_output(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                        config["host"], command], text=True, timeout=90)

    def copy(remote_path, local_path):
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                        config["host"] + ":" + remote_path, str(local_path)], check=True, timeout=300)
        local_path.chmod(0o600)

    def publish(paths, message):
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
        if branch != "main":
            raise ValueError("active branch changed; reports remain local")
        subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, timeout=180)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=repo, text=True).strip()
        if head != upstream:
            raise ValueError("main differs from origin/main; refusing to publish other commits")
        subprocess.run(["git", "merge-base", "--is-ancestor", plan["code_revision"], "HEAD"], cwd=repo, check=True)
        owned = [str(path.relative_to(repo)) for path in paths]
        subprocess.run(["git", "add", "--", *owned], cwd=repo, check=True)
        subprocess.run(["git", "commit", "--only", "-m", message, "--", *owned], cwd=repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, timeout=180)
        state["pushed_commits"].append(commit)
        update()

    exit_code = 1
    try:
        update()
        subprocess.run(["git", "check-ignore", "-q", "--", str(private.relative_to(repo))], cwd=repo, check=True)
        deadline, consecutive_errors = time.monotonic() + 6 * 86400, 0
        while True:
            try:
                terminal = json.loads(remote("cat " + shlex.quote(plan["status_path"])))
                if not isinstance(terminal, dict):
                    raise ValueError("queue status must be an object")
                update(remote=terminal)
                if terminal.get("exit_code") is not None:
                    if terminal.get("phase") != "FINISHED" or terminal.get("status") not in {"COMPLETE", "FAILED"}:
                        raise ValueError("remote exit status is not terminal")
                    break
                consecutive_errors = 0
            except (subprocess.SubprocessError, ValueError) as error:
                consecutive_errors += 1
                update(monitor_error=type(error).__name__, consecutive_errors=consecutive_errors)
                if consecutive_errors >= 30:
                    raise RuntimeError("remote status unavailable for 30 polls") from error
            if time.monotonic() > deadline:
                raise RuntimeError("collector deadline exceeded; queue remains unverified")
            time.sleep(60)
        if any(terminal.get(key) != expected for key, expected in {
                "run_id": plan["run_id"], "code_revision": plan["code_revision"],
                "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest()}.items()):
            raise ValueError("terminal queue identity differs from the frozen plan")
        if [row["id"] for row in terminal.get("stages", [])] != [stage["id"] for stage in plan["stages"]]:
            raise ValueError("terminal stage identities differ from the frozen plan")
        if (type(terminal["exit_code"]) is not int or
                (terminal["status"] == "COMPLETE") != (terminal["exit_code"] == 0)):
            raise ValueError("terminal queue status disagrees with exit code")
        validate_public_json(terminal)
        update(phase="COLLECTING_PRIVATE_ARTIFACTS")
        private.mkdir(parents=True, mode=0o700, exist_ok=False)
        proofs = {}
        for name, remote_path in (("unit_test_status.json", plan["unit_status"]),
                                  ("token_preflight.json", plan["token_status"])):
            copy(remote_path, private / name)
            proof = json.loads((private / name).read_text())
            if proof.get("exit_code") != 0 or proof.get("code_revision") != plan["code_revision"]:
                raise ValueError("successful preflight proof at frozen code revision required")
            proofs[name] = validate_public_json(proof)
        for stage in plan["stages"]:
            observed = proofs["token_preflight.json"].get("models", {}).get(stage["model_key"], {})
            if (observed.get("requests_sha256") != stage["requests_sha256"] or
                    observed.get("request_count") != stage["request_count"] or
                    observed.get("model_path") != plan["models"][stage["model_key"]]["path"] or
                    type(observed.get("max_prompt_tokens")) is not int or
                    not 0 < observed["max_prompt_tokens"] <= 8192 - 128):
                raise ValueError("tokenizer preflight differs from frozen requests or capacity")
        artifacts, summaries = {}, {}
        for stage, result in zip(plan["stages"], terminal["stages"], strict=True):
            if (type(result.get("exit_code")) is not int or result.get("status") not in {"COMPLETE", "FAILED"}
                    or (result["status"] == "COMPLETE") != (result["exit_code"] == 0)
                    or result.get("request_count") != stage["request_count"]):
                raise ValueError("stage has no verified terminal exit status")
            target = private / stage["id"]
            target.mkdir(mode=0o700)
            remote_out = str(Path(plan["run_root"]) / "results" / stage["id"])
            for name in PRIVATE_FILES:
                copy(remote_out + "/" + name, target / name)
            manifest, environment = _verify_stage(target, stage, plan)
            if any(key in result and result[key] != manifest.get(key) for key in
                   ("request_count", "received_count", "missing_count", "error_count", "malformed_count")):
                raise ValueError("terminal stage counts differ from the sealed manifest")
            summary = report_module.prepare_report(target)
            if json.loads((target / "summary.json").read_text()) != summary:
                raise ValueError("remote summary differs from frozen local regrading")
            artifacts[stage["id"]] = {"summary.json": summary, "run_manifest.json": manifest,
                                      "environment.json": environment, "job_status.json": result}
            for value in artifacts[stage["id"]].values():
                validate_public_json(value)
            summaries[stage["id"]] = summary
        if (terminal["exit_code"] == 0) != all(result["exit_code"] == 0 for result in terminal["stages"]):
            raise ValueError("terminal queue and stage exit codes disagree")
        first, second = plan["stages"]
        comparison = validate_public_json(report_module.prepare_report(
            private / second["id"], compare=private / first["id"]))
        overview = {"schema_version": 5, "run_id": plan["run_id"], "status": terminal["status"],
                    "exit_code": terminal["exit_code"], "code_revision": plan["code_revision"],
                    "track": "hf_qa", "protocol": PROTOCOL, "stages": terminal["stages"],
                    "verified_reports": sorted(summaries), "raw_artifacts_published": False,
                    "limitations": ["TyDiQA Korean QA generation is separate from entity linking and automation.",
                                    "Full source is an information ceiling; retrieved arms use bounded source passages.",
                                    "Model family and size both change; no deployment risk guarantee is established."]}
        public_objects = {"queue_plan.json": plan, "queue_status.json": terminal, **proofs,
                          "summary.json": overview, "comparison.json": comparison}
        for value in public_objects.values():
            validate_public_json(value)
        # No public files or commits exist until every copied run and the paired comparison verify.
        update(phase="WRITING_VERIFIED_AGGREGATES")
        public.mkdir(parents=True, exist_ok=False)
        for stage in plan["stages"]:
            target = public / stage["id"]
            target.mkdir()
            for name, value in artifacts[stage["id"]].items():
                save_json(target / name, value)
            (target / "RESULTS.md").write_text(report_module.render_markdown(summaries[stage["id"]]))
        for name, value in public_objects.items():
            save_json(public / name, value)
        (public / "comparison.md").write_text(report_module.render_markdown(comparison))
        lines = ["# Hugging Face Korean QA generation queue", "",
                 f"Status: **{terminal['status']}**. Exit code: `{terminal['exit_code']}`.", "",
                 "Only verified aggregate reports are published; original source, prompts and responses remain private.", "",
                 "| Stage | Status | Received / planned |", "|---|---|---:|"]
        for stage, result in zip(plan["stages"], terminal["stages"], strict=True):
            lines.append(f"| [{stage['id']}]({stage['id']}/RESULTS.md) | {result['status']} | "
                         f"{result.get('received_count', 0)}/{stage['request_count']} |")
        lines += ["", "[Matched model comparison](comparison.md)", "", *overview["limitations"], ""]
        (public / "RESULTS.md").write_text("\n".join(lines))
        update(phase="PUBLISHING_VERIFIED_AGGREGATES")
        for stage in plan["stages"]:
            publish([public / stage["id"] / name for name in PUBLIC_STAGE_FILES],
                    "test: report HF Korean QA " + stage["id"])
        publish([public / name for name in (*public_objects, "comparison.md", "RESULTS.md")],
                "test: summarize matched HF Korean QA experiments")
        subprocess.run(["python3", "scripts/staging_md.py", "done", "--id", config["staging_id"]],
                       cwd=config["workspace"], check=True)
        exit_code = terminal["exit_code"]
    except Exception as error:
        # Avoid printing raw source snippets from a grader or remote exception into a handoff log.
        update(error={"type": type(error).__name__})
        print(json.dumps({"error_type": type(error).__name__}), flush=True)
    finally:
        update(status="COMPLETE" if exit_code == 0 else "FAILED", phase="FINISHED", exit_code=exit_code,
               finished_at=datetime.now(timezone.utc).isoformat())
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    return collect(json.loads(args.config.read_text()))


if __name__ == "__main__":
    raise SystemExit(main())

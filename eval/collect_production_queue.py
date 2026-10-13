"""Collect a terminal remote production queue, verify it, and push owned reports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

from eval.run_production_queue import canonical, file_hash, save_json
from eval.report_production_grounding import prepare_report, render_markdown


def collect(config):
    repo = Path(config["repository"])
    plan = json.loads(Path(config["plan_path"]).read_text())
    state = {"pid": os.getpid(), "status": "RUNNING", "phase": "WAITING_FOR_QUEUE",
             "exit_code": None, "run_id": plan["run_id"], "started_at": datetime.now(timezone.utc).isoformat(),
             "pushed_commits": [], "remote_status": plan["status_path"]}
    status_path = Path(config["status_path"])
    if status_path.exists():
        raise ValueError("collector status already exists")
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
    def commit_paths(paths, message):
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
        if branch != "main":
            raise ValueError("active branch changed; reports remain local for review")
        subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, timeout=180)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=repo, text=True).strip()
        if head != upstream:
            raise ValueError("main is not synchronized; reports remain local without publishing other commits")
        subprocess.run(["git", "merge-base", "--is-ancestor", plan["code_revision"], "HEAD"], cwd=repo, check=True)
        subprocess.run(["git", "add", "--", *paths], cwd=repo, check=True)
        subprocess.run(["git", "commit", "--only", "-m", message, "--", *paths], cwd=repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, timeout=180)
        state["pushed_commits"].append(commit)
        update()
    exit_code = 1
    try:
        update()
        deadline = time.monotonic() + 6 * 86400
        consecutive_errors = 0
        while True:
            try:
                terminal = json.loads(remote("cat " + shlex.quote(plan["status_path"])))
                consecutive_errors = 0
                update(remote=terminal)
                if terminal.get("exit_code") is not None:
                    if terminal.get("phase") != "FINISHED" or terminal.get("status") not in ("COMPLETE", "FAILED"):
                        raise ValueError("remote exit status is not terminal")
                    break
            except (subprocess.SubprocessError, ValueError) as error:
                consecutive_errors += 1
                update(monitor_error=type(error).__name__, consecutive_errors=consecutive_errors)
                if consecutive_errors >= 30:
                    raise RuntimeError("remote status unavailable for 30 polls") from error
            if time.monotonic() > deadline:
                raise RuntimeError("collector timeout; remote status remains unverified")
            time.sleep(60)
        update(phase="COLLECTING")
        if (terminal.get("run_id") != plan["run_id"]
                or terminal.get("code_revision") != plan["code_revision"]
                or [s["id"] for s in terminal.get("stages", [])] != [s["id"] for s in plan["stages"]]):
            raise ValueError("terminal queue identity differs from the frozen plan")
        if terminal.get("plan_sha256") != hashlib.sha256(canonical(plan)).hexdigest():
            raise ValueError("terminal queue used a different frozen plan")
        root = repo / config["report_dir"]
        root.mkdir(parents=True, exist_ok=False)
        save_json(root / "queue_plan.json", plan)
        save_json(root / "queue_status.json", terminal)
        copy(plan["unit_status"], root / "unit_test_status.json")
        # Read only bounded excerpts after the entire queue and owned runtimes exited.
        (root / "queue_log_tail.txt").write_text(remote("tail -n 50 " + shlex.quote(plan["log_path"])))
        summaries = {}
        for stage, result in zip(plan["stages"], terminal["stages"], strict=True):
            if stage["id"] != result["id"]:
                raise ValueError("queue stage identity mismatch")
            target = root / stage["id"]
            target.mkdir()
            remote_out = str(Path(plan["run_root"]) / "results" / stage["id"])
            code = "from pathlib import Path; import json; p=Path(" + repr(remote_out) + ");print(json.dumps([x.name for x in p.glob('*') if x.is_file()]))"
            names = json.loads(remote("python3 -c " + shlex.quote(code)))
            for name in ("requests.jsonl", "responses.jsonl", "graded.json", "run_manifest.json",
                         "summary.json", "RESULTS.md", "environment.json"):
                if name in names:
                    copy(remote_out + "/" + name, target / name)
            save_json(target / "job_status.json", result)
            if result.get("server_log"):
                (target / "runtime_log_tail.txt").write_text(remote("tail -n 35 " + shlex.quote(result["server_log"])))
            if (target / "run_manifest.json").exists():
                manifest = json.loads((target / "run_manifest.json").read_text())
                for field, expected in (("request_corpus_sha256", stage["requests_sha256"]),
                                        ("request_count", stage["request_count"]),
                                        ("code_revision", plan["code_revision"]), ("track", stage["track"]),
                                        ("requested_model", plan["models"][stage["model_key"]]["served_name"])):
                    if manifest.get(field) != expected:
                        raise ValueError("collected result differs from predeclared plan: " + field)
                summary = prepare_report(target)
                if (target / "summary.json").exists() and json.loads((target / "summary.json").read_text()) != summary:
                    raise ValueError("remote report differs from frozen local regrading")
                summaries[stage["id"]] = summary
            else:
                (target / "RESULTS.md").write_text("# Stage did not complete\n\nNo completed model score is claimed. See job_status.json.\n")
            commit_paths([str(target.relative_to(repo))], "test: report production grounding " + stage["id"])
        comparisons = []
        for corpus in ("synthetic", "real"):
            pair = [stage for stage in plan["stages"] if stage["track"] == "production_" + corpus]
            if all(stage["id"] in summaries for stage in pair):
                comparison = prepare_report(root / pair[1]["id"], compare=root / pair[0]["id"])
                save_json(root / (corpus + "_comparison.json"), comparison)
                (root / (corpus + "_comparison.md")).write_text(render_markdown(comparison))
                comparisons.extend([corpus + "_comparison.json", corpus + "_comparison.md"])
        # The overview preserves frozen metrics and makes completion explicit.
        overview = {"run_id": plan["run_id"], "status": terminal["status"],
                    "exit_code": terminal["exit_code"], "code_revision": plan["code_revision"],
                    "stages": terminal["stages"], "verified_reports": sorted(summaries),
                    "limitations": ["Real-document gold is AI annotated, not human verified.",
                        "Synthetic and stratified real-sentence scores are separate; no deployment risk bound.",
                        "Gemma12B versus Qwen27B changes model family as well as size.",
                        "Failures and missing runs remain failures, never inferred successes."]}
        save_json(root / "summary.json", overview)
        lines = ["# Production grounding queue", "", f"Status: **{terminal['status']}**. Exit code: `{terminal['exit_code']}`.", "",
                 "All stages use separate stateless QA and automation requests with the actual production profiles.", "",
                 "| Stage | Status | Received / planned | Malformed |", "|---|---|---:|---:|"]
        for stage, result in zip(plan["stages"], terminal["stages"], strict=True):
            lines.append(f"| [{stage['id']}]({stage['id']}/RESULTS.md) | {result['status']} | {result.get('received_count', 0)}/{stage['request_count']} | {result.get('malformed_count', 'unknown')} |")
        lines += ["", *[f"[{name}]({name})" for name in comparisons if name.endswith(".md")],
                  "", *["- " + x for x in overview["limitations"]], ""]
        (root / "RESULTS.md").write_text("\n".join(lines))
        files = [str((root / name).relative_to(repo)) for name in
                 ("queue_plan.json", "queue_status.json", "unit_test_status.json", "queue_log_tail.txt", "summary.json", "RESULTS.md")]
        files.extend(str((root / name).relative_to(repo)) for name in comparisons)
        commit_paths(files, "test: summarize sequential production grounding experiments")
        subprocess.run(["python3", "scripts/staging_md.py", "done", "--id", config["staging_id"]],
                       cwd=config["workspace"], check=True)
        exit_code = terminal["exit_code"]
    except Exception as error:
        update(error={"type": type(error).__name__, "message": str(error)})
        print(json.dumps(state["error"]), flush=True)
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

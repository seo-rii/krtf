"""Privately verify the followup queue and publish only aggregate evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from .collect_hf_qa_queue import validate_public_json
from .hf_qa import canonical
from .report_followup_llm import prepare_report, render_markdown
from .run_followup_llm import ARTIFACTS
from .run_followup_queue import COMBINED_KIND, DIAGNOSTIC_KIND, EXTENDED_KIND, KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND, EFFICIENCY_KIND, ROBUSTNESS_KIND, SUPPORT_KIND, SUPPORT_CONFIRMATION_KIND, CLOSURE_KIND, validate_plan
from .run_production_queue import save_json


def verify_stage(root, stage, plan, *, selection=None):
    root = Path(root)
    reporter = prepare_report
    if plan["kind"] in {EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND, EFFICIENCY_KIND, ROBUSTNESS_KIND, SUPPORT_KIND, SUPPORT_CONFIRMATION_KIND, CLOSURE_KIND}:
        from .report_extended_suite import prepare_report as reporter
    summary = reporter(root)
    if plan["kind"] == SUPPORT_CONFIRMATION_KIND:
        envelope = json.loads((root / "frozen_envelope.json").read_text())
        source = envelope.get("provenance", {}).get("source", {})
        if (not isinstance(selection, dict)
                or envelope["protocol"]["conditions"] != [selection["baseline_condition"], selection["selected_condition"]]
                or source.get("source_sha256") != selection["fresh_source_sha256"]
                or source.get("review_sha256") != selection["fresh_review_sha256"]):
            raise ValueError("collected confirmation differs from frozen selection and fresh-source proof")
    manifest = json.loads((root / "run_manifest.json").read_text())
    expected = {"code_revision": plan["code_revision"], "experiment": stage["experiment"],
                "request_count": stage["request_count"], "request_corpus_sha256": stage["requests_sha256"],
                "frozen_request_file_sha256": stage["envelope_sha256"],
                "requested_model": plan["models"][stage["model_key"]]["served_name"]}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("verified manifest differs from frozen stage")
    environment = json.loads((root / "environment.json").read_text())
    if any(environment.get(key) != value for key, value in {
            "code_revision": plan["code_revision"], "source_archive_sha256": plan["archive_sha256"],
            "queue_plan_sha256": hashlib.sha256(canonical(plan)).hexdigest()}.items()):
        raise ValueError("stage environment differs from frozen plan")
    if json.loads((root / "summary.json").read_text()) != summary:
        raise ValueError("remote aggregate differs from local raw regrading")
    identity = {**expected, "source_manifest_seal_sha256": manifest["seal_sha256"],
                "artifact_sha256": manifest["artifact_sha256"], "counts": summary["counts"],
                "decoding": summary["decoding"], "schema_transport": summary["schema_transport"]}
    for value in (summary, identity, environment):
        validate_public_json(value)
    return summary, identity, environment


def collect_recovery_provenance(plan, terminal, config, private, copy):
    """Bind one reused closure stage to its original sealed run and collector."""
    if "retry_from" not in plan:
        if "recovery_spec" in config or any("reused_from" in row for row in terminal["stages"]):
            raise ValueError("stage reuse requires a pinned recovery plan and specification")
        return None
    from .recover_followup_queue import (
        reused_stage_state, validate_recovery_origin, validate_recovery_publication,
        validate_recovery_spec,
    )

    def pinned_json(pin, name):
        if (not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
                or not isinstance(pin.get("path"), str) or not Path(pin["path"]).is_absolute()
                or not isinstance(pin.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
            raise ValueError("recovery provenance requires an absolute path and immutable hash")
        target = private / (name + ".json")
        copy(pin["path"], target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("copied recovery provenance differs from frozen hash")
        return json.loads(target.read_text())

    spec_pin = config.get("recovery_spec")
    spec = pinned_json(spec_pin, "recovery_spec")
    validate_recovery_spec(spec, plan)
    if (terminal.get("driver_code_revision") != plan["driver_code_revision"]
            or terminal.get("driver_archive_sha256") != spec["driver_archive_sha256"]
            or terminal.get("retry_from") != plan["retry_from"]
            or terminal.get("recovery_spec_sha256") != spec_pin["sha256"]):
        raise ValueError("terminal recovery driver or specification differs from collector pins")
    retry = plan["retry_from"]
    original = pinned_json({"path": retry["plan_path"], "sha256": retry["plan_sha256"]},
                           "recovery_original_plan")
    original_terminal = pinned_json({"path": retry["status_path"], "sha256": retry["status_sha256"]},
                                   "recovery_original_status")
    origin = validate_recovery_origin(plan, original, original_terminal)
    collector_status = pinned_json(spec["original_collector_status"], "recovery_original_collector_status")
    collector_exit = pinned_json(spec["original_collector_exit"], "recovery_original_collector_exit")
    validate_recovery_publication(plan, original, original_terminal, collector_status, collector_exit)
    if ("reused_from" in terminal["stages"][0]
            or terminal["stages"][1] != reused_stage_state(origin)):
        raise ValueError("reused stage differs from the pinned original terminal result")
    overview = {
        "kind": spec["kind"], "original_run_id": original["run_id"],
        "original_plan_sha256": retry["plan_sha256"],
        "original_status_sha256": retry["status_sha256"],
        "specification_sha256": spec_pin["sha256"],
        "driver_code_revision": plan["driver_code_revision"],
        "experiment_code_revision": plan["code_revision"],
        "planned_new_generation_requests": plan["stages"][0]["request_count"],
        "new_generation_requests": terminal["stages"][0].get("received_count", 0),
        "reused_generation_requests": plan["stages"][1]["request_count"],
        "new_stages": [plan["stages"][0]["id"]],
        "reused_stages": [plan["stages"][1]["id"]],
        "runtime_change": {"model_key": "gemma12b", "setting": "gpu_memory_utilization",
                           "before": original["models"]["gemma12b"]["gpu_memory_utilization"],
                           "after": plan["models"]["gemma12b"]["gpu_memory_utilization"]},
        "inference_policy_changed": False,
        "original_collector_status_sha256": spec["original_collector_status"]["sha256"],
        "original_collector_exit_sha256": spec["original_collector_exit"]["sha256"],
        "reused_stage_artifacts_sha256": spec["reused_stage_artifacts_sha256"],
        "reused_artifacts_unchanged": True,
    }
    return {"original_plan": original, "specification": spec,
            "origin": origin, "overview": validate_public_json(overview)}


def stage_collection_source(plan, stage, result, recovery):
    """Choose provenance before copying; ordinary stages cannot claim reuse."""
    if recovery is not None and stage["model_key"] == "qwen27b":
        from .recover_followup_queue import reused_stage_state
        if result != reused_stage_state(recovery["origin"]):
            raise ValueError("reused stage differs from pinned provenance")
        original = recovery["original_plan"]
        original_stage = next(row for row in original["stages"] if row["id"] == stage["id"])
        return result["reused_from"]["result_path"], original_stage, original
    if "reused_from" in result:
        raise ValueError("unpinned or wrong-stage reuse is not allowed")
    return str(Path(plan["run_root"]) / "results" / stage["id"]), stage, plan


def compare_models(summaries, plan):
    result = {}

    def rate_delta(current, baseline, key):
        # No negatives in the corpus track; semantic safety uses other rates.
        # An absent denominator is unknown, never a zero-percent success rate.
        values = current.get(key), baseline.get(key)
        return None if any(value is None for value in values) else values[0] - values[1]

    def compare_variants(first, second, safety):
        if set(first) != set(second):
            raise ValueError("model conditions differ")
        return {key: {
            "positive_exact_rate_delta": rate_delta(second[key], values, "positive_exact_rate"),
            "no_answer_null_rate_delta": rate_delta(second[key], values, "article_no_answer_null_rate"),
            **({metric + "_delta": rate_delta(second[key], values, metric) for metric in (
                "correct_rate", "accepted_wrong_id_rate", "accepted_wrong_id_rate_among_accepted",
                "accepted_correct_id_rate", "correct_abstention_rate", "over_abstention_rate")}
               if safety else {}),
            "baseline_malformed": values["malformed"], "current_malformed": second[key]["malformed"]}
            for key, values in first.items()}

    for experiment in dict.fromkeys(s["experiment"] for s in plan["stages"]):
        stages = [s for s in plan["stages"] if s["experiment"] == experiment]
        if not all(s["id"] in summaries for s in stages):
            continue
        first, second = (summaries[s["id"]] for s in stages)
        if (first["request_corpus_sha256"] != second["request_corpus_sha256"]
                or first["code_revision"] != second["code_revision"]
                or first["decoding"] != second["decoding"]):
            raise ValueError("matched comparison requires identical inputs and configuration")
        result[experiment] = {"baseline_model": first["model"], "current_model": second["model"],
            "questions": first["questions"], "request_corpus_sha256": first["request_corpus_sha256"],
            "by_variant": compare_variants(first["by_variant"], second["by_variant"],
                                            experiment in {"semantic_safety", "safety_robustness", "review_routing", "routing_confirmation", "evidence_control", "evidence_efficiency", "evidence_robustness", "support_recovery", "evidence_closure"}),
            "limitations": ["Model family and size both change.",
                "Repeated generations do not increase the number of independent questions."]}
        if plan["kind"] in {DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND, EFFICIENCY_KIND, ROBUSTNESS_KIND, SUPPORT_KIND, SUPPORT_CONFIRMATION_KIND, CLOSURE_KIND}:
            left, right = first["by_evaluation_split"], second["by_evaluation_split"]
            if set(left) != set(right) or any(
                    any(left[key][field] != right[key][field] for field in ("questions", "families"))
                    for key in left):
                raise ValueError("diagnostic evaluation splits differ between models")
            result[experiment]["by_evaluation_split"] = {key: {
                "questions": value["questions"], "families": value["families"],
                "by_variant": compare_variants(value["by_variant"], right[key]["by_variant"],
                                                experiment in {"safety_robustness", "review_routing", "routing_confirmation", "evidence_control", "evidence_efficiency", "evidence_robustness", "support_recovery", "evidence_closure"})}
                for key, value in left.items()}
            result[experiment]["aggregate_scope"] = (
                "Reused source diagnostics only; original development/confirmation labels do not denote new holdout validation."
                if plan["kind"] in {ROBUSTNESS_KIND, SUPPORT_KIND} else
                "Fresh AI-authored confirmation; production evaluation and experimental shadow simulation remain separate."
                if plan["kind"] in {SUPPORT_CONFIRMATION_KIND, CLOSURE_KIND} else
                "workload aggregate only; evaluate exposed and fresh splits separately")
        if experiment in {"support_recovery", "evidence_closure"}:
            if first.get("authorization_by_condition") != second.get("authorization_by_condition"):
                raise ValueError("model approval contracts differ")
            result[experiment].update(authorization_by_condition=first["authorization_by_condition"],
                                      execution_authority="none", evaluation_only=True)
    return validate_public_json(result)


def collect(config):
    plan = validate_plan(config["plan"])
    validate_public_json(plan)
    repo = Path(config["repo"]).resolve(strict=True)
    public = (repo / config["report_dir"]).resolve()
    logical_private = Path(os.path.abspath(repo / config["private_dir"]))
    private = logical_private.resolve()
    private_parent = repo / "eval/out"
    if "private_storage_root" in config:
        storage = Path(config["private_storage_root"])
        if plan["kind"] not in {COMBINED_KIND, EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND, EFFICIENCY_KIND, ROBUSTNESS_KIND, SUPPORT_KIND, SUPPORT_CONFIRMATION_KIND, CLOSURE_KIND} or not storage.is_absolute() or not storage.is_dir():
            raise ValueError("explicit absolute private storage root is supported only for combined, extended or diagnostic queues")
        private_parent = storage.resolve(strict=True)
    status_path = Path(config["local_status"]).resolve()
    if (not public.is_relative_to(repo / "reports") or public == repo / "reports"
            or not logical_private.is_relative_to(repo / "eval/out") or logical_private == repo / "eval/out"
            or not private.is_relative_to(private_parent) or private == private_parent
            or private.is_relative_to(public) or public.is_relative_to(private)
            or status_path.is_relative_to(public) or status_path.is_relative_to(private)
            or any(p.exists() for p in (public, private, status_path))):
        raise ValueError("new public report, private ignored output and status paths required")
    ignore_path = config["private_dir"]
    if "private_storage_root" in config:
        ancestor = repo
        for part in logical_private.relative_to(repo).parts:
            ancestor = ancestor / part
            if ancestor.is_symlink():
                # Git refuses descendants of a symlink; its ignored ancestor
                # protects the entire explicitly approved external subtree.
                ignore_path = str(ancestor.relative_to(repo))
                break
    state = {"run_id": plan["run_id"], "pid": os.getpid(), "status": "RUNNING", "phase": "WAITING_FOR_QUEUE",
             "exit_code": None, "started_at": datetime.now(timezone.utc).isoformat(), "pushed_commits": []}

    def update(**values):
        state.update(values)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(status_path, state)

    def remote(command):
        return subprocess.check_output(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            config["host"], command], text=True, timeout=90)

    def copy(source, target):
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            config["host"] + ":" + source, str(target)], check=True, timeout=300)
        target.chmod(0o600)

    def publish(paths, message):
        if subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip() != "main":
            raise ValueError("active branch changed; verified reports remain local")
        subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, timeout=180)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=repo, text=True).strip()
        if head != upstream:
            raise ValueError("main differs from origin/main; refusing to push other commits")
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
        subprocess.run(["git", "check-ignore", "-q", "--", ignore_path], cwd=repo, check=True)
        deadline, failures = time.monotonic() + 7 * 86400, 0
        while True:
            try:
                terminal = json.loads(remote("cat " + shlex.quote(plan["status_path"])))
                update(remote=terminal)
                if terminal.get("exit_code") is not None:
                    break
                failures = 0
            except (ValueError, subprocess.SubprocessError) as error:
                failures += 1
                update(monitor_error_type=type(error).__name__, monitor_failures=failures)
                if failures >= 30:
                    raise RuntimeError("remote status unavailable for 30 polls") from error
            if time.monotonic() > deadline:
                raise RuntimeError("collector deadline exceeded")
            time.sleep(60)
        expected = {"kind": plan["kind"], "run_id": plan["run_id"], "code_revision": plan["code_revision"],
                    "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(), "phase": "FINISHED"}
        if (any(terminal.get(key) != value for key, value in expected.items())
                or type(terminal.get("exit_code")) is not int or terminal.get("status") not in {"COMPLETE", "FAILED"}
                or (terminal["status"] == "COMPLETE") != (terminal["exit_code"] == 0)
                or [s.get("id") for s in terminal.get("stages", [])] != [s["id"] for s in plan["stages"]]):
            raise ValueError("terminal queue identity or status differs")
        validate_public_json(terminal)
        private.mkdir(parents=True, mode=0o700)
        proofs = {}
        for name, spec in plan["proofs"].items():
            target = private / (name + "_proof.json")
            copy(spec["path"], target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != spec["sha256"]:
                raise ValueError("copied proof differs from frozen hash")
            proofs[name] = validate_public_json(json.loads(target.read_text()))
        if plan["kind"] == SUPPORT_CONFIRMATION_KIND:
            target = private / "selection_proof.json"
            copy(plan["selection"]["path"], target)
            from .run_followup_queue import verify_support_selection
            local_plan = {**plan, "selection": {**plan["selection"], "path": str(target)}}
            proofs["selection"] = validate_public_json(verify_support_selection(local_plan))
        if (proofs["unit"].get("exit_code") != 0 or proofs["unit"].get("code_revision") != plan["code_revision"]
                or (plan["kind"] == KIND and proofs["blind_document"].get("exit_code") != 0)
                or proofs["preparation"].get("code_revision") != plan["code_revision"]):
            raise ValueError("successful frozen CPU/test/preparation proofs required")
        recovery = collect_recovery_provenance(plan, terminal, config, private, copy)
        if recovery is not None:
            proofs["recovery"] = recovery["overview"]
            original = recovery["original_plan"]
            original_missing = str(Path(original["run_root"]) / "results" / original["stages"][0]["id"])
            remote("python3 -c " + shlex.quote("import os,sys;sys.exit(int(os.path.lexists(sys.argv[1])))")
                   + " " + shlex.quote(original_missing))
        artifacts, summaries, missing = {}, {}, []
        update(phase="PRIVATE_COLLECTION_AND_REGRADING")
        for stage, result in zip(plan["stages"], terminal["stages"], strict=True):
            if (result.get("experiment") != stage["experiment"] or result.get("request_count") != stage["request_count"]
                    or type(result.get("exit_code")) is not int or result.get("status") not in {"COMPLETE", "FAILED"}
                    or (result["status"] == "COMPLETE") != (result["exit_code"] == 0)):
                raise ValueError("stage identity/count/terminal status differs")
            remote_out, source_stage, source_plan = stage_collection_source(plan, stage, result, recovery)
            if result.get("benchmark_started") is False and result["status"] == "FAILED":
                remote("python3 -c " + shlex.quote("import os,sys;sys.exit(int(os.path.lexists(sys.argv[1])))")
                       + " " + shlex.quote(remote_out))
                missing.append(stage["id"])
                continue
            if result.get("benchmark_started") is not True:
                raise ValueError("stage execution provenance unavailable")
            target = private / stage["id"]
            target.mkdir(mode=0o700)
            for name in (*ARTIFACTS, "run_manifest.json", "environment.json", "summary.json"):
                copy(remote_out + "/" + name, target / name)
                if recovery is not None and stage["model_key"] == "qwen27b":
                    if hashlib.sha256((target / name).read_bytes()).hexdigest() != recovery["specification"]["reused_stage_artifacts_sha256"][name]:
                        raise ValueError("copied reused artifact differs from frozen original bytes")
            if plan["kind"] == SUPPORT_CONFIRMATION_KIND:
                summary, identity, environment = verify_stage(target, source_stage, source_plan, selection=proofs["selection"])
            else:
                summary, identity, environment = verify_stage(target, source_stage, source_plan)
            if any(result.get(key) != summary["counts"][key] for key in (
                    "received_count", "missing_count", "error_count", "malformed_count")):
                raise ValueError("terminal counts differ from sealed raw regrading")
            if (type(result.get("benchmark_exit_code")) is not int
                    or type(result.get("report_exit_code")) is not int
                    or (result["benchmark_exit_code"] == 0) != (summary["status"] == "COMPLETE")
                    or result["exit_code"] != (result["benchmark_exit_code"] or result["report_exit_code"])):
                raise ValueError("terminal stage success differs from verified benchmark/report status")
            summaries[stage["id"]] = summary
            artifacts[stage["id"]] = {"summary.json": summary, "manifest_identity.json": identity,
                                      "environment.json": environment, "job_status.json": result}
        if (terminal["exit_code"] == 0) != all(s["exit_code"] == 0 for s in terminal["stages"]):
            raise ValueError("queue exit status disagrees with stage outcomes")
        if not summaries:
            raise ValueError("no verified generation runs available")
        comparison = compare_models(summaries, plan)
        combined = plan["kind"] == COMBINED_KIND
        extended = plan["kind"] in {EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND, EFFICIENCY_KIND, ROBUSTNESS_KIND, SUPPORT_KIND, SUPPORT_CONFIRMATION_KIND, CLOSURE_KIND}
        diagnostic = plan["kind"] == DIAGNOSTIC_KIND
        review = plan["kind"] == REVIEW_KIND
        confirmation = plan["kind"] == CONFIRMATION_KIND
        evidence = plan["kind"] == EVIDENCE_KIND
        efficiency = plan["kind"] == EFFICIENCY_KIND
        robustness = plan["kind"] == ROBUSTNESS_KIND
        support = plan["kind"] in {SUPPORT_KIND, SUPPORT_CONFIRMATION_KIND}
        support_confirmation = plan["kind"] == SUPPORT_CONFIRMATION_KIND
        closure = plan["kind"] == CLOSURE_KIND
        fresh = combined and plan.get("sample_design", {}).get("kind") == "fresh_document_holdout"
        limitations = ([
            "Previously inspected frozen retrieval questions are reused for this adaptive combined followup; no independent holdout claim.",
            "Repeats are descriptive measurements and do not increase the number of independent questions.",
            "Search is within known source articles; corpus-level document retrieval is not evaluated.",
            "The KTRF pack and its policy form one intervention; pack source matches each retrieval arm.",
            "Common source-token caps do not imply equal actual prompt-token cost.",
            "Model family and size change together; timing on a shared host is descriptive."] if combined else [
            "Blind document gold is AI authored and adjudicated; no human verification or deployment guarantee.",
            "Oracle uses gold and is diagnostic only.", "Stability uses previously inspected questions; repeats are not independent samples.",
            "Model family and size change together; timing on a shared host is descriptive."])
        if fresh:
            limitations[0:1] = [
                "Fresh article split excludes declared prior articles by identity and content hash; this is a same-corpus holdout, not external independent validation.",
                "Exact article exclusion does not establish absence of near-duplicate documents or pretrained-model contamination.",
                "Earlier results informed the methods; this sample was frozen before its generation outputs."]
        if extended:
            limitations = [
                "The four QA experiments share a frozen KLUE-MRC sample; nested subsets are not independent replications.",
                "Overlap filtering covers declared sources only and cannot establish absence of model pretraining contamination.",
                "Corpus retrieval uses a fixed 512-document corpus and positive questions only; article-specific negatives do not establish corpus-wide absence.",
                "Budget comparisons share total prompt caps, not identical consumed token counts.",
                "Semantic safety gold is AI authored and reviewed; it is not independently human verified or a deployment error-rate estimate.",
                "Model family and size change together; shared-host timing is descriptive. No thresholds are tuned on these results."]
        if diagnostic:
            limitations = [
                "The source/pack factorial reuses previously inspected questions and is an adaptive diagnostic, not independent validation.",
                "Fresh KLUE contexts exclude prior source contexts and the complete earlier 512-context search corpus; original article identities and pretraining independence remain unverified.",
                "The factorial fixes policy and pack facts across source amounts; its arms are not a shared-token-cap product comparison.",
                "Compact packs remove metadata while preserving projected semantic facts and caveats; this is not pure serialization alone.",
                "Safety results must separate 96 exposed cases from 64 fresh AI-authored cases; shared families and prompt variants are not independent samples.",
                "Prompt instructions add no execution authority: complete responses still pass the unchanged production guard.",
                "These tests do not tune deployment thresholds or establish operational error-rate guarantees."]
        if review:
            limitations = [
                "Shared public KLUE contexts across QA/policy/budget/routing tracks and shared authored families are not independent samples.",
                "Business documents are AI authored; public natural contexts are AI annotated proxies, not private deployment documents or human gold.",
                "NoMIRACL measures relevance of complete provided passage sets, not answer generation or entity linking; Wikipedia/pretraining overlap remains possible.",
                "Pipeline selectors differ; matched-facts arms isolate presentation and policy conditionally on the declared common candidate set.",
                "All new execution calls use strict occurrence-bound identities; historical reanalysis explicitly retains the sealed legacy contract.",
                "No deployment thresholds are tuned, and synthetic/public proxy observations do not establish operational risk guarantees."]
        if confirmation:
            limitations = [
                "Fresh AI-authored documents: 8 development families and 16 confirmation families; shared scenarios are not independent observations.",
                "Selected policies were frozen before these model outputs; no thresholds are tuned on confirmation results.",
                "The evidence gate checks source quote/attribute consistency and preserves production authorization; it is not an entailment oracle.",
                "Full and compact transports bind the same immutable occurrence; shorter output grants no new authority.",
                "No private workplace document or human verification has been supplied; real shadow evaluation remains WAITING_FOR_INPUT.",
                "Shared-host latency is descriptive; synthetic approvals do not establish deployment risk guarantees."]
        if evidence:
            limitations = [
                "All 64 source cases are previously exposed development documents from 8 AI-authored families; this is an adaptive diagnostic, not a new holdout.",
                "All arms share actual resolver candidates, reference facts, and the unchanged production occurrence authorization guard.",
                "Ambiguous candidates may be proposed but are never authorized by model or evidence scores alone.",
                "Evidence IDs bind source spans on the server; they establish literal identity, not semantic entailment.",
                "Model family and size both change; shared-host latency is descriptive.",
                "No actual workplace documents or independent human annotations have been supplied."]
        if efficiency:
            limitations = [
                "Fresh source gold is AI authored and independently AI reviewed before resolution and generation, not human gold or real workplace records.",
                "64 documents share 8 families and 4 source styles; 2 development and 6 confirmation families are separate.",
                "Methods were selected from earlier exposed diagnostics; this source was sealed before these model outputs.",
                "All arms use the same actual candidates and unchanged occurrence execution guard. Short references grant no new authority.",
                "Selective routing is a frozen source-only rule, not calibrated semantic safety; reference fact compression retains full definitions and source text.",
                "Model family and size both change; shared-host timings are descriptive, not service-load guarantees."]
        if robustness:
            limitations = [
                "All source documents and original development/confirmation families are reused from the evidence-efficiency experiment; no fresh holdout or independent replication claim.",
                "This adaptive diagnostic compares evidence representation, candidate/catalog ordering and unrelated evidence distractors on the same 64 AI-authored cases.",
                "Bundles bind the same four server-known attribute spans; they do not establish semantic entailment or grant execution authority.",
                "Every arm retains actual resolver candidates and the unchanged production occurrence guard.",
                "Family and document paired analyses remain descriptive; repeated conditions do not increase the independent sample size.",
                "No private workplace documents or independent human annotations have been supplied; shared-host costs do not establish deployment guarantees."]
        if support:
            limitations = [
                ("Fresh AI-authored, independently AI-reviewed source families were frozen before generation; the selected method was chosen solely on earlier discovery outputs."
                 if support_confirmation else
                 "All 64 source documents are reused AI-authored diagnostic cases; eight conditions do not constitute eight independent samples."),
                "Production conditions retain the unchanged occurrence guard; shadow conditions are EXPERIMENTAL_SIMULATED_APPROVAL and grant no execution authority.",
                "Candidate and source inventories are built without gold; source attribution rules and missing-attribute policies remain experimental rather than semantic guarantees.",
                "Model proposals, production guard acceptance and simulated shadow acceptance are reported separately for every condition.",
                "No actual workplace documents or independent human gold have been provided; these results cannot certify deployment error bounds.",
                "Shared families and paired conditions require clustered interpretation, and shared-host latency is descriptive."]
        if closure:
            limitations = [
                "Fresh AI-authored and independently AI-reviewed source gold was sealed before resolution and generation; it is not human workplace gold.",
                "96 documents share 12 semantic families; 48 short and 48 long documents balance candidate country, referent kind and target side.",
                "The five paired conditions compare server source-span closure, an explicit null response branch and bundle output; repeated conditions are not independent samples.",
                "All outcomes are experimental shadow judgments with no execution authority; production occurrence-guard outcomes remain separately reported.",
                "Server-added segments bind existing source references and do not establish semantic entailment or permit cross-occurrence evidence borrowing.",
                "No private deployment distribution or independent human annotations have been supplied; shared-host latency is descriptive and no deployment risk is certified."]
        overview = {"kind": plan["kind"], "run_id": plan["run_id"], "status": terminal["status"],
            "exit_code": terminal["exit_code"], "verified_reports": sorted(summaries), "missing_stages": missing,
            "raw_artifacts_published": False,
            "planned_generation_requests": sum(stage["request_count"] for stage in plan["stages"]),
            "limitations": limitations}
        if recovery is not None:
            overview["recovery"] = recovery["overview"]
            overview["new_generation_requests"] = recovery["overview"]["new_generation_requests"]
            overview["reused_generation_requests"] = recovery["overview"]["reused_generation_requests"]
            memory_change = recovery["overview"]["runtime_change"]
            overview["limitations"].extend([
                "Recovery permits new generation only for the previously missing Gemma stage; all 480 Qwen responses are reused byte-for-byte from the pinned original completed stage.",
                f"Gemma GPU memory utilization changes from {memory_change['before']:g} to {memory_change['after']:g} to recover startup capacity; experiment requests, decoding and inference policy remain frozen.",
                "The original Gemma stage failed before benchmark generation, and the original partial collector completed publication with an expected failed-queue exit status.",
            ])
        if fresh:
            overview["sample_design"] = plan["sample_design"]
        public_objects = {"summary.json": overview, "queue_plan.json": plan, "queue_status.json": terminal,
                          "model_comparison.json": comparison, **{name + "_proof.json": value for name, value in proofs.items()}}
        for value in public_objects.values():
            validate_public_json(value)
        public.mkdir(parents=True)
        for stage in plan["stages"]:
            if stage["id"] not in summaries:
                continue
            target = public / stage["id"]
            target.mkdir()
            for name, value in artifacts[stage["id"]].items():
                validate_public_json(value)
                if (recovery is not None and stage["model_key"] == "qwen27b"
                        and name in {"summary.json", "environment.json"}):
                    # Verification used the original plan; retain its original
                    # serialized metadata rather than relabelling the old run.
                    (target / name).write_bytes((private / stage["id"] / name).read_bytes())
                else:
                    save_json(target / name, value)
            renderer = render_markdown
            if extended:
                from .report_extended_suite import render_markdown as renderer
            (target / "RESULTS.md").write_text(renderer(summaries[stage["id"]]))
        for name, value in public_objects.items():
            save_json(public / name, value)
        heading = "# KTRF combined BM25, pack and JSON queue" if combined else "# KTRF followup queue"
        if fresh:
            heading = "# KTRF fresh-document combined BM25, pack and JSON queue"
        if extended:
            heading = "# KTRF five extended experiments"
        if diagnostic:
            heading = "# KTRF source, compact-pack and safety diagnostics"
        if review:
            heading = "# KTRF review-driven QA, relevance and occurrence experiments"
        if confirmation:
            heading = "# KTRF fresh routing confirmation and compact transport"
        if evidence:
            heading = "# KTRF matched candidates and server-bound evidence control"
        if robustness:
            heading = "# KTRF reused-source evidence robustness and bundle cost diagnostics"
        if efficiency:
            heading = "# KTRF fresh evidence efficiency and selective routing"
        if support:
            heading = ("# KTRF fresh support-recovery confirmation (evaluation only)" if support_confirmation else
                       "# KTRF reused-source support-recovery discovery (evaluation only)")
        if closure:
            heading = "# KTRF fresh server evidence closure, null response and bundle confirmation (evaluation only)"
        preparation = ("Frozen unit tests and actual-tokenizer preparation completed before GPU generation." if combined or extended else
                       "CPU preparation and AI blind-document evaluation completed before GPU generation.")
        lines = [heading, "", f"Status: **{terminal['status']}**, exit code `{terminal['exit_code']}`.", "",
                 preparation, "",
                 "| Stage | Status | Received/planned |", "|---|---|---:|"]
        if recovery is not None:
            lines[6:6] = [f"Recovery: **{overview['new_generation_requests']} new Gemma requests; "
                          f"{overview['reused_generation_requests']} reused Qwen requests**. "
                          "The Qwen stage was not regenerated. Gemma GPU memory utilization "
                          f"changes `{memory_change['before']:g} → {memory_change['after']:g}`; "
                          "requests, decoding and inference policy are unchanged.", ""]
        for stage, result in zip(plan["stages"], terminal["stages"], strict=True):
            label = f"[{stage['id']}]({stage['id']}/RESULTS.md)" if stage["id"] in summaries else stage["id"]
            lines.append(f"| {label} | {result['status']} | {result.get('received_count', 'not started')}/{stage['request_count']} |")
        lines += ["", "## Limitations", "", *["- " + value for value in overview["limitations"]], ""]
        (public / "RESULTS.md").write_text("\n".join(lines))
        update(phase="PUBLISHING_VERIFIED_AGGREGATES")
        for stage in plan["stages"]:
            if stage["id"] in summaries:
                paths = [public / stage["id"] / name for name in (*artifacts[stage["id"]], "RESULTS.md")]
                publish(paths, "test: report followup " + stage["id"])
        publish([public / name for name in (*public_objects, "RESULTS.md")],
                "test: summarize fresh evidence closure confirmation" if closure else
                "test: summarize fresh support recovery confirmation" if support_confirmation else
                "test: summarize support recovery discovery" if support else
                "test: summarize reused-source evidence robustness" if robustness else
                "test: summarize fresh evidence efficiency" if efficiency else
                "test: summarize matched evidence control" if evidence else
                "test: summarize fresh routing confirmation" if confirmation else
                "test: summarize review-driven experiments" if review else
                "test: summarize queued source and safety diagnostics" if diagnostic else
                "test: summarize five queued extended experiments" if extended else
                "test: summarize queued combined retrieval experiments" if combined else
                "test: summarize queued retrieval and stability experiments")
        update(publication_complete=True, verified_reports=sorted(summaries), missing_stages=missing)
        exit_code = terminal["exit_code"]
        if exit_code == 0:
            subprocess.run(["python3", "scripts/staging_md.py", "done", "--id", config["staging_id"]], cwd=config["workspace"], check=True)
    except Exception as error:
        update(error_type=type(error).__name__)
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

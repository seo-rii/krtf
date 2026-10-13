"""Report a sealed QA-policy intervention using only its frozen run artifacts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from eval.product_utility import malformed_response_field
from eval.qa_policy_probe import CONDITIONS, grade_policy_outputs
from eval.report_synthetic_grounding import (
    ARTIFACTS, _distribution, _json_bytes, _oracle_ceiling, _routing_abstentions,
)
from ktrf.context import validate_llm_grounding

TASKS = ("document_qa", "structured_routing")


def _valid_value(record, field):
    response = record.get("response") if record else None
    valid = (bool(record) and record.get("status") == "RECEIVED"
             and isinstance(response, dict) and not malformed_response_field(response, field))
    return valid, response.get(field) if valid else None


def _guard(row, value):
    return validate_llm_grounding({"selections": [{
        "surface": row["target_surface"], "entity_id": value}]},
        row["pack"], purpose="execution")["valid"]


def _validate_requests(requests):
    known, documents = {}, defaultdict(dict)
    fixed = ("document_id", "family_id", "task", "world", "stratum", "text", "target_surface",
             "target_span", "document_sha256", "gold", "expected_answer", "expected_entity_id",
             "pack", "cards", "snapshot_id", "candidate_hash", "binding_hash", "source_condition",
             "resolver_authorized_entity_id", "contrast_pair_id", "contrast_member")
    for row in requests:
        key = (row["case_id"], row["condition"])
        if key in known or row["condition"] not in CONDITIONS or row["task"] not in TASKS:
            raise ValueError("duplicate request or unknown condition/task")
        if row.get("source_condition") != "surface_only":
            raise ValueError("policy requests must retain surface_only source identity")
        known[key] = row
        slot = (row["task"], row["condition"])
        if slot in documents[row["document_id"]]:
            raise ValueError("duplicate document task/condition")
        documents[row["document_id"]][slot] = row
    required = {(task, condition) for task in TASKS for condition in CONDITIONS}
    if not documents or any(set(rows) != required for rows in documents.values()):
        raise ValueError("every document must contain both tasks and both conditions")
    for rows in documents.values():
        for task in TASKS:
            baseline, intervention = rows[(task, "strict")], rows[(task, "qa_context")]
            if (baseline["case_id"] != intervention["case_id"] or
                    any(baseline.get(field) != intervention.get(field) for field in fixed)):
                raise ValueError("policy conditions must retain the same case, candidate facts and gold")
        qa, routing = rows[("document_qa", "strict")], rows[("structured_routing", "strict")]
        for field in fixed:
            if field != "task" and qa.get(field) != routing.get(field):
                raise ValueError("document tasks disagree on frozen facts or gold")
    return known


def _supplementary_metrics(rows, recorded):
    """QA content has no authority: separately assess any incidental entity ID."""
    id_counts, negatives = Counter(), defaultdict(Counter)
    for row in rows:
        if row["task"] != "document_qa":
            continue
        record = recorded.get((row["case_id"], row["condition"]))
        valid, answer = _valid_value(record, "answer")
        if row["expected_answer"] is None:
            stats = negatives[row["stratum"]]
            stats["planned"] += 1
            stats["observed"] += bool(record and "response" in record)
            stats["valid"] += valid
            stats["null"] += valid and answer is None
            stats["nonnull"] += valid and answer is not None
        # A malformed answer can still contain an incidental ID worth auditing.
        # This field-level diagnostic never makes the response executable.
        response = record.get("response") if record else None
        if not isinstance(response, dict) or malformed_response_field(response, "entity_id"):
            continue
        entity_id = response["entity_id"]
        if entity_id is None:
            continue
        correct = entity_id == row["expected_entity_id"]
        authorized = _guard(row, entity_id)
        id_counts["nonnull"] += 1
        id_counts["semantic_correct" if correct else "semantic_wrong"] += 1
        id_counts[("correct_" if correct else "wrong_") + ("authorized" if authorized else "blocked")] += 1
        id_counts["answer_correct_with_blocked_id"] += valid and answer == row["expected_answer"] and not authorized
    keys = ("nonnull", "semantic_correct", "semantic_wrong", "correct_authorized", "correct_blocked",
            "wrong_authorized", "wrong_blocked", "answer_correct_with_blocked_id")
    return {
        "qa_incidental_id_semantics": {key: id_counts[key] for key in keys},
        "negative_qa_controls": {
            stratum: {**{key: stats[key] for key in ("planned", "observed", "valid", "null", "nonnull")},
                      "nonnull_rate_planned": stats["nonnull"] / stats["planned"],
                      "nonnull_rate_valid": stats["nonnull"] / stats["valid"] if stats["valid"] else None}
            for stratum, stats in sorted(negatives.items())},
    }


def prepare_report(run_dir):
    """Verify artifacts, protocol identity and frozen regrading before reporting."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("track") != "qa_policy_probe" or manifest.get("protocol") != "qa_policy_separation_v1":
        raise ValueError("report requires qa_policy_probe / qa_policy_separation_v1")
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(_json_bytes(unsealed)).hexdigest() != seal:
        raise ValueError("invalid manifest seal")
    hashes = manifest.get("artifact_sha256", {})
    if set(hashes) != set(ARTIFACTS):
        raise ValueError("manifest must seal all three run artifacts")
    contents = {name: (run_dir / name).read_bytes() for name in ARTIFACTS}
    for name, data in contents.items():
        if hashlib.sha256(data).hexdigest() != hashes[name]:
            raise ValueError(f"artifact hash mismatch: {name}")
    if manifest.get("request_corpus_sha256") != hashes["requests.jsonl"]:
        raise ValueError("request corpus hash disagrees with sealed artifact")
    requests = [json.loads(line) for line in contents["requests.jsonl"].splitlines() if line.strip()]
    records = [json.loads(line) for line in contents["responses.jsonl"].splitlines() if line.strip()]
    known, recorded = _validate_requests(requests), {}
    for record in records:
        key = (record["case_id"], record["condition"])
        if key not in known or key in recorded:
            raise ValueError("unknown or duplicate response key")
        status = record.get("status")
        if status not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown response status")
        if (status in {"RECEIVED", "MALFORMED"}) != ("response" in record):
            raise ValueError("response presence disagrees with status")
        if status == "RECEIVED":
            field = "answer" if known[key]["task"] == "document_qa" else "entity_id"
            if not _valid_value(record, field)[0]:
                raise ValueError("RECEIVED response has malformed task field")
        if (record.get("error") is not None) != (status in {"HTTP_ERROR", "TRANSPORT_ERROR"}):
            raise ValueError("response error disagrees with status")
        recorded[key] = record
    received = sum("response" in record for record in records)
    counts = {"request_count": len(requests), "received_count": received,
              "missing_count": len(requests) - received,
              "error_count": sum(record.get("error") is not None for record in records),
              "malformed_count": sum(record["status"] == "MALFORMED" for record in records)}
    if any(manifest.get(key) != value for key, value in counts.items()):
        raise ValueError("sealed manifest counts disagree with records")
    if manifest.get("status") != ("COMPLETE" if not counts["missing_count"] and not counts["error_count"] else "INCOMPLETE"):
        raise ValueError("run completion status disagrees with records")
    recomputed = grade_policy_outputs(requests, [record for record in records if "response" in record])
    graded = json.loads(contents["graded.json"])["model_results"]
    if graded != recomputed or graded.get("missing_outputs") != counts["missing_count"]:
        raise ValueError("recorded grades disagree with frozen regrading")

    operational, supplementary, abstentions = {}, {}, {}
    for condition in CONDITIONS:
        rows = [row for row in requests if row["condition"] == condition]
        attempts = [record for record in records if record["condition"] == condition]
        latency = [record["latency_ms"] for record in attempts
                   if type(record.get("latency_ms")) in (int, float)
                   and math.isfinite(record["latency_ms"]) and record["latency_ms"] >= 0]
        usage = {key: _distribution([record["usage"][key] for record in attempts
                 if isinstance(record.get("usage"), dict) and type(record["usage"].get(key)) is int
                 and record["usage"][key] >= 0])
                 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        operational[condition] = {"planned": len(rows), "attempted": len(attempts),
            "received": sum("response" in record for record in attempts),
            "missing": len(rows) - sum("response" in record for record in attempts),
            "malformed": sum(record["status"] == "MALFORMED" for record in attempts),
            "status_counts": dict(Counter(record["status"] for record in attempts)),
            "finish_reason_counts": dict(Counter(str(record.get("finish_reason")) for record in attempts)),
            "latency_ms": _distribution(latency), "actual_usage": usage,
            "estimated_input_tokens": sum(row["estimated_input_tokens"] for row in rows)}
        supplementary[condition] = _supplementary_metrics(rows, recorded)
        abstentions[condition] = _routing_abstentions(rows, recorded, condition)
    unique = [row for row in requests if row["condition"] == "strict"]
    documents = [row for row in unique if row["task"] == "document_qa"]
    return {"kind": "sealed_qa_policy_report", "status": manifest["status"],
        "track": manifest["track"], "protocol": manifest["protocol"],
        "annotation_origin": "AI_SYNTHETIC", "human_verified": False, "quality_claim": False,
        **{key: manifest.get(key) for key in ("code_revision", "requested_model", "served_models", "endpoint",
            "started_at", "finished_at", "decoding", "declared_protocol", "request_corpus_sha256")},
        "verified_manifest_seal_sha256": seal, "verified_artifact_sha256": hashes,
        "source_conditions": dict(Counter(row["source_condition"] for row in unique)),
        "source_candidate_hashes": {row["document_id"]: row["candidate_hash"] for row in documents},
        "source_document_hashes": {row["document_id"]: row["document_sha256"] for row in documents},
        "counts": {**counts, "attempted_count": len(records), "documents": len(documents),
                   "families": len({row["family_id"] for row in unique}), "task_cases": len(unique)},
        "strata": dict(Counter(row["stratum"] for row in documents)),
        "gold_labels": dict(Counter(row["gold"]["label"] for row in documents)),
        "policy_diagnostics": graded["policy_diagnostics"],
        "expanded_diagnostics": graded["expanded_diagnostics"],
        "supplementary": supplementary, "routing_abstentions": abstentions,
        "semantic_oracle_ceiling": _oracle_ceiling(unique), "operational": operational,
        "limitations": [
            "AI synthetic documents and gold, correlated families, and one requested model; no deployment risk estimate or independent human-gold claim.",
            "The intervention permits contextual QA among the same supplied candidates; it does not test unrestricted general-knowledge answers.",
            "QA exact matching rejects correct paraphrases; no output repair or model-assisted adjudication is performed.",
            "An answer or incidental QA entity ID never authorizes execution. Routing retains the original execution guard and authored semantic gold.",
            "Null on guard-blocked positive routing is policy compliant and still a semantic miss; malformed and missing outputs are never safe abstention.",
            "Paired flips exclude missing outputs and count malformed outputs as failures. Planned denominators and incomplete pairs are reported separately.",
            "The oracle ceiling supplies authored answers and isolates the execution guard; it does not establish evidence sufficiency or attainable LLM quality.",
            "Latency includes actual attempts, including failures; shared-host contention can affect it. Missing calls have no imputed latency.",
            "Model advertisement is preserved; checkpoint weight revision is not established by these artifacts.",
            "This is a new within-run policy comparison; aggregate differences from earlier v1/v2 runs are not a causal policy effect.",
        ]}


def render_markdown(summary):
    counts, diagnostics = summary["counts"], summary["policy_diagnostics"]
    by_condition = diagnostics["by_condition"]
    lines = ["# QA and execution policy separation experiment", "",
        f"Run status: **{summary['status']}**. {counts['documents']} AI synthetic documents, "
        f"{counts['task_cases']} task cases and {counts['request_count']} planned calls. "
        "Gold has not been human verified.", "",
        f"Model: `{summary['requested_model']}`. Code revision: `{summary['code_revision']}`. "
        f"Request SHA-256: `{summary['request_corpus_sha256']}`.", "",
        f"Decoding: `{json.dumps(summary['decoding'], sort_keys=True)}`. "
        f"Received {counts['received_count']}; missing {counts['missing_count']}; malformed "
        f"{counts['malformed_count']}; transport/API errors {counts['error_count']}.", "",
        "The two conditions use the same surface-bound candidate facts and authored answers. "
        "`qa_context` permits QA to choose a definition from those candidates using document context. "
        "Execution IDs still require the frozen resolver guard. QA answer correctness and any incidental "
        "QA entity ID are measured separately. COMPLETE means response coverage, not reliable task performance.", "",
        "## Primary contextual-collision outcomes", "",
        "| Condition | QA correct / planned | Null | Malformed | Missing | Both contrast members correct / pairs | Incomplete pairs |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        values = by_condition[condition]
        qa = values["by_stratum"].get("contextual_collision", {}).get("document_qa", {})
        pair = values["contextual_pairs"]
        lines.append(f"| {condition} | {qa.get('correct', 0)}/{qa.get('planned', 0)} | "
            f"{qa.get('null', 0)} | {qa.get('malformed', 0)} | {qa.get('missing', 0)} | "
            f"{pair['both_correct']}/{pair['planned']} | {pair['incomplete']} |")
    lines += ["", "Both members must be correct to pass a contrast pair; selecting a fixed candidate cannot pass both. "
        "Incomplete responses remain failures in planned denominators.", "", "## All tasks and routing guard", "",
        "| Condition | QA correct / planned | Routing correct / planned | Correct routing ID blocked | Wrong routing ID accepted | Policy-compliant null on blocked gold | Avoidable null on authorized gold |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        values = by_condition[condition]["by_task"]
        qa, routing = values["document_qa"], values["structured_routing"]
        old_routing = summary["expanded_diagnostics"][condition]["by_task"]["structured_routing"]
        nulls = summary["routing_abstentions"][condition]
        blocked_correct = old_routing["semantic_match"] - old_routing["success"]
        lines.append(f"| {condition} | {qa['correct']}/{qa['planned']} | {routing['correct']}/{routing['planned']} | "
            f"{blocked_correct} | {old_routing['accepted_unauthorized_ids']} | "
            f"{nulls['policy_compliant_null_on_guard_blocked_positive']} | "
            f"{nulls['avoidable_null_on_guard_authorized_positive']} |")
    ceiling = summary["semantic_oracle_ceiling"]
    lines += ["", f"Semantic oracle ceiling with the execution guard: {ceiling['success_ceiling']}/{ceiling['planned']}. "
        "Guard acceptance alone is not semantic correctness. A correct but unapproved ID stays blocked.", "",
        "## Negative QA controls", "",
        "A non-null answer on negative authored gold is an unsupported answer under this rubric. "
        "Rates use all planned negative cases; valid-response denominators are also retained in summary.json.", "",
        "| Condition | Stratum | Non-null / planned | Valid null | Valid responses |",
        "|---|---|---:|---:|---:|"]
    for condition in CONDITIONS:
        for stratum, values in summary["supplementary"][condition]["negative_qa_controls"].items():
            lines.append(f"| {condition} | {stratum} | {values['nonnull']}/{values['planned']} | {values['null']} | {values['valid']} |")
    lines += ["", "## Incidental QA IDs", "",
        "These IDs do not enter QA answer correctness and carry no execution authority. "
        "Well-typed IDs in malformed QA responses are still audited; the malformed response remains a task failure. "
        "The guard below is a diagnostic evaluation of the unchanged execution policy.", "",
        "| Condition | Non-null IDs | Correct but blocked | Wrong and guard-accepted | Wrong and blocked | Correct answer with blocked ID |",
        "|---|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        values = summary["supplementary"][condition]["qa_incidental_id_semantics"]
        lines.append(f"| {condition} | {values['nonnull']} | {values['correct_blocked']} | "
            f"{values['wrong_authorized']} | {values['wrong_blocked']} | {values['answer_correct_with_blocked_id']} |")
    lines += ["", "## Paired changes versus strict", "",
        "| Task | Comparable | Helpful | Harmful | Incomplete |", "|---|---:|---:|---:|---:|"]
    for task, values in diagnostics["paired_changes"]["by_task"].items():
        lines.append(f"| {task} | {values['comparable']} | {values['helpful']} | {values['harmful']} | {values['incomplete']} |")
    lines += ["", "Per-stratum changes and both-members-correct pair changes are retained in summary.json.", "",
        "## Latency and tokens", "",
        "| Condition | Attempts | p50 ms | p95 ms | p99 ms | Prompt tokens | Completion tokens | Length finishes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        op = summary["operational"][condition]
        latency, usage = op["latency_ms"], op["actual_usage"]
        values = ["n/a" if latency[key] is None else f"{latency[key]:,.3f}" for key in ("p50", "p95", "p99")]
        lines.append(f"| {condition} | {op['attempted']} | " + " | ".join(values) +
            f" | {usage['prompt_tokens']['total']} | {usage['completion_tokens']['total']} | {op['finish_reason_counts'].get('length', 0)} |")
    lines += ["", "## Limits and provenance", ""]
    lines += [f"- {limit}" for limit in summary["limitations"]]
    lines += ["", "All three artifact hashes, the manifest seal, response identities and counts were verified. "
        "The complete recorded model grade was recomputed from frozen requests and responses; current fixtures "
        "were not loaded. Source document/candidate hashes and the declared source protocol are retained in summary.json.", "",
        f"Manifest seal: `{summary['verified_manifest_seal_sha256']}`.", "",
        "Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), "
        "[responses](responses.jsonl), [grades](graded.json).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = prepare_report(args.run_dir)
    (args.run_dir / "summary.json").write_bytes(_json_bytes(summary))
    (args.run_dir / "RESULTS.md").write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps({"run_dir": str(args.run_dir), "status": summary["status"], **summary["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

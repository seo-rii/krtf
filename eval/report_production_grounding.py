"""Verify and report frozen production QA/execution runs and paired model comparisons."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from eval.production_grounding import (
    TASKS, grade_production_outputs, production_response_error,
)
from eval.report_synthetic_grounding import ARTIFACTS, _distribution, _json_bytes
from ktrf.context import validate_llm_grounding

PROTOCOLS = {
    "production_synthetic": "production_grounding_synthetic_v1",
    "production_real": "production_grounding_real_holdout_v1",
}


def _verify_requests(requests, protocol):
    """Check frozen identities and paired task facts, without building new requests."""
    known, documents = {}, defaultdict(dict)
    fixed = ("family_id", "domain", "stratum", "text", "target_surface", "target_span",
             "document_sha256", "gold", "expected_answer", "expected_entity_id",
             "provenance", "snapshot_id", "contrast_pair_id", "contrast_member")
    for row in requests:
        key = (row["case_id"], row["condition"])
        if key in known or row["condition"] != "production" or row["task"] not in TASKS:
            raise ValueError("duplicate request or unknown production condition/task")
        known[key] = row
        if row["task"] in documents[row["document_id"]]:
            raise ValueError("duplicate document task")
        documents[row["document_id"]][row["task"]] = row
        expected_profile = "qa_grounding" if row["task"] == "document_qa" else "automation"
        if (row["pack"].get("profile") != expected_profile or
                row["context_policy"].get("profile") != expected_profile):
            raise ValueError("frozen request has the wrong production profile")
        budget = protocol.get("context_budget")
        if not isinstance(budget, dict) or any(row["context_policy"].get(k) != v for k, v in budget.items()):
            raise ValueError("request context budget disagrees with frozen protocol")
    if not documents or any(set(rows) != set(TASKS) for rows in documents.values()):
        raise ValueError("every document requires separate QA and execution tasks")
    for rows in documents.values():
        qa, execution = rows["document_qa"], rows["structured_routing"]
        if any(qa.get(field) != execution.get(field) for field in fixed):
            raise ValueError("document tasks disagree on frozen source facts or gold")
    return known


def _operational(rows, records):
    keys = {(row["case_id"], row["condition"]) for row in rows}
    attempts = [record for record in records if (record["case_id"], record["condition"]) in keys]
    latency = [record["latency_ms"] for record in attempts
               if type(record.get("latency_ms")) in (int, float)
               and math.isfinite(record["latency_ms"]) and record["latency_ms"] >= 0]
    usage = {key: _distribution([record["usage"][key] for record in attempts
             if isinstance(record.get("usage"), dict) and type(record["usage"].get(key)) is int
             and record["usage"][key] >= 0])
             for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    received = sum("response" in record for record in attempts)
    return {"planned": len(rows), "attempted": len(attempts), "received": received,
        "missing": len(rows) - received, "not_attempted": len(rows) - len(attempts),
        "errors": sum(record.get("error") is not None for record in attempts),
        "malformed": sum(record["status"] == "MALFORMED" for record in attempts),
        "status_counts": dict(Counter(record["status"] for record in attempts)),
        "finish_reason_counts": dict(Counter(str(record.get("finish_reason")) for record in attempts)),
        "latency_ms": _distribution(latency), "actual_usage": usage,
        "estimated_input_tokens": _distribution([row["estimated_input_tokens"] for row in rows]),
        "injected": sum(row["injected"] for row in rows)}


def _routing_diagnostics(requests, cases):
    """Policy-compliant abstention remains a miss against positive semantic gold."""
    counts = Counter()
    keys = ("planned", "positive_planned", "gold_guard_authorized", "gold_guard_blocked",
            "semantic_oracle_success_ceiling", "policy_compliant_null_on_guard_blocked_positive",
            "avoidable_null_on_guard_authorized_positive", "correct_id_blocked",
            "wrong_id_accepted", "wrong_id_blocked", "missing_positive", "malformed_positive")
    by_case = {case["case_id"]: case for case in cases}
    for row in requests:
        if row["task"] != "structured_routing":
            continue
        counts["planned"] += 1
        expected = row["expected_entity_id"]
        permitted = validate_llm_grounding({"selections": [{"surface": row["target_surface"],
            "entity_id": expected}]}, row["pack"], purpose="execution")["valid"]
        counts["semantic_oracle_success_ceiling"] += permitted
        case = by_case[row["case_id"]]
        if expected is not None:
            counts["positive_planned"] += 1
            counts["gold_guard_authorized" if permitted else "gold_guard_blocked"] += 1
            counts["missing_positive"] += case["missing"]
            counts["malformed_positive"] += bool(case.get("malformed"))
            if case.get("null"):
                counts["avoidable_null_on_guard_authorized_positive" if permitted else
                       "policy_compliant_null_on_guard_blocked_positive"] += 1
        if case.get("nonnull"):
            if case["value"] == expected and not case["raw_guard_valid"]:
                counts["correct_id_blocked"] += 1
            elif case["value"] != expected:
                counts["wrong_id_accepted" if case["raw_guard_valid"] else "wrong_id_blocked"] += 1
    return {key: counts[key] for key in keys}


def _paired_changes(baseline, current):
    """Only identical frozen requests support a within-case model comparison."""
    if (baseline["request_corpus_sha256"] != current["request_corpus_sha256"] or
            baseline["track"] != current["track"] or baseline["protocol"] != current["protocol"] or
            baseline["declared_protocol"] != current["declared_protocol"] or
            baseline["decoding"] != current["decoding"]):
        raise ValueError("paired comparison requires identical frozen requests, protocol and decoding")
    old = {case["case_id"]: case for case in baseline["metrics"]["cases"]}
    new = {case["case_id"]: case for case in current["metrics"]["cases"]}
    if set(old) != set(new):
        raise ValueError("paired comparison case identities differ")

    def changes(case_ids):
        comparable = [key for key in case_ids if not old[key]["missing"] and not new[key]["missing"]]
        helpful = [key for key in comparable if not old[key]["correct"] and new[key]["correct"]]
        harmful = [key for key in comparable if old[key]["correct"] and not new[key]["correct"]]
        return {"planned": len(case_ids), "comparable": len(comparable),
            "incomplete": len(case_ids) - len(comparable), "helpful": len(helpful), "harmful": len(harmful),
            "both_correct": sum(old[key]["correct"] and new[key]["correct"] for key in comparable),
            "both_incorrect": sum(not old[key]["correct"] and not new[key]["correct"] for key in comparable),
            "helpful_case_ids": helpful, "harmful_case_ids": harmful}

    return {"baseline_model": baseline["requested_model"], "current_model": current["requested_model"],
        "baseline_manifest_seal_sha256": baseline["verified_manifest_seal_sha256"],
        "request_corpus_sha256": current["request_corpus_sha256"],
        "overall": changes(sorted(old)),
        "by_task": {task: changes(sorted(key for key in old if old[key]["task"] == task)) for task in TASKS},
        "by_stratum": {stratum: {task: changes(sorted(key for key in old if
            old[key]["task"] == task and old[key]["stratum"] == stratum)) for task in TASKS}
            for stratum in sorted({case["stratum"] for case in old.values()})},
        "interpretation": "Paired model comparison on identical inputs; model families, training and serving differ. "
                          "This does not isolate model size. Missing pairs are incomplete; malformed outputs are failures."}


def prepare_report(run_dir, *, compare=None):
    """Read only frozen artifacts, verify them, regrade, and return a report value."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("track") not in PROTOCOLS or manifest.get("protocol") != PROTOCOLS[manifest["track"]]:
        raise ValueError("report requires a production track and its matching protocol")
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
    protocol = manifest.get("declared_protocol")
    if (not isinstance(protocol, dict) or protocol.get("kind") != manifest["protocol"] or
            not isinstance(protocol.get("gold_origin"), str) or not protocol["gold_origin"] or
            type(protocol.get("human_verified")) is not bool or
            not isinstance(protocol.get("limitations"), list)):
        raise ValueError("frozen protocol must declare matching identity, gold origin and limitations")
    requests = [json.loads(line) for line in contents["requests.jsonl"].splitlines() if line.strip()]
    records = [json.loads(line) for line in contents["responses.jsonl"].splitlines() if line.strip()]
    known, recorded = _verify_requests(requests, protocol), {}
    for record in records:
        key = (record["case_id"], record["condition"])
        if key not in known or key in recorded:
            raise ValueError("unknown or duplicate response key")
        status = record.get("status")
        if status not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown response status")
        if (status in {"RECEIVED", "MALFORMED"}) != ("response" in record):
            raise ValueError("response presence disagrees with status")
        if "response" in record and not isinstance(record["response"], dict):
            raise ValueError("parsed response must be an object")
        if status == "RECEIVED" and production_response_error(record["response"], known[key]) is not None:
            raise ValueError("RECEIVED response violates the task schema")
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
    recomputed = grade_production_outputs(requests, [record for record in records if "response" in record])
    recomputed["limitations"] = list(protocol["limitations"])
    graded = json.loads(contents["graded.json"])["model_results"]
    if graded != recomputed or graded.get("missing_outputs") != counts["missing_count"]:
        raise ValueError("recorded grades disagree with frozen regrading")
    documents = [row for row in requests if row["task"] == "document_qa"]
    parent_ids = {row["provenance"].get("parent_document_id") for row in documents}
    summary = {"kind": "sealed_production_grounding_report", "status": manifest["status"],
        "track": manifest["track"], "protocol": manifest["protocol"],
        "annotation_origin": protocol["gold_origin"], "human_verified": protocol["human_verified"],
        "quality_claim": False,
        **{key: manifest.get(key) for key in ("code_revision", "requested_model", "served_models", "endpoint",
            "started_at", "finished_at", "decoding", "declared_protocol", "request_provenance", "request_corpus_sha256")},
        "verified_manifest_seal_sha256": seal, "verified_artifact_sha256": hashes,
        "counts": {**counts, "attempted_count": len(records), "not_attempted_count": len(requests) - len(records),
            "documents": len(documents), "source_parent_documents": len(parent_ids) if None not in parent_ids else None,
            "families": len({row["family_id"] for row in documents})},
        "strata": dict(Counter(row["stratum"] for row in documents)),
        "gold_labels": dict(Counter(row["gold"]["label"] for row in documents)),
        "source_document_hashes": {row["document_id"]: row["document_sha256"] for row in documents},
        "metrics": graded, "routing_diagnostics": _routing_diagnostics(requests, graded["cases"]),
        "operational": {"overall": _operational(requests, records),
            **{task: _operational([row for row in requests if row["task"] == task], records) for task in TASKS}},
        "limitations": [*protocol["limitations"],
            "Gold origin and verification are copied from the sealed protocol; real documents do not imply human-verified entity-linking gold.",
            "This run does not establish deployment risk or an independent human-gold guarantee.",
            "QA explanations never authorize execution. QA IDs violate the response contract and are counted separately.",
            "Execution receives its own automation context; the complete response reaches the guard without ID projection or repair.",
            "Null on guard-blocked positive gold can obey the policy while remaining a semantic miss.",
            "Missing counts include transport/API failures and unattempted requests; malformed received responses are separate and never safe abstentions.",
            "COMPLETE means response coverage, including malformed responses, not reliable task performance.",
            "Latency includes recorded attempts, including failures; shared-host contention and serving configurations affect timing.",
            "Advertised model identities are recorded; the report alone does not establish checkpoint weight revision.",
        ]}
    if compare is not None:
        summary["comparison"] = _paired_changes(prepare_report(compare), summary)
    return summary


def render_markdown(summary):
    counts, metrics = summary["counts"], summary["metrics"]
    lines = ["# Production QA and execution evaluation", "",
        f"Run status: **{summary['status']}**. {counts['documents']} target passages and "
        f"{counts['request_count']} planned separate QA/execution calls.", "",
        f"Gold origin: `{summary['annotation_origin']}`; human verified: `{str(summary['human_verified']).lower()}`. "
        "No deployment-risk guarantee is claimed.", "",
        f"Model: `{summary['requested_model']}`. Code revision: `{summary['code_revision']}`. "
        f"Request SHA-256: `{summary['request_corpus_sha256']}`.", "",
        f"Decoding: `{json.dumps(summary['decoding'], sort_keys=True)}`. Context budget: "
        f"`{json.dumps(summary['declared_protocol'].get('context_budget'), sort_keys=True)}`.", "",
        "The production path uses actual XML context and the prepared policy, respecting `should_inject`. "
        "QA and automation use separate calls and profiles. The 6000-token context allowance is explicitly "
        "larger than the 800-token default. QA-generated IDs do not enter execution.", "",
        f"Received {counts['received_count']}; missing {counts['missing_count']} "
        f"(including {counts['error_count']} errors and {counts['not_attempted_count']} unattempted); "
        f"malformed {counts['malformed_count']}. COMPLETE describes coverage, not task quality.", "",
        "## Task outcomes", "",
        "| Task | Correct / planned | Semantic match | Valid null | Malformed | Missing |",
        "|---|---:|---:|---:|---:|---:|"]
    for task in TASKS:
        values = metrics["by_task"][task]
        lines.append(f"| {task} | {values['correct']}/{values['planned']} | {values['semantic_match']} | "
            f"{values['null']} | {values['malformed']} | {values['missing']} |")
    pairs = metrics["contextual_pairs"]
    lines += ["", f"Contextual contrast pairs: both correct **{pairs['both_correct']}/{pairs['planned']}**; "
        f"complete {pairs['complete']}; incomplete {pairs['planned'] - pairs['complete']}.", "",
        "QA exact-definition success includes response-schema compliance. Routing semantic matches require "
        "guard approval to count as correct. Malformed and missing outputs cannot earn null credit.", "",
        "## Strata", "", "| Stratum | Task | Correct / planned | Malformed | Missing |",
        "|---|---|---:|---:|---:|"]
    for stratum, tasks in metrics["by_stratum"].items():
        for task in TASKS:
            values = tasks[task]
            lines.append(f"| {stratum} | {task} | {values['correct']}/{values['planned']} | "
                f"{values['malformed']} | {values['missing']} |")
    route, qa = summary["routing_diagnostics"], metrics["by_task"]["document_qa"]
    lines += ["", "## Execution boundary and QA schema", "",
        "| Measure | Count |", "|---|---:|",
        f"| Wrong routing ID accepted by guard | {route['wrong_id_accepted']} |",
        f"| Wrong routing ID blocked | {route['wrong_id_blocked']} |",
        f"| Semantically correct routing ID blocked | {route['correct_id_blocked']} |",
        f"| Policy-compliant null on blocked positive gold | {route['policy_compliant_null_on_guard_blocked_positive']} |",
        f"| Avoidable null on authorized positive gold | {route['avoidable_null_on_guard_authorized_positive']} |",
        f"| QA responses containing forbidden ID fields | {qa['qa_unexpected_ids']} |",
        f"| QA responses with non-null forbidden IDs | {qa['qa_unexpected_id_nonnull']} |", "",
        f"Routing semantic-oracle ceiling under the frozen guard: "
        f"{route['semantic_oracle_success_ceiling']}/{route['planned']}. "
        "This diagnoses authorization limits; it does not establish attainable model performance.", "",
        "## Cost", "",
        "| Task | Injected / planned | Latency observations | p50 ms | p95 ms | p99 ms | Prompt tokens | Completion tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for task in TASKS:
        values = summary["operational"][task]
        latency, usage = values["latency_ms"], values["actual_usage"]
        lines.append(f"| {task} | {values['injected']}/{values['planned']} | {latency['observations']} | "
            f"{latency['p50']} | {latency['p95']} | {latency['p99']} | "
            f"{usage['prompt_tokens']['total']} | {usage['completion_tokens']['total']} |")
    if "comparison" in summary:
        comparison = summary["comparison"]
        lines += ["", "## Paired model comparison", "",
            f"Baseline `{comparison['baseline_model']}` → current `{comparison['current_model']}`. "
            "Identical request hashes, protocols and decoding were verified.", "",
            "| Task | Comparable | Helpful | Harmful | Incomplete |", "|---|---:|---:|---:|---:|"]
        for task, values in comparison["by_task"].items():
            lines.append(f"| {task} | {values['comparable']} | {values['helpful']} | "
                f"{values['harmful']} | {values['incomplete']} |")
        lines += ["", comparison["interpretation"]]
    lines += ["", "## Reproduction and limitations", "",
        "All three artifact hashes, the canonical manifest seal, request/response identities, counts and frozen "
        "regrading were verified. No current corpus fixtures are loaded by this report.", "",
        f"Manifest seal: `{summary['verified_manifest_seal_sha256']}`.", "",
        "Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), "
        "[responses](responses.jsonl), [grades](graded.json).", "",
        *("- " + limitation for limitation in summary["limitations"]), ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compare", type=Path, help="Sealed baseline run with identical requests and decoding")
    args = parser.parse_args()
    summary = prepare_report(args.run_dir, compare=args.compare)
    (args.run_dir / "summary.json").write_bytes(_json_bytes(summary))
    (args.run_dir / "RESULTS.md").write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps({"run_dir": str(args.run_dir), "status": summary["status"], **summary["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

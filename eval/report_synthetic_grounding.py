"""Report a sealed synthetic expansion run without reading mutable fixtures."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from ktrf.context import validate_llm_grounding

CONDITIONS = ("original", "surface_only", "schema_only", "both", "full_pack")
ARTIFACTS = ("requests.jsonl", "responses.jsonl", "graded.json")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _distribution(values):
    values = sorted(values)
    if not values:
        return {"observations": 0, "total": 0, "min": None, "max": None,
                "p50": None, "p95": None, "p99": None}
    quantiles = {}
    for name, fraction in (("p50", .5), ("p95", .95), ("p99", .99)):
        position = (len(values) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        quantiles[name] = round(values[low] + (values[high] - values[low]) * (position - low), 3)
    return {"observations": len(values), "total": sum(values),
            "min": values[0], "max": values[-1], **quantiles}


def _correct(row, record):
    """Score only frozen expected values and the original execution pack."""
    if not record or record.get("status") != "RECEIVED":
        return False
    response = record.get("response")
    if not isinstance(response, dict):
        return False
    field = "answer" if row["task"] == "document_qa" else "entity_id"
    if field not in response:
        return False
    value = response[field]
    if value is not None and (not isinstance(value, str) or
                              (field == "entity_id" and not value.strip())):
        return False
    expected = row["expected_answer"] if field == "answer" else row["expected_entity_id"]
    if value != expected:
        return False
    if field == "entity_id":
        return validate_llm_grounding({"selections": [{
            "surface": row["target_surface"], "entity_id": value}]},
            row["pack"], purpose="execution")["valid"]
    return True


def prepare_report(run_dir):
    """Verify frozen artifacts and return a summary, without changing files."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("track") != "synthetic_expansion" or manifest.get("protocol") != "synthetic_grounding_expansion_v1":
        raise ValueError("report requires the synthetic_expansion track")
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(_json_bytes(unsealed)).hexdigest() != seal:
        raise ValueError("invalid manifest seal")
    artifact_hashes = manifest.get("artifact_sha256", {})
    if set(artifact_hashes) != set(ARTIFACTS):
        raise ValueError("manifest must seal all three run artifacts")
    contents = {}
    for name in ARTIFACTS:
        contents[name] = (run_dir / name).read_bytes()
        if hashlib.sha256(contents[name]).hexdigest() != artifact_hashes[name]:
            raise ValueError(f"artifact hash mismatch: {name}")
    if manifest.get("request_corpus_sha256") != artifact_hashes["requests.jsonl"]:
        raise ValueError("request corpus hash disagrees with sealed artifact")
    requests = [json.loads(line) for line in contents["requests.jsonl"].splitlines() if line.strip()]
    records = [json.loads(line) for line in contents["responses.jsonl"].splitlines() if line.strip()]
    graded = json.loads(contents["graded.json"])["model_results"]
    diagnostics = graded.get("expanded_diagnostics")
    if not isinstance(diagnostics, dict) or set(diagnostics) != set(CONDITIONS):
        raise ValueError("expanded diagnostics must contain the five declared conditions")
    known = {(row["case_id"], row["condition"]): row for row in requests}
    if len(known) != len(requests) or set(row["condition"] for row in requests) != set(CONDITIONS):
        raise ValueError("duplicate requests or incorrect conditions")
    recorded = {}
    for record in records:
        key = (record["case_id"], record["condition"])
        if key not in known or key in recorded:
            raise ValueError("unknown or duplicate response key")
        if record.get("status") not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown response status")
        recorded[key] = record
    received = sum("response" in record for record in records)
    missing = len(requests) - received
    errors = sum(record.get("error") is not None for record in records)
    malformed = sum(record["status"] == "MALFORMED" for record in records)
    counts = {"request_count": len(requests), "received_count": received,
              "missing_count": missing, "error_count": errors, "malformed_count": malformed}
    if any(manifest.get(key) != value for key, value in counts.items()) or graded.get("missing_outputs") != missing:
        raise ValueError("sealed manifest or grader counts disagree with records")
    if manifest.get("status") != ("COMPLETE" if not missing and not errors else "INCOMPLETE"):
        raise ValueError("run completion status disagrees with records")

    comparisons, operational = {}, {}
    for condition in CONDITIONS:
        rows = [row for row in requests if row["condition"] == condition]
        attempts = [record for record in records if record["condition"] == condition]
        diagnostic = diagnostics[condition]
        if diagnostic["overall"]["observed"] != sum("response" in record for record in attempts):
            raise ValueError("diagnostic observed count disagrees with records")
        successes = sum(_correct(row, recorded.get((row["case_id"], condition))) for row in rows)
        if diagnostic["overall"]["success"] != successes:
            raise ValueError("diagnostic success count disagrees with frozen responses")
        paired = [(row, recorded[(row["case_id"], condition)],
                   recorded[(row["case_id"], "original")]) for row in rows
                  if "response" in recorded.get((row["case_id"], condition), {})
                  and "response" in recorded.get((row["case_id"], "original"), {})]
        comparisons[condition] = {"paired_with_original": len(paired),
            "helpful_flip": sum(not _correct(known[(row["case_id"], "original")], before)
                                and _correct(row, after) for row, after, before in paired),
            "harmful_flip": sum(_correct(known[(row["case_id"], "original")], before)
                                and not _correct(row, after) for row, after, before in paired),
            "missing_pairs": len(rows) - len(paired)}
        latency = [record["latency_ms"] for record in attempts
                   if type(record.get("latency_ms")) in (int, float)
                   and math.isfinite(record["latency_ms"]) and record["latency_ms"] >= 0]
        usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage[key] = _distribution([record["usage"][key] for record in attempts
                if isinstance(record.get("usage"), dict) and type(record["usage"].get(key)) is int
                and record["usage"][key] >= 0])
        operational[condition] = {"expected": len(rows), "attempted": len(attempts),
            "received": sum("response" in record for record in attempts),
            "missing": len(rows) - sum("response" in record for record in attempts),
            "malformed": sum(record["status"] == "MALFORMED" for record in attempts),
            "status_counts": dict(Counter(record["status"] for record in attempts)),
            "finish_reason_counts": dict(Counter(str(record.get("finish_reason")) for record in attempts)),
            "latency_ms": _distribution(latency), "actual_usage": usage,
            "estimated_input_tokens": sum(row["estimated_input_tokens"] for row in rows)}
    unique = [row for row in requests if row["condition"] == "original"]
    docs = {row["document_id"]: row for row in unique}
    return {"kind": "sealed_synthetic_grounding_report", "status": manifest["status"],
        "annotation_origin": "AI_SYNTHETIC", "human_verified": False,
        "code_revision": manifest["code_revision"], "requested_model": manifest["requested_model"],
        "served_models": manifest.get("served_models"), "endpoint": manifest["endpoint"],
        "started_at": manifest["started_at"], "finished_at": manifest["finished_at"],
        "decoding": manifest["decoding"], "request_corpus_sha256": manifest["request_corpus_sha256"],
        "verified_manifest_seal_sha256": seal, "verified_artifact_sha256": artifact_hashes,
        "counts": {**counts, "attempted_count": len(records), "families": len({row["family_id"] for row in unique}),
                   "documents": len(docs), "task_cases": len(unique)},
        "gold_labels": dict(Counter(row["gold"]["label"] for row in docs.values())),
        "strata": dict(Counter(row["stratum"] for row in docs.values())),
        "expanded_diagnostics": diagnostics, "paired_vs_original": comparisons,
        "operational": operational, "quality_claim": False,
        "limitations": ["AI-authored synthetic documents and gold; not independent human gold or deployment traffic.",
            "Family clusters are correlated; family macro is descriptive, without a risk bound or risk certification.",
            "full_pack is a separate information reference beyond the isolated four-condition 2x2.",
            "QA exact-match grading can reject correct paraphrases; no model-assisted repair or adjudication is performed.",
            "The output cap is recorded in decoding (planned 128 tokens); length finishes can constrain answers.",
            "Missing and malformed outputs are failures, never safe abstention; COMPLETE denotes transport coverage, not task success.",
            "Routing success requires semantic correctness and the original execution guard; guard acceptance alone is not semantic correctness.",
            "The execution guard is surface-based; explicit occurrence spans in prompts do not make it occurrence-aware.",
            "Latency includes recorded attempts, including failed attempts; shared-host contention can affect it, and absent outputs have no imputed latency.",
            "Advertised model identity is recorded; checkpoint weight revision is not established by these artifacts."]}


def render_markdown(summary):
    counts, diagnostics = summary["counts"], summary["expanded_diagnostics"]
    def percentage(value):
        return "n/a" if value is None else f"{100 * value:.2f}%"
    def number(value):
        return "n/a" if value is None else f"{value:,.3f}"
    def main_row(condition):
        overall = diagnostics[condition]["overall"]
        operation = summary["operational"][condition]
        return (f"| {condition} | {overall['success']}/{operation['expected']} | "
                f"{percentage(diagnostics[condition]['family_macro_success'])} | "
                f"{overall['answerable_success']}/{overall['answerable']} | "
                f"{overall['over_abstention']} | {overall['safe_abstention']} | "
                f"{operation['malformed']} | {operation['missing']} |")
    lines = ["# Expanded synthetic grounding experiment", "",
        f"Run status: **{summary['status']}**. {counts['families']} AI-authored families, "
        f"{counts['documents']} distinct documents, {counts['task_cases']} task cases and "
        f"{counts['request_count']} planned calls. Gold is AI synthetic and has not been human verified.", "",
        f"Model: `{summary['requested_model']}`. Code revision: `{summary['code_revision']}`. "
        f"Request SHA-256: `{summary['request_corpus_sha256']}`.", "",
        f"Decoding: `{json.dumps(summary['decoding'], sort_keys=True)}`. "
        "The planned output cap is 128 tokens; finish reasons and actual usage below show whether this bound affected outputs.", "",
        f"Received {counts['received_count']}/{counts['request_count']}; missing {counts['missing_count']}, "
        f"malformed {counts['malformed_count']}, transport/API errors {counts['error_count']}. "
        "COMPLETE means response coverage, not successful or reliable task performance.", "",
        "## Controlled 2×2 input comparison", "",
        "The four cells keep candidate facts, questions, system policy and execution guard fixed. "
        "Surface bindings and policy-named fields are the declared factors.", "",
        "| Condition | Success / planned | Family macro (observed) | Answerable success / observed | Over-abstention | Safe abstention | Malformed | Missing |",
        "|---|---:|---:|---:|---:|---:|---:|---:|", *[main_row(c) for c in CONDITIONS[:4]], "",
        "Family macro averages observed task success within each family. Missing calls remain failures in the planned denominator "
        "and appear separately; family macro is descriptive over observed outputs.", "",
        "## Full-pack information reference", "",
        "This condition includes the full production context pack and may add information. "
        "It is separate from the isolated 2×2 comparison.", "",
        "| Condition | Success / planned | Family macro (observed) | Answerable success / observed | Over-abstention | Safe abstention | Malformed | Missing |",
        "|---|---:|---:|---:|---:|---:|---:|---:|", main_row("full_pack"), "",
        "## Task outcomes and execution guard", "",
        "| Condition | QA success / observed | Routing success / observed | Observed / planned | Semantic routing matches | Wrong non-null IDs | Guard rejections | Wrong IDs accepted by guard |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        tasks = diagnostics[condition]["by_task"]
        qa, routing = tasks["document_qa"], tasks["structured_routing"]
        lines.append(f"| {condition} | {qa['success']}/{qa['observed']} | "
            f"{routing['success']}/{routing['observed']} | "
            f"{summary['operational'][condition]['received']}/{summary['operational'][condition]['expected']} | "
            f"{routing['semantic_match']} | "
            f"{routing['wrong_ids']} | {routing['guard_rejections']} | {routing['accepted_unauthorized_ids']} |")
    lines += ["", "A wrong ID is measured against authored semantic gold. A guard rejection can also reject a "
        "semantically correct ID that the resolver did not authorize. The accepted-wrong-ID column counts "
        "semantic errors that passed the guard; it is not a deployment risk estimate.", "",
        "## Paired changes versus original", "",
        "Pairs use the same case ID in each condition. Malformed responses count as failures; "
        "missing responses are excluded from pairs and shown explicitly.", "",
        "| Condition | Pairs | Helpful flips | Harmful flips | Missing pairs |", "|---|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        pair = summary["paired_vs_original"][condition]
        lines.append(f"| {condition} | {pair['paired_with_original']} | {pair['helpful_flip']} | "
                     f"{pair['harmful_flip']} | {pair['missing_pairs']} |")
    lines += ["", "## Per-stratum success", "",
        "Entries show success / observed. These include both QA and routing tasks for the same documents.", "",
        "| Stratum | original | surface_only | schema_only | both | full_pack |", "|---|---:|---:|---:|---:|---:|"]
    for stratum in sorted(diagnostics["original"]["by_stratum"]):
        entries = [diagnostics[c]["by_stratum"][stratum] for c in CONDITIONS]
        lines.append(f"| {stratum} | " + " | ".join(f"{x['success']}/{x['observed']}" for x in entries) + " |")
    lines += ["", "## Recorded latency and token usage", "",
        "Latency percentiles use linear interpolation over actual recorded attempts, including failed attempts. "
        "There is no imputed latency for missing calls. Shared-host contention can affect these measurements.", "",
        "| Condition | Attempts | p50 ms | p95 ms | p99 ms | Actual prompt tokens | Actual completion tokens | Completion max | Length finishes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        op = summary["operational"][condition]
        latency, usage = op["latency_ms"], op["actual_usage"]
        lines.append(f"| {condition} | {op['attempted']} | {number(latency['p50'])} | {number(latency['p95'])} | "
            f"{number(latency['p99'])} | {usage['prompt_tokens']['total']} | {usage['completion_tokens']['total']} | "
            f"{usage['completion_tokens']['max'] if usage['completion_tokens']['max'] is not None else 'n/a'} | "
            f"{op['finish_reason_counts'].get('length', 0)} |")
    lines += ["", "Actual usage observation counts, totals and distributions are in `summary.json`; estimated input "
        "tokens are reported separately and do not replace API usage.", "", "## Limits and artifact verification", ""]
    lines.extend(f"- {limit}" for limit in summary["limitations"])
    lines += ["", "All three input artifact SHA-256 values and the canonical manifest seal were verified before this report "
        "was generated. This report reads only frozen requests, responses, graded diagnostics and manifest; "
        "it does not reload current fixtures.", "",
        f"Manifest seal: `{summary['verified_manifest_seal_sha256']}`.", "",
        "Artifacts: [summary](summary.json), [sealed manifest](run_manifest.json), [requests](requests.jsonl), "
        "[responses](responses.jsonl), [graded diagnostics](graded.json).", ""]
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

"""Verify private frozen HF QA artifacts and publish aggregate-only metrics."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from .hf_qa import CONDITIONS, PROTOCOL_ID, canonical, grade_outputs, response_error, validate_requests
from .report_synthetic_grounding import ARTIFACTS, _distribution


def read_run(run_dir):
    root = Path(run_dir)
    manifest = json.loads((root / "run_manifest.json").read_text())
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(canonical(unsealed)).hexdigest() != seal:
        raise ValueError("invalid HF run manifest seal")
    if manifest.get("track") != "hf_qa" or manifest.get("protocol") != PROTOCOL_ID:
        raise ValueError("wrong HF track/protocol")
    declared = manifest.get("declared_protocol", {})
    if (declared.get("kind") != PROTOCOL_ID or declared.get("phase") != "FINAL_FROZEN"
            or declared.get("conditions") != list(CONDITIONS)):
        raise ValueError("HF declared protocol differs from frozen comparison")
    data = {name: (root / name).read_bytes() for name in ARTIFACTS}
    if set(manifest["artifact_sha256"]) != set(ARTIFACTS):
        raise ValueError("all private artifacts must be sealed")
    if any(hashlib.sha256(value).hexdigest() != manifest["artifact_sha256"][name]
           for name, value in data.items()):
        raise ValueError("HF artifact hash mismatch")
    if manifest["request_corpus_sha256"] != manifest["artifact_sha256"]["requests.jsonl"]:
        raise ValueError("HF request hash mismatch")
    requests = [json.loads(line) for line in data["requests.jsonl"].splitlines()]
    records = [json.loads(line) for line in data["responses.jsonl"].splitlines()]
    validate_requests(requests)
    by_key = {(r["case_id"], r["condition"]): r for r in requests}
    seen = set()
    for record in records:
        key = (record["case_id"], record["condition"])
        if key not in by_key or key in seen:
            raise ValueError("unknown or duplicate recorded HF response")
        seen.add(key)
        status = record.get("status")
        if status not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown HF response status")
        if (status in {"RECEIVED", "MALFORMED"}) != ("response" in record):
            raise ValueError("response presence disagrees with status")
        if status == "RECEIVED" and response_error(record["response"]):
            raise ValueError("RECEIVED output violates answer contract")
        if (record.get("error") is not None) != (status in {"HTTP_ERROR", "TRANSPORT_ERROR"}):
            raise ValueError("response error/status disagree")
    outputs = [record for record in records if "response" in record]
    graded = grade_outputs(requests, outputs)
    graded["limitations"] = list(manifest["declared_protocol"]["limitations"])
    sealed_grades = json.loads(data["graded.json"])["model_results"]
    # Python 3.12 changed sum(float) to compensated summation. Permit only a
    # two-ULP aggregate difference; every individual score, label and count must
    # still match exactly. Keep the verified sealed totals for reproducible reports.
    for condition in CONDITIONS:
        expected = sealed_grades["by_condition"][condition]["positive_character_f1_sum"]
        actual = graded["by_condition"][condition]["positive_character_f1_sum"]
        if (type(expected) is float and math.isfinite(expected)
                and abs(expected - actual) <= 2 * math.ulp(actual)):
            graded["by_condition"][condition]["positive_character_f1_sum"] = expected
    if sealed_grades != graded:
        raise ValueError("HF grades differ from sealed local regrading")
    counts = {"request_count": len(requests), "received_count": len(outputs),
              "missing_count": graded["missing_outputs"],
              "malformed_count": sum(r["status"] == "MALFORMED" for r in records),
              "error_count": sum(r.get("error") is not None for r in records)}
    if any(manifest.get(key) != value for key, value in counts.items()):
        raise ValueError("HF manifest counts differ")
    if manifest["status"] != ("COMPLETE" if not counts["missing_count"] and not counts["error_count"] else "INCOMPLETE"):
        raise ValueError("HF manifest completion differs")
    return manifest, requests, records, graded, counts


def prepare_report(run_dir, *, compare=None):
    manifest, requests, records, graded, counts = read_run(run_dir)
    if compare is not None:
        old_manifest, old_requests, _, old_graded, _ = read_run(compare)
        for key in ("request_corpus_sha256", "code_revision", "decoding"):
            if manifest[key] != old_manifest[key]:
                raise ValueError("model comparison requires identical frozen requests/configuration")
        first = {(r["case_id"], r["condition"]): r for r in old_graded["cases"]}
        second = {(r["case_id"], r["condition"]): r for r in graded["cases"]}
        if set(first) != set(second):
            raise ValueError("model comparison case sets differ")
        comparisons = {}
        for condition in CONDITIONS:
            keys = [key for key in first if key[1] == condition
                    and (condition != "none_knowledge" or first[key]["positive_gold"])]
            comparable = [key for key in keys if not any(first[key][f] or second[key][f]
                                                       for f in ("missing", "malformed"))]
            comparisons[condition] = {"planned": len(keys), "comparable": len(comparable),
                "current_helpful": sum(not first[key]["exact_match"] and second[key]["exact_match"] for key in comparable),
                "current_harmful": sum(first[key]["exact_match"] and not second[key]["exact_match"] for key in comparable)}
        return {"protocol": PROTOCOL_ID, "comparison": True,
                "baseline_model": old_manifest["requested_model"], "current_model": manifest["requested_model"],
                "request_corpus_sha256": manifest["request_corpus_sha256"],
                "code_revision": manifest["code_revision"], "by_condition": comparisons,
                "limitations": list(manifest["declared_protocol"]["limitations"])}
    metrics = {}
    for condition, values in graded["by_condition"].items():
        calls = [r for r in records if r["condition"] == condition]
        usage, observed_usage = {}, {}
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage_values = [r["usage"].get(name) for r in calls if isinstance(r.get("usage"), dict)]
            usage_values = [value for value in usage_values if type(value) is int and value >= 0]
            usage[name], observed_usage[name] = sum(usage_values), len(usage_values)
        latencies = [r["latency_ms"] for r in calls]
        latency_summary = _distribution(latencies)
        latency_summary["total"] = math.fsum(latencies)
        metrics[condition] = {**values,
            "positive_exact_rate": values["positive_exact"] / values["positive_planned"] if values["positive_planned"] else None,
            "positive_character_f1_mean": values["positive_character_f1_sum"] / values["positive_planned"] if values["positive_planned"] else None,
            "source_no_answer_null_rate": (values["article_no_answer_null"] / values["no_answer_planned"]
                                           if values["no_answer_planned"] and condition != "none_knowledge" else None),
            "usage": usage, "usage_observed_responses": observed_usage,
            "latency_ms": latency_summary}
    return {"protocol": PROTOCOL_ID, "comparison": False, "model": manifest["requested_model"],
            "code_revision": manifest["code_revision"], "request_corpus_sha256": manifest["request_corpus_sha256"],
            "status": manifest["status"], "counts": counts, "decoding": manifest["decoding"],
            "questions": len({r["case_id"] for r in requests}),
            "parent_documents": len({r["parent_document_id"] for r in requests}),
            "by_condition": metrics, "paired": graded["paired"],
            "limitations": list(manifest["declared_protocol"]["limitations"]),
            "publication": "aggregate_only_no_source_text_or_individual_model_answers"}


def render_markdown(summary):
    if summary.get("comparison"):
        lines = ["# HF QA model comparison", "", f"Baseline: `{summary['baseline_model']}`; current: `{summary['current_model']}`.", "",
                 "Same frozen questions, conditions and decoding; model family and size both change.", "",
                 "| Condition | Comparable | Current helpful | Current harmful |", "|---|---:|---:|---:|"]
        for key, value in summary["by_condition"].items():
            lines.append(f"| {key} | {value['comparable']}/{value['planned']} | {value['current_helpful']} | {value['current_harmful']} |")
    else:
        lines = ["# HF TyDiQA generation results", "", f"Model: `{summary['model']}`. Status: `{summary['status']}`.", "",
                 f"Questions: {summary['questions']}; parent articles: {summary['parent_documents']}. Counts: `{summary['counts']}`.", "",
                 "These are generation normalized exact match and partial character-F1 diagnostics, not official TyDi byte-span F1.", "",
                 "| Condition | Positive exact | Article no-answer null | Malformed | Missing | Prompt tokens | p95 ms |",
                 "|---|---:|---:|---:|---:|---:|---:|"]
        for key, value in summary["by_condition"].items():
            negative = "unjudged" if key == "none_knowledge" else f"{value['article_no_answer_null']}/{value['no_answer_planned']}"
            lines.append(f"| {key} | {value['positive_exact']}/{value['positive_planned']} | {negative} | "
                         f"{value['malformed']} | {value['missing']} | {value['usage']['prompt_tokens']} | {value['latency_ms']['p95']} |")
        lines += ["", "Matched source-contract changes (incomplete/malformed pairs are separate):", "",
                  "```json", json.dumps(summary["paired"], indent=2), "```"]
    lines += ["", *["- " + limitation for limitation in summary["limitations"]], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = prepare_report(args.run_dir)
    (args.run_dir / "summary.json").write_bytes(canonical(summary))
    (args.run_dir / "RESULTS.md").write_text(render_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

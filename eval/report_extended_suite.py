"""Verify sealed extended runs, reparse model output, and publish only aggregates."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from .hf_qa import canonical
from .report_synthetic_grounding import _distribution
from .run_extended_suite import (ANSWER_SCHEMA, ARTIFACTS, DECODING, PROTOCOL_ID,
                                 ROUTING_SCHEMA, grade_outputs, load_request_file,
                                 output_error, decoding_for, schema_for, validate_protocol, AUDITED_CONDITION_COUNTS,
                                 _metrics)
from .run_product_llm import parse_model_json


def read_run(run_dir):
    root = Path(run_dir)
    manifest = json.loads((root / "run_manifest.json").read_text())
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(canonical(unsealed)).hexdigest() != seal:
        raise ValueError("invalid extended manifest seal")
    validate_protocol(manifest.get("declared_protocol"))
    if (manifest.get("protocol") != PROTOCOL_ID or manifest.get("track") != "extended_suite"
            or manifest.get("decoding") != decoding_for(manifest["declared_protocol"])
            or manifest.get("prompt_fields") != ["system", "user"]
            or manifest.get("retries") != 0 or manifest.get("schema_transport") != "response_format.json_schema.strict"):
        raise ValueError("extended protocol or fixed decoding differs")
    if set(manifest.get("artifact_sha256", {})) != set(ARTIFACTS):
        raise ValueError("all extended private artifacts must be sealed")
    data = {name: (root / name).read_bytes() for name in ARTIFACTS}
    if any(hashlib.sha256(value).hexdigest() != manifest["artifact_sha256"][name] for name, value in data.items()):
        raise ValueError("extended artifact hash mismatch")
    rows, protocol, provenance = load_request_file(root / "frozen_envelope.json")
    schema = schema_for(rows, protocol)
    if (manifest.get("experiment") != protocol["experiment"] or manifest.get("declared_protocol") != protocol
            or manifest.get("request_provenance") != provenance or manifest.get("answer_schema") != schema
            or manifest.get("declared_protocol_sha256") != hashlib.sha256(canonical(protocol)).hexdigest()
            or manifest.get("frozen_request_file_sha256") != manifest["artifact_sha256"]["frozen_envelope.json"]
            or manifest.get("request_corpus_sha256") != manifest["artifact_sha256"]["requests.jsonl"]
            or data["requests.jsonl"] != b"".join(canonical(row) for row in rows)
            or manifest.get("request_count") != len(rows)):
        raise ValueError("frozen envelope and manifest disagree")
    records = [json.loads(line) for line in data["responses.jsonl"].splitlines()]
    keyed = {(row["case_id"], row["condition"]): row for row in rows}
    for record in records:
        if not isinstance(record, dict) or (record.get("case_id"), record.get("condition")) not in keyed:
            raise ValueError("unknown response key")
        row = keyed[(record["case_id"], record["condition"])]
        status = record.get("status")
        if status not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown recorded response status")
        is_error = status in {"HTTP_ERROR", "TRANSPORT_ERROR"}
        if ("response" in record) == is_error or (record.get("error") is not None) != is_error:
            raise ValueError("response presence/error disagree with status")
        if (record.get("parse_error") is not None) != (status == "MALFORMED"):
            raise ValueError("parse error disagrees with status")
        latency = record.get("latency_ms")
        if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
            raise ValueError("invalid recorded latency")
        if protocol["experiment"] == "routing_confirmation" and status == "RECEIVED":
            cost = record.get("execution_validation_ms")
            if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
                raise ValueError("confirmation execution validation timing required")
        if is_error:
            if any(record.get(field) is not None for field in ("raw_response", "raw_text", "usage", "finish_reason")):
                raise ValueError("transport errors cannot contain successful response fields")
            continue
        raw = record.get("raw_response")
        choice = (raw["choices"][0] if isinstance(raw, dict) and isinstance(raw.get("choices"), list)
                  and raw["choices"] and isinstance(raw["choices"][0], dict) else None)
        message = choice.get("message") if choice is not None else None
        content = message.get("content") if isinstance(message, dict) else None
        if content != record.get("raw_text"):
            raise ValueError("raw model content differs from recorded text")
        if (record.get("usage") != (raw.get("usage") if choice is not None else None)
                or record.get("finish_reason") != (choice.get("finish_reason") if choice is not None else None)):
            raise ValueError("raw usage or finish reason differs from recorded metadata")
        parsed = {}
        try:
            parsed = parse_model_json(content)
            invalid = output_error(parsed, row)
        except ValueError as error:
            invalid = str(error)
        if parsed != record["response"]:
            raise ValueError("parsed response differs from raw model text")
        if (invalid is None) != (status == "RECEIVED"):
            raise ValueError("raw model output disagrees with response status")
    graded = grade_outputs(rows, records, protocol)
    if json.loads(data["graded.json"]) != graded:
        raise ValueError("extended grades differ from sealed local regrading")
    counts = {"request_count": len(rows), "record_count": len(records),
        "received_count": sum(r["status"] in {"RECEIVED", "MALFORMED"} for r in records),
        "missing_count": graded["missing_outputs"],
        "error_count": sum(r["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"} for r in records),
        "malformed_count": sum(r["status"] == "MALFORMED" for r in records)}
    if any(manifest.get(key) != value for key, value in counts.items()):
        raise ValueError("extended manifest counts differ")
    status = "COMPLETE" if not manifest["setup_error"] and not counts["missing_count"] and not counts["error_count"] else "INCOMPLETE"
    if manifest.get("status") != status or (manifest["setup_error"] is not None and records):
        raise ValueError("extended completion status differs")
    return manifest, rows, records, graded, counts


def _with_observations(variants, records):
    by_variant = {}
    for condition, values in variants.items():
        calls = [record for record in records if record["condition"] == condition]
        usage, observed = {}, {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            tokens = [record["usage"][key] for record in calls if isinstance(record.get("usage"), dict)
                      and type(record["usage"].get(key)) is int and record["usage"][key] >= 0]
            usage[key], observed[key] = sum(tokens), len(tokens)
        by_variant[condition] = values | {"usage": usage, "usage_observed_responses": observed,
            "latency_ms": _distribution([record["latency_ms"] for record in calls]),
            "finish_reason_counts": dict(Counter(record["finish_reason"] if record.get("finish_reason") in
                ("stop", "length", "content_filter", "tool_calls", "function_call") else
                "missing" if record.get("finish_reason") is None else "other" for record in calls))}
        validation_times = [record["execution_validation_ms"] for record in calls
                            if "execution_validation_ms" in record]
        if validation_times:
            by_variant[condition]["execution_validation_ms"] = _distribution(validation_times)
    return by_variant


def prepare_report(run_dir):
    manifest, rows, records, graded, counts = read_run(run_dir)
    by_variant = _with_observations(graded["by_variant"], records)
    summary = {"protocol": PROTOCOL_ID, "experiment": manifest["experiment"], "task": rows[0]["task"],
        "model": manifest["requested_model"], "code_revision": manifest["code_revision"],
        "request_corpus_sha256": manifest["request_corpus_sha256"],
        "frozen_request_file_sha256": manifest["frozen_request_file_sha256"], "status": manifest["status"],
        "setup_failed": manifest["setup_error"] is not None, "counts": counts,
        "questions": len({row["case_id"] for row in rows}),
        "parent_documents": len({row.get("parent_document_id", row.get("document_id")) for row in rows}),
        "decoding": manifest["decoding"], "schema_transport": manifest["schema_transport"],
        "by_variant": by_variant, "paired": graded["paired"], "repeat_count": 1,
        "inference_unit": "case; shared documents, semantic families and conditions are not independent samples",
        "limitations": list(manifest["declared_protocol"]["limitations"]),
        "publication": "aggregate_only_no_source_text_or_individual_model_answers"}
    if "by_evaluation_split" in graded:
        summary.update(families=len({row["family_id"] for row in rows}), by_evaluation_split={},
            aggregate_scope="Workload aggregate; exposed diagnostics and fresh families must be assessed separately.")
        for split, values in graded["by_evaluation_split"].items():
            keys = {(row["case_id"], row["condition"]) for row in rows if row["evaluation_split"] == split}
            summary["by_evaluation_split"][split] = values | {"by_variant": _with_observations(
                values["by_variant"], [record for record in records
                    if (record["case_id"], record["condition"]) in keys])}
        for condition, values in summary["by_variant"].items():
            condition_rows = [row for row in rows if row["condition"] == condition]
            for field in ("source_variant", "pack_variant"):
                labels = sorted({row[field] for row in condition_rows if field in row})
                if labels:
                    values[field + "s"] = labels
    if manifest["experiment"] in AUDITED_CONDITION_COUNTS:
        from .review_cpu import paired_cluster_bootstrap
        indexed = {(c["case_id"], c["condition"]): c for c in graded["cases"]}
        summary["paired_cluster_bootstrap"] = {}
        for label, selected in [("all_planned", graded["cases"])] + [
                (split, [c for c in graded["cases"] if c["evaluation_split"] == split])
                for split in sorted({c["evaluation_split"] for c in graded["cases"]})]:
            contrasts = {}
            for name in graded["paired"]:
                left, right = name.split("_to_", 1)
                observations = [{"family": c["family_id"], "document": c["document_id"],
                    "left": int(c["correct"]), "right": int(indexed[(c["case_id"], right)]["correct"])}
                    for c in selected if c["condition"] == left]
                contrasts[name] = {unit: paired_cluster_bootstrap(observations, unit=unit)
                                   for unit in ("family", "document")}
            summary["paired_cluster_bootstrap"][label] = contrasts
        summary["by_terminology_need"] = {}
        for label, flag in (("required", True), ("not_required", False), ("unannotated", None)):
            selected = [case for case in graded["cases"] if case.get("requires_terminology") is flag]
            if selected:
                summary["by_terminology_need"][label] = {
                    "questions": len({c["case_id"] for c in selected}),
                    "by_variant": {condition: _metrics([c for c in selected if c["condition"] == condition],
                        rows[0]["task"] == "structured_routing") for condition in graded["by_variant"]}}
        summary["metric_interpretation"] = (
            "Provided-passage relevance classification: positive_exact means YES on relevant passage sets; no-answer null means abstention on non-relevant sets. Not answer-generation accuracy or entity linking."
            if manifest["experiment"] == "review_nomiracl" else
            "Normalized answer EM and separate source/terminology-need strata; character overlap is not semantic entailment."
            if rows[0]["task"] == "document_qa" else
            "Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.")
    if manifest["experiment"] == "routing_confirmation":
        unique_rows = {row["case_id"]: row for row in rows}
        timing_fields = ("snapshot_compile", "first_prepare", "warm_prepare")
        summary["preparation_timing_ms"] = {field: _distribution([
            row["preparation_timing_ms"][field] for row in unique_rows.values()
            if field in row.get("preparation_timing_ms", {})
            and (field != "snapshot_compile" or row["preparation_timing_ms"][field] > 0)])
            for field in timing_fields}
        summary["pipeline_diagnostics"] = {}
        for split in sorted({row["evaluation_split"] for row in rows}):
            selected = [row for row in unique_rows.values() if row["evaluation_split"] == split]
            summary["pipeline_diagnostics"][split] = {
                "targets": len(selected),
                "positives": sum(row["expected_entity_id"] is not None for row in selected),
                "exact_core_detected": sum(bool(row.get("pipeline_trace", {}).get(
                    "exact_core_detected")) for row in selected),
                "positive_gold_in_candidates": sum(
                    row["expected_entity_id"] is not None
                    and bool(row.get("pipeline_trace", {}).get("gold_in_candidates"))
                    for row in selected),
            }
        summary["cost_interpretation"] = (
            "Request wall time includes local parsing and execution validation; preparation costs are "
            "measured separately. Snapshot compilation counts only actual compilations, excluding cached "
            "zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs."
        )
    return summary


def render_markdown(summary):
    lines = ["# Extended frozen experiment", "",
        f"Experiment: `{summary['experiment']}`. Model: `{summary['model']}`. Status: `{summary['status']}`.", "",
        f"Cases: {summary['questions']}; parent documents: {summary['parent_documents']}. Counts: `{summary['counts']}`.", "",
        "One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.", ""]
    safety = summary["task"] == "structured_routing"
    if safety:
        lines.extend(["| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for condition, values in summary["by_variant"].items():
            lines.append(f"| {condition} | {values['accepted_correct_id']} | {values['accepted_wrong_id']} | {values['rejected_wrong_id']} | {values['correct_abstention']} | {values['over_abstention']} | {values['malformed']} | {values['errors']} | {values['missing']} | {values['usage']['prompt_tokens']} |")
    else:
        lines.extend(["| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |",
                      "|---|---:|---:|---:|---:|---:|---:|"])
        for condition, values in summary["by_variant"].items():
            lines.append(f"| {condition} | {values['positive_exact']}/{values['positive_planned']} | {values['article_no_answer_null']}/{values['no_answer_planned']} | {values['malformed']} | {values['errors']} | {values['missing']} | {values['usage']['prompt_tokens']} |")
    if summary.get("metric_interpretation"):
        lines.extend(["", summary["metric_interpretation"], ""])
    if summary.get("cost_interpretation"):
        lines.extend([summary["cost_interpretation"], "",
            "| Condition | p50 ms | p95 ms | Input tokens | Output tokens |",
            "|---|---:|---:|---:|---:|"])
        for condition, values in summary["by_variant"].items():
            lines.append(f"| {condition} | {values['latency_ms']['p50']} | "
                         f"{values['latency_ms']['p95']} | {values['usage']['prompt_tokens']} | "
                         f"{values['usage']['completion_tokens']} |")
        lines.extend(["", "Preparation timings and pipeline diagnostics:", "", "```json",
            json.dumps({"preparation_timing_ms": summary["preparation_timing_ms"],
                        "pipeline_diagnostics": summary["pipeline_diagnostics"]}, indent=2), "```", ""])
    if summary.get("by_terminology_need"):
        lines.extend(["Pre-inference terminology-need strata:", "", "```json",
                      json.dumps(summary["by_terminology_need"], indent=2), "```", ""])
    lines.extend(["", "Paired comparisons:", "", "```json", json.dumps(summary["paired"], indent=2), "```", ""])
    if "by_evaluation_split" in summary:
        lines.extend([summary["aggregate_scope"], "",
            "Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.", ""])
        for split, values in summary["by_evaluation_split"].items():
            lines.extend([f"Evaluation split: `{split}`. Cases: {values['questions']}; families: {values['families']}.", ""])
            if safety:
                lines.extend(["| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |",
                    "|---|---:|---:|---:|---:|---:|"])
                for condition, metrics in values["by_variant"].items():
                    lines.append(f"| {condition} | {metrics['accepted_correct_id']} | {metrics['accepted_wrong_id']} | {metrics['correct_abstention']} | {metrics['over_abstention']} | {metrics['usage']['prompt_tokens']} |")
            else:
                lines.extend(["| Condition | Positive exact | No-answer null | Prompt tokens |",
                    "|---|---:|---:|---:|"])
                for condition, metrics in values["by_variant"].items():
                    lines.append(f"| {condition} | {metrics['positive_exact']}/{metrics['positive_planned']} | {metrics['article_no_answer_null']}/{metrics['no_answer_planned']} | {metrics['usage']['prompt_tokens']} |")
            lines.extend(["", "Split paired comparisons:", "", "```json", json.dumps(values["paired"], indent=2), "```", ""])
    lines.extend([*["- " + value for value in summary["limitations"]], ""])
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

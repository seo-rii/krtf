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
                                 output_error)
from .run_product_llm import parse_model_json


def read_run(run_dir):
    root = Path(run_dir)
    manifest = json.loads((root / "run_manifest.json").read_text())
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(canonical(unsealed)).hexdigest() != seal:
        raise ValueError("invalid extended manifest seal")
    if (manifest.get("protocol") != PROTOCOL_ID or manifest.get("track") != "extended_suite"
            or manifest.get("decoding") != DECODING or manifest.get("prompt_fields") != ["system", "user"]
            or manifest.get("retries") != 0 or manifest.get("schema_transport") != "response_format.json_schema.strict"):
        raise ValueError("extended protocol or fixed decoding differs")
    if set(manifest.get("artifact_sha256", {})) != set(ARTIFACTS):
        raise ValueError("all extended private artifacts must be sealed")
    data = {name: (root / name).read_bytes() for name in ARTIFACTS}
    if any(hashlib.sha256(value).hexdigest() != manifest["artifact_sha256"][name] for name, value in data.items()):
        raise ValueError("extended artifact hash mismatch")
    rows, protocol, provenance = load_request_file(root / "frozen_envelope.json")
    schema = ANSWER_SCHEMA if rows[0]["task"] == "document_qa" else ROUTING_SCHEMA
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


def prepare_report(run_dir):
    manifest, rows, records, graded, counts = read_run(run_dir)
    by_variant = {}
    for condition, values in graded["by_variant"].items():
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
    return {"protocol": PROTOCOL_ID, "experiment": manifest["experiment"], "task": rows[0]["task"],
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
    lines.extend(["", "Paired comparisons:", "", "```json", json.dumps(summary["paired"], indent=2), "```", "",
                  *["- " + value for value in summary["limitations"]], ""])
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

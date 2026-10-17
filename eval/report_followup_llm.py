"""Regrade sealed private followup runs and publish aggregate-only diagnostics."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from .hf_qa import canonical, response_error
from .report_synthetic_grounding import _distribution
from .run_followup_llm import (ANSWER_SCHEMA, ARTIFACTS, DECODING, PROTOCOL_ID,
                               grade_outputs, load_request_file)
from .run_product_llm import parse_model_json


def read_run(run_dir):
    root = Path(run_dir)
    manifest = json.loads((root / "run_manifest.json").read_text())
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if hashlib.sha256(canonical(unsealed)).hexdigest() != seal:
        raise ValueError("invalid followup manifest seal")
    if (manifest.get("protocol") != PROTOCOL_ID or manifest.get("track") != "hf_followup"
            or manifest.get("decoding") != DECODING or manifest.get("answer_schema") != ANSWER_SCHEMA
            or manifest.get("prompt_fields") != ["system", "user"] or manifest.get("retries") != 0
            or manifest.get("schema_transport") != "response_format.json_schema.strict"):
        raise ValueError("followup protocol or fixed decoding differs")
    if set(manifest.get("artifact_sha256", {})) != set(ARTIFACTS):
        raise ValueError("all followup private artifacts must be sealed")
    data = {name: (root / name).read_bytes() for name in ARTIFACTS}
    if any(hashlib.sha256(value).hexdigest() != manifest["artifact_sha256"][name] for name, value in data.items()):
        raise ValueError("followup artifact hash mismatch")
    rows, protocol, provenance = load_request_file(root / "frozen_envelope.json")
    if (manifest.get("experiment") != protocol["experiment"] or manifest.get("declared_protocol") != protocol
            or manifest.get("request_provenance") != provenance
            or manifest.get("declared_protocol_sha256") != hashlib.sha256(canonical(protocol)).hexdigest()
            or manifest.get("frozen_request_file_sha256") != manifest["artifact_sha256"]["frozen_envelope.json"]
            or manifest.get("request_corpus_sha256") != manifest["artifact_sha256"]["requests.jsonl"]
            or data["requests.jsonl"] != b"".join(canonical(row) for row in rows)
            or manifest.get("request_count") != len(rows)):
        raise ValueError("frozen envelope and manifest disagree")
    records = [json.loads(line) for line in data["responses.jsonl"].splitlines()]
    for record in records:
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
        if not is_error:
            raw = record.get("raw_response")
            try:
                content = raw["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                content = None
            if content != record.get("raw_text"):
                raise ValueError("raw model content differs from recorded text")
            try:
                parsed = parse_model_json(content)
                invalid = response_error(parsed)
                if parsed != record["response"]:
                    raise ValueError("parsed response differs from raw model text")
            except ValueError as error:
                if str(error) == "parsed response differs from raw model text":
                    raise
                invalid = str(error)
            if (invalid is None) != (status == "RECEIVED"):
                raise ValueError("raw model output disagrees with response status")
    graded = grade_outputs(rows, records)
    if json.loads(data["graded.json"]) != graded:
        raise ValueError("followup grades differ from sealed local regrading")
    counts = {"request_count": len(rows), "record_count": len(records),
        "received_count": sum(r["status"] in {"RECEIVED", "MALFORMED"} for r in records),
        "missing_count": graded["missing_outputs"],
        "error_count": sum(r["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"} for r in records),
        "malformed_count": sum(r["status"] == "MALFORMED" for r in records)}
    if any(manifest.get(key) != value for key, value in counts.items()):
        raise ValueError("followup manifest counts differ")
    status = "COMPLETE" if not manifest["setup_error"] and not counts["missing_count"] and not counts["error_count"] else "INCOMPLETE"
    if manifest.get("status") != status:
        raise ValueError("followup completion status differs")
    return manifest, rows, records, graded, counts


def prepare_report(run_dir):
    manifest, rows, records, graded, counts = read_run(run_dir)
    by_variant = {}
    keyed = {(row["case_id"], row["condition"]): row for row in rows}
    for variant, values in graded["by_variant"].items():
        context, mode = variant.split("__")
        calls = [record for record in records if (keyed[(record["case_id"], record["condition"])]["context_condition"],
            keyed[(record["case_id"], record["condition"])]["decoding_mode"]) == (context, mode)]
        usage, usage_observed = {}, {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            observed = [r["usage"][key] for r in calls if isinstance(r.get("usage"), dict)
                        and type(r["usage"].get(key)) is int and r["usage"][key] >= 0]
            usage[key], usage_observed[key] = sum(observed), len(observed)
        latencies = [r["latency_ms"] for r in calls]
        by_variant[variant] = values | {"usage": usage, "usage_observed_responses": usage_observed,
            "latency_ms": _distribution(latencies) | {"total": math.fsum(latencies)},
            "finish_reason_counts": dict(Counter(
                r["finish_reason"] if isinstance(r.get("finish_reason"), str) and r["finish_reason"] in {"stop", "length", "content_filter", "tool_calls", "function_call"}
                else "missing" if r.get("finish_reason") is None else "other" for r in calls))}
    return {"protocol": PROTOCOL_ID, "experiment": manifest["experiment"], "model": manifest["requested_model"],
        "code_revision": manifest["code_revision"], "request_corpus_sha256": manifest["request_corpus_sha256"],
        "frozen_request_file_sha256": manifest["frozen_request_file_sha256"], "status": manifest["status"],
        "setup_failed": manifest["setup_error"] is not None, "counts": counts,
        "questions": len({row["case_id"] for row in rows}),
        "parent_documents": len({row["parent_document_id"] for row in rows}),
        "decoding": manifest["decoding"], "schema_transport": manifest["schema_transport"],
        "by_variant": by_variant, "by_repeat": graded["by_repeat"],
        "paired": graded["paired"], "repeat_agreement": graded["repeat_agreement"],
        "limitations": list(manifest["declared_protocol"]["limitations"]),
        "publication": "aggregate_only_no_source_text_or_individual_model_answers"}


def render_markdown(summary):
    lines = ["# Frozen HF QA followup", "", f"Experiment: `{summary['experiment']}`. Model: `{summary['model']}`. Status: `{summary['status']}`.", "",
        f"Questions: {summary['questions']}; parent documents: {summary['parent_documents']}. Counts: `{summary['counts']}`.", "",
        "Question-level averages include all planned requests. Repeats are descriptive and do not increase the independent sample size.", "",
        "| Context / decoding | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for variant, value in summary["by_variant"].items():
        lines.append(f"| {variant} | {value['positive_exact']}/{value['positive_planned']} | {value['article_no_answer_null']}/{value['no_answer_planned']} | {value['malformed']} | {value['errors']} | {value['missing']} | {value['usage']['prompt_tokens']} |")
    lines += ["", "Matched comparisons and per-question mean changes:", "", "```json", json.dumps(summary["paired"], indent=2), "```",
              "", "Repeated identical-prompt agreement:", "", "```json", json.dumps(summary["repeat_agreement"], indent=2), "```",
              "", *["- " + value for value in summary["limitations"]], ""]
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

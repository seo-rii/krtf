"""Export text-free observations from sealed runs already represented in reports.

This is an offline archival step. Original inputs and model outputs stay in the
private backup. Historical grades are checked against their seals and published
aggregates, without silently replacing them with scores from newer graders.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .hf_qa import canonical


BOOL_FIELDS = frozenset("""
accepted_correct_id accepted_wrong_id attempted_nonnull base_guard_valid
closed_validation_valid correct correct_abstention error evaluation_only
evidence_gate_valid evidence_required exact_match guard_valid malformed missing
nonnull null null_wire_error over_abstention pack_injected positive_gold
production_base_guard_valid production_guard_accepted_correct_id
production_guard_accepted_wrong_id proposal_abstention proposal_correct_id
proposal_wrong_id raw_accepted_correct_id raw_accepted_wrong_id raw_guard_valid
raw_validation_valid rejected_correct_id rejected_wrong_id requires_terminology
semantic_match shadow_accepted_correct_id shadow_accepted_wrong_id
source_gold_visible valid wire_valid human_verified independent_validation
source_reused pack_bypassed_due_to_budget anchor_document_retrieved
""".split())
LABEL_FIELDS = frozenset("""
condition context_condition decoding_mode evaluation_split original_evaluation_split
source_origin_split stratum document_length_band authorization_mode
execution_authority source_variant pack_variant selector_variant pack_format
policy_factor annotation_origin binding_span_origin evaluation_population
""".split())
NUMBER_FIELDS = frozenset("""
character_f1 repeat_id estimated_input_tokens
reserved_output_tokens total_prompt_token_cap source_character_count
corpus_document_count anchor_document_rank
""".split())
IDENTITY_FIELDS = ("case_id", "document_id", "parent_document_id", "family_id")
VIOLATION_FIELDS = ("guard_violations", "raw_guard_violations",
                    "production_guard_violations", "evidence_gate_violations")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def observation(request, grade, record):
    """Allow only typed outcomes, labels, costs and stable hashed identities."""
    result = {}
    for field in IDENTITY_FIELDS:
        value = request.get(field, grade.get(field))
        if value is not None:
            if not isinstance(value, str) or not value:
                raise ValueError("invalid observation identity")
            # One namespace per role; no run salt, so repeated documents/families
            # remain joinable across conditions, models and diagnostic queues.
            result[field + "_sha256"] = digest(canonical([field, value]))
    for field in sorted(BOOL_FIELDS | LABEL_FIELDS | NUMBER_FIELDS):
        if field not in request and field not in grade:
            continue
        value = grade.get(field, request.get(field))
        if value is not None:
            if field in BOOL_FIELDS and type(value) is not bool:
                raise ValueError("invalid boolean observation: " + field)
            if field in LABEL_FIELDS and (not isinstance(value, str) or not re.fullmatch(
                    r"[A-Za-z0-9_:.+/-]{1,100}", value)):
                raise ValueError("invalid observation label: " + field)
            if field in NUMBER_FIELDS and (type(value) not in (int, float)
                    or not math.isfinite(value) or value < 0):
                raise ValueError("invalid numeric observation: " + field)
        result[field] = value
    result["prompt_sha256"] = digest(canonical([request["system"], request["user"]]))
    for field in ("prompt_tokens", "source_tokens", "prompt_budget_utilization"):
        if field in request:
            prepared = request[field]
            values = prepared.values() if isinstance(prepared, dict) else [prepared]
            types = (int, float) if field == "prompt_budget_utilization" else (int,)
            if (any(type(value) not in types or not math.isfinite(value) or value < 0 for value in values)
                    or isinstance(prepared, dict) and set(prepared) - {"gemma12b", "qwen27b"}):
                raise ValueError("invalid prepared token measurement: " + field)
            result["prepared_" + field] = prepared
    for field in ("document_sha256", "rendered_source_sha256", "source_records_sha256"):
        if field in request:
            value = request[field]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("invalid source digest")
            result[field] = value
    if "pipeline_trace" in request:
        trace = request["pipeline_trace"]
        pipeline = {key: trace[key] for key in ("exact_core_detected", "gold_in_candidates")}
        if any(value is not None and type(value) is not bool for value in pipeline.values()):
            raise ValueError("invalid pipeline observation")
        pipeline.update(candidate_count=len(trace["candidate_entity_ids"]),
                        resolver_committed=trace["resolved_entity_id"] is not None)
        result["pipeline"] = pipeline
    if "preparation_timing_ms" in request:
        timings = {key: request["preparation_timing_ms"][key]
                   for key in ("snapshot_compile", "first_prepare", "warm_prepare")}
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
               for value in timings.values()):
            raise ValueError("invalid preparation timing")
        result["preparation_timing_ms"] = timings
    for field in VIOLATION_FIELDS:
        if field in grade:
            result[field + "_count"] = len(grade[field])
    if "server_added_segments" in grade:
        result["server_added_segment_count"] = len(grade["server_added_segments"])
    result["observed"] = record is not None
    if record is not None:
        for field in ("latency_ms", "execution_validation_ms"):
            if field in record:
                value = record[field]
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("invalid measured timing")
                result[field] = value
        result["finish_reason"] = (record.get("finish_reason")
            if record.get("finish_reason") in {"stop", "length", "content_filter", "tool_calls", "function_call"}
            else "missing" if record.get("finish_reason") is None else "other")
        result["usage"] = {key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if type(value := (record.get("usage") or {}).get(key)) is int and value >= 0}
    return validate_public_json(result)


def verified_stage(root, identity, summary):
    manifest = json.loads((root / "run_manifest.json").read_text())
    if manifest.get("protocol") not in {"ktrf_extended_v1", "hf_followup_v1"}:
        raise ValueError("unsupported observation protocol")
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    if digest(canonical(unsealed)) != seal:
        raise ValueError("invalid archived manifest seal")
    names = ("frozen_envelope.json", "requests.jsonl", "responses.jsonl", "graded.json")
    data = {name: (root / name).read_bytes() for name in names}
    if manifest.get("artifact_sha256") != {name: digest(value) for name, value in data.items()}:
        raise ValueError("archived artifact hash mismatch")
    requests = [json.loads(line) for line in data["requests.jsonl"].splitlines()]
    records = [json.loads(line) for line in data["responses.jsonl"].splitlines()]
    graded = json.loads(data["graded.json"])
    envelope = json.loads(data["frozen_envelope.json"])
    if (envelope.get("requests") != requests
            or manifest.get("request_corpus_sha256") != digest(data["requests.jsonl"])
            or manifest.get("frozen_request_file_sha256") != digest(data["frozen_envelope.json"])):
        raise ValueError("archived envelope differs from requests")
    def indexed(rows):
        keyed = {(row["case_id"], row["condition"]): row for row in rows}
        if len(keyed) != len(rows):
            raise ValueError("duplicate archived observation key")
        return keyed

    keyed_requests, keyed_records, keyed_grades = map(indexed, (requests, records, graded["cases"]))
    if set(keyed_requests) != set(keyed_grades) or set(keyed_records) - set(keyed_requests):
        raise ValueError("archived observation keys disagree")
    counts = {"request_count": len(requests), "record_count": len(records),
        "received_count": sum(row["status"] in {"RECEIVED", "MALFORMED"} for row in records),
        "missing_count": len(requests) - len(records),
        "error_count": sum(row["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"} for row in records),
        "malformed_count": sum(row["status"] == "MALFORMED" for row in records)}
    if (any(manifest.get(key) != value for key, value in counts.items())
            or graded["missing_outputs"] != counts["missing_count"]):
        raise ValueError("archived observation counts disagree")
    expected = {key: manifest[key] for key in (
        "artifact_sha256", "request_count", "request_corpus_sha256",
        "frozen_request_file_sha256", "code_revision", "requested_model", "experiment")}
    expected.update(source_manifest_seal_sha256=manifest["seal_sha256"], counts=counts)
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("backup run differs from published manifest identity")
    if (summary.get("counts") != counts or summary.get("request_corpus_sha256") != manifest["request_corpus_sha256"]
            or summary.get("model") != manifest["requested_model"]):
        raise ValueError("backup run differs from published summary")
    for condition, metrics in graded["by_variant"].items():
        public_metrics = summary["by_variant"][condition]
        if any(public_metrics.get(key) != value for key, value in metrics.items()):
            raise ValueError("archived metrics differ from published summary")
    return manifest, [observation(keyed_requests[key], row, keyed_records.get(key))
        for row in graded["cases"] for key in [(row["case_id"], row["condition"])]]


def export(backup, repo, output):
    backup, repo, output = Path(backup), Path(repo), Path(output)
    if output.exists():
        raise ValueError("refusing to overwrite existing publication")
    runs = backup / "data/data/one/mil_llm_refusal/ktrf/experiments"
    index = {}
    for path in sorted(runs.glob("*/results/*/run_manifest.json")):
        manifest = json.loads(path.read_text())
        index.setdefault(manifest.get("seal_sha256"), path.parent)
    candidates, skipped = {}, []
    for path in sorted((repo / "reports").glob("*/*/manifest_identity.json")):
        identity = json.loads(path.read_text())
        root = index.get(identity.get("source_manifest_seal_sha256"))
        if root is None:
            raise ValueError("published sealed run absent from backup: " + str(path))
        manifest = json.loads((root / "run_manifest.json").read_text())
        if manifest.get("protocol") not in {"ktrf_extended_v1", "hf_followup_v1"}:
            skipped.append(str(path.parent.relative_to(repo)))
            continue
        hashes = identity["artifact_sha256"]
        key = (hashes["requests.jsonl"], hashes["responses.jsonl"])
        candidates.setdefault(key, []).append((path, root, identity))
    # Verify every published reference, including aliases of reused stages.
    stages = []
    for number, aliases in enumerate(candidates.values(), 1):
        rows = None
        for path, root, identity in aliases:
            summary = json.loads((path.parent / "summary.json").read_text())
            manifest, checked = verified_stage(root, identity, summary)
            if rows is not None and checked != rows:
                raise ValueError("reused generation has conflicting observations")
            rows = checked
        name = f"observations/{number:02d}_{root.name}.jsonl.gz"
        payload = b"".join(canonical(row) for row in rows)
        compressed = gzip.compress(payload, compresslevel=9, mtime=0)
        stages.append((name, compressed, {
            "file": name, "sha256": digest(compressed), "jsonl_sha256": digest(payload),
            "observations": len(rows), "case_count": len({row["case_id_sha256"] for row in rows}),
            "model": manifest["requested_model"], "experiment": manifest["experiment"],
            "protocol": manifest["protocol"], "code_revision": manifest["code_revision"],
            "source_artifact_sha256": manifest["artifact_sha256"],
            "source_manifest_seals": sorted({alias[2]["source_manifest_seal_sha256"] for alias in aliases}),
            "published_reports": [str(path.parent.relative_to(repo)) for path, _, _ in aliases],
            "condition_counts": dict(Counter(row["condition"] for row in rows)),
        }))
    if not stages:
        raise ValueError("no supported sealed observations found")
    metadata = backup / "metadata"
    shared = json.loads((metadata / "shared-runtime-and-model-identities.json").read_text())
    runtime = {"capture_scope": "Shared vLLM environment at backup time; not an attestation of every earlier run.",
        "platform": shared["platform"], "system_python": shared["system_python"],
        "package_environments": [{"role": "shared_vllm", "exit_code": value["exit_code"],
            "packages": [{"name": row["name"], "version": row["version"]} for row in value["packages"]]}
            for key, value in shared["runtime_packages"].items() if key.endswith("/.venvs/vllm/bin/python")],
        "shared_model_files": [{"model_directory": Path(row["path"]).parent.name,
            "filename": Path(row["path"]).name, "size": row["size"], "sha256": row["sha256"]}
            for row in shared["shared_model_files"] if row.get("type") == "file"
            and not Path(row["path"]).name.startswith(".")]}
    models = json.loads((metadata / "public-model-reproduction.json").read_text())
    manifest = {"schema_version": 1, "kind": "ktrf_text_free_backup_observations_v1",
        "backup_manifest_sha256": digest((metadata / "retained-manifest.json").read_bytes()),
        "stage_count": len(stages), "published_report_references": sum(len(a) for a in candidates.values()),
        "planned_observations": sum(item[2]["observations"] for item in stages),
        "reused_report_references_deduplicated": sum(len(a) - 1 for a in candidates.values()),
        "unsupported_reports": skipped, "stages": [item[2] for item in stages],
        "interpretation": "Request rows include conditions, repeats and reused source documents/families; they are not independent samples.",
        "grading_scope": "Historical sealed grades matched to the published reports; not regraded under the exporter code revision.",
        "publication": "Typed text-free metrics only; original prompts, answers and documents remain private."}
    files = {name: data for name, data, _ in stages}
    files.update({"model_reproduction.json": canonical(validate_public_json(models)),
                  "runtime_inventory.json": canonical(validate_public_json(runtime))})
    manifest["metadata_sha256"] = {name: digest(data) for name, data in files.items() if name.endswith(".json")}
    files["manifest.json"] = canonical(validate_public_json(manifest))
    output.mkdir(parents=True)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export(args.backup, args.repo, args.output)
    print(json.dumps({key: result[key] for key in (
        "stage_count", "planned_observations", "reused_report_references_deduplicated")}))


if __name__ == "__main__":
    main()

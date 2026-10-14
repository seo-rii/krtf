"""Verify and compare a sealed knowledge/source document factorial experiment.

All quality comparisons use the same schema-valid semantic outcome before an
arm's execution validator. Knowledge and source interventions remain separate;
there is deliberately no pooled primary score across the factorial cells.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from eval.document_context import (
    grade_document_context_outputs, validate_document_context_requests,
)
from eval.production_grounding import TASKS, production_response_error
from eval.report_production_grounding import _operational
from eval.report_synthetic_grounding import ARTIFACTS, _json_bytes

KNOWLEDGE_MODES = ("none", "full", "retrieved", "ktrf")
SOURCE_MODES = ("none", "full", "retrieved")
CONDITIONS = tuple(f"{knowledge}__{source}" for knowledge in KNOWLEDGE_MODES for source in SOURCE_MODES)
PROTOCOL = "document_context_factorial_v1"


def _read_run(run_dir):
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("track") != "document_context" or manifest.get("protocol") != PROTOCOL:
        raise ValueError("report requires the document context track and matching protocol")
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
            raise ValueError("artifact hash mismatch: " + name)
    if manifest.get("request_corpus_sha256") != hashes["requests.jsonl"]:
        raise ValueError("request corpus hash disagrees with sealed artifact")
    protocol = manifest.get("declared_protocol")
    if (not isinstance(protocol, dict) or protocol.get("kind") != PROTOCOL or
            not isinstance(protocol.get("gold_origin"), str) or not protocol["gold_origin"] or
            type(protocol.get("human_verified")) is not bool or not isinstance(protocol.get("limitations"), list)):
        raise ValueError("frozen protocol must declare matching identity, gold origin and limitations")
    if (protocol["gold_origin"] != "AI_AUTHORED_SYNTHETIC" or protocol["human_verified"] is not False or
            protocol.get("conditions") != list(CONDITIONS) or protocol.get("tasks") != list(TASKS) or
            protocol.get("knowledge_modes") != list(KNOWLEDGE_MODES) or
            protocol.get("source_modes") != list(SOURCE_MODES)):
        raise ValueError("frozen protocol disagrees with authored factorial identity")
    requests = [json.loads(line) for line in contents["requests.jsonl"].splitlines() if line.strip()]
    records = [json.loads(line) for line in contents["responses.jsonl"].splitlines() if line.strip()]
    # The validator uses only frozen row facts here; it must not load fixtures or
    # require the current production policy text to equal historical policy text.
    validate_document_context_requests(requests, check_current_policy=False)
    documents = defaultdict(list)
    for row in requests:
        documents[row["document_id"]].append(row)
    fixed = ("family_id", "domain", "stratum", "source_text", "document_sha256", "target_surface", "target_span",
             "knowledge_text", "knowledge_document_id", "knowledge_sha256", "gold", "expected_answer",
             "expected_entity_id", "decisive_evidence", "glossary_entity_ids", "snapshot_id", "provenance")
    for rows in documents.values():
        if {(row["condition"], row["task"]) for row in rows} != {(condition, task)
                for condition in CONDITIONS for task in TASKS}:
            raise ValueError("every document requires the complete condition/task matrix")
        if any(any(row[field] != rows[0][field] for field in fixed) for row in rows[1:]):
            raise ValueError("document conditions disagree on frozen source facts or gold")
    known = {(row["case_id"], row["condition"]): row for row in requests}
    recorded = {}
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
    recomputed = grade_document_context_outputs(requests, [record for record in records if "response" in record])
    recomputed["limitations"] = list(protocol["limitations"])
    graded = json.loads(contents["graded.json"])["model_results"]
    if graded != recomputed or graded.get("missing_outputs") != counts["missing_count"]:
        raise ValueError("recorded grades disagree with frozen regrading")
    return manifest, requests, records, graded, counts


def _outcomes(cases):
    observed = [case for case in cases if not case["missing"]]
    positives = [case for case in cases if case["positive_gold"]]
    negatives = [case for case in cases if not case["positive_gold"]]
    return {"planned": len(cases), "observed": len(observed), "missing": len(cases) - len(observed),
        **{name: sum(bool(case.get(name)) for case in observed) for name in
           ("semantic_match", "operational_correct", "wrong", "null", "safe_null", "positive_null", "malformed")},
        "positive_planned": len(positives), "nonpositive_planned": len(negatives),
        "positive_semantic_match": sum(bool(case.get("semantic_match")) for case in positives),
        "nonpositive_semantic_match": sum(bool(case.get("semantic_match")) for case in negatives)}


def _evidence(cases):
    positives = [case for case in cases if case["positive_gold"]]
    source_applicable = sum(case["source_gold_visible"] is not None for case in cases)
    source_visible = sum(case["source_gold_visible"] is True for case in cases)
    definitions = sum(case["definition_visible"] for case in positives)
    ids = sum(case["entity_id_visible"] for case in positives)
    return {"planned": len(cases), "positive_planned": len(positives),
        "source_gold_visible": source_visible, "source_evidence_applicable": source_applicable,
        "source_evidence_presence_rate": source_visible / source_applicable if source_applicable else None,
        "gold_definition_visible": definitions,
        "definition_recall": definitions / len(positives) if positives else None,
        "gold_entity_id_visible": ids,
        "entity_id_recall": ids / len(positives) if positives else None,
        "scope": "Frozen visibility, not model correctness. Definition/ID recall is conditional on positive gold; source evidence includes null-gold decision cues."}


def _routing_acceptance(cases, *, knowledge_mode):
    observed = [case for case in cases if case["task"] == "structured_routing" and not case["missing"]]
    accepted = lambda case: not case.get("malformed") and bool(case.get("operational_valid"))
    return {"validator": "KTRF complete-response execution guard" if knowledge_mode == "ktrf" else
            "schema and ID membership in actually provided evidence",
        "accepted_correct_nonnull": sum(bool(case.get("nonnull")) and accepted(case) and case["semantic_match"] for case in observed),
        "accepted_wrong_nonnull": sum(bool(case.get("wrong")) and accepted(case) for case in observed),
        "rejected_correct_nonnull": sum(bool(case.get("nonnull")) and not accepted(case) and case["semantic_match"] for case in observed),
        "rejected_wrong_nonnull": sum(bool(case.get("wrong")) and not accepted(case) for case in observed),
        "accepted_null": sum(bool(case.get("null")) and accepted(case) for case in observed)}


def _changes(old_cases, new_cases):
    """Compare one cell with one cell, keeping tasks and strata separate."""
    old = {case["case_id"]: case for case in old_cases}
    new = {case["case_id"]: case for case in new_cases}
    if len(old) != len(old_cases) or len(new) != len(new_cases) or set(old) != set(new):
        raise ValueError("paired semantic comparison case identities differ")
    if any(any(old[key][field] != new[key][field] for field in
               ("task", "document_id", "family_id", "stratum", "positive_gold")) for key in old):
        raise ValueError("paired semantic comparison case facts differ")

    def group(keys):
        comparable = [key for key in keys if not old[key]["missing"] and not new[key]["missing"]]
        helpful = [key for key in comparable if not old[key]["semantic_match"] and new[key]["semantic_match"]]
        harmful = [key for key in comparable if old[key]["semantic_match"] and not new[key]["semantic_match"]]
        return {"planned": len(keys), "comparable": len(comparable), "incomplete": len(keys) - len(comparable),
            "helpful": len(helpful), "harmful": len(harmful),
            "both_correct": sum(old[key]["semantic_match"] and new[key]["semantic_match"] for key in comparable),
            "both_incorrect": sum(not old[key]["semantic_match"] and not new[key]["semantic_match"] for key in comparable),
            "helpful_case_ids": helpful, "harmful_case_ids": harmful}

    return {"by_task": {task: group(sorted(key for key in old if old[key]["task"] == task)) for task in TASKS},
        "by_stratum": {stratum: {task: group(sorted(key for key in old if old[key]["task"] == task
            and old[key]["stratum"] == stratum)) for task in TASKS}
            for stratum in sorted({case["stratum"] for case in old.values()})}}


def _factorial_comparisons(cases):
    cells = {condition: [case for case in cases if case["condition"] == condition] for condition in CONDITIONS}

    def contrast(old, new):
        return {"baseline_condition": old, "current_condition": new, **_changes(cells[old], cells[new])}

    return {
        "knowledge_at_fixed_source": {source: {
            f"{old}_to_{new}": contrast(f"{old}__{source}", f"{new}__{source}")
            for old, new in (("none", "full"), ("none", "retrieved"), ("none", "ktrf"),
                             ("full", "retrieved"), ("full", "ktrf"), ("retrieved", "ktrf"))}
            for source in SOURCE_MODES},
        "source_at_fixed_knowledge": {knowledge: {
            f"{old}_to_{new}": contrast(f"{knowledge}__{old}", f"{knowledge}__{new}")
            for old, new in (("none", "full"), ("none", "retrieved"), ("full", "retrieved"))}
            for knowledge in KNOWLEDGE_MODES},
        "interpretation": "Primary comparisons use schema-valid semantic matches before validators. Missing pairs are incomplete; malformed outputs are failures. Fixing one axis does not remove retrieval, formatting and policy differences on the other axis."}


def prepare_report(run_dir, *, compare=None):
    """Verify all sealed inputs and regrade without rebuilding contemporary prompts."""
    manifest, requests, records, graded, counts = _read_run(Path(run_dir))
    documents = {row["document_id"]: row for row in requests}
    cases = graded["cases"]
    by_condition = {}
    for condition in CONDITIONS:
        knowledge, source = condition.split("__")
        rows = [row for row in requests if row["condition"] == condition]
        cell_cases = [case for case in cases if case["condition"] == condition]
        by_condition[condition] = {"knowledge_mode": knowledge, "source_mode": source,
            "by_task": {task: {
                "semantic": _outcomes([case for case in cell_cases if case["task"] == task]),
                "evidence": _evidence([case for case in cell_cases if case["task"] == task]),
                "operational": _operational([row for row in rows if row["task"] == task], records)}
                for task in TASKS},
            "by_stratum": {stratum: {task: _outcomes([case for case in cell_cases if
                case["stratum"] == stratum and case["task"] == task]) for task in TASKS}
                for stratum in sorted({case["stratum"] for case in cell_cases})},
            "routing_acceptance": _routing_acceptance(cell_cases, knowledge_mode=knowledge)}
    summary = {"kind": "sealed_document_context_report", "status": manifest["status"],
        "track": manifest["track"], "protocol": manifest["protocol"],
        "annotation_origin": manifest["declared_protocol"]["gold_origin"],
        "human_verified": manifest["declared_protocol"]["human_verified"], "quality_claim": False,
        **{key: manifest.get(key) for key in ("code_revision", "requested_model", "served_models", "endpoint",
            "started_at", "finished_at", "decoding", "declared_protocol", "request_provenance", "request_corpus_sha256")},
        "verified_manifest_seal_sha256": manifest["seal_sha256"],
        "verified_artifact_sha256": manifest["artifact_sha256"],
        "counts": {**counts, "attempted_count": len(records), "not_attempted_count": len(requests) - len(records),
            "documents": len(documents), "conditions": len(CONDITIONS),
            "families": len({row["family_id"] for row in documents.values()})},
        "strata": dict(Counter(row["stratum"] for row in documents.values())),
        "gold_labels": dict(Counter(row["gold"]["label"] for row in documents.values())),
        "metrics": graded, "by_condition": by_condition,
        "factorial_comparisons": _factorial_comparisons(cases),
        "primary_metric": "schema-valid exact semantic_match before any arm's execution validator, separately for every condition and task",
        "limitations": [*manifest["declared_protocol"]["limitations"],
            "These complete source and knowledge documents are authored originals, not reconstructed news articles. Their AI-authored gold is not independent human gold or evidence of deployment risk.",
            "No pooled factorial success score is a primary result. Each source mode, knowledge mode and task is reported separately.",
            "All twelve conditions are newly inferred on identical documents and gold for this model. Prior production C responses are not used as controls.",
            "The none/none condition sees only the question and target expression. Recovering an opaque glossary ID without evidence is not a fair test of general knowledge; report QA and ID visibility alongside execution.",
            "KTRF includes its retrieval, context packaging, policy and guard. Compared with full or retrieved knowledge, this measures a system intervention, not an isolated resolver effect.",
            "KTRF's guard and baseline supplied-ID membership validation differ. Their operational acceptance is separate from common semantic accuracy; malformed/missing responses never earn null credit.",
            "Full means the entire frozen document; search uses only its retrieved chunks and neighbors. Evidence presence/recall is a property of provided inputs, not a model score.",
            "The target and relevant source document are known in this track. Source chunk retrieval is not an evaluation of corpus-wide document discovery.",
            "QA exact-definition matching can mark synonymous free wording incorrect; the fixed response contract is common across conditions.",
            "Latency uses math.fsum across recorded attempts, including failures. Missing attempts receive no imputed latency. Shared-host and serving differences affect latency.",
            "COMPLETE measures response coverage, including malformed outputs, rather than task quality. No confidence or risk-control guarantee follows from this authored sample.",
        ]}
    if compare is not None:
        baseline = prepare_report(compare)
        if any(baseline[field] != summary[field] for field in
               ("request_corpus_sha256", "track", "protocol", "declared_protocol", "decoding")):
            raise ValueError("paired model comparison requires identical frozen requests, protocol and decoding")
        summary["comparison"] = {"baseline_model": baseline["requested_model"], "current_model": summary["requested_model"],
            "baseline_manifest_seal_sha256": baseline["verified_manifest_seal_sha256"],
            "by_condition": {condition: _changes(
                [case for case in baseline["metrics"]["cases"] if case["condition"] == condition],
                [case for case in cases if case["condition"] == condition]) for condition in CONDITIONS},
            "interpretation": "Same requests, protocol and decoding; model families, training and serving differ. This does not isolate parameter count."}
    return summary


def render_markdown(summary):
    counts = summary["counts"]
    lines = ["# Knowledge and source document context experiment", "",
        f"Status: **{summary['status']}**. Model: `{summary['requested_model']}`. "
        f"{counts['documents']} complete authored documents × {counts['conditions']} conditions × 2 tasks; "
        f"{counts['request_count']} calls planned.", "",
        f"Gold: `{summary['annotation_origin']}`; human verified: `{str(summary['human_verified']).lower()}`. "
        "Authored documents and AI gold do not establish deployment risk.", "",
        f"Received {counts['received_count']}; missing {counts['missing_count']}; malformed {counts['malformed_count']}; "
        f"API/transport errors {counts['error_count']}.", "",
        "Knowledge modes: no knowledge, the full knowledge document, retrieved knowledge passages, and KTRF. "
        "Source modes: no surrounding source, the full source document, and retrieved source passages with neighbors. "
        "Both axes vary independently; the no/no condition contains only the question and target expression. "
        "Every condition uses new inference; no historical C outputs are reused.", "",
        "The primary metric is a schema-valid exact semantic match **before** each arm's validator. "
        "QA and ID routing are reported separately. There is no pooled primary score.", "",
        "## Semantic outcomes", "",
        "| Knowledge | Source | Task | Match / planned | Positive null | Correct null | Wrong non-null | Malformed | Missing |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for cell in summary["by_condition"].values():
        for task, result in cell["by_task"].items():
            value = result["semantic"]
            lines.append(f"| {cell['knowledge_mode']} | {cell['source_mode']} | {task} | "
                f"{value['semantic_match']}/{value['planned']} | {value['positive_null']} | {value['safe_null']} | "
                f"{value['wrong']} | {value['malformed']} | {value['missing']} |")
    lines += ["", "## Provided evidence", "",
        "Source presence includes decision cues for null-gold targets. Definition and entity-ID recall use positive gold only. "
        "Visibility does not imply the model used the evidence correctly.", "",
        "| Knowledge | Source | Task | Source cue / annotated | Definition / positive | ID / positive |",
        "|---|---|---|---:|---:|---:|"]
    for cell in summary["by_condition"].values():
        for task, result in cell["by_task"].items():
            value = result["evidence"]
            lines.append(f"| {cell['knowledge_mode']} | {cell['source_mode']} | {task} | "
                f"{value['source_gold_visible']}/{value['source_evidence_applicable']} | "
                f"{value['gold_definition_visible']}/{value['positive_planned']} | "
                f"{value['gold_entity_id_visible']}/{value['positive_planned']} |")
    for axis, title in (("knowledge_at_fixed_source", "Knowledge changes at fixed source"),
                        ("source_at_fixed_knowledge", "Source changes at fixed knowledge")):
        lines += ["", "## " + title, "",
            "Helpful means the current condition succeeds where baseline fails; harmful means the reverse. "
            "Missing pairs are incomplete; malformed responses remain failures.", "",
            "| Fixed mode | Change | Task | Comparable | Helpful | Harmful | Incomplete |",
            "|---|---|---|---:|---:|---:|---:|"]
        for fixed, contrasts in summary["factorial_comparisons"][axis].items():
            for name, contrast in contrasts.items():
                for task, value in contrast["by_task"].items():
                    lines.append(f"| {fixed} | {name} | {task} | {value['comparable']} | "
                        f"{value['helpful']} | {value['harmful']} | {value['incomplete']} |")
    lines += ["", "## Operational execution acceptance", "",
        "KTRF applies its complete-response guard. Other modes check the schema and membership among IDs actually "
        "provided in evidence. Acceptance is not semantic correctness, and these validators are not interchangeable.", "",
        "| Knowledge | Source | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for cell in summary["by_condition"].values():
        value = cell["routing_acceptance"]
        lines.append(f"| {cell['knowledge_mode']} | {cell['source_mode']} | {value['accepted_correct_nonnull']} | "
            f"{value['accepted_wrong_nonnull']} | {value['rejected_correct_nonnull']} | "
            f"{value['rejected_wrong_nonnull']} | {value['accepted_null']} |")
    lines += ["", "## Cost", "", "Latency includes failed attempts. Usage counts only reported observations.", "",
        "| Knowledge | Source | Task | Latency observations | Total ms | p95 ms | Prompt tokens | Completion tokens | Usage observations |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for cell in summary["by_condition"].values():
        for task, result in cell["by_task"].items():
            cost = result["operational"]
            latency, usage = cost["latency_ms"], cost["actual_usage"]
            lines.append(f"| {cell['knowledge_mode']} | {cell['source_mode']} | {task} | {latency['observations']} | "
                f"{latency['total']:.3f} | {latency['p95']} | {usage['prompt_tokens']['total']} | "
                f"{usage['completion_tokens']['total']} | {usage['total_tokens']['observations']} |")
    if "comparison" in summary:
        comparison = summary["comparison"]
        lines += ["", "## Paired model comparison", "",
            f"`{comparison['baseline_model']}` → `{comparison['current_model']}` on identical frozen requests and decoding. "
            + comparison["interpretation"], "",
            "| Condition | Task | Comparable | Helpful | Harmful | Incomplete |",
            "|---|---|---:|---:|---:|---:|"]
        for condition, contrast in comparison["by_condition"].items():
            for task, value in contrast["by_task"].items():
                lines.append(f"| {condition} | {task} | {value['comparable']} | {value['helpful']} | "
                    f"{value['harmful']} | {value['incomplete']} |")
    lines += ["", "Per-stratum results and helpful/harmful case IDs are available in `summary.json`.", "",
        "## Reproducibility and limits", "",
        f"Code revision: `{summary['code_revision']}`. Request SHA-256: `{summary['request_corpus_sha256']}`. "
        f"Manifest seal: `{summary['verified_manifest_seal_sha256']}`.", "",
        f"Decoding: `{json.dumps(summary['decoding'], sort_keys=True)}`.", ""]
    lines.extend("- " + limitation for limitation in summary["limitations"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    summary = prepare_report(args.run_dir, compare=args.compare)
    (args.run_dir / "summary.json").write_bytes(_json_bytes(summary))
    (args.run_dir / "RESULTS.md").write_text(render_markdown(summary))
    print(json.dumps({"run_dir": str(args.run_dir), "status": summary["status"], "counts": summary["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

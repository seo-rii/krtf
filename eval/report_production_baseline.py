"""Report sealed glossary retrieval B runs against matching frozen production C runs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from eval.production_baseline import grade_baseline_outputs
from eval.production_grounding import TASKS, production_response_error
from eval.report_production_grounding import _operational, prepare_report as prepare_production_report
from eval.report_synthetic_grounding import ARTIFACTS, _distribution, _json_bytes
from eval.synthetic_grounding import _binding_cards

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = {"baseline_synthetic": "production_baseline_synthetic_v1",
             "baseline_real": "production_baseline_real_v1"}
SOURCE_FIELDS = ("case_id", "document_id", "family_id", "domain", "stratum", "task", "text",
    "target_surface", "target_span", "document_sha256", "gold", "expected_answer", "expected_entity_id",
    "provenance", "snapshot_id", "contrast_pair_id", "contrast_member")


def _read_run(run_dir):
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("track") not in PROTOCOLS or manifest.get("protocol") != PROTOCOLS[manifest["track"]]:
        raise ValueError("report requires a baseline track and its matching protocol")
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
    if (not isinstance(protocol, dict) or protocol.get("kind") != manifest["protocol"] or
            not isinstance(protocol.get("gold_origin"), str) or not protocol["gold_origin"] or
            type(protocol.get("human_verified")) is not bool or not isinstance(protocol.get("limitations"), list)):
        raise ValueError("frozen protocol must declare matching identity, gold origin and limitations")
    requests = [json.loads(line) for line in contents["requests.jsonl"].splitlines() if line.strip()]
    records = [json.loads(line) for line in contents["responses.jsonl"].splitlines() if line.strip()]
    known, documents = {}, defaultdict(set)
    for row in requests:
        key = (row["case_id"], row["condition"])
        if key in known or row["condition"] != "plain_glossary" or row["task"] not in TASKS:
            raise ValueError("duplicate baseline request or unknown condition/task")
        if row["task"] in documents[row["document_id"]]:
            raise ValueError("duplicate document task")
        known[key] = row
        documents[row["document_id"]].add(row["task"])
    if not documents or any(tasks != set(TASKS) for tasks in documents.values()):
        raise ValueError("every document requires separate QA and execution tasks")
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
    recomputed = grade_baseline_outputs(requests, [record for record in records if "response" in record])
    recomputed["limitations"] = list(protocol["limitations"])
    graded = json.loads(contents["graded.json"])["model_results"]
    if graded != recomputed or graded.get("missing_outputs") != counts["missing_count"]:
        raise ValueError("recorded grades disagree with frozen regrading")
    return manifest, requests, records, graded, counts


def _reference(manifest, requests):
    protocol, provenance = manifest["declared_protocol"], manifest.get("request_provenance")
    if (not isinstance(provenance, dict) or not protocol.get("reference_root") or
            provenance.get("reference_root") != protocol["reference_root"] or
            not isinstance(protocol.get("reference_runs"), dict) or
            set(protocol["reference_runs"]) != {"gemma12b", "qwen27b"} or
            any(not isinstance(value, dict) for value in protocol["reference_runs"].values()) or
            provenance.get("reference_runs") != protocol["reference_runs"]):
        raise ValueError("frozen protocol and provenance must agree on production references")
    matches = [(key, value) for key, value in protocol["reference_runs"].items()
               if value.get("requested_model") == manifest["requested_model"]]
    if len(matches) != 1:
        raise ValueError("exactly one matching-model production reference required")
    key, reference = matches[0]
    corpus = manifest["track"].removeprefix("baseline_")
    if reference.get("stage_id") != corpus + "_" + key:
        raise ValueError("production reference stage identity differs from corpus/model")
    declared_root = Path(protocol["reference_root"])
    declared_dir = declared_root / reference["stage_id"]
    if Path(reference.get("run_dir", "")) != declared_dir:
        raise ValueError("production reference directory differs from frozen root/stage")
    path = declared_dir if declared_dir.is_absolute() else REPOSITORY_ROOT / declared_dir
    manifest_bytes = (path / "run_manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != reference.get("run_manifest_sha256"):
        raise ValueError("production reference manifest file hash mismatch")
    summary = prepare_production_report(path)
    expected = {"verified_manifest_seal_sha256": reference.get("manifest_seal_sha256"),
        "request_corpus_sha256": reference.get("request_corpus_sha256"),
        "requested_model": manifest["requested_model"], "decoding": manifest["decoding"],
        "code_revision": reference.get("code_revision"), "track": "production_" + corpus}
    if any(summary.get(field) != value for field, value in expected.items()):
        raise ValueError("production reference seal, model, decoding or source identity mismatch")
    if reference.get("decoding") != manifest["decoding"]:
        raise ValueError("baseline and production reference decoding differ")
    if (summary["annotation_origin"] != protocol["gold_origin"] or
            summary["human_verified"] != protocol["human_verified"]):
        raise ValueError("baseline and production reference gold origin differs")
    source_rows = [json.loads(line) for line in (path / "requests.jsonl").read_bytes().splitlines() if line.strip()]
    sources = {row["case_id"]: row for row in source_rows}
    if set(sources) != {row["case_id"] for row in requests} or len(sources) != len(requests):
        raise ValueError("baseline and production reference case sets differ")
    for row in requests:
        source = sources[row["case_id"]]
        if (row.get("reference_request_sha256") != hashlib.sha256(_json_bytes(source)).hexdigest() or
                any(row.get(field) != source.get(field) for field in SOURCE_FIELDS)):
            raise ValueError("baseline document, target, gold or source-request identity changed")
    return reference, summary, source_rows


def _changes(old_cases, new_cases):
    """Compare schema-valid exact semantic matches before each arm's validator."""
    old = {case["case_id"]: case for case in old_cases}
    new = {case["case_id"]: case for case in new_cases}
    if set(old) != set(new):
        raise ValueError("semantic comparison case identities differ")

    def group(keys):
        comparable = [key for key in keys if not old[key]["missing"] and not new[key]["missing"]]
        helpful = [key for key in comparable if not old[key]["semantic_match"] and new[key]["semantic_match"]]
        harmful = [key for key in comparable if old[key]["semantic_match"] and not new[key]["semantic_match"]]
        return {"planned": len(keys), "comparable": len(comparable), "incomplete": len(keys) - len(comparable),
            "helpful": len(helpful), "harmful": len(harmful),
            "both_correct": sum(old[key]["semantic_match"] and new[key]["semantic_match"] for key in comparable),
            "both_incorrect": sum(not old[key]["semantic_match"] and not new[key]["semantic_match"] for key in comparable),
            "helpful_case_ids": helpful, "harmful_case_ids": harmful}

    return {"overall": group(sorted(old)),
        "by_task": {task: group(sorted(key for key in old if old[key]["task"] == task)) for task in TASKS},
        "by_stratum": {stratum: {task: group(sorted(key for key in old if old[key]["task"] == task
            and old[key]["stratum"] == stratum)) for task in TASKS}
            for stratum in sorted({case["stratum"] for case in old.values()})}}


def _outcomes(cases):
    observed = [case for case in cases if not case["missing"]]
    return {"planned": len(cases), "observed": len(observed), "missing": len(cases) - len(observed),
        **{name: sum(bool(case.get(name)) for case in observed) for name in
           ("semantic_match", "correct", "wrong", "null", "safe_null", "positive_null", "malformed")}}


def _candidate_recall(rows, *, baseline):
    result = {}
    for task in TASKS:
        task_rows = [row for row in rows if row["task"] == task]
        positives = [row for row in task_rows if row["expected_entity_id"] is not None]
        found = sum(row["expected_entity_id"] in row["candidate_entity_ids"] if baseline else
                    bool(row["gold_entity_in_candidates"]) for row in positives)
        result[task] = {"positive_planned": len(positives), "gold_retrieved": found,
            "recall": found / len(positives) if positives else None,
            "candidate_count": _distribution([len(row["candidate_entity_ids"]) if baseline else
                len({card["entity_id"] for card in _binding_cards(row["pack"])
                     if card["binding_surface"] == row["target_surface"]}) for row in task_rows]),
            "scope": "B provided glossary IDs" if baseline else "C candidate cards bound to the exact target surface"}
    return result


def _routing_acceptance(cases, *, baseline):
    observed = [case for case in cases if case["task"] == "structured_routing" and not case["missing"]]
    accepted = lambda case: bool(case.get("baseline_accepted") if baseline else case.get("guard_compliant"))
    return {"validator": "schema and ID membership in B's supplied glossary cards" if baseline else
            "C's existing surface-bound production execution guard",
        "accepted_correct_nonnull": sum(bool(case.get("nonnull")) and accepted(case) and case["semantic_match"] for case in observed),
        "accepted_wrong_nonnull": sum(bool(case.get("wrong")) and accepted(case) for case in observed),
        "rejected_correct_nonnull": sum(bool(case.get("nonnull")) and not accepted(case) and case["semantic_match"] for case in observed),
        "rejected_wrong_nonnull": sum(bool(case.get("wrong")) and not accepted(case) for case in observed),
        "accepted_null": sum(bool(case.get("null")) and accepted(case) for case in observed)}


def prepare_report(run_dir, *, compare=None):
    run_dir = Path(run_dir)
    manifest, requests, records, graded, counts = _read_run(run_dir)
    reference, production, source_rows = _reference(manifest, requests)
    documents = [row for row in requests if row["task"] == "document_qa"]
    operational = {"overall": _operational(requests, records),
        **{task: _operational([row for row in requests if row["task"] == task], records) for task in TASKS}}
    by_task = {task: {"B": _outcomes([case for case in graded["cases"] if case["task"] == task]),
        "C": _outcomes([case for case in production["metrics"]["cases"] if case["task"] == task])} for task in TASKS}
    summary = {"kind": "sealed_production_baseline_report", "status": manifest["status"],
        "track": manifest["track"], "protocol": manifest["protocol"],
        "annotation_origin": manifest["declared_protocol"]["gold_origin"],
        "human_verified": manifest["declared_protocol"]["human_verified"], "quality_claim": False,
        **{key: manifest.get(key) for key in ("code_revision", "requested_model", "served_models", "endpoint",
            "started_at", "finished_at", "decoding", "declared_protocol", "request_provenance", "request_corpus_sha256")},
        "verified_manifest_seal_sha256": manifest["seal_sha256"],
        "verified_artifact_sha256": manifest["artifact_sha256"],
        "counts": {**counts, "attempted_count": len(records), "not_attempted_count": len(requests) - len(records),
            "documents": len(documents), "families": len({row["family_id"] for row in documents})},
        "strata": dict(Counter(row["stratum"] for row in documents)),
        "metrics": graded, "operational": operational,
        "production_comparison": {"direction": "B plain glossary retrieval -> C KTRF production",
            "primary_metric": "schema-valid exact semantic_match before either arm's execution validator",
            "reference": reference, "reference_status": production["status"],
            "by_task": by_task, "paired_changes": _changes(graded["cases"], production["metrics"]["cases"]),
            "candidate_recall": {"B": _candidate_recall(requests, baseline=True),
                                  "C": _candidate_recall(source_rows, baseline=False)},
            "routing_acceptance": {"B": _routing_acceptance(graded["cases"], baseline=True),
                                   "C": _routing_acceptance(production["metrics"]["cases"], baseline=False)},
            "cost": {"B": operational, "C": production["operational"]}},
        "limitations": [*manifest["declared_protocol"]["limitations"],
            "The primary semantic metric is schema-valid exact matching before validator decisions; malformed and missing outputs never earn null credit.",
            "B/C share documents, gold, model and decoding, but differ in retrieval, prompt/policy packaging and execution validation. This is a system-package comparison, not an isolated resolver or formatting effect.",
            "B uses only its supplied-ID membership validator; it is never evaluated through C's execution guard. Validator acceptance and semantic correctness are reported separately.",
            "C is a previously sealed run, not a concurrent randomized control; timing can differ because of host contention and runtime state.",
            "LLM-only A is not a new primary condition: dictionary-free models cannot fairly recover opaque glossary IDs. Historical A results do not isolate the value of KTRF.",
            "Candidate recall has arm-specific evidence scope: B supplied IDs versus C exact-target-bound cards; candidate-set size and cost must accompany it.",
            "Gold is AI authored; no independent human-gold or deployment-risk guarantee is claimed.",
            "Latency totals use math.fsum; failures retain recorded latency, and absent calls receive no imputed latency.",
            "COMPLETE describes response coverage, including malformed responses, not task quality.",
        ]}
    if compare is not None:
        other = prepare_report(compare)
        if (other["request_corpus_sha256"] != summary["request_corpus_sha256"] or
                other["declared_protocol"] != summary["declared_protocol"] or other["decoding"] != summary["decoding"] or
                other["track"] != summary["track"]):
            raise ValueError("paired B-model comparison requires identical requests, protocol, source references and decoding")
        summary["comparison"] = {"baseline_model": other["requested_model"], "current_model": summary["requested_model"],
            "baseline_manifest_seal_sha256": other["verified_manifest_seal_sha256"],
            "primary_metric": "schema-valid exact semantic_match before B's supplied-ID validator",
            **_changes(other["metrics"]["cases"], graded["cases"])}
    return summary


def render_markdown(summary):
    counts, comparison = summary["counts"], summary["production_comparison"]
    lines = ["# Plain glossary retrieval B versus KTRF production C", "",
        f"B status: **{summary['status']}**; C reference status: **{comparison['reference_status']}**. "
        f"Model: `{summary['requested_model']}`. {counts['documents']} target passages; {counts['request_count']} planned B calls.", "",
        f"Gold: `{summary['annotation_origin']}`; human verified: `{str(summary['human_verified']).lower()}`. "
        f"B request SHA-256: `{summary['request_corpus_sha256']}`.", "",
        f"Received {counts['received_count']}; missing {counts['missing_count']}; malformed {counts['malformed_count']}; "
        f"API/transport errors {counts['error_count']}.", "",
        "Primary success is a schema-valid exact semantic match **before** either arm's execution validator. "
        "The same frozen documents, gold, requested model and decoding were verified. Prompts, evidence selection "
        "and policies differ, so this measures the complete system package. QA and execution remain separate calls.", "",
        "## Semantic outcomes", "",
        "| Task | Arm | Semantic match / planned | Wrong non-null | Valid null | Malformed | Missing |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for task in TASKS:
        for arm in ("B", "C"):
            values = comparison["by_task"][task][arm]
            lines.append(f"| {task} | {arm} | {values['semantic_match']}/{values['planned']} | {values['wrong']} | "
                f"{values['null']} | {values['malformed']} | {values['missing']} |")
    lines += ["", "## Paired changes B → C", "",
        "Helpful means C succeeds where B fails; harmful means B succeeds where C fails. "
        "Missing pairs are incomplete; malformed outputs remain failures.", "",
        "| Task | Comparable | Helpful for C | Harmful for C | Incomplete |", "|---|---:|---:|---:|---:|"]
    for task, values in comparison["paired_changes"]["by_task"].items():
        lines.append(f"| {task} | {values['comparable']} | {values['helpful']} | {values['harmful']} | {values['incomplete']} |")
    lines += ["", "| Stratum | Task | Helpful for C | Harmful for C | Incomplete |", "|---|---|---:|---:|---:|"]
    for stratum, tasks in comparison["paired_changes"]["by_stratum"].items():
        for task, values in tasks.items():
            lines.append(f"| {stratum} | {task} | {values['helpful']} | {values['harmful']} | {values['incomplete']} |")
    lines += ["", "## Operational execution decisions", "",
        "B validates the schema and membership in its supplied glossary IDs. C applies its original production "
        "guard. B is never passed through C's guard. Acceptance alone does not imply correctness.", "",
        "| Arm | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, values in comparison["routing_acceptance"].items():
        lines.append(f"| {arm} | {values['accepted_correct_nonnull']} | {values['accepted_wrong_nonnull']} | "
            f"{values['rejected_correct_nonnull']} | {values['rejected_wrong_nonnull']} | {values['accepted_null']} |")
    lines += ["", "## Retrieval and cost", "",
        "| Task | Arm | Gold retrieved / positive targets | Median candidates | p95 ms | Prompt tokens | Completion tokens |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for task in TASKS:
        for arm in ("B", "C"):
            recall, cost = comparison["candidate_recall"][arm][task], comparison["cost"][arm][task]
            usage = cost["actual_usage"]
            lines.append(f"| {task} | {arm} | {recall['gold_retrieved']}/{recall['positive_planned']} | "
                f"{recall['candidate_count']['p50']} | {cost['latency_ms']['p95']} | "
                f"{usage['prompt_tokens']['total']} | {usage['completion_tokens']['total']} |")
    if "comparison" in summary:
        values = summary["comparison"]
        lines += ["", "## Paired B-model comparison", "",
            f"`{values['baseline_model']}` → `{values['current_model']}` on identical B requests and source references. "
            "This changes model family as well as size.", "",
            "| Task | Helpful | Harmful | Incomplete |", "|---|---:|---:|---:|"]
        for task, row in values["by_task"].items():
            lines.append(f"| {task} | {row['helpful']} | {row['harmful']} | {row['incomplete']} |")
    lines += ["", "## Reproduction and limitations", "",
        f"B manifest seal: `{summary['verified_manifest_seal_sha256']}`. "
        f"C manifest seal: `{comparison['reference']['manifest_seal_sha256']}`.", "",
        "Both arms' sealed artifacts and frozen grading were verified. The matching C source manifest, case set, "
        "per-request hash, documents, gold, model and decoding were checked before comparison.", "",
        "Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), "
        "[responses](responses.jsonl), [grades](graded.json).", "",
        *("- " + limitation for limitation in summary["limitations"]), ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compare", type=Path, help="Other B-model run on identical frozen requests")
    args = parser.parse_args()
    summary = prepare_report(args.run_dir, compare=args.compare)
    (args.run_dir / "summary.json").write_bytes(_json_bytes(summary))
    (args.run_dir / "RESULTS.md").write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps({"run_dir": str(args.run_dir), "status": summary["status"], **summary["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

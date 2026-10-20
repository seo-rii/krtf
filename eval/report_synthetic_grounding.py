"""Report a sealed synthetic expansion run without reading mutable fixtures."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from ktrf.context import validate_llm_grounding

CONDITIONS = ("original", "surface_only", "schema_only", "both", "full_pack")
ARTIFACTS = ("requests.jsonl", "responses.jsonl", "graded.json")
PROTOCOLS = {"synthetic_expansion": "synthetic_grounding_expansion_v1",
             "synthetic_expansion_v2": "synthetic_grounding_expansion_v2"}


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
            row["pack"], purpose="execution", execution_contract='legacy_surface_v1')["valid"]
    return True


def _oracle_ceiling(rows):
    """A perfect semantic answer still cannot bypass the frozen execution guard."""
    by_task, by_family = defaultdict(list), defaultdict(list)
    blocked = []
    for row in rows:
        field = "answer" if row["task"] == "document_qa" else "entity_id"
        expected = row["expected_answer"] if field == "answer" else row["expected_entity_id"]
        succeeds = _correct(row, {"status": "RECEIVED", "response": {field: expected}})
        by_task[row["task"]].append(succeeds)
        by_family[row["family_id"]].append(succeeds)
        if not succeeds:
            blocked.append(row["case_id"])
    total = sum(len(values) for values in by_task.values())
    success = sum(sum(values) for values in by_task.values())
    return {"planned": total, "success_ceiling": success,
            "rate": success / total if total else None,
            "by_task": {task: {"planned": len(values), "success_ceiling": sum(values),
                              "rate": sum(values) / len(values)}
                        for task, values in sorted(by_task.items())},
            "family_macro_ceiling": (sum(sum(values) / len(values) for values in by_family.values())
                                     / len(by_family) if by_family else None),
            "guard_blocked_gold_case_ids": blocked}


def _routing_abstentions(rows, recorded, condition):
    """Supplement the original gold grade; never redefine a positive as NIL."""
    result = Counter()
    keys = ("positive_planned", "positive_observed", "gold_guard_authorized",
            "gold_guard_blocked", "policy_compliant_null_on_guard_blocked_positive",
            "avoidable_null_on_guard_authorized_positive", "missing_positive", "malformed_positive")
    for row in rows:
        if row["task"] != "structured_routing" or row["expected_entity_id"] is None:
            continue
        result["positive_planned"] += 1
        authorized = _correct(row, {"status": "RECEIVED",
                                   "response": {"entity_id": row["expected_entity_id"]}})
        result["gold_guard_authorized" if authorized else "gold_guard_blocked"] += 1
        record = recorded.get((row["case_id"], condition), {})
        if "response" not in record:
            result["missing_positive"] += 1
            continue
        result["positive_observed"] += 1
        response = record["response"]
        value = response.get("entity_id") if isinstance(response, dict) else None
        if (record.get("status") != "RECEIVED" or not isinstance(response, dict)
                or "entity_id" not in response or
                (value is not None and (not isinstance(value, str) or not value.strip()))):
            result["malformed_positive"] += 1
            continue
        if value is None:
            result["avoidable_null_on_guard_authorized_positive" if authorized else
                   "policy_compliant_null_on_guard_blocked_positive"] += 1
    return {key: result[key] for key in keys}


def _shortcut_diagnostics(rows):
    """Text-blind rules read only the original candidate cards, never model outputs."""
    documents = defaultdict(dict)
    for row in rows:
        if row["stratum"] == "contextual_collision":
            documents[row["document_id"]][row["task"]] = row
    rules = {name: Counter() for name in ("non_main_suffix", "first_candidate", "last_candidate")}
    positions, candidate_counts, cases = Counter(), Counter(), []
    for document_id, tasks in sorted(documents.items()):
        row = tasks.get("document_qa", next(iter(tasks.values())))
        by_id = {}
        for card in row.get("cards", []):
            by_id.setdefault(card["entity_id"], card)
        candidates = list(by_id.values())
        ids = [card["entity_id"] for card in candidates]
        target_position = ids.index(row["expected_entity_id"]) + 1 if row["expected_entity_id"] in ids else None
        positions[str(target_position) if target_position is not None else "absent"] += 1
        candidate_counts[str(len(ids))] += 1
        main = [card for card in candidates if card["entity_id"].endswith(".main")]
        others = [card for card in candidates if not card["entity_id"].endswith(".main")]
        chosen = {"non_main_suffix": others[0] if len(main) == len(others) == 1 else None,
                  "first_candidate": candidates[0] if candidates else None,
                  "last_candidate": candidates[-1] if candidates else None}
        selections = {}
        for name, candidate in chosen.items():
            stats = rules[name]
            stats["documents"] += 1
            stats["support"] += candidate is not None
            eid = candidate["entity_id"] if candidate else None
            answer = candidate["definition"] if candidate else None
            selections[name] = eid
            if "document_qa" in tasks:
                qa = tasks["document_qa"]
                stats["qa_cases"] += 1
                stats["qa_exact_matches"] += answer == qa["expected_answer"]
            if "structured_routing" in tasks:
                routing = tasks["structured_routing"]
                stats["routing_cases"] += 1
                stats["semantic_id_matches"] += eid == routing["expected_entity_id"]
                valid = validate_llm_grounding({"selections": [{"surface": routing["target_surface"],
                    "entity_id": eid}]}, routing["pack"], purpose="execution", execution_contract='legacy_surface_v1')["valid"]
                stats["guard_accepted_semantic_id_matches"] += valid and eid == routing["expected_entity_id"]
                stats["guard_rejected_nonnull_ids"] += eid is not None and not valid
        cases.append({"document_id": document_id, "family_id": row["family_id"],
            "corpus_version": row.get("corpus_version", "v1"),
            "contrast_pair_id": row.get("contrast_pair_id"), "contrast_member": row.get("contrast_member"),
            "candidate_ids_in_original_order": ids, "expected_entity_id": row["expected_entity_id"],
            "original_target_candidate_position": target_position, "selected_ids": selections})
    count_keys = ("documents", "support", "qa_cases", "qa_exact_matches", "routing_cases",
                  "semantic_id_matches", "guard_accepted_semantic_id_matches", "guard_rejected_nonnull_ids")
    return {"documents": len(documents), "candidate_source": "original.cards in presentation order; first card per entity ID",
        "uses_document_text": False, "uses_model_outputs": False, "position_base": 1,
        "original_target_candidate_positions": dict(sorted(positions.items())),
        "candidate_count_distribution": dict(sorted(candidate_counts.items())),
        "rules": {name: {**{key: stats[key] for key in count_keys},
                          "qa_accuracy_all_cases": stats["qa_exact_matches"] / stats["qa_cases"] if stats["qa_cases"] else None,
                          "semantic_id_accuracy_all_cases": stats["semantic_id_matches"] / stats["routing_cases"] if stats["routing_cases"] else None}
                  for name, stats in rules.items()}, "cases": cases}


def analyze_frozen_requests(requests):
    """Export corpus-only diagnostics; no responses, grader or fixture reload required."""
    original = [row for row in requests if row["condition"] == "original"]
    if not original:
        raise ValueError("corpus diagnostics require original-condition requests")
    return {"semantic_oracle_ceiling": _oracle_ceiling(original),
            "contextual_collision_shortcuts": _shortcut_diagnostics(original)}


def prepare_report(run_dir):
    """Verify frozen artifacts and return a summary, without changing files."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    if manifest.get("track") not in PROTOCOLS or manifest.get("protocol") != PROTOCOLS[manifest["track"]]:
        raise ValueError("report requires the synthetic_expansion track or its matching v2 track/protocol")
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

    comparisons, operational, abstentions, observed_ceilings = {}, {}, {}, {}
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
        abstentions[condition] = _routing_abstentions(rows, recorded, condition)
        observed_ceilings[condition] = _oracle_ceiling([
            row for row in rows if "response" in recorded.get((row["case_id"], condition), {})])
    unique = [row for row in requests if row["condition"] == "original"]
    docs = {row["document_id"]: row for row in unique}
    return {"kind": "sealed_synthetic_grounding_report", "status": manifest["status"],
        "track": manifest["track"], "protocol": manifest["protocol"],
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
        **analyze_frozen_requests(unique),
        "observed_semantic_oracle_ceiling": observed_ceilings,
        "routing_abstention_diagnostics": abstentions,
        "operational": operational, "quality_claim": False,
        "limitations": ["AI-authored synthetic documents and gold; not independent human gold or deployment traffic.",
            "Family clusters are correlated; family macro is descriptive, without a risk bound or risk certification.",
            "The semantic oracle ceiling assumes authored answers are known; it isolates the execution guard and is not an achievable LLM or information-availability guarantee.",
            "Text-blind candidate baselines are corpus bias diagnostics, not model results; selection rules are fixed without reading document text or model outputs.",
            "V1 authoring IDs such as .main and .rival can expose answer patterns; candidate order is also measured. These diagnostics do not alter sealed gold or grades.",
            "Policy-compliant null on guard-blocked positive routing remains a semantic miss in the original grade; it is separated from avoidable null on guard-authorized positives.",
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
    ceiling, shortcuts = summary["semantic_oracle_ceiling"], summary["contextual_collision_shortcuts"]
    summary_artifact = summary.get("summary_artifact", "summary.json")
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
        f"Model: `{summary['requested_model']}`. Experiment code revision: `{summary['code_revision']}`. "
        f"Request SHA-256: `{summary['request_corpus_sha256']}`.", "",
        *([f"Supplemental reporting code revision: `{summary['reporting_code_revision']}`. "
           "The experiment revision and original sealed grades are preserved.", ""]
          if summary.get("report_mode") == "supplement" else []),
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
        "and appear separately; family macro is descriptive over observed outputs. The sealed over-abstention count "
        "includes every valid null on positive semantic gold; the policy-aware routing breakdown below leaves this original grade unchanged.", "",
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
        "## Semantic oracle ceiling and policy-aware abstention", "",
        "This diagnostic supplies the authored correct answer or ID for every frozen request. QA has no execution gate; "
        "routing still passes the original execution guard. It uses no model responses and does not revise semantic gold. "
        "It isolates the guard ceiling, not whether the prompt contains enough evidence for an LLM to find the answer.", "",
        "| Task | Oracle successes / planned | Ceiling |", "|---|---:|---:|"]
    for task, values in ceiling["by_task"].items():
        lines.append(f"| {task} | {values['success_ceiling']}/{values['planned']} | {percentage(values['rate'])} |")
    lines += [f"| all tasks | {ceiling['success_ceiling']}/{ceiling['planned']} | {percentage(ceiling['rate'])} |", "",
        f"Planned family-macro ceiling: {percentage(ceiling['family_macro_ceiling'])}. "
        f"Per-condition ceilings over observed outputs are retained separately in `{summary_artifact}`, so missing cases do not change a comparison denominator silently.", "",
        "Positive routing with an unauthorized correct ID cannot succeed under the sealed rubric. A valid null in that case "
        "complies with execution policy while remaining a semantic miss. Null on an authorized correct ID is avoidable abstention. "
        "Malformed or missing outputs enter neither null count.", "",
        "| Condition | Positive routing planned | Gold ID blocked by guard | Policy-compliant null on blocked gold | Avoidable null on authorized gold | Observed family-macro ceiling |",
        "|---|---:|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        nulls = summary["routing_abstention_diagnostics"][condition]
        observed_ceiling = summary["observed_semantic_oracle_ceiling"][condition]
        lines.append(f"| {condition} | {nulls['positive_planned']} | {nulls['gold_guard_blocked']} | "
            f"{nulls['policy_compliant_null_on_guard_blocked_positive']} | "
            f"{nulls['avoidable_null_on_guard_authorized_positive']} | {percentage(observed_ceiling['family_macro_ceiling'])} |")
    lines += ["", "## Text-blind candidate bias diagnostics", "",
        f"The {shortcuts['documents']} contextual-collision documents are examined once using original-condition candidate cards, "
        "in their presentation order. These fixed rules read neither document text nor model output. QA returns the selected "
        "candidate's definition; the raw semantic ID is scored separately from execution authorization. They are corpus baselines, not LLM scores.", "",
        "`non_main_suffix` chooses the non-`.main` ID only with exactly one `.main` candidate and one other distinct candidate. "
        "Otherwise it returns null. `first_candidate` and `last_candidate` expose order shortcuts; repeated IDs use their first card. "
        "Support counts documents where the rule makes a non-null selection; accuracy denominators include unsupported cases.", "",
        "| Rule | Support / documents | QA exact match / cases | Semantic ID match / cases | Guard-accepted semantic matches | Non-null guard rejections |",
        "|---|---:|---:|---:|---:|---:|"]
    for name, values in shortcuts["rules"].items():
        lines.append(f"| {name} | {values['support']}/{values['documents']} | "
            f"{values['qa_exact_matches']}/{values['qa_cases']} | "
            f"{values['semantic_id_matches']}/{values['routing_cases']} | "
            f"{values['guard_accepted_semantic_id_matches']} | {values['guard_rejected_nonnull_ids']} |")
    lines += ["", "Gold target positions in the original candidate order (1-based; `absent` means no candidate): "
        f"`{json.dumps(shortcuts['original_target_candidate_positions'], sort_keys=True)}`. "
        "Per-document candidate IDs, target positions, predictions and any v2 contrast-pair metadata are retained in summary.json. "
        "V1 authoring IDs leak semantic roles; v2 opaque IDs and paired contexts must be checked with these same diagnostics, "
        "without treating synthetic performance as a production risk estimate.", "",
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
    lines += ["", f"Actual usage observation counts, totals and distributions are in `{summary_artifact}`; estimated input "
        "tokens are reported separately and do not replace API usage.", "", "## Limits and artifact verification", ""]
    lines.extend(f"- {limit}" for limit in summary["limitations"])
    lines += ["", "All three input artifact SHA-256 values and the canonical manifest seal were verified before this report "
        "was generated. This report reads only frozen requests, responses, graded diagnostics and manifest; "
        "it does not reload current fixtures.", "",
        f"Manifest seal: `{summary['verified_manifest_seal_sha256']}`.", "",
        f"Artifacts: [summary]({summary_artifact}), "
        "[sealed manifest](run_manifest.json), [requests](requests.jsonl), "
        "[responses](responses.jsonl), [graded diagnostics](graded.json).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--supplement", action="store_true",
                        help="write reviewed_summary.json and REVIEWED_RESULTS.md; preserve original reports")
    parser.add_argument("--analysis-revision", help="commit of the supplemental reporting code")
    args = parser.parse_args()
    if args.supplement and not (args.analysis_revision and args.analysis_revision.strip()):
        parser.error("--analysis-revision is required with --supplement")
    if args.analysis_revision and not args.supplement:
        parser.error("--analysis-revision is only valid with --supplement")
    summary = prepare_report(args.run_dir)
    summary_name, markdown_name = "summary.json", "RESULTS.md"
    if args.supplement:
        summary_name, markdown_name = "reviewed_summary.json", "REVIEWED_RESULTS.md"
        summary.update(report_mode="supplement", reporting_code_revision=args.analysis_revision,
                       summary_artifact=summary_name)
    (args.run_dir / summary_name).write_bytes(_json_bytes(summary))
    (args.run_dir / markdown_name).write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps({"run_dir": str(args.run_dir), "status": summary["status"], **summary["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

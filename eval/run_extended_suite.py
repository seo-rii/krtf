"""Run sealed, single-repeat QA and execution experiments on a local model server."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from .hf_qa import canonical, character_f1, normalize_answer, response_error
from .production_grounding import production_response_error, validate_production_requests
from .run_followup_llm import ANSWER_SCHEMA, ARTIFACTS, DECODING
from .run_product_llm import _request_json, parse_model_json

PROTOCOL_ID = "ktrf_extended_v1"
REVIEW_CONDITION_COUNTS = {"review_abcd": 8, "review_policy": 6,
                           "review_budget": 6, "review_nomiracl": 3, "review_routing": 8}
CONFIRMATION_CONDITION_COUNTS = {"routing_confirmation": 6, "evidence_control": 4, "evidence_efficiency": 5, "evidence_robustness": 6,
                                 "support_recovery": (2, 8), "evidence_closure": 5}
OCCURRENCE_EXPERIMENTS = set(CONFIRMATION_CONDITION_COUNTS)
AUDITED_CONDITION_COUNTS = REVIEW_CONDITION_COUNTS | CONFIRMATION_CONDITION_COUNTS
DIAGNOSTIC_CONDITION_COUNTS = {"source_pack_factorial": 6, "fresh_compact": 3,
                               "safety_robustness": 4, **AUDITED_CONDITION_COUNTS}
DIAGNOSTIC_EXPERIMENTS = set(DIAGNOSTIC_CONDITION_COUNTS)
EXPERIMENTS = {"transfer", "budget", "corpus", "pack", "semantic_safety"} | DIAGNOSTIC_EXPERIMENTS
SAFETY_EXPERIMENTS = {"semantic_safety", "safety_robustness", "review_routing"} | OCCURRENCE_EXPERIMENTS
ROUTING_SCHEMA = {"type": "object", "properties": {"selections": {
    "type": "array", "minItems": 1, "maxItems": 1, "items": {
        "type": "object", "properties": {"surface": {"type": "string"},
            "entity_id": {"anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]}},
        "required": ["surface", "entity_id"], "additionalProperties": False}}},
    "required": ["selections"], "additionalProperties": False}
SAFETY_METRICS = ("correct", "accepted_correct_id", "accepted_wrong_id", "rejected_wrong_id",
                  "correct_abstention", "over_abstention", "rejected_correct_id",
                  "attempted_nonnull", "guard_valid", "semantic_match")


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def decoding_for(protocol):
    if protocol["experiment"] in OCCURRENCE_EXPERIMENTS:
        return {**DECODING, "max_tokens": 768}
    return {**DECODING, "max_tokens": 384} if protocol["experiment"] == "review_routing" else DECODING


def schema_for(rows, protocol):
    if protocol["experiment"] == "evidence_closure":
        from .evidence_closure import evidence_closure_schema
        return {json.dumps([row["case_id"], row["condition"]], ensure_ascii=False,
                           separators=(",", ":")): evidence_closure_schema(row) for row in rows}
    if protocol["experiment"] == "support_recovery":
        from .support_recovery import support_recovery_schema
        return {json.dumps([row["case_id"], row["condition"]], ensure_ascii=False,
                           separators=(",", ":")): support_recovery_schema(row) for row in rows}
    if protocol["experiment"] == "evidence_robustness":
        from .evidence_robustness import evidence_robustness_schema
        return {json.dumps([row["case_id"], row["condition"]], ensure_ascii=False,
                           separators=(",", ":")): evidence_robustness_schema(row) for row in rows}
    if protocol["experiment"] == "evidence_efficiency":
        from .evidence_efficiency import evidence_efficiency_schema
        # Selective routing has a different schema for easy and difficult requests.
        return {json.dumps([row["case_id"], row["condition"]], ensure_ascii=False,
                           separators=(",", ":")): evidence_efficiency_schema(row) for row in rows}
    if protocol["experiment"] == "evidence_control":
        from .evidence_control import evidence_control_schema
        return {row["condition"]: evidence_control_schema(row) for row in rows}
    if protocol["experiment"] == "routing_confirmation":
        from .routing_confirmation import confirmation_schema
        return {row["condition"]: confirmation_schema(row) for row in rows}
    if protocol["experiment"] == "review_routing":
        from .review_business import ROUTING_SCHEMA as schema
        return schema
    return ANSWER_SCHEMA if rows[0]["task"] == "document_qa" else ROUTING_SCHEMA


def request_schema_for(row, protocol):
    if protocol["experiment"] == "evidence_closure":
        from .evidence_closure import evidence_closure_schema
        return evidence_closure_schema(row)
    if protocol["experiment"] == "support_recovery":
        from .support_recovery import support_recovery_schema
        return support_recovery_schema(row)
    if protocol["experiment"] == "evidence_robustness":
        from .evidence_robustness import evidence_robustness_schema
        return evidence_robustness_schema(row)
    if protocol["experiment"] == "evidence_efficiency":
        from .evidence_efficiency import evidence_efficiency_schema
        return evidence_efficiency_schema(row)
    if protocol["experiment"] == "evidence_control":
        from .evidence_control import evidence_control_schema
        return evidence_control_schema(row)
    if protocol["experiment"] == "routing_confirmation":
        from .routing_confirmation import confirmation_schema
        return confirmation_schema(row)
    return schema_for([row], protocol)


def validate_protocol(protocol):
    if (not isinstance(protocol, dict) or protocol.get("kind") != PROTOCOL_ID
            or protocol.get("phase") != "FINAL_FROZEN" or protocol.get("experiment") not in EXPERIMENTS):
        raise ValueError("FINAL_FROZEN extended envelope required")
    conditions = protocol.get("conditions")
    if (not isinstance(conditions, list) or not conditions
            or any(not isinstance(c, str) or re.fullmatch(r"[a-z][a-z0-9_]*", c) is None for c in conditions)
            or len(set(conditions)) != len(conditions)):
        raise ValueError("unique explicit condition names required")
    condition_count = DIAGNOSTIC_CONDITION_COUNTS.get(protocol["experiment"])
    allowed_counts = condition_count if isinstance(condition_count, tuple) else (condition_count,)
    if condition_count is not None and len(conditions) not in allowed_counts:
        raise ValueError(f"{protocol['experiment']} requires {condition_count} conditions")
    if type(protocol.get("repeat_count")) is not int or protocol["repeat_count"] != 1:
        raise ValueError("extended experiments require repeat_count=1")
    if (not isinstance(protocol.get("limitations"), list) or not protocol["limitations"]
            or any(not isinstance(v, str) or not v.strip() for v in protocol["limitations"])):
        raise ValueError("explicit limitations required")
    comparisons = protocol.get("comparisons", [[conditions[0], c] for c in conditions[1:]])
    if (not isinstance(comparisons, list) or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
            or pair[0] == pair[1] or any(c not in conditions for c in pair) for pair in comparisons)):
        raise ValueError("comparisons must name two different declared conditions")
    if len({tuple(pair) for pair in comparisons}) != len(comparisons):
        raise ValueError("duplicate comparison")
    return protocol


def validate_requests(rows, protocol):
    validate_protocol(protocol)
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("nonempty request object list required")
    tasks = {row.get("task") for row in rows}
    if len(tasks) != 1 or not tasks <= {"document_qa", "structured_routing"}:
        raise ValueError("mixed tasks or unknown task")
    safety = next(iter(tasks)) == "structured_routing"
    if safety != (protocol["experiment"] in SAFETY_EXPERIMENTS):
        raise ValueError("task differs from declared experiment")
    if safety:
        if protocol["experiment"] == "evidence_closure":
            from .evidence_closure import validate_evidence_closure_requests
            validate_evidence_closure_requests(rows)
        elif protocol["experiment"] == "support_recovery":
            from .support_recovery import validate_support_recovery_requests
            validate_support_recovery_requests(rows, conditions=protocol["conditions"])
        elif protocol["experiment"] == "evidence_robustness":
            from .evidence_robustness import validate_evidence_robustness_requests
            validate_evidence_robustness_requests(rows)
        elif protocol["experiment"] == "evidence_efficiency":
            from .evidence_efficiency import validate_evidence_efficiency_requests
            validate_evidence_efficiency_requests(rows)
        elif protocol["experiment"] == "evidence_control":
            from .evidence_control import validate_evidence_control_requests
            validate_evidence_control_requests(rows)
        elif protocol["experiment"] == "routing_confirmation":
            from .routing_confirmation import validate_confirmation_requests
            validate_confirmation_requests(rows)
        elif protocol["experiment"] == "review_routing":
            from .review_business import validate_business_requests
            validate_business_requests(rows)
        elif protocol["experiment"] == "safety_robustness":
            from .diagnostic_safety import validate_robustness_requests
            validate_robustness_requests(rows)
        else:
            validate_production_requests(rows, check_current_policy=False)
    diagnostic = protocol["experiment"] in DIAGNOSTIC_EXPERIMENTS
    fixed = (("stratum", "text", "target_surface", "target_span", "gold", "expected_entity_id", "document_sha256")
             if safety else ("stratum", "positive_gold", "expected_answers", "parent_document_id",
                             "document_sha256", "source_text", "question"))
    fixed += ("evaluation_split", "family_id")
    grouped, seen, family_splits = defaultdict(list), set(), defaultdict(set)
    for row in rows:
        for field in ("case_id", "condition", "system", "user"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("nonempty string field required: " + field)
        if row.get("experiment", protocol["experiment"]) != protocol["experiment"]:
            raise ValueError("mixed experiment")
        for field in ("evaluation_split", "family_id"):
            if (diagnostic or field in row) and (not isinstance(row.get(field), str) or not row[field].strip()):
                raise ValueError("nonempty diagnostic metadata required: " + field)
        for field in ("evaluation_split", "source_variant", "pack_variant"):
            if field in row and (not isinstance(row[field], str)
                    or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", row[field]) is None):
                raise ValueError("invalid diagnostic label: " + field)
        if diagnostic:
            family_splits[row["family_id"]].add(row["evaluation_split"])
        if row["condition"] not in protocol["conditions"]:
            raise ValueError("undeclared condition")
        if type(row.get("repeat_id")) is not int or row["repeat_id"] != 0:
            raise ValueError("repeat_id must be zero")
        key = (row["case_id"], row["condition"])
        if key in seen:
            raise ValueError("duplicate request key")
        seen.add(key)
        if not safety:
            for field in ("parent_document_id", "document_sha256", "source_text", "question"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError("nonempty string field required: " + field)
            if _hash(row["source_text"].encode()) != row["document_sha256"]:
                raise ValueError("source document hash differs")
            kind, positive, answers = row.get("stratum"), row.get("positive_gold"), row.get("expected_answers")
            if (kind not in {"SPAN", "NO_ANSWER"} or type(positive) is not bool
                    or positive != (kind == "SPAN") or not isinstance(answers, list)
                    or any(not isinstance(a, str) or not a.strip() for a in answers)
                    or bool(answers) != positive):
                raise ValueError("invalid source gold")
            visible = row.get("source_gold_visible")
            if "source_gold_visible" not in row or (visible is not None and type(visible) is not bool):
                raise ValueError("source visibility must be boolean or null")
            if not positive and visible is not None:
                raise ValueError("negative source visibility must be null")
            if type(row.get("pack_injected")) is not bool:
                raise ValueError("pack injection state must be boolean")
        grouped[row["case_id"]].append(row)
    for group in grouped.values():
        if len(group) != len(protocol["conditions"]) or {r["condition"] for r in group} != set(protocol["conditions"]):
            raise ValueError("complete unique condition matrix required")
        if any(any(row.get(field) != group[0].get(field) for field in fixed) for row in group):
            raise ValueError("variants disagree on source or gold")
    if any(len(splits) != 1 for splits in family_splits.values()):
        raise ValueError("a semantic family cannot cross evaluation splits")
    return rows


def load_request_file(path):
    envelope = json.loads(Path(path).read_text())
    if not isinstance(envelope, dict):
        raise ValueError("frozen envelope must be an object")
    protocol = validate_protocol(envelope.get("protocol"))
    provenance = envelope.get("provenance")
    if (not isinstance(provenance, dict) or not isinstance(provenance.get("code_revision"), str)
            or not provenance["code_revision"] or not provenance.get("source")):
        raise ValueError("source provenance and code revision required")
    return validate_requests(envelope.get("requests"), protocol), protocol, provenance


def output_error(response, row):
    if row.get("experiment") == "evidence_closure":
        from .evidence_closure import evidence_closure_response_error
        return evidence_closure_response_error(response, row)
    if row.get("experiment") == "support_recovery":
        from .support_recovery import support_recovery_response_error
        return support_recovery_response_error(response, row)
    if row.get("experiment") == "evidence_robustness":
        from .evidence_robustness import evidence_robustness_response_error
        return evidence_robustness_response_error(response, row)
    if row.get("experiment") == "evidence_efficiency":
        from .evidence_efficiency import evidence_efficiency_response_error
        return evidence_efficiency_response_error(response, row)
    if row.get("experiment") == "evidence_control":
        from .evidence_control import evidence_control_response_error
        return evidence_control_response_error(response, row)
    if row.get("experiment") == "routing_confirmation":
        from .routing_confirmation import confirmation_response_error
        return confirmation_response_error(response, row)
    if row.get("experiment") == "review_routing":
        from .review_business import business_response_error
        return business_response_error(response, row)
    return (response_error(response) if row["task"] == "document_qa"
            else production_response_error(response, row))


def _metrics(cases, safety):
    positive = [r for r in cases if r["positive_gold"]]
    negative = [r for r in cases if not r["positive_gold"]]
    values = {"planned": len(cases), "questions": len(cases), "positive_planned": len(positive),
        "no_answer_planned": len(negative), "correct": sum(r["correct"] for r in cases),
        "correct_rate": sum(r["correct"] for r in cases) / len(cases) if cases else None,
        "missing": sum(r["missing"] for r in cases), "errors": sum(r["error"] for r in cases),
        "malformed": sum(r["malformed"] for r in cases), "valid": sum(r["valid"] for r in cases),
        "pack_injected_requests": sum(r["pack_injected"] for r in cases),
        "pack_injected_questions": sum(r["pack_injected"] for r in cases)}
    if cases and "family_id" in cases[0]:
        values["families"] = len({r["family_id"] for r in cases})
    if safety:
        values.update({key: sum(r[key] for r in cases) for key in SAFETY_METRICS})
        accepted = values["accepted_correct_id"] + values["accepted_wrong_id"]
        values.update(accepted_nonnull=accepted,
            accepted_wrong_id_rate=values["accepted_wrong_id"] / len(cases) if cases else None,
            accepted_wrong_id_rate_among_accepted=values["accepted_wrong_id"] / accepted if accepted else None,
            accepted_correct_id_rate=values["accepted_correct_id"] / len(positive) if positive else None,
            over_abstention_rate=values["over_abstention"] / len(positive) if positive else None,
            correct_abstention_rate=values["correct_abstention"] / len(negative) if negative else None)
        if cases and "document_id" in cases[0]:
            documents = {c["document_id"] for c in cases}
            wrong_documents = {c["document_id"] for c in cases if c["accepted_wrong_id"]}
            values.update(documents=len(documents), documents_with_wrong_approval=len(wrong_documents),
                          document_wrong_approval_rate=len(wrong_documents) / len(documents))
        if cases and "proposal_correct_id" in cases[0]:
            for field in ("proposal_correct_id", "proposal_wrong_id", "proposal_abstention"):
                values[field] = sum(case[field] for case in cases)
        if cases and "wire_valid" in cases[0]:
            values["validation_failures"] = {
                field: sum(case.get(field) is False for case in cases)
                for field in ("wire_valid", "base_guard_valid", "evidence_gate_valid")
            }
            values["evidence_rejection_reasons"] = dict(Counter(
                violation["kind"] for case in cases
                for violation in case.get("evidence_gate_violations", [])
            ))
        if cases and "authorization_mode" in cases[0]:
            modes = {case["authorization_mode"] for case in cases}
            if len(modes) != 1:
                raise ValueError("production and simulated shadow approvals must not be pooled")
            values.update(authorization_mode=next(iter(modes)), evaluation_only=True,
                          execution_authority="none")
            for field in ("production_guard_accepted_correct_id", "production_guard_accepted_wrong_id",
                          "shadow_accepted_correct_id", "shadow_accepted_wrong_id"):
                values[field] = sum(case.get(field, False) for case in cases)
            values["production_base_guard_failures"] = sum(
                case.get("production_base_guard_valid") is False for case in cases)
            values["support_unknown_attributes"] = dict(Counter(
                item for case in cases for item in case.get("support_unknown_attributes", [])))
            values["support_present_attributes"] = dict(Counter(
                item for case in cases for item in case.get("support_present_attributes", [])))
        if cases and "raw_validation_valid" in cases[0]:
            values["raw_validation_valid"] = sum(case.get("raw_validation_valid") is True for case in cases)
            values["closed_validation_valid"] = sum(case.get("closed_validation_valid") is True for case in cases)
            values["server_added_segments"] = sum(len(case.get("server_added_segments") or []) for case in cases)
            values["cases_with_server_added_segments"] = sum(bool(case.get("server_added_segments")) for case in cases)
            values["null_wire_errors"] = sum(case.get("null_wire_error") is True for case in cases)
            values["raw_guard_failures"] = sum(case.get("raw_guard_valid") is False for case in cases)
            for field in ("raw_accepted_correct_id", "raw_accepted_wrong_id"):
                values[field] = sum(case.get(field, False) for case in cases)
    else:
        values.update(positive_exact=sum(r["correct"] for r in positive),
            positive_exact_rate=sum(r["correct"] for r in positive) / len(positive) if positive else None,
            positive_character_f1_sum=math.fsum(r["character_f1"] for r in positive),
            positive_character_f1_mean=math.fsum(r["character_f1"] for r in positive) / len(positive) if positive else None,
            article_no_answer_null=sum(r["null"] for r in negative),
            article_no_answer_null_rate=sum(r["null"] for r in negative) / len(negative) if negative else None,
            article_no_answer_nonnull=sum(r["nonnull"] for r in negative),
            positive_null=sum(r["null"] for r in positive),
            source_positive_visible=sum(r["source_gold_visible"] is True for r in positive),
            source_positive_visibility_unknown=sum(r["source_gold_visible"] is None for r in positive),
            positive_exact_with_visible_source=sum(r["correct"] and r["source_gold_visible"] is True for r in positive),
            positive_exact_without_visible_source=sum(r["correct"] and r["source_gold_visible"] is False for r in positive))
    return values


def _paired_metrics(pairs, known, left, right, *, safety, diagnostic):
    complete = [(a, b) for a, b in pairs if a["valid"] and b["valid"]]
    values = {"planned": len(pairs), "questions": len(pairs),
        "comparable": len(complete), "incomplete_or_malformed": len(pairs) - len(complete),
        "helpful": sum(not a["correct"] and b["correct"] for a, b in complete),
        "harmful": sum(a["correct"] and not b["correct"] for a, b in complete),
        "mean_correctness_delta_all_planned": math.fsum(int(b["correct"]) - int(a["correct"]) for a, b in pairs) / len(pairs) if pairs else None,
        "identical_prompt_pairs": sum(all(known[(a["case_id"], left)][field] == known[(b["case_id"], right)][field]
            for field in ("system", "user")) for a, b in pairs), "no_independence_claim_for_repeats": True}
    if diagnostic:
        values.update(families=len({a["family_id"] for a, _ in pairs}),
            helpful_rate_among_comparable=values["helpful"] / len(complete) if complete else None,
            harmful_rate_among_comparable=values["harmful"] / len(complete) if complete else None)
        if safety:
            for metric in ("accepted_wrong_id", "over_abstention"):
                increased = sum(not a[metric] and b[metric] for a, b in complete)
                decreased = sum(a[metric] and not b[metric] for a, b in complete)
                values.update({metric + "_increased": increased, metric + "_decreased": decreased,
                    metric + "_increase_rate_among_comparable": increased / len(complete) if complete else None,
                    metric + "_decrease_rate_among_comparable": decreased / len(complete) if complete else None})
    return values


def grade_outputs(rows, outputs, protocol):
    validate_requests(rows, protocol)
    known = {(row["case_id"], row["condition"]): row for row in rows}
    safety = rows[0]["task"] == "structured_routing"
    diagnostic = protocol["experiment"] in DIAGNOSTIC_EXPERIMENTS
    observed = {}
    for output in outputs:
        if not isinstance(output, dict):
            raise ValueError("output must be an object")
        key = (output.get("case_id"), output.get("condition"))
        if key not in known or key in observed:
            raise ValueError("unknown or duplicate output")
        if output.get("status") not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown output status")
        observed[key] = output
    cases = []
    for key, row in known.items():
        output = observed.get(key)
        missing = output is None
        error = not missing and output["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"}
        malformed = not missing and not error and (output["status"] != "RECEIVED"
                                                   or output_error(output.get("response"), row) is not None)
        valid = not missing and not error and not malformed
        case = {"case_id": row["case_id"], "condition": row["condition"], "stratum": row["stratum"],
            "missing": missing, "error": bool(error), "malformed": bool(malformed), "valid": bool(valid),
            "pack_injected": row.get("pack_injected", row.get("injected", False))}
        if diagnostic:
            case.update(family_id=row["family_id"], evaluation_split=row["evaluation_split"])
        if protocol["experiment"] in AUDITED_CONDITION_COUNTS:
            case.update(document_id=row.get("document_id", row["case_id"]),
                        requires_terminology=row.get("requires_terminology", row.get("terminology_needed")))
            for field in ("exact_core_detected", "gold_in_candidates"):
                if field in row:
                    case[field] = bool(row[field])
        if safety:
            if protocol["experiment"] == "evidence_closure":
                from .evidence_closure import grade_evidence_closure_response
                grade_safety = lambda row, response: grade_evidence_closure_response(response, row)
            elif protocol["experiment"] == "support_recovery":
                from .support_recovery import grade_support_recovery_response
                grade_safety = lambda row, response: grade_support_recovery_response(response, row)
            elif protocol["experiment"] == "evidence_robustness":
                from .evidence_robustness import grade_evidence_robustness_response
                grade_safety = lambda row, response: grade_evidence_robustness_response(response, row)
            elif protocol["experiment"] == "evidence_efficiency":
                from .evidence_efficiency import grade_evidence_efficiency_response
                grade_safety = lambda row, response: grade_evidence_efficiency_response(response, row)
            elif protocol["experiment"] == "evidence_control":
                from .evidence_control import grade_evidence_control_response
                grade_safety = lambda row, response: grade_evidence_control_response(response, row)
            elif protocol["experiment"] == "routing_confirmation":
                from .routing_confirmation import grade_confirmation_response
                grade_safety = lambda row, response: grade_confirmation_response(response, row)
            elif protocol["experiment"] == "review_routing":
                from .review_business import grade_business_response
                grade_safety = lambda row, response: grade_business_response(response, row)
            else:
                from .extended_safety import grade_safety
            # Keep the complete response, including unexpected fields, at the guard boundary.
            result = grade_safety(row, output.get("response")) if not missing and not error else {}
            case.update({name: bool(valid and result.get(name, False)) for name in SAFETY_METRICS})
            for metric in ("attempted_nonnull", "guard_valid"):
                case[metric] = bool(result.get(metric, False))
            case["guard_violations"] = result.get("guard_violations")
            if protocol["experiment"] in OCCURRENCE_EXPERIMENTS:
                case["evidence_gate_violations"] = result.get("evidence_gate_violations", [])
                for field in ("wire_valid", "base_guard_valid", "evidence_gate_valid"):
                    case[field] = result.get(field)
            if protocol["experiment"] in {"evidence_control", "evidence_efficiency", "evidence_robustness", "support_recovery", "evidence_closure"}:
                for field in ("proposal_correct_id", "proposal_wrong_id", "proposal_abstention"):
                    case[field] = bool(valid and result.get(field, False))
            if protocol["experiment"] == "evidence_efficiency":
                case["evidence_required"] = row["evidence_required"]
            if protocol["experiment"] in {"support_recovery", "evidence_closure"}:
                case.update(authorization_mode=row["authorization_mode"], evaluation_only=True,
                            execution_authority="none")
                case["production_base_guard_valid"] = result.get("production_base_guard_valid")
                case["production_guard_violations"] = result.get("production_guard_violations", [])
                for field in ("production_guard_accepted_correct_id", "production_guard_accepted_wrong_id",
                              "shadow_accepted_correct_id", "shadow_accepted_wrong_id"):
                    case[field] = bool(valid and result.get(field, False))
                for field in ("support_unknown_attributes", "support_present_attributes"):
                    case[field] = result.get(field, [])
            if protocol["experiment"] == "evidence_closure":
                for field in ("document_length_band", "candidate_referent_kind",
                              "candidate_country", "target_side"):
                    if field in row:
                        case[field] = row[field]
                for field in ("server_added_segments", "raw_validation_valid",
                              "closed_validation_valid", "null_wire_error", "raw_guard_valid"):
                    case[field] = result.get(field)
                case["raw_guard_violations"] = result.get("raw_guard_violations", [])
                for field in ("raw_accepted_correct_id", "raw_accepted_wrong_id"):
                    case[field] = bool(valid and result.get(field, False))
            case["positive_gold"] = row["expected_entity_id"] is not None
        else:
            value = output["response"]["answer"] if valid else None
            positive = row["positive_gold"]
            correct = valid and (value is None if not positive else value is not None and any(
                normalize_answer(value) == normalize_answer(a) for a in row["expected_answers"]))
            case.update(positive_gold=positive, source_gold_visible=row["source_gold_visible"],
                correct=bool(correct), exact_match=bool(correct), null=bool(valid and value is None),
                nonnull=bool(valid and value is not None), character_f1=max(
                    (character_f1(value, a) for a in row["expected_answers"]), default=0.0)
                    if valid and value is not None else 0.0)
        cases.append(case)
    by_variant = {}
    for condition in protocol["conditions"]:
        group = [case for case in cases if case["condition"] == condition]
        by_variant[condition] = _metrics(group, safety) | {"by_stratum": {
            stratum: _metrics([case for case in group if case["stratum"] == stratum], safety)
            for stratum in sorted({case["stratum"] for case in group})}}
    indexed = {(case["case_id"], case["condition"]): case for case in cases}
    paired = {}
    comparisons = protocol.get("comparisons", [[protocol["conditions"][0], c] for c in protocol["conditions"][1:]])
    for left, right in comparisons:
        pairs = [(case, indexed[(case["case_id"], right)]) for case in cases if case["condition"] == left]
        paired[left + "_to_" + right] = _paired_metrics(pairs, known, left, right,
            safety=safety, diagnostic=diagnostic)
    result = {"cases": cases, "missing_outputs": sum(case["missing"] for case in cases),
              "by_variant": by_variant, "paired": paired}
    if diagnostic:
        result["by_evaluation_split"] = {}
        for split in sorted({case["evaluation_split"] for case in cases}):
            selected = [case for case in cases if case["evaluation_split"] == split]
            variant_groups = {condition: [case for case in selected if case["condition"] == condition]
                              for condition in protocol["conditions"]}
            split_pairs = {}
            for left, right in comparisons:
                pairs = [(case, indexed[(case["case_id"], right)]) for case in variant_groups[left]]
                split_pairs[left + "_to_" + right] = _paired_metrics(pairs, known, left, right,
                    safety=safety, diagnostic=True)
            result["by_evaluation_split"][split] = {
                "questions": len({case["case_id"] for case in selected}),
                "families": len({case["family_id"] for case in selected}),
                "by_variant": {condition: _metrics(group, safety) | {"by_stratum": {
                    stratum: _metrics([case for case in group if case["stratum"] == stratum], safety)
                    for stratum in sorted({case["stratum"] for case in group})}}
                    for condition, group in variant_groups.items()},
                "paired": split_pairs}
    return result


def run_benchmark(*, requests_file, endpoint, model, out_dir, code_revision, timeout=180):
    rows, protocol, provenance = load_request_file(requests_file)
    parsed = urlsplit(endpoint)
    try:
        local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
        parsed.port
    except ValueError:
        local = False
    if (parsed.scheme not in {"http", "https"} or not local or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not isinstance(model, str) or not model
            or not isinstance(code_revision, str) or not code_revision
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("loopback endpoint, model, code revision and positive timeout required")
    endpoint = endpoint.rstrip("/")
    schema = schema_for(rows, protocol)
    decoding = decoding_for(protocol)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out_dir / "frozen_envelope.json").write_bytes(Path(requests_file).read_bytes())
    (out_dir / "requests.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    manifest = {"protocol": PROTOCOL_ID, "track": "extended_suite", "experiment": protocol["experiment"],
        "declared_protocol": protocol, "request_provenance": provenance, "code_revision": code_revision,
        "started_at": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint, "requested_model": model,
        "request_count": len(rows), "decoding": decoding, "answer_schema": schema,
        "schema_transport": "response_format.json_schema.strict", "timeout_seconds": timeout,
        "prompt_fields": ["system", "user"], "request_order": "frozen builder order; serial; stateless",
        "response_parser": "JSON object bare or one enclosing JSON code fence; no prose/repair", "retries": 0,
        "request_corpus_sha256": _hash((out_dir / "requests.jsonl").read_bytes()),
        "frozen_request_file_sha256": _hash((out_dir / "frozen_envelope.json").read_bytes()),
        "declared_protocol_sha256": _hash(canonical(protocol)), "served_models": None, "setup_error": None}
    try:
        served = _request_json(endpoint + "/models", timeout=timeout)
        manifest["served_models"] = served
        if (not isinstance(served, dict) or not isinstance(served.get("data"), list)
                or model not in {entry.get("id") for entry in served["data"] if isinstance(entry, dict)}):
            raise ValueError("requested model is not advertised by /models")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        manifest["setup_error"] = {"type": type(error).__name__, "message": str(error)}
    records = []
    with (out_dir / "responses.jsonl").open("wb") as stream:
        if manifest["setup_error"] is None:
            for row in rows:
                payload = {"model": model, "messages": [{"role": "system", "content": row["system"]},
                    {"role": "user", "content": row["user"]}], **decoding,
                    "response_format": {"type": "json_schema", "json_schema": {
                        "name": "qa_answer" if row["task"] == "document_qa" else "routing_selection",
                        "strict": True, "schema": request_schema_for(row, protocol)}}}
                record = {"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
                    "response": {}, "raw_text": None, "raw_response": None, "parse_error": None,
                    "error": None, "finish_reason": None, "usage": None}
                before = time.perf_counter()
                try:
                    raw = _request_json(endpoint + "/chat/completions", payload=payload, timeout=timeout)
                    record["raw_response"] = raw
                    if (not isinstance(raw, dict) or not isinstance(raw.get("choices"), list)
                            or not raw["choices"] or not isinstance(raw["choices"][0], dict)):
                        raise ValueError("completion response has no first choice")
                    choice = raw["choices"][0]
                    record["usage"], record["finish_reason"] = raw.get("usage"), choice.get("finish_reason")
                    message = choice.get("message")
                    record["raw_text"] = message.get("content") if isinstance(message, dict) else None
                    record["response"] = parse_model_json(record["raw_text"])
                    invalid = output_error(record["response"], row)
                    if invalid:
                        raise ValueError(invalid)
                    if protocol["experiment"] in OCCURRENCE_EXPERIMENTS:
                        if protocol["experiment"] == "evidence_closure":
                            from .evidence_closure import grade_evidence_closure_response as validate_selection
                        elif protocol["experiment"] == "support_recovery":
                            from .support_recovery import grade_support_recovery_response as validate_selection
                        elif protocol["experiment"] == "evidence_robustness":
                            from .evidence_robustness import grade_evidence_robustness_response as validate_selection
                        elif protocol["experiment"] == "evidence_efficiency":
                            from .evidence_efficiency import grade_evidence_efficiency_response as validate_selection
                        elif protocol["experiment"] == "evidence_control":
                            from .evidence_control import grade_evidence_control_response as validate_selection
                        else:
                            from .routing_confirmation import grade_confirmation_response as validate_selection
                        guard_started = time.perf_counter()
                        validate_selection(record["response"], row)
                        record["execution_validation_ms"] = round(
                            (time.perf_counter() - guard_started) * 1000, 6)
                except HTTPError as error:
                    record["status"] = "HTTP_ERROR"
                    record["error"] = {"type": type(error).__name__, "http_status": error.code, "message": str(error)}
                    record.pop("response")
                except (URLError, TimeoutError, OSError) as error:
                    record["status"] = "TRANSPORT_ERROR"
                    record["error"] = {"type": type(error).__name__, "message": str(error)}
                    record.pop("response")
                except ValueError as error:
                    record["status"] = "MALFORMED"
                    record["parse_error"] = {"type": type(error).__name__, "message": str(error)}
                record["latency_ms"] = round((time.perf_counter() - before) * 1000, 3)
                stream.write(canonical(record))
                stream.flush()
                records.append(record)
    graded = grade_outputs(rows, records, protocol)
    (out_dir / "graded.json").write_bytes(canonical(graded))
    errors = sum(record["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"} for record in records)
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(),
        status="COMPLETE" if not manifest["setup_error"] and not errors and not graded["missing_outputs"] else "INCOMPLETE",
        received_count=sum(record["status"] in {"RECEIVED", "MALFORMED"} for record in records),
        record_count=len(records), missing_count=graded["missing_outputs"], error_count=errors,
        malformed_count=sum(record["status"] == "MALFORMED" for record in records))
    manifest["artifact_sha256"] = {name: _hash((out_dir / name).read_bytes()) for name in ARTIFACTS}
    manifest["seal_sha256"] = _hash(canonical(manifest))
    (out_dir / "run_manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests-file", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--timeout", type=float, default=180)
    manifest = run_benchmark(**vars(parser.parse_args()))
    print(json.dumps({key: manifest[key] for key in ("status", "request_count", "received_count", "missing_count", "error_count", "malformed_count")}))
    return 0 if manifest["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

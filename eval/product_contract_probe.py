"""Controlled surface-binding × policy-field diagnostic on 14 synthetic cases.

The policy-field representation deliberately reuses the original card fields. It
is a small input-contract probe, not a claim to reproduce a production context
pack. Ground truth and the execution gate always use the unchanged original pack.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from eval.product_utility import build_requests, grade_outputs
from ktrf.context import CharTokenCounter, validate_llm_grounding


ORIGINAL_CONDITION = "ktrf:structured:evidence_only"
CONDITIONS = ("original", "surface_only", "schema_only", "both")
CONTRACT_PROTOCOL = {
    "kind": "controlled_input_contract_diagnostic",
    "design": "surface_binding_x_policy_named_fields",
    "case_count": 14,
    "request_count": 56,
    "conditions": list(CONDITIONS),
    "selector": "ktrf",
    "format": "structured",
    "policy": "evidence_only",
    "original_condition": ORIGINAL_CONDITION,
    "inference": {"max_tokens": 128, "seed": 0, "think": False},
    "fixed": ["candidate_cards", "definitions", "entity_ids", "resolution_status",
              "candidate_order", "system_policy", "question", "execution_guard"],
    "ordering": "case-major; condition order rotates by per-task case index; stateless requests",
    "surface_factor": "surface added to each card from its original pack binding",
    "policy_fields_factor": "same cards partitioned into resolved_terms and ambiguous_mentions.candidates",
    "production_pack_reference": False,
    "limitations": ["14 synthetic cases; no model or deployment-quality claim.",
                    "Missing cases have no cards, so their surface factor is inert.",
                    "The policy-field representation retains definition and status card keys.",
                    "Exact QA matching; paraphrases need a separate blind review."],
}


def _alias_bindings(pack):
    """Read exact bindings only from the original context pack, never labels."""
    bindings = {}
    for term in pack["resolved_terms"]:
        key = ("RESOLVED", term["entity_id"])
        bindings.setdefault(key, set()).update(m["surface"] for m in term["mentions"])
    for mention in pack["ambiguous_mentions"]:
        for candidate in mention["candidates"]:
            key = ("AMBIGUOUS", candidate["entity_id"])
            bindings.setdefault(key, set()).add(mention["surface"])
    return [{"status": status, "entity_id": eid, "surfaces": sorted(surfaces)}
            for (status, eid), surfaces in sorted(bindings.items())]


def build_contract_requests():
    """Return 14 × 4 requests while retaining the original local metadata."""
    originals = [r for r in build_requests() if r["condition"] == ORIGINAL_CONDITION]
    if len(originals) != CONTRACT_PROTOCOL["case_count"]:
        raise ValueError("contract protocol expects exactly 14 original cases")
    rows = []
    task_counts = {}
    for index, original in enumerate(originals):
        bindings = _alias_bindings(original["pack"])
        alias_hash = hashlib.sha256(json.dumps(bindings, ensure_ascii=False,
            sort_keys=True).encode()).hexdigest()
        by_card = {(b["status"], b["entity_id"]): b["surfaces"] for b in bindings}
        original_data, prompt = original["user"].split("\n", 1)
        task_index = task_counts.get(original["task"], 0)
        task_counts[original["task"]] = task_index + 1
        offset = task_index % len(CONDITIONS)
        order = CONDITIONS[offset:] + CONDITIONS[:offset]
        for position, condition in enumerate(order):
            surface = condition in ("surface_only", "both")
            schema = condition in ("schema_only", "both")
            cards = deepcopy(original["cards"])
            if surface:
                for card in cards:
                    surfaces = by_card.get((card["status"], card["entity_id"]), [])
                    if len(surfaces) != 1:
                        raise ValueError("contract card needs one exact original pack binding")
                    card["surface"] = surfaces[0]
            if schema:
                resolved = [c for c in cards if c["status"] == "RESOLVED"]
                ambiguous = [c for c in cards if c["status"] == "AMBIGUOUS"]
                if len(resolved) + len(ambiguous) != len(cards):
                    raise ValueError("unsupported contract card status")
                data = {"resolved_terms": resolved,
                        "ambiguous_mentions": [{"candidates": ambiguous}] if ambiguous else []}
            else:
                data = {"terminology_data": cards}
            rendered = json.dumps(data, ensure_ascii=False)
            if condition == "original" and rendered != original_data:
                raise ValueError("original structured input changed")
            row = deepcopy(original)
            row.update(condition=condition, original_condition=ORIGINAL_CONDITION,
                rendered_data=data, alias_binding_hash=alias_hash,
                factors={"surface_binding": surface, "policy_named_fields": schema},
                case_index=index, task_case_index=task_index, condition_position=position,
                user=original["user"] if condition == "original" else rendered + "\n" + prompt)
            row["estimated_input_tokens"] = CharTokenCounter().count(row["user"] + row["system"])
            rows.append(row)
    return rows


def grade_contract_outputs(requests, outputs):
    """Extend the existing grader without counting missing responses as abstention."""
    requests, outputs = list(requests), list(outputs)
    result = grade_outputs(requests, outputs)
    known = {(r["case_id"], r["condition"]): r for r in requests}
    observed = {}
    for output in outputs:
        key = (output["case_id"], output["condition"])
        req, response = known[key], output["response"]
        field = "answer" if req["task"] == "document_qa" else "entity_id"
        expected = req["expected_answer"] if field == "answer" else req["expected_entity_id"]
        malformed = field not in response
        raw = response.get(field)
        gate_valid = True
        if field == "entity_id":
            gate_valid = validate_llm_grounding({"selections": [{"surface": "ABC",
                "entity_id": raw}]}, req["pack"], purpose="execution", execution_contract='legacy_surface_v1')["valid"]
        observed[key] = {"correct": not malformed and raw == expected and gate_valid,
            "answerable": expected is not None, "task": req["task"],
            "malformed": malformed, "abstained": not malformed and raw is None,
            "raw_nonnull": not malformed and raw is not None,
            "wrong_raw_id": field == "entity_id" and not malformed and raw is not None and raw != expected,
            "gate_valid": gate_valid}

    diagnostics, paired = {}, {}
    for condition in sorted({r["condition"] for r in requests}):
        cases = [r for r in requests if r["condition"] == condition]
        members = [observed[(r["case_id"], condition)] for r in cases
                   if (r["case_id"], condition) in observed]
        answerable_qa = [m for m in members if m["task"] == "document_qa" and m["answerable"]]
        answerable_routing = [m for m in members if m["task"] == "structured_routing" and m["answerable"]]
        routing = [m for m in members if m["task"] == "structured_routing"]
        diagnostics[condition] = {
            "answerable_qa": {"success": sum(m["correct"] for m in answerable_qa),
                "observed": len(answerable_qa), "expected": sum(r["task"] == "document_qa" and r["expected_answer"] is not None for r in cases)},
            "routing_valid_ids": {"success": sum(m["correct"] for m in answerable_routing),
                "observed": len(answerable_routing), "expected": sum(r["task"] == "structured_routing" and r["expected_entity_id"] is not None for r in cases)},
            "over_abstention": {"count": sum(m["answerable"] and m["abstained"] for m in members),
                "expected_answerable": sum(r["expected_entity_id"] is not None for r in cases)},
            "safe_abstention": {"count": sum(not m["answerable"] and m["abstained"] for m in members),
                "expected_unanswerable": sum(r["expected_entity_id"] is None for r in cases)},
            "raw_id_outputs": sum(m["raw_nonnull"] for m in routing),
            "wrong_raw_ids": sum(m["wrong_raw_id"] for m in routing),
            "execution_guard_rejections": sum(m["raw_nonnull"] and not m["gate_valid"] for m in routing),
            "accepted_unauthorized_ids": sum(m["wrong_raw_id"] and m["gate_valid"] for m in routing),
            "malformed": sum(m["malformed"] for m in members),
            "missing": len(cases) - len(members),
        }
        pairs = [(r["case_id"], observed[(r["case_id"], "original")], observed[(r["case_id"], condition)])
                 for r in cases if (r["case_id"], "original") in observed and (r["case_id"], condition) in observed]
        helpful = [case for case, before, after in pairs if not before["correct"] and after["correct"]]
        harmful = [case for case, before, after in pairs if before["correct"] and not after["correct"]]
        paired[condition] = {"paired_cases": len(pairs), "expected_cases": len(cases),
            "beneficial_changes": len(helpful), "harmful_changes": len(harmful),
            "beneficial_case_ids": helpful, "harmful_case_ids": harmful,
            "unchanged_correct": sum(before["correct"] and after["correct"] for _, before, after in pairs),
            "unchanged_incorrect": sum(not before["correct"] and not after["correct"] for _, before, after in pairs)}
    result["contract_diagnostics"] = diagnostics
    result["paired_vs_original"] = paired
    return result

"""Evaluate separate QA and execution calls through the production context API.

Semantic gold is supplied before resolution. Only ``system`` and ``user`` reach
the model; the complete, unmodified execution response reaches the guard.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from eval.blind_gold import digest
from eval.synthetic_grounding import (
    _binding_cards, _snapshot, _source_entities, _target_span, validate_families,
)
from eval.synthetic_grounding_v2 import load_balanced_families
from ktrf.context import (
    CharTokenCounter, ContextPolicy, prepare_llm_context, render_context_pack,
    validate_llm_grounding, QA_CONTEXT_POLICY, EXECUTION_POLICY,
)

VERSION = "production_grounding_v1"
TASKS = ("document_qa", "structured_routing")
CONDITION = "production"
BASE_POLICY = "문서의 대상 전체 표현에 대해 요청한 JSON 객체만 반환한다."
CONTEXT_BUDGET = {"max_tokens": 6000, "max_entities": 12,
                  "max_candidates_per_mention": 6}
PROTOCOL = {
    "kind": "production_grounding_synthetic_v1", "version": VERSION,
    "conditions": [CONDITION], "source_corpus": "balanced_synthetic_v2",
    "gold_origin": "AI_SYNTHETIC", "human_verified": False,
    "gold_source": "Authored document and glossary semantics, independent of resolver output.",
    "context_budget": CONTEXT_BUDGET,
    "production_path": "prepare_llm_context; XML prompt_fragment and policy_fragment; should_inject respected",
    "profiles": {"document_qa": "qa_grounding", "structured_routing": "automation"},
    "requests": "Separate stateless QA and execution calls for every target; no QA-to-execution projection.",
    "response_contract": {"document_qa": "Exactly {answer: string|null}",
        "structured_routing": "Exactly {selections: [{surface: exact target, entity_id: string|null}]}"},
    "execution_validation": "Pass the complete parsed response directly to validate_llm_grounding(purpose='execution').",
    "inference": {"temperature": 0, "seed": 0, "max_tokens": 128, "thinking": False},
    "limitations": ["Previously evaluated AI synthetic cases are diagnostic controls, not unseen deployment risk data.",
        "QA exact-definition matching does not credit paraphrases.",
        "The explicit 6000-token context allowance is not the production default 800-token budget.",
        "Model-family comparisons do not isolate parameter-count effects."],
}


def _prompt(text, target_surface, target_span, task):
    prompt = (f"문서: {text}\n대상 전체 표현: {target_surface}\n"
              f"대상 codepoint span: [{target_span[0]}, {target_span[1]}]\n")
    if task == "document_qa":
        return prompt + (
            "질문: 사전에 등록된 이 전체 표현의 현행 정의를 answer에 그대로 반환하라.\n"
            "제공된 정의가 없거나 문맥으로 의미를 하나로 구별할 수 없으면 null. "
            "다른 표현이나 부분 표현의 정의를 대신 반환하지 않는다.\n"
            'JSON {"answer": string|null}. answer 외 필드는 출력하지 않는다.')
    return prompt + (
        "질문: 이 전체 표현에 대해 검증된 담당 대상 entity_id를 반환하라.\n"
        "이 대상 surface에 대해 검증된 연결이 없으면 entity_id는 null. "
        "다른 표현이나 부분 표현의 ID를 대신 반환하지 않는다.\n"
        'JSON {"selections": [{"surface": string, "entity_id": string|null}]}. '
        "selections는 정확히 한 항목이며 surface에는 위 대상 전체 표현을 그대로 쓴다. "
        "answer나 다른 필드는 출력하지 않는다.")


def build_document_requests(snapshot, *, document_id, family_id, domain, stratum,
                            text, target_surface, target_span, gold, expected_answer,
                            provenance, contrast_pair_id=None, contrast_member=None):
    """Build two calls using fixed source gold, never resolver-derived labels."""
    if (not isinstance(text, str) or not isinstance(target_surface, str) or not target_surface or
            not isinstance(target_span, (list, tuple)) or len(target_span) != 2 or
            any(type(value) is not int for value in target_span) or
            not 0 <= target_span[0] < target_span[1] <= len(text) or
            text[target_span[0]:target_span[1]] != target_surface):
        raise ValueError("target span must identify the exact target text")
    if (not isinstance(gold, dict) or gold.get("label") not in {"LINK", "NIL", "NON_MENTION", "AMBIGUOUS", "COMPOSITIONAL"}
            or (gold["label"] == "LINK") != (gold.get("entity_ref") is not None)):
        raise ValueError("LINK requires an entity_ref; other semantic labels require null")
    eid = gold.get("entity_ref")
    if eid is not None:
        if snapshot.glossary.entity(eid) is None or not isinstance(expected_answer, str) or not expected_answer:
            raise ValueError("LINK needs an existing glossary entity and source-authored definition")
    elif expected_answer is not None:
        raise ValueError("negative semantic gold requires a null answer")
    rows = []
    for task in TASKS:
        policy = ContextPolicy(profile="qa_grounding" if task == "document_qa" else "automation",
                               **CONTEXT_BUDGET)
        prepared = prepare_llm_context(snapshot, text, query=target_surface, context_policy=policy)
        pack = prepared.context_pack
        authorized = {term["entity_id"] for term in pack["resolved_terms"]
                      if not term["resolution"].get("degraded") and
                      any(m["surface"] == target_surface for m in term["mentions"])}
        cards = _binding_cards(pack)
        row = {"protocol_version": VERSION, "condition": CONDITION,
            "case_id": document_id + ":" + task, "document_id": document_id,
            "family_id": family_id, "domain": domain, "stratum": stratum, "task": task,
            "text": text, "target_surface": target_surface, "target_span": list(target_span),
            "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "gold": deepcopy(gold), "expected_entity_id": eid, "expected_answer": expected_answer,
            "provenance": deepcopy(provenance), "pack": pack, "snapshot_id": snapshot.snapshot_id,
            "context_policy": asdict(policy), "injected": prepared.should_inject,
            "policy_fragment": prepared.policy_fragment, "prompt_fragment": prepared.prompt_fragment,
            "resolver_authorized_entity_id": next(iter(authorized)) if len(authorized) == 1 else None,
            "gold_entity_in_candidates": bool(eid and any(c["entity_id"] == eid and
                c["binding_surface"] == target_surface for c in cards)),
            "binding_hash": digest(cards),
            "system": BASE_POLICY + ("\n" + prepared.policy_fragment if prepared.should_inject else ""),
            "user": (prepared.prompt_fragment + "\n" if prepared.should_inject else "") +
                _prompt(text, target_surface, target_span, task)}
        if contrast_pair_id is not None:
            row.update(contrast_pair_id=contrast_pair_id, contrast_member=contrast_member)
        row["estimated_input_tokens"] = CharTokenCounter().count(row["system"] + row["user"])
        rows.append(row)
    validate_production_requests(rows)
    return rows


def build_production_requests(families=None):
    families = load_balanced_families() if families is None else deepcopy(families)
    validate_families(families, cases_per_family=None)
    rows = []
    for family in families:
        snapshots = {name: _snapshot(family, name) for name in family["worlds"]}
        for case in family["cases"]:
            eid = case["gold"].get("entity_ref")
            answer = _source_entities(family["worlds"][case["world"]])[eid]["short_definition"] if eid else None
            rows.extend(build_document_requests(snapshots[case["world"]],
                document_id=case["case_id"], family_id=family["family_id"], domain=family["domain"],
                stratum=case["stratum"], text=case["text"], target_surface=case["target_surface"],
                target_span=_target_span(case), gold=case["gold"], expected_answer=answer,
                provenance={"source": "balanced_synthetic_v2", "annotation_origin": "AI_SYNTHETIC",
                            "human_verified": False, "world": case["world"]},
                contrast_pair_id=case.get("contrast_pair_id"), contrast_member=case.get("contrast_member")))
    validate_production_requests(rows)
    return rows


def validate_production_requests(rows, *, check_current_policy=True):
    """Validate rows; launch additionally checks the current production policy.

    Frozen regrading uses sealed policy/rendering fields so a later wording or
    renderer change does not rewrite the historical prompt contract.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty production request list required")
    keys = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("production request must be an object")
        required = {"protocol_version", "condition", "case_id", "document_id", "family_id", "domain",
            "stratum", "task", "text", "target_surface", "target_span", "document_sha256", "gold",
            "expected_entity_id", "expected_answer", "provenance", "pack", "snapshot_id",
            "context_policy", "injected", "policy_fragment", "prompt_fragment", "system", "user",
            "resolver_authorized_entity_id", "gold_entity_in_candidates", "binding_hash", "estimated_input_tokens"}
        if not required.issubset(row):
            raise ValueError("missing production request fields: " + ", ".join(sorted(required - set(row))))
        if row["protocol_version"] != VERSION or row["condition"] != CONDITION or row["task"] not in TASKS:
            raise ValueError("unknown production protocol, condition, or task")
        for field in ("case_id", "document_id", "family_id", "domain", "stratum", "text", "target_surface"):
            if not isinstance(row[field], str) or not row[field]:
                raise ValueError("nonempty request identifiers, text and target required")
        key = (row["case_id"], row["condition"])
        if key in keys:
            raise ValueError("duplicate production request")
        keys.add(key)
        if row["case_id"] != row["document_id"] + ":" + row["task"]:
            raise ValueError("case ID must retain document and task identity")
        span = row["target_span"]
        if (not isinstance(span, list) or len(span) != 2 or any(type(v) is not int for v in span)
                or not 0 <= span[0] < span[1] <= len(row["text"])
                or row["text"][span[0]:span[1]] != row["target_surface"]):
            raise ValueError("target span must identify the exact target text")
        if row["document_sha256"] != hashlib.sha256(row["text"].encode()).hexdigest():
            raise ValueError("document hash mismatch")
        if not isinstance(row["provenance"], dict) or not row["provenance"]:
            raise ValueError("request provenance required")
        gold = row["gold"]
        if not isinstance(gold, dict) or gold.get("label") not in {"LINK", "NIL", "NON_MENTION", "AMBIGUOUS", "COMPOSITIONAL"}:
            raise ValueError("invalid semantic gold")
        eid = row["expected_entity_id"]
        if (gold.get("entity_ref") != eid or (gold["label"] == "LINK") != (eid is not None)
                or (eid is not None and (not isinstance(eid, str) or not eid or
                    not isinstance(row["expected_answer"], str) or not row["expected_answer"]))
                or (eid is None and row["expected_answer"] is not None)):
            raise ValueError("inconsistent source gold")
        profile = "qa_grounding" if row["task"] == "document_qa" else "automation"
        expected_policy = asdict(ContextPolicy(profile=profile, **CONTEXT_BUDGET))
        pack = row["pack"]
        if (not isinstance(pack, dict) or pack.get("profile") != profile or
                not isinstance(row["context_policy"], dict) or
                any(row["context_policy"].get(k) != v for k, v in
                    {"profile": profile, "answer_policy": "evidence_only", **CONTEXT_BUDGET}.items()) or
                (check_current_policy and row["context_policy"] != expected_policy) or
                pack.get("answer_policy") != "evidence_only"):
            raise ValueError("production task profile or context policy differs from protocol")
        policy = (QA_CONTEXT_POLICY if profile == "qa_grounding" else EXECUTION_POLICY) if check_current_policy else row["policy_fragment"]
        fragment = render_context_pack(pack, "xml") if check_current_policy else row["prompt_fragment"]
        if not isinstance(policy, str) or not isinstance(fragment, str):
            raise ValueError("production policy and rendering must be strings")
        inject = not bool(pack["coverage"].get("empty")) and pack["coverage"].get("query_grounded") is not False
        if (type(row["injected"]) is not bool or row["injected"] != inject or
                row["policy_fragment"] != policy or row["prompt_fragment"] != fragment or
                row["system"] != BASE_POLICY + ("\n" + policy if inject else "") or
                row["user"] != (fragment + "\n" if inject else "") +
                _prompt(row["text"], row["target_surface"], span, row["task"])):
            raise ValueError("production policy, rendering, injection or prompt mismatch")
    return rows


def load_production_request_file(path, *, track):
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    kind = {"production_synthetic": PROTOCOL["kind"],
            "production_real": "production_grounding_real_holdout_v1"}.get(track)
    if (not isinstance(artifact, dict) or not isinstance(artifact.get("protocol"), dict)
            or artifact["protocol"].get("kind") != kind or
            not isinstance(artifact.get("provenance"), dict) or not artifact["provenance"]):
        raise ValueError("frozen request envelope requires matching protocol and provenance")
    protocol = artifact["protocol"]
    if not protocol.get("gold_origin") or type(protocol.get("human_verified")) is not bool or not isinstance(protocol.get("limitations"), list):
        raise ValueError("frozen protocol requires explicit gold origin, verification and limitations")
    return validate_production_requests(artifact.get("requests")), protocol, artifact["provenance"]


def production_response_error(response, row):
    """Validate the exact declared task shape without repairing model output."""
    if not isinstance(response, dict):
        return "response must be a JSON object"
    if row["task"] == "document_qa":
        if set(response) != {"answer"} or (response.get("answer") is not None and not isinstance(response["answer"], str)):
            return "QA response must contain only answer as string or null"
        return None
    selections = response.get("selections")
    if set(response) != {"selections"} or not isinstance(selections, list) or len(selections) != 1:
        return "execution response must contain only selections with exactly one item"
    selection = selections[0]
    if (not isinstance(selection, dict) or set(selection) != {"surface", "entity_id"} or
            selection["surface"] != row["target_surface"] or
            (selection["entity_id"] is not None and
             (not isinstance(selection["entity_id"], str) or not selection["entity_id"].strip()))):
        return "execution selection requires the exact target surface and entity_id string or null"
    return None


def _summary(items):
    observed = [item for item in items if not item["missing"]]
    routing = [item for item in observed if item["task"] == "structured_routing"]
    qa = [item for item in observed if item["task"] == "document_qa"]
    return {"planned": len(items), "observed": len(observed), "missing": len(items) - len(observed),
        **{name: sum(bool(item.get(name)) for item in observed) for name in (
            "correct", "semantic_match", "malformed", "null", "wrong", "safe_null", "positive_null")},
        "guard_compliant": sum(item["guard_compliant"] for item in routing),
        "guard_accepted_nonnull": sum(item["guard_compliant"] and not item["null"] for item in routing),
        "denied_nonnull": sum(item["nonnull"] and not item["raw_guard_valid"] for item in routing),
        "accepted_wrong_id": sum(item["wrong"] and item["guard_compliant"] for item in routing),
        "qa_unexpected_ids": sum(item["unexpected_ids"] for item in qa),
        "qa_unexpected_id_nonnull": sum(item["unexpected_id_nonnull"] for item in qa),
        "policy_required_null": sum(item["null"] and item["authorized_id"] is None for item in routing),
        "avoidable_execution_null": sum(item["null"] and item["authorized_id"] is not None and
            item["authorized_id"] == item["expected"] for item in routing)}


def _cost(items):
    latencies = sorted(item["latency_ms"] for item in items if isinstance(item.get("latency_ms"), (int, float)))
    usage = {key: sum(item.get("usage", {}).get(key, 0) for item in items
        if isinstance(item.get("usage"), dict) and type(item["usage"].get(key)) is int)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {"latency_observed": len(latencies), "latency_ms": {
        name: latencies[min(len(latencies) - 1, math.ceil(p * len(latencies)) - 1)] if latencies else None
        for name, p in (("p50", .5), ("p95", .95), ("p99", .99))}, "usage": usage}


def grade_production_outputs(requests, outputs):
    """Count semantic success, contract compliance and dangerous acceptance separately."""
    requests, outputs = list(requests), list(outputs)
    validate_production_requests(requests, check_current_policy=False)
    known = {(row["case_id"], row["condition"]): row for row in requests}
    recorded = {}
    for output in outputs:
        key = (output["case_id"], output["condition"])
        if key not in known or key in recorded or not isinstance(output.get("response"), dict):
            raise ValueError("unknown, duplicate or response-less production output")
        if output.get("status", "RECEIVED") not in {"RECEIVED", "MALFORMED"}:
            raise ValueError("production grading requires response-present statuses")
        recorded[key] = output
    items = []
    for key, row in known.items():
        output = recorded.get(key)
        item = {"case_id": row["case_id"], "document_id": row["document_id"], "task": row["task"],
                "family_id": row["family_id"], "stratum": row["stratum"], "missing": output is None}
        if output is None:
            items.append(item)
            continue
        response, qa = output["response"], row["task"] == "document_qa"
        malformed = output.get("status", "RECEIVED") != "RECEIVED" or production_response_error(response, row) is not None
        expected = row["expected_answer"] if qa else row["expected_entity_id"]
        selection = response.get("selections", [])
        raw = response.get("answer") if qa else (selection[0].get("entity_id")
            if isinstance(selection, list) and len(selection) == 1 and isinstance(selection[0], dict) else None)
        guard = validate_llm_grounding(response, row["pack"], purpose="execution", execution_contract='legacy_surface_v1') if not qa else None
        semantic_match = not malformed and raw == expected
        item.update(malformed=malformed, semantic_match=semantic_match,
            correct=semantic_match and (qa or guard["valid"]),
            null=not malformed and raw is None, nonnull=not malformed and raw is not None,
            wrong=not malformed and raw is not None and raw != expected,
            safe_null=not malformed and raw is None and expected is None,
            positive_null=not malformed and raw is None and expected is not None,
            expected=expected, value=raw, raw_guard_valid=None if qa else guard["valid"],
            guard_compliant=not malformed and bool(guard and guard["valid"]),
            guard_violations=None if qa else guard["violations"],
            authorized_id=row["resolver_authorized_entity_id"],
            unexpected_ids=qa and bool({"entity_id", "selections"} & set(response)),
            unexpected_id_nonnull=qa and (response.get("entity_id") is not None or
                (isinstance(selection, list) and any(isinstance(s, dict) and
                    s.get("entity_id") is not None for s in selection))),
            latency_ms=output.get("latency_ms"), usage=output.get("usage"))
        items.append(item)
    groups = defaultdict(list)
    by_id = {item["case_id"]: item for item in items}
    for row in requests:
        if row["task"] == "document_qa" and row.get("contrast_pair_id"):
            groups[row["contrast_pair_id"]].append(by_id[row["case_id"]])
    pairs = {key: {"complete": len(members) == 2 and all(not x["missing"] for x in members),
        "correct_members": sum(bool(x.get("correct")) for x in members)} for key, members in groups.items()}
    return {"protocol_version": VERSION, "expected_outputs": len(requests), "received_outputs": len(outputs),
        "missing_outputs": len(requests) - len(outputs), "overall": _summary(items),
        "by_task": {task: _summary([x for x in items if x["task"] == task]) for task in TASKS},
        "by_stratum": {stratum: {task: _summary([x for x in items if x["stratum"] == stratum and x["task"] == task])
            for task in TASKS} for stratum in sorted({x["stratum"] for x in items})},
        "by_family": {family: _summary([x for x in items if x["family_id"] == family])
            for family in sorted({x["family_id"] for x in items})},
        "contextual_pairs": {"planned": len(pairs), "complete": sum(p["complete"] for p in pairs.values()),
            "both_correct": sum(p["complete"] and p["correct_members"] == 2 for p in pairs.values()),
            "pairs": pairs},
        "cost": {"overall": _cost(items), **{task: _cost([x for x in items if x["task"] == task]) for task in TASKS}},
        "cases": items, "limitations": list(PROTOCOL["limitations"])}

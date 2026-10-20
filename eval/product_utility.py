"""Offline factorial experiment: generate requests and grade recorded responses.
No model or human performance is synthesized by the local contract check.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from ktrf.context import (CharTokenCounter, ContextPolicy, EXECUTION_POLICY, KNOWLEDGE_ASSISTANCE_POLICY,
                          prepare_llm_context, validate_llm_grounding)
from ktrf.registry.layers import TermLayer, compile_layered_snapshot
from ktrf.registry.simple_schema import SimpleTermsError, compile_simple_terms
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot

TEXT = "ABC 관련 요청을 처리해 주세요."
QUERY = "ABC의 의미와 담당 대상을 알려 주세요."


def _doc(key, name, definition, override=False):
    return {"terms": [{"key": key, "canonical": name, "surfaces": ["ABC"],
                       "short_definition": definition, "override": override}]}


def swap_worlds():
    a = _doc("billing", "과금 콘솔", "청구 상태를 관리하는 시스템")
    b = _doc("access", "출입 승인 절차", "출입 요청을 승인하는 절차")
    p = _doc("project", "프로젝트 접수창구", "프로젝트 문의를 받는 창구", True)
    s = _doc("session", "세션 검토창구", "현재 세션의 검토를 담당하는 창구", True)
    specs = [
        ("tenant-a", "a", [TermLayer("global", a)], "global:billing"),
        ("tenant-b", "b", [TermLayer("global", b)], "global:access"),
        ("project-a", "a", [TermLayer("global", a), TermLayer("project", p)], "project:project"),
        ("session-a", "a", [TermLayer("global", a), TermLayer("project", p), TermLayer("session", s)], "session:session"),
        ("untrusted-session", "a", [TermLayer("global", a), TermLayer("session", s, trusted=False)], "global:billing")]
    worlds = []
    for name, tenant, layers, expected in specs:
        snap, _ = compile_layered_snapshot(layers, glossary_id=name, tenant_id=tenant,
                    strict_conflicts=True, run_conformance=False)
        worlds.append((name, snap, expected))
    for name, doc in [("ambiguous", {"terms": a["terms"] + b["terms"]}),
                      ("missing", {"terms": []})]:
        snap = compile_snapshot(load_glossary(compile_simple_terms(doc)), run_conformance=False)
        worlds.append((name, snap, None))
    return worlds


def _pack(snap):
    return prepare_llm_context(snap, TEXT, query=QUERY,
        context_policy=ContextPolicy(max_tokens=4000)).context_pack


def local_swap_checks():
    worlds = swap_worlds()
    checks = []
    for name, snap, expected in worlds + worlds[:1]:
        ids = [c["entity_id"] for c in _pack(snap)["resolved_terms"]]
        checks.append({"world": name, "expected": expected, "resolved": ids,
            "passed": ids == ([] if expected is None else [expected]),
            "snapshot_id": snap.snapshot_id})
    rejected = False
    try:
        compile_layered_snapshot([
            TermLayer("global", _doc("a", "과금", "과금")),
            TermLayer("project", _doc("b", "출입", "출입"))],
            strict_conflicts=True, run_conformance=False)
    except SimpleTermsError:
        rejected = True
    return {"kind": "deterministic_contract_checks", "checks": checks,
        "undeclared_override_rejected": rejected,
        "passed": rejected and all(r["passed"] for r in checks),
        "limitations": ["Synthetic glossary; no LLM/human trial.",
                         "Separate snapshot isolation, not server authentication."]}


def _cards(snap, pack, selector):
    if selector == "ktrf":
        cards = [{"entity_id": c["entity_id"], "canonical": c["canonical"],
                  "definition": c["short_definition"], "status": "RESOLVED"}
                 for c in pack["resolved_terms"]]
        cards.extend({"entity_id": c["entity_id"], "canonical": c["canonical"],
                      "definition": c["short_definition"], "status": "AMBIGUOUS"}
                     for a in pack["ambiguous_mentions"] for c in a["candidates"])
        return cards[:3]
    # Local lexical baseline, not a claim about dense RAG.
    ids = sorted({b.entity_id for b in snap.glossary.alias_bindings if b.surface in TEXT})[:3]
    resolved = {c["entity_id"] for c in pack["resolved_terms"]}
    return [{"entity_id": eid, "canonical": snap.glossary.entity(eid).canonical,
             "definition": snap.glossary.entity(eid).description,
             "status": "RESOLVED" if eid in resolved else "AMBIGUOUS"} for eid in ids]


def build_requests():
    rows = []
    for world, snap, expected in swap_worlds():
        pack = _pack(snap)
        entity = snap.glossary.entity(expected) if expected else None
        answer = (entity.grounding or {}).get("short_definition") if entity else None
        for task in ("document_qa", "structured_routing"):
            common = {"case_id": f"{world}:{task}", "world": world, "task": task,
                "snapshot_id": snap.snapshot_id, "expected_entity_id": expected,
                "expected_answer": answer, "pack": pack}
            question = ("ABC가 하는 일을 answer에 정의하라." if task == "document_qa"
                        else "ABC 요청의 담당 대상 entity_id를 반환하라.")
            prompt = (f"문서: {TEXT}\n질문: {question}\n"
                      'JSON {"answer": string|null, "entity_id": string|null}.')
            rows.append({**common, "condition": "no_context", "cards": [],
                         "user": prompt, "system": "한국어 질문에 JSON으로 답하라."})
            for selector in ("ktrf", "lexical"):
                cards = _cards(snap, pack, selector)
                digest = hashlib.sha256(json.dumps(cards, ensure_ascii=False,
                    sort_keys=True).encode()).hexdigest()
                for fmt in ("plain", "structured"):
                    rendered = (json.dumps({"terminology_data": cards}, ensure_ascii=False)
                        if fmt == "structured" else "\n".join(
                        f"- {c['entity_id']} | {c['canonical']} | {c['definition']} | {c['status']}" for c in cards))
                    for policy in ("knowledge", "evidence_only"):
                        instructions = (KNOWLEDGE_ASSISTANCE_POLICY if policy == "knowledge"
                            else EXECUTION_POLICY + "답변도 제공된 근거에만 의존한다.")
                        rows.append({**common, "condition": f"{selector}:{fmt}:{policy}",
                            "selector": selector, "format": fmt, "policy": policy,
                            "cards": cards, "candidate_hash": digest,
                            "user": rendered + "\n" + prompt, "system": instructions})
    for row in rows:
        row["estimated_input_tokens"] = CharTokenCounter().count(row["user"] + row["system"])
    return rows


def malformed_response_field(response, field):
    if field not in response:
        return True
    value = response[field]
    return value is not None and (not isinstance(value, str) or
                                  (field == "entity_id" and not value.strip()))


def grade_outputs(requests, outputs):
    """Missing model outputs stay missing; they are never safe abstentions."""
    known = {(r["case_id"], r["condition"]): r for r in requests}
    scored = {}
    for output in outputs:
        key = (output["case_id"], output["condition"])
        if key not in known or key in scored:
            raise ValueError(f"unknown or duplicate response key: {key}")
        req, response = known[key], output["response"]
        if not isinstance(response, dict):
            raise ValueError("response must be an object")
        field = "answer" if req["task"] == "document_qa" else "entity_id"
        expected = req["expected_answer"] if field == "answer" else req["expected_entity_id"]
        malformed = malformed_response_field(response, field)
        abstained = not malformed and response[field] is None
        correct = not malformed and response[field] == expected
        if field == "entity_id":
            gate = validate_llm_grounding({"selections": [{"surface": req.get("target_surface", "ABC"),
                "entity_id": None if malformed else response.get("entity_id")}]}, req["pack"], purpose="execution", execution_contract='legacy_surface_v1')
            correct = correct and gate["valid"]
        scored[key] = {"correct": correct, "safe_abstention": expected is None and abstained,
                      "over_abstention": expected is not None and abstained,
                      "malformed": malformed, "task": req["task"],
                      "world": req["world"], "entity_id": response.get("entity_id"),
                      "latency_ms": output.get("latency_ms"),
                      "input_tokens": req["estimated_input_tokens"]}
    metrics = {}
    for condition in sorted({r["condition"] for r in requests}):
        members = [(case, r) for (case, cond), r in scored.items() if cond == condition]
        pairs = [(r, scored[(case, "no_context")]) for case, r in members if (case, "no_context") in scored]
        swaps = []
        stale = 0
        for old, new in (("tenant-a", "tenant-b"), ("tenant-a", "project-a"),
                         ("project-a", "session-a")):
            old_key, new_key = (f"{old}:structured_routing", condition), (f"{new}:structured_routing", condition)
            if old_key in scored and new_key in scored:
                before, after = scored[old_key], scored[new_key]
                swaps.append(before["correct"] and after["correct"])
                old_id = known[old_key]["expected_entity_id"]
                stale += after["entity_id"] == old_id
        metrics[condition] = {"observed": len(members),
            "expected": sum(r["condition"] == condition for r in requests),
            "task_success": sum(r["correct"] for _, r in members),
            "safe_abstention": sum(r["safe_abstention"] for _, r in members),
            "over_abstention": sum(r["over_abstention"] for _, r in members),
            "malformed": sum(r["malformed"] for _, r in members),
            "paired_with_baseline": len(pairs),
            "harmful_flip": sum(b["correct"] and not r["correct"] for r, b in pairs),
            "helpful_flip": sum(not b["correct"] and r["correct"] for r, b in pairs),
            "glossary_swap_pairs": len(swaps), "correct_meaning_switch": sum(swaps),
            "previous_meaning_retained": stale,
            "estimated_input_tokens": sum(r["input_tokens"] for _, r in members),
            "latency_ms_observations": [r["latency_ms"] for _, r in members if r["latency_ms"] is not None],
            "by_task": {task: {"observed": sum(r["task"] == task for _, r in members),
                "success": sum(r["task"] == task and r["correct"] for _, r in members)}
                for task in ("document_qa", "structured_routing")}}
    return {"kind": "recorded_model_outputs", "metrics": metrics,
            "missing_outputs": len(known) - len(scored),
            "limitations": ["Tiny synthetic track; no deployment risk certification.",
                "Exact QA matching; paraphrases require blind adjudication.",
                "Human correction time requires a separate human trial."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--responses", type=Path, help="JSONL case_id, condition, response")
    args = parser.parse_args()
    requests = build_requests()
    result = {"local_checks": local_swap_checks(), "requests": requests}
    if args.responses:
        outputs = [json.loads(line) for line in args.responses.read_text().splitlines() if line.strip()]
        result["model_results"] = grade_outputs(requests, outputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "requests": len(requests),
        "local_checks_passed": result["local_checks"]["passed"], "model_results": bool(args.responses)}))


if __name__ == "__main__":
    main()

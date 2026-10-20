"""Controlled contextual QA assistance with unchanged execution authorization."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy

from eval.product_utility import malformed_response_field
from eval.synthetic_grounding import grade_expanded_outputs
from eval.synthetic_grounding_v2 import BALANCED_PROTOCOL, build_balanced_requests
from ktrf.context import CharTokenCounter, validate_llm_grounding

CONDITIONS = ("strict", "qa_context")
STRICT_ABSTENTION_CLAUSE = "대상 연결을 확정할 수 없으면 null."
QA_CONTEXT_CLAUSE = (
    "answer에는 대상 전체 표현의 문서 문맥이 제공된 후보 중 하나의 의미를 유일하게 뒷받침할 때에만 "
    "그 후보의 definition을 그대로 반환한다. 다른 표현이나 부분 표현의 정의를 빌리지 않는다. "
    "제공된 정의가 없거나 문맥으로 하나를 구별할 수 없으면 answer는 null. "
    "entity_id에는 기존에 검증된 연결만 허용하며 검증되지 않은 후보 ID는 null."
)
QA_CONTEXT_POLICY = """
QA 참고 설명에 한정한 예외: JSON의 answer는 자동 실행·치환에 사용하는 구조화 ID 필드가 아니라
사용자가 읽는 참고 설명이다. 대상 전체 표현의 문서 문맥이 제공된 후보 중 하나의 의미를
유일하게 뒷받침하면 AMBIGUOUS 후보의 definition을 answer에 그대로 반환할 수 있다.
외부 지식이나 추측으로 보충하지 않으며, 문맥으로 구별할 수 없으면 answer는 null이다.
이는 resolver가 검증한 연결이나 확정 사실로 승격되지 않는다. 이 예외는 entity_id에는
적용되지 않는다. 어떤 작업에서도 entity_id는 해당 surface에 대해 기존에 검증된 연결만
사용한다. 문맥에 따른 후보 선택은 실행 권한을 부여하지 않으며 승인되지 않은 ID는 null이다.
"""
PROTOCOL = {
    **deepcopy(BALANCED_PROTOCOL),
    "kind": "qa_policy_separation_v1",
    "conditions": list(CONDITIONS),
    "source_condition": "surface_only",
    "policy": "evidence_only_with_contextual_qa_exception",
    "full_pack_is_separate_reference": False,
    "fixed": ["document", "question", "candidate_facts", "surface_bindings", "gold",
              "target_span", "candidate_order", "snapshot", "execution_guard"],
    "primary_endpoint": "Contextual-collision QA, including both-correct accuracy for all 37 contrast pairs.",
    "controls": "All 437 v2 documents: QA and routing, including true ambiguity and negative controls.",
    "intervention": "Single bundled QA policy intervention (system plus QA abstention clause).",
    "limitations": [*(limit for limit in BALANCED_PROTOCOL["limitations"]
                      if not limit.startswith("The full-pack condition")),
        "Both conditions use supplied evidence only; outside knowledge is prohibited.",
        "The bundled intervention does not isolate individual wording changes.",
        "Correct QA does not authorize an entity ID; incidental QA IDs are graded separately.",
        "Previously evaluated synthetic documents are diagnostic controls, not an unseen risk test."],
}


def build_policy_requests(families=None, *, source_requests=None):
    """Keep v2 surface-only inputs fixed and rotate two stateless conditions."""
    if families is not None and source_requests is not None:
        raise ValueError("provide families or source_requests, not both")
    sources = build_balanced_requests(families) if source_requests is None else source_requests
    baselines = [row for row in sources if row["condition"] == "surface_only"]
    if not baselines or len({r["case_id"] for r in baselines}) != len(baselines):
        raise ValueError("nonempty unique surface_only source tasks required")
    rows, counts = [], Counter()
    for source in baselines:
        task = source["task"]
        offset = counts[task] % len(CONDITIONS)
        counts[task] += 1
        for position, condition in enumerate(CONDITIONS[offset:] + CONDITIONS[:offset]):
            row = deepcopy(source)
            row.update(condition=condition, condition_position=position,
                       source_condition="surface_only")
            if condition == "qa_context":
                row["system"] += QA_CONTEXT_POLICY
                if task == "document_qa":
                    # Replace only the prompt suffix, never authored data with similar text.
                    data, prompt = row["user"].split("\n", 1)
                    if prompt.count(STRICT_ABSTENTION_CLAUSE) != 1:
                        raise ValueError("source QA abstention clause changed")
                    row["user"] = data + "\n" + prompt.replace(
                        STRICT_ABSTENTION_CLAUSE, QA_CONTEXT_CLAUSE, 1)
            row["estimated_input_tokens"] = CharTokenCounter().count(row["user"] + row["system"])
            rows.append(row)
    return rows


def _observation(row, output):
    if output is None:
        return {"row": row, "missing": True, "correct": False}
    response = output["response"]
    qa = row["task"] == "document_qa"
    field = "answer" if qa else "entity_id"
    value = response.get(field)
    expected = row["expected_answer"] if qa else row["expected_entity_id"]
    malformed = (output.get("status", "RECEIVED") != "RECEIVED" or
                 malformed_response_field(response, field))
    id_absent = "entity_id" not in response
    id_malformed = not id_absent and malformed_response_field(response, "entity_id")
    entity_id = response.get("entity_id")
    guard_valid = (not id_absent and not id_malformed and validate_llm_grounding(
        {"selections": [{"surface": row["target_surface"], "entity_id": entity_id}]},
        row["pack"], purpose="execution", execution_contract='legacy_surface_v1')["valid"])
    return {"row": row, "missing": False, "malformed": malformed,
        "correct": not malformed and value == expected and (qa or guard_valid),
        "null": not malformed and value is None,
        "wrong": not malformed and value is not None and value != expected,
        "expected": expected, "id_absent": id_absent, "id_malformed": id_malformed,
        "entity_id": entity_id, "guard_valid": guard_valid}


def _summarize(items):
    observed = [item for item in items if not item["missing"]]
    routing = [x for x in observed if x["row"]["task"] == "structured_routing"]
    return {"planned": len(items), "observed": len(observed),
        "missing": len(items) - len(observed), "malformed": sum(x["malformed"] for x in observed),
        "correct": sum(x["correct"] for x in observed), "null": sum(x["null"] for x in observed),
        "wrong": sum(x["wrong"] for x in observed),
        "safe_null": sum(x["null"] and x["expected"] is None for x in observed),
        "positive_null": sum(x["null"] and x["expected"] is not None for x in observed),
        "guard_compliant": sum(not x["malformed"] and x["guard_valid"] for x in routing),
        "guard_accepted_nonnull": sum(not x["malformed"] and x["guard_valid"] and
                                      x["entity_id"] is not None for x in routing),
        "denied_nonnull": sum(not x["malformed"] and x["entity_id"] is not None and
                              not x["guard_valid"] for x in routing),
        "accepted_wrong_id": sum(x["wrong"] and x["guard_valid"] for x in routing)}


def _incidental_ids(items):
    observed = [x for x in items if not x["missing"]]
    valid_type = [x for x in observed if not x["id_absent"] and not x["id_malformed"]]
    nonnull = [x for x in valid_type if x["entity_id"] is not None]
    return {"planned": len(items), "observed": len(observed), "missing": len(items) - len(observed),
        "absent": sum(x["id_absent"] for x in observed),
        "malformed": sum(x["id_malformed"] for x in observed),
        "null": sum(x["entity_id"] is None for x in valid_type), "nonnull": len(nonnull),
        "guard_accepted": sum(x["guard_valid"] for x in nonnull),
        "guard_accepted_wrong": sum(x["guard_valid"] and
            x["entity_id"] != x["row"]["expected_entity_id"] for x in nonnull),
        "denied": sum(not x["guard_valid"] for x in nonnull),
        "denied_semantically_correct": sum(not x["guard_valid"] and
            x["entity_id"] == x["row"]["expected_entity_id"] for x in nonnull)}


def _contextual_pairs(items):
    groups = defaultdict(list)
    for item in items:
        if item["row"]["task"] == "document_qa" and item["row"].get("contrast_pair_id"):
            groups[item["row"]["contrast_pair_id"]].append(item)
    pairs = {key: {"complete": len(members) == 2 and not any(x["missing"] for x in members),
                   "correct_members": sum(x["correct"] for x in members)}
             for key, members in groups.items()}
    complete = {key: value for key, value in pairs.items() if value["complete"]}
    return {"planned": len(pairs), "complete": len(complete), "incomplete": len(pairs) - len(complete),
        "both_correct": sum(x["correct_members"] == 2 for x in complete.values()),
        "exactly_one_correct": sum(x["correct_members"] == 1 for x in complete.values()),
        "neither_correct": sum(x["correct_members"] == 0 for x in complete.values()),
        "both_correct_case_ids": sorted(key for key, value in complete.items()
                                         if value["correct_members"] == 2),
        "pairs": pairs}


def _changes(pairs):
    comparable = [(key, old, new) for key, old, new in pairs if old is not None and new is not None]
    return {"planned": len(pairs), "comparable": len(comparable),
        "incomplete": len(pairs) - len(comparable),
        "helpful": sum(not old and new for _, old, new in comparable),
        "harmful": sum(old and not new for _, old, new in comparable),
        "both_correct": sum(old and new for _, old, new in comparable),
        "both_incorrect": sum(not old and not new for _, old, new in comparable),
        "helpful_case_ids": [key for key, old, new in comparable if not old and new],
        "harmful_case_ids": [key for key, old, new in comparable if old and not new]}


def grade_policy_outputs(requests, outputs):
    """QA correctness never grants execution approval; missing is not abstention."""
    requests, outputs = list(requests), list(outputs)
    keys = [(row["case_id"], row["condition"]) for row in requests]
    if len(set(keys)) != len(keys) or any(row["condition"] not in CONDITIONS for row in requests):
        raise ValueError("unique requests in declared policy conditions required")
    known = dict(zip(keys, requests))
    normalized = []
    for output in outputs:
        record = dict(output)
        if record.get("status", "RECEIVED") != "RECEIVED":
            if record.get("status") != "MALFORMED":
                raise ValueError("grading outputs require response-present statuses")
            row = known.get((record["case_id"], record["condition"]))
            if row is not None and isinstance(record.get("response"), dict):
                record["response"] = dict(record["response"])
                field = "answer" if row["task"] == "document_qa" else "entity_id"
                record["response"].pop(field, None)
        normalized.append(record)
    result = grade_expanded_outputs(requests, normalized)
    recorded = {(out["case_id"], out["condition"]): out for out in outputs}
    observed = {key: _observation(row, recorded.get(key)) for key, row in zip(keys, requests)}
    strata = sorted({row["stratum"] for row in requests})
    tasks = ("document_qa", "structured_routing")
    conditions = {}
    for condition in CONDITIONS:
        items = [value for key, value in observed.items() if key[1] == condition]
        conditions[condition] = {
            "by_task": {task: _summarize([x for x in items if x["row"]["task"] == task]) for task in tasks},
            "by_stratum": {s: {task: _summarize([x for x in items if x["row"]["stratum"] == s and
                x["row"]["task"] == task]) for task in tasks} for s in strata},
            "qa_incidental_ids": _incidental_ids([x for x in items if x["row"]["task"] == "document_qa"]),
            "contextual_pairs": _contextual_pairs(items)}
    by_case = {row["case_id"]: row for row in requests}
    changes = {}
    for case_id in sorted(by_case):
        values = [observed.get((case_id, c)) for c in CONDITIONS]
        changes[case_id] = (case_id, *(None if v is None or v["missing"] else v["correct"] for v in values))
    paired = {"overall": _changes(list(changes.values())),
        "by_task": {task: _changes([v for key, v in changes.items() if by_case[key]["task"] == task])
                    for task in tasks},
        "by_stratum": {s: {task: _changes([v for key, v in changes.items()
            if by_case[key]["stratum"] == s and by_case[key]["task"] == task]) for task in tasks}
            for s in strata}}
    pair_ids = sorted(set().union(*(conditions[c]["contextual_pairs"]["pairs"] for c in CONDITIONS)))
    pairs = []
    for pair_id in pair_ids:
        values = [conditions[c]["contextual_pairs"]["pairs"].get(pair_id) for c in CONDITIONS]
        pairs.append((pair_id, *(None if v is None or not v["complete"] else
                                 v["correct_members"] == 2 for v in values)))
    paired["contextual_pairs"] = _changes(pairs)
    result["policy_diagnostics"] = {"by_condition": conditions, "paired_changes": paired,
        "definitions": {
            "correct": "Exact QA answer; routing additionally requires unchanged execution guard approval.",
            "wrong": "Well-formed non-null field differs from semantic gold; nulls counted separately.",
            "guard_compliant": "Routing field is well formed and accepted, including deliberate null.",
            "qa_incidental_ids": "ID approval is independent of QA answer correctness; absent is not null.",
            "complete_pair": "Both context documents returned responses; malformed fields remain failures.",
            "paired_changes": "Only response-present comparisons; missing remains incomplete, malformed is failure."}}
    result["limitations"] += PROTOCOL["limitations"][-4:]
    return result

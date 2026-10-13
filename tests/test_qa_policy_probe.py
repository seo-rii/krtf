"""Policy intervention preserves evidence and keeps QA separate from execution."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from eval import qa_policy_probe as suite
from eval.blind_gold import digest
from eval.synthetic_grounding_v2 import build_balanced_requests
from ktrf.context import EXECUTION_POLICY


@pytest.fixture(scope="module")
def corpus():
    sources = build_balanced_requests()
    return sources, suite.build_policy_requests(source_requests=sources)


def _output(row, **response):
    return {"case_id": row["case_id"], "condition": row["condition"], "response": response}


def _select(rows, *, stratum, task="document_qa"):
    case_id = next(r["case_id"] for r in rows if r["stratum"] == stratum and r["task"] == task)
    return sorted((r for r in rows if r["case_id"] == case_id), key=lambda r: suite.CONDITIONS.index(r["condition"]))


def test_all_v2_cases_are_preserved_with_frozen_surface_inputs(corpus):
    sources, requests = corpus
    manifest = json.loads(Path("reports/SYNTHETIC_GROUNDING_V2_CORPUS.json").read_text())
    encoded = b"".join((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode() for r in sources)
    assert hashlib.sha256(encoded).hexdigest() == manifest["requests_sha256"]
    assert len(requests) == 1748
    assert len({r["document_id"] for r in requests}) == 437
    baseline = {r["case_id"]: r for r in sources if r["condition"] == "surface_only"}
    changed = {"condition", "condition_position", "source_condition", "system", "user", "estimated_input_tokens"}
    before = digest(sources)
    assert suite.build_policy_requests(source_requests=sources) == requests
    assert digest(sources) == before
    for row in requests:
        original = baseline[row["case_id"]]
        assert {k: v for k, v in row.items() if k not in changed} == {
            k: v for k, v in original.items() if k not in changed}
        assert row["source_condition"] == "surface_only"
        assert row["system"].startswith(EXECUTION_POLICY)
        if row["condition"] == "strict":
            assert row["user"] == original["user"] and row["system"] == original["system"]
            assert row["estimated_input_tokens"] == original["estimated_input_tokens"]
        else:
            assert row["system"] == original["system"] + suite.QA_CONTEXT_POLICY
            expected = original["user"]
            if row["task"] == "document_qa":
                expected = expected.replace(suite.STRICT_ABSTENTION_CLAUSE, suite.QA_CONTEXT_CLAUSE, 1)
            assert row["user"] == expected
        assert json.loads(row["user"].split("\n", 1)[0]) == json.loads(original["user"].split("\n", 1)[0])
        for entity_id in re.findall(r"(?:global|project|session):[a-z0-9_.-]+", row["user"]):
            assert re.fullmatch(r"(?:global|project|session):e_[0-9a-f]{24}", entity_id)


def test_condition_order_rotates_per_task_and_all_contrast_pairs_survive(corpus):
    _, requests = corpus
    for task in ("document_qa", "structured_routing"):
        tasks = [r for r in requests if r["task"] == task]
        for index in range(0, len(tasks), 2):
            pair = tasks[index:index + 2]
            assert len({r["case_id"] for r in pair}) == 1
            assert [r["condition_position"] for r in pair] == [0, 1]
            assert pair[0]["condition"] == suite.CONDITIONS[(index // 2) % 2]
    contrasts = defaultdict(set)
    for row in requests:
        if row.get("contrast_pair_id"):
            contrasts[row["contrast_pair_id"]].add(row["document_id"])
    assert len(contrasts) == 37 and all(len(members) == 2 for members in contrasts.values())


def test_correct_qa_does_not_authorize_incidental_or_routing_id(corpus):
    _, requests = corpus
    qa = _select(requests, stratum="contextual_collision")
    routing = [r for r in requests if r["document_id"] == qa[0]["document_id"] and r["task"] == "structured_routing"]
    rows = qa + routing
    outputs = [_output(r, answer=r["expected_answer"], entity_id=r["expected_entity_id"]) for r in rows]
    result = suite.grade_policy_outputs(rows, outputs)
    for condition in suite.CONDITIONS:
        diagnostics = result["policy_diagnostics"]["by_condition"][condition]
        assert diagnostics["by_task"]["document_qa"]["correct"] == 1
        assert diagnostics["by_task"]["structured_routing"]["correct"] == 0
        assert diagnostics["by_task"]["structured_routing"]["denied_nonnull"] == 1
        assert diagnostics["qa_incidental_ids"]["denied"] == 1
        assert diagnostics["qa_incidental_ids"]["denied_semantically_correct"] == 1
        assert diagnostics["qa_incidental_ids"]["guard_accepted"] == 0


def test_approved_ids_remain_allowed_and_qa_answer_is_independent(corpus):
    _, requests = corpus
    case_id = next(r["case_id"] for r in requests if r["task"] == "document_qa" and
        r["expected_entity_id"] is not None and r["resolver_authorized_entity_id"] == r["expected_entity_id"])
    rows = [r for r in requests if r["case_id"] == case_id]
    outputs = [_output(r, answer="incorrect definition", entity_id=r["expected_entity_id"]) for r in rows]
    result = suite.grade_policy_outputs(rows, outputs)["policy_diagnostics"]
    for condition in suite.CONDITIONS:
        assert result["by_condition"][condition]["qa_incidental_ids"]["guard_accepted"] == 1
        assert result["by_condition"][condition]["by_task"]["document_qa"]["correct"] == 0


def test_true_ambiguity_is_not_rewarded_for_guessing(corpus):
    _, requests = corpus
    strict, context = _select(requests, stratum="ambiguous")
    assert strict["expected_answer"] is None
    candidate = context["cards"][0]
    outputs = [_output(strict, answer=None, entity_id=None),
               _output(context, answer=candidate["definition"], entity_id=candidate["entity_id"])]
    result = suite.grade_policy_outputs([strict, context], outputs)["policy_diagnostics"]
    assert result["by_condition"]["strict"]["by_task"]["document_qa"]["safe_null"] == 1
    assert result["by_condition"]["qa_context"]["by_task"]["document_qa"]["wrong"] == 1
    assert result["by_condition"]["qa_context"]["qa_incidental_ids"]["denied"] == 1
    assert result["paired_changes"]["overall"]["harmful"] == 1


def test_guard_accepted_qa_id_can_still_be_semantically_wrong(corpus):
    _, requests = corpus
    row = next(r for r in requests if r["task"] == "document_qa" and
               r["expected_entity_id"] is None and r["resolver_authorized_entity_id"] is not None)
    result = suite.grade_policy_outputs([row], [_output(row, answer=None,
        entity_id=row["resolver_authorized_entity_id"])])["policy_diagnostics"]["by_condition"][row["condition"]]
    assert result["by_task"]["document_qa"]["correct"] == 1
    assert result["qa_incidental_ids"]["guard_accepted"] == 1
    assert result["qa_incidental_ids"]["guard_accepted_wrong"] == 1


def test_missing_malformed_and_deliberate_null_are_separate(corpus):
    _, requests = corpus
    rows = [r for r in requests if r["condition"] == "strict" and r["task"] == "document_qa"][:5]
    outputs = [_output(rows[1], answer=123, entity_id=[]),
               _output(rows[2], answer=None, entity_id=None),
               _output(rows[3], answer=rows[3]["expected_answer"]),
               _output(rows[4], entity_id=None)]
    result = suite.grade_policy_outputs(rows, outputs)
    qa = result["policy_diagnostics"]["by_condition"]["strict"]["by_task"]["document_qa"]
    ids = result["policy_diagnostics"]["by_condition"]["strict"]["qa_incidental_ids"]
    assert result["missing_outputs"] == 1
    assert (qa["planned"], qa["observed"], qa["missing"], qa["malformed"]) == (5, 4, 1, 2)
    assert qa["null"] == 1 + (rows[3]["expected_answer"] is None)
    assert (ids["missing"], ids["absent"], ids["malformed"], ids["null"]) == (1, 1, 1, 2)
    assert result["policy_diagnostics"]["paired_changes"]["overall"]["comparable"] == 0


def test_pair_accuracy_requires_both_opposite_contexts(corpus):
    _, requests = corpus
    pair_id = next(r["contrast_pair_id"] for r in requests if "contrast_pair_id" in r)
    rows = [r for r in requests if r.get("contrast_pair_id") == pair_id and r["task"] == "document_qa"]
    outputs = [_output(r, answer=r["expected_answer"] if r["condition"] == "qa_context" else None,
                       entity_id=None) for r in rows]
    result = suite.grade_policy_outputs(rows, outputs)["policy_diagnostics"]
    assert result["by_condition"]["strict"]["contextual_pairs"]["neither_correct"] == 1
    assert result["by_condition"]["qa_context"]["contextual_pairs"]["both_correct"] == 1
    assert result["paired_changes"]["contextual_pairs"]["helpful"] == 1
    assert result["paired_changes"]["by_stratum"]["contextual_collision"]["document_qa"]["helpful"] == 2
    partial = suite.grade_policy_outputs(rows, outputs[:-1])["policy_diagnostics"]
    assert partial["paired_changes"]["contextual_pairs"]["incomplete"] == 1
    assert partial["paired_changes"]["contextual_pairs"]["helpful"] == 0


def test_recorded_malformed_status_cannot_be_success_or_safe_null(corpus):
    _, requests = corpus
    rows = _select(requests, stratum="ambiguous")
    outputs = [dict(_output(r, answer=None, entity_id=None), status="MALFORMED") for r in rows]
    before = deepcopy(outputs)
    result = suite.grade_policy_outputs(rows, outputs)
    assert outputs == before
    for condition in suite.CONDITIONS:
        task = result["policy_diagnostics"]["by_condition"][condition]["by_task"]["document_qa"]
        assert task["malformed"] == 1
        assert task["correct"] == task["safe_null"] == task["null"] == 0
        assert result["expanded_diagnostics"][condition]["overall"]["success"] == 0
        assert result["metrics"][condition]["safe_abstention"] == 0
    assert result["policy_diagnostics"]["paired_changes"]["overall"]["both_incorrect"] == 1


def test_answer_oracle_does_not_change_execution_ceiling(corpus):
    _, rows = corpus
    outputs = [_output(r, answer=r["expected_answer"], entity_id=r["expected_entity_id"]) for r in rows]
    result = suite.grade_policy_outputs(rows, outputs)
    for condition in suite.CONDITIONS:
        tasks = result["policy_diagnostics"]["by_condition"][condition]["by_task"]
        assert tasks["document_qa"]["correct"] == 437
        assert tasks["structured_routing"]["correct"] == 336
        assert tasks["structured_routing"]["denied_nonnull"] == 101
        pairs = result["policy_diagnostics"]["by_condition"][condition]["contextual_pairs"]
        assert pairs["planned"] == pairs["both_correct"] == 37


def test_invalid_source_or_response_keys_are_rejected(corpus):
    sources, rows = corpus
    source = next(r for r in sources if r["condition"] == "surface_only" and r["task"] == "document_qa")
    with pytest.raises(ValueError, match="unique"):
        suite.build_policy_requests(source_requests=[source, source])
    changed = deepcopy(source)
    changed["user"] = changed["user"].replace(suite.STRICT_ABSTENTION_CLAUSE, "changed")
    with pytest.raises(ValueError, match="clause changed"):
        suite.build_policy_requests(source_requests=[changed])
    with pytest.raises(ValueError, match="unique requests"):
        suite.grade_policy_outputs([rows[0], rows[0]], [])
    output = _output(rows[0], answer=None, entity_id=None)
    with pytest.raises(ValueError, match="duplicate response"):
        suite.grade_policy_outputs([rows[0]], [output, output])

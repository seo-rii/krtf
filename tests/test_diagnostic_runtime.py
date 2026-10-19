"""Diagnostic interventions keep split identity, guard inputs and paired denominators."""
from copy import deepcopy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from eval import extended_safety, run_extended_suite as runner
from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import canonical
from eval.report_extended_suite import prepare_report, render_markdown


CONDITIONS = ["pack_first_baseline", "pack_last_baseline",
              "pack_first_semantic_check", "pack_last_semantic_check"]


def protocol(experiment):
    conditions = (CONDITIONS + ["extra_none", "extra_compact"])[:
        runner.DIAGNOSTIC_CONDITION_COUNTS.get(experiment, 4)]
    return {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": experiment,
        "conditions": conditions, "comparisons": [[CONDITIONS[0], CONDITIONS[2]]],
        "repeat_count": 1, "limitations": ["Authored diagnostic; no deployment risk guarantee."]}


def qa_rows(experiment="source_pack_factorial"):
    source = "가상기관의 표식은 푸른색이다."
    return [{"case_id": "private-qa-case", "condition": condition, "repeat_id": 0,
        "task": "document_qa", "stratum": "SPAN", "positive_gold": True,
        "expected_answers": ["푸른색"], "parent_document_id": "private-parent",
        "document_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "source_text": source, "question": "표식은?", "source_gold_visible": True,
        "pack_injected": False, "system": "주어진 근거에만 답하세요.", "user": source + condition,
        "evaluation_split": "adaptive_reused", "family_id": "private-qa-family",
        "source_variant": "full", "pack_variant": "none"} for condition in protocol(experiment)["conditions"]]


def routing_rows():
    rows = []
    for split in ("exposed_diagnostic", "fresh_family"):
        for positive in (True, False):
            for condition in CONDITIONS:
                rows.append({"case_id": f"private-{split}-{positive}", "condition": condition,
                    "repeat_id": 0, "task": "structured_routing", "stratum": "LINK" if positive else "NIL",
                    "text": "가상기관", "target_surface": "가상기관", "target_span": [0, 4],
                    "expected_entity_id": "private-entity" if positive else None,
                    "gold": {"label": "LINK" if positive else "NIL", "entity_ref": "private-entity" if positive else None},
                    "document_sha256": hashlib.sha256("가상기관".encode()).hexdigest(),
                    "parent_document_id": f"private-parent-{split}-{positive}",
                    "family_id": "private-family-" + split, "evaluation_split": split,
                    "system": "판단하세요.", "user": "가상기관 " + condition, "injected": True})
    return rows


@pytest.fixture
def safety_hooks(monkeypatch):
    validations, responses = [], []
    monkeypatch.setitem(sys.modules, "eval.diagnostic_safety", SimpleNamespace(
        validate_robustness_requests=lambda rows: validations.append(rows)))
    monkeypatch.setattr(runner, "validate_production_requests", lambda *a, **k: pytest.fail(
        "robustness rows must go through their intervention validator"))

    def grade(row, response):
        responses.append(response)
        selected = response.get("selections", [{}])[0].get("entity_id") if isinstance(response, dict) else None
        positive = row["expected_entity_id"] is not None
        correct_id = positive and selected == row["expected_entity_id"]
        abstention = selected is None
        wrong_id = not abstention and not correct_id
        return {"correct": correct_id or (not positive and abstention), "accepted_correct_id": correct_id,
            "accepted_wrong_id": wrong_id, "correct_abstention": not positive and abstention,
            "over_abstention": positive and abstention, "attempted_nonnull": not abstention,
            "guard_valid": True, "semantic_match": correct_id or (not positive and abstention)}

    monkeypatch.setattr(extended_safety, "grade_safety", grade)
    return validations, responses


@pytest.mark.parametrize("experiment", ["source_pack_factorial", "fresh_compact"])
def test_diagnostic_qa_requires_fixed_split_and_family(experiment):
    rows = qa_rows(experiment)
    assert runner.validate_requests(rows, protocol(experiment)) is rows
    for field in ("evaluation_split", "family_id"):
        changed = deepcopy(rows)
        changed[0][field] = "another"
        with pytest.raises(ValueError, match="disagree"):
            runner.validate_requests(changed, protocol(experiment))
        for row in changed:
            row.pop(field)
        with pytest.raises(ValueError, match="metadata"):
            runner.validate_requests(changed, protocol(experiment))


def test_diagnostic_family_cannot_cross_exposed_and_fresh_splits():
    rows = qa_rows("fresh_compact")
    fresh = deepcopy(rows)
    for row in fresh:
        row.update(case_id="private-second-case", evaluation_split="fresh_context_holdout")
    with pytest.raises(ValueError, match="family cannot cross"):
        runner.validate_requests(rows + fresh, protocol("fresh_compact"))


@pytest.mark.parametrize("experiment", ["source_pack_factorial", "fresh_compact", "safety_robustness"])
def test_diagnostic_experiment_task_mismatch_rejected(experiment):
    rows = qa_rows() if experiment == "safety_robustness" else routing_rows()
    with pytest.raises(ValueError, match="task differs"):
        runner.validate_requests(rows, protocol(experiment))


@pytest.mark.parametrize("experiment", ["source_pack_factorial", "fresh_compact", "safety_robustness"])
def test_declared_diagnostic_condition_count_is_fixed(experiment):
    declared = protocol(experiment)
    declared["conditions"] = declared["conditions"][:-1]
    with pytest.raises(ValueError, match="requires .* conditions"):
        runner.validate_protocol(declared)


def test_robustness_validation_dispatch_and_complete_matrix(safety_hooks):
    rows = routing_rows()
    assert runner.validate_requests(rows, protocol("safety_robustness")) is rows
    assert safety_hooks[0] == [rows]
    with pytest.raises(ValueError, match="matrix"):
        runner.validate_requests(rows[:-1], protocol("safety_robustness"))


def selected_id(row):
    positive = row["expected_entity_id"] is not None
    intervention = row["condition"] == CONDITIONS[2]
    fresh = row["evaluation_split"] == "fresh_family"
    correct = (positive == intervention) if fresh else (positive != intervention)
    return (row["expected_entity_id"] if positive else None) if correct else (
        "wrong-private-entity" if fresh or not positive else None)


def routing_outputs(rows):
    return [{"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
        "response": {"selections": [{"surface": row["target_surface"], "entity_id": selected_id(row)}]}}
        for row in rows]


def test_splitwise_safety_pairs_and_family_counts(safety_hooks):
    rows = routing_rows()
    graded = runner.grade_outputs(rows, routing_outputs(rows), protocol("safety_robustness"))
    comparison = CONDITIONS[0] + "_to_" + CONDITIONS[2]
    assert graded["by_variant"][CONDITIONS[0]]["families"] == 2
    for split, values in graded["by_evaluation_split"].items():
        assert values["questions"] == 2 and values["families"] == 1
        paired = values["paired"][comparison]
        assert paired["helpful"] == paired["harmful"] == 1
        assert paired["helpful_rate_among_comparable"] == paired["harmful_rate_among_comparable"] == 0.5
        assert paired["mean_correctness_delta_all_planned"] == 0
        assert paired["identical_prompt_pairs"] == 0
        assert set(values["by_variant"][CONDITIONS[0]]["by_stratum"]) == {"LINK", "NIL"}
    fresh = graded["by_evaluation_split"]["fresh_family"]["paired"][comparison]
    assert fresh["accepted_wrong_id_increased"] == fresh["accepted_wrong_id_decreased"] == 1
    exposed = graded["by_evaluation_split"]["exposed_diagnostic"]["paired"][comparison]
    assert exposed["over_abstention_increased"] == 1
    assert exposed["over_abstention_increase_rate_among_comparable"] == 0.5


def test_missing_or_malformed_pairs_have_no_zero_denominator_credit(safety_hooks):
    rows = routing_rows()
    outputs = routing_outputs(rows)
    response = outputs[0]["response"]
    response["unexpected"] = "complete response must reach guard"
    graded = runner.grade_outputs(rows, outputs[:1], protocol("safety_robustness"))
    assert safety_hooks[1][0] is response
    comparison = CONDITIONS[0] + "_to_" + CONDITIONS[2]
    for values in graded["by_evaluation_split"].values():
        paired = values["paired"][comparison]
        assert paired["comparable"] == paired["helpful"] == paired["harmful"] == 0
        assert paired["harmful_rate_among_comparable"] is None
        assert paired["accepted_wrong_id_increase_rate_among_comparable"] is None
        assert values["by_variant"][CONDITIONS[0]]["accepted_wrong_id_rate_among_accepted"] is None
    assert graded["by_variant"][CONDITIONS[0]]["malformed"] == 1


def test_new_qa_pair_rates_with_missing_outputs():
    rows = qa_rows()
    outputs = [{"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
        "response": {"answer": "푸른색" if row["condition"] == CONDITIONS[2] else "wrong"}} for row in rows]
    graded = runner.grade_outputs(rows, outputs, protocol("source_pack_factorial"))
    pair = next(iter(graded["by_evaluation_split"]["adaptive_reused"]["paired"].values()))
    assert pair["helpful"] == pair["helpful_rate_among_comparable"] == 1
    assert pair["harmful_rate_among_comparable"] == 0
    empty = runner.grade_outputs(rows, [], protocol("source_pack_factorial"))
    assert next(iter(empty["paired"].values()))["helpful_rate_among_comparable"] is None


def test_sealed_report_preserves_split_costs_and_private_identity(tmp_path, monkeypatch, safety_hooks):
    rows = routing_rows()
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical({"protocol": protocol("safety_robustness"),
        "provenance": {"code_revision": "authored-revision", "source": "authored"}, "requests": rows}))
    outputs = iter(routing_outputs(rows))

    def api(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "authored-model"}]}
        return {"choices": [{"message": {"content": json.dumps(next(outputs)["response"])},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}

    monkeypatch.setattr(runner, "_request_json", api)
    root = tmp_path / "result"
    runner.run_benchmark(requests_file=frozen, endpoint="http://127.0.0.1:1234/v1",
        model="authored-model", out_dir=root, code_revision="authored-revision")
    summary = prepare_report(root)
    validate_public_json(summary)
    assert summary["families"] == 2 and summary["questions"] == 4
    assert set(summary["by_evaluation_split"]) == {"exposed_diagnostic", "fresh_family"}
    for values in summary["by_evaluation_split"].values():
        assert all(v["usage"]["prompt_tokens"] == 20 for v in values["by_variant"].values())
    serialized = json.dumps(summary)
    for private in ("private-family", "private-entity", "private-parent", "private-exposed"):
        assert private not in serialized
    markdown = render_markdown(summary)
    assert "fresh_family" in markdown and "no new deployment risk bound" in markdown


def test_legacy_grades_do_not_gain_diagnostic_fields():
    rows = qa_rows("transfer")
    for row in rows:
        row.pop("evaluation_split")
        row.pop("family_id")
    graded = runner.grade_outputs(rows, [], protocol("transfer"))
    assert set(graded) == {"cases", "missing_outputs", "by_variant", "paired"}
    assert "families" not in graded["by_variant"][CONDITIONS[0]]
    assert "helpful_rate_among_comparable" not in next(iter(graded["paired"].values()))

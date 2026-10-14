"""Controlled ranking inputs never acquire production execution authority."""

from copy import deepcopy
import hashlib
import json
import sys

import pytest

from eval.context_ranking_corpus import build_cases, hypotheses
from eval.run_context_ranking import (BatchOne, INPUT_VARIANTS, StrictLocalScalarScorer,
                                      _runtime_provenance, evaluate, preflight_pairs)


@pytest.fixture(scope="module")
def cases():
    return build_cases()


class ConstantScorer:
    reranker_id = "test-constant"

    def __init__(self, score=-4.25):
        self.score, self.calls = score, []

    def score_pairs(self, pairs):
        self.calls.extend(pairs)
        return [self.score] * len(pairs)


def test_all_variants_keep_identical_complete_candidate_sets_and_guards(cases):
    scorer = ConstantScorer()
    report = evaluate(cases, scorer, repeats=1)
    inventories = []
    for result in report["variants"].values():
        inventories.append([(row["case_id"],
                             [(c["entity_id"], c["path_id"], c["guard_allowed"], c["guard_reasons"])
                              for c in row["candidates"]]) for row in result["cases"]])
        assert result["measured_pair_calls"] == 128
        assert result["mean_candidate_count"] == 2
        assert result["candidate_exact_link_recall"] == 1.0
        assert result["positive_cases"] == 32
    assert all(inventory == inventories[0] for inventory in inventories)
    assert len(scorer.calls) == 650  # 640 measured pairs and ten untimed warmups.
    assert report["token_proof"]["validated_pairs"] == 640
    assert report["production_authorized"] is False
    assert report["coverage_valid"] is False
    assert all(row["production_authorized"] is False for row in report["rows"])


def test_overflow_in_later_format_stops_before_any_inference(cases):
    class Tokenizer:
        def __call__(self, query, profile, **kwargs):
            assert kwargs["truncation"] is False
            return {"input_ids": [1] * (50 if "[TARGET]" in query else 2)}

    scorer = ConstantScorer()
    scorer.tokenizer = Tokenizer()
    with pytest.raises(ValueError, match="token overflow before inference"):
        evaluate(cases, scorer, repeats=1, max_length=20)
    assert scorer.calls == []


def test_high_ranking_scores_do_not_authorize_roles_or_negative_labels(cases):
    report = evaluate(cases, ConstantScorer(100.0), repeats=1, variants=("path_full",))
    rows = report["rows"]
    roles = [row for row in rows if row["gold_kind"] == "COMPOSITIONAL"]
    assert roles
    assert all(not row["guard_allowed"] for row in roles)
    assert all(not c["guard_allowed"] for row in roles for c in row["candidates"])
    assert all("typed_derivative" in row["guard_reasons"] for row in roles)
    assert all(not row["top1_exact_link"] for row in rows if row["gold_kind"] != "LINK")
    assert all(row["production_authorized"] is False for row in rows)


def test_negative_raw_scores_and_ties_remain_raw_and_deterministic(cases):
    report = evaluate(cases, ConstantScorer(-12.75), repeats=2, variants=("target_full",))
    result = report["variants"]["target_full"]
    assert result["measured_pair_calls"] == 256
    assert result["all_scores_repeat_stable"] is True
    for row in result["cases"]:
        assert row["top_score"] == -12.75
        assert row["score_margin"] == 0.0
        assert [c["entity_id"] for c in row["candidates"]] == sorted(c["entity_id"] for c in row["candidates"])


def test_full_context_and_target_offsets_preserved_in_frozen_pairs(cases):
    fixed = [hypotheses(case) for case in cases]
    proof = preflight_pairs(cases, fixed)
    sample = next(case for case in cases if len(case["text"]) > 200)
    by_variant = {row["variant"]: row for row in proof["pairs"]
                  if row["case_id"] == sample["case_id"] and row["entity_id"] == sample["candidates"][0]["entity_id"]}
    start, end = sample["core_span"]
    marked = sample["text"][:start] + "[TARGET]" + sample["text"][start:end] + "[/TARGET]" + sample["text"][end:]
    assert by_variant["surface"]["query"] == sample["text"][start:end]
    assert by_variant["target_full"]["query"] == marked
    assert by_variant["path_full"]["query"].startswith(marked + "\nPATH ")
    assert len(by_variant["target_local"]["query"]) < len(marked)
    assert all(row["token_count"] is None for row in proof["pairs"])
    assert proof["truncation"] is False


def test_annotation_and_gold_never_enter_pair_inputs(cases):
    changed = deepcopy(cases)
    for case in changed:
        case["world_gold"] = {"label": "NIL", "entity_ref": None}
        case["expected_entity_id"] = None
        case["gold"] = []
        case["expected_answer"] = None
        case["decisive_evidence"] = [{"quote": "FAKE GOLD ANSWER"}]
    original = preflight_pairs(cases, [hypotheses(case) for case in cases])
    replaced = preflight_pairs(changed, [hypotheses(case) for case in changed])
    assert original == replaced
    assert "FAKE GOLD ANSWER" not in json.dumps(original)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf"), True])
def test_invalid_scalar_outputs_rejected(score):
    with pytest.raises(ValueError, match="finite raw relevance"):
        BatchOne(ConstantScorer(score)).score_pairs([("query", "profile")])


def test_batch_one_synchronizes_before_and_after_each_pair():
    events = []

    class Scorer:
        def synchronize(self):
            events.append("sync")

        def score_pairs(self, pairs):
            assert len(pairs) == 1
            events.append("score")
            return [-8.0]

    measured = BatchOne(Scorer())
    assert measured.score_pairs([("q1", "p1"), ("q2", "p2")]) == [-8.0, -8.0]
    assert events == ["sync", "score", "sync", "sync", "score", "sync"]
    assert len(measured.latencies_ms) == 2


def test_direct_scalar_adapter_rechecks_overflow_before_model_call():
    scorer = StrictLocalScalarScorer.__new__(StrictLocalScalarScorer)
    scorer.max_length = 3
    scorer.tokenizer = lambda *args, **kwargs: {"input_ids": [0, 1, 2, 3]}
    # No torch/model attributes are needed: overflow fails first.
    with pytest.raises(ValueError, match="token overflow before inference"):
        scorer.score_pairs([("query", "profile")])


def test_runtime_provenance_records_actual_model_and_process_gpu_memory():
    from types import SimpleNamespace

    cuda = SimpleNamespace(synchronize=lambda device: None,
                           get_device_properties=lambda device: SimpleNamespace(name="test GPU", total_memory=800),
                           max_memory_allocated=lambda device: 350,
                           max_memory_reserved=lambda device: 400)
    scorer = SimpleNamespace(model=SimpleNamespace(
        parameters=lambda: iter([SimpleNamespace(dtype="torch.float32")]),
        config=SimpleNamespace(_attn_implementation="sdpa", max_position_embeddings=16384)),
        torch=SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="13.0"),
                              backends=SimpleNamespace(cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=False)))),
        tokenizer=SimpleNamespace(model_max_length=16384), max_length=1024, device="cuda:0")
    runtime = _runtime_provenance(scorer)
    assert runtime["model_parameter_dtypes"] == ["torch.float32"]
    assert runtime["attention_implementation"] == "sdpa"
    assert runtime["physical_position_limit"] == runtime["tokenizer_model_max_length"] == 16384
    assert runtime["requested_pair_token_limit"] == 1024
    assert runtime["gpu"]["peak_allocated_bytes"] == 350
    assert runtime["gpu"]["peak_reserved_bytes"] == 400
    assert runtime["gpu"]["total_memory_bytes"] == 800
    assert runtime["torch_cuda_version"] == "13.0"
    assert runtime["matmul_allow_tf32"] is False
    assert _runtime_provenance(ConstantScorer()) is None


def test_pair_token_proof_rejects_nested_ids(cases):
    tokenizer = lambda *args, **kwargs: {"input_ids": [[1, 2, 3]]}
    with pytest.raises(ValueError, match="flat integer"):
        preflight_pairs(cases, [hypotheses(case) for case in cases], tokenizer=tokenizer, max_length=10)


def test_cli_hashes_the_evaluated_case_bytes_even_if_input_changes(cases, tmp_path, monkeypatch):
    from eval import run_context_ranking as runner

    payload = b"".join(json.dumps(case, ensure_ascii=False).encode() + b"\n" for case in cases)
    source, output = tmp_path / "cases.jsonl", tmp_path / "report.json"
    source.write_bytes(payload)
    original = runner.evaluate

    def changed_after_scoring(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_bytes(b"changed after scoring\n")
        return result

    monkeypatch.setattr(runner, "evaluate", changed_after_scoring)
    monkeypatch.setattr(sys, "argv", ["ranking", "--cases", str(source), "--out", str(output), "--repeats", "1"])
    runner.main()
    report = json.loads(output.read_text())
    assert report["cases_sha256"] == hashlib.sha256(payload).hexdigest()
    assert output.with_suffix(".md").exists()
    assert report["risk_protocol_sha256"]

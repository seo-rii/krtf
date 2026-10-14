"""New score observations cannot refit rules or bypass structural guards."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import sys

import pytest

from eval import run_context_ranking_challenge as runner
from ktrf.segmentation import StructuralPath


class ConstantScorer:
    reranker_id = "constant-test"

    def __init__(self, score=5):
        self.score, self.calls = score, []

    def score_pairs(self, pairs):
        self.calls.extend(pairs)
        return [self.score] * len(pairs)


class ProfileScorer(ConstantScorer):
    def score_pairs(self, pairs):
        self.calls.extend(pairs)
        return [6.0 if profile == "first profile" else 1.0 for query, profile in pairs]


def case(case_id, *, document_id=None, text="첫쪽 나래는 작업했다.", occurrence=0,
         gold="global:e1", label=None, role=False, group=None):
    alias = "나래"
    start = -1
    for _ in range(occurrence + 1):
        start = text.find(alias, start + 1)
    assert start >= 0
    end = start + len(alias)
    path = StructuralPath(token=alias + ("장" if role else ""), token_span=(start, end + int(role)),
                          core=alias, core_span=(start, end), kind="SUFFIX" if role else "BARE",
                          residual="장" if role else "", residual_kind="SUFFIX" if role else "",
                          full_identity="DISTINCT" if role else "SAME",
                          relation="HAS_ROLE" if role else "IDENTITY")
    candidates = [{"entity_id": "global:e" + str(i), "path": asdict(path),
                   "profile": profile, "channel": "abbrev", "transform_cost": 0.0}
                  for i, profile in ((1, "first profile"), (2, "second profile"))]
    return {"case_id": case_id, "document_id": document_id or case_id,
            "family_id": "new-family", "split": "external_test", "domain": "operations",
            "source_collection": "context_ranking_challenge", "text": text,
            "document_sha256": hashlib.sha256(text.encode()).hexdigest(), "stratum": label or "paraphrase",
            "target_span": [start, end + int(role)], "core_span": [start, end],
            "expected_entity_id": gold, "semantic_label": label or ("LINK" if gold else "NIL"),
            "target_group_id": group, "candidates": candidates}


@pytest.fixture
def unit_cases(monkeypatch):
    # Corpus schema/label validation has separate integration tests. These
    # small cases isolate actual pair building, score rules and guards.
    monkeypatch.setattr(runner, "validate_cases", lambda cases: cases)
    return [case("correct"), case("wrong", gold="global:e2"), case("nil", gold=None),
            case("ambiguous", gold=None, label="AMBIGUOUS"),
            case("role", text="첫쪽 나래장은 작업했다.", gold=None,
                 label="COMPOSITIONAL", role=True)]


def test_frozen_prior_rules_are_identified_by_exact_report_bytes():
    lexical, nano = runner.frozen_protocol("lexical"), runner.frozen_protocol("nano")
    assert lexical["rule"] == {"minimum_score": .7, "minimum_margin": .1}
    assert nano["rule"] == {"minimum_score": 0., "minimum_margin": 2.}
    assert lexical["family_alpha"] == nano["family_alpha"] == .00625
    for protocol in (lexical, nano):
        assert protocol["prior_report_sha256"] == protocol["declared_protocol"]["prior_report_sha256"][protocol["backend"]]
        assert len(protocol["declared_protocol_file_sha256"]) == 64
        assert protocol["selection_status"].endswith("NO_THRESHOLD_SEARCH")
        assert protocol["production_authorized"] is False


def test_new_negative_and_wrong_positive_proposals_are_errors(unit_cases):
    report = runner.evaluate(unit_cases, ProfileScorer(), backend="nano", variants=("target_full",))
    result = report["variants"]["target_full"]
    assert result["proposals"] == 4
    assert result["correct_proposals"] == 1
    assert result["wrong_proposals"] == 3
    assert result["wrong_positive_proposals"] == 1
    assert result["wrong_negative_proposals"] == 2
    assert result["by_stratum"]["AMBIGUOUS"]["wrong_proposals"] == 1
    assert result["family_risk"]["families_with_proposals"] == 1
    assert result["family_risk"]["families_with_any_wrong_proposal"] == 1
    assert report["threshold_fitting_performed"] is False
    assert report["production_authorized"] is False
    assert all(row["production_authorized"] is False for row in report["rows"])


def test_new_scores_and_gold_do_not_change_frozen_threshold(unit_cases):
    first = runner.evaluate(unit_cases, ProfileScorer(), backend="nano", variants=("surface",))
    changed = deepcopy(unit_cases)
    for row in changed:
        row["expected_entity_id"], row["semantic_label"] = None, "NIL"
    second = runner.evaluate(changed, ConstantScorer(-100), backend="nano", variants=("surface",))
    assert first["frozen_protocol"] == second["frozen_protocol"]
    assert first["frozen_protocol_sha256"] == second["frozen_protocol_sha256"]
    assert "threshold_grid" not in first


def test_changed_threshold_and_backend_rejected_before_scoring(unit_cases):
    scorer = ProfileScorer()
    protocol = runner.frozen_protocol("nano")
    protocol["rule"]["minimum_margin"] = 0
    with pytest.raises(ValueError, match="frozen rules"):
        runner.evaluate(unit_cases, scorer, backend="nano", protocol=protocol)
    with pytest.raises(ValueError, match="backend must match"):
        runner.evaluate(unit_cases, scorer, backend="lexical", protocol=runner.frozen_protocol("nano"))
    assert scorer.calls == []


def test_structural_roles_block_even_high_confident_relevance(unit_cases):
    report = runner.evaluate(unit_cases, ProfileScorer(), backend="nano", variants=("target_full",))
    role = next(row for row in report["rows"] if row["gold_kind"] == "COMPOSITIONAL")
    assert role["top_score"] == 6
    assert role["score_margin"] == 5
    assert role["guard_allowed"] is False
    assert "typed_derivative" in role["guard_reasons"]
    assert role["proposal_selected"] is False
    assert all(not candidate["guard_allowed"] for candidate in role["candidates"])


def test_same_document_unmarked_pairs_equal_marked_targets_distinct(unit_cases):
    text = "첫 작업 나래에 요청했다. " + "일정 확인. " * 45 + "다른 작업 나래에 전달했다."
    first = case("multi::a", document_id="multi", text=text, gold="global:e1", group="multi")
    second = case("multi::b", document_id="multi", text=text, occurrence=1, gold="global:e2", group="multi")
    report = runner.evaluate([first, second], ProfileScorer(), backend="nano",
                             variants=("context_full", "target_full"))
    for result in report["variants"].values():
        assert result["target_cases"] == 2
        assert result["documents"] == 1
        assert result["families"] == 1
    control = report["variants"]["context_full"]["multi_target_controls"]
    assert control["all_inputs_identical"] is True
    assert control["all_scores_identical"] is True
    assert control["different_entity_groups"] == 1
    assert control["different_entity_top_changed"] == 0
    assert control["both_top1_correct"] == 0
    assert report["variants"]["target_full"]["multi_target_controls"]["all_inputs_identical"] is False
    pairs = report["token_proof"]["pairs"]
    queries = [pair["query"] for pair in pairs if pair["variant"] == "target_full"
               and pair["entity_id"] == "global:e1"]
    assert queries[0] != queries[1]
    assert queries[0].replace("[TARGET]", "").replace("[/TARGET]", "") == text
    assert queries[1].replace("[TARGET]", "").replace("[/TARGET]", "") == text


def test_all_inputs_preflight_before_first_warmup_even_late_overflow(unit_cases):
    scorer = ConstantScorer()
    scorer.tokenizer = lambda query, profile, **kwargs: {
        "input_ids": [1] * (50 if "[TARGET]" in query else 2)}
    with pytest.raises(ValueError, match="token overflow before inference"):
        runner.evaluate(unit_cases, scorer, max_length=20)
    assert scorer.calls == []


def test_gold_and_annotation_excluded_from_model_pair_inputs(unit_cases):
    changed = deepcopy(unit_cases)
    for row in changed:
        row["expected_entity_id"] = "FAKE GOLD ANSWER"
        row["world_gold"] = {"label": "LINK", "entity_ref": "FAKE GOLD ANSWER"}
        row["decisive_evidence"] = [{"quote": "FAKE GOLD ANSWER"}]
    first = runner.preflight_pairs(unit_cases, [runner.hypotheses(row) for row in unit_cases])
    second = runner.preflight_pairs(changed, [runner.hypotheses(row) for row in changed])
    assert first == second
    assert "FAKE GOLD ANSWER" not in json.dumps(first)


def test_single_repeat_leaves_stability_unverified(unit_cases):
    report = runner.evaluate(unit_cases, ConstantScorer(), repeats=1,
                             variants=("target_full",))
    result = report["variants"]["target_full"]
    assert result["repetition_stability_checked"] is False
    assert result["all_scores_repeat_stable"] is None
    assert all(row["deterministic"] is None and not row["repetition_stability_checked"]
               for row in result["cases"])


def test_constant_score_ties_abstain_without_probability_transform(unit_cases):
    report = runner.evaluate(unit_cases, ConstantScorer(-12.75), backend="nano", repeats=2,
                             variants=("target_full",))
    result = report["variants"]["target_full"]
    assert result["proposals"] == 0
    assert result["tie_rejections"] == len(unit_cases)
    assert result["all_scores_repeat_stable"] is True
    assert result["measured_pair_calls"] == len(unit_cases) * 2 * 2
    assert all(row["top_score"] == -12.75 and row["score_margin"] == 0 for row in report["rows"])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), True])
def test_nonfinite_or_boolean_scalar_rejected(unit_cases, invalid):
    with pytest.raises(ValueError, match="finite raw relevance"):
        runner.evaluate(unit_cases, ConstantScorer(invalid), variants=("surface",))


def test_cluster_bound_uses_families_not_targets_or_documents(unit_cases):
    from eval.fixed_risk import binomial_error_ucb

    only_correct = [case(str(i)) for i in range(20)]
    report = runner.evaluate(only_correct, ProfileScorer(), backend="nano", variants=("target_full",))
    risk = report["variants"]["target_full"]["family_risk"]
    assert risk["families_with_proposals"] == 1
    assert risk["family_any_error_ucb"] == pytest.approx(binomial_error_ucb(0, 1, .00625))
    assert risk["family_any_error_ucb"] > binomial_error_ucb(0, 20, .00625)
    assert risk["bound_assumptions_met"] is False


def test_full_new_inventory_fixed_candidates_and_control_groups():
    cases = runner.build_cases()
    assert len(cases) == 384
    assert len({row["document_id"] for row in cases}) == 336
    assert len({row["family_id"] for row in cases}) == 24
    assert all(row["split"] == "external_test" for row in cases)
    report = runner.evaluate(cases, ConstantScorer(), variants=("context_full",))
    result = report["variants"]["context_full"]
    assert result["measured_pair_calls"] == 768
    assert result["positive_cases"] + result["negative_cases"] == 384
    assert result["candidate_exact_link_recall"] == 1
    assert result["multi_target_controls"]["groups"] == 48
    assert result["multi_target_controls"]["both_top1_correct"] == 0
    assert result["multi_target_controls"]["all_inputs_identical"] is True
    assert result["multi_target_controls"]["all_scores_identical"] is True


def test_cli_hashes_frozen_input_bytes_before_possible_external_rewrite(unit_cases, tmp_path, monkeypatch):
    fixture = tmp_path / "families.jsonl"
    fixture.write_bytes(b"fixture source\n")
    for row in unit_cases:
        row["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
    payload = b"".join(json.dumps(row, ensure_ascii=False).encode() + b"\n" for row in unit_cases)
    source, output = tmp_path / "cases.jsonl", tmp_path / "report.json"
    source.write_bytes(payload)
    annotation = tmp_path / "annotation_manifest.json"
    annotation.write_text(json.dumps({"review_status": "ADJUDICATED_BEFORE_INFERENCE",
                                      "final_fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest()}))
    original_protocol = runner.PROTOCOL_PATH
    monkeypatch.setattr(runner, "PROTOCOL_PATH", tmp_path / "protocol.json")
    monkeypatch.setattr(runner, "_source_manifest", lambda: {})
    original_evaluate = runner.evaluate

    def rewrite_after_scoring(*args, **kwargs):
        result = original_evaluate(*args, **kwargs)
        source.write_bytes(b"changed after scoring\n")
        return result

    monkeypatch.setattr(runner, "evaluate", rewrite_after_scoring)
    monkeypatch.setattr(sys, "argv", ["challenge", "--cases", str(source), "--out", str(output),
                                     "--protocol", str(original_protocol),
                                     "--annotation-manifest", str(annotation)])
    runner.main()
    report = json.loads(output.read_text())
    assert report["cases_sha256"] == hashlib.sha256(payload).hexdigest()
    assert report["protocol_file_sha256"] == hashlib.sha256(original_protocol.read_bytes()).hexdigest()
    assert report["annotation_manifest"]["review_status"] == "ADJUDICATED_BEFORE_INFERENCE"
    assert report["threshold_fitting_performed"] is False
    assert output.with_suffix(".md").exists()


@pytest.mark.parametrize("invalid", ["unreviewed", "source_changed", "stale_cases"])
def test_cli_rejects_unreviewed_or_stale_fixture_before_loading_scorer(
        unit_cases, tmp_path, monkeypatch, invalid):
    fixture = tmp_path / "families.jsonl"
    fixture.write_bytes(b"reviewed source\n")
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    annotation = tmp_path / "annotation_manifest.json"
    annotation.write_text(json.dumps({
        "review_status": "PENDING" if invalid == "unreviewed" else "ADJUDICATED_BEFORE_INFERENCE",
        "final_fixture_sha256": "0" * 64 if invalid == "source_changed" else digest,
    }))
    for row in unit_cases:
        row["fixture_sha256"] = "0" * 64 if invalid == "stale_cases" else digest
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in unit_cases))
    actual_protocol = runner.PROTOCOL_PATH
    monkeypatch.setattr(runner, "PROTOCOL_PATH", tmp_path / "protocol.json")
    scorer_loaded = []
    monkeypatch.setattr(runner, "LexicalCrossEncoder", lambda: scorer_loaded.append(True))
    monkeypatch.setattr(sys, "argv", ["challenge", "--cases", str(cases_path),
                                     "--protocol", str(actual_protocol), "--out", str(tmp_path / "out.json"),
                                     "--annotation-manifest", str(annotation)])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    assert scorer_loaded == []
    assert not (tmp_path / "out.json").exists()

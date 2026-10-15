"""Evidence experiments preserve source identity, actual queries and guards."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import sys

import pytest

from eval import occurrence_evidence_corpus as corpus
from eval import run_occurrence_evidence as runner
from eval.context_ranking_corpus import _digest
from ktrf.segmentation import StructuralPath


class ConstantScorer:
    reranker_id = "constant-test"

    def __init__(self, score=6):
        self.score, self.calls = score, []

    def score_pairs(self, pairs):
        self.calls.extend(pairs)
        return [self.score] * len(pairs)


class ProfileScorer(ConstantScorer):
    def score_pairs(self, pairs):
        self.calls.extend(pairs)
        return [6.0 if profile == "first profile" else 1.0 for query, profile in pairs]


@dataclass(frozen=True)
class Selection:
    rendered_query: str
    spans: tuple
    mode: str
    status: str
    gate_allowed: bool
    abstain_reason: str | None
    assertion: object = None


def case(case_id, *, document_id=None, text="첫쪽 나래는 작업했다.", occurrence=0,
         gold="global:e1", label=None, role=False, group=None, cohort="development"):
    start = -1
    for _ in range(occurrence + 1):
        start = text.find("나래", start + 1)
    assert start >= 0
    end = start + 2
    path = StructuralPath(token="나래" + ("장" if role else ""), token_span=(start, end + int(role)),
                          core="나래", core_span=(start, end), kind="SUFFIX" if role else "BARE",
                          residual="장" if role else "", residual_kind="SUFFIX" if role else "",
                          full_identity="DISTINCT" if role else "SAME",
                          relation="HAS_ROLE" if role else "IDENTITY")
    candidates = [{"entity_id": "global:e" + str(i), "path": asdict(path), "profile": profile,
                   "canonical": "정식" + str(i), "aliases": ["나래", "정식" + str(i)],
                   "short_definition": "후보 설명" + str(i), "channel": "abbrev", "transform_cost": 0.0}
                  for i, profile in ((1, "first profile"), (2, "second profile"))]
    return {"case_id": case_id, "document_id": document_id or case_id,
            "family_id": cohort + "-family", "cohort": cohort, "split": cohort,
            "domain": "operations", "source_collection": "occurrence_evidence_" + cohort,
            "text": text, "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "stratum": label or "paraphrase", "target_span": [start, end + int(role)],
            "core_span": [start, end], "expected_entity_id": gold,
            "semantic_label": label or ("LINK" if gold else "NIL"), "target_group_id": group,
            "candidates": candidates}


@pytest.fixture
def unit_cases(monkeypatch):
    monkeypatch.setattr(runner, "validate_cases", lambda cases: cases)

    def select(text, core_span, candidates, *, mode, max_chars):
        allowed = not text.startswith("VETO")
        query = "SELECTED " + mode + " [TARGET]" + text[slice(*core_span)] + "[/TARGET]"
        return Selection(query, ({"start": 0, "end": len(text), "quote": text, "reason": "test_source"},),
                         mode, "SELECTED", allowed, None if allowed else "quoted_or_denied")

    monkeypatch.setattr(runner, "select_evidence", select)
    return [case("correct"), case("wrong", gold="global:e2"),
            case("nil", gold=None, cohort="heldout"),
            case("veto", text="VETO 나래는 예시다.", gold=None, label="NON_MENTION", cohort="heldout"),
            case("role", text="첫쪽 나래장은 작업했다.", gold=None, label="COMPOSITIONAL", role=True)]


def test_predeclared_protocol_keeps_thresholds_and_all_sixteen_comparisons():
    for backend, expected in (("lexical", {"minimum_score": .7, "minimum_margin": .1}),
                              ("nano", {"minimum_score": 0., "minimum_margin": 2.})):
        protocol = runner.frozen_protocol(backend)
        assert protocol["rule"] == expected
        assert protocol["family_alpha_per_comparison"] == .05 / (4 * 2 * 2)
        assert protocol["threshold_fitting_performed"] is False
        assert protocol["production_authorized"] is False


def test_actual_selected_queries_are_scored_with_all_candidates(unit_cases):
    scorer = ProfileScorer()
    result = runner.evaluate(unit_cases, scorer, backend="nano", variants=("target_paragraph",))
    assert scorer.calls and all(query.startswith("SELECTED paragraph") for query, _ in scorer.calls)
    assert {profile for _, profile in scorer.calls} == {"first profile", "second profile"}
    assert result["token_proof"]["validated_pairs"] == len(unit_cases) * 2
    assert sum(group["variants"]["target_paragraph"]["measured_pair_calls"]
               for group in result["cohorts"].values()) == len(unit_cases) * 2
    assert all(row["candidate_count"] == 2 and not row["truncated"] for row in result["rows"])


def test_scoped_inputs_identical_and_veto_only_changes_permission(unit_cases):
    result = runner.evaluate(unit_cases, ProfileScorer(), backend="nano",
                             variants=("scoped_evidence", "scoped_asserted"))
    proof = result["token_proof"]["pairs"]
    for event in unit_cases:
        first = [pair["pair_sha256"] for pair in proof if pair["case_id"] == event["case_id"]
                 and pair["variant"] == "scoped_evidence"]
        second = [pair["pair_sha256"] for pair in proof if pair["case_id"] == event["case_id"]
                  and pair["variant"] == "scoped_asserted"]
        assert first == second
    ungated = next(row for row in result["rows"] if row["case_id"] == "veto" and row["variant"] == "scoped_evidence")
    gated = next(row for row in result["rows"] if row["case_id"] == "veto" and row["variant"] == "scoped_asserted")
    assert ungated["top_score"] == gated["top_score"] == 6
    assert ungated["proposal_selected"] is True
    assert gated["proposal_selected"] is False
    assert gated["assertion_abstain_reason"] == "quoted_or_denied"


def test_structural_role_guard_blocks_every_input_and_high_relevance(unit_cases):
    result = runner.evaluate(unit_cases, ProfileScorer(), backend="nano")
    roles = [row for row in result["rows"] if row["gold_kind"] == "COMPOSITIONAL"]
    assert len(roles) == 4
    assert all(row["top_score"] == 6 and row["score_margin"] == 5 for row in roles)
    assert all(not row["guard_allowed"] and not row["proposal_selected"] for row in roles)
    assert all("typed_derivative" in row["guard_reasons"] for row in roles)
    assert all(not candidate["guard_allowed"] for row in roles for candidate in row["candidates"])


def test_both_cohorts_fully_preflight_before_warmup_even_late_overflow(unit_cases):
    scorer = ProfileScorer()
    scorer.tokenizer = lambda query, profile, **kwargs: {
        "input_ids": [1] * (99 if "scoped" in query else 2)}
    with pytest.raises(ValueError, match="token overflow before inference"):
        runner.evaluate(unit_cases, scorer, backend="nano", max_length=20)
    assert scorer.calls == []


def test_gold_stratum_and_rationale_cannot_change_selected_inputs(unit_cases):
    changed = deepcopy(unit_cases)
    for row in changed:
        row["world_gold"] = {"label": "LINK", "entity_ref": "FAKE GOLD"}
        row["expected_entity_id"], row["semantic_label"] = "FAKE GOLD", "LINK"
        row["decisive_evidence"], row["rationale"], row["stratum"] = ["FAKE GOLD"], "FAKE GOLD", "FAKE GOLD"
    first = runner.preflight_pairs(unit_cases, [runner.hypotheses(row) for row in unit_cases])
    second = runner.preflight_pairs(changed, [runner.hypotheses(row) for row in changed])
    assert first["pairs"] == second["pairs"]
    assert first["selections"] == second["selections"]
    assert first["inputs_sha256"] == second["inputs_sha256"]
    assert "FAKE GOLD" not in json.dumps(first)


def test_ties_abstain_raw_scores_and_one_repeat_not_stability_claim(unit_cases):
    result = runner.evaluate(unit_cases, ConstantScorer(-12.75), backend="nano", variants=("scoped_asserted",))
    assert all(row["top_score"] == -12.75 and row["score_margin"] == 0 and not row["proposal_selected"]
               and row["deterministic"] is None for row in result["rows"])
    assert result["threshold_fitting_performed"] is False
    assert result["coverage_valid"] is False


def test_selection_cost_counts_cache_once_separately_from_pair_cost(unit_cases):
    result = runner.evaluate(unit_cases, ProfileScorer(), backend="nano")
    cost = result["token_proof"]["selection_cost"]
    assert cost["calls"] == len(unit_cases) * 3
    assert cost["excluded_from_batch1_pair_latency"] is True
    assert cost["scoped_selection_cached_across_gate_ablation"] is True
    assert sum(group["calls"] for group in cost["groups"]) == len(unit_cases) * 3
    assert sum(row["mode"] == "scoped" for row in cost["details"]) == len(unit_cases)
    assert all(row["elapsed_ms"] >= 0 for row in cost["details"])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), True])
def test_nonfinite_boolean_scores_rejected(unit_cases, invalid):
    with pytest.raises(ValueError, match="finite raw relevance"):
        runner.evaluate(unit_cases, ConstantScorer(invalid), variants=("target_full",))


def test_threshold_or_alpha_edits_rejected_before_scoring(unit_cases):
    protocol = runner.frozen_protocol("nano")
    scorer = ProfileScorer()
    protocol["frozen_rules"]["nano"]["minimum_margin"] = 0
    with pytest.raises(ValueError, match="frozen rules"):
        runner.evaluate(unit_cases, scorer, backend="nano", protocol=protocol)
    protocol = runner.frozen_protocol("nano")
    protocol["family_alpha_per_comparison"] = .05
    with pytest.raises(ValueError, match="frozen rules"):
        runner.evaluate(unit_cases, scorer, backend="nano", protocol=protocol)
    assert scorer.calls == []


def test_cohort_metrics_do_not_pool_development_and_heldout(unit_cases):
    result = runner.evaluate(unit_cases, ProfileScorer(), backend="nano", variants=("target_full",))
    development = result["cohorts"]["development"]["variants"]["target_full"]
    heldout = result["cohorts"]["heldout"]["variants"]["target_full"]
    assert development["target_cases"] == 3 and heldout["target_cases"] == 2
    assert development["wrong_positive_proposals"] == 1
    assert heldout["wrong_negative_proposals"] == 2
    assert heldout["by_negative_kind"]["NON_MENTION"]["wrong_proposals"] == 1
    assert development["family_risk"]["families_with_proposals"] == 1
    assert heldout["family_risk"]["families_with_any_wrong_proposal"] == 1
    assert heldout["family_risk"]["bound_assumptions_met"] is False


def test_multi_target_document_counts_once_and_requires_both_proposals(unit_cases):
    text = "나래는 첫 작업을 했다.\n\n나래는 두 번째 작업을 했다."
    events = [case("multi::a", document_id="multi", text=text, group="multi"),
              case("multi::b", document_id="multi", text=text, group="multi", occurrence=1, gold="global:e2")]
    result = runner.evaluate(events, ProfileScorer(), backend="nano", variants=("target_full",))
    counts = result["cohorts"]["development"]["variants"]["target_full"]
    assert counts["target_cases"] == 2 and counts["documents"] == 1
    control = counts["multi_target_controls"]
    assert control["groups"] == 1 and control["both_correct_proposals"] == 0
    assert control["different_entity_groups"] == 1 and control["all_inputs_identical"] is False


@pytest.fixture(scope="module")
def development_cases():
    # Only previously inspected development sources are accessed here. Holdout
    # text is intentionally absent from selector-development unit tests.
    return corpus.build_cases(cohort="development")


def test_development_inventory_and_explicit_consumed_status(development_cases):
    assert len(development_cases) == 384
    assert len({case["document_id"] for case in development_cases}) == 336
    assert len({case["family_id"] for case in development_cases}) == 24
    assert all(case["seen_prior_context"] and case["cohort"] == "development" for case in development_cases)
    assert all(len(case["candidates"]) == 2 for case in development_cases)
    assert sum(case["target_group_id"] is not None for case in development_cases) == 96


def test_blind_projection_omits_author_labels_titles_and_order(development_cases):
    projected = corpus.blind_projection(development_cases)
    assert len(projected) == len(development_cases)
    assert projected == sorted(projected, key=lambda row: row["case_id"])
    assert all(set(row) == {"case_id", "document_id", "family_id", "text", "target_surface",
                            "target_occurrence", "target_span", "catalog_terms"} for row in projected)
    binding = corpus.blind_binding_map(development_cases)
    assert set(binding) == {row["case_id"] for row in projected}
    assert set(binding.values()) == {row["case_id"] for row in development_cases}


def test_rehashed_candidate_pruning_and_path_forgery_rejected(development_cases):
    changed = deepcopy(development_cases)
    changed[0]["candidates"] = changed[0]["candidates"][:1]
    changed[0]["candidate_sha256"] = _digest(changed[0]["candidates"])
    with pytest.raises(ValueError, match="complete fixed candidate inventory"):
        corpus.validate_cases(changed)
    changed = deepcopy(development_cases)
    role = next(case for case in changed if case["full_identity"] == "DISTINCT")
    for candidate in role["candidates"]:
        candidate["path"]["full_identity"] = "SAME"
    role["candidate_sha256"] = _digest(role["candidates"])
    with pytest.raises(ValueError, match="actual structural path"):
        corpus.validate_cases(changed)


def test_offset_and_author_annotation_edits_detected(development_cases):
    changed = deepcopy(development_cases)
    changed[0]["target_span"][0] += 1
    with pytest.raises(ValueError, match="occurrence offset"):
        corpus.validate_cases(changed)
    changed = deepcopy(development_cases)
    changed[0]["rationale"] += " changed"
    with pytest.raises(ValueError, match="annotation hash"):
        corpus.validate_cases(changed)


def test_independent_blind_label_changes_do_not_prune_candidates(tmp_path):
    first = json.loads(corpus.DEVELOPMENT_PATH.read_text(encoding="utf-8").splitlines()[0])
    path = tmp_path / "family.jsonl"
    path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")
    original = corpus.build_cases(path, "development", require_inventory=False)
    target = next(target for doc in first["documents"] for target in doc["targets"] if target["gold"]["label"] == "LINK")
    target["gold"] = {"label": "AMBIGUOUS", "entity_ref": None}
    path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")
    corrected = corpus.build_cases(path, "development", require_inventory=False)
    assert [row["candidate_sha256"] for row in original] == [row["candidate_sha256"] for row in corrected]
    assert any(a["semantic_label"] != b["semantic_label"] for a, b in zip(original, corrected))


@pytest.mark.parametrize("field,value", [("review_status", "PENDING"),
                                          ("final_fixture_sha256", "bad"),
                                          ("selector_source_sha256", "bad"),
                                          ("selector_freeze_revision", "")])
def test_cli_rejects_unreviewed_fixture_or_unfrozen_selector_before_scoring(tmp_path, monkeypatch, field, value):
    heldout, annotation = tmp_path / "families.jsonl", tmp_path / "annotation.json"
    heldout.write_bytes(b"heldout fixture\n")
    metadata = {"review_status": "ADJUDICATED_BEFORE_INFERENCE",
                "final_fixture_sha256": hashlib.sha256(heldout.read_bytes()).hexdigest(),
                "selector_source_sha256": hashlib.sha256(runner.SELECTOR_PATH.read_bytes()).hexdigest(),
                "selector_freeze_revision": "frozen-revision"}
    metadata[field] = value
    annotation.write_text(json.dumps(metadata))
    monkeypatch.setattr(sys, "argv", ["evidence", "--heldout", str(heldout), "--annotation-manifest", str(annotation),
                                      "--out", str(tmp_path / "report.json")])
    monkeypatch.setattr(runner, "evaluate", lambda *a, **k: pytest.fail("must reject before scoring"))
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_cli_captures_exact_cases_and_review_bytes_before_inference(unit_cases, tmp_path, monkeypatch):
    development, heldout = tmp_path / "development.jsonl", tmp_path / "heldout.jsonl"
    development.write_bytes(b"development source\n")
    heldout.write_bytes(b"heldout source\n")
    for event in unit_cases:
        source = development if event["cohort"] == "development" else heldout
        event["fixture_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    source, output, annotation = tmp_path / "cases.jsonl", tmp_path / "report.json", tmp_path / "annotation.json"
    payload = b"".join(json.dumps(event, ensure_ascii=False).encode() + b"\n" for event in unit_cases)
    source.write_bytes(payload)
    annotation.write_text(json.dumps({"review_status": "ADJUDICATED_BEFORE_INFERENCE",
                                     "final_fixture_sha256": hashlib.sha256(heldout.read_bytes()).hexdigest(),
                                     "selector_source_sha256": hashlib.sha256(runner.SELECTOR_PATH.read_bytes()).hexdigest(),
                                     "selector_freeze_revision": "frozen-revision"}))
    annotation_bytes = annotation.read_bytes()
    monkeypatch.setattr(runner, "_source_manifest", lambda: {})
    original = runner.evaluate

    def rewrite_after_scoring(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_bytes(b"changed after scoring\n")
        annotation.write_bytes(b"changed after scoring\n")
        return result

    monkeypatch.setattr(runner, "evaluate", rewrite_after_scoring)
    monkeypatch.setattr(sys, "argv", ["evidence", "--cases", str(source), "--development", str(development),
                                      "--heldout", str(heldout), "--annotation-manifest", str(annotation), "--out", str(output)])
    runner.main()
    report = json.loads(output.read_text())
    assert report["cases_sha256"] == hashlib.sha256(payload).hexdigest()
    assert report["annotation_manifest"]["sha256"] == hashlib.sha256(annotation_bytes).hexdigest()
    assert report["annotation_manifest"]["review_status"] == "ADJUDICATED_BEFORE_INFERENCE"
    assert report["threshold_fitting_performed"] is False

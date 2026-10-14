from copy import deepcopy
import math

import pytest

from eval.context_ranking_risk import evaluate_thresholds, predeclared_protocol
from eval.fixed_risk import binomial_error_ucb


def row(case_id, family, partition, *, gold="e1", kind=None, top="e1",
        score=0.8, margin=0.2, guard=True, variant="target_full", collection="original"):
    return {"case_id": case_id, "document_id": case_id, "family_id": family,
            "partition": partition, "gold_entity_id": gold,
            "gold_kind": kind or ("LINK" if gold is not None else "NIL"),
            "top_entity_id": top, "top_score": score, "score_margin": margin,
            "guard_allowed": guard, "variant": variant, "source_collection": collection}


def protocol(scorer="lexical", **kwargs):
    return predeclared_protocol(scorer, ["target_full"], **kwargs)


def lowest(result, partition="tuning_grid"):
    return result["variants"]["target_full"][partition][0]


def test_fixed_protocol_does_not_interpret_raw_logits_as_probabilities():
    lexical, nano = protocol(), protocol("nano")
    assert lexical["minimum_scores"] == [0.0, 0.3, 0.5, 0.7]
    assert nano["minimum_scores"] == [-12.0, -9.0, -6.0, -3.0, 0.0, 3.0]
    assert nano["score_semantics"] == "raw_relevance_not_probability"
    assert nano["data_status"] == "AI_AUTHORED_SYNTHETIC_PREVIOUSLY_EXAMINED"
    assert nano["coverage_valid"] is False
    assert nano["production_authorized"] is False
    result = evaluate_thresholds([row("t", "f01", "tune", score=-5, margin=1)], protocol=nano)
    assert lowest(result)["proposals"] == 1
    assert result["variants"]["target_full"]["tuning_grid"][-1]["proposals"] == 0


def test_negative_proposals_and_wrong_positive_links_are_counted_as_errors():
    rows = [row("right", "f01", "tune"),
            row("wrong-id", "f01", "tune", top="e2"),
            row("nil", "f02", "tune", gold=None),
            row("ambiguous", "f02", "tune", gold=None, kind="AMBIGUOUS"),
            row("test", "f08", "test")]
    result = evaluate_thresholds(rows, protocol=protocol())
    measurement = lowest(result)
    assert measurement["proposals"] == 4
    assert measurement["correct_proposals"] == 1
    assert measurement["wrong_positive_proposals"] == 1
    assert measurement["wrong_negative_proposals"] == 2
    assert measurement["positive_rejections"] == 0
    assert measurement["missed_positive_links"] == 1
    assert measurement["positive_recall"] == 0.5
    assert measurement["observed_error_given_proposal"] == 0.75
    assert measurement["families_with_any_wrong_proposal"] == 2


def test_structural_role_guard_and_exact_score_ties_always_abstain():
    rows = [row("role", "f01", "tune", gold=None, kind="COMPOSITIONAL", guard=False,
                score=100, margin=100),
            row("tie", "f02", "tune", score=100, margin=0),
            row("right", "f03", "tune"), row("test", "f08", "test")]
    result = evaluate_thresholds(rows, protocol=protocol())
    measurement = lowest(result)
    assert measurement["proposals"] == 1
    assert measurement["wrong_proposals"] == 0
    assert measurement["structural_guard_rejections"] == 1
    assert measurement["tie_rejections"] == 1
    assert all(m["proposals"] <= 1 for m in result["variants"]["target_full"]["tuning_grid"])


def test_family_cluster_is_not_replaced_by_eight_independent_documents():
    rows = [row(f"old-{i}", "f01", "tune", collection="document_context") for i in range(4)]
    rows += [row(f"new-{i}", "f01", "tune", collection="context_definitions") for i in range(4)]
    rows += [row("second-family", "f02", "tune"), row("test", "f08", "test")]
    result = evaluate_thresholds(rows, protocol=protocol())
    measured = lowest(result)
    alpha = result["per_stage_variant_rule_alpha"]
    assert measured["documents"] == 9
    assert measured["families_with_proposals"] == 2
    assert measured["family_any_error_ucb"] == pytest.approx(binomial_error_ucb(0, 2, alpha))
    assert measured["family_any_error_ucb"] > binomial_error_ucb(0, 9, alpha)
    assert measured["families_detail"][0] == {"family_id": "f01", "documents": 8,
                                              "proposals": 8, "wrong_proposals": 0}


def test_single_wrong_proposal_marks_whole_family_once():
    rows = [row("a", "f01", "tune"), row("b", "f01", "tune", top="e2"),
            row("c", "f01", "tune", gold=None), row("d", "f02", "tune")]
    measured = lowest(evaluate_thresholds(rows, protocol=protocol()))
    assert measured["wrong_proposals"] == 2
    assert measured["families_with_any_wrong_proposal"] == 1
    assert measured["families_with_proposals"] == 2


def test_small_synthetic_family_sample_cannot_be_certified():
    rows = [row(f"{family}-{i}", family, partition)
            for partition, families in protocol()["family_partition"].items()
            for family in families for i in range(8)]
    result = evaluate_thresholds(rows, protocol=protocol())
    variant = result["variants"]["target_full"]
    assert variant["status"] == "INSUFFICIENT_DATA"
    assert variant["selected_threshold"] is None
    assert variant["exploratory_threshold"] is not None
    assert variant["exploratory_status"] == "UNCERTIFIED_TUNE_ONLY"
    assert result["minimum_zero_error_families_for_bound"] > 4
    assert result["bound_assumptions_met"] is False
    assert result["coverage_valid"] is False
    assert result["production_authorized"] is False


def test_even_a_numerical_bound_met_does_not_authorize_synthetic_results():
    rows = [row("t", "f01", "tune"), row("v", "f08", "test")]
    result = evaluate_thresholds(rows, protocol=protocol(epsilon=0.999))
    variant = result["variants"]["target_full"]
    assert variant["status"] == "DIAGNOSTIC_BOUND_MET"
    assert variant["selected_threshold"] is not None
    assert variant["coverage_valid"] is False
    assert variant["production_authorized"] is False
    assert result["bound_assumptions_met"] is False


def test_test_scores_and_labels_do_not_choose_exploratory_threshold():
    tuning = [row("good", "f01", "tune", score=.8, margin=.2),
              row("low-wrong", "f02", "tune", score=.25, margin=.01, top="e2")]
    original = evaluate_thresholds(tuning + [row("test", "f08", "test")], protocol=protocol())
    changed = evaluate_thresholds(tuning + [row("test", "f08", "test", score=100,
                                                margin=100, gold=None)], protocol=protocol())
    first, second = (result["variants"]["target_full"] for result in (original, changed))
    assert first["selected_threshold"] == second["selected_threshold"]
    assert first["exploratory_threshold"] == second["exploratory_threshold"]
    assert first["exploratory_tuning"] == second["exploratory_tuning"]
    assert first["exploratory_test"]["wrong_proposals"] == 0
    assert second["exploratory_test"]["wrong_proposals"] == 1


def test_simultaneous_alpha_accounts_for_both_stages_variants_and_all_rules():
    declared = predeclared_protocol("nano", ["surface", "target_full"])
    rows = [row("t", "f01", "tune", variant=variant) for variant in declared["variants"]]
    result = evaluate_thresholds(rows, protocol=declared)
    assert result["per_stage_variant_rule_alpha"] == pytest.approx(.05 / (2 * 2 * 30))
    assert len(result["variants"]["surface"]["test_grid"]) == 30


def test_case_field_aliases_preserve_existing_runner_compatibility():
    original = row("t", "f01", "tune")
    aliased = deepcopy(original)
    for preferred, alternate in (("partition", "split"), ("gold_entity_id", "expected_entity_id"),
                                 ("gold_kind", "semantic_label")):
        aliased[alternate] = aliased.pop(preferred)
    assert evaluate_thresholds([original], protocol=protocol()) == evaluate_thresholds(
        [aliased], protocol=protocol())


@pytest.mark.parametrize("key,value", [("top_score", math.nan), ("top_score", math.inf),
                                      ("score_margin", math.inf), ("score_margin", -.1),
                                      ("guard_allowed", 1)])
def test_nonfinite_or_invalid_rank_decisions_rejected(key, value):
    invalid = row("t", "f01", "tune")
    invalid[key] = value
    with pytest.raises(ValueError):
        evaluate_thresholds([invalid], protocol=protocol())


def test_changed_or_nonfinite_predeclared_grid_rejected():
    for mutation in ([-1.0, 0.3, 0.5, 0.7], [math.nan, 0.3, 0.5, 0.7]):
        declared = protocol()
        declared["minimum_scores"] = mutation
        with pytest.raises(ValueError):
            evaluate_thresholds([row("t", "f01", "tune")], protocol=declared)


def test_family_split_overlap_and_wrong_partition_rejected():
    with pytest.raises(ValueError, match="disjoint"):
        protocol(family_partition={"tune": ["f01"], "test": ["f01"]})
    with pytest.raises(ValueError, match="family-disjoint"):
        evaluate_thresholds([row("t", "f01", "test")], protocol=protocol())


def test_same_document_cannot_be_counted_twice_under_different_case_ids():
    first, second = row("a", "f01", "tune"), row("b", "f02", "tune")
    second["document_id"] = first["document_id"]
    with pytest.raises(ValueError, match="duplicate independent"):
        evaluate_thresholds([first, second], protocol=protocol())


def test_variants_require_identical_case_inventories_and_gold():
    declared = predeclared_protocol("lexical", ["surface", "target_full"])
    with pytest.raises(ValueError, match="complete case inventory"):
        evaluate_thresholds([row("t", "f01", "tune", variant="surface")], protocol=declared)
    with pytest.raises(ValueError, match="gold changed"):
        evaluate_thresholds([row("t", "f01", "tune", variant="surface"),
                             row("t", "f01", "tune", gold=None)], protocol=declared)


def test_negative_kind_cannot_retain_positive_entity_gold():
    with pytest.raises(ValueError, match="only a LINK"):
        evaluate_thresholds([row("t", "f01", "tune", kind="AMBIGUOUS")], protocol=protocol())


def test_empty_rows_or_duplicate_variants_cannot_hide_failed_inference():
    with pytest.raises(ValueError, match="nonempty ranking"):
        evaluate_thresholds([], protocol=protocol())
    with pytest.raises(ValueError, match="unique predeclared variants"):
        predeclared_protocol("nano", ["surface", "surface"])

"""Descriptive threshold diagnostics for the authored context-ranking corpus.

Raw relevance scores are not calibrated probabilities. The corpus has already
been examined in earlier experiments, and its labels are AI-authored. A fixed
family partition prevents this experiment's threshold choice from consulting
its test scores; it does not turn these documents into a sealed audit sample.
No result from this module authorizes a resolver commit or execution.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math

from eval.fixed_risk import binomial_error_ucb


VERSION = "context_ranking_risk_v1"
DEFAULT_FAMILY_PARTITION = {
    "tune": ["f05", "f03", "f01", "f02"],
    "test": ["f08", "f06", "f04", "f07"],
}
SCORE_GRIDS = {
    "lexical": {"minimum_scores": [0.0, 0.3, 0.5, 0.7],
                "minimum_margins": [0.0, 0.025, 0.05, 0.1]},
    "nano": {"minimum_scores": [-12.0, -9.0, -6.0, -3.0, 0.0, 3.0],
             "minimum_margins": [0.0, 0.25, 0.5, 1.0, 2.0]},
}
GOLD_KINDS = frozenset({"LINK", "NIL", "AMBIGUOUS", "COMPOSITIONAL", "NON_MENTION"})


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def predeclared_protocol(scorer_id, variants, *, epsilon=0.05, alpha=0.05,
                         minimum_families=1, family_partition=None):
    """Create the protocol before inference, including the scorer-specific grid.

    The alpha budget covers every variant, rule and both partitions. Bounds
    concern a *family having any wrong proposal*, conditional on that family
    having a proposal, rather than error per mention or guaranteed coverage.
    """
    if scorer_id not in SCORE_GRIDS:
        raise ValueError("unknown scorer class for the predeclared raw-score grid")
    protocol = {
        "version": VERSION, "scorer_class": scorer_id, "variants": list(variants),
        **deepcopy(SCORE_GRIDS[scorer_id]), "epsilon": epsilon, "alpha": alpha,
        "minimum_families": minimum_families,
        "family_partition": deepcopy(DEFAULT_FAMILY_PARTITION if family_partition is None
                                     else family_partition),
        "score_semantics": "raw_relevance_not_probability",
        "risk_unit": "family_has_any_wrong_proposal_given_at_least_one_proposal",
        "family_aggregation": "all_documents_across_source_collections",
        "data_status": "AI_AUTHORED_SYNTHETIC_PREVIOUSLY_EXAMINED",
        "test_status": "family_disjoint_diagnostic_partition_not_sealed_audit",
        "selection_status": "threshold_choice_uses_tune_scores_only",
        "coverage_valid": False, "production_authorized": False,
    }
    _validate_protocol(protocol)
    return protocol


def _validate_protocol(protocol):
    if protocol.get("version") != VERSION or protocol.get("scorer_class") not in SCORE_GRIDS:
        raise ValueError("unsupported context-ranking risk protocol")
    variants = protocol.get("variants")
    if (not isinstance(variants, list) or not variants
            or any(not isinstance(v, str) or not v for v in variants)
            or len(set(variants)) != len(variants)):
        raise ValueError("nonempty unique predeclared variants required")
    for name in ("minimum_scores", "minimum_margins"):
        values = protocol.get(name)
        if (not isinstance(values, list) or not values or any(not _finite_number(v) for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("finite unique predeclared threshold grids required")
        if name == "minimum_margins" and any(value < 0 for value in values):
            raise ValueError("a minimum margin cannot be negative")
    # A persisted protocol cannot silently replace its scorer-specific grid.
    if any(protocol[name] != SCORE_GRIDS[protocol["scorer_class"]][name]
           for name in ("minimum_scores", "minimum_margins")):
        raise ValueError("threshold grid differs from the predeclared scorer class")
    if any(not _finite_number(protocol.get(name)) or not 0 < protocol[name] < 1
           for name in ("epsilon", "alpha")):
        raise ValueError("epsilon and alpha must be finite values in (0, 1)")
    minimum = protocol.get("minimum_families")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise ValueError("positive minimum family count required")
    partition = protocol.get("family_partition")
    if not isinstance(partition, dict) or set(partition) != {"tune", "test"}:
        raise ValueError("predeclared tune and test family partitions required")
    for families in partition.values():
        if (not isinstance(families, list) or not families
                or any(not isinstance(f, str) or not f for f in families)
                or len(set(families)) != len(families)):
            raise ValueError("unique identified families required in each partition")
    if set(partition["tune"]) & set(partition["test"]):
        raise ValueError("tuning and test families must be disjoint")
    if protocol.get("coverage_valid") is not False or protocol.get("production_authorized") is not False:
        raise ValueError("this authored-corpus diagnostic cannot authorize production")


def _field(row, preferred, alternate):
    if preferred in row and alternate in row and row[preferred] != row[alternate]:
        raise ValueError("inconsistent duplicate row metadata")
    if preferred in row:
        return row[preferred]
    if alternate in row:
        return row[alternate]
    raise ValueError("missing ranking row metadata: " + preferred)


def _validate_rows(rows, protocol):
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty ranking rows required")
    normalized, seen, identity, inventories = [], set(), {}, defaultdict(set)
    for source in rows:
        row = dict(source)
        row["partition"] = _field(row, "partition", "split")
        row["gold_entity_id"] = _field(row, "gold_entity_id", "expected_entity_id")
        row["gold_kind"] = _field(row, "gold_kind", "semantic_label")
        if row.get("variant") not in protocol["variants"]:
            raise ValueError("row variant outside the predeclared protocol")
        for key in ("case_id", "document_id", "family_id", "top_entity_id"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError("identified ranking rows and top candidate required")
        partition = row["partition"]
        if (partition not in {"tune", "test"}
                or row["family_id"] not in protocol["family_partition"][partition]):
            raise ValueError("row violates the predeclared family-disjoint partition")
        if (row["gold_kind"] not in GOLD_KINDS
                or (row["gold_kind"] == "LINK") != (isinstance(row["gold_entity_id"], str)
                                                      and bool(row["gold_entity_id"]))
                or (row["gold_kind"] != "LINK" and row["gold_entity_id"] is not None)):
            raise ValueError("only a LINK label can have an expected entity")
        if (not _finite_number(row.get("top_score"))
                or not _finite_number(row.get("score_margin")) or row["score_margin"] < 0):
            raise ValueError("finite raw scores and a nonnegative ordered margin required")
        if not isinstance(row.get("guard_allowed"), bool):
            raise ValueError("structural guard decision must be binary")
        key = (row["variant"], row["case_id"])
        if key in seen:
            raise ValueError("duplicate case within a ranking variant")
        seen.add(key)
        metadata = tuple(row[name] for name in ("document_id", "family_id", "partition",
                                                "gold_kind", "gold_entity_id"))
        if row["case_id"] in identity and identity[row["case_id"]] != metadata:
            raise ValueError("case identity or gold changed across ranking variants")
        identity[row["case_id"]] = metadata
        inventories[row["variant"]].add(row["case_id"])
        normalized.append(row)
    if set(inventories) != set(protocol["variants"]) or any(
            inventory != inventories[protocol["variants"][0]] for inventory in inventories.values()):
        raise ValueError("every variant must score the same complete case inventory")
    # Different case IDs cannot hide the same document or move it to a new family.
    document_cases = {}
    for case_id, metadata in identity.items():
        document_id = metadata[0]
        if document_id in document_cases and document_cases[document_id] != case_id:
            raise ValueError("a document cannot contribute duplicate independent cases")
        document_cases[document_id] = case_id
    return normalized


def _measure(rows, threshold, alpha):
    selected = [row for row in rows if row["guard_allowed"] and row["score_margin"] > 0
                and row["score_margin"] >= threshold["minimum_margin"]
                and row["top_score"] >= threshold["minimum_score"]]
    correct = [row for row in selected if row["gold_entity_id"] is not None
               and row["top_entity_id"] == row["gold_entity_id"]]
    wrong = [row for row in selected if row["gold_entity_id"] is None
             or row["top_entity_id"] != row["gold_entity_id"]]
    selected_families = {row["family_id"] for row in selected}
    wrong_families = {row["family_id"] for row in wrong}
    positives = sum(row["gold_entity_id"] is not None for row in rows)
    counts = {
        "documents": len(rows), "families": len({row["family_id"] for row in rows}),
        "positive_documents": positives, "negative_documents": len(rows) - positives,
        "proposals": len(selected), "correct_proposals": len(correct), "wrong_proposals": len(wrong),
        "wrong_positive_proposals": sum(row["gold_entity_id"] is not None for row in wrong),
        "wrong_negative_proposals": sum(row["gold_entity_id"] is None for row in wrong),
        "positive_rejections": positives - sum(row["gold_entity_id"] is not None for row in selected),
        "missed_positive_links": positives - len(correct),
        "proposal_rate": len(selected) / len(rows) if rows else None,
        "positive_recall": len(correct) / positives if positives else None,
        "observed_error_given_proposal": len(wrong) / len(selected) if selected else None,
        "families_with_proposals": len(selected_families),
        "families_with_any_wrong_proposal": len(wrong_families),
        "family_any_error_ucb": binomial_error_ucb(len(wrong_families), len(selected_families), alpha),
        "family_alpha": alpha,
        "structural_guard_rejections": sum(not row["guard_allowed"] for row in rows),
        "tie_rejections": sum(row["score_margin"] == 0 for row in rows),
    }
    counts["families_detail"] = [{
        "family_id": family,
        "documents": sum(row["family_id"] == family for row in rows),
        "proposals": sum(row["family_id"] == family for row in selected),
        "wrong_proposals": sum(row["family_id"] == family for row in wrong),
    } for family in sorted({row["family_id"] for row in rows})]
    return counts


def evaluate_thresholds(rows, *, protocol):
    """Evaluate frozen rules and select only from the tuning partition.

    Test-grid measurements are descriptive comparisons of predeclared rules;
    they never choose an exploratory threshold. The exact binomial family UCB
    is a diagnostic that would require exchangeable, independently sampled
    families to justify a population claim. This synthetic set supplies no
    deployment guarantee, even if a numerical diagnostic bound is small.
    """
    _validate_protocol(protocol)
    rows = _validate_rows(rows, protocol)
    rules = [{"minimum_score": score, "minimum_margin": margin}
             for score in protocol["minimum_scores"] for margin in protocol["minimum_margins"]]
    per_alpha = protocol["alpha"] / (2 * len(protocol["variants"]) * len(rules))
    result = {
        "protocol": deepcopy(protocol), "coverage_valid": False, "production_authorized": False,
        "risk_interpretation": "descriptive_family_cluster_diagnostic_only",
        "bound_assumptions_met": False, "per_stage_variant_rule_alpha": per_alpha,
        "minimum_zero_error_families_for_bound": math.ceil(
            math.log(per_alpha) / math.log1p(-protocol["epsilon"])),
        "variants": {},
    }
    for variant in protocol["variants"]:
        subset = [row for row in rows if row["variant"] == variant]
        tune = [row for row in subset if row["partition"] == "tune"]
        test = [row for row in subset if row["partition"] == "test"]
        tuning = [{"threshold": rule, **_measure(tune, rule, per_alpha)} for rule in rules]
        testing = [{"threshold": rule, **_measure(test, rule, per_alpha)} for rule in rules]
        eligible = [measurement for measurement in tuning
                    if measurement["families_with_proposals"] >= protocol["minimum_families"]
                    and measurement["family_any_error_ucb"] <= protocol["epsilon"]]
        preference = lambda m: (m["proposals"], m["threshold"]["minimum_score"],
                                m["threshold"]["minimum_margin"])
        selected = max(eligible, key=preference) if eligible else None
        exploratory = None
        if selected is None:
            error_free = [m for m in tuning if m["wrong_proposals"] == 0 and m["proposals"] > 0]
            exploratory = max(error_free, key=preference) if error_free else None
        selected_test = next((m for m in testing if selected is not None
                              and m["threshold"] == selected["threshold"]), None)
        bound_met = selected_test is not None and (
            selected_test["families_with_proposals"] >= protocol["minimum_families"]
            and selected_test["family_any_error_ucb"] <= protocol["epsilon"])
        result["variants"][variant] = {
            "status": "DIAGNOSTIC_BOUND_MET" if bound_met else "INSUFFICIENT_DATA",
            "selected_threshold": deepcopy(selected["threshold"]) if selected else None,
            "selected_tuning": selected, "selected_test": selected_test,
            "exploratory_threshold": deepcopy(exploratory["threshold"]) if exploratory else None,
            "exploratory_status": "UNCERTIFIED_TUNE_ONLY" if exploratory else "NONE",
            "exploratory_tuning": exploratory,
            "exploratory_test": next((m for m in testing if exploratory is not None
                                      and m["threshold"] == exploratory["threshold"]), None),
            "tuning_grid": tuning, "test_grid": testing,
            "coverage_valid": False, "production_authorized": False,
        }
    return result

"""Evaluate frozen ranking rules on new authored families without refitting.

All four input variants see the complete two-entity family catalog. Every
actual model input is checked without truncation before the first score call.
Scores and proposals are diagnostics; existing production guards retain all
execution authority.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from importlib import metadata
import os
from pathlib import Path
import platform
import resource
import statistics

from eval.context_ranking_challenge import build_cases, hypotheses, validate_cases
from eval.fixed_risk import binomial_error_ucb
from eval.run_context_ranking import (
    BatchOne, StrictLocalScalarScorer, _digest, _identity, _json_bytes,
    _percentile, _ranked_payload, _runtime_provenance, _token_count,
)
from eval.run_rerank_ablation import model_digest
from ktrf.rerank import LexicalCrossEncoder, rank_hypotheses, rerank_query

INPUT_VARIANTS = ("surface", "target_local", "context_full", "target_full")
FROZEN_RULES = {
    "lexical": {"minimum_score": 0.7, "minimum_margin": 0.1},
    "nano": {"minimum_score": 0.0, "minimum_margin": 2.0},
}
PRIOR_REPORT_DIR = Path(__file__).parent.parent / "reports" / "context_ranking_20261014T103421Z"
PROTOCOL_PATH = Path(__file__).parent / "fixtures" / "context_ranking_challenge" / "protocol.json"


def frozen_protocol(backend, *, prior_report=None, protocol_path=PROTOCOL_PATH):
    """Copy the old target_full tune-only rule, never inspect new scores."""
    if backend not in FROZEN_RULES:
        raise ValueError("unknown frozen scoring backend")
    declared_payload = Path(protocol_path).read_bytes()
    declared = json.loads(declared_payload)
    if (declared.get("protocol_id") != "context-ranking-challenge-v1"
            or declared.get("variants") != list(INPUT_VARIANTS)
            or declared.get("frozen_rules") != FROZEN_RULES
            or declared.get("candidate_budget") != 2 or declared.get("local_radius") != 60
            or declared.get("maximum_pair_tokens") != 1024 or declared.get("repeats") != 1
            or declared.get("familywise_alpha") != .05
            or declared.get("family_alpha_per_comparison") != .05 / 8
            or declared.get("bound_assumptions_met") is not False
            or declared.get("coverage_valid") is not False
            or declared.get("production_authorized") is not False):
        raise ValueError("declared challenge protocol differs from the frozen comparison")
    path = Path(prior_report) if prior_report is not None else PRIOR_REPORT_DIR / (backend + ".json")
    payload = path.read_bytes()
    prior = json.loads(payload)
    rule = prior["risk"]["variants"]["target_full"]["exploratory_threshold"]
    if rule != FROZEN_RULES[backend]:
        raise ValueError("prior tune-only rule differs from the frozen challenge rule")
    if hashlib.sha256(payload).hexdigest() != declared["prior_report_sha256"][backend]:
        raise ValueError("prior report bytes differ from the predeclared report identity")
    return {
        "version": "context_ranking_challenge_fixed_rules_v1", "backend": backend,
        "variants": list(INPUT_VARIANTS), "rule": deepcopy(rule),
        "prior_report": str(path.relative_to(Path(__file__).parent.parent))
        if path.is_relative_to(Path(__file__).parent.parent) else str(path),
        "prior_report_sha256": hashlib.sha256(payload).hexdigest(),
        "declared_protocol": declared,
        "declared_protocol_file_sha256": hashlib.sha256(declared_payload).hexdigest(),
        "prior_rule_variant": "target_full",
        "prior_selection": "UNCERTIFIED_TUNE_ONLY",
        "selection_status": "FROZEN_BEFORE_NEW_CORPUS_INFERENCE_NO_THRESHOLD_SEARCH",
        "score_semantics": "raw_relevance_not_probability",
        "require_structural_guard": True, "require_strictly_positive_margin": True,
        "alpha": 0.05, "family_alpha": 0.05 / (4 * 2), "epsilon": 0.05,
        "simultaneous_comparisons": "four_predeclared_variants_times_two_backends",
        "risk_unit": "family_has_any_wrong_proposal_given_at_least_one_proposal",
        "family_aggregation": "all_documents_and_targets_in_each_family",
        "independent_sampling_assumptions_met": False,
        "data_status": "NEW_AI_AUTHORED_SYNTHETIC_NOT_HUMAN_VERIFIED",
        "production_authorized": False, "coverage_valid": False,
    }


def _validate_protocol(protocol):
    backend = protocol.get("backend")
    if (protocol.get("version") != "context_ranking_challenge_fixed_rules_v1"
            or backend not in FROZEN_RULES or protocol.get("rule") != FROZEN_RULES[backend]
            or protocol.get("variants") != list(INPUT_VARIANTS)
            or protocol.get("family_alpha") != .05 / 8
            or protocol.get("alpha") != .05 or protocol.get("epsilon") != .05
            or protocol.get("require_structural_guard") is not True
            or protocol.get("require_strictly_positive_margin") is not True
            or protocol.get("independent_sampling_assumptions_met") is not False
            or protocol.get("production_authorized") is not False
            or protocol.get("coverage_valid") is not False):
        raise ValueError("challenge protocol must preserve frozen rules and diagnostic scope")


def _variant_settings(variant, text):
    settings = {"surface": ("surface", 60), "target_local": ("target", 60),
                "context_full": ("context", len(text)), "target_full": ("target", len(text))}
    if variant not in settings:
        raise ValueError("unknown challenge input variant: " + str(variant))
    return settings[variant]


def _pairs(case, shortlist, variant):
    query_variant, radius = _variant_settings(variant, case["text"])
    return [(rerank_query(case["text"], h.path.core_span, query_variant, h.path, radius), h.profile)
            for h in shortlist]


def preflight_pairs(cases, fixed, *, variants=INPUT_VARIANTS, tokenizer=None, max_length=None):
    """Reject even a later-format overflow before warmup or inference."""
    if tokenizer is not None and (type(max_length) is not int or max_length < 1):
        raise ValueError("tokenized preflight requires a positive max_length")
    if len(cases) != len(fixed):
        raise ValueError("every case requires its complete fixed shortlist")
    rows = []
    for variant in variants:
        for case, shortlist in zip(cases, fixed):
            for h, pair in zip(shortlist, _pairs(case, shortlist, variant)):
                count = _token_count(tokenizer, pair) if tokenizer is not None else None
                if count is not None and count > max_length:
                    raise ValueError(f"token overflow before inference: {case['case_id']} "
                                     f"{variant} {h.entity_id}: {count} > {max_length}")
                rows.append({"variant": variant, "case_id": case["case_id"],
                             "document_id": case["document_id"], "entity_id": h.entity_id,
                             "query": pair[0], "profile": pair[1], "pair_sha256": _digest(pair),
                             "token_count": count, "query_characters": len(pair[0]),
                             "profile_characters": len(pair[1])})
    counts = [r["token_count"] for r in rows if r["token_count"] is not None]
    return {"truncation": False, "tokenizer_checked": tokenizer is not None,
            "max_length": max_length if tokenizer is not None else None,
            "validated_pairs": len(rows), "maximum_pair_tokens": max(counts) if counts else None,
            "inputs_sha256": _digest(rows), "pairs": rows}


def _propose(row, rule):
    score, margin = row["top_score"], row["score_margin"]
    if (isinstance(score, bool) or isinstance(margin, bool)
            or not math.isfinite(score) or not math.isfinite(margin) or margin < 0):
        raise ValueError("proposal requires finite raw scores and nonnegative margin")
    return bool(row["guard_allowed"] and margin > 0
                and margin >= rule["minimum_margin"] and score >= rule["minimum_score"])


def _measure(rows):
    positives = [r for r in rows if r["gold_kind"] == "LINK"]
    selected = [r for r in rows if r["proposal_selected"]]
    correct = [r for r in selected if r["top1_exact_link"]]
    wrong = [r for r in selected if not r["top1_exact_link"]]
    return {
        "target_cases": len(rows), "documents": len({r["document_id"] for r in rows}),
        "families": len({r["family_id"] for r in rows}), "positive_cases": len(positives),
        "negative_cases": len(rows) - len(positives),
        "exact_link_top1_count": sum(r["top1_exact_link"] for r in positives),
        "exact_link_top1": statistics.mean(r["top1_exact_link"] for r in positives) if positives else None,
        "proposals": len(selected), "correct_proposals": len(correct), "wrong_proposals": len(wrong),
        "wrong_positive_proposals": sum(r["gold_kind"] == "LINK" for r in wrong),
        "wrong_negative_proposals": sum(r["gold_kind"] != "LINK" for r in wrong),
        "positive_proposal_recall": len(correct) / len(positives) if positives else None,
        "observed_error_given_proposal": len(wrong) / len(selected) if selected else None,
        "structural_guard_rejections": sum(not r["guard_allowed"] for r in rows),
        "tie_rejections": sum(r["score_margin"] == 0 for r in rows),
    }


def _groups(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return {str(name): _measure(group) for name, group in sorted(grouped.items(), key=lambda item: str(item[0]))}


def _family_risk(rows, protocol):
    selected = [r for r in rows if r["proposal_selected"]]
    proposed = {r["family_id"] for r in selected}
    wrong = {r["family_id"] for r in selected if not r["top1_exact_link"]}
    upper = binomial_error_ucb(len(wrong), len(proposed), protocol["family_alpha"])
    return {"interpretation": "DESCRIPTIVE_FAMILY_CLUSTER_DIAGNOSTIC_ONLY",
            "families_with_proposals": len(proposed), "families_with_any_wrong_proposal": len(wrong),
            "family_any_error_ucb": upper, "family_alpha": protocol["family_alpha"],
            "epsilon": protocol["epsilon"], "numerical_bound_met": upper <= protocol["epsilon"],
            "bound_assumptions_met": False, "coverage_valid": False, "production_authorized": False,
            "status": "UNCERTIFIED_SYNTHETIC_EXTERNAL_TEST",
            "families_detail": [{"family_id": name, **counts} for name, counts in _groups(rows, "family_id").items()]}


def _target_groups(rows, proof_pairs):
    groups = defaultdict(list)
    for row in rows:
        if row.get("target_group_id") is not None:
            groups[row["target_group_id"]].append(row)
    input_map = defaultdict(dict)
    for pair in proof_pairs:
        input_map[pair["case_id"]][pair["entity_id"]] = pair["pair_sha256"]
    detail = []
    for group_id, group in sorted(groups.items()):
        if len(group) != 2 or len({r["document_id"] for r in group}) != 1:
            raise ValueError("a multi-target control must contain exactly two targets from one document")
        first, second = group
        inputs_identical = input_map[first["case_id"]] == input_map[second["case_id"]]
        scores_identical = ({c["entity_id"]: c["score"] for c in first["candidates"]}
                            == {c["entity_id"]: c["score"] for c in second["candidates"]})
        expected_different = bool(first["gold_entity_id"] and second["gold_entity_id"]
                                  and first["gold_entity_id"] != second["gold_entity_id"])
        detail.append({"target_group_id": group_id, "case_ids": [r["case_id"] for r in group],
                       "both_top1_correct": all(r["top1_exact_link"] for r in group),
                       "both_correct_proposals": all(r["proposal_selected"] and r["top1_exact_link"] for r in group),
                       "expected_different_entities": expected_different,
                       "top_entity_changed": first["top_entity_id"] != second["top_entity_id"],
                       "inputs_identical": inputs_identical, "scores_identical": scores_identical})
    return {"groups": len(detail), "both_top1_correct": sum(r["both_top1_correct"] for r in detail),
            "both_correct_proposals": sum(r["both_correct_proposals"] for r in detail),
            "different_entity_groups": sum(r["expected_different_entities"] for r in detail),
            "different_entity_top_changed": sum(r["expected_different_entities"] and r["top_entity_changed"] for r in detail),
            "all_inputs_identical": all(r["inputs_identical"] for r in detail) if detail else None,
            "all_scores_identical": all(r["scores_identical"] for r in detail) if detail else None,
            "details": detail}


def evaluate(cases, scorer, *, backend="lexical", repeats=1, variants=INPUT_VARIANTS,
             max_length=None, protocol=None):
    validate_cases(cases)
    if type(repeats) is not int or repeats < 1 or not variants or len(set(variants)) != len(variants):
        raise ValueError("positive repeats and unique nonempty variants required")
    for variant in variants:
        _variant_settings(variant, "")
    protocol = frozen_protocol(backend) if protocol is None else deepcopy(protocol)
    _validate_protocol(protocol)
    if protocol["backend"] != backend:
        raise ValueError("frozen rule backend must match the scorer")
    protocol_hash = _digest(protocol)
    fixed = [hypotheses(case) for case in cases]
    if any(len(shortlist) != 2 for shortlist in fixed):
        raise ValueError("every case must retain both registered family candidates")
    proof = preflight_pairs(cases, fixed, variants=variants,
                            tokenizer=getattr(scorer, "tokenizer", None), max_length=max_length)
    results, rows = {}, []
    for variant in variants:
        query_variant, _ = _variant_settings(variant, "")
        for pair in _pairs(cases[0], fixed[0], variant):
            scorer.score_pairs([pair])
        getattr(scorer, "synchronize", lambda: None)()
        timed, variant_rows = BatchOne(scorer), []
        for case, shortlist in zip(cases, fixed):
            _, radius = _variant_settings(variant, case["text"])
            runs = [rank_hypotheses(case["text"], shortlist, timed, query_variant, radius=radius)
                    for _ in range(repeats)]
            ranked, gold = runs[0], case["expected_entity_id"]
            top = ranked[0]
            stable = (all([(_identity(r.hypothesis), r.score) for r in run]
                          == [(_identity(r.hypothesis), r.score) for r in ranked] for run in runs)
                      if repeats > 1 else None)
            correct = bool(gold and top.hypothesis.entity_id == gold
                           and top.hypothesis.path.core_span == tuple(case["core_span"])
                           and top.hypothesis.path.full_identity == "SAME")
            row = {"variant": variant, "case_id": case["case_id"], "document_id": case["document_id"],
                   "family_id": case["family_id"], "partition": case["split"],
                   "domain": case.get("domain"), "source_collection": case["source_collection"],
                   "document_sha256": case["document_sha256"], "stratum": case["stratum"],
                   "target_group_id": case.get("target_group_id"),
                   "gold_entity_id": gold, "gold_kind": case["semantic_label"],
                   "target_span": case["target_span"], "core_span": case["core_span"],
                   "candidate_count": 2, "total_candidate_count": 2, "truncated": False,
                   "top_entity_id": top.hypothesis.entity_id, "top_score": top.score,
                   "score_margin": top.score - ranked[1].score,
                   "guard_allowed": top.commit_allowed, "guard_reasons": list(top.guard_reasons),
                   "top1_exact_link": correct,
                   "gold_in_shortlist": bool(gold and any(h.entity_id == gold
                        and h.path.core_span == tuple(case["core_span"]) and h.path.full_identity == "SAME"
                        for h in shortlist)),
                   "deterministic": stable if repeats > 1 else None,
                   "repetition_stability_checked": repeats > 1,
                   "production_authorized": False, "coverage_valid": False,
                   "candidates": _ranked_payload(ranked)}
            row["proposal_selected"] = _propose(row, protocol["rule"])
            row["proposal_entity_id"] = row["top_entity_id"] if row["proposal_selected"] else None
            variant_rows.append(row)
            rows.append(row)
        positives = [r for r in variant_rows if r["gold_kind"] == "LINK"]
        family_positive = defaultdict(list)
        for row in positives:
            family_positive[row["family_id"]].append(row["top1_exact_link"])
        token_pairs = [p for p in proof["pairs"] if p["variant"] == variant]
        controls = _target_groups(variant_rows, token_pairs)
        if variant == "context_full" and controls["groups"] and not controls["all_inputs_identical"]:
            raise ValueError("unmarked full-document controls must have identical actual pair inputs")
        results[variant] = {
            **_measure(variant_rows), "family_macro_top1": statistics.mean(
                statistics.mean(v) for v in family_positive.values()) if family_positive else None,
            "candidate_exact_link_recall": statistics.mean(r["gold_in_shortlist"] for r in positives)
            if positives else None,
            "mean_candidate_count": 2,
            "maximum_pair_tokens": max((p["token_count"] for p in token_pairs
                                        if p["token_count"] is not None), default=None),
            "batch1_pair_p50_ms": _percentile(timed.latencies_ms, .5),
            "batch1_pair_p95_ms": _percentile(timed.latencies_ms, .95),
            "batch1_pair_p99_ms": _percentile(timed.latencies_ms, .99),
            "measured_pair_calls": len(timed.latencies_ms),
            "repetition_stability_checked": repeats > 1,
            "all_scores_repeat_stable": all(r["deterministic"] for r in variant_rows)
            if repeats > 1 else None,
            "by_stratum": _groups(variant_rows, "stratum"), "by_domain": _groups(variant_rows, "domain"),
            "by_family": _groups(variant_rows, "family_id"),
            "family_risk": _family_risk(variant_rows, protocol), "multi_target_controls": controls,
            "cases": variant_rows,
        }
    if _digest(protocol) != protocol_hash:
        raise ValueError("frozen protocol changed during scoring")
    return {"variants": results, "rows": rows, "token_proof": proof,
            "frozen_protocol": protocol, "frozen_protocol_sha256": protocol_hash,
            "production_authorized": False, "coverage_valid": False,
            "independent_sampling_assumptions_met": False, "threshold_fitting_performed": False}


def _source_manifest():
    root = Path(__file__).resolve().parents[1]
    paths = ("eval/run_context_ranking_challenge.py", "eval/context_ranking_challenge.py",
             "eval/build_context_ranking_challenge.py", "eval/context_ranking_corpus.py",
             "eval/run_context_ranking.py", "eval/run_rerank_ablation.py", "eval/fixed_risk.py",
             "ktrf/rerank.py", "ktrf/segmentation.py")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def render_report(report):
    rule = report["frozen_protocol"]["rule"]
    lines = ["# New-family target/context ranking challenge", "",
             "AI-authored out-of-sample synthetic evaluation; no threshold refitting or production authorization.", "",
             f"Backend: `{report['backend']}`; frozen minimum score `{rule['minimum_score']}` "
             f"and minimum margin `{rule['minimum_margin']}` (strictly positive margin and existing structural guard required).",
             f"Corpus SHA-256: `{report['cases_sha256']}`.",
             f"Frozen protocol SHA-256: `{report['frozen_protocol_sha256']}`.", "",
             "| Input | Positive top-1 | Correct proposals | Wrong proposals | Negative errors | Pair p95 ms |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, result in report["variants"].items():
        lines.append(f"| {name} | {result['exact_link_top1_count']}/{result['positive_cases']} "
                     f"| {result['correct_proposals']} | {result['wrong_proposals']} "
                     f"| {result['wrong_negative_proposals']} | {result['batch1_pair_p95_ms']:.3f} |")
    lines.extend(["", "Multiple target cases from one document are not independent samples. Risk diagnostics",
                  "aggregate every document and target within its entity family; the alpha budget covers",
                  "four input variants and two scoring backends. Synthetic authoring does not satisfy",
                  "independent deployment-sampling assumptions, even if a numerical bound is small.",
                  "The JSON retains all scores, guards, actual input pairs, token counts and target-pair controls.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--annotation-manifest", type=Path,
                        default=PROTOCOL_PATH.parent / "annotation_manifest.json")
    parser.add_argument("--backend", choices=("lexical", "scalar"), default="lexical")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model-id")
    parser.add_argument("--model-revision")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--source-revision", default=os.environ.get("KTRF_CODE_REVISION"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.max_length < 1 or args.repeats < 1:
        parser.error("max-length and repeats must be positive")
    if args.backend == "scalar" and (args.model_dir is None or not args.model_dir.is_dir()
                                     or not args.model_id or not args.model_revision):
        parser.error("scalar backend requires local model-dir and pinned model-id/model-revision")
    if args.cases is not None:
        payload = args.cases.read_bytes()
        cases = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    else:
        cases = build_cases()
        payload = b"".join(_json_bytes(case) + b"\n" for case in cases)
    validate_cases(cases)
    protocol = frozen_protocol("lexical" if args.backend == "lexical" else "nano",
                               protocol_path=args.protocol)
    declared = protocol["declared_protocol"]
    if args.max_length != declared["maximum_pair_tokens"] or args.repeats != declared["repeats"]:
        parser.error("max-length and repeats must match the frozen protocol")
    if args.backend == "scalar" and (args.model_id != declared["model_id"]
                                     or args.model_revision != declared["model_revision"]):
        parser.error("model-id and revision must match the frozen protocol")
    digest = model_digest(args.model_dir) if args.backend == "scalar" else None
    if digest is not None and digest != declared["expected_model_sha256"]:
        parser.error("model files differ from the frozen weight identity")
    annotation_payload = args.annotation_manifest.read_bytes()
    annotation_value = json.loads(annotation_payload)
    if annotation_value.get("review_status") != "ADJUDICATED_BEFORE_INFERENCE":
        parser.error("annotation manifest must record adjudication before inference")
    fixture_path = PROTOCOL_PATH.parent / "families.jsonl"
    if annotation_value.get("final_fixture_sha256") != hashlib.sha256(fixture_path.read_bytes()).hexdigest():
        parser.error("annotation manifest must identify the actual final source fixture")
    if {case.get("fixture_sha256") for case in cases} != {annotation_value["final_fixture_sha256"]}:
        parser.error("frozen cases must identify the adjudicated final source fixture")
    annotation = {"path": str(args.annotation_manifest),
                  "sha256": hashlib.sha256(annotation_payload).hexdigest(),
                  "review_status": annotation_value["review_status"],
                  "final_fixture_sha256": annotation_value["final_fixture_sha256"]}
    sources = _source_manifest()
    scorer = LexicalCrossEncoder() if args.backend == "lexical" else StrictLocalScalarScorer(
        args.model_dir, args.max_length, args.device)
    if args.backend == "scalar" and str(args.device).startswith("cuda"):
        scorer.torch.cuda.reset_peak_memory_stats(scorer.device)
    result = evaluate(cases, scorer, backend=protocol["backend"], repeats=args.repeats,
                      max_length=args.max_length, protocol=protocol)
    packages = {}
    for package in ("torch", "transformers", "tokenizers"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    report = {"schema_version": 1, "task": "new_family_context_ranking_challenge",
              "measured_at": datetime.now(timezone.utc).isoformat(),
              "cases_sha256": hashlib.sha256(payload).hexdigest(), "source_revision": args.source_revision,
              "source_files": sources, "backend": args.backend, "scorer_id": scorer.reranker_id,
              "model_id": args.model_id, "model_revision": args.model_revision,
              "model_sha256": digest, "annotation_manifest": annotation,
              "protocol_file_sha256": protocol["declared_protocol_file_sha256"],
              "fixture_files": {str(path.relative_to(Path(__file__).parent.parent)):
                                hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sorted((Path(__file__).parent / "fixtures" /
                                                    "context_ranking_challenge").glob("*.json*"))},
              "runtime": _runtime_provenance(scorer), "packages": packages, "device": args.device,
              "python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "omp_threads": os.environ.get("OMP_NUM_THREADS"), "mkl_threads": os.environ.get("MKL_NUM_THREADS"),
              "batch_size": 1, "repeats": args.repeats,
              "max_length": args.max_length if args.backend == "scalar" else None,
              "warmup_measured": False, "candidate_budget": 2, "calibration_status": "INSUFFICIENT_DATA",
              "limitations": ["New AI-authored documents do not constitute an independent human audit.",
                              "Raw relevance and frozen proposals are not probabilities or execution authority.",
                              "Target cases cluster within documents and families; no mention-level risk guarantee.",
                              "Candidate recall is controlled; actual retrieval and end-to-end utility are not measured."],
              **result}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    args.out.with_suffix(".md").write_text(render_report(report))


if __name__ == "__main__":
    main()

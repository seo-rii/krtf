"""Compare occurrence evidence selection and an assertion veto, with fixed rules.

Both cohorts and every actual pair are checked before warmup. Custom evidence
queries are scored directly; production structural guards remain separate from
the experimental assertion veto. No score is a probability or execution grant.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import resource
import statistics
import time

from eval.fixed_risk import binomial_error_ucb
from eval.occurrence_evidence_corpus import (
    DEVELOPMENT_PATH, HELDOUT_PATH, INVENTORIES, build_cases, hypotheses, validate_cases,
)
from eval.run_context_ranking import (
    BatchOne, StrictLocalScalarScorer, _digest, _identity, _json_bytes, _percentile,
    _ranked_payload, _runtime_provenance, _token_count,
)
from eval.run_context_ranking_challenge import FROZEN_RULES, PRIOR_REPORT_DIR, _groups, _measure, _target_groups
from eval.run_rerank_ablation import model_digest
from ktrf.occurrence_evidence import select_evidence
from ktrf.rerank import LexicalCrossEncoder, RankedHypothesis, rerank_query
from ktrf.segmentation import MatchEvidence, ResolutionGuard

INPUT_VARIANTS = ("target_full", "target_paragraph", "scoped_evidence", "scoped_asserted")
PROTOCOL_PATH = HELDOUT_PATH.parent / "protocol.json"
SELECTOR_PATH = Path(__file__).resolve().parents[1] / "ktrf" / "occurrence_evidence.py"


def _validate_protocol(protocol):
    if (protocol.get("protocol_id") != "occurrence-evidence-v1"
            or protocol.get("variants") != list(INPUT_VARIANTS)
            or set(protocol.get("cohorts", {})) != set(INVENTORIES)
            or protocol.get("frozen_rules") != FROZEN_RULES
            or protocol.get("candidate_budget") != 2
            or protocol.get("maximum_pair_tokens") != 1024
            or protocol.get("selection_max_chars") != 1024
            or protocol.get("repeats") != 1 or protocol.get("backends") != ["lexical", "nano"]
            or protocol.get("familywise_alpha") != .05
            or protocol.get("family_alpha_per_comparison") != .05 / 16
            or protocol.get("coverage_valid") is not False
            or protocol.get("production_authorized") is not False
            or protocol.get("bound_assumptions_met") is not False
            or protocol.get("threshold_fitting_performed") is not False
            or protocol.get("selector_freeze_before_heldout_review") is not True):
        raise ValueError("protocol must preserve frozen rules, cohorts and diagnostic-only scope")
    for cohort, inventory in INVENTORIES.items():
        if any(protocol["cohorts"][cohort].get(key) != inventory[key] for key in ("families", "documents", "events")):
            raise ValueError("declared cohort inventory differs from the frozen comparison")


def frozen_protocol(backend, *, protocol_path=PROTOCOL_PATH):
    payload = Path(protocol_path).read_bytes()
    protocol = json.loads(payload)
    _validate_protocol(protocol)
    if backend not in FROZEN_RULES:
        raise ValueError("backend must be lexical or nano")
    for name in FROZEN_RULES:
        previous = (PRIOR_REPORT_DIR / (name + ".json")).read_bytes()
        if (hashlib.sha256(previous).hexdigest() != protocol["prior_report_sha256"][name]
                or json.loads(previous)["risk"]["variants"]["target_full"]["exploratory_threshold"] != FROZEN_RULES[name]):
            raise ValueError("prior report or tune-only rule differs from its predeclared identity")
    return {**protocol, "backend": backend, "rule": deepcopy(FROZEN_RULES[backend]),
            "protocol_file_sha256": hashlib.sha256(payload).hexdigest(),
            "selection_status": "FROZEN_BEFORE_HELDOUT_INFERENCE_NO_THRESHOLD_SEARCH",
            "score_semantics": "raw_relevance_not_probability"}


def _select(case, variant, max_chars):
    if variant == "target_full":
        query = rerank_query(case["text"], tuple(case["core_span"]), "target", radius=len(case["text"]))
        return {"rendered_query": query,
                "spans": [{"start": 0, "end": len(case["text"]), "quote": case["text"],
                           "reason": "full_document_control"}],
                "mode": "full", "status": "FULL_DOCUMENT_CONTROL", "gate_allowed": True,
                "abstain_reason": None, "assertion": None}
    if variant not in INPUT_VARIANTS:
        raise ValueError("unknown occurrence-evidence variant")
    mode = "paragraph" if variant == "target_paragraph" else "scoped"
    selected = select_evidence(case["text"], tuple(case["core_span"]), case["candidates"],
                               mode=mode, max_chars=max_chars)
    result = asdict(selected)
    if not isinstance(result.get("rendered_query"), str) or not result["rendered_query"]:
        raise ValueError("evidence selection produced an empty query before inference: " + case["case_id"])
    for span in result["spans"]:
        start, end = span["start"], span["end"]
        if not 0 <= start < end <= len(case["text"]) or case["text"][start:end] != span["quote"]:
            raise ValueError("selected evidence must retain exact source offsets and quotations")
    return result


def preflight_pairs(cases, fixed, *, variants=INPUT_VARIANTS, tokenizer=None, max_length=None, max_chars=1024):
    """Materialize all exact input pairs before the first score or warmup call."""
    if tokenizer is not None and (type(max_length) is not int or max_length < 1):
        raise ValueError("tokenized preflight requires a positive max_length")
    if len(cases) != len(fixed):
        raise ValueError("each occurrence requires its complete fixed shortlist")
    rows, selections, cache, selection_timings = [], {}, {}, []
    for variant in variants:
        for case, shortlist in zip(cases, fixed):
            mode = ("scoped" if variant in {"scoped_evidence", "scoped_asserted"}
                    else "paragraph" if variant == "target_paragraph" else "full")
            key = (mode, case["case_id"])
            if key not in cache:
                start = time.perf_counter()
                cache[key] = _select(case, variant, max_chars)
                selection_timings.append({"cohort": case["cohort"], "case_id": case["case_id"],
                                          "mode": mode, "elapsed_ms": (time.perf_counter() - start) * 1000})
            selection = cache[key]
            selections[variant + "::" + case["case_id"]] = deepcopy(selection)
            for hypothesis in shortlist:
                pair = (selection["rendered_query"], hypothesis.profile)
                count = _token_count(tokenizer, pair) if tokenizer is not None else None
                if count is not None and count > max_length:
                    raise ValueError(f"token overflow before inference: {case['cohort']} {case['case_id']} "
                                     f"{variant} {hypothesis.entity_id}: {count} > {max_length}")
                rows.append({"variant": variant, "cohort": case["cohort"], "case_id": case["case_id"],
                             "document_id": case["document_id"], "entity_id": hypothesis.entity_id,
                             "query": pair[0], "profile": pair[1], "pair_sha256": _digest(pair),
                             "token_count": count, "query_characters": len(pair[0]),
                             "profile_characters": len(pair[1])})
    counts = [row["token_count"] for row in rows if row["token_count"] is not None]
    timing_groups = defaultdict(list)
    for timing in selection_timings:
        timing_groups[(timing["cohort"], timing["mode"])].append(timing["elapsed_ms"])
    selection_cost = [{"cohort": cohort, "mode": mode, "calls": len(values),
                       "total_ms": math.fsum(values), "p50_ms": _percentile(values, .5),
                       "p95_ms": _percentile(values, .95), "p99_ms": _percentile(values, .99)}
                      for (cohort, mode), values in sorted(timing_groups.items())]
    return {"truncation": False, "tokenizer_checked": tokenizer is not None,
            "max_length": max_length if tokenizer is not None else None,
            "selection_max_chars": max_chars, "validated_pairs": len(rows),
            "maximum_pair_tokens": max(counts) if counts else None,
            "inputs_sha256": _digest(rows), "pairs": rows, "selections": selections,
            "selection_cost": {"measured_during_preflight": True,
                               "excluded_from_batch1_pair_latency": True,
                               "scoped_selection_cached_across_gate_ablation": True,
                               "calls": len(selection_timings), "groups": selection_cost,
                               "details": selection_timings}}


def _rank_custom(shortlist, pairs, scorer):
    """Score prepared queries directly, then evaluate the production path guard."""
    scores = scorer.score_pairs(pairs)
    if len(scores) != len(shortlist):
        raise ValueError("one finite raw relevance score is required per candidate")
    guard, ranked = ResolutionGuard(), []
    for hypothesis, score in zip(shortlist, scores):
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("one finite raw relevance score is required per candidate")
        verdict = guard.evaluate(MatchEvidence.from_path(
            hypothesis.channel, hypothesis.path, transform_cost=hypothesis.transform_cost))
        ranked.append(RankedHypothesis(hypothesis, float(score), verdict.commit_allowed, verdict.reasons))
    return sorted(ranked, key=lambda item: (-item.score, item.hypothesis.path.core_span,
                                           item.hypothesis.entity_id, item.hypothesis.path.kind))


def _family_risk(rows, protocol):
    proposed = {row["family_id"] for row in rows if row["proposal_selected"]}
    wrong = {row["family_id"] for row in rows if row["proposal_selected"] and not row["top1_exact_link"]}
    upper = binomial_error_ucb(len(wrong), len(proposed), protocol["family_alpha_per_comparison"])
    return {"interpretation": "DESCRIPTIVE_FAMILY_CLUSTER_DIAGNOSTIC_ONLY",
            "families_with_proposals": len(proposed), "families_with_any_wrong_proposal": len(wrong),
            "family_any_error_ucb": upper, "family_alpha": protocol["family_alpha_per_comparison"],
            "simultaneous_comparisons": "four_variants_times_two_backends_times_two_cohorts",
            "epsilon": .05, "numerical_bound_met": upper <= .05,
            "bound_assumptions_met": False, "coverage_valid": False, "production_authorized": False,
            "status": "UNCERTIFIED_SYNTHETIC_DIAGNOSTIC",
            "families_detail": [{"family_id": family, **counts} for family, counts in _groups(rows, "family_id").items()]}


def evaluate(cases, scorer, *, backend="lexical", variants=INPUT_VARIANTS, repeats=1,
             max_length=None, protocol=None):
    validate_cases(cases)
    if repeats != 1 or not variants or len(set(variants)) != len(variants) or any(v not in INPUT_VARIANTS for v in variants):
        raise ValueError("one repeat and unique predeclared variants are required")
    protocol = frozen_protocol(backend) if protocol is None else deepcopy(protocol)
    _validate_protocol(protocol)
    if protocol.get("backend") != backend or protocol.get("rule") != FROZEN_RULES.get(backend):
        raise ValueError("frozen backend and rule must match the scorer")
    protocol_hash = _digest(protocol)
    fixed = [hypotheses(case) for case in cases]
    if any(len(shortlist) != 2 for shortlist in fixed):
        raise ValueError("all variants must retain both family catalog candidates")
    proof = preflight_pairs(cases, fixed, variants=variants, tokenizer=getattr(scorer, "tokenizer", None),
                            max_length=max_length, max_chars=protocol["selection_max_chars"])
    pair_map = defaultdict(list)
    for row in proof["pairs"]:
        pair_map[(row["variant"], row["case_id"])].append((row["query"], row["profile"]))
    rows, cohorts = [], {cohort: {"variants": {}} for cohort in INVENTORIES if any(c["cohort"] == cohort for c in cases)}
    for variant in variants:
        for pair in pair_map[(variant, cases[0]["case_id"])]:
            scorer.score_pairs([pair])
        getattr(scorer, "synchronize", lambda: None)()
        for cohort, output in cohorts.items():
            timed, variant_rows = BatchOne(scorer), []
            for case, shortlist in zip(cases, fixed):
                if case["cohort"] != cohort:
                    continue
                prepared = pair_map[(variant, case["case_id"])]
                ranked = _rank_custom(shortlist, prepared, timed)
                selection = proof["selections"][variant + "::" + case["case_id"]]
                top, gold = ranked[0], case["expected_entity_id"]
                score, margin = top.score, top.score - ranked[1].score
                assertion_allowed = bool(selection["gate_allowed"])
                selected = bool(top.commit_allowed and margin > 0
                                and score >= protocol["rule"]["minimum_score"]
                                and margin >= protocol["rule"]["minimum_margin"]
                                and (variant != "scoped_asserted" or assertion_allowed))
                correct = bool(gold and top.hypothesis.entity_id == gold
                               and top.hypothesis.path.core_span == tuple(case["core_span"])
                               and top.hypothesis.path.full_identity == "SAME")
                row = {"variant": variant, "cohort": cohort, "case_id": case["case_id"],
                       "document_id": case["document_id"], "family_id": case["family_id"],
                       "partition": cohort, "domain": case["domain"], "source_collection": case["source_collection"],
                       "document_sha256": case["document_sha256"], "stratum": case["stratum"],
                       "negative_kind": case["semantic_label"] if case["semantic_label"] != "LINK" else None,
                       "target_group_id": case["target_group_id"], "gold_entity_id": gold,
                       "gold_kind": case["semantic_label"], "target_span": case["target_span"],
                       "core_span": case["core_span"], "candidate_count": 2, "total_candidate_count": 2,
                       "truncated": False, "top_entity_id": top.hypothesis.entity_id,
                       "top_score": score, "score_margin": margin, "guard_allowed": top.commit_allowed,
                       "guard_reasons": list(top.guard_reasons), "assertion_gate_allowed": assertion_allowed,
                       "assertion_gate_applied": variant == "scoped_asserted",
                       "assertion_abstain_reason": selection["abstain_reason"],
                       "evidence_selection": deepcopy(selection),
                       "top1_exact_link": correct,
                       "gold_in_shortlist": bool(gold and any(h.entity_id == gold and h.path.full_identity == "SAME"
                            and h.path.core_span == tuple(case["core_span"]) for h in shortlist)),
                       "proposal_selected": selected,
                       "proposal_entity_id": top.hypothesis.entity_id if selected else None,
                       "production_authorized": False, "coverage_valid": False,
                       "deterministic": None, "repetition_stability_checked": False,
                       "candidates": _ranked_payload(ranked)}
                variant_rows.append(row)
                rows.append(row)
            positives = [row for row in variant_rows if row["gold_kind"] == "LINK"]
            families = defaultdict(list)
            for row in positives:
                families[row["family_id"]].append(row["top1_exact_link"])
            token_pairs = [pair for pair in proof["pairs"] if pair["variant"] == variant and pair["cohort"] == cohort]
            output["variants"][variant] = {
                **_measure(variant_rows),
                "family_macro_top1": statistics.mean(statistics.mean(group) for group in families.values()) if families else None,
                "candidate_exact_link_recall": statistics.mean(row["gold_in_shortlist"] for row in positives) if positives else None,
                "mean_candidate_count": 2, "maximum_pair_tokens": max((pair["token_count"] for pair in token_pairs
                    if pair["token_count"] is not None), default=None),
                "batch1_pair_p50_ms": _percentile(timed.latencies_ms, .5),
                "batch1_pair_p95_ms": _percentile(timed.latencies_ms, .95),
                "batch1_pair_p99_ms": _percentile(timed.latencies_ms, .99),
                "measured_pair_calls": len(timed.latencies_ms),
                "assertion_gate_rejections": sum(not row["assertion_gate_allowed"] for row in variant_rows),
                "assertion_gate_applied": variant == "scoped_asserted",
                "repetition_stability_checked": False, "all_scores_repeat_stable": None,
                "by_stratum": _groups(variant_rows, "stratum"), "by_domain": _groups(variant_rows, "domain"),
                "by_family": _groups(variant_rows, "family_id"),
                "by_negative_kind": _groups([row for row in variant_rows if row["negative_kind"]], "negative_kind"),
                "family_risk": _family_risk(variant_rows, protocol),
                "multi_target_controls": _target_groups(variant_rows, token_pairs), "cases": variant_rows,
            }
    if _digest(protocol) != protocol_hash:
        raise ValueError("frozen protocol changed during inference")
    return {"cohorts": cohorts, "rows": rows, "token_proof": proof,
            "frozen_protocol": protocol, "frozen_protocol_sha256": protocol_hash,
            "threshold_fitting_performed": False, "production_authorized": False,
            "coverage_valid": False, "independent_sampling_assumptions_met": False}


def _source_manifest():
    root = Path(__file__).resolve().parents[1]
    paths = ("eval/run_occurrence_evidence.py", "eval/occurrence_evidence_corpus.py",
             "ktrf/occurrence_evidence.py", "ktrf/context_resolution.py",
             "eval/context_ranking_challenge.py", "eval/context_ranking_corpus.py",
             "eval/run_context_ranking.py", "eval/run_context_ranking_challenge.py", "eval/run_rerank_ablation.py",
             "eval/fixed_risk.py", "ktrf/rerank.py", "ktrf/segmentation.py")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def render_report(report):
    lines = ["# Occurrence evidence and assertion-veto diagnostic", "",
             "Fixed candidates and thresholds; development and new synthetic heldout families are reported separately.",
             "Scores, proposal counts and family bounds confer no production execution authority.", "",
             "| Cohort | Input | Positive top-1 | Correct proposals | Wrong proposals | Negative errors | Pair p95 ms |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for cohort, result in report["cohorts"].items():
        for variant, counts in result["variants"].items():
            lines.append(f"| {cohort} | {variant} | {counts['exact_link_top1_count']}/{counts['positive_cases']} "
                         f"| {counts['correct_proposals']} | {counts['wrong_proposals']} "
                         f"| {counts['wrong_negative_proposals']} | {counts['batch1_pair_p95_ms']:.3f} |")
    lines.extend(["", "The scoped inputs are identical with and without the assertion veto; only proposal permission changes.",
                  "All source offsets, selected quotes, veto reasons, raw scores, fixed candidates and tokenized input proofs",
                  "are retained in JSON. Multiple occurrences share document and family clusters. The alpha allocation covers",
                  "four variants, two backends and two cohorts; synthetic sampling does not establish a deployment risk bound.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, default=DEVELOPMENT_PATH)
    parser.add_argument("--heldout", type=Path, default=HELDOUT_PATH)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--annotation-manifest", type=Path, default=HELDOUT_PATH.parent / "annotation_manifest.json")
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
    backend = "lexical" if args.backend == "lexical" else "nano"
    protocol = frozen_protocol(backend, protocol_path=args.protocol)
    if args.max_length != protocol["maximum_pair_tokens"] or args.repeats != protocol["repeats"]:
        parser.error("max-length and repeats must match the frozen protocol")
    if args.backend == "scalar" and (args.model_dir is None or not args.model_dir.is_dir()
            or args.model_id != protocol["model_id"] or args.model_revision != protocol["model_revision"]):
        parser.error("scalar backend requires the predeclared local pinned model")
    annotation_payload = args.annotation_manifest.read_bytes()
    annotation = json.loads(annotation_payload)
    heldout_hash = hashlib.sha256(args.heldout.read_bytes()).hexdigest()
    selector_hash = hashlib.sha256(SELECTOR_PATH.read_bytes()).hexdigest()
    if (annotation.get("review_status") != "ADJUDICATED_BEFORE_INFERENCE"
            or annotation.get("final_fixture_sha256") != heldout_hash
            or annotation.get("selector_source_sha256") != selector_hash
            or not annotation.get("selector_freeze_revision")):
        parser.error("heldout annotation must identify the adjudicated source and frozen selector before inference")
    if args.cases is not None:
        payload = args.cases.read_bytes()
        cases = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    else:
        cases = build_cases(args.development, "development") + build_cases(args.heldout, "heldout")
        payload = b"".join(_json_bytes(case) + b"\n" for case in cases)
    validate_cases(cases)
    if {case["cohort"] for case in cases} != set(INVENTORIES):
        parser.error("both development and heldout cohorts must be frozen together")
    fixture_hashes = {"development": hashlib.sha256(args.development.read_bytes()).hexdigest(), "heldout": heldout_hash}
    if any(case["fixture_sha256"] != fixture_hashes[case["cohort"]] for case in cases):
        parser.error("frozen cases must identify the actual source fixture revisions")
    digest = model_digest(args.model_dir) if args.backend == "scalar" else None
    if digest is not None and digest != protocol["expected_model_sha256"]:
        parser.error("model files differ from the predeclared weight identity")
    sources = _source_manifest()
    scorer = LexicalCrossEncoder() if args.backend == "lexical" else StrictLocalScalarScorer(
        args.model_dir, args.max_length, args.device)
    if args.backend == "scalar" and str(args.device).startswith("cuda"):
        scorer.torch.cuda.reset_peak_memory_stats(scorer.device)
    result = evaluate(cases, scorer, backend=backend, repeats=args.repeats,
                      max_length=args.max_length, protocol=protocol)
    packages = {}
    for package in ("torch", "transformers", "tokenizers"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    report = {"schema_version": 1, "task": "occurrence_evidence_and_assertion_veto",
              "measured_at": datetime.now(timezone.utc).isoformat(), "source_revision": args.source_revision,
              "source_files": sources, "cases_sha256": hashlib.sha256(payload).hexdigest(),
              "fixture_files": fixture_hashes, "backend": args.backend, "scorer_id": scorer.reranker_id,
              "model_id": args.model_id, "model_revision": args.model_revision, "model_sha256": digest,
              "annotation_manifest": {"path": str(args.annotation_manifest), "sha256": hashlib.sha256(annotation_payload).hexdigest(),
                                      **annotation},
              "protocol_file_sha256": protocol["protocol_file_sha256"],
              "runtime": _runtime_provenance(scorer), "packages": packages, "device": args.device,
              "python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "omp_threads": os.environ.get("OMP_NUM_THREADS"), "mkl_threads": os.environ.get("MKL_NUM_THREADS"),
              "batch_size": 1, "repeats": args.repeats, "max_length": args.max_length if args.backend == "scalar" else None,
              "warmup_measured": False, "candidate_budget": 2, "calibration_status": "INSUFFICIENT_DATA",
              "limitations": ["Development data has already informed evidence-selector design.",
                              "Separately authored, blind AI-reviewed synthetic families are not a human or deployment audit.",
                              "Raw relevance and fixed diagnostic proposals confer no execution authority.",
                              "Fixed catalog candidates do not measure production retrieval or mention detection."], **result}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(render_report(report), encoding="utf-8")


if __name__ == "__main__":
    main()

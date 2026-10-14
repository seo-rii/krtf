"""Fixed-candidate target/context reranking, without execution authority.

All candidate pairs are tokenized without truncation before the first model
call. Scores stay raw; the family-disjoint risk diagnostic is a separate step.
Weights must already be available locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import statistics
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from eval.context_ranking_corpus import build_cases, hypotheses, validate_cases
from eval.context_ranking_risk import evaluate_thresholds, predeclared_protocol
from eval.run_rerank_ablation import LocalScalarScorer, model_digest
from ktrf.rerank import LexicalCrossEncoder, rank_hypotheses, rerank_query

INPUT_VARIANTS = ("surface", "local_context", "target_local", "target_full", "path_full")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _variant_settings(variant, text):
    settings = {"surface": ("surface", 60), "local_context": ("context", 60),
                "target_local": ("target", 60), "target_full": ("target", len(text)),
                "path_full": ("path", len(text))}
    if variant not in settings:
        raise ValueError(f"unknown context-ranking variant: {variant}")
    return settings[variant]


def _pairs(case, shortlist, variant):
    query_variant, radius = _variant_settings(variant, case["text"])
    return [(rerank_query(case["text"], h.path.core_span, query_variant, h.path, radius),
             h.profile) for h in shortlist]


def _token_count(tokenizer, pair):
    encoded = tokenizer(pair[0], pair[1], add_special_tokens=True, truncation=False)
    ids = encoded["input_ids"]
    if not isinstance(ids, (list, tuple)) or any(type(x) is not int for x in ids):
        raise ValueError("pair tokenizer must return a flat integer input_ids list")
    return len(ids)


def preflight_pairs(cases, fixed, *, variants=INPUT_VARIANTS, tokenizer=None, max_length=None):
    """Freeze every actual input and reject overflow before any inference."""
    if tokenizer is not None and (max_length is None or max_length < 1):
        raise ValueError("tokenized preflight requires a positive max_length")
    rows = []
    for variant in variants:
        for case, shortlist in zip(cases, fixed):
            for h, pair in zip(shortlist, _pairs(case, shortlist, variant)):
                count = _token_count(tokenizer, pair) if tokenizer is not None else None
                if count is not None and count > max_length:
                    raise ValueError(f"token overflow before inference: {case['case_id']} "
                                     f"{variant} {h.entity_id}: {count} > {max_length}")
                rows.append({"variant": variant, "case_id": case["case_id"],
                             "entity_id": h.entity_id, "query": pair[0], "profile": pair[1],
                             "pair_sha256": _digest(pair), "token_count": count,
                             "query_characters": len(pair[0]), "profile_characters": len(pair[1])})
    counts = [r["token_count"] for r in rows if r["token_count"] is not None]
    return {"truncation": False, "validated_pairs": len(rows),
            "tokenizer_checked": tokenizer is not None,
            "max_length": max_length if tokenizer is not None else None,
            "maximum_pair_tokens": max(counts) if counts else None,
            "inputs_sha256": _digest(rows), "pairs": rows}


class StrictLocalScalarScorer(LocalScalarScorer):
    """HF scalar model adapter with no truncation or probability conversion."""

    def __init__(self, directory, max_length, device):
        super().__init__(directory, max_length, device)
        physical_limit = getattr(self.model.config, "max_position_embeddings", None)
        if isinstance(physical_limit, int) and 0 < physical_limit < 1_000_000:
            if max_length > physical_limit:
                raise ValueError(f"max_length {max_length} exceeds model position limit {physical_limit}")

    def synchronize(self):
        if str(self.device).startswith("cuda"):
            self.torch.cuda.synchronize(self.device)

    def score_pairs(self, pairs):
        # Recheck at the adapter boundary, so future direct callers remain safe.
        for pair in pairs:
            count = _token_count(self.tokenizer, pair)
            if count > self.max_length:
                raise ValueError(f"token overflow before inference: {count} > {self.max_length}")
        inputs = self.tokenizer([a for a, _ in pairs], [b for _, b in pairs],
                                padding=True, truncation=False, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            logits = self.model(**inputs).logits
        if logits.ndim != 2 or logits.shape[1] != 1:
            raise ValueError("local scalar model must output one raw relevance logit")
        scores = logits[:, 0].float().cpu().tolist()
        if len(scores) != len(pairs) or any(not math.isfinite(x) for x in scores):
            raise ValueError("one finite raw relevance score is required per pair")
        return scores


class BatchOne:
    """Serial tokenization/inference/transfer latency with CUDA synchronization."""

    def __init__(self, scorer):
        self.scorer = scorer
        self.latencies_ms = []

    def score_pairs(self, pairs):
        out = []
        for pair in pairs:
            synchronize = getattr(self.scorer, "synchronize", lambda: None)
            synchronize()
            start = time.perf_counter()
            scores = self.scorer.score_pairs([pair])
            synchronize()
            elapsed = (time.perf_counter() - start) * 1000
            if len(scores) != 1 or isinstance(scores[0], bool) or not math.isfinite(scores[0]):
                raise ValueError("one finite raw relevance score is required per pair")
            self.latencies_ms.append(elapsed)
            out.append(float(scores[0]))
        return out


def _identity(h):
    return (h.entity_id, h.path.core_span, h.path.full_identity, h.path.kind)


def _percentile(values, probability):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)] if ordered else None


def _ranked_payload(ranked):
    out = []
    for item in ranked:
        h = item.hypothesis
        path = {**h.path.as_dict(), "core_span": list(h.path.core_span),
                "surface_span": list(h.path.surface_span), "full_identity": h.path.full_identity,
                "relation": h.path.relation, "kind": h.path.kind}
        out.append({"entity_id": h.entity_id, "core_span": list(h.path.core_span),
                    "full_identity": h.path.full_identity, "path": path,
                    "path_id": _digest(path), "hypothesis_id": _digest([h.entity_id, path]),
                    "score": item.score, "guard_allowed": item.commit_allowed,
                    "guard_reasons": list(item.guard_reasons)})
    return out


def evaluate(cases, scorer, *, repeats=1, variants=INPUT_VARIANTS, max_length=None,
             protocol=None):
    """Rank fixed shortlists, then evaluate frozen proposal thresholds."""
    validate_cases(cases)
    if repeats < 1 or len(set(variants)) != len(variants) or not variants:
        raise ValueError("positive repeats and unique nonempty variants are required")
    for variant in variants:
        _variant_settings(variant, "")
    fixed = [hypotheses(case) for case in cases]
    if any(len(shortlist) != 2 for shortlist in fixed):
        raise ValueError("every context-ranking case must use the same two catalog candidates")
    if protocol is None:
        protocol = predeclared_protocol("nano" if hasattr(scorer, "tokenizer") else "lexical", variants)
    # Hash before the first scoring call; thresholds cannot depend on observed scores.
    protocol_hash = _digest(protocol)
    proof = preflight_pairs(cases, fixed, variants=variants,
                            tokenizer=getattr(scorer, "tokenizer", None), max_length=max_length)
    results, rows = {}, []
    for variant in variants:
        query_variant, _ = _variant_settings(variant, "")
        # The first input is selected by corpus order, never by its gold label.
        if cases:
            for pair in _pairs(cases[0], fixed[0], variant):
                scorer.score_pairs([pair])
            getattr(scorer, "synchronize", lambda: None)()
        timed = BatchOne(scorer)
        variant_rows = []
        for case, shortlist in zip(cases, fixed):
            _, radius = _variant_settings(variant, case["text"])
            runs = [rank_hypotheses(case["text"], shortlist, timed, query_variant, radius=radius)
                    for _ in range(repeats)]
            ranked = runs[0]
            stable = all([(_identity(r.hypothesis), r.score) for r in run]
                         == [(_identity(r.hypothesis), r.score) for r in ranked] for run in runs)
            top = ranked[0]
            gold = case["expected_entity_id"]
            correct = bool(gold and top.hypothesis.entity_id == gold
                           and top.hypothesis.path.core_span == tuple(case["core_span"])
                           and top.hypothesis.path.full_identity == "SAME")
            row = {"variant": variant, "case_id": case["case_id"],
                   "document_id": case["document_id"], "family_id": case["family_id"],
                   "partition": case["split"], "source_collection": case["source_collection"],
                   "document_sha256": case["document_sha256"], "stratum": case.get("stratum"),
                   "gold_entity_id": gold, "gold_kind": case["semantic_label"],
                   "target_span": case["target_span"], "core_span": case["core_span"],
                   "candidate_count": len(shortlist), "total_candidate_count": len(shortlist),
                   "truncated": False, "top_entity_id": top.hypothesis.entity_id,
                   "top_score": top.score, "score_margin": top.score - ranked[1].score,
                   "guard_allowed": top.commit_allowed, "guard_reasons": list(top.guard_reasons),
                   "top1_exact_link": correct,
                   "gold_in_shortlist": bool(gold and any(h.entity_id == gold and
                        h.path.core_span == tuple(case["core_span"]) and h.path.full_identity == "SAME"
                        for h in shortlist)),
                   "deterministic": stable, "production_authorized": False,
                   "candidates": _ranked_payload(ranked)}
            variant_rows.append(row)
            rows.append(row)
        positive = [r for r in variant_rows if r["gold_kind"] == "LINK"]
        families = {}
        for row in positive:
            families.setdefault(row["family_id"], []).append(row["top1_exact_link"])
        token_rows = [r for r in proof["pairs"] if r["variant"] == variant and r["token_count"] is not None]
        results[variant] = {"positive_cases": len(positive),
                            "exact_link_top1_count": sum(r["top1_exact_link"] for r in positive),
                            "exact_link_top1": statistics.mean(r["top1_exact_link"] for r in positive)
                            if positive else None,
                            "family_macro_top1": statistics.mean(statistics.mean(v) for v in families.values())
                            if families else None,
                            "candidate_exact_link_recall": statistics.mean(r["gold_in_shortlist"] for r in positive)
                            if positive else None,
                            "negative_cases": len(variant_rows) - len(positive),
                            "negative_top_structural_guard_blocks": sum(not r["guard_allowed"] for r in variant_rows
                                                                         if r["gold_kind"] != "LINK"),
                            "mean_candidate_count": 2 if variant_rows else 0,
                            "maximum_pair_tokens": max((r["token_count"] for r in token_rows), default=None),
                            "batch1_pair_p50_ms": _percentile(timed.latencies_ms, .5),
                            "batch1_pair_p95_ms": _percentile(timed.latencies_ms, .95),
                            "batch1_pair_p99_ms": _percentile(timed.latencies_ms, .99),
                            "measured_pair_calls": len(timed.latencies_ms),
                            "all_scores_repeat_stable": all(r["deterministic"] for r in variant_rows),
                            "cases": variant_rows}
    if _digest(protocol) != protocol_hash:
        raise ValueError("frozen risk protocol changed during scoring")
    risk = evaluate_thresholds(rows, protocol=protocol)
    return {"variants": results, "rows": rows, "token_proof": proof,
            "risk_protocol": protocol, "risk_protocol_sha256": protocol_hash,
            "risk": risk, "production_authorized": False, "coverage_valid": False}


def _source_manifest():
    root = Path(__file__).resolve().parents[1]
    paths = ("eval/run_context_ranking.py", "eval/context_ranking_corpus.py",
             "eval/context_ranking_risk.py", "eval/run_rerank_ablation.py",
             "ktrf/rerank.py", "ktrf/segmentation.py")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def _runtime_provenance(scorer):
    """Describe the actual scalar runtime without claiming isolated performance."""
    if not hasattr(scorer, "model") or not hasattr(scorer, "torch"):
        return None
    torch, model = scorer.torch, scorer.model
    dtypes = sorted({str(parameter.dtype) for parameter in model.parameters()})
    config = model.config
    runtime = {"model_parameter_dtypes": dtypes,
               "attention_implementation": getattr(config, "_attn_implementation", None),
               "physical_position_limit": getattr(config, "max_position_embeddings", None),
               "tokenizer_model_max_length": getattr(scorer.tokenizer, "model_max_length", None),
               "requested_pair_token_limit": scorer.max_length,
               "torch_cuda_version": torch.version.cuda,
               "matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
               "gpu": None}
    if str(scorer.device).startswith("cuda"):
        torch.cuda.synchronize(scorer.device)
        properties = torch.cuda.get_device_properties(scorer.device)
        runtime["gpu"] = {"device": str(scorer.device), "name": properties.name,
                          "total_memory_bytes": properties.total_memory,
                          "peak_allocated_bytes": torch.cuda.max_memory_allocated(scorer.device),
                          "peak_reserved_bytes": torch.cuda.max_memory_reserved(scorer.device),
                          "memory_scope": "this process, reset after model loading before warmup"}
    return runtime


def render_report(report):
    lines = ["# Fixed-candidate target/context ranking", "",
             "Raw relevance scores and ranking proposals do not authorize production execution.", "",
             f"Backend: `{report['backend']}`; model: `{report.get('model_id') or report['scorer_id']}`.",
             f"Corpus SHA-256: `{report['cases_sha256']}`.",
             f"Risk protocol SHA-256: `{report['risk_protocol_sha256']}`.", "",
             "| Input | Positive top-1 | Candidate recall | Pair p95 ms | Max pair tokens |",
             "|---|---:|---:|---:|---:|"]
    for name, result in report["variants"].items():
        recall = result["candidate_exact_link_recall"]
        latency = result["batch1_pair_p95_ms"]
        lines.append(f"| {name} | {result['exact_link_top1_count']}/{result['positive_cases']} "
                     f"| {recall:.3f} | {latency:.3f} | {result['maximum_pair_tokens']} |")
    lines.extend(["", "The corpus contains AI-authored synthetic documents, shares eight entity families,",
                  "and does not provide independent human or deployment-distribution risk validation.",
                  "The JSON report preserves every candidate score, structural guard, input pair,",
                  "and family-level proposal-risk result. Coverage validity remains false.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, help="frozen corpus JSONL; otherwise build existing 64 cases")
    parser.add_argument("--backend", choices=("lexical", "scalar"), default="lexical")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model-id")
    parser.add_argument("--model-revision")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--repeats", type=int, default=3)
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
    sources = _source_manifest()
    protocol = predeclared_protocol("lexical" if args.backend == "lexical" else "nano", INPUT_VARIANTS)
    scorer = LexicalCrossEncoder() if args.backend == "lexical" else StrictLocalScalarScorer(
        args.model_dir, args.max_length, args.device)
    if args.backend == "scalar" and str(args.device).startswith("cuda"):
        scorer.torch.cuda.reset_peak_memory_stats(scorer.device)
    results = evaluate(cases, scorer, repeats=args.repeats, max_length=args.max_length, protocol=protocol)
    runtime = _runtime_provenance(scorer)
    packages = {}
    for package in ("torch", "transformers", "tokenizers"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    report = {"schema_version": 1, "task": "fixed_candidate_context_ranking",
              "measured_at": datetime.now(timezone.utc).isoformat(),
              "cases_sha256": hashlib.sha256(payload).hexdigest(), "source_files": sources,
              "source_revision": args.source_revision, "backend": args.backend,
              "scorer_id": scorer.reranker_id, "model_id": args.model_id,
              "model_revision": args.model_revision,
              "model_sha256": model_digest(args.model_dir) if args.backend == "scalar" else None,
              "runtime": runtime,
              "packages": packages, "device": args.device, "python": platform.python_version(),
              "platform": platform.platform(), "machine": platform.machine(),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "omp_threads": os.environ.get("OMP_NUM_THREADS"),
              "mkl_threads": os.environ.get("MKL_NUM_THREADS"), "batch_size": 1,
              "repeats": args.repeats, "max_length": args.max_length if args.backend == "scalar" else None,
              "warmup_measured": False, "candidate_budget": 2, "calibration_status": "INSUFFICIENT_DATA",
              "limitations": ["Raw relevance is not a probability or execution authorization.",
                              "Eight reused synthetic families do not validate deployment risk.",
                              "Retrieval latency and end-to-end task utility are not measured."], **results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    args.out.with_suffix(".md").write_text(render_report(report))


if __name__ == "__main__":
    main()

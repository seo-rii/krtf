"""Fixed-candidate, batch-one target/path input ablations.

Usage: python -m eval.run_rerank_ablation --out eval/out/rerank_ablation.json
Use --cases FILE for independently annotated JSONL and --backend onnx --model-dir
DIR for a local exported model. Local HF scalar and PyLate MaxSim adapters are
experimental, explicitly selected, and do not change the production resolver.
No model weights are downloaded by this runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import time
import os
import resource
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from ktrf.rerank import (INPUT_VARIANTS, LexicalCrossEncoder, LinkingHypothesis,
                         OnnxCrossEncoder, maxsim, rank_hypotheses)
from ktrf.rerank import rerank_query
from ktrf.segmentation import StructuralPath

DEFAULT_CASES = Path(__file__).parent / "data" / "rerank_confusion.jsonl"


class LocalScalarScorer:
    """Local HF sequence-classification baseline; logits stay raw."""

    def __init__(self, directory: Path, max_length: int, device: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch, self.max_length = torch, max_length
        self.tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            directory, local_files_only=True).to(device).eval()
        self.device = device
        self.reranker_id = f"local-hf:{directory.name}"

    def score_pairs(self, pairs):
        inputs = self.tokenizer([a for a, _ in pairs], [b for _, b in pairs],
                                padding=True, truncation=True,
                                max_length=self.max_length, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            logits = self.model(**inputs).logits
        if logits.ndim != 2 or logits.shape[1] != 1:
            raise ValueError("local scalar model must output one relevance logit")
        return logits[:, 0].float().cpu().tolist()


class LocalMaxSimScorer:
    """PyLate masks model tokens; score a fixed shortlist, without an index."""

    def __init__(self, directory: Path, max_length: int, device: str):
        from pylate import models

        if max_length < 2:
            raise ValueError("MaxSim combined token budget must be at least two")
        query_cap = max_length // 2
        self.model = models.ColBERT(model_name_or_path=str(directory), device=device,
                                   query_length=query_cap, document_length=max_length - query_cap,
                                   local_files_only=True)
        self.reranker_id = f"local-maxsim:{directory.name}"

    def score_pairs(self, pairs):
        query = self.model.encode([a for a, _ in pairs], is_query=True,
                                  batch_size=1, show_progress_bar=False)
        documents = self.model.encode([b for _, b in pairs], is_query=False,
                                      batch_size=1, show_progress_bar=False)
        return [maxsim(q.tolist(), d.tolist()) for q, d in zip(query, documents)]


class BatchOne:
    """Measure serial batch-one calls, including tokenization and CPU transfer."""

    def __init__(self, scorer):
        self.scorer = scorer
        self.latencies_ms = []

    def score_pairs(self, pairs):
        out = []
        for pair in pairs:
            start = time.perf_counter()
            scores = self.scorer.score_pairs([pair])
            self.latencies_ms.append((time.perf_counter() - start) * 1000)
            if len(scores) != 1 or not math.isfinite(scores[0]):
                raise ValueError("one finite score is required per pair")
            out.append(scores[0])
        return out


def load_cases(path: Path, payload: bytes | None = None):
    cases = [json.loads(line) for line in (payload if payload is not None else path.read_bytes()).decode().splitlines()
             if line.strip()]
    ids = set()
    for case in cases:
        if case["case_id"] in ids:
            raise ValueError("duplicate case_id")
        ids.add(case["case_id"])
        # Provenance is mandatory even for constructed smoke data.
        for key in ("document_id", "family_id", "source", "ambiguity", "gold"):
            if key not in case:
                raise ValueError(f"missing case field {key}")
        if case["ambiguity"] not in ("resolvable", "ambiguous", "nil"):
            raise ValueError("ambiguity must be resolvable, ambiguous, or nil")
        if case["ambiguity"] == "resolvable" and len(case["gold"]) != 1:
            raise ValueError("resolvable cases require exactly one gold hypothesis")
        if case["ambiguity"] == "ambiguous" and len(case["gold"]) < 2:
            raise ValueError("ambiguous cases require multiple acceptable hypotheses")
        if case["ambiguity"] == "nil" and case["gold"]:
            raise ValueError("NIL cases cannot have a KB gold hypothesis")
        if not case["candidates"]:
            raise ValueError("fixed candidate set cannot be empty")
    return cases


def hypotheses(case, budget):
    result = []
    # Same ordered shortlist is selected once, independent of scorer/variant.
    for candidate in case["candidates"][:budget]:
        features = dict(candidate["path"])
        start, end = features.pop("core_span")
        token_start, token_end = features.pop("token_span", (start, end))
        for key in ("particles", "residual_parts", "residual_classes", "prefix_span"):
            if key in features and features[key] is not None:
                features[key] = tuple(features[key])
        path = StructuralPath(token=case["text"][token_start:token_end],
                              token_span=(token_start, token_end),
                              core=case["text"][start:end], core_span=(start, end), **features)
        result.append(LinkingHypothesis(path, candidate["entity_id"], candidate["profile"],
                                       candidate.get("channel", "abbrev"),
                                       candidate.get("transform_cost", 0.0)))
    return result


def identity(h):
    return (h.entity_id, h.path.core_span, h.path.full_identity)


def gold_identities(case):
    return {(g["entity_id"], tuple(g["core_span"]), g.get("full_identity", "SAME"))
            for g in case["gold"]}


def hard_negative_pairs(cases, budget=8, variant="target", radius=60):
    """Export confusion-conditioned pairs while preserving source groups.

    Ambiguous cases label all acceptable hypotheses positive, rather than
    inventing a winner. Partition by document/family BEFORE fitting anything.
    """
    if budget < 1:
        raise ValueError("budget must be positive")
    pairs = []
    for case in cases:
        gold = gold_identities(case)
        for h in hypotheses(case, budget):
            pairs.append({"case_id": case["case_id"], "document_id": case["document_id"],
                          "family_id": case["family_id"], "source": case["source"],
                          "ambiguity": case["ambiguity"], "entity_id": h.entity_id,
                          "core_span": list(h.path.core_span),
                          "full_identity": h.path.full_identity,
                          "query": rerank_query(case["text"], h.path.core_span, variant, h.path, radius),
                          "profile": h.profile, "label": int(identity(h) in gold)})
    return pairs


def model_digest(directory):
    """Content identity for local weights/configs; no path-only model identity."""
    if directory is None:
        return None
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in (".json", ".safetensors", ".onnx", ".bin", ".txt"):
            digest.update(str(path.relative_to(directory)).encode())
            digest.update(b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def _percentile(values, p):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)] if ordered else None


def evaluate(cases, scorer, budget=8, repeats=3, radius=60):
    if budget < 1 or repeats < 1:
        raise ValueError("budget and repeats must be positive")
    fixed = [(c, hypotheses(c, budget)) for c in cases]
    results = {}
    for variant in INPUT_VARIANTS:
        timed = BatchOne(scorer)
        rows = []
        # Warm up each format once; keep those calls out of latency statistics.
        if fixed:
            rank_hypotheses(fixed[0][0]["text"], fixed[0][1], scorer, variant, radius=radius)
        for case, shortlist in fixed:
            runs = [rank_hypotheses(case["text"], shortlist, timed, variant, radius=radius)
                    for _ in range(repeats)]
            ranked = runs[0]
            stable = all([(identity(r.hypothesis), r.score) for r in run]
                         == [(identity(r.hypothesis), r.score) for r in ranked] for run in runs)
            gold = gold_identities(case)
            top = ranked[0]
            rows.append({"case_id": case["case_id"], "document_id": case["document_id"],
                         "family_id": case["family_id"], "ambiguity": case["ambiguity"],
                         "gold_in_shortlist": bool(gold & {identity(h) for h in shortlist}),
                         "top1_exact_link": identity(top.hypothesis) in gold,
                         "candidate_count": len(shortlist),
                         "total_candidate_count": len(case["candidates"]),
                         "truncated": len(shortlist) < len(case["candidates"]),
                         "top1": {"entity_id": top.hypothesis.entity_id,
                                  "core_span": list(top.hypothesis.path.core_span),
                                  "full_identity": top.hypothesis.path.full_identity,
                                  "score": top.score, "guard_allowed": top.commit_allowed,
                                  "guard_reasons": list(top.guard_reasons)},
                         "score_margin": top.score - ranked[1].score if len(ranked) > 1 else None,
                         "deterministic": stable})
        labeled = [r for r in rows if r["ambiguity"] == "resolvable"]
        families = {}
        for r in labeled:
            families.setdefault(r["family_id"], []).append(r["top1_exact_link"])
        results[variant] = {
            "resolvable_cases": len(labeled),
            "exact_link_top1": sum(r["top1_exact_link"] for r in labeled) / len(labeled)
            if labeled else None,
            "family_macro_top1": statistics.mean(statistics.mean(v) for v in families.values())
            if families else None,
            "candidate_exact_link_recall": sum(r["gold_in_shortlist"] for r in labeled) / len(labeled)
            if labeled else None,
            "mean_candidate_count": statistics.mean(r["candidate_count"] for r in rows) if rows else 0,
            "batch1_pair_p50_ms": _percentile(timed.latencies_ms, .5),
            "batch1_pair_p95_ms": _percentile(timed.latencies_ms, .95),
            "batch1_pair_p99_ms": _percentile(timed.latencies_ms, .99),
            "measured_pair_calls": len(timed.latencies_ms), "cases": rows}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--backend", choices=("lexical", "onnx", "scalar", "maxsim"), default="lexical")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model-id", help="upstream model identity for the manifest")
    parser.add_argument("--model-revision", help="pinned upstream revision used to provision local weights")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--budget", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--radius", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("eval/out/rerank_ablation.json"))
    parser.add_argument("--pairs-out", type=Path, help="export grouped confusion pairs; no training is run")
    parser.add_argument("--pairs-variant", choices=INPUT_VARIANTS, default="target")
    args = parser.parse_args()
    if args.max_length < 1:
        parser.error("max-length must be positive")
    if args.backend != "lexical" and (args.model_dir is None or not args.model_dir.is_dir()):
        parser.error("neural backends require an existing local --model-dir")
    loaders = {"onnx": OnnxCrossEncoder, "scalar": LocalScalarScorer, "maxsim": LocalMaxSimScorer}
    scorer = (LexicalCrossEncoder() if args.backend == "lexical" else
              loaders[args.backend](args.model_dir, args.max_length, args.device))
    case_payload = args.cases.read_bytes()
    cases = load_cases(args.cases, case_payload)
    results = evaluate(cases, scorer, args.budget, args.repeats, args.radius)
    packages = {}
    for package in ("torch", "transformers", "pylate", "onnxruntime", "tokenizers"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    report = {"schema_version": 1, "task": "fixed_candidate_rerank_ablation",
              "measured_at": datetime.now(timezone.utc).isoformat(),
              "cases_sha256": hashlib.sha256(case_payload).hexdigest(),
              "source_kind": sorted({c["source"] for c in cases}),
              "scorer_id": scorer.reranker_id, "backend": args.backend,
              "model_sha256": model_digest(args.model_dir) if args.backend != "lexical" else None,
              "model_id": args.model_id, "model_revision": args.model_revision,
              "packages": packages,
              "device": args.device, "python": platform.python_version(),
              "platform": platform.platform(), "machine": platform.machine(),
              "omp_threads": os.environ.get("OMP_NUM_THREADS"),
              "mkl_threads": os.environ.get("MKL_NUM_THREADS"),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "pair_budget_per_case": args.budget, "batch_size": 1,
              "max_length": args.max_length if args.backend != "lexical" else None,
              "maxsim_query_length": args.max_length // 2 if args.backend == "maxsim" else None,
              "maxsim_document_length": args.max_length - args.max_length // 2
              if args.backend == "maxsim" else None,
              "context_radius": args.radius, "repeats": args.repeats,
              "coverage_valid": False, "calibration_status": "INSUFFICIENT_DATA",
              "limitations": ["Relevance scores are not probabilities; no automatic commits are issued.",
                              "Ranking gains do not establish fixed-risk commit-rate gains.",
                              "Synthetic smoke data does not measure independent document quality.",
                              "Tokenization, scoring and transfer are timed; retrieval is excluded."],
              "variants": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.pairs_out:
        args.pairs_out.parent.mkdir(parents=True, exist_ok=True)
        args.pairs_out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in
                                        hard_negative_pairs(cases, args.budget, args.pairs_variant, args.radius)))
    print(f"Wrote {args.out}: {len(cases)} cases, backend={args.backend}")


if __name__ == "__main__":
    main()

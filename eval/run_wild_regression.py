"""Paired wild-corpus regression check for a resolver change.

Usage: python -m eval.run_wild_regression [--sentences N] [--paths K]

``reports/WILD_CORPUS.md`` is the authoritative real-text report, but a full
run is hours long, which makes it useless as a gate on a single change. This
runs the same silver-recall and fake-glossary suites from ``run_wild`` on a
sample, once per arm of a ``RuntimePolicy`` change, in one process.

It is a **regression check, not a replacement**: the sample is smaller, so
the confidence intervals are wider and the absolute numbers are not the ones
to publish. What it answers is narrower and sufficient — did this change move
silver recall, commit behaviour, or structural false positives?

Writes eval/out/wild_regression.json.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from ktrf.snapshot import RuntimePolicy

from .run_wild import run_fake_glossary_fp, run_silver_and_tails
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260830


def _summary(silver: dict, fp: dict) -> dict:
    return {
        "silver_mentions": silver["silver_mentions"],
        "detected_e2e": silver["core_detected_e2e"]["rate"],
        "gold_in_set_e2e": silver["gold_in_set_e2e"]["rate"],
        "resolved_commits": silver["resolved"]["count"],
        "resolved_precision": silver["resolved"]["precision_given_commit"],
        "resolved_coverage": silver["resolved"]["coverage_of_silver"],
        "ledger_commits": silver["commit_ledger"]["commits"],
        "ledger_on_silver": silver["commit_ledger"]["on_silver_span"],
        "ledger_off_silver": silver["commit_ledger"]["off_silver_span"],
        "tail_coverage": silver["tail_distribution"]["coverage"],
        "latency_p50_ms": silver["latency_ms"]["p50"],
        "latency_p95_ms": silver["latency_ms"]["p95"],
        "fake_candidates_per_1k": fp["candidate_mentions_per_1k_chars"],
        "fake_resolved_fp": fp["resolved_fp_count"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", type=int, default=20000)
    ap.add_argument("--paths", type=int, default=4)
    args = ap.parse_args()

    corpus = load_corpus()
    sample = random.Random(SEED).sample(corpus, min(args.sentences, len(corpus)))
    print(f"sample: {len(sample)} of {len(corpus)} sentences")

    arms = {}
    for name, paths in (("control", 1), ("treatment", args.paths)):
        policy = RuntimePolicy(max_segmentation_paths=paths)
        t0 = time.perf_counter()
        silver = run_silver_and_tails(sample, policy=policy)
        fp = run_fake_glossary_fp(sample, policy=policy)
        arms[name] = {"max_segmentation_paths": paths, **_summary(silver, fp),
                      "elapsed_seconds": round(time.perf_counter() - t0, 1)}
        print(f"[{name}] {json.dumps(arms[name], ensure_ascii=False)}")

    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "wild_regression.json").write_text(
        json.dumps({"sample_sentences": len(sample), "seed": SEED, **arms},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nkey                       control -> treatment")
    for key in arms["control"]:
        if key in ("max_segmentation_paths", "elapsed_seconds"):
            continue
        a, b = arms["control"][key], arms["treatment"][key]
        flag = "" if a == b else "   <-- changed"
        print(f"{key:26s} {a} -> {b}{flag}")


if __name__ == "__main__":
    main()

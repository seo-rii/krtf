"""Diagnose harmful flips from an A/B run: was the gold entity in the pack?

Usage: python -m eval.analyze_flips [--model qwen3:8b]

A harmful flip is a case the model answered correctly *without* terminology
context and got wrong *with* it. Averages hide why that happens, so this
rebuilds the exact context pack for each flipped case and classifies it:

  pack_had_gold_as_fact       KTRF grounded the right entity; the model
                              still went wrong (model-side failure)
  pack_had_gold_as_candidate  gold offered as one of several senses
  pack_had_wrong_fact         KTRF committed to the WRONG entity — the
                              dangerous class, worth a hard look
  pack_empty                  nothing was grounded at all

The first pilot found the last bucket dominating, which is what motivated
the "never inject an empty pack" contract in ``ktrf.context``.

Reads eval/out/ab_grounding.json (written by ``eval.run_ab_grounding``).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ktrf.context import ContextPolicy, build_context_pack
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .run_ab_grounding import BUDGET_TOKENS, QUESTION, ROOT, build_cases
from .wild_data import load_corpus


def classify(pack: dict, gold: str) -> str:
    resolved_ids = {c["entity_id"] for c in pack["resolved_terms"]}
    candidate_ids = {c["entity_id"] for a in pack["ambiguous_mentions"]
                     for c in a["candidates"]}
    if gold in resolved_ids:
        return "pack_had_gold_as_fact"
    if gold in candidate_ids:
        return "pack_had_gold_as_candidate"
    if resolved_ids:
        return "pack_had_wrong_fact"
    return "pack_empty"


def analyze(model: str) -> dict:
    payload = json.loads(
        (ROOT / "eval" / "out" / "ab_grounding.json").read_text(
            encoding="utf-8"))
    runs = payload.get("runs") or {payload.get("model"): payload}
    if model not in runs:
        raise SystemExit(f"no run for {model!r}; have {sorted(runs)}")
    records = runs[model]["case_records"]

    def _correct(rec, cond) -> bool:
        value = rec["results"].get(cond)
        # newer runs store the full per-call record, older ones a bool
        return bool(value["correct"] if isinstance(value, dict) else value)

    flipped = [i for i, r in enumerate(records)
               if _correct(r, "A_llm_only") and not _correct(r, "C_ktrf")]

    corpus = load_corpus()
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    cases, holdout_glossary = build_cases(
        corpus, glossary, runs[model]["cases"] // 2)

    from ktrf.encoders import HashEncoder, OnnxE5Encoder
    e5_dir = ROOT / "models" / "multilingual-e5-small"
    encoder = OnnxE5Encoder(e5_dir) if e5_dir.exists() else HashEncoder()
    snapshots = {
        "known_abbrev": compile_snapshot(glossary, encoder=encoder,
                                         run_conformance=False),
        "unseen_abbrev": compile_snapshot(holdout_glossary, encoder=encoder,
                                          run_conformance=False),
    }

    buckets: Counter = Counter()
    rows = []
    for i in flipped:
        case = cases[i]
        question = QUESTION.format(surface=case["surface"])
        snapshot = snapshots[case["slice"]]
        resp = resolve(snapshot, case["text"], mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50,
                                "detect_unregistered_mentions": True})
        pack = build_context_pack(
            snapshot, resp, query=question,
            policy=ContextPolicy(max_tokens=BUDGET_TOKENS))
        bucket = classify(pack, case["entity_id"])
        buckets[bucket] += 1
        rows.append({"slice": case["slice"], "surface": case["surface"],
                     "gold": case["entity_id"], "bucket": bucket,
                     "pack_facts": sorted(
                         c["entity_id"] for c in pack["resolved_terms"])[:3],
                     "text": case["text"][:60]})
    return {"model": model, "harmful_flips": len(flipped),
            "by_slice": dict(Counter(cases[i]["slice"] for i in flipped)),
            "buckets": dict(buckets), "cases": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:8b")
    args = ap.parse_args()
    result = analyze(args.model)
    out = ROOT / "eval" / "out" / f"flips_{args.model.replace(':', '_')}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"harmful flips: {result['harmful_flips']} {result['by_slice']}")
    for bucket, n in sorted(result["buckets"].items(), key=lambda kv: -kv[1]):
        print(f"  {bucket}: {n}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

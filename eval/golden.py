"""Golden-set evaluation (spec §45.8, §48.6 축소판).

Hand-written sentences independent of the deterministic generator:
mid-sentence mentions, homograph particles, nesting, sense context and
negatives. Never used for training/tuning (§45.8).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ktrf.resolver import resolve

from .metrics import EvalReport

GOLDEN_PATH = Path(__file__).resolve().parent / "golden.yaml"


def _find_span(text: str, surface: str, occurrence: int = 1) -> tuple[int, int]:
    start = -1
    for _ in range(occurrence):
        start = text.index(surface, start + 1)
    return (start, start + len(surface))


def _mention_entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def run_golden(snapshot, report: EvalReport) -> dict:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        cases = yaml.safe_load(f)

    detected = in_set = gold_total = 0
    top_correct = top_total = 0
    resolved_total = resolved_correct = 0
    violations: list[dict] = []

    for case in cases:
        text = case["text"]
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        mentions = resp["mentions"]
        by_span = {}
        for m in mentions:
            cp = m["span"]["codepoint"]
            by_span[(cp["start"], cp["end"])] = m

        gold_spans = {}
        for g in case.get("gold", []):
            span = _find_span(text, g["surface"], g.get("occurrence", 1))
            gold_spans[span] = g["entity"]
            gold_total += 1
            m = by_span.get(span)
            if m is None:
                # constrained containment for Level B cases (§43.3)
                overlaps = [x for s, x in by_span.items()
                            if s[0] < span[1] and span[0] < s[1]]
                if case.get("level") == "B" and overlaps:
                    detected += 1
                    if any(g["entity"] in _mention_entities(x) for x in overlaps):
                        in_set += 1
                    continue
                violations.append({"text": text, "miss": g["surface"]})
                continue
            detected += 1
            ids = _mention_entities(m)
            if g["entity"] in ids:
                in_set += 1
            else:
                violations.append({"text": text, "gold_not_in_set": g["surface"],
                                   "got": sorted(ids)})
            # top-1 (soft diagnostic): resolved entity or highest marginal
            members = [x for x in m.get("prediction_set", {}).get("members", [])
                       if x.get("kind", "ENTITY") == "ENTITY"
                       and x.get("calibrated_probability") is not None]
            top = (m.get("resolved_entity", {}).get("entity_id")
                   or (max(members, key=lambda x: x["calibrated_probability"])
                       ["entity_id"] if members else None))
            if top is not None:
                top_total += 1
                top_correct += int(top == g["entity"])

        forbidden = set(case.get("forbidden", []))
        for m in mentions:
            ids = _mention_entities(m)
            hit = ids & forbidden
            if hit:
                violations.append({"text": text, "forbidden_hit": sorted(hit)})
            cp = m["span"]["codepoint"]
            span = (cp["start"], cp["end"])
            if m.get("link_decision") == "RESOLVED":
                if case.get("no_resolved"):
                    violations.append({"text": text,
                                       "unexpected_resolved": m["surface"]})
                elif span in gold_spans:
                    resolved_total += 1
                    resolved_correct += int(
                        m["resolved_entity"]["entity_id"] == gold_spans[span])

    report.add_metric("golden_core_span_recall", "E2E", detected, gold_total,
                      slice_key="golden")
    report.add_metric("golden_gold_in_prediction_set", "E2E", in_set,
                      gold_total, slice_key="golden")
    report.add_metric("golden_top1_accuracy", "|mention", top_correct,
                      top_total, slice_key="golden")
    if resolved_total:
        report.add_metric("golden_resolved_precision", "|commit",
                          resolved_correct, resolved_total, slice_key="golden")
    return {
        "cases": len(cases),
        "gold_mentions": gold_total,
        "violations": violations,
    }

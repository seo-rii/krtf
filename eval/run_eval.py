"""KTRF V1 evaluation runner (spec §43 metrics, §44 release gate).

Usage: python -m eval.run_eval [glossary.yaml]

Writes eval/out/report.json and EVALUATION.md. Level A slices are measured
E2E against the deterministic pipeline; Level B slices use constrained
containment (§43.3 approximation: an overlapping mention whose prediction
set retains the gold entity counts as a candidate hit).
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from ktrf.conformance import generate_fixtures, run_fixtures
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .datagen import generate
from .golden import run_golden
from .metrics import EvalReport

ROOT = Path(__file__).resolve().parent.parent

RELEASE_GATE = {
    "conformance_failures_max": 0,  # REQ-LVL-002
    "golden_violations_max": 0,  # a single golden violation is a hard fail
    "level_a_core_span_recall_min_e2e": 0.995,  # §44 (point estimate)
    "level_a_gold_in_set_min_given_mention": 0.997,
    "resolved_precision_min_commit": 0.98,
    # CI-lower-bound gates (§43.8): point estimates on small n are not
    # evidence — the Wilson 95% lower bound must also clear these floors.
    # They are set to what the CURRENT sample size can support at 100%
    # observed; growing the eval set is the only way to tighten them.
    "level_a_core_span_recall_ci_lower_min": 0.98,
    "level_a_gold_in_set_ci_lower_min": 0.98,
    "resolved_precision_ci_lower_min": 0.96,
    # an always-abstaining system must not pass on vacuous precision
    "resolved_min_commits": 25,
    "forbidden_entity_hits_max": 0,
    "offset_invariant_failures_max": 0,
}


def _mention_entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def _cp(m: dict) -> tuple[int, int]:
    cp = m["span"]["codepoint"]
    return (cp["start"], cp["end"])


def run(glossary_path: str) -> dict:
    glossary = load_glossary(glossary_path)
    t0 = time.perf_counter()
    snap = compile_snapshot(glossary, run_conformance=False)
    compile_s = time.perf_counter() - t0

    report = EvalReport()

    # ---- conformance (failure count, kept apart from coverage: §3.5) ----
    fixtures = generate_fixtures(glossary)
    conf = run_fixtures(snap, fixtures)
    report.set_conformance(conf.total, conf.failed, conf.failures[:10])

    # ---- corpus metrics ----
    examples = generate(glossary)
    counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    resolved_total = resolved_correct = 0
    forbidden_hits = 0
    offset_failures = 0
    fast_a_total = fast_a_detected = 0
    latencies: list[float] = []

    for ex in examples:
        t1 = time.perf_counter()
        resp = resolve(snap, ex.text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        latencies.append(time.perf_counter() - t1)
        mentions = resp["mentions"]

        for m in mentions:
            cp = m["span"]["codepoint"]
            if ex.text[cp["start"]:cp["end"]] != m["surface"]:
                offset_failures += 1

        gold_by_span = {g.span: g for g in ex.gold}
        c = counters[ex.slice]
        for g in ex.gold:
            c["gold_total"] += 1
            exact_hit = next((m for m in mentions if _cp(m) == g.span), None)
            overlap_hits = [m for m in mentions
                            if _cp(m)[0] < g.span[1] and g.span[0] < _cp(m)[1]]
            if ex.level == "A":
                detected = exact_hit is not None
                in_set = detected and g.entity_id in _mention_entities(exact_hit)
            else:
                detected = bool(overlap_hits)
                in_set = any(g.entity_id in _mention_entities(m)
                             for m in overlap_hits)
            c["detected"] += int(detected)
            c["in_set_e2e"] += int(in_set)
            if detected:
                c["mention_cond_total"] += 1
                c["in_set_given_mention"] += int(in_set)

        for m in mentions:
            if m.get("link_decision") == "RESOLVED":
                span = _cp(m)
                eid = m["resolved_entity"]["entity_id"]
                if ex.expect_no_mention:
                    resolved_total += 1  # counts as an incorrect commit
                elif span in gold_by_span:
                    resolved_total += 1
                    resolved_correct += int(gold_by_span[span].entity_id == eid)
                # RESOLVED on non-gold spans of positive examples is not
                # counted: gold annotation there is partial (§38.1 UNLABELED)
            ids = _mention_entities(m)
            forbidden_hits += len(ids & set(ex.forbidden_entities))
            if ex.expect_no_mention and m.get("link_decision") == "RESOLVED":
                c["negative_resolved"] += 1

        if ex.level == "A" and ex.gold:
            fresp = resolve(snap, ex.text, mode="fast",
                            options={"return_all_mentions": True})
            fast_a_total += len(ex.gold)
            fast_spans = {_cp(m) for m in fresp["mentions"]}
            fast_a_detected += sum(g.span in fast_spans for g in ex.gold)

    # ---- aggregate ----
    a_slices = {s for s in counters
                if any(e.slice == s and e.level == "A" and e.gold
                       for e in examples)}
    b_slices = {s for s in counters
                if any(e.slice == s and e.level == "B" for e in examples)}

    def agg(slices, key):
        return sum(counters[s][key] for s in slices)

    report.add_metric("level_a_core_span_recall", "E2E",
                      agg(a_slices, "detected"), agg(a_slices, "gold_total"))
    report.add_metric("level_a_gold_in_prediction_set", "|mention",
                      agg(a_slices, "in_set_given_mention"),
                      agg(a_slices, "mention_cond_total"))
    report.add_metric("level_a_gold_in_prediction_set_e2e", "E2E",
                      agg(a_slices, "in_set_e2e"), agg(a_slices, "gold_total"))
    report.add_metric("level_b_gold_in_prediction_set", "E2E",
                      agg(b_slices, "in_set_e2e"), agg(b_slices, "gold_total"))
    report.add_metric("resolved_precision", "|commit",
                      resolved_correct, resolved_total)
    report.add_metric("fast_mode_core_span_recall", "E2E",
                      fast_a_detected, fast_a_total)

    for s in sorted(counters):
        c = counters[s]
        if c["gold_total"]:
            report.add_metric("core_span_recall", "E2E", c["detected"],
                              c["gold_total"], slice_key=s)
            report.add_metric("gold_in_prediction_set", "E2E",
                              c["in_set_e2e"], c["gold_total"], slice_key=s)

    golden = run_golden(snap, report)

    latencies.sort()
    perf = {
        "examples": len(examples),
        "compile_seconds": round(compile_s, 3),
        "resolve_p50_ms": round(1000 * latencies[len(latencies) // 2], 2),
        "resolve_p95_ms": round(1000 * latencies[int(len(latencies) * 0.95)], 2),
    }

    gate = compute_gate(
        conformance_failures=conf.failed,
        golden_violations=len(golden["violations"]),
        recall_metric=report.metrics[0],
        in_set_metric=report.metrics[1],
        resolved_correct=resolved_correct,
        resolved_total=resolved_total,
        forbidden_entity_hits=forbidden_hits,
        offset_invariant_failures=offset_failures,
    )

    return {
        "glossary": {"id": glossary.glossary_id, "version": glossary.version,
                     "bindings": len(glossary.alias_bindings)},
        "report": report.to_dict(),
        "golden": golden,
        "performance": perf,
        "release_gate": gate,
    }


def compute_gate(*, conformance_failures, golden_violations, recall_metric,
                 in_set_metric, resolved_correct, resolved_total,
                 forbidden_entity_hits, offset_invariant_failures) -> dict:
    """§44 release gate as a pure function so its edge cases are testable.

    Every criterion is an explicit named check; 0 commits yields precision
    ``None`` (never a vacuous 1.0) and fails the gate; point estimates must
    also clear Wilson-lower-bound floors (§43.8).
    """
    from .metrics import wilson_interval
    recall_m = recall_metric
    in_set_m = in_set_metric
    prec_ci_lo, _ = wilson_interval(resolved_correct, resolved_total)
    gate_values = {
        "conformance_failures": conformance_failures,
        "golden_violations": golden_violations,
        "level_a_core_span_recall_e2e": recall_m.value,
        "level_a_core_span_recall_ci_lower": round(recall_m.ci95[0], 4),
        "level_a_gold_in_set_given_mention": in_set_m.value,
        "level_a_gold_in_set_ci_lower": round(in_set_m.ci95[0], 4),
        # 0 commits => precision is undefined, NEVER vacuously 1.0
        "resolved_precision_commit": (round(resolved_correct / resolved_total, 4)
                                      if resolved_total else None),
        "resolved_precision_ci_lower": (round(prec_ci_lo, 4)
                                        if resolved_total else None),
        "resolved_commits": resolved_total,
        "forbidden_entity_hits": forbidden_entity_hits,
        "offset_invariant_failures": offset_invariant_failures,
    }
    # every criterion is an explicit named check so the report can show
    # per-row pass/fail honestly instead of a decorative checkmark
    gate_checks = {
        "conformance_failures":
            conformance_failures <= RELEASE_GATE["conformance_failures_max"],
        "golden_violations":
            gate_values["golden_violations"]
            <= RELEASE_GATE["golden_violations_max"],
        "level_a_core_span_recall":
            recall_m.value >= RELEASE_GATE["level_a_core_span_recall_min_e2e"]
            and recall_m.ci95[0]
            >= RELEASE_GATE["level_a_core_span_recall_ci_lower_min"],
        "level_a_gold_in_set":
            in_set_m.value
            >= RELEASE_GATE["level_a_gold_in_set_min_given_mention"]
            and in_set_m.ci95[0]
            >= RELEASE_GATE["level_a_gold_in_set_ci_lower_min"],
        "resolved_precision":
            resolved_total >= RELEASE_GATE["resolved_min_commits"]
            and gate_values["resolved_precision_commit"] is not None
            and gate_values["resolved_precision_commit"]
            >= RELEASE_GATE["resolved_precision_min_commit"]
            and prec_ci_lo >= RELEASE_GATE["resolved_precision_ci_lower_min"],
        "forbidden_entity_hits":
            forbidden_entity_hits
            <= RELEASE_GATE["forbidden_entity_hits_max"],
        "offset_invariant_failures":
            offset_invariant_failures
            <= RELEASE_GATE["offset_invariant_failures_max"],
    }
    return {"criteria": RELEASE_GATE, "values": gate_values,
            "checks": gate_checks, "pass": all(gate_checks.values())}


def write_markdown(result: dict, out_path: Path) -> None:
    r = result["report"]
    gate = result["release_gate"]
    perf = result["performance"]
    lines = [
        "# KTRF V1 평가 결과 (Evaluation Report)",
        "",
        f"대상: `{result['glossary']['id']}` v{result['glossary']['version']} "
        f"({result['glossary']['bindings']} bindings) — V1 symbolic core "
        "(Python reference implementation)",
        "",
        "모든 지표는 측정 조건(`E2E` / `|mention` / `|commit`)을 표기한다"
        " (REQ-EVAL-001). conformance는 §3.5에 따라 실패 **건수**로만 보고하며"
        " 커버리지 %와 합산하지 않는다 (REQ-LVL-003).",
        "",
        "## 1. Conformance (Level A 결정적 보장, §14.8)",
        "",
        f"- fixture 수: **{r['conformance']['total_fixtures']}**"
        " (§14.7 변형 카탈로그 × 활성 glossary 전 binding, 단일 조사 전수 +"
        " 연쇄 depth-2 대표 조합 포함)",
        f"- 실패 건수: **{r['conformance']['failure_count']}** (목표 0,"
        " 실패 1건 = release blocker)",
        "",
        "## 2. 품질 지표 (§43)",
        "",
        "| 지표 | 조건 | 값 | n | Wilson 95% CI |",
        "|---|---|---:|---:|---|",
    ]
    for m in r["metrics"]:
        cond = m["conditioning"].replace("|", "\\|")
        lines.append(
            f"| {m['name']} | {cond} | {m['value']:.4f} "
            f"| {m['hits']}/{m['total']} | [{m['ci95'][0]:.4f}, {m['ci95'][1]:.4f}] |")
    lines += ["", "### Slice별 (E2E core-span recall / gold-in-set)", "",
              "| slice | recall | gold-in-set |", "|---|---:|---:|"]
    for s, ms in sorted(r["slices"].items()):
        vals = {m["name"]: m for m in ms}
        rec = vals.get("core_span_recall") or vals.get("golden_core_span_recall")
        gis = (vals.get("gold_in_prediction_set")
               or vals.get("golden_gold_in_prediction_set"))
        if rec and gis:
            lines.append(f"| {s} | {rec['hits']}/{rec['total']} "
                         f"| {gis['hits']}/{gis['total']} |")
    g = result["golden"]
    lines += [
        "",
        "## 3. 골든 셋 (§48.6 축소판, 수작업 문장)",
        "",
        f"- {g['cases']} 문장, {g['gold_mentions']} gold mentions"
        f" — 위반 {len(g['violations'])}건",
    ]
    for m in r["slices"].get("golden", []):
        lines.append(f"- {m['name']} ({m['conditioning']}): "
                     f"**{m['value']:.3f}** ({m['hits']}/{m['total']})")
    lines += [
        "",
        "## 4. Release Gate (§44)",
        "",
        "| 기준 | 목표 | 실측 | 판정 |",
        "|---|---|---|---|",
    ]
    crit = gate["criteria"]
    vals = gate["values"]
    checks = gate.get("checks", {})
    rows = [
        ("conformance failures", f"≤ {crit['conformance_failures_max']}",
         vals["conformance_failures"], "conformance_failures"),
        ("golden violations", f"≤ {crit['golden_violations_max']}",
         vals["golden_violations"], "golden_violations"),
        ("Level A core-span recall (E2E)",
         f"≥ {crit['level_a_core_span_recall_min_e2e']} "
         f"(CI하한 ≥ {crit['level_a_core_span_recall_ci_lower_min']})",
         f"{vals['level_a_core_span_recall_e2e']} "
         f"(CI하한 {vals['level_a_core_span_recall_ci_lower']})",
         "level_a_core_span_recall"),
        ("Level A gold-in-set (\\|mention)",
         f"≥ {crit['level_a_gold_in_set_min_given_mention']} "
         f"(CI하한 ≥ {crit['level_a_gold_in_set_ci_lower_min']})",
         f"{vals['level_a_gold_in_set_given_mention']} "
         f"(CI하한 {vals['level_a_gold_in_set_ci_lower']})",
         "level_a_gold_in_set"),
        ("RESOLVED precision (\\|commit)",
         f"≥ {crit['resolved_precision_min_commit']}, commits ≥ "
         f"{crit['resolved_min_commits']}, "
         f"CI하한 ≥ {crit['resolved_precision_ci_lower_min']}",
         f"{vals['resolved_precision_commit'] if vals['resolved_precision_commit'] is not None else 'N/A (0 commits)'} "
         f"({vals['resolved_commits']} commits, "
         f"CI하한 {vals['resolved_precision_ci_lower']})",
         "resolved_precision"),
        ("forbidden-entity hits", f"≤ {crit['forbidden_entity_hits_max']}",
         vals["forbidden_entity_hits"], "forbidden_entity_hits"),
        ("offset invariant failures",
         f"≤ {crit['offset_invariant_failures_max']}",
         vals["offset_invariant_failures"], "offset_invariant_failures"),
    ]
    for name, target, val, key in rows:
        mark = "✅" if checks.get(key) else "❌"
        lines.append(f"| {name} | {target} | {val} | {mark} |")
    lines += [
        "",
        f"**게이트 판정: {'PASS' if gate['pass'] else 'FAIL'}**",
        "",
        "## 5. 성능 (참고치, Python 구현)",
        "",
        f"- 평가 예제: {perf['examples']}건, compile "
        f"{perf['compile_seconds']}s",
        f"- resolve(commit) p50 {perf['resolve_p50_ms']}ms / p95 "
        f"{perf['resolve_p95_ms']}ms",
    ]
    bench_path = ROOT / "eval" / "out" / "benchmark.json"
    if bench_path.exists():
        bench = json.loads(bench_path.read_text(encoding="utf-8"))
        lines += ["", "### 규모 벤치마크 (synthetic glossary, §53 축소판)", "",
                  "| entities | bindings | compile | conformance | commit p50/p95 | fast p50/p95 |",
                  "|---:|---:|---:|---|---|---|"]
        for b in bench:
            conf = (f"{b['conformance']['fixtures']} fixtures, "
                    f"{b['conformance']['failed']} failed, "
                    f"{b['conformance']['fixtures_per_sec']}/s"
                    if b["conformance"] else "(skipped)")
            lines.append(
                f"| {b['entities']} | {b['bindings']} | {b['compile_seconds']}s "
                f"| {conf} | {b['latency']['commit']['p50_ms']} / "
                f"{b['latency']['commit']['p95_ms']}ms "
                f"| {b['latency']['fast']['p50_ms']} / "
                f"{b['latency']['fast']['p95_ms']}ms |")
        lines += [
            "",
            "fast 모드는 결정적 경로만 실행하므로(§26.1) sub-millisecond로 동작"
            "한다. commit 모드의 지연은 fuzzy window/Pass 2의 Python 선형 탐색이"
            " 지배하며, 프로덕션 Rust core(§34) 대상 최적화 항목이다.",
        ]
    lines += [
        "",
        "## 6. 해석과 한계",
        "",
        "- Level A 지표가 100%인 것은 datagen이 구현과 동일한 §14.7/§16 카탈로그"
        "에서 유도되기 때문이다 — 이는 conformance(구현 결함 검출)의 성격이며,"
        " 실제 corpus 분포 커버리지(§3.5의 통계 목표)와는 다르다. 분포 커버리지는"
        " 실 데이터 golden set 확장(§48.6) 이후에만 주장할 수 있다.",
        "- 골든 셋은 생성기와 독립적으로 작성한 문장(문장 중간 위치, 동형 충돌,"
        " 문맥 의존 sense, 부정 예)이며 V1의 실질 동작 점검에 해당한다."
        " 다만 21문장 규모는 §48.6의 slice당 n≥200 기준에 크게 못 미치는"
        " 스모크 수준이다.",
        "- calibrated_probability는 V1 휴리스틱 보수 보정이며(§48.1) conformal"
        " 보장(§25)은 M4 범위다. prediction-set coverage 지표는 라벨 축적"
        " (Correction API, M3) 전까지 보고하지 않는다.",
        "",
        "*generated by `python -m eval.run_eval` — 재현 가능*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    glossary_path = sys.argv[1] if len(sys.argv) > 1 else str(
        ROOT / "examples" / "demo_glossary.yaml")
    result = run(glossary_path)
    out_dir = ROOT / "eval" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    write_markdown(result, ROOT / "reports" / "EVALUATION.md")
    print(json.dumps(result["release_gate"], indent=2))
    print(f"\nfull report: {out_dir / 'report.json'}")
    print(f"markdown: {ROOT / 'reports' / 'EVALUATION.md'}")


if __name__ == "__main__":
    main()

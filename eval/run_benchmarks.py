"""Comprehensive anti-overfitting benchmark runner.

Usage: python -m eval.run_benchmarks [--quick]

Runs, per glossary size × seed:
  boundary traps · composed transforms · out-of-catalog tails ·
  negative corpus · fuzzy distractors · multi-sense discipline ·
  unicode fuzz · pathological inputs
plus a calibration holdout-coverage benchmark, and aggregates across seeds.

Writes eval/out/benchmarks.json and BENCHMARKS.md.

Hard gates (violations of Level A / commit contracts — must be 0 at every
size and seed): boundary-trap hits, sense loss, arbitrary multi-sense
commits, wrong-sibling commits, crashes, offset failures.
Soft metrics (statistical, reported with values): composed-transform recall,
negative-corpus FP rate, fuzzy distractor recovery, OOC retention.
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from ktrf.calibration import TrainingExample, fit_calibrator
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot

from .adversarial import (
    run_boundary_traps,
    run_composed_transforms,
    run_fuzzy_distractors,
    run_multisense_discipline,
    run_negative_corpus,
    run_ooc_tails,
)
from .fuzzing import run_pathological, run_unicode_fuzz
from .metrics import wilson_interval
from .synthetic import build_synthetic_glossary, collision_stats

ROOT = Path(__file__).resolve().parent.parent

SIZES = [200, 1000, 3000]
SEEDS = [1, 2, 3]
QUICK_SIZES = [200]
QUICK_SEEDS = [1]


def run_calibration_holdout(rng: random.Random) -> dict:
    """Fit/holdout split coverage across alphas and skewed group sizes."""
    def make(n, group, pos_mu, neg_mu, spread):
        out = []
        for _ in range(n):
            out.append(TrainingExample(
                pos_mu + spread * (rng.random() - 0.5), group, 1))
            out.append(TrainingExample(
                neg_mu + spread * (rng.random() - 0.5), group, 0))
        return out

    pool = (make(400, "exact|multi", 1.0, 0.55, 0.5)
            + make(150, "fuzzy|multi", 0.8, 0.45, 0.6)
            + make(20, "dense|multi", 0.6, 0.35, 0.6))
    rng.shuffle(pool)
    cut = int(len(pool) * 0.7)
    fit_set, holdout = pool[:cut], pool[cut:]
    results = {}
    for alpha in (0.05, 0.1):
        cal = fit_calibrator(fit_set, alpha=alpha, n_min=80)
        per_group: dict[str, list[int]] = {}
        for e in holdout:
            if e.label != 1:
                continue
            inc, _ = cal.in_prediction_set(
                cal.calibrate_marginal(e.ranking_score), e.group)
            per_group.setdefault(e.group, []).append(int(inc))
        overall = [x for lst in per_group.values() for x in lst]
        results[f"alpha_{alpha}"] = {
            "target": 1 - alpha,
            "holdout_coverage": round(sum(overall) / len(overall), 4),
            "n_holdout": len(overall),
            "per_group": {g: round(sum(l) / len(l), 3)
                          for g, l in sorted(per_group.items())},
        }
    return {"name": "calibration_holdout", "results": results,
            "interpretation": "held-out coverage must be ≥ ~target (1-α); "
                              "fit and holdout are disjoint"}


def run_one(n_entities: int, seed: int, quick: bool) -> dict:
    scale = 0.4 if quick else 1.0
    g_dict, meta = build_synthetic_glossary(n_entities, seed=seed)
    glossary = load_glossary(g_dict)
    t0 = time.perf_counter()
    snap = compile_snapshot(glossary, strict=False, run_conformance=False)
    compile_s = time.perf_counter() - t0
    rng = random.Random(seed * 1000 + n_entities)

    suites = {}
    traps = run_boundary_traps(snap, meta, rng,
                               max_aliases=int(120 * scale))
    suites["boundary_traps"] = traps.to_dict()
    composed = run_composed_transforms(snap, meta, rng,
                                       max_cases=int(150 * scale))
    suites["composed_transforms"] = composed.to_dict()
    retention, overcommit = run_ooc_tails(snap, meta, rng,
                                          max_cases=int(100 * scale))
    suites["ooc_tail_retention"] = retention.to_dict()
    suites["ooc_tail_overcommit"] = overcommit.to_dict()
    suites["negative_corpus"] = run_negative_corpus(
        snap, meta, rng, n_sentences=int(200 * scale))
    suites["fuzzy_distractors"] = run_fuzzy_distractors(
        snap, meta, rng, max_pairs=int(60 * scale))
    suites["multisense_discipline"] = run_multisense_discipline(
        snap, meta, rng, max_aliases=int(80 * scale))
    suites["unicode_fuzz"] = run_unicode_fuzz(
        snap, meta, rng, n_cases=int(200 * scale))
    suites["pathological"] = run_pathological(snap, meta)

    hard_violations = {
        "boundary_trap_hits": traps.hits,
        "sense_loss": suites["multisense_discipline"]["sense_loss"],
        "arbitrary_multisense_commits":
            suites["multisense_discipline"]["arbitrary_commits"],
        "wrong_sibling_commits":
            suites["fuzzy_distractors"]["wrong_sibling_commits"],
        "fuzz_crashes": suites["unicode_fuzz"]["crashes"],
        "offset_failures": suites["unicode_fuzz"]["offset_invariant_failures"],
        "pathological_crashes": sum(
            1 for c in suites["pathological"]["cases"].values()
            if c.get("crashed")),
    }
    return {
        "entities": n_entities,
        "seed": seed,
        "bindings": len(g_dict["alias_bindings"]),
        "collision_stats": collision_stats(meta),
        "compile_seconds": round(compile_s, 2),
        "suites": suites,
        "hard_violations": hard_violations,
        "hard_pass": all(v == 0 for v in hard_violations.values()),
    }


def aggregate(runs: list[dict]) -> dict:
    def pool(path_get):
        hits = total = 0
        for r in runs:
            h, t = path_get(r)
            hits += h
            total += t
        lo, hi = wilson_interval(hits, total)
        return {"hits": hits, "total": total,
                "rate": round(hits / total, 4) if total else None,
                "ci95": [round(lo, 4), round(hi, 4)]}

    agg = {
        "runs": len(runs),
        "hard_pass_all": all(r["hard_pass"] for r in runs),
        "hard_violations_total": {
            k: sum(r["hard_violations"][k] for r in runs)
            for k in runs[0]["hard_violations"]
        },
        "composed_transform_recall": pool(
            lambda r: (r["suites"]["composed_transforms"]["hits"],
                       r["suites"]["composed_transforms"]["total"])),
        "ooc_tail_retention": pool(
            lambda r: (r["suites"]["ooc_tail_retention"]["hits"],
                       r["suites"]["ooc_tail_retention"]["total"])),
        "ooc_tail_overcommit": pool(
            lambda r: (r["suites"]["ooc_tail_overcommit"]["hits"],
                       r["suites"]["ooc_tail_overcommit"]["total"])),
        "fuzzy_recovery": pool(
            lambda r: (
                round((r["suites"]["fuzzy_distractors"]["recovered_rate"] or 0)
                      * r["suites"]["fuzzy_distractors"]["total"]),
                r["suites"]["fuzzy_distractors"]["total"])),
    }
    fp = [r["suites"]["negative_corpus"]["resolved_fp_per_1k_chars"]
          for r in runs]
    agg["negative_fp_per_1k_chars"] = {
        "max": max(fp), "mean": round(sum(fp) / len(fp), 3)}
    return agg


def write_markdown(payload: dict, out_path: Path) -> None:
    lines = [
        "# KTRF 확장 벤치마크 (Anti-Overfitting Benchmarks)",
        "",
        "데모 glossary와 카탈로그 유래 datagen은 구현과 같은 카탈로그에서 나오므로"
        " 과적합을 감지할 수 없다. 본 벤치마크는 **독립 생성된 적대적 스위트**를"
        " 규모(200/1000/3000 entities) × 시드(3종)로 실행한다."
        " 재현: `python -m eval.run_benchmarks`.",
        "",
        "## 합성 glossary 구조",
        "",
        "| entities | seed | bindings | 한글 다의 약어 | 최대 sense | Latin 다의 | near-miss | nested |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in payload["runs"]:
        c = r["collision_stats"]
        lines.append(
            f"| {r['entities']} | {r['seed']} | {r['bindings']} "
            f"| {c['hangul_multi_sense']} | {c['max_hangul_senses']} "
            f"| {c['latin_multi_sense']} | {c['near_miss_pairs']} "
            f"| {c['nested_pairs']} |")
    agg = payload["aggregate"]
    hv = agg["hard_violations_total"]
    lines += [
        "",
        "## Hard gates (Level A / commit 계약 위반 — 전 시드·규모 합산, 목표 0)",
        "",
        "| 항목 | 합산 위반 | 판정 |",
        "|---|---:|---|",
    ]
    for k, v in hv.items():
        lines.append(f"| {k} | {v} | {'✅' if v == 0 else '❌'} |")
    lines += [
        "",
        f"**전체 hard gate: {'PASS' if agg['hard_pass_all'] else 'FAIL'}**",
        "",
        "## Soft metrics (통계 지표, 시드 합산 + Wilson 95% CI)",
        "",
        "| 지표 | 값 | n | CI95 | 해석 |",
        "|---|---:|---:|---|---|",
    ]
    ct = agg["composed_transform_recall"]
    lines.append(f"| composed-transform recall (E2E) | {ct['rate']} "
                 f"| {ct['hits']}/{ct['total']} | {ct['ci95']} "
                 f"| 카탈로그 변형 3중 합성(접두+공백+조사연쇄 / 전각+소문자+연쇄) |")
    rt = agg["ooc_tail_retention"]
    lines.append(f"| OOC-tail core retention | {rt['rate']} "
                 f"| {rt['hits']}/{rt['total']} | {rt['ci95']} "
                 f"| 미등록 tail에서 core 후보 보존 (§16.5, 높을수록 좋음) |")
    oc = agg["ooc_tail_overcommit"]
    lines.append(f"| OOC-tail overcommit | {oc['rate']} "
                 f"| {oc['hits']}/{oc['total']} | {oc['ci95']} "
                 f"| 미등록 tail에서 RESOLVED 남발 (낮을수록 좋음) |")
    fz = agg["fuzzy_recovery"]
    lines.append(f"| fuzzy 1-jamo recovery (near-miss pairs) | {fz['rate']} "
                 f"| {fz['hits']}/{fz['total']} | {fz['ci95']} "
                 f"| 형제 entity가 있는 상황의 오타 복구 |")
    fp = agg["negative_fp_per_1k_chars"]
    lines.append(f"| negative-corpus RESOLVED FP /1k chars | mean {fp['mean']}, "
                 f"max {fp['max']} | — | — | 용어 없는 문장에서의 확정 오탐 |")
    lines += ["", "## Unicode fuzz / pathological (규모·시드별)", "",
              "| entities/seed | fuzz crashes | offset fails | 카탈로그 변형 recall "
              "| particle bomb | 64KB doc | degraded |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for r in payload["runs"]:
        uf = r["suites"]["unicode_fuzz"]
        pc = r["suites"]["pathological"]["cases"]
        bomb = pc.get("particle_bomb", {})
        doc = pc.get("near_limit_document", {})
        lines.append(
            f"| {r['entities']}/s{r['seed']} | {uf['crashes']} "
            f"| {uf['offset_invariant_failures']} "
            f"| {uf['catalog_variant_recall']} "
            f"| {bomb.get('ms', '—')}ms | {doc.get('ms', '—')}ms "
            f"| {doc.get('degraded', '—')} |")
    cal = payload["calibration_holdout"]["results"]
    lines += ["", "## Calibration holdout coverage (fit/holdout 분리)", "",
              "| α | 목표 | holdout coverage | n | 그룹별 |", "|---|---|---|---:|---|"]
    for k, v in cal.items():
        lines.append(f"| {k.split('_')[1]} | {v['target']} "
                     f"| {v['holdout_coverage']} | {v['n_holdout']} "
                     f"| {v['per_group']} |")
    lines += [
        "",
        "## 해석",
        "",
        "- **Hard gate 0건**은 boundary/다의성 보존/offset 계약이 규모·충돌 밀도와"
        " 무관하게 유지됨을 뜻한다 — 이것이 Level A '결정적 보장'의 실측 검증이다.",
        "- Soft 지표는 카탈로그 밖 일반화 능력의 근사치다. composed recall과 fuzzy"
        " recovery는 100%가 목표가 아니라 추적 대상이며, 회귀 감지 기준선으로"
        " 사용한다.",
        "- 합성 corpus는 실제 조직 문서 분포가 아니다. §3.5의 분포 커버리지 주장은"
        " 여전히 실 데이터 golden set(§48.6) 축적 이후에만 가능하다.",
        "",
        f"*총 소요: {payload['elapsed_seconds']}s — generated by "
        "`python -m eval.run_benchmarks`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    quick = "--quick" in sys.argv
    sizes = QUICK_SIZES if quick else SIZES
    seeds = QUICK_SEEDS if quick else SEEDS
    t0 = time.perf_counter()
    runs = []
    for n in sizes:
        for seed in seeds:
            print(f"running entities={n} seed={seed} ...", flush=True)
            runs.append(run_one(n, seed, quick))
    payload = {
        "runs": runs,
        "aggregate": aggregate(runs),
        "calibration_holdout": run_calibration_holdout(random.Random(42)),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmarks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "BENCHMARKS.md")
    agg = payload["aggregate"]
    print(json.dumps({"hard_pass_all": agg["hard_pass_all"],
                      "hard_violations": agg["hard_violations_total"],
                      "composed_recall": agg["composed_transform_recall"],
                      "negative_fp": agg["negative_fp_per_1k_chars"]},
                     indent=2))
    print(f"\nwrote {out / 'benchmarks.json'} and {ROOT / 'BENCHMARKS.md'}")


if __name__ == "__main__":
    main()

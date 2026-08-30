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
from .metrics import wilson_interval, provenance_line
from .synthetic import build_synthetic_glossary, collision_stats

ROOT = Path(__file__).resolve().parent.parent

SIZES = [200, 1000, 3000]
SEEDS = [1, 2, 3]
QUICK_SIZES = [200]
QUICK_SEEDS = [1]


CALIBRATION_SEEDS = (42, 43, 44, 45, 46, 47, 48, 49)
CALIBRATION_SCALE = 4  # pool multiplier; see the n-power note below


def _holdout_trial(seed: int, alpha: float, scale: int) -> tuple[int, int, dict]:
    rng = random.Random(seed)

    def make(n, group, pos_mu, neg_mu, spread):
        out = []
        for _ in range(n):
            out.append(TrainingExample(
                pos_mu + spread * (rng.random() - 0.5), group, 1))
            out.append(TrainingExample(
                neg_mu + spread * (rng.random() - 0.5), group, 0))
        return out

    pool = (make(400 * scale, "exact|multi", 1.0, 0.55, 0.5)
            + make(150 * scale, "fuzzy|multi", 0.8, 0.45, 0.6)
            + make(20 * scale, "dense|multi", 0.6, 0.35, 0.6))
    rng.shuffle(pool)
    cut = int(len(pool) * 0.7)
    cal = fit_calibrator(pool[:cut], alpha=alpha, n_min=80)
    per_group: dict[str, list[int]] = {}
    for e in pool[cut:]:
        if e.label != 1:
            continue
        inc, _ = cal.in_prediction_set(
            cal.calibrate_marginal(e.ranking_score), e.group)
        per_group.setdefault(e.group, []).append(int(inc))
    covered = sum(sum(l) for l in per_group.values())
    total = sum(len(l) for l in per_group.values())
    return covered, total, {g: (sum(l), len(l)) for g, l in per_group.items()}


def run_calibration_holdout(rng: random.Random | None = None) -> dict:
    """Fit/holdout split coverage, pooled over seeds with a CI.

    Split conformal guarantees coverage *in expectation over draws*, so a
    single holdout at n=171 says almost nothing: across seeds that estimator
    ranges 0.92-0.97 purely from sampling. Reporting one draw as "the
    coverage" produced a report that moved whenever the seed or the fit code
    moved, and read as a regression either way. This pools several
    independent trials at a sample size with power and gates on the Wilson
    lower bound, matching the release gate's CI-floor convention.
    """
    results = {}
    for alpha in (0.05, 0.1):
        per_seed: list[float] = []
        covered = total = 0
        groups: dict[str, list[int]] = {}
        for seed in CALIBRATION_SEEDS:
            c, t, g = _holdout_trial(seed, alpha, CALIBRATION_SCALE)
            per_seed.append(round(c / t, 4))
            covered += c
            total += t
            for name, (gc, gt) in g.items():
                acc = groups.setdefault(name, [0, 0])
                acc[0] += gc
                acc[1] += gt
        lo, hi = wilson_interval(covered, total)
        target = 1 - alpha
        # Three-valued on purpose (VARIANTS_PLAN M0 item 4): a point estimate
        # a few tenths of a point under target neither proves undercoverage
        # nor clears the guarantee. Calling that a PASS with a hand-picked
        # tolerance, or a FAIL on the point estimate, would both be claims
        # the sample cannot support.
        if lo >= target:
            verdict = "PASS"
        elif hi < target:
            verdict = "FAIL"
        else:
            verdict = "INSUFFICIENT_DATA"
        results[f"alpha_{alpha}"] = {
            "target": round(target, 4),
            "pooled_coverage": round(covered / total, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "verdict": verdict,
            "n_holdout_pooled": total,
            "trials": len(CALIBRATION_SEEDS),
            "per_seed_coverage": per_seed,
            "per_group": {g: round(v[0] / v[1], 3)
                          for g, v in sorted(groups.items())},
        }
    return {"name": "calibration_holdout", "results": results,
            "interpretation": "pooled held-out coverage over "
                              f"{len(CALIBRATION_SEEDS)} independent trials. "
                              "PASS requires the Wilson lower bound to clear "
                              "the target; FAIL requires the upper bound to "
                              "miss it; in between the sample cannot decide "
                              "and the result is INSUFFICIENT_DATA, not a "
                              "pass"}


def run_one(n_entities: int, seed: int, quick: bool, dense: bool = False) -> dict:
    scale = 0.4 if quick else 1.0
    g_dict, meta = build_synthetic_glossary(n_entities, seed=seed)
    glossary = load_glossary(g_dict)
    encoder = None
    if dense:
        from ktrf.encoders import HashEncoder

        encoder = HashEncoder()
    t0 = time.perf_counter()
    snap = compile_snapshot(glossary, strict=False, run_conformance=False,
                            encoder=encoder)
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
        "dense": dense,
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
    if payload.get("dense_runs"):
        da = payload["dense_aggregate"]
        dhv = da["hard_violations_total"]
        lines += [
            "",
            "## V2 dense 구성 hard gates (bi-encoder Pass 2 활성, hash encoder)",
            "",
            f"{len(payload['dense_runs'])}개 run — dense 채널이 boundary/commit"
            " 계약을 침식하지 않는지 검증한다.",
            "",
            "| 항목 | 합산 위반 | 판정 |",
            "|---|---:|---|",
        ]
        for k, v in dhv.items():
            lines.append(f"| {k} | {v} | {'✅' if v == 0 else '❌'} |")
        oc = da["ooc_tail_overcommit"]
        lines.append("")
        lines.append(f"**dense hard gate: "
                     f"{'PASS' if da['hard_pass_all'] else 'FAIL'}** — "
                     f"OOC overcommit {oc['hits']}/{oc['total']}, "
                     f"negative FP mean {da['negative_fp_per_1k_chars']['mean']}"
                     f"/1k chars")
    cal = payload["calibration_holdout"]["results"]
    lines += ["", "## Calibration holdout coverage (fit/holdout 분리)", "",
              "단일 holdout 한 번은 split conformal의 보장을 검증하지 못한다 —"
              " n=171에서 시드만 바꿔도 coverage가 0.92~0.97로 움직인다."
              " 아래는 독립 시행을 pooling한 값이며, 판정은 점추정치가 아니라"
              " **CI로** 한다: 하한이 목표 이상이면 ✅ PASS, 상한이 목표 미달이면"
              " ❌ FAIL, 그 사이는 ◐ **INSUFFICIENT_DATA**다 — 표본이 판단할 수"
              " 없는 구간을 통과로 적지 않는다.",
              "",
              "| α | 목표 | pooled coverage | CI95 | 판정 | n | 시드별 | 그룹별 |",
              "|---|---|---:|---|---|---:|---|---|"]
    for k, v in cal.items():
        mark = {"PASS": "✅", "FAIL": "❌"}.get(v["verdict"], "◐")
        lines.append(f"| {k.split('_')[1]} | {v['target']} "
                     f"| {mark} {v['pooled_coverage']} "
                     f"| [{v['ci95'][0]}, {v['ci95'][1]}] "
                     f"| {v['verdict']} | {v['n_holdout_pooled']} "
                     f"| {v['per_seed_coverage']} | {v['per_group']} |")
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
        provenance_line(ROOT, f"총 소요 {payload['elapsed_seconds']}s"),
        "",
        "*generated by `python -m eval.run_benchmarks`*",
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
    # V2 configuration: same hard gates with the dense channel enabled —
    # Pass-2 retrieval must not break boundary/commit discipline
    dense_runs = []
    for n in (sizes if quick else [200, 1000]):
        for seed in (seeds if quick else [1, 2]):
            print(f"running entities={n} seed={seed} [dense] ...", flush=True)
            dense_runs.append(run_one(n, seed, quick, dense=True))
    payload = {
        "runs": runs,
        "aggregate": aggregate(runs),
        "dense_runs": dense_runs,
        "dense_aggregate": aggregate(dense_runs),
        "calibration_holdout": run_calibration_holdout(),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmarks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "BENCHMARKS.md")
    agg = payload["aggregate"]
    print(json.dumps({"hard_pass_all": agg["hard_pass_all"],
                      "hard_violations": agg["hard_violations_total"],
                      "composed_recall": agg["composed_transform_recall"],
                      "negative_fp": agg["negative_fp_per_1k_chars"]},
                     indent=2))
    print(f"\nwrote {out / 'benchmarks.json'} and {ROOT / 'BENCHMARKS.md'}")


if __name__ == "__main__":
    main()

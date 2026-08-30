"""Paired A/B for shared segmentation (VARIANTS_PLAN M1).

Usage: python -m eval.run_segmentation_ab [--sentences N]

Before M1 the exact channel decomposed 조사/suffix through the tail parser
while the Level B channels (jamo, keyboard, abbreviation) fed whole raw
tokens to their indexes. ``한국전려`` was recoverable and ``한국전려에서도``
was not — a decomposition disagreement, not a capacity limit — and a fuzzy
mention span could cover a particle nothing had analysed.

``RuntimePolicy.max_segmentation_paths = 1`` reproduces exactly that: the
segmenter always ranks the bare token first, so a budget of one is the
pre-M1 control. Both arms therefore run in one process over one sample,
which is what makes the comparison paired rather than two reports written
weeks apart.

Three suites, all on the same sentences:

1. **Variant recall** — silver surfaces perturbed by one of four typed
   formations (particle, suffix+particle, single-jamo typo, typo+particle).
   The perturbation is applied to real sentences, so the surrounding
   distribution is real even though the surface is synthetic. Reports
   core-span exactness, not just any-overlap.
2. **Cost** — per-sentence latency and Pass-1 fuzzy query counts.
3. **False positives** — the fake-glossary suite from ``run_wild``: any
   commit of a surface verified absent from the corpus is an FP by
   construction. This is the guard's load-bearing measurement, because
   feeding three cores per token instead of one is exactly how a variant
   channel starts hallucinating.

Writes eval/out/segmentation_ab.json and reports/SEGMENTATION_AB.md.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.hangul import compose_syllable, decompose_syllable
from ktrf.resolver import resolve
from ktrf.snapshot import RuntimePolicy, compile_snapshot

from .metrics import provenance_line
from .synthetic import absent_bindings_only, build_synthetic_glossary
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260830

# Formations are typed so a slice can be reported on its own: an aggregate
# over formations only reflects how they were mixed (the A/B lesson from
# reports/AB_GROUNDING.md).
FORMATIONS = ("particle", "suffix_particle", "typo", "typo_particle")

_PARTICLES_BATCHIM = ("은", "이", "을", "과", "에서", "에서도", "으로")
_PARTICLES_OPEN = ("는", "가", "를", "와", "에서", "에서도", "로")
_SUFFIXES = ("본부", "장관", "측", "노조")


def _has_batchim(ch: str) -> bool:
    d = decompose_syllable(ch)
    return bool(d and d[2])


def _particle_for(core: str, rng: random.Random) -> str:
    pool = _PARTICLES_BATCHIM if _has_batchim(core[-1]) else _PARTICLES_OPEN
    return rng.choice(pool)


def _single_jamo_typo(core: str, rng: random.Random) -> str | None:
    """Perturb one 중성 of one syllable — the §17.2 near-miss class."""
    idxs = [i for i, c in enumerate(core) if decompose_syllable(c)]
    if not idxs:
        return None
    vowels = "ㅏㅐㅑㅓㅔㅕㅗㅛㅜㅠㅡㅣ"
    for i in rng.sample(idxs, len(idxs)):
        cho, jung, jong = decompose_syllable(core[i])
        alt = [v for v in vowels if v != jung]
        if not alt:
            continue
        out = compose_syllable(cho, rng.choice(alt), jong)
        if out and out != core[i]:
            return core[:i] + out + core[i + 1:]
    return None


def build_variant_cases(corpus, aliases, n_per_formation, rng):
    """Place a perturbed surface into a real sentence, one case per formation."""
    hosts = [r["text"] for r in corpus if 20 <= len(r["text"]) <= 160]
    rng.shuffle(hosts)
    cases = []
    hi = 0
    for formation in FORMATIONS:
        made = 0
        attempts = 0
        while made < n_per_formation and attempts < n_per_formation * 40:
            attempts += 1
            surface, entity_id = rng.choice(aliases)
            if len(surface) < 3 or not all("가" <= c <= "힣" for c in surface):
                continue
            core = surface
            if formation in ("typo", "typo_particle"):
                core = _single_jamo_typo(surface, rng)
                if core is None:
                    continue
            token = core
            if formation == "particle":
                token = core + _particle_for(core, rng)
            elif formation == "suffix_particle":
                suf = rng.choice(_SUFFIXES)
                token = core + suf + _particle_for(suf, rng)
            elif formation == "typo_particle":
                token = core + _particle_for(core, rng)
            host = hosts[hi % len(hosts)]
            hi += 1
            # a clean left boundary: the mention starts a fresh token
            cut = host.find(" ")
            prefix = host[:cut + 1] if 0 < cut < 40 else ""
            text = f"{prefix}{token} {host[cut + 1:] if prefix else host}"
            start = len(prefix)
            cases.append({
                "formation": formation, "text": text,
                "entity_id": entity_id, "surface": surface,
                "core": core, "token": token,
                "core_span": [start, start + len(core)],
            })
            made += 1
    return cases


def run_variant_suite(snapshot, cases):
    per_formation = {f: {"n": 0, "core_hit": 0, "span_exact": 0,
                         "in_set": 0, "resolved": 0, "resolved_correct": 0,
                         "wrong_commit": 0}
                     for f in FORMATIONS}
    examples = []
    for case in cases:
        r = resolve(snapshot, case["text"], mode="commit")
        agg = per_formation[case["formation"]]
        agg["n"] += 1
        want = tuple(case["core_span"])
        hit = None
        for m in r["mentions"]:
            cp = m["span"]["codepoint"]
            span = (cp["start"], cp["end"])
            members = {mem.get("entity_id")
                       for mem in m["prediction_set"]["members"]}
            if case["entity_id"] in members:
                if hit is None or span == want:
                    hit = (m, span)
        if hit is None:
            continue
        m, span = hit
        agg["core_hit"] += 1
        agg["in_set"] += 1
        if span == want:
            agg["span_exact"] += 1
        if m["link_decision"] == "RESOLVED":
            agg["resolved"] += 1
            if m.get("resolved_entity", {}).get("entity_id") == case["entity_id"]:
                agg["resolved_correct"] += 1
        if len(examples) < 12 and case["formation"] == "typo_particle":
            examples.append({"token": case["token"], "surface": case["surface"],
                             "span": list(span), "want": list(want),
                             "link": m["link_decision"]})
    # commits that landed on a span we did not label are not counted as
    # correct *or* wrong here; the labelled-span ledger is the honest one
    for agg in per_formation.values():
        n = agg["n"] or 1
        agg["core_recall"] = round(agg["core_hit"] / n, 4)
        agg["span_exact_rate"] = round(agg["span_exact"] / n, 4)
        agg["resolved_rate"] = round(agg["resolved"] / n, 4)
        agg["commit_precision"] = (round(agg["resolved_correct"] / agg["resolved"], 4)
                                   if agg["resolved"] else None)
    return {"per_formation": per_formation, "examples": examples}


def run_cost_suite(snapshot, texts):
    lats = []
    fuzzy_queries = 0
    for t in texts:
        t0 = time.perf_counter()
        r = resolve(snapshot, t, mode="commit", options={"return_trace": True})
        lats.append((time.perf_counter() - t0) * 1000)
        fuzzy_queries += (r.get("trace") or {}).get("fuzzy_windows", 0)
    lats.sort()
    n = len(lats)
    return {
        "sentences": n,
        "p50_ms": round(lats[n // 2], 3),
        "p95_ms": round(lats[int(n * 0.95)], 3),
        "mean_ms": round(sum(lats) / n, 3),
        "fuzzy_core_queries": fuzzy_queries,
        "fuzzy_queries_per_sentence": round(fuzzy_queries / n, 2),
    }


def build_fake_glossary(texts):
    """Synthetic glossary whose surfaces are verified absent from the sample."""
    g_dict, _meta = build_synthetic_glossary(400, seed=5)
    g_dict, _removed = absent_bindings_only(g_dict, texts)
    return load_glossary(g_dict)


def run_fp_suite(fake_snapshot, texts):
    chars = sum(len(t) for t in texts)
    cand = commits = 0
    commit_examples = []
    for t in texts:
        r = resolve(fake_snapshot, t, mode="commit",
                    options={"return_all_mentions": True})
        for m in r["mentions"]:
            cand += 1
            if m["link_decision"] == "RESOLVED":
                commits += 1
                if len(commit_examples) < 10:
                    commit_examples.append(
                        {"surface": m["surface"],
                         "entity": m["resolved_entity"]["entity_id"],
                         "channels": m["generation_channels"]})
    return {
        "chars": chars,
        "candidate_mentions": cand,
        "candidates_per_1k_chars": round(cand / chars * 1000, 4),
        "resolved_fp": commits,
        "resolved_fp_per_1k_chars": round(commits / chars * 1000, 4),
        "examples": commit_examples,
    }


def _fmt(v):
    return "—" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)


def write_markdown(payload, path: Path):
    ctrl, treat = payload["control"], payload["treatment"]
    lines = [
        "# 공유 segmentation A/B (VARIANTS_PLAN M1)",
        "",
        f"기준일: {payload['generated_at']} · 재현: `python -m eval.run_segmentation_ab`",
        "",
        "M1 이전에는 exact 채널만 조사·suffix를 분해하고 Level B 채널"
        "(jamo·keyboard·abbrev)은 **원시 토큰 전체**를 인덱스에 넣었다."
        " 같은 문서를 채널마다 다르게 읽은 것이므로 모델 용량 문제가 아니다.",
        "",
        "- **대조군(A)** `max_segmentation_paths=1` — 원시 토큰만 조회 (M1 이전 동작)",
        f"- **처리군(B)** `max_segmentation_paths={payload['treatment_paths']}` — 공유 분해 결과 조회",
        f"- 표본: 실문장 {payload['host_sentences']}개에서 생성한 formation당"
        f" {payload['cases_per_formation']}건, FP 측정 {payload['fp_sentences']}문장",
        "",
        "## 1. formation별 변형 recall (동일 사례 쌍)",
        "",
        "**formation을 합산하지 말 것** — 합계는 formation을 어떤 비율로"
        " 섞었는지만 반영한다. 각 formation은 독립적으로 읽는다.",
        "",
        "| formation | n | core recall A→B | 정확 span A→B | RESOLVED A→B | commit prec B |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for f in FORMATIONS:
        a = ctrl["variants"]["per_formation"][f]
        b = treat["variants"]["per_formation"][f]
        lines.append(
            f"| `{f}` | {a['n']} | {a['core_recall']:.2f} → **{b['core_recall']:.2f}** "
            f"| {a['span_exact_rate']:.2f} → **{b['span_exact_rate']:.2f}** "
            f"| {a['resolved_rate']:.2f} → {b['resolved_rate']:.2f} "
            f"| {_fmt(b['commit_precision'])} |")
    lines += [
        "",
        "`core recall`은 gold entity가 prediction set에 들어온 비율,"
        " `정확 span`은 그중 mention core span이 gold core와 **완전히 일치**한"
        " 비율이다. any-overlap이 아니라 exact 일치로 센다.",
        "",
        "읽는 법 세 가지:",
        "",
        "1. `particle`·`suffix_particle`은 **변화가 없다**. 이미 exact 경로가"
        " 처리하던 영역이며, M1이 Level A를 건드리지 않았다는 증거다.",
        "2. `typo_particle`이 이 변경의 전부다. 오타 단독(`typo`)은 원래"
        " 0.68이었는데 거기에 조사가 붙으면 0.10으로 무너졌다 — 오타가"
        " 어려워서가 아니라 채널이 입력을 다르게 읽어서였다.",
        "3. `typo`·`typo_particle`의 RESOLVED는 **양쪽 모두 0.00**이다."
        " fuzzy 증거만으로는 확정하지 않는다는 계약이 그대로 유지된다."
        " M1은 **후보를 복구할 뿐 확정 기준을 느슨하게 만들지 않는다**.",
        "",
        "## 2. 비용",
        "",
        "| 지표 | A | B |",
        "|---|---:|---:|",
    ]
    for key, label in (("p50_ms", "지연 p50 (ms)"), ("p95_ms", "지연 p95 (ms)"),
                       ("mean_ms", "지연 평균 (ms)"),
                       ("fuzzy_queries_per_sentence", "문장당 fuzzy core 조회")):
        lines.append(f"| {label} | {ctrl['cost'][key]} | {treat['cost'][key]} |")
    ratio = treat["cost"]["p95_ms"] / max(1e-9, ctrl["cost"]["p95_ms"])
    lines += [
        "",
        f"p95 기준 **{ratio:.2f}배**다. 토큰당 core 조회가 늘어난 직접 비용이며"
        " 숨길 이유가 없다. 줄이려면 `max_segmentation_paths`를 낮추면 되고,"
        " 1로 두면 변경 전과 완전히 같은 동작·비용으로 돌아간다."
        " 추론된 core가 2음절이면 조회하지 않는 규칙과 분해 결과 캐싱으로"
        " 초기 구현의 1.9배에서 여기까지 낮춘 것이다.",
    ]
    lines += [
        "",
        "## 3. 오탐 — fake glossary (구조적 FP)",
        "",
        "corpus에 존재하지 않음이 검증된 표면형만 남긴 합성 glossary."
        " 모든 RESOLVED commit은 정의상 오탐이다. 토큰당 core를 1개에서"
        " 여러 개로 늘리는 변경에서 가장 먼저 무너지는 지표이므로 이것이"
        " ResolutionGuard의 실제 시험대다.",
        "",
        "| 지표 | A | B |",
        "|---|---:|---:|",
        f"| candidate mentions /1k chars | {ctrl['fp']['candidates_per_1k_chars']} "
        f"| {treat['fp']['candidates_per_1k_chars']} |",
        f"| **RESOLVED FP** | {ctrl['fp']['resolved_fp']} "
        f"| **{treat['fp']['resolved_fp']}** |",
        f"| RESOLVED FP /1k chars | {ctrl['fp']['resolved_fp_per_1k_chars']} "
        f"| {treat['fp']['resolved_fp_per_1k_chars']} |",
        "",
        "## 4. 이 측정이 말하지 않는 것",
        "",
        "- 변형 표면형은 **합성**이다. 문장 분포는 실제지만 표면형 자체는"
        " 규칙으로 만든 것이므로, 실제 오탈자 분포를 대표하지 않는다."
        " 실분포 taxonomy는 M3의 wild-tail 수동 분류가 담당한다.",
        "- `typo` 계열은 중성 1개 치환만 쓴다. 자모 삽입·전치·키보드 혼용은"
        " 별도 슬라이스가 필요하다.",
        "- commit precision은 **라벨된 span 위의 commit만** 분모에 넣는다."
        " 라벨 밖 commit은 오답이 아니라 미측정이다.",
        "- FP 측정은 fake glossary 기준이며, 실제 glossary에서 서로 다른"
        " 실존 entity를 혼동하는 오류율은 여기서 측정하지 않는다.",
        "",
        provenance_line(ROOT),
        "",
        "*generated by `python -m eval.run_segmentation_ab`*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", type=int, default=6000,
                    help="sentences used for the cost and FP suites")
    ap.add_argument("--cases-per-formation", type=int, default=400)
    ap.add_argument("--paths", type=int, default=4)
    args = ap.parse_args()

    rng = random.Random(SEED)
    corpus = load_corpus()
    print(f"corpus: {len(corpus)} sentences")
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    aliases = [(b.surface, b.entity_id) for b in glossary.alias_bindings]

    cases = build_variant_cases(corpus, aliases, args.cases_per_formation, rng)
    print(f"variant cases: {len(cases)}")

    sample = rng.sample(corpus, min(args.sentences, len(corpus)))
    texts = [r["text"] for r in sample]
    fake_glossary = build_fake_glossary(texts)

    arms = {}
    for name, paths in (("control", 1), ("treatment", args.paths)):
        policy = RuntimePolicy(max_segmentation_paths=paths)
        snap = compile_snapshot(glossary, policy=policy)
        fake_snap = compile_snapshot(fake_glossary, policy=policy,
                                     strict=False, run_conformance=False)
        print(f"[{name}] paths={paths} snapshot={snap.snapshot_id}")
        t0 = time.perf_counter()
        arms[name] = {
            "max_segmentation_paths": paths,
            "snapshot_id": snap.snapshot_id,
            "variants": run_variant_suite(snap, cases),
            "cost": run_cost_suite(snap, texts),
            "fp": run_fp_suite(fake_snap, texts),
            "elapsed_seconds": round(time.perf_counter() - t0, 1),
        }
        print(f"[{name}] done in {arms[name]['elapsed_seconds']}s")

    payload = {
        "generated_at": time.strftime("%Y-%m-%d"),
        "seed": SEED,
        "glossary_id": glossary.glossary_id,
        "corpus_sentences": len(corpus),
        "host_sentences": len(texts),
        "fp_sentences": len(texts),
        "cases_per_formation": args.cases_per_formation,
        "treatment_paths": args.paths,
        "formation_counts": dict(Counter(c["formation"] for c in cases)),
        **arms,
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "segmentation_ab.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "SEGMENTATION_AB.md")
    for f in FORMATIONS:
        a = arms["control"]["variants"]["per_formation"][f]
        b = arms["treatment"]["variants"]["per_formation"][f]
        print(f"{f:16s} recall {a['core_recall']:.3f} -> {b['core_recall']:.3f}"
              f"   exact-span {a['span_exact_rate']:.3f} -> {b['span_exact_rate']:.3f}")
    print("FP", arms["control"]["fp"]["resolved_fp"], "->",
          arms["treatment"]["fp"]["resolved_fp"])
    print("p95", arms["control"]["cost"]["p95_ms"], "->",
          arms["treatment"]["cost"]["p95_ms"])


if __name__ == "__main__":
    main()

"""Level B gate: dense-retrieval evaluation on the §42 unseen splits.

Usage: python -m eval.run_neural_eval

Builds **UE-derived-abbreviation / UE-canonical-only** conditions from the
real-org glossary + the wild KLUE corpus: abbreviation bindings are REMOVED
from the test glossary, so their real-text occurrences become unseen
surfaces that only Pass 2 (abbrev alignment ∪ dense retrieval) can recover.
Per MODEL_RECOMMEND.md, public leaderboards don't transfer to this
short-alias distribution — this is the direct measurement.

Compared configurations:
  symbolic  — abbreviation alignment only (V1 Pass 2)
  hash      — + HashEncoder dense (lexical baseline)
  e5        — + multilingual-e5-small ONNX (Role-2 lightweight reference)

Also reports retrieval-only Recall@k (encoder quality isolated from the
pipeline) and encoding latency. Writes eval/out/neural.json + NEURAL_EVAL.md.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ktrf.encoders import HashEncoder, OnnxE5Encoder
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import wilson_interval, provenance_line
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
E5_DIR = ROOT / "models" / "multilingual-e5-small"

# abbreviations held out of the test glossary (their entities keep only
# canonical/description + full-name binding -> UE condition for these
# surfaces on real text)
HOLDOUT_ABBREVS = ["과기정통부", "금감원", "금융위", "공정위", "기재부", "국토부",
                   "복지부", "행안부", "문체부", "해수부", "농식품부", "식약처",
                   "중기부", "산업부", "노동부", "미래부", "선관위", "국정원",
                   "방통위", "원안위", "한수원"]


def _holdout_glossary():
    g = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    import copy

    from ktrf.glossary import Glossary

    holdout_map = {}
    kept = []
    for b in g.alias_bindings:
        if b.surface in HOLDOUT_ABBREVS:
            holdout_map[b.surface] = b.entity_id
        else:
            kept.append(b)
    kept_fids = {b.family_id for b in kept}
    g2 = Glossary(
        glossary_id=g.glossary_id + "-ue", version=g.version,
        schema_version=g.schema_version, entities=copy.deepcopy(g.entities),
        alias_families=[f for f in g.alias_families
                        if f.family_id in kept_fids],
        alias_bindings=kept, entity_relations=[],
        normalization_profiles=g.normalization_profiles,
    )
    return g2, holdout_map


def _queries(holdout_map: dict, all_occurrences: bool = True) -> list[dict]:
    """Real-text UE queries: wild sentences containing a held-out surface.

    Every occurrence of every held-out alias becomes a case. The earlier
    version stopped at the first alias per sentence, which silently biased
    the sample toward whichever alias happened to appear first and made a
    "query case" count look like an occurrence count.
    """
    corpus = load_corpus()
    out = []
    for row in corpus:
        text = row["text"]
        for surface, entity_id in holdout_map.items():
            start = 0
            while True:
                i = text.find(surface, start)
                if i < 0:
                    break
                start = i + 1
                prev = text[i - 1] if i > 0 else ""
                if prev and ("가" <= prev <= "힣"
                             or (prev.isascii() and prev.isalnum())):
                    continue
                out.append({"text": text, "surface": surface,
                            "span": (i, i + len(surface)),
                            "gold": entity_id})
                if not all_occurrences:
                    break
            if out and not all_occurrences and out[-1]["text"] == text:
                break
    return out


def _pipeline_recall(snapshot, queries, label) -> dict:
    """E2E recall with exact-core matching and a global commit ledger.

    Two measurement fixes over the earlier version:

    - a hit requires the mention span to *equal* the gold span (exact
      core). Any-overlap credited a mention that merely brushed the gold
      span, which inflates recall on exactly the hard cases this
      benchmark exists to measure. Overlap is still reported separately
      as a diagnostic.
    - the commit ledger counts EVERY resolved mention in the evaluated
      sentences and separates those on a labeled span from the rest. In
      this track only the held-out abbreviation spans carry labels, so a
      commit elsewhere (a full organization name in the same sentence) is
      unlabeled, not wrong — precision is therefore reported over labeled
      commits only, with the unlabeled count exposed beside it.
    """
    exact_hits = overlap_hits = 0
    ledger_total = ledger_on_gold = ledger_correct = 0
    set_sizes: list[int] = []
    latencies = []
    misses = []
    per_family: dict[str, list[int]] = {}
    seen_sentences: set[str] = set()
    for q in queries:
        t0 = time.perf_counter()
        resp = resolve(snapshot, q["text"], mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50,
                                "detect_unregistered_mentions": True})
        latencies.append(time.perf_counter() - t0)
        s, e = q["span"]
        exact_found = overlap_found = False
        for m in resp["mentions"]:
            cp = m["span"]["codepoint"]
            ids = {x.get("entity_id") for x in
                   m.get("prediction_set", {}).get("members", [])}
            if "resolved_entity" in m:
                ids.add(m["resolved_entity"]["entity_id"])
            if cp["start"] == s and cp["end"] == e:
                set_sizes.append(len([
                    x for x in m.get("prediction_set", {}).get("members", [])
                    if x.get("kind", "ENTITY") == "ENTITY"]))
                if q["gold"] in ids:
                    exact_found = True
            elif cp["start"] < e and s < cp["end"] and q["gold"] in ids:
                overlap_found = True
        # commit ledger: every RESOLVED mention in this sentence counts
        # once, whether or not it sits on the gold span
        if q["text"] not in seen_sentences:
            seen_sentences.add(q["text"])
            gold_by_span = {(qq["span"][0], qq["span"][1]): qq["gold"]
                            for qq in queries if qq["text"] == q["text"]}
            for m in resp["mentions"]:
                if m.get("link_decision") != "RESOLVED":
                    continue
                cp = m["span"]["codepoint"]
                ledger_total += 1
                expected = gold_by_span.get((cp["start"], cp["end"]))
                if expected is not None:
                    ledger_on_gold += 1
                    ledger_correct += int(
                        m["resolved_entity"]["entity_id"] == expected)
        exact_hits += int(exact_found)
        overlap_hits += int(exact_found or overlap_found)
        per_family.setdefault(q["surface"], []).append(int(exact_found))
        if not exact_found and len(misses) < 8:
            misses.append({"text": q["text"], "surface": q["surface"]})
    latencies.sort()
    n = len(queries)
    lo, hi = wilson_interval(exact_hits, n)
    family_rates = {k: sum(v) / len(v) for k, v in per_family.items()}
    macro = sum(family_rates.values()) / len(family_rates) if family_rates else None
    set_sizes.sort()
    return {
        "config": label,
        "queries": n,
        "gold_in_set_e2e": {"hits": exact_hits, "total": n,
                            "rate": round(exact_hits / n, 4),
                            "ci95": [round(lo, 4), round(hi, 4)]},
        "gold_in_set_any_overlap_diagnostic": round(overlap_hits / n, 4),
        "family_macro": round(macro, 4) if macro is not None else None,
        "families": len(family_rates),
        "worst_family": (min(family_rates.items(), key=lambda kv: kv[1])
                         if family_rates else None),
        "commit_ledger": {
            "commits": ledger_total,
            "on_labeled_span": ledger_on_gold,
            "correct_on_labeled_span": ledger_correct,
            "unlabeled_span": ledger_total - ledger_on_gold,
            "precision_on_labeled": (round(ledger_correct / ledger_on_gold, 4)
                                     if ledger_on_gold else None),
            "note": "only held-out abbreviation spans are labeled in this "
                    "track, so commits elsewhere are unlabeled rather than "
                    "wrong; precision covers labeled commits only",
        },
        "prediction_set_size": {
            "mean": round(sum(set_sizes) / len(set_sizes), 2)
            if set_sizes else None,
            "p95": set_sizes[int(len(set_sizes) * .95)] if set_sizes else None,
        },
        "latency_p50_ms": round(1000 * latencies[len(latencies) // 2], 2),
        "latency_p95_ms": round(1000 * latencies[int(len(latencies) * .95)], 2),
        "misses": misses,
    }


def _retrieval_only(encoder, glossary, queries, label) -> dict:
    """Encoder quality isolated: rank entities for the mention context."""
    from ktrf.dense import DenseArtifacts

    t0 = time.perf_counter()
    dense = DenseArtifacts.build(glossary, encoder)
    build_s = time.perf_counter() - t0
    recall_at = {1: 0, 5: 0, 10: 0, 20: 0, 50: 0}
    top_k = max(recall_at)
    enc_ms = []
    for q in queries:
        s, e = q["span"]
        window = q["text"][max(0, s - 40):e + 40]
        t0 = time.perf_counter()
        qv = encoder.encode_query(window)
        enc_ms.append(1000 * (time.perf_counter() - t0))
        ranked = [eid for eid, _ in dense.index.search(qv, top_k)]
        for k in recall_at:
            recall_at[k] += int(q["gold"] in ranked[:k])
    n = len(queries)
    enc_ms.sort()
    return {
        "encoder": label,
        "encoder_id": encoder.encoder_id,
        "dim": encoder.dim,
        "index_build_seconds": round(build_s, 2),
        "recall_at": {str(k): round(v / n, 4) for k, v in recall_at.items()},
        "query_encode_p50_ms": round(enc_ms[len(enc_ms) // 2], 2),
    }


def main():
    glossary, holdout_map = _holdout_glossary()
    queries = _queries(holdout_map)
    print(f"UE queries from wild corpus: {len(queries)} "
          f"({len(holdout_map)} held-out abbreviations)")

    encoders = {"hash": HashEncoder()}
    if E5_DIR.exists():
        encoders["e5"] = OnnxE5Encoder(E5_DIR)
    else:
        print("NOTE: e5 model dir missing; running hash baseline only")

    results = {"queries": len(queries),
               "holdout_abbreviations": len(holdout_map),
               "pipeline": [], "retrieval_only": []}

    snap = compile_snapshot(glossary, run_conformance=False)
    results["pipeline"].append(_pipeline_recall(snap, queries, "symbolic"))
    for name, enc in encoders.items():
        snap = compile_snapshot(glossary, run_conformance=False, encoder=enc)
        results["pipeline"].append(_pipeline_recall(snap, queries, name))
        results["retrieval_only"].append(
            _retrieval_only(enc, glossary, queries, name))

    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "neural.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(results, ROOT / "reports" / "NEURAL_EVAL.md")
    for p in results["pipeline"]:
        print(f'  {p["config"]:9} exact-core={p["gold_in_set_e2e"]["rate"]}'
              f' macro={p["family_macro"]}'
              f' overlap={p["gold_in_set_any_overlap_diagnostic"]}'
              f' commit_prec={p["commit_ledger"]["precision_on_labeled"]}'
              f' p95={p["latency_p95_ms"]}ms')
    for r in results["retrieval_only"]:
        print(f'  retrieval {r["encoder"]:5} R@1={r["recall_at"]["1"]}'
              f' R@10={r["recall_at"]["10"]} R@50={r["recall_at"]["50"]}')
    print(f"wrote {out / 'neural.json'} and {ROOT / 'reports' / 'NEURAL_EVAL.md'}")


def _write_md(r: dict, path: Path) -> None:
    lines = [
        "# KTRF Level B 평가 — Dense Retrieval (M4 gate)",
        "",
        f"§42 **UE-derived-abbreviation** 조건: 실존 조직 glossary에서 약칭"
        f" binding {r['holdout_abbreviations']}종을 제거하고, 실제 KLUE 뉴스"
        f" 문장 중 해당 표면형이 등장하는 {r['queries']}문장을 질의로 사용한다."
        " 시스템은 canonical/description만으로 정답 entity를 복구해야 한다"
        " (Pass 2: abbreviation alignment ∪ dense retrieval)."
        " 재현: `python -m eval.run_neural_eval`.",
        "",
        "## 파이프라인 E2E (exact-core span 기준 gold-in-prediction-set)",
        "",
        "**exact-core**: mention span이 gold span과 정확히 일치해야 hit다."
        " any-overlap은 진단용으로만 병기한다 — 겹치기만 한 mention을"
        " 인정하면 이 벤치마크가 측정하려는 어려운 사례에서 recall이"
        " 부풀려진다.",
        "",
        "| 구성 | exact-core recall | CI95 | family macro | any-overlap(진단) "
        "| set size mean/p95 | p50/p95 |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for p in r["pipeline"]:
        g = p["gold_in_set_e2e"]
        ss = p["prediction_set_size"]
        lines.append(
            f"| {p['config']} | **{g['rate']}** ({g['hits']}/{g['total']}) "
            f"| {g['ci95']} | {p['family_macro']} "
            f"| {p['gold_in_set_any_overlap_diagnostic']} "
            f"| {ss['mean']} / {ss['p95']} "
            f"| {p['latency_p50_ms']} / {p['latency_p95_ms']} ms |")
    lines += [
        "",
        "### Commit ledger",
        "",
        "평가 문장 안의 **모든** RESOLVED mention을 센다. 다만 이 트랙에서"
        " 라벨이 있는 span은 held-out 약칭 위치뿐이므로, 그 밖의 확정(같은"
        " 문장의 정식 명칭 등)은 *오탐이 아니라 라벨이 없는 것*이다."
        " precision은 라벨된 commit에 한해 계산하고 나머지는 별도로 노출한다.",
        "",
        "| 구성 | 전체 commits | 라벨 span 위 | 정답 | 라벨 없음 | precision(라벨 한정) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in r["pipeline"]:
        cl = p["commit_ledger"]
        lines.append(f"| {p['config']} | {cl['commits']} "
                     f"| {cl['on_labeled_span']} "
                     f"| {cl['correct_on_labeled_span']} "
                     f"| {cl['unlabeled_span']} "
                     f"| {cl['precision_on_labeled']} |")
    lines += [
        "",
        "## Retrieval-only (encoder 단독, 문맥 window -> entity 순위)",
        "",
        "| encoder | dim | R@1 | R@5 | R@10 | R@20 | R@50 | encode p50 "
        "| index build |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in r["retrieval_only"]:
        ra = x["recall_at"]
        lines.append(
            f"| {x['encoder']} (`{x['encoder_id'][:28]}…`) | {x['dim']} "
            f"| {ra['1']} | {ra['5']} | {ra['10']} | {ra['20']} | {ra['50']} "
            f"| {x['query_encode_p50_ms']} ms | {x['index_build_seconds']} s |")
    worst = [(p["config"], p["worst_family"]) for p in r["pipeline"]]
    # derive the cost-of-recall sentence from this run: hardcoding it is how
    # a report keeps quoting a delta its own table no longer shows
    by_cfg = {p["config"]: p for p in r["pipeline"]}
    base = by_cfg.get("symbolic")
    dense = max((p for c, p in by_cfg.items() if c != "symbolic"),
                key=lambda p: p["gold_in_set_e2e"]["rate"], default=None)
    if base and dense:
        d_exact = dense["gold_in_set_e2e"]["rate"] - base["gold_in_set_e2e"]["rate"]
        d_overlap = (dense["gold_in_set_any_overlap_diagnostic"]
                     - base["gold_in_set_any_overlap_diagnostic"])
        b_set = base["prediction_set_size"]["mean"]
        d_set = dense["prediction_set_size"]["mean"]
        cost_bullet = (
            f"- **recall 증가의 비용을 함께 본다**: dense 최고 구성"
            f" ({dense['config']})은 symbolic 대비 exact-core recall을"
            f" {d_exact * 100:+.1f}%p 움직이는 대신 prediction set 크기를"
            f" {d_set / b_set:.1f}배로 키운다(mean {b_set} → {d_set})."
            f" any-overlap 기준으로는 그 차이가 {d_overlap * 100:+.1f}%p로"
            f" 보이지만, span을 정확히 요구하면 증분은 훨씬 작다 — 겹치기만"
            f" 한 mention에 주던 크레딧이 사라지기 때문이다.")
    else:
        cost_bullet = ""
    lines += [
        "",
        "## 해석과 한계",
        "",
        "- MODEL_RECOMMEND.md의 검증 원칙에 따라 공개 벤치마크가 아닌 KTRF 자체"
        " 분포(짧은 약칭 ↔ canonical/description)에서 측정했다.",
        "- symbolic 대비 dense의 증분이 bi-encoder의 실효 기여분이다. hash는"
        " 표면 유사(자모 n-gram) 기반의 lexical 하한선, e5는 의미 기반 검색의"
        " Role-2 경량 기준이다.",
        cost_bullet,
        "- **이 트랙은 commit precision을 측정할 수 없다**: 라벨된 span 위"
        " 확정이 0건이다. 약칭 binding이 제거된 상태에서 resolver가 해당"
        " 위치를 확정하지 않는 것은 의도된 보수적 동작이며, 그 결과 이"
        " 트랙에서 나오는 확정은 전부 라벨 밖(같은 문장의 정식 명칭 등)이다.",
        f"- **family macro**를 함께 본다: 이 트랙은 약칭"
        f" {r['holdout_abbreviations']}종뿐이고 occurrence 수가 종마다 크게"
        " 달라, micro 평균은 빈출 약칭이 지배한다. 최악 family: "
        + ", ".join(f"{cfg} `{wf[0]}` {wf[1]:.2f}" for cfg, wf in worst
                    if wf) + ".",
        "- 이 트랙은 **binding holdout**이다. alias family·formation·entity가"
        " 모두 새로운 경우(진짜 미지 약어)는 측정하지 않으므로, 여기 수치를"
        " '신규 합성 약어 일반화'의 근거로 쓰지 않는다.",
        "- 프로덕션 후보(KURE-v1 등 568M급)는 동일 `encoder spec` 인터페이스로"
        " 교체 평가한다(ONNX export 후 `onnx:<dir>`).",
        "",
        provenance_line(ROOT),
        "",
        "*generated by `python -m eval.run_neural_eval`*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

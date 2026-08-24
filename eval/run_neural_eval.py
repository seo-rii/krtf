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

from .metrics import wilson_interval
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


def _queries(holdout_map: dict) -> list[dict]:
    """Real-text UE queries: wild sentences containing a held-out surface."""
    corpus = load_corpus()
    out = []
    for row in corpus:
        text = row["text"]
        for surface, entity_id in holdout_map.items():
            i = text.find(surface)
            if i < 0:
                continue
            prev = text[i - 1] if i > 0 else ""
            if prev and ("가" <= prev <= "힣" or (prev.isascii() and prev.isalnum())):
                continue
            out.append({"text": text, "surface": surface,
                        "span": (i, i + len(surface)), "gold": entity_id})
            break
    return out


def _pipeline_recall(snapshot, queries, label) -> dict:
    hits = resolved_correct = resolved = 0
    latencies = []
    misses = []
    for q in queries:
        t0 = time.perf_counter()
        resp = resolve(snapshot, q["text"], mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50,
                                "detect_unregistered_mentions": True})
        latencies.append(time.perf_counter() - t0)
        s, e = q["span"]
        found = False
        for m in resp["mentions"]:
            cp = m["span"]["codepoint"]
            if cp["start"] < e and s < cp["end"]:
                ids = {x.get("entity_id") for x in
                       m.get("prediction_set", {}).get("members", [])}
                if "resolved_entity" in m:
                    ids.add(m["resolved_entity"]["entity_id"])
                if q["gold"] in ids:
                    found = True
                    if m.get("link_decision") == "RESOLVED":
                        resolved += 1
                        resolved_correct += int(
                            m["resolved_entity"]["entity_id"] == q["gold"])
        hits += int(found)
        if not found and len(misses) < 8:
            misses.append({"text": q["text"], "surface": q["surface"]})
    latencies.sort()
    lo, hi = wilson_interval(hits, len(queries))
    return {
        "config": label,
        "queries": len(queries),
        "gold_in_set_e2e": {"hits": hits, "total": len(queries),
                            "rate": round(hits / len(queries), 4),
                            "ci95": [round(lo, 4), round(hi, 4)]},
        "resolved_precision": (round(resolved_correct / resolved, 4)
                               if resolved else None),
        "resolved_count": resolved,
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
    recall_at = {1: 0, 5: 0, 10: 0}
    enc_ms = []
    for q in queries:
        s, e = q["span"]
        window = q["text"][max(0, s - 40):e + 40]
        t0 = time.perf_counter()
        qv = encoder.encode_query(window)
        enc_ms.append(1000 * (time.perf_counter() - t0))
        ranked = [eid for eid, _ in dense.index.search(qv, 10)]
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
        print(f'  {p["config"]:9} gold-in-set={p["gold_in_set_e2e"]["rate"]}'
              f' p95={p["latency_p95_ms"]}ms')
    for r in results["retrieval_only"]:
        print(f'  retrieval {r["encoder"]:5} R@1={r["recall_at"]["1"]}'
              f' R@5={r["recall_at"]["5"]} R@10={r["recall_at"]["10"]}')
    print(f"wrote {out / 'neural.json'} and {ROOT / 'NEURAL_EVAL.md'}")


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
        "## 파이프라인 E2E (gold-in-prediction-set)",
        "",
        "| 구성 | recall | CI95 | RESOLVED precision | p50/p95 |",
        "|---|---:|---|---|---|",
    ]
    for p in r["pipeline"]:
        g = p["gold_in_set_e2e"]
        lines.append(
            f"| {p['config']} | **{g['rate']}** ({g['hits']}/{g['total']}) "
            f"| {g['ci95']} | {p['resolved_precision']} "
            f"({p['resolved_count']}) "
            f"| {p['latency_p50_ms']} / {p['latency_p95_ms']} ms |")
    lines += [
        "",
        "## Retrieval-only (encoder 단독, 문맥 window -> entity 순위)",
        "",
        "| encoder | dim | R@1 | R@5 | R@10 | encode p50 | index build |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for x in r["retrieval_only"]:
        ra = x["recall_at"]
        lines.append(
            f"| {x['encoder']} (`{x['encoder_id'][:28]}…`) | {x['dim']} "
            f"| {ra['1']} | {ra['5']} | {ra['10']} "
            f"| {x['query_encode_p50_ms']} ms | {x['index_build_seconds']} s |")
    lines += [
        "",
        "## 해석",
        "",
        "- MODEL_RECOMMEND.md의 검증 원칙에 따라 공개 벤치마크가 아닌 KTRF 자체"
        " 분포(짧은 약칭 ↔ canonical/description)에서 측정했다.",
        "- symbolic 대비 dense의 증분이 bi-encoder의 실효 기여분이다. hash는"
        " 표면 유사(자모 n-gram) 기반의 lexical 하한선, e5는 의미 기반 검색의"
        " Role-2 경량 기준이다.",
        "- 프로덕션 후보(KURE-v1 등 568M급)는 동일 `encoder spec` 인터페이스로"
        " 교체 평가한다(ONNX export 후 `onnx:<dir>`).",
        "",
        "*generated by `python -m eval.run_neural_eval`*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

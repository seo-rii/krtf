"""Wild-corpus benchmark on real Korean text (HuggingFace KLUE news).

Usage: python -m eval.run_wild

Three suites over ~5k real news headlines (eval/wild_data.py cache):

1. **Silver recall** (realorg glossary): occurrences of unambiguous real-org
   surfaces (full names + 3+-char government abbreviations) are silver gold —
   in news text these are near-certain mentions. Measures E2E detection,
   gold-in-prediction-set, and RESOLVED behavior on real distribution.
   Occurrences embedded in longer registered aliases or attached to a
   preceding Hangul/Latin character are excluded from the denominator
   (they are compounds like 서울지방경찰청, not silver-certain).
2. **Real-tail distribution coverage** (§5.2 조사·어미 분포 커버리지): the
   Hangul run following each silver mention, classified by the tail parser —
   the fraction fully explained by the particle/suffix catalogs, measured on
   *real* usage, plus the uncovered tails as catalog-extension signals.
3. **Fake-glossary false positives**: a synthetic glossary whose surfaces
   are verified absent from the corpus — any candidate or commit of a fake
   entity on real text is a false positive by construction.

Writes eval/out/wild.json and WILD_CORPUS.md.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.morphology import ParticleFST
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot
from ktrf.tailparser import analyze_tail

from .metrics import wilson_interval
from .synthetic import build_synthetic_glossary
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent

# aliases whose bare occurrence in news is near-certainly an org mention
SILVER_MIN_LEN = 3
# short/ambiguous aliases: measured for detection stats only, not recall
DETECTION_ONLY = {"한전", "한은", "헌재", "KT", "SKT", "국민연금", "청와대",
                  "네이버", "카카오"}


def _is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def _silver_occurrences(text: str, aliases: list[str]) -> list[tuple[int, int, str]]:
    """Maximal, left-clean occurrences of silver aliases in text."""
    raw: list[tuple[int, int, str]] = []
    for a in aliases:
        start = 0
        while True:
            i = text.find(a, start)
            if i < 0:
                break
            start = i + 1
            prev = text[i - 1] if i > 0 else ""
            if prev and (_is_hangul(prev) or prev.isascii() and prev.isalnum()):
                continue  # compound like 서울지방경찰청 — not silver-certain
            raw.append((i, i + len(a), a))
    # keep only maximal occurrences (복지부 inside 보건복지부 drops out)
    out = []
    for s, e, a in raw:
        if not any((s2 <= s and e <= e2) and (s2, e2) != (s, e)
                   for s2, e2, _ in raw):
            out.append((s, e, a))
    return out


def _mention_entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def run_silver_and_tails(corpus: list[dict]) -> dict:
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    snap = compile_snapshot(glossary)
    alias_to_entity = {b.surface: b.entity_id for b in glossary.alias_bindings}
    silver_aliases = [s for s in alias_to_entity
                      if len(s) >= SILVER_MIN_LEN and s not in DETECTION_ONLY]

    fst = ParticleFST()
    all_surfaces = set(alias_to_entity)
    total = detected = in_set = 0
    resolved = resolved_correct = 0
    detection_only_hits = 0
    misses: list[dict] = []
    tail_total = tail_covered = 0
    juxtaposed = 0
    uncovered_tails: Counter = Counter()
    latencies: list[float] = []

    for row in corpus:
        text = row["text"]
        occs = _silver_occurrences(text, silver_aliases)
        has_detection_only = any(a in text for a in DETECTION_ONLY)
        if not occs and not has_detection_only:
            continue
        t0 = time.perf_counter()
        resp = resolve(snap, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        latencies.append(time.perf_counter() - t0)
        mentions = resp["mentions"]
        spans = {}
        for m in mentions:
            cp = m["span"]["codepoint"]
            spans[(cp["start"], cp["end"])] = m

        for s, e, alias in occs:
            gold = alias_to_entity[alias]
            total += 1
            m = spans.get((s, e))
            if m is None:
                overl = [x for (s2, e2), x in spans.items()
                         if s2 < e and s < e2]
                if overl and any(gold in _mention_entities(x) for x in overl):
                    detected += 1
                    in_set += 1
                else:
                    misses.append({"text": text, "alias": alias})
                continue
            detected += 1
            if gold in _mention_entities(m):
                in_set += 1
            else:
                misses.append({"text": text, "alias": alias, "wrong_set": True})
            if m.get("link_decision") == "RESOLVED":
                resolved += 1
                resolved_correct += int(
                    m["resolved_entity"]["entity_id"] == gold)
            # real tail distribution (§5.2): Hangul run following the core
            j = e
            while j < len(text) and _is_hangul(text[j]):
                j += 1
            tail = text[e:j]
            if tail:
                if any(tail.startswith(s) for s in all_surfaces):
                    # headline-style org juxtaposition (미래부방통위) — a
                    # separate mention, not a morphological tail
                    juxtaposed += 1
                    continue
                tail_total += 1
                analyses = analyze_tail(tail, text[e - 1], fst)
                best = analyses[0]
                covered = (best.residual_kind in ("", "SUFFIX",
                                                  "SUFFIX_WITH_MODIFIER")
                           and best.score >= 0.7)
                tail_covered += int(covered)
                if not covered:
                    uncovered_tails[tail] += 1

        for m in mentions:
            if m["surface"] in DETECTION_ONLY:
                detection_only_hits += 1

    latencies.sort()
    lo, hi = wilson_interval(in_set, total)
    tlo, thi = wilson_interval(tail_covered, tail_total)
    return {
        "silver_mentions": total,
        "core_detected_e2e": {"hits": detected, "total": total,
                              "rate": round(detected / total, 4)},
        "gold_in_set_e2e": {"hits": in_set, "total": total,
                            "rate": round(in_set / total, 4),
                            "ci95": [round(lo, 4), round(hi, 4)]},
        "resolved": {"count": resolved,
                     "precision_given_commit":
                         round(resolved_correct / resolved, 4) if resolved else None,
                     "coverage_of_silver": round(resolved / total, 4)},
        "detection_only_mentions": detection_only_hits,
        "tail_distribution": {
            "attached_tails": tail_total,
            "juxtaposed_alias_tails": juxtaposed,
            "catalog_covered": tail_covered,
            "coverage": round(tail_covered / tail_total, 4) if tail_total else None,
            "ci95": [round(tlo, 4), round(thi, 4)],
            "top_uncovered": uncovered_tails.most_common(15),
        },
        "latency_ms": {"p50": round(1000 * latencies[len(latencies) // 2], 2),
                       "p95": round(1000 * latencies[int(len(latencies) * .95)], 2)}
        if latencies else None,
        "misses": misses[:15],
    }


def run_fake_glossary_fp(corpus: list[dict]) -> dict:
    g_dict, meta = build_synthetic_glossary(400, seed=5)
    all_text = "\n".join(r["text"] for r in corpus)
    # keep only bindings whose surface never occurs in the corpus:
    # any hit on real text is then a false positive by construction
    kept = [b for b in g_dict["alias_bindings"]
            if b["surface"] not in all_text]
    removed = len(g_dict["alias_bindings"]) - len(kept)
    kept_fids = {b["family_id"] for b in kept}
    g_dict["alias_bindings"] = kept
    g_dict["alias_families"] = [f for f in g_dict["alias_families"]
                                if f["family_id"] in kept_fids]
    snap = compile_snapshot(load_glossary(g_dict), strict=False,
                            run_conformance=False)

    chars = 0
    candidate_mentions = resolved_fp = 0
    examples: list[dict] = []
    for row in corpus:
        text = row["text"]
        chars += len(text)
        resp = resolve(snap, text, mode="commit",
                       options={"return_all_mentions": True})
        for m in resp["mentions"]:
            candidate_mentions += 1
            if m.get("link_decision") == "RESOLVED":
                resolved_fp += 1
                if len(examples) < 10:
                    examples.append({"text": text, "surface": m["surface"]})
    return {
        "bindings_tested": len(kept),
        "bindings_removed_as_present_in_corpus": removed,
        "sentences": len(corpus),
        "chars": chars,
        "candidate_mentions_per_1k_chars":
            round(1000 * candidate_mentions / chars, 3),
        "resolved_fp_count": resolved_fp,
        "resolved_fp_per_1k_chars": round(1000 * resolved_fp / chars, 4),
        "examples": examples,
        "interpretation": "fake-org glossary on real news: every RESOLVED "
                          "commit is a false positive by construction",
    }


def write_markdown(payload: dict, out_path: Path) -> None:
    s = payload["silver"]
    fp = payload["fake_fp"]
    td = s["tail_distribution"]
    lines = [
        "# KTRF Wild-Corpus 벤치마크 (실제 한국어 텍스트)",
        "",
        f"코퍼스: HuggingFace KLUE (뉴스 헤드라인 등) {payload['corpus_sentences']}문장,"
        " CC BY-SA 4.0. 합성 데이터와 달리 구현 카탈로그와 독립적인 실 분포다."
        " 재현: `python -m eval.run_wild` (최초 실행 시 다운로드).",
        "",
        "## 1. Silver recall — 실존 조직 표면형 (E2E, commit mode)",
        "",
        "무모호 표면형(정부기관 전체명·3자 이상 약칭)의 뉴스 내 출현은 사실상"
        " 확실한 mention이다(silver label). 좌측 문자 결합·상위 alias 내포"
        " 출현은 분모에서 제외한다.",
        "",
        f"- silver mentions: **{s['silver_mentions']}**",
        f"- core 탐지 (E2E): **{s['core_detected_e2e']['rate']}**"
        f" ({s['core_detected_e2e']['hits']}/{s['core_detected_e2e']['total']})",
        f"- gold-in-prediction-set (E2E): **{s['gold_in_set_e2e']['rate']}**"
        f" ({s['gold_in_set_e2e']['hits']}/{s['gold_in_set_e2e']['total']},"
        f" CI95 {s['gold_in_set_e2e']['ci95']})",
        f"- RESOLVED precision (|commit): **{s['resolved']['precision_given_commit']}**"
        f" ({s['resolved']['count']} commits,"
        f" silver 대비 coverage {s['resolved']['coverage_of_silver']})",
        f"- 짧은/다의 표면형(한전·한은·KT 등) 탐지 mention: "
        f"{s['detection_only_mentions']}건 (recall 분모 제외)",
        f"- latency p50/p95: {s['latency_ms']['p50']} / {s['latency_ms']['p95']} ms",
        "",
        "## 2. 조사·어미 실분포 커버리지 (§5.2)",
        "",
        f"silver mention 직후의 한글 run {td['attached_tails']}건 중 카탈로그"
        f"(조사 연쇄·기관 suffix)로 완전히 설명되는 비율: **{td['coverage']}**"
        f" (CI95 {td['ci95']})",
        "",
        "카탈로그 미포함 상위 tail (확장 우선순위 신호, §3.5):",
        "",
    ]
    for tail, cnt in td["top_uncovered"]:
        lines.append(f"- `{tail}` × {cnt}")
    lines += [
        "",
        "## 3. Fake-glossary 오탐 (구조적 FP 측정)",
        "",
        "corpus에 존재하지 않는 표면형만 남긴 합성 glossary"
        f"({fp['bindings_tested']} bindings)로 실 텍스트를 처리 —"
        " 모든 RESOLVED commit은 정의상 오탐이다.",
        "",
        f"- candidate mentions /1k chars: {fp['candidate_mentions_per_1k_chars']}"
        " (fuzzy/keyboard 채널의 실 텍스트 자극 밀도)",
        f"- **RESOLVED FP: {fp['resolved_fp_count']}건**"
        f" ({fp['resolved_fp_per_1k_chars']} /1k chars, {fp['chars']} chars)",
        "",
        "## 4. 해석과 한계",
        "",
        "- silver label은 수동 검증이 아닌 규칙 기반 근사다. 미포함(짧은 약칭,"
        " 좌측 결합형)은 보수적으로 제외했으므로 recall 분모가 실제보다 좁다.",
        "- KLUE 헤드라인은 문어체 뉴스 도메인이다. 사내 문서·구어체 분포는"
        " tenant golden set(§48.6)으로만 검증할 수 있다.",
        "- tail 커버리지의 미포함 항목은 §16 카탈로그 확장의 실측 우선순위"
        " 신호로 사용한다 (OQ-001).",
        "",
        "*generated by `python -m eval.run_wild`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    corpus = load_corpus()
    print(f"corpus: {len(corpus)} sentences")
    t0 = time.perf_counter()
    silver = run_silver_and_tails(corpus)
    print("silver suite done")
    fake_fp = run_fake_glossary_fp(corpus)
    payload = {
        "corpus_sentences": len(corpus),
        "silver": silver,
        "fake_fp": fake_fp,
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "wild.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "WILD_CORPUS.md")
    print(json.dumps({
        "silver_gold_in_set": silver["gold_in_set_e2e"],
        "resolved_precision": silver["resolved"]["precision_given_commit"],
        "tail_coverage": silver["tail_distribution"]["coverage"],
        "fake_fp_resolved": fake_fp["resolved_fp_count"],
    }, ensure_ascii=False, indent=2))
    print(f"wrote {out / 'wild.json'} and {ROOT / 'WILD_CORPUS.md'}")


if __name__ == "__main__":
    main()

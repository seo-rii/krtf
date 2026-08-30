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

from .metrics import wilson_interval, provenance_line
from .synthetic import absent_bindings_only, build_synthetic_glossary
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent

# aliases whose bare occurrence in news is near-certainly an org mention
SILVER_MIN_LEN = 3
# short/ambiguous aliases: measured for detection stats only, not recall
DETECTION_ONLY = {"한전", "한은", "헌재", "KT", "SKT", "국민연금", "청와대",
                  "네이버", "카카오",
                  # 지자체 축약형: 지명·수식 용법과 겹침 (서울시내, 제주도 여행)
                  "서울시", "부산시", "인천시", "세종시", "제주도"}


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
            nxt = text[i + len(a)] if i + len(a) < len(text) else ""
            if (a[-1].isascii() and a[-1].isalnum()
                    and nxt.isascii() and nxt.isalnum()):
                continue  # KBS inside KBSN — mid-Latin-run, not a clean token
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


def run_silver_and_tails(corpus: list[dict], encoder=None, policy=None) -> dict:
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    snap = compile_snapshot(glossary, encoder=encoder, policy=policy,
                            run_conformance=encoder is None)
    alias_to_entity = {b.surface: b.entity_id for b in glossary.alias_bindings}
    silver_aliases = [s for s in alias_to_entity
                      if len(s) >= SILVER_MIN_LEN and s not in DETECTION_ONLY]

    fst = ParticleFST()
    all_surfaces = set(alias_to_entity)
    total = detected = in_set = 0
    resolved = resolved_correct = 0
    # global commit ledger: EVERY RESOLVED mention in the scanned
    # sentences, not only those landing on a silver span. Counting only
    # on-span commits makes precision structurally 1.0 — it cannot see the
    # commits that would be wrong (REVIEW: silver-span-only precision must
    # not be presented as system precision).
    ledger_commits = ledger_on_silver = ledger_correct = 0
    ledger_examples: list[dict] = []
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

        gold_spans = {(s, e): alias_to_entity[a] for s, e, a in occs}
        for m in mentions:
            if m["surface"] in DETECTION_ONLY:
                detection_only_hits += 1
            if m.get("link_decision") == "RESOLVED":
                cp = m["span"]["codepoint"]
                ledger_commits += 1
                expected = gold_spans.get((cp["start"], cp["end"]))
                if expected is not None:
                    ledger_on_silver += 1
                    ledger_correct += int(
                        m["resolved_entity"]["entity_id"] == expected)
                elif len(ledger_examples) < 10:
                    ledger_examples.append(
                        {"text": text, "surface": m["surface"],
                         "entity_id": m["resolved_entity"]["entity_id"]})

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
        "commit_ledger": {
            "commits": ledger_commits,
            "on_silver_span": ledger_on_silver,
            "correct_on_silver": ledger_correct,
            "off_silver_span": ledger_commits - ledger_on_silver,
            "off_span_examples": ledger_examples,
            "note": "off-span commits are unlabeled here: the silver "
                    "scanner only labels registered unambiguous surfaces, "
                    "so these are candidates for human adjudication, not "
                    "confirmed false positives",
        },
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


def run_fake_glossary_fp(corpus: list[dict], encoder=None, policy=None) -> dict:
    g_dict, meta = build_synthetic_glossary(400, seed=5)
    # keep only bindings whose surface cannot occur in the corpus *through
    # any normalization profile*: any hit on real text is then a false
    # positive by construction. A case-sensitive substring test is not
    # enough — the matcher case-folds, so `gb` survives a corpus containing
    # `GB` and then matches it, scoring a construction error as a product FP.
    g_dict, removed = absent_bindings_only(g_dict, [r["text"] for r in corpus])
    kept = g_dict["alias_bindings"]
    snap = compile_snapshot(load_glossary(g_dict), strict=False, policy=policy,
                            run_conformance=False, encoder=encoder)

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
        f"코퍼스: HuggingFace 공개 한국어 텍스트 {payload['corpus_sentences']}문장"
        " (뉴스 헤드라인·국민청원·판례 전문·위키 지문 — 다중 도메인)."
        " 합성 데이터와 달리 구현 카탈로그와 독립적인 실 분포다."
        " 재현: `python -m eval.run_wild` (최초 실행 시 다운로드).",
        "",
        "소스 구성: " + ", ".join(
            f"`{k.split('/')[-1]}` {v}"
            for k, v in sorted(payload.get("corpus_by_source", {}).items(),
                               key=lambda kv: -kv[1])),
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
        f"- RESOLVED precision (silver span 위 commit 한정):"
        f" **{s['resolved']['precision_given_commit']}**"
        f" ({s['resolved']['count']} commits,"
        f" silver 대비 coverage {s['resolved']['coverage_of_silver']})"
        f" — 아래 commit ledger를 함께 볼 것",
        f"- 짧은/다의 표면형(한전·한은·KT 등) 탐지 mention: "
        f"{s['detection_only_mentions']}건 (recall 분모 제외)",
        f"- latency p50/p95: {s['latency_ms']['p50']} / {s['latency_ms']['p95']} ms",
        "",
        "### 1.5 Commit ledger — 이 precision이 뜻하지 않는 것",
        "",
        f"위 precision은 **silver span 위에 떨어진 commit만**의 정확도다."
        f" 같은 문장들에서 실제로 발생한 전체 RESOLVED는"
        f" **{s['commit_ledger']['commits']}건**이고, 그중"
        f" {s['commit_ledger']['off_silver_span']}건은 silver span 밖이다.",
        "",
        "silver 스캐너는 등록된 무모호 표면형만 라벨링하므로 span 밖 commit은"
        " *오탐으로 확인된 것이 아니라 라벨이 없는 것*이다 (다른 등록 용어의"
        " 정당한 확정일 수도 있다). 따라서 이 값은 시스템 전체 precision이"
        " 아니며, 그렇게 인용해서도 안 된다 — 전체 precision을 주장하려면"
        " exhaustive human annotation이 필요하다 (ROADMAP 백로그).",
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
    ]
    if payload.get("dense_variants"):
        lines += [
            "",
            "## 3.5 V2 dense 구성 비교 (실 텍스트)",
            "",
            "| 구성 | silver gold-in-set | RESOLVED precision | fake-glossary RESOLVED FP |",
            "|---|---:|---:|---:|",
            f"| symbolic (기본) | {s['gold_in_set_e2e']['rate']} "
            f"| {s['resolved']['precision_given_commit']} "
            f"| {fp['resolved_fp_count']} |",
        ]
        for name, v in payload["dense_variants"].items():
            vs, vf = v["silver"], v["fake_fp"]
            lines.append(
                f"| {name} | {vs['gold_in_set_e2e']['rate']} "
                f"| {vs['resolved']['precision_given_commit']} "
                f"| {vf['resolved_fp_count']} |")
        lines += [
            "",
            "dense 채널은 recall 신호만 추가해야 하며(silver 비열화), 가짜"
            " glossary에서 RESOLVED commit을 만들면 안 된다(0 유지).",
        ]
    lines += [
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
        provenance_line(ROOT),
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
    # V2: same real-text suites with the dense channel enabled — dense must
    # not erode silver recall nor create fake-glossary commits
    dense_variants = {}
    from ktrf.encoders import HashEncoder, OnnxE5Encoder

    encoders = {"hash_dense": HashEncoder()}
    e5_dir = ROOT / "models" / "multilingual-e5-small"
    if e5_dir.exists():
        encoders["e5_dense"] = OnnxE5Encoder(e5_dir)
    for name, enc in encoders.items():
        print(f"dense variant: {name}")
        dense_variants[name] = {
            "silver": run_silver_and_tails(corpus, encoder=enc),
            "fake_fp": run_fake_glossary_fp(corpus, encoder=enc),
        }
    payload = {
        "corpus_sentences": len(corpus),
        "corpus_by_source": dict(Counter(r["source"] for r in corpus)),
        "silver": silver,
        "fake_fp": fake_fp,
        "dense_variants": dense_variants,
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
    print(f"wrote {out / 'wild.json'} and {ROOT / 'reports' / 'WILD_CORPUS.md'}")


if __name__ == "__main__":
    main()

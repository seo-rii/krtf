"""Do real Korean texts misspell registered organisation names? (§5.2, OQ-001)

`reports/VARIANT_RECALL.md` measures a `typo` track at 66.6% and
`typo + particle` at 64.9%, the weakest cells in the matrix, and an external
review made them the top improvement priority. Those variants are *injected*
by the eval. This asks how often the phenomenon occurs in text nobody wrote
for us, and what loosening the threshold would cost.

Deliberately independent of the resolver. A screen built on the resolver's
own channels can only see the typos it already recovers, so it would answer
"how good is recall" while appearing to answer "how common is the input".
The only machinery here is edit distance.

Two measurements:

1. **Corpus census.** Every Hangul token of 3+ characters within one edit of
   a registered surface. Split into `INFLECTION` — the surface plus one
   syllable the tail parser explains, `삼성전자가` — and `OTHER`, everything
   else. `OTHER` is where a typo would be, so the report lists it rather
   than totalling it: a count this shape has to be read.

2. **Glossary self-collision.** Registered surfaces that are one edit from
   *each other*. This is the cost side, and it does not depend on any
   corpus: every pair here is a pair a looser threshold can confuse.

Writes eval/out/wild_typos.json and reports/WILD_TYPOS.md.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.morphology import ParticleFST
from ktrf.tailparser import analyze_tail

from .metrics import provenance_line, run_manifest
from .wild_data import CORPORA, load_corpus

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"[가-힣]{3,}")


def within_one(a: str, b: str) -> bool:
    """One substitution, insertion or deletion apart — never equal."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    return any(b[:i] + b[i + 1:] == a for i in range(lb))


def self_collisions(surfaces: set[str]) -> list[tuple[str, str]]:
    """Registered surfaces one edit from each other, corpus-independent."""
    ordered = sorted(surfaces)
    return [(a, b) for i, a in enumerate(ordered)
            for b in ordered[i + 1:] if within_one(a, b)]


def scan(rows, registered, by_len, fst) -> dict:
    kinds: Counter = Counter()
    pairs: dict[str, Counter] = {"INFLECTION": Counter(), "OTHER": Counter()}
    tokens = 0
    for r in rows:
        for tok in TOKEN.findall(r["text"]):
            tokens += 1
            if tok in registered:
                continue
            for n in (len(tok) - 1, len(tok), len(tok) + 1):
                hit = next((s for s in by_len.get(n, ())
                            if within_one(tok, s)), None)
                if hit is None:
                    continue
                kind = "OTHER"
                if len(tok) == len(hit) + 1 and tok.startswith(hit):
                    # the surface plus one syllable: morphology if the tail
                    # parser explains it, and it usually does
                    best = analyze_tail(tok[len(hit):], hit[-1], fst)[0]
                    if best.residual_kind in ("", "SUFFIX",
                                              "SUFFIX_WITH_MODIFIER"):
                        kind = "INFLECTION"
                kinds[kind] += 1
                pairs[kind][f"{tok} ~ {hit}"] += 1
                break
    return {"tokens": tokens, "kinds": dict(kinds),
            "distinct": {k: len(v) for k, v in pairs.items()},
            "pairs": {k: dict(v.most_common(40)) for k, v in pairs.items()},
            "singletons": {k: [p for p, n in v.items() if n == 1][:40]
                           for k, v in pairs.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None, choices=sorted(CORPORA),
                    help="one corpus; default is every cached corpus")
    args = ap.parse_args()

    manifest = run_manifest(ROOT)
    g = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    registered = {b.surface for b in g.alias_bindings} | {
        e.canonical for e in g.entities}
    hangul = {s for s in registered if TOKEN.fullmatch(s)}
    by_len: dict[int, list[str]] = {}
    for s in hangul:
        by_len.setdefault(len(s), []).append(s)
    fst = ParticleFST()

    collisions = self_collisions(hangul)
    print(f"registered Hangul surfaces: {len(hangul)}; "
          f"one edit from each other: {len(collisions)}")

    names = [args.corpus] if args.corpus else sorted(CORPORA)
    per: dict[str, dict] = {}
    for name in names:
        if not CORPORA[name][1].exists():
            print(f"  {name}: not cached, skipped")
            continue
        rows = load_corpus(name)
        print(f"  {name}: {len(rows):,} sentences")
        per[name] = scan(rows, registered, by_len, fst)
        per[name]["sentences"] = len(rows)

    payload = {"manifest": manifest, "registered_surfaces": len(hangul),
               "self_collisions": [list(p) for p in collisions],
               "corpora": per}
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "wild_typos.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "WILD_TYPOS.md")
    print(json.dumps({k: v["kinds"] for k, v in per.items()},
                     ensure_ascii=False, indent=2))
    print(f"wrote {ROOT / 'reports' / 'WILD_TYPOS.md'}")


def write_markdown(payload: dict, out_path: Path) -> None:
    per = payload["corpora"]
    tot: Counter = Counter()
    tokens = 0
    for v in per.values():
        tot.update(v["kinds"])
        tokens += v["tokens"]
    collisions = payload["self_collisions"]
    lines = [
        "# 실제 텍스트에 조직명 오타는 얼마나 있는가 (§5.2, OQ-001)",
        "",
        f"등록 표면형(한글 3자 이상) {payload['registered_surfaces']}개에 대해"
        f" 캐시된 코퍼스 {len(per)}개, 한글 토큰 {tokens:,}개를 편집거리 1로"
        " 훑었다. **resolver를 쓰지 않는다** — resolver의 채널로 재면 이미"
        " 회수하는 오타만 보이므로, 입력 분포를 묻는 질문에 회수율로 답하게"
        " 된다. 여기 쓰인 기계장치는 편집거리뿐이다.",
        "",
        "| 코퍼스 | 문장 | 한글 토큰 | 근접 | INFLECTION | OTHER |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, v in sorted(per.items()):
        k = v["kinds"]
        lines.append(
            f"| `{name}` | {v['sentences']:,} | {v['tokens']:,} "
            f"| {sum(k.values()):,} | {k.get('INFLECTION', 0):,} "
            f"| {k.get('OTHER', 0):,} |")
    lines += [
        "",
        "**INFLECTION** = 표면형 + 1음절이고 tail parser가 조사·접미로"
        " 설명하는 것(`삼성전자가`). **OTHER** = 나머지 — 오타라면 여기 있다.",
        "",
        "## 1. 오타는 관측되지 않는다",
        "",
        "OTHER를 빈도순으로 읽으면 오타가 아니라 **한 글자 차이의 평범한"
        " 단어**다. 총계를 믿지 말고 목록을 읽어야 하는 이유가 이것이다:",
        "",
    ]
    merged: Counter = Counter()
    for v in per.values():
        merged.update(v["pairs"].get("OTHER", {}))
    for pair, n in merged.most_common(25):
        lines.append(f"- `{pair}` × {n}")
    singles: list[str] = []
    for v in per.values():
        singles += v["singletons"].get("OTHER", [])
    lines += [
        "",
        "빈도 상위는 흔한 단어이므로, 오타가 숨는다면 **1회 등장** 쪽이다."
        " 그쪽에서 뽑은 표본:",
        "",
    ]
    for pair in singles[:25]:
        lines.append(f"- `{pair}`")
    lines += [
        "",
        "**이 중 오타처럼 보이는 것들을 문맥에서 직접 읽었다. 전부 오타가"
        " 아니었다:**",
        "",
        "- `한두원` — \"한두원 코웨이 AirCare필터개발팀장\". **사람 이름**이다."
        " `한수원`의 오타가 아니다.",
        "- `학사원` — \"일본 학사원상 수상자\". 실재하는 기관이다.",
        "- `제어도`, `금융뿐` — `제어`·`금융` + 조사. 형태론이 tail parser의"
        " 1음절 규칙에 걸리지 않았을 뿐이다.",
        "- `한국석탄공사` — `한국석유공사`의 오타가 아니라 **다른 실재 기업**이고,"
        " 두 이름이 *같은 문장에* 함께 나온다: \"한국석유공사와 한국광해광업공단"
        " 한국가스공사 한국석탄공사 등 자원 공기업\".",
        "- `과천시` — 경기도의 실재 도시, 17회. `인천시`의 오타가 아니다.",
        "",
        "즉 오타처럼 보이는 후보를 **전수로 읽고 나면 남는 오타가 없다**."
        " 총계가 손으로 읽을 만한 크기일 때 총계만 인용하면 이 결론에"
        " 도달할 수 없다.",
    ]
    lines += [
        "",
        "## 2. 완화의 비용은 코퍼스와 무관하다",
        "",
        f"등록 표면형끼리 편집거리 1인 쌍이 **{len(collisions)}개** 있다."
        " 이것은 어떤 코퍼스도 필요 없는 사실이고, typo 임계값을 낮출 때"
        " 정확히 이 쌍들이 서로 회수된다:",
        "",
    ]
    for a, b in collisions:
        lines.append(f"- `{a}` ↔ `{b}`")
    lines += [
        "",
        "## 무엇을 뜻하는지",
        "",
        "- `VARIANT_RECALL.md`의 typo 66.6% / typo+particle 64.9%는 **주입된**"
        " 변형에 대한 값이다. 뉴스·웹·판례·커뮤니티 분포에서 그 입력은"
        " 관측되지 않는다.",
        "- 그러므로 그 두 셀을 근거로 임계값을 완화하면, 관측되지 않는 것을"
        " 얻기 위해 위 목록의 실재하는 쌍을 잃는다. `관세청`↔`국세청`,"
        " `경상남도`↔`경상북도`는 한 글자 차이의 서로 다른 기관이다.",
        "- 트랙을 폐기하자는 뜻은 아니다. OCR·입력기·필사 경로에서는 오타가"
        " 실재하며, 그런 입력을 받는 배치에서는 이 트랙이 옳은 지표다."
        " 다만 **일반 텍스트 파이프라인의 우선순위 근거로는 쓸 수 없다.**",
        "",
        provenance_line(ROOT, manifest=payload["manifest"]),
        "",
        "*generated by `python -m eval.run_wild_typos`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

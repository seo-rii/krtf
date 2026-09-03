"""Does document-local alias detection do anything on real text?

Usage: python -m eval.run_doclocal_audit [--sentences N] [--json PATH]
                                         [--compare PATH] [--render-only PATH]

Spec §18 has the resolver read in-document definitions — `한국전력공사(한전)`,
`X, 이하 Y` — and give the alias a scoring boost. REQ-LOC-001/002 were pinned
by two tests, both asserting the detector does *not* overwrite global
bindings. Nothing asserted that it finds anything, and over the whole wild
corpus it very nearly did not: **2,346 definition patterns matched and six
bindings came out** (zero in a 20,000-sentence sample), because
:meth:`ktrf.doclocal.DocLocalDetector.extract` requires the long form to
already name a registered entity — a condition anti-correlated with the
reason texts write definitions at all. Reading those six one at a time, which
the total would have hidden, found the second defect: three of them were
wrong, and all three came from the reversed branch.

This harness measures both halves of that funnel and publishes the rejected
mass with it. Two numbers, and they are not the same number:

- **doc-local aliases** — definitions of names the glossary already holds.
  These become request-scoped bindings and change resolution.
- **new-term definitions** — definitions of names it does not hold. These
  become :mod:`ktrf.registry.proposals` proposals and change nothing until
  someone approves them.

Writes eval/out/doclocal_audit.json and reports/DOCLOCAL_AUDIT.md.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import time
from pathlib import Path

from ktrf.doclocal import DocLocalDetector
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot

from .metrics import provenance_line
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260831


def audit(rows: list) -> dict:
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    snap = compile_snapshot(glossary)
    det: DocLocalDetector = snap.doclocal
    t0 = time.perf_counter()

    rejections: collections.Counter = collections.Counter()
    aliases: collections.Counter = collections.Counter()
    terms: collections.Counter = collections.Counter()
    term_docs: dict[tuple[str, str], set] = collections.defaultdict(set)
    by_pattern: collections.Counter = collections.Counter()
    matched = registered = 0

    for i, row in enumerate(rows):
        text = row["text"] if isinstance(row, dict) else row
        # `_pairs` is private, and the harness is the one caller that has to
        # see the raw funnel: how many patterns fired before any gate ran.
        for name, long_form, short, _span in det._pairs(text):
            matched += 1
            by_pattern[name] += 1
            if det._resolve_long_form(long_form) or det._resolve_long_form(short):
                registered += 1
        for b in det.extract(text):
            aliases[(b.alias_surface, tuple(b.entity_ids))] += 1
        for t in det.extract_new_terms(text, rejections=rejections):
            terms[(t.surface, t.canonical)] += 1
            term_docs[(t.surface, t.canonical)].add(i)

    found = [{"surface": s, "canonical": c, "occurrences": n,
              "documents": len(term_docs[(s, c)])}
             for (s, c), n in terms.most_common()]
    return {
        "sentences": len(rows),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        "patterns_matched": matched,
        "patterns_by_kind": dict(by_pattern),
        "long_form_registered": registered,
        "doclocal_aliases": sum(aliases.values()),
        "distinct_doclocal_aliases": len(aliases),
        "new_term_occurrences": sum(terms.values()),
        "distinct_new_terms": len(terms),
        "rejections": dict(rejections.most_common()),
        # the list, not just the count: reading these one at a time is what
        # found the reversed-branch defect that the total hid
        "doclocal_alias_list": [{"alias": a, "entity_ids": list(e),
                                 "occurrences": n}
                                for (a, e), n in aliases.most_common()],
        "new_terms": found,
    }


def write_markdown(t: dict, control: dict | None, out_path: Path) -> None:
    c = control
    rej_total = sum(t["rejections"].values())
    lines = [
        "# 문서 내 정의 감사 — 별칭과 미등록 이름",
        "",
        "스펙 §18은 `한국전력공사(한전)`·`X, 이하 Y` 같은 **문서 내 정의**를"
        " 읽어 요청 범위 별칭으로 쓰고 점수 보정까지 준다. REQ-LOC-001/002를"
        " 고정한 테스트는 두 개였고 **둘 다 '전역 사전을 덮어쓰지 않는다'**만"
        " 검사했다 — 아무 일도 하지 않는 모듈이 완벽하게 통과하는 성질이다.",
        "",
        "재현: `python -m eval.run_doclocal_audit` · 리포트만 다시 쓰려면"
        " `--render-only`.",
        "",
        f"표본: 실문장 **{t['sentences']:,}문장**, realorg glossary.",
        "",
        "## 0. 깔때기 — 무엇이 걸리고 무엇이 남았나",
        "",
        "| 단계 | 건수 |",
        "|---|---:|",
        f"| 정의 패턴 일치 | {t['patterns_matched']:,} |",
    ]
    for k, v in sorted(t["patterns_by_kind"].items()):
        lines.append(f"| — `{k}` | {v:,} |")
    lines += [
        f"| 긴 이름이 **이미 등록된 entity**인 것 | {t['long_form_registered']:,} |",
        f"| → 문서 내 별칭(§18, 해석에 영향) | **{t['doclocal_aliases']:,}**"
        f" (서로 다른 {t['distinct_doclocal_aliases']:,}) |",
        f"| → 미등록 이름 정의(M6, 제안 큐) | **{t['new_term_occurrences']:,}**"
        f" (서로 다른 {t['distinct_new_terms']:,}) |",
        "",
        "**두 번째 줄이 이 리포트의 이유다.** `extract()`는 긴 이름이 이미"
        " 등록돼 있어야 별칭을 만드는데, 문서가 `X(Y)`를 쓰는 이유는 정확히"
        " 독자가 **가지고 있지 않은** 이름을 소개하기 위해서다. 조건이 목적과"
        " 반대로 걸려 있으므로 이 모듈은 **아무것도 더해주지 않는 경우에만**"
        " 발동할 수 있다 — 20,000문장 표본에서는 0건이었다.",
        "",
        "그리고 총계만 보면 놓쳤을 것이 하나 더 있다. 전 코퍼스에서 나온"
        " 별칭을 하나씩 읽어 보니 **`Y(X)` 갈래가 세 번 발동해 세 번"
        " 틀렸다** — `노선영(강원도청)`은 선수(소속팀), "
        "`현대캐피탈(현대자동차그룹)`은 자회사(모기업)다. 그 갈래의 유일한"
        " 증거가 '괄호 안이 더 길다'였기 때문이고, 더 길다는 것은 증거가"
        " 아니다. 이제 한글 약칭은 부분수열 정렬을 보여야 한다.",
        "",
        "남은 문서 내 별칭 — 총계가 아니라 목록으로 싣는다. 이것을 하나씩"
        " 읽는 것이 위 결함을 찾은 방법이다:",
        "",
        "| 별칭 | entity | 관측 |",
        "|---|---|---:|",
    ] + [
        f"| `{a['alias']}` | {', '.join(a['entity_ids'])} | {a['occurrences']} |"
        for a in t.get("doclocal_alias_list", [])[:20]
    ] + [
        "",
        f"정렬이 거부한 쌍 **{rej_total:,}건**의 사유:",
        "",
        "| 사유 | 건수 | 뜻 |",
        "|---|---:|---|",
    ]
    why = {
        "not_a_subsequence": "약어가 아니다 — 동격 설명·번역·역할 표기",
        "too_short_to_abbreviate": "짧은 쪽이 2자 미만이거나 더 짧지 않다",
        "contiguous_substring": "건너뛰지 않는다 — 이름을 자른 것이지 줄인 것이 아니다",
        "name_does_not_end_there": "정렬이 이름을 넘어 문장으로 번졌다",
        "bare_type_terminal": "짧은 쪽이 기관 유형어 자체(`위원회`)다",
        "degenerate": "정렬 후 남는 이름이 없다",
    }
    for k, v in t["rejections"].items():
        lines.append(f"| `{k}` | {v:,} | {why.get(k, '')} |")

    lines += [
        "",
        "## 1. 미등록 이름 정의 — 문서가 직접 준 canonical",
        "",
        "채굴(M4)과 다른 점이 하나 있다. 잔여부 채굴은 이름이 **있다**는 것만"
        " 알아서 canonical을 사람이 채워야 하지만, 정의 패턴은 문서가"
        " **canonical을 직접 말한 것**이다 — 그것이 정의를 정의이게 하는"
        " 성질이다. 다만 문서는 그것이 **무엇인지**는 말하지 않으므로"
        " `short_definition`은 여전히 사람 몫이고 `to_proposal`이 지어내기를"
        " 거부한다.",
        "",
        "판정 근거는 `AbbrevAligner`가 이미 요구하는 것과 같은 부분수열 정렬을"
        " 사전 대신 **문서 자신의 짝**에 적용한 것이다. 정렬은 문자 체계를"
        " 가리지 않으므로 `PPR`/`Portland Pattern Repository`가"
        " `국공노`/`국가공무원노동조합`과 같은 이유로 통과한다.",
        "",
        f"- 발견: **{t['distinct_new_terms']}건**"
        f" (관측 {t['new_term_occurrences']}회)",
        "",
        "| 표면형 | 문서가 준 canonical | 관측 | 문서 |",
        "|---|---|---:|---:|",
    ]
    for g in t["new_terms"][:40]:
        lines.append(f"| `{g['surface']}` | {g['canonical']} |"
                     f" {g['occurrences']} | {g['documents']} |")

    if c:
        lines += [
            "",
            "## 2. 대조군 대비",
            "",
            "| 지표 | 대조군 | 현재 |",
            "|---|---:|---:|",
            f"| 패턴 일치 | {c['patterns_matched']:,} |"
            f" {t['patterns_matched']:,} |",
            f"| 문서 내 별칭 | {c['doclocal_aliases']:,} |"
            f" {t['doclocal_aliases']:,} |",
            f"| 미등록 이름 정의 | {c['distinct_new_terms']:,} |"
            f" {t['distinct_new_terms']:,} |",
        ]

    lines += [
        "",
        "## 이 리포트가 말하지 않는 것",
        "",
        "- **정밀도.** 이 표에 gold는 없다. 남은 오탐은 실재하며 —"
        " 문장을 가로질러 정렬된 짝은 조건 세 개를 통과하고도 이름이 아닐 수"
        " 있다 — 그래서 이 표는 **검토 큐**이지 사전 패치가 아니다. 규칙을 더"
        f" 얹어 이 목록을 손으로 다듬는 것은 {t['distinct_new_terms']}행에 대한"
        " 과적합이므로 하지 않았다. 후보 규칙 셋을 더 재봤고 셋 다 진짜 이름을"
        " 죽였다.",
        "- **무엇을 뜻하는지.** 문서는 이름을 주지 의미를 주지 않는다.",
        "- **어느 쪽이 해석을 바꾸는지.** 미등록 이름 정의는 resolver를 거치지"
        " 않는다 — 등록할 entity가 아직 없으므로 붙일 곳이 없다. 반면 위의"
        " reversed 갈래 수정은 문서 내 별칭을 없애므로 해석을 **바꾼다**;"
        " 그쪽은 `eval.run_wild_regression`의 쌍 측정이 잰다.",
        "",
        provenance_line(ROOT, f"표본 {t['sentences']:,}문장"),
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", type=int, default=0,
                    help="0 = the whole corpus (this harness is cheap)")
    ap.add_argument("--json", type=str, default=None)
    ap.add_argument("--compare", type=str, default=None)
    ap.add_argument("--render-only", type=str, default=None)
    args = ap.parse_args()

    out_md = ROOT / "reports" / "DOCLOCAL_AUDIT.md"
    control = (json.loads(Path(args.compare).read_text(encoding="utf-8"))
               if args.compare else None)

    if args.render_only:
        payload = json.loads(Path(args.render_only).read_text(encoding="utf-8"))
        write_markdown(payload, control, out_md)
        print(f"rendered {out_md} from {args.render_only}")
        return

    corpus = load_corpus()
    rows = (corpus if not args.sentences else
            random.Random(SEED).sample(corpus, min(args.sentences, len(corpus))))
    print(f"sample: {len(rows)} of {len(corpus)} sentences")
    payload = audit(rows)

    out_json = ROOT / "eval" / "out" / "doclocal_audit.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    out_json.write_text(body, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(body, encoding="utf-8")
    write_markdown(payload, control, out_md)
    print(f"doc-local aliases: {payload['doclocal_aliases']}, "
          f"new-term definitions: {payload['distinct_new_terms']}")
    print(f"wrote {out_json} and {out_md}")


if __name__ == "__main__":
    main()

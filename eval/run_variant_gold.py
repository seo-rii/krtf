"""Grade the resolver against hand-labelled real sentences.

Usage: python -m eval.run_variant_gold [--json PATH] [--compare PATH]

Every other real-text suite in ``eval/`` *counts* — how many mentions, how
many commits, how the tails are distributed. None of them says whether the
labels are **right**, because saying so needs someone to read the sentence.
``eval/data/variant_gold.jsonl`` is that reading: 160 (text, span) claims,
each one asserting what is true at that span, written down before any
resolver output was compared against it.

What this measures, and what it does not:

- **it measures precision and the price of silence** — of the mentions the
  resolver emits at these spans, how many are real; of the spans where a
  commit is warranted, how many it actually makes.
- **it does not measure corpus recall.** The spans come from a stratified
  sample of resolver output, so a mention the resolver never proposed is
  not in the file. Recall over real text is the silver suite's job
  (``eval.run_wild``), and family recall is ``eval.run_variant_recall``.
- **the aggregate is not a corpus rate.** Strata were quota-sampled to put
  enough mass on the rare and interesting cases, so read the per-stratum
  rows, never the total, as "how often this happens in Korean text".

Three labels do the work (docs/VARIANT_GOLD_GUIDE.md has the rules):

``span_ok``
    the span does not cut a word in half (`대한`민국, `자부`심).
``refers``
    ``YES`` the entity is mentioned here · ``PARTIAL`` its name occurs
    inside the proper name of something else (`농협`카드, `카카오`톡) ·
    ``NO`` not a mention at all (`금융`시장).
``should_commit``
    a careful reader, given the glossary, would name that entity here.
    Judged from the sentence, not from the guard's rules — otherwise the
    resolver would be grading its own homework.

Writes eval/out/variant_gold.json and reports/VARIANT_GOLD.md.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import provenance_line, wilson_interval

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "data" / "variant_gold.jsonl"
GLOSSARY = ROOT / "examples" / "realorg_glossary.yaml"

# gold vocabulary -> the response's spelling of the same idea
_IDENTITY = {"SAME": "SAME_AS_CORE", "DISTINCT": "DISTINCT_FROM_CORE"}


def load_gold(path: Path = GOLD) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cp(m: dict) -> tuple[int, int]:
    cp = m["span"]["codepoint"]
    return cp["start"], cp["end"]


def _entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def grade(rows: list[dict], snap) -> list[dict]:
    out = []
    for row in rows:
        span = tuple(row["span"])
        g = row["gold"]
        resp = resolve(snap, row["text"], mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        m = next((x for x in resp["mentions"] if _cp(x) == span), None)
        fs = m.get("full_surface") if m else None
        committed = m.get("link_decision") == "RESOLVED" if m else False
        got_entity = (m["resolved_entity"]["entity_id"]
                      if committed else None)
        rec = {
            "id": row["id"], "stratum": row["stratum"],
            "gold_refers": g["refers"], "gold_span_ok": g["span_ok"],
            "gold_entity": g["entity"], "should_commit": g["should_commit"],
            "emitted": m is not None,
            "committed": committed,
            "commit_entity": got_entity,
            "commit_correct": bool(committed and g["should_commit"]
                                   and got_entity == g["entity"]),
            "commit_unwarranted": bool(committed and not g["should_commit"]),
            "in_set": bool(m and g["entity"] and g["entity"] in _entities(m)),
            "identity_gold": g["full_identity"],
            "identity_got": fs.get("identity") if fs else None,
            "relation_gold": g["relation"],
            "relation_got": (m.get("core_link", {}).get("relation")
                             if m else None),
            "wider_reported": fs is not None,
        }
        # A relation named on a span the reader says is not a mention at all
        # is an overclaim: the response has moved from "this surface is not
        # that core", which the morphology settles, to "here is how they
        # relate", which it does not. Both ride the candidate layer, so this
        # counts legibility rather than safety.
        rec["overclaimed_relation"] = bool(
            g["refers"] != "YES" and rec["relation_got"]
            and rec["relation_got"] != "UNKNOWN")
        # `SAME` says the wider string is still just the entity, so saying
        # SAME_AS_CORE and saying nothing at all are the same answer — the
        # response has not claimed the wider string is something else. That
        # matters because a tail the particle catalog learns to strip stops
        # being a "wider surface" at all: `SKT서` reported SAME before `서`
        # was a particle and reports nothing after, and both are right.
        # `DISTINCT` gets no such licence: staying silent there is a failure
        # to warn, which is exactly what invariant ② exists to prevent.
        rec["identity_correct"] = (
            rec["identity_got"] == _IDENTITY.get(g["full_identity"])
            or (g["full_identity"] == "SAME" and rec["identity_got"] is None))
        rec["relation_correct"] = (bool(g["relation"])
                                   and rec["relation_got"] == g["relation"])
        out.append(rec)
    return out


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson_interval(k, n)
    return {"hits": k, "total": n,
            "rate": round(k / n, 4) if n else None,
            "ci95": [round(lo, 4), round(hi, 4)]}


def summarise(graded: list[dict]) -> dict:
    emitted = [r for r in graded if r["emitted"]]
    yes = [r for r in graded if r["gold_refers"] == "YES"]
    want = [r for r in graded if r["should_commit"]]
    committed = [r for r in graded if r["committed"]]
    ident = [r for r in graded if r["identity_gold"] in _IDENTITY]
    rel = [r for r in graded if r["relation_gold"]]

    per_stratum = {}
    for s in sorted({r["stratum"] for r in graded}):
        rs = [r for r in graded if r["stratum"] == s]
        em = [r for r in rs if r["emitted"]]
        per_stratum[s] = {
            "rows": len(rs),
            "emitted": len(em),
            "refers_yes": _rate(sum(r["gold_refers"] == "YES" for r in em),
                                len(em)),
            "refers_partial": sum(r["gold_refers"] == "PARTIAL" for r in em),
            "refers_no": sum(r["gold_refers"] == "NO" for r in em),
            "span_cut": sum(not r["gold_span_ok"] for r in em),
            "commits": sum(r["committed"] for r in em),
            "unwarranted_commits": sum(r["commit_unwarranted"] for r in em),
        }

    return {
        "rows": len(graded),
        "emitted": len(emitted),
        # |mention — of what the resolver put in the response, how much is real
        "mention_precision": _rate(
            sum(r["gold_refers"] == "YES" for r in emitted), len(emitted)),
        "mention_name_inside_a_name": _rate(
            sum(r["gold_refers"] == "PARTIAL" for r in emitted), len(emitted)),
        "core_span_cut_rate": _rate(
            sum(not r["gold_span_ok"] for r in emitted), len(emitted)),
        # |candidate
        "candidate_recall_on_real_mentions": _rate(
            sum(r["in_set"] for r in yes), len(yes)),
        # |commit — both directions
        "commit_precision": _rate(
            sum(r["commit_correct"] for r in committed), len(committed)),
        "unwarranted_commits": sum(r["commit_unwarranted"] for r in graded),
        "commit_recall_where_warranted": _rate(
            sum(r["commit_correct"] for r in want), len(want)),
        # labels
        # |mention — of the labels riding on spans that are not mentions,
        # how many name a relation instead of admitting they cannot
        "overclaimed_relations": _rate(
            sum(r["overclaimed_relation"] for r in graded),
            sum(1 for r in graded
                if r["emitted"] and r["gold_refers"] != "YES"
                and r["relation_got"])),
        "identity_accuracy": _rate(sum(r["identity_correct"] for r in ident),
                                   len(ident)),
        "relation_accuracy": _rate(sum(r["relation_correct"] for r in rel),
                                   len(rel)),
        "identity_confusion": dict(collections.Counter(
            f'{r["identity_gold"]}->{r["identity_got"]}' for r in graded
            if r["identity_gold"] or r["identity_got"]).most_common()),
        "by_stratum": per_stratum,
        "misses": [{"id": r["id"], "gold": r["gold_entity"]}
                   for r in want if not r["commit_correct"]][:20],
        "unwarranted": [{"id": r["id"], "committed": r["commit_entity"]}
                        for r in graded if r["commit_unwarranted"]][:20],
    }


def _d(now: dict | None, before: dict | None) -> str:
    if not now:
        return "—"
    s = f"**{now['rate']}** ({now['hits']}/{now['total']})"
    if before and before.get("rate") is not None and now["rate"] is not None:
        d = round(now["rate"] - before["rate"], 4)
        s = (f"{before['rate']} → {s} ({'+' if d > 0 else ''}{d})")
    return s


def write_markdown(payload: dict, out_path: Path,
                   control: dict | None = None) -> None:
    s = payload["summary"]
    c = control["summary"] if control else {}
    lines = [
        "# 실문장 gold — 라벨을 채점한다",
        "",
        "다른 실텍스트 스위트는 **센다**. 이 리포트는 **맞는지 본다**. 문장을"
        " 읽어야만 알 수 있는 것이라, 사람이 라벨한 (문장, span) 주장"
        f" **{s['rows']}건**을 고정 파일로 두고 그것에 대고 채점한다.",
        "",
        "재현: `python -m eval.run_variant_gold` ·"
        " gold: `eval/data/variant_gold.jsonl` ·"
        " 라벨 규칙: [VARIANT_GOLD_GUIDE](../docs/VARIANT_GOLD_GUIDE.md)",
        "",
        "> **이 표의 합계를 코퍼스 비율로 읽지 말 것.** span은 리졸버 출력의"
        " *층화* 표본이고, 드문 사례에 일부러 질량을 실었다. 코퍼스 비율은"
        " 층별 행에서만 읽을 수 있고, 재현율은 여기서 잴 수 없다"
        " (silver 스위트가 그 몫이다).",
        "",
        "## 0. 응답에 실린 것 중 진짜는 얼마인가",
        "",
        "| 지표 | 조건 | 값 |",
        "|---|---|---|",
        f"| mention precision (`refers=YES`) | `\\|mention` |"
        f" {_d(s['mention_precision'], c.get('mention_precision'))} |",
        f"| 남의 고유명 안의 이름 (`PARTIAL`) | `\\|mention` |"
        f" {_d(s['mention_name_inside_a_name'], c.get('mention_name_inside_a_name'))} |",
        f"| **단어를 자른 span** | `\\|mention` |"
        f" {_d(s['core_span_cut_rate'], c.get('core_span_cut_rate'))} |",
        f"| gold entity가 후보에 | `\\|candidate` |"
        f" {_d(s['candidate_recall_on_real_mentions'], c.get('candidate_recall_on_real_mentions'))} |",
        f"| commit precision | `\\|commit` |"
        f" {_d(s['commit_precision'], c.get('commit_precision'))} |",
        f"| **근거 없는 확정** | `\\|commit` |"
        f" {s['unwarranted_commits']}건 |",
        f"| **확정해야 할 때 확정한 비율** | `\\|commit` |"
        f" {_d(s['commit_recall_where_warranted'], c.get('commit_recall_where_warranted'))} |",
        "| **mention이 아닌 곳에 관계를 단언** | `\|mention` | "
        + _d(s["overclaimed_relations"], c.get("overclaimed_relations")) + " |",
        "",
        "바로 위 줄은 안전성이 아니라 **가독성**이다. gold가 \"여기엔 그 entity가"
        " 없다\"고 한 자리에 응답이 `ROLE_OF` 같은 **특정 관계**를 실은 비율이며,"
        " 전부 candidate 층이라 확정 오류가 아니다(아래 층별 표에서 확인). 형태론이"
        " 정하는 `DISTINCT`까지 지우자는 뜻도 아니다 — 지울 것은 근거 없는"
        " **관계 이름**뿐이다.",
        "",
        "마지막 줄이 이 리포트가 처음 재는 값이다. 다른 어떤 리포트도"
        " **침묵의 값**을 매기지 않는다 — commit precision 1.0은 아무것도"
        " 확정하지 않아도 얻어지고, 그 대가는 여기서만 보인다.",
        "",
        "## 1. 관계 라벨은 맞는가",
        "",
        f"- `full_surface.identity` 정확도: "
        f"{_d(s['identity_accuracy'], c.get('identity_accuracy'))}",
        f"- `core_link.relation` 정확도: "
        f"{_d(s['relation_accuracy'], c.get('relation_accuracy'))}",
        "",
        "gold → 관측 분포:",
        "",
    ]
    for k, n in s["identity_confusion"].items():
        lines.append(f"- `{k}` × {n}")
    stray = sum(n for k, n in s["identity_confusion"].items()
                if k.startswith("None->"))
    lines += [
        "",
        f"`None->…` **{stray}건**이 한 덩어리다. gold가 \"여기엔 그 entity가"
        " 없다\"(`refers≠YES`)고 한 자리에 응답이 관계 라벨을 실은 경우다."
        " 확정이 아니라 **후보 층의 라벨**이므로 commit 안전성과는 무관하지만,"
        " 응답을 읽는 소비자에게는 구분되지 않는다 — M2 검토의 미결 항목 #3이"
        " 이것이고, 이제 숫자가 붙었다. candidate 층과 commit 층을 응답에서도"
        " 분리하면 결함이 아니라 후보 층의 정상 출력이 된다.",
        "",
        "## 2. 층별",
        "",
        "| 층 | 행 | 응답에 실림 | refers=YES | PARTIAL | NO | 단어 자름"
        " | 확정 | 근거 없는 확정 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k, v in s["by_stratum"].items():
        lines.append(
            f"| `{k}` | {v['rows']} | {v['emitted']} |"
            f" {v['refers_yes']['rate']} | {v['refers_partial']}"
            f" | {v['refers_no']} | {v['span_cut']} | {v['commits']}"
            f" | {v['unwarranted_commits']} |")
    lines += [
        "",
        "## 3. 읽는 법과 한계",
        "",
        "- **주석자 1인, 대조 주석 없음.** κ가 없으므로 이 수치는 단일 판단이며,"
        " Gate A(2인 주석 κ≥0.75)를 충족하지 않는다. 경계 사례는 `note`에"
        " 이유를 적어 두었으니 재주석 시 그것부터 다툴 것.",
        "- `PARTIAL`은 오답이 아니라 **별도 범주**다. `농협카드`의 `농협`은"
        " 농협은행을 가리키지 않지만 무관한 문자열도 아니다. 이 비율이 높다는"
        " 것은 응답이 남의 고유명 안에서 core를 찾는다는 뜻이고, 그 자체가"
        " 확정 오류는 아니다(대부분 확정되지 않는다).",
        "- `should_commit`은 §2 계약과 문장 자체에서 나왔지 guard 규칙에서"
        " 나오지 않았다. 그래서 `확정해야 할 때 확정한 비율`이 1.0이 아닌 것을"
        " **결함이 아니라 보수성의 가격**으로 읽을 수 있다.",
        "- gold는 리졸버 출력에서 층화 추출했으므로 **리졸버가 한 번도 제안하지"
        " 않은 mention은 이 파일에 없다**. 그것은 recall이고 silver 스위트가 잰다.",
        "",
        provenance_line(ROOT),
        "",
        "*generated by `python -m eval.run_variant_gold`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--compare", type=Path, default=None)
    args = ap.parse_args()

    rows = load_gold()
    snap = compile_snapshot(load_glossary(str(GLOSSARY)))
    graded = grade(rows, snap)
    payload = {"gold_rows": len(rows), "summary": summarise(graded),
               "graded": graded}
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "variant_gold.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    control = (json.loads(args.compare.read_text(encoding="utf-8"))
               if args.compare else None)
    write_markdown(payload, ROOT / "reports" / "VARIANT_GOLD.md", control)
    print(json.dumps({k: v for k, v in payload["summary"].items()
                      if k not in ("by_stratum", "misses", "unwarranted",
                                   "identity_confusion")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

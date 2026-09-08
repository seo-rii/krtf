"""What would another corpus actually add? (corpus-selection evidence)

Three corpora were added in a row — `holdout3`, `web`, `law` — and each
reached **zero** entities the others did not. "Add more data" keeps sounding
like the answer, so this makes the question answerable before the download
rather than after: which registered entities are reached, how thinly, and by
which corpus.

Cheap on purpose. Silver occurrence counting only, no resolver, so it runs
over every cached corpus in a couple of minutes and can be re-run whenever a
new corpus is proposed.

Reads: entities never reached (excluding `DETECTION_ONLY`, which are
withheld by design and would otherwise read as gaps), entities reached
fewer than `--thin` times, and per-corpus exclusivity — how many entities
each corpus is the *only* source for.

Writes eval/out/corpus_coverage.json and reports/CORPUS_COVERAGE.md.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ktrf.glossary import load_glossary

from .metrics import provenance_line, run_manifest, wilson_interval
from .run_wild import DETECTION_ONLY, SILVER_MIN_LEN, silver_occurrences
from .wild_data import CORPORA, load_corpus

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thin", type=int, default=5,
                    help="occurrences at or below which an entity is thin")
    args = ap.parse_args()

    manifest = run_manifest(ROOT)
    g = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    aliases = sorted(
        {b.surface for b in g.alias_bindings
         if len(b.surface) >= SILVER_MIN_LEN and b.surface not in DETECTION_ONLY}
        | {e.canonical for e in g.entities
           if e.canonical not in DETECTION_ONLY})
    alias_to = {b.surface: b.entity_id for b in g.alias_bindings}
    alias_to |= {e.canonical: e.entity_id for e in g.entities}
    name_of = {e.entity_id: e.canonical for e in g.entities}
    # entities every one of whose silver surfaces is withheld: absent from
    # this census by construction, and reporting them as gaps would send
    # someone hunting for a corpus that cannot help.
    withheld = {e.entity_id for e in g.entities
                if e.entity_id not in {alias_to[a] for a in aliases}}

    per: dict[str, Counter] = {}
    sizes: dict[str, int] = {}
    for name in sorted(CORPORA):
        if not CORPORA[name][1].exists():
            print(f"  {name}: not cached, skipped")
            continue
        rows = load_corpus(name)
        hits: Counter = Counter()
        for r in rows:
            for _, _, a in silver_occurrences(r["text"], aliases):
                hits[alias_to.get(a, a)] += 1
        per[name] = hits
        sizes[name] = len(rows)
        print(f"  {name}: {len(rows):,} sentences, {sum(hits.values()):,} "
              f"occurrences, {len(hits)} entities")

    total: Counter = Counter()
    for h in per.values():
        total.update(h)
    all_ids = {e.entity_id for e in g.entities}
    measurable = all_ids - withheld
    exclusive = {name: sorted(e for e in h
                              if all(e not in o for k, o in per.items()
                                     if k != name))
                 for name, h in per.items()}

    payload = {
        "manifest": manifest,
        "entities_total": len(all_ids),
        "entities_withheld": sorted(withheld),
        "entities_measurable": len(measurable),
        "reached": len(set(total) & measurable),
        "unreached": sorted(measurable - set(total)),
        "thin": {e: total[e] for e in sorted(measurable)
                 if 0 < total[e] <= args.thin},
        "per_corpus": {k: {"sentences": sizes[k], "entities": len(v),
                           "occurrences": sum(v.values()),
                           "exclusive": exclusive[k]}
                       for k, v in per.items()},
        "thin_threshold": args.thin,
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "corpus_coverage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, name_of, ROOT / "reports" / "CORPUS_COVERAGE.md")
    print(json.dumps({k: v for k, v in payload.items()
                      if k in ("entities_measurable", "reached", "unreached")},
                     ensure_ascii=False, indent=2))
    print(f"wrote {ROOT / 'reports' / 'CORPUS_COVERAGE.md'}")


def write_markdown(payload: dict, name_of: dict, out_path: Path) -> None:
    per = payload["per_corpus"]
    reached = payload["reached"]
    measurable = payload["entities_measurable"]
    lo, hi = wilson_interval(reached, measurable)
    lines = [
        "# 코퍼스를 하나 더 넣으면 무엇이 늘어나는가",
        "",
        f"등록 entity {payload['entities_total']}개 중 silver 표면형이 모두"
        f" `DETECTION_ONLY`로 보류된 {len(payload['entities_withheld'])}개를"
        f" 빼면 측정 대상은 **{measurable}개**다. 캐시된 코퍼스"
        f" {len(per)}개가 그중 **{reached}개**에 도달한다"
        f" (Wilson 95% [{lo:.3f}, {hi:.3f}]).",
        "",
        "| 코퍼스 | 문장 | silver 발생 | entity | **단독 도달** |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, v in sorted(per.items()):
        lines.append(
            f"| `{name}` | {v['sentences']:,} | {v['occurrences']:,} "
            f"| {v['entities']} | **{len(v['exclusive'])}** |")
    lines += [
        "",
        "**단독 도달** = 그 코퍼스에만 나오는 entity 수. 이 열이 왜 중요한지:"
        " `holdout3`·`web`·`law`를 연달아 넣었고 셋 다 단독 도달이 0이었다."
        " 문장 수는 늘었지만 사전 커버리지는 늘지 않았다.",
        "",
        "## 도달하지 못한 entity",
        "",
    ]
    if payload["unreached"]:
        for e in payload["unreached"]:
            lines.append(f"- `{e}` {name_of.get(e, '')}")
    else:
        lines.append("없음 — 측정 대상 entity는 모두 최소 1회 등장한다.")
    lines += [
        "",
        f"## 희박한 entity ({payload['thin_threshold']}회 이하)",
        "",
        "여기가 실제 공백이다. 도달은 했으나 신뢰구간이 무의미할 만큼"
        " 적게 나온다. 일반 뉴스·웹을 더 넣어도 이 목록은 거의 움직이지"
        " 않는다 — 필요한 것은 해당 도메인의 텍스트다.",
        "",
    ]
    for e, n in sorted(payload["thin"].items(), key=lambda kv: kv[1]):
        lines.append(f"- {n}회 · `{e}` {name_of.get(e, '')}")
    lines += [
        "",
        "## 보류된 entity (측정 대상 아님)",
        "",
        "silver 표면형이 전부 `DETECTION_ONLY`인 경우다. 짧거나 일반어와"
        " 겹쳐 은silver 라벨로 쓰지 않기로 한 것이므로, 코퍼스를 아무리"
        " 늘려도 이 census에는 나타나지 않는다. 공백으로 읽으면 안 된다.",
        "",
    ]
    for e in payload["entities_withheld"]:
        lines.append(f"- `{e}` {name_of.get(e, '')}")
    lines += [
        "",
        provenance_line(ROOT, manifest=payload["manifest"]),
        "",
        "*generated by `python -m eval.run_corpus_coverage`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

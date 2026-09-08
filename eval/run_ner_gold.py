"""Human-annotated spans as a denominator the resolver did not choose (§48.6).

Every recall figure in this repo rests on *silver* labels — occurrences of
registered surfaces, found by the same string matching the resolver uses. A
mention nobody's rule found is missing from the denominator as well as the
numerator, so silver recall cannot see a false negative, and the hand-labelled
`variant_gold` is a stratified sample of resolver *output*, which cannot
either. The review that raised this asked for a gold built without reference
to system output.

KLUE-NER is exactly that and was sitting unused: `wild` draws on KLUE's
`ynat`, `nli` and `sts` and never touched `ner`, whose sentences carry
human span annotations typed `OG` (organisation), `PS` (person), `LC`
(location), `QT`, `DT`, `TI`.

Two things it can measure that nothing here could:

1. **Detection recall on marked organisations.** For every `OG` span whose
   text is a registered surface, did the resolver emit a mention covering
   it? Humans drew the span, so a miss is visible.

2. **Commits on spans humans typed as something else.** A RESOLVED mention
   overlapping a `PS`/`QT`/`DT`/`TI` span is a commit on text a person said
   is not an organisation. Precision has been structurally 1.0 because
   off-span commits were unlabeled rather than wrong; here they are labeled.

   `LC` is reported apart from the rest and is *not* counted as an error.
   `서울시`, `경기도`, `제주도` are a municipality and a government body at
   once, and the annotator's choice between `LC` and `OG` does not settle
   which reading a sentence intends. Folding that ambiguity into an error
   count would manufacture failures out of a genuine class.

Writes eval/out/ner_gold.json and reports/NER_GOLD.md.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import provenance_line, run_manifest, wilson_interval
from .run_wild import DETECTION_ONLY

ROOT = Path(__file__).resolve().parent.parent
API = "https://datasets-server.huggingface.co/rows"
DATASET = ("klue/klue", "ner")
LICENSE = "CC BY-SA 4.0 (KLUE benchmark)"
MARKUP = re.compile(r"<([^<>:]+):(DT|LC|OG|PS|QT|TI)>")
AMBIGUOUS_TYPES = ("LC",)
ERROR_TYPES = ("PS", "QT", "DT", "TI")


def parse_annotated(sentence: str) -> tuple[str, list[dict]]:
    """Strip `<surface:TYPE>` markup, returning clean text and spans.

    Offsets are codepoint offsets into the *clean* text, which is what the
    resolver reports against.
    """
    out: list[str] = []
    spans: list[dict] = []
    pos = 0
    cursor = 0
    for m in MARKUP.finditer(sentence):
        out.append(sentence[cursor:m.start()])
        pos += m.start() - cursor
        surface = m.group(1)
        spans.append({"surface": surface, "type": m.group(2),
                      "start": pos, "end": pos + len(surface)})
        out.append(surface)
        pos += len(surface)
        cursor = m.end()
    out.append(sentence[cursor:])
    return "".join(out), spans


def fetch(split: str, want: int) -> list[str]:
    rows: list[str] = []
    offset = 0
    while len(rows) < want:
        qs = urllib.parse.urlencode({"dataset": DATASET[0],
                                     "config": DATASET[1], "split": split,
                                     "offset": offset, "length": 100})
        req = urllib.request.Request(f"{API}?{qs}",
                                     headers={"User-Agent": "ktrf-eval/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            got = json.loads(r.read().decode("utf-8")).get("rows", [])
        if not got:
            break
        rows += [x["row"]["sentence"] for x in got]
        offset += 100
    return rows[:want]


def overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation")
    ap.add_argument("--sentences", type=int, default=3000)
    args = ap.parse_args()

    manifest = run_manifest(ROOT, split=args.split)
    g = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    snap = compile_snapshot(g, strict=False)
    registered = {b.surface for b in g.alias_bindings} | {
        e.canonical for e in g.entities}

    raw = fetch(args.split, args.sentences)
    print(f"fetched {len(raw)} annotated sentences")

    marked = 0                      # OG spans whose text is registered
    detected = 0                    # ... covered by some mention
    committed = 0                   # ... and RESOLVED
    missed: list[dict] = []
    on_other: dict[str, list] = {t: [] for t in ERROR_TYPES + AMBIGUOUS_TYPES}
    span_types: Counter = Counter()

    for sentence in raw:
        text, spans = parse_annotated(sentence)
        if not spans:
            continue
        span_types.update(s["type"] for s in spans)
        mentions = resolve(snap, text).get("mentions", [])
        mspans = []
        for m in mentions:
            cp = m["span"]["codepoint"]
            # the committed entity is under `resolved_entity`; a top-level
            # `entity_id` does not exist on a mention and read as None for
            # every row until this was checked against a real response
            mspans.append({"start": cp["start"], "end": cp["end"],
                           "surface": m.get("surface"),
                           "link": m.get("link_decision"),
                           "entity": (m.get("resolved_entity") or {}).get(
                               "entity_id")})

        for s in spans:
            if s["type"] == "OG" and s["surface"] in registered:
                marked += 1
                hit = next((x for x in mspans if overlaps(s, x)), None)
                if hit is None:
                    missed.append({"surface": s["surface"],
                                   "text": text[:110]})
                else:
                    detected += 1
                    if hit["link"] == "RESOLVED":
                        committed += 1
            elif s["type"] in on_other:
                for x in mspans:
                    if x["link"] == "RESOLVED" and overlaps(s, x):
                        on_other[s["type"]].append(
                            {"human": s["surface"], "human_type": s["type"],
                             "committed": x["surface"],
                             "entity": x["entity"],
                             # the project's own list of surfaces too
                             # ambiguous to use as silver labels. A commit on
                             # one is not a surprise about this corpus; it is
                             # the resolver committing what the eval already
                             # refuses to score.
                             "detection_only": x["surface"] in DETECTION_ONLY,
                             # Did the human call *this exact string* a
                             # place, or is the org name merely inside a
                             # wider locative phrase? `강원도` labelled LC on
                             # its own is the first; `대검찰청` inside
                             # `서울 서초동 대검찰청` is the second, and there
                             # the commit is right and the span is just
                             # wider. Collapsing the two would read a
                             # correct answer as an error.
                             "same_string": x["surface"] == s["surface"],
                             "text": text[:110]})

    payload = {
        "manifest": manifest, "license": LICENSE,
        "dataset": f"{DATASET[0]}:{DATASET[1]}:{args.split}",
        "sentences": len(raw), "span_types": dict(span_types),
        "marked_registered_og": marked, "detected": detected,
        "committed": committed,
        "missed": missed[:60],
        # examples are truncated for the payload; the breakdown is counted
        # over the WHOLE list first. Computing it from the stored sample made
        # the split add up to 40 beside a total of 74 — a truncation quietly
        # deciding a published number.
        "commits_on_other_types": {k: v[:40] for k, v in on_other.items()},
        "commits_on_other_counts": {k: len(v) for k, v in on_other.items()},
        "lc_breakdown": {
            "same_string": sum(1 for r in on_other["LC"] if r["same_string"]),
            "org_inside_place_phrase": sum(
                1 for r in on_other["LC"] if not r["same_string"]),
            "same_string_detection_only": sum(
                1 for r in on_other["LC"]
                if r["same_string"] and r["detection_only"]),
            "same_string_surfaces": dict(Counter(
                r["committed"] for r in on_other["LC"] if r["same_string"])),
        },
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ner_gold.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "NER_GOLD.md")
    print(json.dumps({k: payload[k] for k in
                      ("marked_registered_og", "detected", "committed",
                       "commits_on_other_counts")},
                     ensure_ascii=False, indent=2))
    print(f"wrote {ROOT / 'reports' / 'NER_GOLD.md'}")


def write_markdown(payload: dict, out_path: Path) -> None:
    marked = payload["marked_registered_og"]
    det, com = payload["detected"], payload["committed"]
    dlo, dhi = wilson_interval(det, marked)
    clo, chi = wilson_interval(com, marked)
    counts = payload["commits_on_other_counts"]
    errors = sum(counts.get(t, 0) for t in ERROR_TYPES)
    lines = [
        "# 사람이 표시한 span을 분모로 쓴 평가 (§48.6)",
        "",
        f"출처: `{payload['dataset']}` — {payload['license']}."
        f" 문장 {payload['sentences']:,}개.",
        "",
        "이 저장소의 recall은 전부 **silver**다: 등록 표면형의 출현을,"
        " resolver가 쓰는 것과 같은 문자열 매칭으로 찾는다. 그래서 아무"
        " 규칙도 찾지 못한 mention은 분자에서만이 아니라 **분모에서도**"
        " 빠진다 — silver recall은 미탐을 볼 수 없다. 손으로 라벨한"
        " `variant_gold`도 resolver *출력*의 층화 표본이라 마찬가지다."
        " KLUE-NER의 span은 사람이 시스템과 무관하게 그은 것이다.",
        "",
        "## 1. 사람이 조직으로 표시한 것을 찾는가",
        "",
        f"`OG`로 표시된 span 중 표면형이 등록된 것 **{marked}건**이"
        " 분모다.",
        "",
        "| 지표 | 값 | CI95 |",
        "|---|---:|---|",
        f"| 탐지 (mention 생성) | {det}/{marked} = {det / max(1, marked):.4f} "
        f"| [{dlo:.4f}, {dhi:.4f}] |",
        f"| 확정 (RESOLVED) | {com}/{marked} = {com / max(1, marked):.4f} "
        f"| [{clo:.4f}, {chi:.4f}] |",
        "",
    ]
    if payload["missed"]:
        lines += ["놓친 span (표본):", ""]
        for m in payload["missed"][:20]:
            lines.append(f"- `{m['surface']}` — {m['text']}")
        lines.append("")
    lines += [
        "## 2. 사람이 조직이 아니라고 한 곳에 확정하는가",
        "",
        "여기가 지금까지 잴 수 없던 것이다. off-span 확정은 *라벨이 없는*"
        " 것이지 틀린 것이 아니었으므로 precision이 구조적으로 1.0이었다."
        " 사람이 `PS`(인명)·`QT`·`DT`·`TI`로 표시한 span 위의 RESOLVED는"
        " 라벨된 오탐이다.",
        "",
        "| 사람 라벨 | 그 위의 RESOLVED |",
        "|---|---:|",
    ]
    for t in ERROR_TYPES:
        lines.append(f"| `{t}` | {counts.get(t, 0)} |")
    lcb = payload.get("lc_breakdown", {})
    lines += [
        f"| **합계 (오탐)** | **{errors}** |",
        f"| `LC` (모호, 오탐 아님) | {counts.get('LC', 0)} |",
        f"| — 사람이 그 문자열 자체를 장소라 함 | {lcb.get('same_string', 0)} |",
        f"| — 조직명이 더 넓은 장소구 안에 있음 "
        f"| {lcb.get('org_inside_place_phrase', 0)} |",
        f"| — 앞의 것 중 `DETECTION_ONLY` "
        f"| {lcb.get('same_string_detection_only', 0)} |",
        "",
        "`LC`는 오탐으로 세지 않는다. `서울시`·`경기도`·`제주도`는 지자체이자"
        " 행정기관이고, 주석자가 `LC`를 골랐다는 사실이 그 문장이 어느 쪽을"
        " 뜻하는지 정하지 못한다. 이 모호성을 오탐에 접으면 실재하는 분류"
        " 문제에서 실패를 만들어내는 것이 된다.",
        "",
        "`LC` 안에서도 두 갈래는 다르다. `서울 서초동 대검찰청`처럼 사람이"
        " **더 넓은 장소구**를 표시하고 그 안에 조직명이 들어 있는 경우, 확정은"
        " 옳고 span이 넓을 뿐이다. 반면 `강원도`처럼 **그 문자열 자체**를"
        " 장소로 표시한 경우는 다르다.",
        "",
        "그 문자열 자체가 장소로 표시된 행의 표면형 분포: "
        + ", ".join(f"`{k}` {v}" for k, v in sorted(
            lcb.get("same_string_surfaces", {}).items(),
            key=lambda kv: -kv[1])) + ".",
        "",
        "다만 그중 `DETECTION_ONLY` 행은 따로 센다. 그 목록은 **이 프로젝트가"
        " 스스로** \"짧거나 일반어와 겹쳐 silver 라벨로 쓸 수 없다\"고 판단한"
        " 표면형이다. silver 분모에서 빼는 것은 채점을 멈출 뿐 resolver가"
        " 확정하는 것을 막지 않는다 — `제주도, 울릉도, 서해5도 등 장거리"
        " 항로`에서 `제주도`가 ORG_JEJU로 0.92에 확정된다. 라벨을 거부하면서"
        " 확정은 허용하는 것이 의도된 설계인지는 이 표가 묻는 질문이다.",
        "",
    ]
    for t in ERROR_TYPES + AMBIGUOUS_TYPES:
        rows = payload["commits_on_other_types"].get(t) or []
        if not rows:
            continue
        lines += [f"### `{t}` span 위의 확정", ""]
        for r in rows[:14]:
            flag = " *(DETECTION_ONLY)*" if r.get("detection_only") else ""
            flag += "" if r.get("same_string") else " *(넓은 장소구 안)*"
            lines.append(f"- 사람: `{r['human']}` / 확정: `{r['committed']}`"
                         f" → `{r['entity']}`{flag} — {r['text']}")
        lines.append("")
    lines += [
        "## 한계",
        "",
        "- KLUE-NER은 모든 조직을 표시하지만 이 glossary는 170개만 등록한다."
        " 분모를 **등록된 표면형인 `OG` span**으로 좁힌 이유이며, 따라서"
        " 이것은 \"모든 조직을 찾는가\"가 아니라 \"등록한 것을 사람이 표시한"
        " 자리에서 찾는가\"다.",
        "- 주석 자체도 완벽하지 않고 단일 출처다. 불일치는 위 목록을 읽어"
        " 판단해야 한다.",
        "- 이 span들은 resolver 출력과 무관하지만 KLUE 뉴스 도메인에는"
        " 의존한다. 사내 문서 분포는 여전히 tenant golden set이 필요하다.",
        "",
        provenance_line(ROOT, manifest=payload["manifest"]),
        "",
        "*generated by `python -m eval.run_ner_gold`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

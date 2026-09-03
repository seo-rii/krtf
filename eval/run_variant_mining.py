"""How much of the glossary's backlog can be read off its own responses?

Usage: python -m eval.run_variant_mining [--sentences N] [--json PATH]
                                         [--compare PATH] [--render-only PATH]

VARIANTS_PLAN M4 asks for unregistered variants to be mined and routed
through an approval loop. This measures the first half: run
:class:`ktrf.mining.VariantMiner` over real text and report what it finds,
so the backlog is a ranked list with evidence rather than a manual reading
of the corpus.

Two numbers matter and they are not the same number:

- **suffix gaps** — endings the catalog does not classify, each seen behind
  several distinct entities. These feed the M3 taxonomy, which until now was
  extended by hand.
- **name gaps** — names the text keeps using that the glossary does not
  hold. These feed :mod:`ktrf.registry.proposals`.

The report also carries the *rejected* mass, because a miner that only shows
its hits is unfalsifiable: the slot histogram says how much of what the
resolver flagged was a singleton, and how much the two gates dropped.

Writes eval/out/variant_mining.json.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import time
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.mining import VariantMiner
from ktrf.morphology import SUFFIX_CLASSES
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import provenance_line
from .wild_data import corpus_fingerprint, load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260831


def mine(corpus: list[dict], limit: int | None = None) -> dict:
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    snap = compile_snapshot(glossary)
    miner = VariantMiner()
    t0 = time.perf_counter()

    rows = corpus[:limit] if limit else corpus
    for i, row in enumerate(rows):
        text = row["text"] if isinstance(row, dict) else row
        miner.observe(resolve(snap, text, mode="commit"), i, text)
    report = miner.report()

    # The denominator side: everything the miner saw and did not surface.
    # `_slots` is private, and reading it here is deliberate — the harness is
    # the one caller that must be able to say what was dropped.
    slots = miner._slots
    hist: collections.Counter = collections.Counter(
        min(s["n"], 10) for s in slots.values())
    by_residual: dict[str, set] = collections.defaultdict(set)
    for (entity, residual) in slots:
        by_residual[residual].add(entity)
    cross = {r for r, e in by_residual.items() if len(e) >= miner.min_entities}

    payload = report.to_dict()
    payload.update({
        "sentences": len(rows),
        "corpus": corpus_fingerprint(),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        "slot_frequency_histogram": {str(k): v for k, v in sorted(hist.items())},
        "distinct_residuals": len(by_residual),
        "cross_entity_residuals": len(cross),
        "cross_entity_already_catalogued": len(cross & set(SUFFIX_CLASSES)),
        "singleton_slots": hist.get(1, 0),
    })
    return payload


def write_markdown(t: dict, control: dict | None, out_path: Path) -> None:
    c = control
    lines = [
        "# 미등록 변형 채굴 — 카탈로그·사전 백로그",
        "",
        "resolver는 이미 `full_surface`로 **자기가 가지지 못한 이름이 여기 있다**고"
        " 말하고 있다. 이 리포트는 그 진술을 모아 순위를 매긴 것이며, 새로운 분석을"
        " 하지 않는다 — 공개 응답 필드만 읽는다.",
        "",
        "재현: `python -m eval.run_variant_mining` · 리포트만 다시 쓰려면"
        " `--render-only`.",
        "",
        f"표본: 실문장 **{t['sentences']:,}문장**, realorg glossary.",
        "",
        "## 0. 무엇을 보고 무엇을 버렸나",
        "",
        "| 단계 | 건수 |",
        "|---|---:|",
        f"| mention | {t['observed_mentions']:,} |",
        f"| core보다 넓은 표면형 | {t['wider_surfaces']:,} |",
        f"| 그중 등록된 `COMPOSES_TO`가 이름을 준 것 | {t['already_named']:,} |",
        f"| 서로 다른 (entity, 잔여부) 자리 | {t['distinct_slots']:,} |",
        f"| 그중 **1회성** | {t['singleton_slots']:,} |",
        f"| 서로 다른 잔여부 | {t['distinct_residuals']:,} |",
        f"| 그중 여러 entity에 붙는 것 | {t['cross_entity_residuals']:,} |",
        f"| 그중 이미 카탈로그에 있는 것 | {t['cross_entity_already_catalogued']:,} |",
        "",
        "**버린 쪽이 리포트의 절반이다.** 채굴기가 맞힌 것만 보이면 반증할 수 없다.",
        "",
        "자리별 빈도 분포(1회성이 대부분이라는 것이 이 백로그의 성질이다):",
        "",
        "| 관측 횟수 | 자리 수 |",
        "|---|---:|",
    ]
    for k, v in t["slot_frequency_histogram"].items():
        lines.append(f"| {'10+' if k == '10' else k} | {v} |")

    lines += [
        "",
        "## 1. 종결어 공백 — 카탈로그가 읽지 못하는 끝",
        "",
        "**여러 entity 뒤에 반복해서 나타나는 잔여부**다. 우연이라면 서로 무관한"
        " 이름들에서 같은 끝이 반복되어야 하므로, entity 수가 곧 증거다. M3까지"
        " 손으로 하던 taxonomy 작업이 여기서는 측정값이다.",
        "",
        "> §5는 `wild tail 목록을 검토 없이 전역 SUFFIXES에 추가`하는 것을 금지한다."
        " 이 표는 **검토 대상 목록**이지 패치가 아니다. class를 고르는 것은 사람의"
        " 일이고, 잘못된 class는 대칭이 아니다 — `NAME_PART`/`REFERENTIAL`은 전체"
        " 표면형의 확정을 **허용**한다.",
        "",
        f"- 발견: **{len(t['suffix_gaps'])}건**",
        "",
        "| 잔여부 | entity 수 | 관측 | 문서 | tail 파서가 읽은 관계 | 예시 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for g in t["suffix_gaps"][:25]:
        rel = ", ".join(f"`{k}` {n}" for k, n in g["relations"][:3])
        ex = (g["examples"][0][:34] + "…") if g["examples"] else "—"
        lines.append(f"| `{g['residual']}` | {g['entity_count']} |"
                     f" {g['occurrences']} | {g['documents']} | {rel} | {ex} |")

    lines += [
        "",
        "## 2. 이름 공백 — 사전이 가지지 못한 이름",
        "",
        "**한 entity 뒤에서만 반복되는 잔여부**다. 이쪽이 M4가 원래 노린 것이고,"
        " 둘 중 **약한** 증거다: 약어 채널은 우연히 겹치는 접두를 진짜만큼 안정적으로"
        " 반복해서 맞힌다(`해수` + `욕장`이 9개 문서에서 버텼다). 흔한 것은 이름이"
        " 아니라 **단어**이기 때문이다.",
        "",
        "그래서 이름 공백은 **exact 채널이 찾은 core 뒤에서만** 채굴한다 — 등록된"
        " 표면형이지 부분수열이 아니라는 뜻이고, `카카오`+`톡`과 `해수`+`욕장`을"
        " 가르는 것이 정확히 그 차이다.",
        "",
        f"- 발견: **{len(t['name_gaps'])}건**",
        "",
        "| 표면형 | core entity | 잔여부 | 관계 | 판정 | 관측 | 문서 |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for g in t["name_gaps"][:25]:
        lines.append(f"| `{g['surface']}` | `{g['entity_id']}` |"
                     f" `{g['residual']}` | {g['relation']} | {g['identity']} |"
                     f" {g['occurrences']} | {g['documents']} |")

    _cc = (c or {}).get("corpus") or {}
    _tc = t.get("corpus") or {}
    # only when both arms recorded one: a control payload from before
    # the fingerprint existed is unknown, not different
    if _cc.get("sha256") and _tc.get("sha256") and \
            _cc["sha256"] != _tc["sha256"]:
        lines += [
            "",
            "> **두 팔이 서로 다른 코퍼스를 읽었다.** 아래 비교는 변경의"
            " 효과가 아니라 데이터 차이를 포함한다 — 같은 캐시로 다시"
            " 재야 한다.",
        ]
    if c:
        lines += [
            "",
            "## 3. 대조군 대비",
            "",
            "| 지표 | 대조군 | 현재 |",
            "|---|---:|---:|",
            f"| 종결어 공백 | {len(c['suffix_gaps'])} | {len(t['suffix_gaps'])} |",
            f"| 이름 공백 | {len(c['name_gaps'])} | {len(t['name_gaps'])} |",
            f"| 넓은 표면형 | {c['wider_surfaces']:,} | {t['wider_surfaces']:,} |",
            f"| 등록 관계가 답한 것 | {c['already_named']:,} |"
            f" {t['already_named']:,} |",
            "",
            "백로그가 **줄어드는 것**이 진전이다: 카탈로그나 사전이 넓어지면 같은"
            " 코퍼스에서 채굴되는 공백이 줄어야 한다.",
        ]

    lines += [
        "",
        "## 이 리포트가 말하지 않는 것",
        "",
        "- **어떤 class인지, 무엇을 뜻하는지.** 채굴기는 이름이 *있다*는 것만 말한다."
        " canonical과 class는 사람이나 LLM이 제안하고 `ktrf.registry.proposals`의"
        " 검증·승인을 거친다. 모델 추론만으로 영구 사전이 바뀌지 않는다.",
        "- **core 매칭이 옳았는지.** 이름 공백의 core는 확정된 것도 있고 후보에"
        " 그친 것도 있다. 확정 정확도는 `WILD_CORPUS.md`가 잰다.",
        "",
        provenance_line(ROOT, f"표본 {t['sentences']:,}문장",
                        corpus=t.get("corpus")),
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", type=int, default=20000)
    ap.add_argument("--json", type=str, default=None)
    ap.add_argument("--compare", type=str, default=None)
    ap.add_argument("--render-only", type=str, default=None)
    ap.add_argument("--corpus", type=str, default="wild",
                    help="wild (what the reports measure) or a held-out "
                         "corpus the miner's gates were not chosen against")
    args = ap.parse_args()

    out_md = ROOT / "reports" / (f"VARIANT_MINING_{args.corpus.upper()}.md" if args.corpus != "wild"
                                 else "VARIANT_MINING.md")
    control = (json.loads(Path(args.compare).read_text(encoding="utf-8"))
               if args.compare else None)

    if args.render_only:
        payload = json.loads(Path(args.render_only).read_text(encoding="utf-8"))
        write_markdown(payload, control, out_md)
        print(f"rendered {out_md} from {args.render_only}")
        return

    corpus = load_corpus(args.corpus)
    sample = random.Random(SEED).sample(corpus,
                                        min(args.sentences, len(corpus)))
    print(f"sample: {len(sample)} of {len(corpus)} sentences")
    payload = mine(sample)

    out_json = ROOT / "eval" / "out" / (
        f"variant_mining_{args.corpus}.json" if args.corpus != "wild"
        else "variant_mining.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    out_json.write_text(body, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(body, encoding="utf-8")
    write_markdown(payload, control, out_md)
    print(f"suffix gaps: {len(payload['suffix_gaps'])}, "
          f"name gaps: {len(payload['name_gaps'])}")
    print(f"wrote {out_json} and {out_md}")


if __name__ == "__main__":
    main()

"""How often does a mention's full surface stop meaning what its core means?

Usage: python -m eval.run_composition_audit [--sentences N] [--json PATH]

VARIANTS_PLAN §2 says a related derivative (`한전노조`, `금감원장`) may produce
a core candidate but must never let the parent entity take the whole surface.
Until M2 the resolver had no way to say that in a response, and no report
said how often it mattered. This measures the phenomenon on real text:

- how many mentions carry a surface wider than their core,
- what the tails are (`ROLE`, `ORG_UNIT`, `DERIVED_ORG`, …),
- how many commits the guard now withholds, and for which reason,
- how many derivatives a registered `COMPOSES_TO` relation could name — the
  backlog signal for variant mining (M4).

The script reads only public response fields and treats every M2 key as
optional, so it runs unchanged against a pre-M2 checkout: absent keys mean
"this build could not draw the distinction", which is the honest control.
Pair the two arms with ``--json`` and compare, rather than quoting one arm.

Writes eval/out/composition_audit.json.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import time
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.morphology import PARTICLES, ParticleFST
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import provenance_line
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260831


def audit(corpus: list[dict], limit: int | None = None) -> dict:
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    snap = compile_snapshot(glossary)

    # The *whole* catalog, on purpose. A count of surfaces ending in a
    # particle the resolver has agreed to split is 0 by construction and
    # measures nothing; this asks the question the consumer asks — is there
    # 조사 inside the name I was told to highlight — and the residue after a
    # split rule lands is exactly what that rule deliberately left behind.
    #
    # 받침 agreement is checked because a plain suffix test says `카카오페이`
    # and `롯데제과` end in 조사: 이 needs a 받침 before it and 페 has none,
    # so 이 there is not a 조사 at all and no reading was ever available.
    # The rule is the FST's own, not the split list's, so the number stays
    # independent of the thing it is measuring.
    fst = ParticleFST()
    particle_endings = sorted(PARTICLES, key=len, reverse=True)

    def _ends_in_particle(name: str) -> str | None:
        for p in particle_endings:
            if not name.endswith(p) or len(name) <= len(p):
                continue
            prev = name[-len(p) - 1]
            if any(x.grammatical for x in fst.parse_full(p, prev)):
                return p
        return None

    mentions = 0
    wider_surface = 0
    name_ends_in_particle = 0
    particle_inside_name: collections.Counter = collections.Counter()
    commits = 0
    tail_classes: collections.Counter = collections.Counter()
    identities: collections.Counter = collections.Counter()
    relations: collections.Counter = collections.Counter()
    blocked: collections.Counter = collections.Counter()
    composes_to = 0
    examples: dict[str, list[str]] = collections.defaultdict(list)
    t0 = time.perf_counter()

    for row in corpus[:limit] if limit else corpus:
        text = row["text"] if isinstance(row, dict) else row
        for m in resolve(snap, text, mode="commit")["mentions"]:
            mentions += 1
            if m.get("link_decision") == "RESOLVED":
                commits += 1
            for member in m.get("prediction_set", {}).get("members", []):
                if member.get("commit_blocked"):
                    blocked[member["commit_blocked"]] += 1
            fs = m.get("full_surface")
            if not fs:
                continue
            wider_surface += 1
            hit = _ends_in_particle(fs["surface"])
            if hit:
                name_ends_in_particle += 1
                particle_inside_name[hit] += 1
            identities[fs["identity"]] += 1
            tail_classes[fs.get("tail_class") or "NONE"] += 1
            relations[m["core_link"]["relation"]] += 1
            if "composes_to" in fs:
                composes_to += 1
            # keyed by relation, not tail class: a NAME_PART head behind a
            # modifier still yields NAMED_VARIANT, and the pair read alone is
            # confusing (`대한민국` is tail_class NAME_PART but not IDENTITY)
            key = m["core_link"]["relation"]
            entry = f'{fs["surface"]} (core {m["core_link"]["surface"]})'
            if len(examples[key]) < 6 and entry not in examples[key]:
                examples[key].append(entry)

    return {
        "sentences": len(corpus[:limit] if limit else corpus),
        "mentions": mentions,
        "resolved_commits": commits,
        # a build with no M2 keys reports 0 here — that is the control, not a
        # measurement that the phenomenon is absent
        "surface_wider_than_core": wider_surface,
        "share_of_mentions": (round(wider_surface / mentions, 4)
                              if mentions else None),
        # §16: a 조사 is grammar, so a `full_surface` ending in one is
        # reporting a name that does not exist. Not a contract — some of
        # these endings are also ordinary name-final syllables and stay on
        # purpose (`공항철도`, `카카오게임`) — but the number should fall
        # when the tail parser learns where a name stops.
        "name_ends_in_particle": name_ends_in_particle,
        "name_ends_in_particle_by_ending":
            dict(particle_inside_name.most_common(12)),
        "identity": dict(identities.most_common()),
        "tail_class": dict(tail_classes.most_common()),
        "core_relation": dict(relations.most_common()),
        "commit_blocked": dict(blocked.most_common()),
        "named_by_registered_relation": composes_to,
        "examples": {k: v for k, v in sorted(examples.items())},
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }


def write_markdown(treatment: dict, control: dict | None,
                   out_path: Path) -> None:
    """Render the audit, paired against a control arm when one is supplied."""
    t = treatment
    lines = [
        "# 표면형 합성 감사 — core_link / full_surface",
        "",
        "`한전노조`의 `한전`은 한국전력공사를 가리키지만 `한전노조` 전체는"
        " 다른 조직이고, `금감원장`은 사람이다. VARIANTS_PLAN §2 불변조건 ②는"
        " 부모 entity가 전체 표면형을 가져가는 것을 금지한다. 이 리포트는 그"
        " 현상이 실제 텍스트에서 **얼마나 자주** 일어나는지를 센다.",
        "",
        "재현: `python -m eval.run_composition_audit`"
        " (대조군은 다른 체크아웃에서 같은 스크립트를 돌려 `--compare`로"
        " 넘긴다 — 두 arm은 같은 seed·같은 표본이다). 리포트만 다시 쓰려면"
        " `--render-only`.",
        "",
        f"표본: KLUE 등 실문장 **{t['sentences']:,}문장**, realorg glossary.",
        "",
        "## 무엇이 얼마나 바뀌었나",
        "",
    ]
    if control:
        lines += [
            "| 지표 | 대조군 | 현재 |",
            "|---|---:|---:|",
            f"| mention 수 | {control['mentions']:,} | {t['mentions']:,} |",
            f"| RESOLVED 확정 | {control['resolved_commits']:,} "
            f"| {t['resolved_commits']:,} |",
            f"| core보다 넓은 표면형 | {control['surface_wider_than_core']:,} "
            f"| {t['surface_wider_than_core']:,} |",
            f"| 이름 안에 조사가 들어간 것 | "
            f"{control.get('name_ends_in_particle', 0):,} "
            f"| {t['name_ends_in_particle']:,} |",
            f"| commit 보류된 후보 슬롯 | "
            f"{sum(control['commit_blocked'].values()):,} "
            f"| {sum(t['commit_blocked'].values()):,} |",
            "",
            "대조군에서 `core보다 넓은 표면형`이 0이라면 그 현상이 없어서가"
            " 아니라 **그 빌드가 구분을 표현할 수 없어서**다 — M2 이전"
            " 체크아웃이 그렇다. 두 arm 모두 0이 아니면 그 열은 실제 변화다.",
            "",
        ]
    else:
        lines += [
            f"- mention {t['mentions']:,}건 중 **{t['surface_wider_than_core']:,}건"
            f"**({(t['share_of_mentions'] or 0) * 100:.1f}%)이 core보다 넓은"
            " 표면형을 가진다.",
            f"- RESOLVED 확정 {t['resolved_commits']:,}건.",
            f"- 그중 이름이 조사로 끝나는 것 **{t['name_ends_in_particle']:,}건**"
            " — §16이 조사를 이름 밖으로 두기로 했으므로, 존재하지 않는 이름을"
            " 가리키는 span이다. 남는 것은 이름의 끝음절이기도 한 조사들이다: "
            + (", ".join(f"`{k}` {n}" for k, n
                         in t["name_ends_in_particle_by_ending"].items())
               or "없음"),
            "",
        ]

    lines += ["## 전체 표면형이 core와 같은 것을 가리키는가", "",
              "| 판정 | 건수 |", "|---|---:|"]
    for k, v in t["identity"].items():
        lines.append(f"| `{k}` | {v:,} |")
    lines += ["", "## core → 전체 표면형 관계", "",
              "| 관계 | 건수 |", "|---|---:|"]
    for k, v in t["core_relation"].items():
        lines.append(f"| `{k}` | {v:,} |")
    lines += ["", "## commit 보류 사유", "",
              "prediction set **멤버** 단위 집계다 — mention 수가 아니고,"
              " 한 mention이 여러 후보를 담으면 여러 번 세어진다."
              " 확정(RESOLVED) 수와는 위 표에서 따로 본다.",
              "", "| 사유 | 건수 |", "|---|---:|"]
    for k, v in t["commit_blocked"].items():
        lines.append(f"| `{k}` | {v:,} |")

    lines += ["", "## 실제 사례", ""]
    for rel, ex in t["examples"].items():
        lines.append(f"- **{rel}**: " + ", ".join(f"`{e}`" for e in ex))

    lines += [
        "",
        "## 읽는 법과 한계",
        "",
        "- `NAMED_VARIANT`가 많은 것은 카탈로그 suffix 앞에 수식어가 붙은"
        " 경우(`서울본부`)다. head가 `NAME_PART`여도 앞에 수식어가 있으면"
        " 전체는 다른 이름이므로 DISTINCT로 간다.",
        "- 이 표본의 mention에는 Level B 채널이 만든 **잘못된 분해**도 섞여"
        " 있다(예: `금융시장`을 core + `장`으로 읽는 경우). 그런 후보는"
        " commit이 보류되므로 precision에는 영향이 없지만, 응답에 관계"
        " 필드가 붙는다는 뜻이다 — 숨기지 않고 여기 노출한다.",
        "- **카탈로그 자체의 한계가 예시에 보인다**: `제주도지사`가 `PART_OF`로"
        " 분류되는데, 여기 `지사`는 支社(지점)가 아니라 知事(도지사, 사람)다."
        " suffix 하나가 두 의미를 갖는 경우는 표면형만으로 가를 수 없고,"
        " 카탈로그 확장(M3)에서 다룬다. 두 해석 모두 DISTINCT라 commit"
        " 안전성에는 차이가 없고, 틀리는 것은 relation 라벨이다.",
        "- `named_by_registered_relation`이 "
        f"{t['named_by_registered_relation']}건인 것은 realorg glossary에"
        " `COMPOSES_TO` 선언이 없기 때문이다. 이 수는 **미등록 파생의 규모"
        " 신호**이며 M4 variant mining의 우선순위 입력이다.",
        "- 이 리포트는 빈도를 세며, 각 판정이 옳은지는 채점하지 않는다."
        " 정오 판정에는 human-gold seed(M0 잔여 항목)가 필요하다.",
        "",
        provenance_line(ROOT, f"표본 {t['sentences']:,}문장"),
        "",
        "*generated by `python -m eval.run_composition_audit`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", type=int, default=20000)
    ap.add_argument("--json", type=str, default=None,
                    help="output path (default eval/out/composition_audit.json)")
    ap.add_argument("--compare", type=str, default=None,
                    help="control-arm JSON from another checkout")
    ap.add_argument("--markdown", type=str, default=None,
                    help="also write reports/COMPOSITION_AUDIT.md")
    ap.add_argument("--render-only", type=str, default=None,
                    help="rewrite the report from an existing payload without "
                         "re-measuring. Re-stamping a report after a commit, "
                         "or fixing a layout, should not cost a 10k-sentence "
                         "run.")
    args = ap.parse_args()

    if args.render_only:
        payload = json.loads(Path(args.render_only).read_text(encoding="utf-8"))
        control = (json.loads(Path(args.compare).read_text(encoding="utf-8"))
                   if args.compare else None)
        md = (Path(args.markdown) if args.markdown
              else ROOT / "reports" / "COMPOSITION_AUDIT.md")
        write_markdown(payload, control, md)
        print(f"rendered {md} from {args.render_only}")
        return

    corpus = load_corpus()
    sample = random.Random(SEED).sample(corpus, min(args.sentences, len(corpus)))
    print(f"sample: {len(sample)} of {len(corpus)} sentences")

    payload = audit(sample)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    out = (Path(args.json) if args.json
           else ROOT / "eval" / "out" / "composition_audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": SEED, **payload}, ensure_ascii=False,
                              indent=2), encoding="utf-8")
    print(f"\nwrote {out}")

    if args.markdown or args.compare:
        control = None
        if args.compare:
            control = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        md = Path(args.markdown) if args.markdown else \
            ROOT / "reports" / "COMPOSITION_AUDIT.md"
        write_markdown(payload, control, md)
        print(f"wrote {md}")


if __name__ == "__main__":
    main()

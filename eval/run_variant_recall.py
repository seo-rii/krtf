"""Variant-family recall — the headline the evaluation axis is built around.

Usage: python -m eval.run_variant_recall [--per-cell N] [--sentences N]
                                         [--json PATH] [--compare PATH]

Every other suite in ``eval/`` counts occurrences. This one counts
**registered terms**: for each entity in the glossary, deform its surfaces
one typed formation at a time, drop each deformation into a real sentence,
and ask whether the term came back. The headline is the macro average over
families, so a ministry named in a thousand headlines and a term named once
weigh the same — which is how a glossary owner weighs them.

Four things are reported apart, because merging them is how the older
numbers misled:

1. **Candidate layer** (``|candidate``) — was the gold entity in the
   prediction set at the exact core span? This is what retrieval and
   generation are responsible for.
2. **Commit layer** (``|commit``) — did the resolver actually say so?
   Withholding is not a candidate failure, and §2 makes withholding
   *correct* for some formations, so the two layers can never be one number.
3. **Span** — a mention at the wrong boundary (`대한민국` read as core
   `대한`) is not a recall success even when the entity is right. Reported
   as ``core_span_wrong``, the error class the M2 audit surfaced.
4. **Contract violations** — a commit that takes the whole of `한전노조`
   breaks invariant ②. This must be 0; a rate is not an acceptable answer.

Confusion suites replace the fake glossary as the negative control. See
``eval/confusion.py`` for why an invented stranger is the easy question and
a one-중성 sibling is the real one.

Writes eval/out/variant_recall.json and reports/VARIANT_RECALL.md.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import time
from pathlib import Path

import yaml

from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .confusion import build_confusion_glossary, decoy_stats
from .metrics import provenance_line, wilson_interval
from .run_wild import DETECTION_ONLY, SILVER_MIN_LEN, silver_occurrences
from .variants import BY_KEY, FORBIDDEN, FORMATIONS, SAME, build_cases
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "examples" / "realorg_glossary.yaml"
SEED = 20260901


def _cp(m: dict, key: str = "span") -> tuple[int, int]:
    cp = m[key]["codepoint"]
    return cp["start"], cp["end"]


def _entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def score_case(case, mentions: list[dict]) -> dict:
    """Grade one deformation. Layers stay separate all the way down."""
    gold, cs = case.entity_id, case.core_span
    at_core = next((m for m in mentions if _cp(m) == cs), None)
    overlapping = [m for m in mentions
                   if _cp(m)[0] < cs[1] and cs[0] < _cp(m)[1]]
    misaligned = [m for m in overlapping if _cp(m) != cs]

    committed = [m for m in mentions if m.get("link_decision") == "RESOLVED"]
    commit_at_core = next((m for m in committed if _cp(m) == cs), None)

    # invariant ②: for a derivative, no commit may reach past the core, and
    # a commit at the core must not claim the wider surface is the same
    # entity. Both are read off the response rather than off the guard's own
    # reasons — a guard that stopped running would still report clean
    # reasons, and this notices that.
    violation = None
    if BY_KEY[case.formation].commit == FORBIDDEN:
        for m in committed:
            ms, me = _cp(m)
            if ms <= cs[0] and me > cs[1] and gold in _entities(m):
                violation = "parent_took_full_surface"
                break
        if violation is None and commit_at_core is not None:
            fs = commit_at_core.get("full_surface")
            if fs and fs.get("identity") == "SAME_AS_CORE":
                violation = "full_surface_declared_same"

    fs = at_core.get("full_surface") if at_core else None
    return {
        "entity_id": gold,
        "formation": case.formation,
        "core_span_exact": at_core is not None,
        "core_span_wrong": at_core is None and bool(misaligned),
        "detected": bool(overlapping),
        # |candidate — strict: the exact core span, not any overlap
        "gold_in_set": at_core is not None and gold in _entities(at_core),
        "gold_in_set_any_span": any(gold in _entities(m) for m in overlapping),
        # |commit
        "committed": commit_at_core is not None,
        "commit_gold": (commit_at_core is not None
                        and commit_at_core["resolved_entity"]["entity_id"] == gold),
        "commit_wrong": (commit_at_core is not None
                         and commit_at_core["resolved_entity"]["entity_id"] != gold),
        "violation": violation,
        # the label, which is what a catalog change is allowed to move
        "relation": (at_core.get("core_link", {}).get("relation")
                     if at_core else None),
        "identity": fs.get("identity") if fs else None,
        "surface_wider": fs is not None,
        # Where does the response say the *name* ends? Only scored where the
        # generator knows the answer (a formation that appends a 조사). The
        # two layers stay apart here too: this is not about whether the core
        # was found or committed, only about the extent the response asks a
        # consumer to highlight or substitute.
        "name_span_exact": (None if not case.name
                            else bool(fs) and fs.get("surface") == case.name),
    }


def _macro(records: list[dict], field: str) -> float | None:
    """Mean over families of the family's own rate — one term, one vote."""
    per: dict[str, list[int]] = {}
    for r in records:
        per.setdefault(r["entity_id"], []).append(int(bool(r[field])))
    if not per:
        return None
    return statistics.fmean(statistics.fmean(v) for v in per.values())


def _micro(records: list[dict], field: str) -> float | None:
    if not records:
        return None
    return sum(int(bool(r[field])) for r in records) / len(records)


def _slice(records: list[dict]) -> dict:
    n = len(records)
    hits = sum(int(r["gold_in_set"]) for r in records)
    lo, hi = wilson_interval(hits, n)
    return {
        "cases": n,
        "families": len({r["entity_id"] for r in records}),
        "candidate_macro": round(_macro(records, "gold_in_set"), 4) if n else None,
        "candidate_micro": round(_micro(records, "gold_in_set"), 4) if n else None,
        "candidate_ci95": [round(lo, 4), round(hi, 4)],
        "commit_macro": round(_macro(records, "commit_gold"), 4) if n else None,
        "core_span_exact": round(_micro(records, "core_span_exact"), 4) if n else None,
        "core_span_wrong": round(_micro(records, "core_span_wrong"), 4) if n else None,
        "commit_wrong": sum(int(r["commit_wrong"]) for r in records),
        "violations": sum(int(bool(r["violation"])) for r in records),
        # a wider surface the resolver could *name*: UNKNOWN means the
        # catalog had nothing to say, which is the M3 backlog signal
        "relation_named": sum(1 for r in records
                              if r["surface_wider"] and r["identity"]
                              and r["identity"] != "UNKNOWN"),
        "identity_unknown": sum(1 for r in records if r["identity"] == "UNKNOWN"),
        "name_span_scored": sum(1 for r in records
                                if r["name_span_exact"] is not None),
        "name_span_exact": round(
            _micro([r for r in records if r["name_span_exact"] is not None],
                   "name_span_exact"), 4)
        if any(r["name_span_exact"] is not None for r in records) else None,
    }


def run_variant_suite(corpus, per_cell: int, seed: int,
                      encoder=None, policy=None) -> dict:
    glossary = load_glossary(str(GLOSSARY))
    snap = compile_snapshot(glossary, encoder=encoder, policy=policy,
                            run_conformance=encoder is None)
    cases = build_cases(corpus, glossary, per_cell=per_cell, seed=seed)
    records: list[dict] = []
    examples: dict[str, list[dict]] = collections.defaultdict(list)
    t0 = time.perf_counter()
    for case in cases:
        resp = resolve(snap, case.text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        rec = score_case(case, resp["mentions"])
        records.append(rec)
        key = case.formation
        if not rec["gold_in_set"] and len(examples[key]) < 6:
            examples[key].append({"token": case.token, "core": case.core,
                                  "entity_id": case.entity_id,
                                  "core_span_wrong": rec["core_span_wrong"]})

    by_formation = {f.key: _slice([r for r in records if r["formation"] == f.key])
                    for f in FORMATIONS}
    # overall macro weights formations equally inside a family, then
    # families equally: the alternative lets whichever formation generated
    # the most cases decide the headline
    per_family: dict[str, dict[str, list[int]]] = {}
    for r in records:
        per_family.setdefault(r["entity_id"], {}).setdefault(
            r["formation"], []).append(int(r["gold_in_set"]))
    fam_rate = {e: statistics.fmean(statistics.fmean(v) for v in f.values())
                for e, f in per_family.items()}
    worst = sorted(fam_rate.items(), key=lambda kv: kv[1])[:12]

    same_keys = {f.key for f in FORMATIONS if f.commit == SAME}
    forbidden = [r for r in records if BY_KEY[r["formation"]].commit == FORBIDDEN]
    same = [r for r in records if r["formation"] in same_keys]
    # Level A formations are reached by deterministic normalisation and
    # segmentation; Level B ones only by a fuzzy channel, which the guard
    # then judges. Averaging the two hides the only slice that can move:
    # Level A is contractually near 1.0 and drags the headline up with it.
    tier = {t: [r for r in records if BY_KEY[r["formation"]].tier == t]
            for t in ("A", "B")}
    return {
        "cases": len(records),
        "families": len(per_family),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        "headline": {
            "variant_family_macro_recall": round(
                statistics.fmean(fam_rate.values()), 4) if fam_rate else None,
            "conditioning": "|candidate",
            "level_a_macro": round(_macro(tier["A"], "gold_in_set"), 4)
            if tier["A"] else None,
            "level_b_macro": round(_macro(tier["B"], "gold_in_set"), 4)
            if tier["B"] else None,
            "commit_macro_on_same": round(_macro(same, "commit_gold"), 4)
            if same else None,
            "core_span_wrong_rate": round(_micro(records, "core_span_wrong"), 4),
            # |mention, and only over the cases whose generator appended a
            # 조사: does `full_surface` stop where the name stops?
            "name_span_exact_rate": round(
                _micro([r for r in records if r["name_span_exact"] is not None],
                       "name_span_exact"), 4)
            if any(r["name_span_exact"] is not None for r in records) else None,
            "contract_violations": sum(int(bool(r["violation"])) for r in records),
            "wrong_entity_commits": sum(int(r["commit_wrong"]) for r in records),
        },
        "by_formation": by_formation,
        "forbidden_labels": {
            "cases": len(forbidden),
            "surface_wider_reported": sum(int(r["surface_wider"]) for r in forbidden),
            "identity_unknown": sum(1 for r in forbidden
                                    if r["identity"] == "UNKNOWN"),
            "relation": dict(collections.Counter(
                r["relation"] for r in forbidden if r["relation"]).most_common()),
        },
        "worst_families": [[e, round(v, 4)] for e, v in worst],
        "miss_examples": {k: v for k, v in sorted(examples.items())},
    }


def run_confusion_suite(corpus, seed: int, limit: int | None = None) -> dict:
    """Real text, real glossary plus decoys anchored to the real entities."""
    base = yaml.safe_load(GLOSSARY.read_text(encoding="utf-8"))
    texts = [r["text"] for r in corpus]
    g_dict, meta = build_confusion_glossary(base, texts, seed=seed)
    snap = compile_snapshot(load_glossary(g_dict), run_conformance=False)
    plain = compile_snapshot(load_glossary(str(GLOSSARY)))

    real_glossary = load_glossary(str(GLOSSARY))
    alias_to_entity = {b.surface: b.entity_id
                       for b in real_glossary.alias_bindings}
    silver_aliases = [s for s in alias_to_entity
                      if len(s) >= SILVER_MIN_LEN and s not in DETECTION_ONLY]

    rows = corpus[:limit] if limit else corpus
    decoy_commits = decoy_candidates = 0
    decoy_examples: list[dict] = []
    silver_total = silver_in_set = silver_commit = 0
    base_commit = 0
    collision_mentions = collision_committed = collision_both_in_set = 0
    collision_examples: list[dict] = []

    for row in rows:
        text = row["text"]
        occs = silver_occurrences(text, silver_aliases)
        collides = [a for a in meta.collisions if a in text]
        if not occs and not collides:
            continue
        resp = resolve(snap, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        mentions = resp["mentions"]
        spans = {_cp(m): m for m in mentions}

        for m in mentions:
            if _entities(m) & meta.decoy_entities:
                decoy_candidates += 1
            if (m.get("link_decision") == "RESOLVED"
                    and m["resolved_entity"]["entity_id"] in meta.decoy_entities):
                decoy_commits += 1
                if len(decoy_examples) < 10:
                    decoy_examples.append(
                        {"text": text, "surface": m["surface"],
                         "decoy": m["resolved_entity"]["entity_id"]})

        # paired: the same silver spans, with and without the decoys present
        base_resp = resolve(plain, text, mode="commit",
                            options={"return_all_mentions": True,
                                     "max_prediction_set": 50})
        base_spans = {_cp(m): m for m in base_resp["mentions"]}
        for s, e, alias in occs:
            gold = alias_to_entity[alias]
            silver_total += 1
            m = spans.get((s, e))
            if m is not None and gold in _entities(m):
                silver_in_set += 1
            if (m is not None and m.get("link_decision") == "RESOLVED"
                    and m["resolved_entity"]["entity_id"] == gold):
                silver_commit += 1
            b = base_spans.get((s, e))
            if (b is not None and b.get("link_decision") == "RESOLVED"
                    and b["resolved_entity"]["entity_id"] == gold):
                base_commit += 1

        for ab in collides:
            # every occurrence, not the first: a headline that names the
            # colliding abbreviation twice is two chances to over-commit,
            # and this suite is sparse enough already
            starts, at = [], text.find(ab)
            while at >= 0:
                starts.append(at)
                at = text.find(ab, at + 1)
            for i in starts:
                m = spans.get((i, i + len(ab)))
                if m is None:
                    continue
                collision_mentions += 1
                if set(meta.collisions[ab]) <= _entities(m):
                    collision_both_in_set += 1
                if m.get("link_decision") == "RESOLVED":
                    collision_committed += 1
                    if len(collision_examples) < 10:
                        collision_examples.append(
                            {"text": text, "abbrev": ab,
                             "committed": m["resolved_entity"]["entity_id"]})

    return {
        "decoys": decoy_stats(meta),
        "sentences_scanned": len(rows),
        "decoy_candidate_mentions": decoy_candidates,
        "decoy_commits": decoy_commits,
        "decoy_examples": decoy_examples,
        "silver": {
            "mentions": silver_total,
            "gold_in_set": round(silver_in_set / silver_total, 4)
            if silver_total else None,
            "commits_with_decoys": silver_commit,
            "commits_without_decoys": base_commit,
            "commit_cost_of_decoys": base_commit - silver_commit,
        },
        "abbrev_collision": {
            "mentions": collision_mentions,
            "both_senses_in_set": collision_both_in_set,
            "committed_anyway": collision_committed,
            "overcommit_rate": round(collision_committed / collision_mentions, 4)
            if collision_mentions else None,
            "examples": collision_examples,
        },
    }


def _delta(now, before, digits: int = 4) -> str:
    """`before → now (±d)` when a control arm exists, else just the value."""
    if before is None or now is None:
        return str(now)
    d = round(now - before, digits)
    return f"{before} → **{now}** ({'+' if d > 0 else ''}{d})"


def write_markdown(payload: dict, out_path: Path,
                   control: dict | None = None) -> None:
    v, c = payload["variant"], payload["confusion"]
    h = v["headline"]
    ch = control["variant"]["headline"] if control else {}
    cf = control["variant"]["by_formation"] if control else {}
    lines = [
        "# 변형 회수 — variant family 단위 평가",
        "",
        "이 리포트의 단위는 mention이 아니라 **등록 용어**다. glossary의 각"
        " entity에 대해 표면형을 formation 하나씩 변형해 실문장에 넣고, 그 용어가"
        " 돌아오는지를 묻는다. headline은 family 매크로 평균이라 천 번 언급되는"
        " 부처와 한 번 언급되는 용어가 같은 무게를 갖는다.",
        "",
        f"재현: `python -m eval.run_variant_recall` · seed {payload['seed']} ·"
        f" {v['families']} families × {len(FORMATIONS)} formations ="
        f" **{v['cases']} cases** · host 문장 {payload['sentences']}개.",
        "",
    ]
    if control:
        lines += [
            "대조군은 같은 스크립트·같은 seed를 다른 체크아웃에서 돌린 것이다"
            " (`--compare`). 두 arm은 같은 표본·같은 case를 본다.",
            "",
        ]
    lines += [
        "## 0. 한눈에",
        "",
        "| 지표 | 조건 | 값 |",
        "|---|---|---:|",
        "| **variant-family macro recall** | `\\|candidate` | "
        + _delta(h["variant_family_macro_recall"],
                 ch.get("variant_family_macro_recall")) + " |",
        "| ├ Level A formation | `\\|candidate` | "
        + _delta(h["level_a_macro"], ch.get("level_a_macro")) + " |",
        "| └ **Level B formation** | `\\|candidate` | "
        + _delta(h["level_b_macro"], ch.get("level_b_macro")) + " |",
        "| commit macro (§2 SAME 형성) | `\\|commit` | "
        + _delta(h["commit_macro_on_same"], ch.get("commit_macro_on_same")) + " |",
        "| core span 오분해율 | `\\|mention` | "
        + _delta(h["core_span_wrong_rate"], ch.get("core_span_wrong_rate")) + " |",
        "| 이름 끝을 맞게 보고 (`name_span_exact`) | `\\|mention` | "
        + _delta(h["name_span_exact_rate"], ch.get("name_span_exact_rate"))
        + " |",
        "| 잘못된 entity 확정 | `\\|commit` | "
        + _delta(h["wrong_entity_commits"], ch.get("wrong_entity_commits"), 0) + " |",
        "| **불변조건 ② 위반** | `\\|commit` | "
        + _delta(h["contract_violations"], ch.get("contract_violations"), 0) + " |",
        "",
        "마지막 두 줄은 비율이 아니라 건수다. 0이 아니면 그 자체가 결함이고,"
        " 재현율과 교환할 수 있는 값이 아니다.",
        "",
        "Level A는 결정적 정규화·분해로 닿는 formation(원형·띄어쓰기·전각·조사·"
        "자모 분리)이고, Level B는 fuzzy 채널로만 닿는 것(오타·키보드)이다."
        " **전체 매크로는 Level A가 끌어올린다** — 움직임이 보이는 곳은 B다.",
        "",
        "## 1. formation별",
        "",
        "`§2 계약` 열은 VARIANTS_PLAN §2에서 왔다 — 리졸버의 guard 규칙이 아니라"
        " 계획 문서다. guard에서 가져오면 정의상 통과하는 시험이 된다.",
        "",
        "| formation | tier | §2 계약 | cases | candidate macro | micro"
        " | commit macro | span 정확 | `UNKNOWN` 판정 | 위반 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for f in FORMATIONS:
        s = v["by_formation"][f.key]
        if not s["cases"]:
            lines.append(f"| `{f.key}` | {f.tier} | {f.commit}"
                         " | 0 | — | — | — | — | — | — |")
            continue
        prev = cf.get(f.key, {}).get("candidate_macro") if control else None
        prev_unk = cf.get(f.key, {}).get("identity_unknown") if control else None
        # the UNKNOWN column is the one a catalog change is allowed to move:
        # it counts wider surfaces the resolver could not name. Keeping it
        # beside `위반` makes the trade visible — a catalog that lowers one
        # while raising the other has loosened the contract, not improved.
        unk = ("—" if f.commit != FORBIDDEN
               else _delta(s["identity_unknown"], prev_unk, 0))
        lines.append(
            f"| `{f.key}` | {f.tier} | {f.commit} | {s['cases']} | "
            + _delta(s["candidate_macro"], prev)
            + f" | {s['candidate_micro']} | {s['commit_macro']}"
            f" | {s['core_span_exact']} | {unk} | {s['violations']} |")
    fl = v["forbidden_labels"]
    c_unknown = (control["variant"]["forbidden_labels"]["identity_unknown"]
                 if control else None)
    lines += [
        "",
        "FORBIDDEN 행의 `commit macro`는 재현율이 아니라 **보수성**이다: core에"
        " 확정을 건 비율이며, 낮을수록 guard가 많이 보류했다는 뜻이다."
        " CONDITIONAL 행의 0.0도 결함이 아니다 — §2가 확정을 요구하지 않는다.",
        "",
        "## 2. FORBIDDEN 계약 — 막았는가, 그리고 뭐라고 불렀는가",
        "",
        "`한전노조`는 다른 조직이고 `금감원장`은 사람이다. 두 가지를 따로 센다:"
        " **확정을 막았는가**(불변조건 ②, 위 표의 `위반` 열)와 **관계를 이름으로"
        " 말했는가**. 앞은 계약이라 0이어야 하고, 뒤는 카탈로그 커버리지라 개선"
        " 대상이다 — 카탈로그를 넓히면 뒤가 오르고 앞은 그대로여야 한다.",
        "",
        f"- FORBIDDEN cases: **{fl['cases']}**",
        f"- 넓은 표면형을 응답에 실은 것: {fl['surface_wider_reported']}",
        "- 그중 `UNKNOWN` 판정: "
        + _delta(fl["identity_unknown"], c_unknown, 0) + " (카탈로그 확장 여지)",
        "",
        "관계 라벨 분포: "
        + (", ".join(f"`{k}` {n}" for k, n in fl["relation"].items()) or "없음"),
        "",
    ]
    if c:
        lines += [
            "## 3. Confusion — 닮은 것 중에 고르기",
            "",
            "fake glossary는 코퍼스와 형태소를 공유하지 않는 이름을 쓴다. 거기서의"
            " 0은 '엉뚱한 것을 만들지 않는다'는 뜻이지 '둘 중 맞는 것을 고른다'는"
            " 뜻이 아니다. 여기 decoy는 전부 **실제 등록 entity에 붙여** 만든다.",
            "",
            f"- decoy entity {c['decoys']['decoy_entities']}개"
            f" (근접 표면형 {c['decoys']['near_miss']},"
            f" 약칭 충돌 {c['decoys']['abbrev_collisions']},"
            f" 접두 확장 {c['decoys']['prefix_extensions']})",
            f"- decoy가 **후보로 올라온** mention: {c['decoy_candidate_mentions']}"
            " — 0이면 이 시험은 무의미하다(decoy에 닿지도 못했다는 뜻)",
            f"- **decoy 확정(FP): {c['decoy_commits']}건**",
            "",
            "### 3.1 decoy를 넣으면 진짜 확정이 줄어드는가",
            "",
            "같은 문장·같은 silver span을 decoy 있는 스냅샷과 없는 스냅샷에서 각각"
            " 돌린 쌍 비교다.",
            "",
            f"- silver mention {c['silver']['mentions']}건,"
            f" gold-in-set {c['silver']['gold_in_set']}",
            f"- 확정: decoy 없음 {c['silver']['commits_without_decoys']} →"
            f" decoy 있음 {c['silver']['commits_with_decoys']}"
            f" (**차이 {c['silver']['commit_cost_of_decoys']}**)",
            "",
            "### 3.2 약칭 충돌 — 두 뜻이 생기면 확정을 미루는가",
            "",
            "decoy가 실제 약칭을 **같이** 등록한다. 그러면 그 약칭의 올바른 답은"
            " AMBIGUOUS(두 뜻 모두 후보)이지 어느 한쪽의 확정이 아니다.",
            "",
            f"- 충돌 약칭 mention: {c['abbrev_collision']['mentions']}",
            "- 두 뜻이 모두 prediction set에: "
            f"{c['abbrev_collision']['both_senses_in_set']}",
            f"- **그럼에도 확정: {c['abbrev_collision']['committed_anyway']}"
            f" (과확정률 {c['abbrev_collision']['overcommit_rate']})**",
            "",
        ]
    if v["worst_families"]:
        lines += [
            "## 4. 최악 family",
            "",
            "매크로 평균이 감추는 것이 여기 있다 — 이 용어들은 어떤 변형에서도"
            " 잘 돌아오지 않는다.",
            "",
            "| entity | family recall |",
            "|---|---:|",
        ]
        lines += [f"| `{e}` | {r} |" for e, r in v["worst_families"]]
        lines.append("")
    lines += [
        "## 5. 읽는 법과 한계",
        "",
        "- **매크로와 마이크로가 갈리면 매크로를 본다.** 마이크로는 case를 많이"
        " 만든 family가 지배하고, 이 스위트는 family마다 같은 수를 만들므로 둘의"
        " 차이는 곧 family 간 편차다.",
        "- 변형은 합성이고 **문맥은 실제**다. 사람이 라벨한 실문장 gold는"
        " [VARIANT_GOLD.md](VARIANT_GOLD.md)에서 따로 잰다.",
        "- formation은 §2 표의 행에 대응한다. `CONDITIONAL` 행은 확정해도 안 해도"
        " 계약 위반이 아니므로 **판정을 내리지 않고 비율만** 싣는다.",
        "- 적용 불가 cell(라틴 표면형에 중성 오타)은 0점이 아니라 **분모에서"
        " 빠진다**. 문자 체계 때문에 family가 손해 보면 안 된다.",
        "- decoy는 합성이지만 실제 등록 표면형에서 **1 중성 거리**로 만든다."
        " 형태소를 공유하지 않는 fake glossary와는 난이도가 다르다.",
        "",
        provenance_line(ROOT),
        "",
        "*generated by `python -m eval.run_variant_recall`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=2)
    ap.add_argument("--sentences", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--json", type=Path, default=None,
                    help="also write the raw payload here (for --compare)")
    ap.add_argument("--compare", type=Path, default=None,
                    help="a payload from another checkout, rendered as the "
                         "control column")
    ap.add_argument("--skip-confusion", action="store_true")
    ap.add_argument("--render-only", type=Path, default=None,
                    help="rewrite the report from an existing payload without "
                         "re-measuring. A layout fix should not cost a run.")
    args = ap.parse_args()

    if args.render_only:
        payload = json.loads(args.render_only.read_text(encoding="utf-8"))
        control = (json.loads(args.compare.read_text(encoding="utf-8"))
                   if args.compare else None)
        write_markdown(payload, ROOT / "reports" / "VARIANT_RECALL.md", control)
        print(f"rendered from {args.render_only}")
        return

    corpus = load_corpus()
    rng = random.Random(args.seed)
    sample = rng.sample(corpus, min(args.sentences, len(corpus)))
    print(f"corpus: {len(corpus)} sentences, sample {len(sample)}")

    variant = run_variant_suite(sample, args.per_cell, args.seed)
    print("variant suite done:", json.dumps(variant["headline"],
                                            ensure_ascii=False))
    confusion = ({} if args.skip_confusion
                 else run_confusion_suite(sample, args.seed))
    payload = {"seed": args.seed, "sentences": len(sample),
               "per_cell": args.per_cell,
               "variant": variant, "confusion": confusion}
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "variant_recall.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    control = (json.loads(args.compare.read_text(encoding="utf-8"))
               if args.compare else None)
    write_markdown(payload, ROOT / "reports" / "VARIANT_RECALL.md", control)
    print(json.dumps({"headline": variant["headline"],
                      "confusion": {k: confusion.get(k)
                                    for k in ("decoy_commits",
                                              "decoy_candidate_mentions")}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Downstream A/B evaluation: does KTRF terminology context actually
improve LLM answers?

Usage: python -m eval.run_ab_grounding [--model qwen3:8b] [--n-per-slice 150]

Four conditions on the SAME seeded cases (paired design):

  A  llm_only        no terminology context
  B  full_glossary   naive glossary dump, budget-capped at the same token
                     budget as C (entity-id order — no relevance selection)
  C  ktrf            KTRF context pack (resolve → build_context_pack)
  D  gold            the correct entity's card only, same renderer/budget —
                     the oracle ceiling for context selection

Two auto-gradable slices built from the wild corpus (rule-derived gold —
same silver/UE machinery as WILD_CORPUS/NEURAL_EVAL, limitations included):

  known_abbrev   registered abbreviation in a real sentence (금감원 …);
                 gold = the entity's full name. Context condition C uses
                 the full glossary.
  unseen_abbrev  §42 UE holdout: the abbreviation's binding is REMOVED
                 from the glossary; C must ground through Pass-2
                 (abbrev alignment ∪ dense) candidates.

Task (Track 1, terminology interpretation): "이 문장에서 '<surface>'이(가)
가리키는 대상의 정식 명칭은?" → JSON {"canonical": ...}. Graded by
normalized containment against the entity's full-name alias set.

Headline metrics (per slice, vs condition A): accuracy, Helpful Flip
(A wrong → cond right), Harmful Flip (A right → cond wrong), and
Gold Benefit Recovery = (acc_C − acc_A) / (acc_D − acc_A).

Writes eval/out/ab_grounding.json and reports/AB_GROUNDING.md.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from ktrf.context import (CharTokenCounter, ContextPolicy,
                          TERMINOLOGY_POLICY, build_context_pack,
                          render_context_pack)
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import wilson_interval
from .run_llm_rag import OllamaError, ollama_chat
from .run_neural_eval import HOLDOUT_ABBREVS, _holdout_glossary, _queries
from .run_wild import _silver_occurrences
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 11
BUDGET_TOKENS = 800

SYSTEM_PROMPT = ("너는 한국어 문서를 읽고 질문에 답하는 어시스턴트다. "
                 "반드시 JSON만 출력한다.")

QUESTION = ("이 문장에서 {surface!r}이(가) 가리키는 대상의 정식 명칭"
            "(full name)은? 확실하지 않으면 canonical에 null을 넣어라.\n"
            '출력 형식: {{"canonical": "...", "confident": true}}')


# ------------------------------------------------------------------ cases

def _full_name_answers(glossary, entity_id: str) -> list[str]:
    """Acceptable answers: canonical + full-name (non-abbreviation) aliases."""
    ent = glossary.entity(entity_id)
    out = {ent.canonical}
    for b in glossary.alias_bindings:
        if b.entity_id == entity_id and b.kind != "abbreviation":
            out.add(b.surface)
    return sorted(out)


def build_cases(corpus, glossary, n_per_slice: int) -> list[dict]:
    rng = random.Random(SEED)
    alias_to = {b.surface: (b.entity_id, b.kind)
                for b in glossary.alias_bindings}
    # known slice: registered abbreviations (surface != full name), not in
    # the UE holdout so the two slices stay disjoint
    abbrevs = [s for s, (eid, kind) in alias_to.items()
               if kind == "abbreviation" and len(s) >= 3
               and s not in HOLDOUT_ABBREVS]
    known: list[dict] = []
    for row in corpus:
        occs = _silver_occurrences(row["text"], abbrevs)
        for s, e, a in occs:
            eid = alias_to[a][0]
            known.append({
                "slice": "known_abbrev", "text": row["text"], "surface": a,
                "entity_id": eid,
                "answers": _full_name_answers(glossary, eid),
            })
            break  # at most one case per sentence
    rng.shuffle(known)
    known = known[:n_per_slice]

    holdout_glossary, holdout_map = _holdout_glossary()
    unseen: list[dict] = []
    for q in _queries(holdout_map):
        unseen.append({
            "slice": "unseen_abbrev", "text": q["text"],
            "surface": q["surface"], "entity_id": q["gold"],
            "answers": _full_name_answers(glossary, q["gold"]),
        })
    rng.shuffle(unseen)
    unseen = unseen[:n_per_slice]
    return known + unseen, holdout_glossary


# -------------------------------------------------------------- contexts

def _naive_glossary_dump(glossary, budget: int) -> str:
    """Condition B: entity-id-ordered dump, cut at the shared budget."""
    counter = CharTokenCounter()
    lines = ["<glossary>"]
    used = counter.count(lines[0]) + 12
    aliases: dict[str, list[str]] = {}
    for b in glossary.alias_bindings:
        aliases.setdefault(b.entity_id, []).append(b.surface)
    for ent in sorted(glossary.entities, key=lambda e: e.entity_id):
        al = ", ".join(s for s in aliases.get(ent.entity_id, [])
                       if s != ent.canonical)
        desc = (ent.grounding or {}).get("short_definition") \
            or ent.description[:80]
        line = (f'  <term canonical="{ent.canonical}" aliases="{al}">'
                f"{desc}</term>")
        cost = counter.count(line)
        if used + cost > budget:
            break
        lines.append(line)
        used += cost
    lines.append("</glossary>")
    return "\n".join(lines)


def _gold_pack_fragment(glossary, case: dict) -> str:
    """Condition D: exactly the right entity, same renderer as C."""
    ent = glossary.entity(case["entity_id"])
    pack = {
        "schema_version": "1", "profile": "qa_grounding",
        "expose_entity_ids": True,
        "snapshot": {"glossary_id": glossary.glossary_id,
                     "glossary_version": glossary.version},
        "resolved_terms": [{
            "entity_id": ent.entity_id, "canonical": ent.canonical,
            "short_definition": (ent.grounding or {}).get(
                "short_definition") or ent.description[:180],
            "disambiguation_hints": [],
            "mentions": [{"surface": case["surface"]}],
        }],
        "ambiguous_mentions": [], "document_definitions": [],
        "unknown_mentions": [], "omissions": [],
        "coverage": {"complete": True},
    }
    return render_context_pack(pack, "xml")


def _ktrf_fragment(snapshot, case: dict, question: str) -> str:
    resp = resolve(snapshot, case["text"], mode="commit",
                   options={"return_all_mentions": True,
                            "max_prediction_set": 50,
                            "detect_unregistered_mentions": True})
    pack = build_context_pack(
        snapshot, resp, query=question,
        policy=ContextPolicy(max_tokens=BUDGET_TOKENS))
    if pack["coverage"].get("empty"):
        # a pack that grounds nothing is not injected: an empty
        # terminology block reads as authoritative absence and makes the
        # model distrust knowledge it already had (measured: 13 of 17
        # harmful flips in the first pilot came from empty packs)
        return ""
    return render_context_pack(pack, "xml")


# ---------------------------------------------------------------- grading

def _norm(s: str) -> str:
    return "".join((s or "").split()).lower()


def grade(answer_raw: str, answers: list[str]) -> bool:
    try:
        obj = json.loads(answer_raw)
    except json.JSONDecodeError:
        return False
    cand = obj.get("canonical") if isinstance(obj, dict) else None
    if not isinstance(cand, str) or not cand.strip():
        return False
    n = _norm(cand)
    for gold in answers:
        g = _norm(gold)
        if g and (g in n or n in g):
            return True
    return False


# ------------------------------------------------------------------- run

def run_condition(base: str, model: str, cases: list[dict],
                  fragments: dict[int, str]) -> list[dict]:
    """fragments: case index -> terminology context ('' for condition A)."""
    out = []
    for i, case in enumerate(cases):
        question = QUESTION.format(surface=case["surface"])
        frag = fragments.get(i, "")
        parts = []
        if frag:
            parts += [TERMINOLOGY_POLICY, "", frag, ""]
        parts += ["[문장]", case["text"], "", question]
        t0 = time.perf_counter()
        raw, _ = ollama_chat(base, model, SYSTEM_PROMPT, "\n".join(parts))
        out.append({"correct": grade(raw, case["answers"]),
                    "raw": raw[:200],
                    "latency_s": round(time.perf_counter() - t0, 2)})
    return out


def summarize(cases, results_by_cond) -> dict:
    conds = list(results_by_cond)
    slices = sorted({c["slice"] for c in cases})
    summary: dict = {"slices": {}, "overall": {}}

    def acc(rows, idxs):
        hits = sum(rows[i]["correct"] for i in idxs)
        lo, hi = wilson_interval(hits, len(idxs))
        return {"hits": hits, "total": len(idxs),
                "rate": round(hits / len(idxs), 4) if idxs else None,
                "ci95": [round(lo, 4), round(hi, 4)]}

    def flips(base_rows, rows, idxs):
        helpful = sum(1 for i in idxs
                      if not base_rows[i]["correct"] and rows[i]["correct"])
        harmful = sum(1 for i in idxs
                      if base_rows[i]["correct"] and not rows[i]["correct"])
        return {"helpful": helpful, "harmful": harmful,
                "harmful_rate": round(harmful / len(idxs), 4)}

    for scope, idxs in ([("overall", list(range(len(cases))))]
                        + [(s, [i for i, c in enumerate(cases)
                                if c["slice"] == s]) for s in slices]):
        block = {}
        for cond in conds:
            block[cond] = acc(results_by_cond[cond], idxs)
            if cond != "A_llm_only":
                block[cond]["flips_vs_A"] = flips(
                    results_by_cond["A_llm_only"],
                    results_by_cond[cond], idxs)
        a = block["A_llm_only"]["rate"]
        c = block.get("C_ktrf", {}).get("rate")
        d = block.get("D_gold", {}).get("rate")
        if None not in (a, c, d) and d - a > 0.005:
            block["gold_benefit_recovery"] = round((c - a) / (d - a), 4)
        else:
            block["gold_benefit_recovery"] = None
        target = summary["slices"] if scope != "overall" else summary
        if scope == "overall":
            summary["overall"] = block
        else:
            target[scope] = block
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--n-per-slice", type=int, default=150)
    ap.add_argument("--ollama", default="http://localhost:11434")
    args = ap.parse_args()

    corpus = load_corpus()
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    cases, holdout_glossary = build_cases(corpus, glossary, args.n_per_slice)
    print(f"cases: {len(cases)} "
          f"({sum(c['slice'] == 'known_abbrev' for c in cases)} known / "
          f"{sum(c['slice'] == 'unseen_abbrev' for c in cases)} unseen)")

    from ktrf.encoders import HashEncoder, OnnxE5Encoder
    e5_dir = ROOT / "models" / "multilingual-e5-small"
    encoder = OnnxE5Encoder(e5_dir) if e5_dir.exists() else HashEncoder()
    full_snap = compile_snapshot(glossary, encoder=encoder,
                                 run_conformance=False)
    holdout_snap = compile_snapshot(holdout_glossary, encoder=encoder,
                                    run_conformance=False)

    # precompute per-condition context fragments (CPU side, deterministic)
    frag_b, frag_c, frag_d = {}, {}, {}
    naive = _naive_glossary_dump(glossary, BUDGET_TOKENS)
    for i, case in enumerate(cases):
        question = QUESTION.format(surface=case["surface"])
        snap = (full_snap if case["slice"] == "known_abbrev"
                else holdout_snap)
        frag_b[i] = naive
        frag_c[i] = _ktrf_fragment(snap, case, question)
        frag_d[i] = _gold_pack_fragment(glossary, case)
    print("context fragments prepared")

    results_by_cond = {}
    for cond, frags in [("A_llm_only", {}), ("B_full_glossary", frag_b),
                        ("C_ktrf", frag_c), ("D_gold", frag_d)]:
        print(f"=== {cond} ({args.model}) ===")
        t0 = time.perf_counter()
        try:
            results_by_cond[cond] = run_condition(
                args.ollama, args.model, cases, frags)
        except OllamaError as e:
            print(f"ABORT {cond}: {e}")
            return
        n_ok = sum(r["correct"] for r in results_by_cond[cond])
        print(f"  acc {n_ok}/{len(cases)} "
              f"({time.perf_counter() - t0:.0f}s)")

    summary = summarize(cases, results_by_cond)
    run = {
        "budget_tokens": BUDGET_TOKENS,
        "cases": len(cases),
        "seed": SEED,
        "summary": summary,
        "case_records": [
            {**{k: c[k] for k in ("slice", "surface", "entity_id")},
             "results": {cond: results_by_cond[cond][i]["correct"]
                         for cond in results_by_cond}}
            for i, c in enumerate(cases)],
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "ab_grounding.json"
    # accumulate across models: a second model must extend the comparison,
    # not overwrite the first model's run
    payload = {"runs": {}}
    if path.exists():
        prior = json.loads(path.read_text(encoding="utf-8"))
        payload["runs"] = prior.get("runs") or (
            {prior["model"]: prior} if "model" in prior else {})
    payload["runs"][args.model] = run
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "AB_GROUNDING.md")
    print(json.dumps(summary["overall"], ensure_ascii=False, indent=2)[:800])
    print("wrote eval/out/ab_grounding.json and reports/AB_GROUNDING.md")


def write_markdown(payload: dict, out_path: Path) -> None:
    runs = payload["runs"]
    conds = [("A_llm_only", "A. LLM only"),
             ("B_full_glossary", "B. naive full glossary"),
             ("C_ktrf", "C. KTRF context pack"),
             ("D_gold", "D. gold context (oracle)")]
    any_run = next(iter(runs.values()))
    lines = [
        "# KTRF Downstream A/B — LLM 답변 개선 효과",
        "",
        f"동일 seeded {any_run['cases']}사례 (paired), context budget"
        f" {any_run['budget_tokens']} tokens (B/C/D 동일 — 선택 방식만"
        " 다름). 과제: 문장 속 약칭이 가리키는 대상의 정식 명칭 답하기"
        " (Track 1). gold label은 silver/UE 규칙 기반 근사다."
        " 재현: `python -m eval.run_ab_grounding --model <name>`.",
        "",
        "## 요약 (모델별 전체 accuracy)",
        "",
        "| 모델 | A. LLM only | C. KTRF | D. gold | GBR | harmful flip |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model, run in runs.items():
        o = run["summary"]["overall"]
        gbr = o.get("gold_benefit_recovery")
        lines.append(
            f"| {model} | {o['A_llm_only']['rate']}"
            f" | **{o['C_ktrf']['rate']}** | {o['D_gold']['rate']}"
            f" | {gbr if gbr is not None else 'N/A'}"
            f" | {o['C_ktrf']['flips_vs_A']['harmful']} |")
    lines.append("")

    for model, run in runs.items():
        s = run["summary"]
        lines += [f"## {model}", ""]
        for scope_name, block in [("전체", s["overall"])] + [
                (k, v) for k, v in s["slices"].items()]:
            lines += [f"### {scope_name}", "",
                      "| 조건 | accuracy | CI95 | helpful flip | harmful flip |",
                      "|---|---:|---|---:|---:|"]
            for key, label in conds:
                b = block[key]
                f = b.get("flips_vs_A")
                lines.append(
                    f"| {label} | {b['rate']} ({b['hits']}/{b['total']})"
                    f" | {b['ci95']}"
                    f" | {f['helpful'] if f else '—'}"
                    f" | {f['harmful'] if f else '—'} |")
            gbr = block.get("gold_benefit_recovery")
            lines += ["",
                      f"**Gold Benefit Recovery: "
                      f"{gbr if gbr is not None else 'N/A'}**"
                      " — KTRF context가 이상적 context 효과의 몇 %를"
                      " 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).", ""]
    lines += [
        "## 해석과 한계",
        "",
        "- paired 설계: 같은 사례에 네 조건을 적용해 flip을 직접 센다."
        " Harmful flip(원래 맞던 답을 context가 망친 사례)은 도입 결정의"
        " 핵심 지표다.",
        "- known 슬라이스는 LLM 세계지식만으로도 상당 부분 답할 수 있는"
        " 영역(유명 기관 약칭), unseen 슬라이스는 glossary에 등록되지 않은"
        " 약칭이라 KTRF도 Pass-2 후보로만 지원한다.",
        "- gold label은 규칙 기반 근사이며 사람 주석이 아니다. 표본 확대와"
        " human-gold 구축은 ROADMAP 백로그 참조.",
        "",
        "*generated by `python -m eval.run_ab_grounding`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

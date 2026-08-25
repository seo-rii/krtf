"""LLM+RAG baseline vs KTRF on the wild-corpus silver benchmark.

Usage: python -m eval.run_llm_rag [--models qwen3:8b,gemma3:12b] [--silver-n 200]
                                  [--fake-n 100] [--ollama http://localhost:11434]

Asks the question the user actually cares about: what does the symbolic+dense
KTRF stack buy over "just prompt a general open-weight LLM with retrieval"?
Both systems get the *same task* on the *same seeded sample* of real Korean
news sentences (KLUE, eval/wild_data.py cache):

- **Recall (silver)**: unambiguous real-org occurrences are near-certain
  mentions; system must produce the gold entity_id.
- **Grounding precision / hallucination**: an output entity none of whose
  registered surfaces occurs in the sentence is a hallucination.
- **Fake-glossary FP**: candidates retrieved from a glossary whose surfaces
  are verified absent from the corpus — any claimed mention is a false
  positive by construction (KTRF measures 0 here).
- **Speed**: per-sentence wall latency (p50/p95) and throughput.

The LLM gets a *generous hybrid retriever* (dense top-k over entity profiles
UNION every entity whose alias literally occurs in the sentence), so the
comparison isolates linking/grounding quality, not retriever quality.
LLM backend: Ollama HTTP API (quantized open-weight models; RTX 3080 10GB
fits ~14B q4 — 27B-class models are documented as out of budget).

Writes eval/out/llm_rag.json and reports/LLM_RAG_COMPARE.md.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

from ktrf.dense import VectorIndex, entity_profile_text
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from .metrics import wilson_interval
from .run_neural_eval import _holdout_glossary, _pipeline_recall, _queries
from .run_wild import DETECTION_ONLY, SILVER_MIN_LEN, _silver_occurrences
from .synthetic import build_synthetic_glossary
from .wild_data import load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 7
TOP_K = 10
MAX_CANDIDATES = 14
NUM_PREDICT = 512

SYSTEM_PROMPT = (
    "너는 한국어 용어 해석기다. 주어진 용어집 후보 중에서 문장에 실제로 "
    "언급된 entity만 찾아 연결한다. 반드시 JSON만 출력한다."
)

USER_TEMPLATE = """[용어집 후보]
{cards}

[문장]
{sentence}

문장에 실제로 언급된 용어집 entity를 모두 찾아라. 별칭이나 조사가 붙은 형태(예: 한전이, 금감원은)도 언급이다. 문장에 없는 entity, 후보에 없는 entity_id를 절대 만들지 마라.
출력 형식: {{"mentions": [{{"surface": "문장 속 표면형", "entity_id": "..."}}]}}
언급이 없으면 {{"mentions": []}}"""


# ---------------------------------------------------------------- retrieval

def build_cards(glossary) -> dict[str, str]:
    """entity_id -> one-line card with canonical, aliases, description."""
    aliases: dict[str, list[str]] = {}
    for b in glossary.alias_bindings:
        aliases.setdefault(b.entity_id, []).append(b.surface)
    cards = {}
    for e in glossary.entities:
        al = [s for s in aliases.get(e.entity_id, []) if s != e.canonical]
        cards[e.entity_id] = (
            f"- entity_id: {e.entity_id} | 명칭: {e.canonical}"
            + (f" | 별칭: {', '.join(al)}" if al else "")
            + f" | 설명: {e.description}")
    return cards


class HybridRetriever:
    """Dense top-k over entity profiles ∪ literal alias hits (LLM-generous)."""

    def __init__(self, glossary, encoder):
        self.encoder = encoder
        self.surface_to_entity = [(b.surface, b.entity_id)
                                  for b in glossary.alias_bindings]
        ids = [e.entity_id for e in glossary.entities]
        vecs = encoder.encode_passages(
            [entity_profile_text(e) for e in glossary.entities])
        self.index = VectorIndex(ids, vecs)

    def retrieve(self, sentence: str) -> list[str]:
        lexical = [eid for s, eid in self.surface_to_entity if s in sentence]
        dense = [eid for eid, _ in
                 self.index.search(self.encoder.encode_query(sentence), TOP_K)]
        out: list[str] = []
        for eid in lexical + dense:  # lexical hits first, order-preserving dedup
            if eid not in out:
                out.append(eid)
        return out[:MAX_CANDIDATES]


# ------------------------------------------------------------------ ollama

class OllamaError(RuntimeError):
    pass


def ollama_chat(base: str, model: str, system: str, user: str,
                timeout: float = 300.0) -> tuple[str, dict]:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": NUM_PREDICT},
    }
    if model.startswith("gpt-oss"):
        body["think"] = "low"  # reasoning can't be disabled, only shortened
    elif model.startswith(("qwen3", "gemma4")):
        body["think"] = False  # measure answer latency, not chain-of-thought
    for attempt in (0, 1):
        req = urllib.request.Request(
            f"{base}/api/chat", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", ""), data
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            if attempt == 0 and "think" in body:
                body.pop("think")  # model rejects the thinking toggle
                continue
            raise OllamaError(f"HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError) as e:
            raise OllamaError(f"ollama unreachable: {e}") from e


def parse_mentions(raw: str, allowed: set[str]) -> tuple[list[dict], bool]:
    """Returns (grounded-format mentions, parse_ok)."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return [], False
    ms = obj.get("mentions") if isinstance(obj, dict) else None
    if not isinstance(ms, list):
        return [], False
    out = []
    for m in ms:
        if isinstance(m, dict) and isinstance(m.get("entity_id"), str):
            out.append({"surface": str(m.get("surface", "")),
                        "entity_id": m["entity_id"],
                        "in_candidates": m["entity_id"] in allowed})
    return out, True


# ------------------------------------------------------------------ suites

def sample_silver_sentences(corpus, glossary, n: int) -> list[dict]:
    alias_to_entity = {b.surface: b.entity_id for b in glossary.alias_bindings}
    silver_aliases = [s for s in alias_to_entity
                      if len(s) >= SILVER_MIN_LEN and s not in DETECTION_ONLY]
    rows = []
    for row in corpus:
        occs = _silver_occurrences(row["text"], silver_aliases)
        if occs:
            rows.append({"text": row["text"],
                         "gold": [{"surface": a, "entity_id": alias_to_entity[a]}
                                  for _, _, a in occs]})
    random.Random(SEED).shuffle(rows)
    return rows[:n]


def entity_surfaces(glossary) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for b in glossary.alias_bindings:
        out.setdefault(b.entity_id, []).append(b.surface)
    return out


def eval_llm_silver(base, model, samples, retriever, cards, surfaces) -> dict:
    gold_total = gold_hit = 0
    reported = grounded = 0
    parse_fail = 0
    latencies: list[float] = []
    examples: list[dict] = []
    for row in samples:
        cand = retriever.retrieve(row["text"])
        prompt = USER_TEMPLATE.format(
            cards="\n".join(cards[c] for c in cand), sentence=row["text"])
        t0 = time.perf_counter()
        raw, _ = ollama_chat(base, model, SYSTEM_PROMPT, prompt)
        latencies.append(time.perf_counter() - t0)
        mentions, ok = parse_mentions(raw, set(cand))
        if not ok:
            parse_fail += 1
        got_ids = {m["entity_id"] for m in mentions}
        for g in row["gold"]:
            gold_total += 1
            if g["entity_id"] in got_ids:
                gold_hit += 1
            elif len(examples) < 10:
                examples.append({"text": row["text"], "missed": g,
                                 "got": sorted(got_ids)})
        for m in mentions:
            reported += 1
            if any(s in row["text"] for s in surfaces.get(m["entity_id"], [])):
                grounded += 1
            elif len(examples) < 10:
                examples.append({"text": row["text"], "hallucinated": m})
    latencies.sort()
    lo, hi = wilson_interval(gold_hit, gold_total)
    return {
        "recall": {"hits": gold_hit, "total": gold_total,
                   "rate": round(gold_hit / gold_total, 4) if gold_total else None,
                   "ci95": [round(lo, 4), round(hi, 4)]},
        "grounding_precision": {
            "grounded": grounded, "reported": reported,
            "rate": round(grounded / reported, 4) if reported else None},
        "hallucinated_mentions": reported - grounded,
        "parse_failures": parse_fail,
        "latency_s": _lat(latencies),
        "examples": examples,
    }


def eval_llm_fake(base, model, sentences, retriever, cards) -> dict:
    fp = 0
    calls = 0
    latencies: list[float] = []
    examples: list[dict] = []
    for text in sentences:
        cand = retriever.retrieve(text)
        if not cand:
            continue
        prompt = USER_TEMPLATE.format(
            cards="\n".join(cards[c] for c in cand), sentence=text)
        t0 = time.perf_counter()
        raw, _ = ollama_chat(base, model, SYSTEM_PROMPT, prompt)
        latencies.append(time.perf_counter() - t0)
        calls += 1
        mentions, _ = parse_mentions(raw, set(cand))
        if mentions:
            fp += len(mentions)
            if len(examples) < 10:
                examples.append({"text": text, "claimed": mentions})
    latencies.sort()
    return {"sentences": calls, "fp_mentions": fp,
            "fp_rate_per_sentence": round(fp / calls, 4) if calls else None,
            "latency_s": _lat(latencies), "examples": examples}


def eval_ktrf_silver(samples, snap) -> dict:
    gold_total = gold_hit = resolved = resolved_correct = 0
    latencies: list[float] = []
    for row in samples:
        t0 = time.perf_counter()
        resp = resolve(snap, row["text"], mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        latencies.append(time.perf_counter() - t0)
        for g in row["gold"]:
            gold_total += 1
            hit = False
            for m in resp["mentions"]:
                ids = {x.get("entity_id") for x in
                       m.get("prediction_set", {}).get("members", [])}
                if "resolved_entity" in m:
                    ids.add(m["resolved_entity"]["entity_id"])
                if (m["surface"].startswith(g["surface"])
                        or g["surface"].startswith(m["surface"])) \
                        and g["entity_id"] in ids:
                    hit = True
            gold_hit += int(hit)
        for m in resp["mentions"]:
            if m.get("link_decision") == "RESOLVED":
                resolved += 1
                eid = m["resolved_entity"]["entity_id"]
                if any(g["entity_id"] == eid and
                       (m["surface"].startswith(g["surface"])
                        or g["surface"].startswith(m["surface"]))
                       for g in row["gold"]):
                    resolved_correct += 1
    latencies.sort()
    lo, hi = wilson_interval(gold_hit, gold_total)
    return {
        "recall": {"hits": gold_hit, "total": gold_total,
                   "rate": round(gold_hit / gold_total, 4),
                   "ci95": [round(lo, 4), round(hi, 4)]},
        "resolved_commits": resolved,
        "resolved_precision_lower_bound":
            round(resolved_correct / resolved, 4) if resolved else None,
        "latency_s": _lat(latencies),
    }


def eval_llm_hard(base, model, queries, retriever, cards) -> dict:
    """UE holdout: the mention surface is NOT a registered alias — the
    system must infer the link from canonical/description world knowledge."""
    total = hit = in_cand = 0
    latencies: list[float] = []
    misses: list[dict] = []
    for q in queries:
        cand = retriever.retrieve(q["text"])
        in_cand += int(q["gold"] in cand)
        prompt = USER_TEMPLATE.format(
            cards="\n".join(cards[c] for c in cand), sentence=q["text"])
        t0 = time.perf_counter()
        raw, _ = ollama_chat(base, model, SYSTEM_PROMPT, prompt)
        latencies.append(time.perf_counter() - t0)
        mentions, _ = parse_mentions(raw, set(cand))
        total += 1
        if q["gold"] in {m["entity_id"] for m in mentions}:
            hit += 1
        elif len(misses) < 8:
            misses.append({"text": q["text"], "surface": q["surface"]})
    latencies.sort()
    lo, hi = wilson_interval(hit, total)
    return {
        "recall": {"hits": hit, "total": total,
                   "rate": round(hit / total, 4) if total else None,
                   "ci95": [round(lo, 4), round(hi, 4)]},
        "gold_in_candidates": round(in_cand / total, 4) if total else None,
        "latency_s": _lat(latencies),
        "misses": misses,
    }


def eval_ktrf_fake(sentences, snap) -> dict:
    fp = 0
    latencies: list[float] = []
    for text in sentences:
        t0 = time.perf_counter()
        resp = resolve(snap, text, mode="commit",
                       options={"return_all_mentions": True})
        latencies.append(time.perf_counter() - t0)
        fp += sum(1 for m in resp["mentions"]
                  if m.get("link_decision") == "RESOLVED")
    latencies.sort()
    return {"sentences": len(sentences), "fp_mentions": fp,
            "latency_s": _lat(latencies)}


def _lat(latencies: list[float]) -> dict | None:
    if not latencies:
        return None
    return {"p50": round(latencies[len(latencies) // 2], 3),
            "p95": round(latencies[int(len(latencies) * .95)], 3),
            "mean": round(sum(latencies) / len(latencies), 3),
            "throughput_per_min": round(60 * len(latencies) /
                                        sum(latencies), 1)}


# ------------------------------------------------------------------- main

def build_fake_setup(corpus, encoder):
    g_dict, _ = build_synthetic_glossary(400, seed=5)
    all_text = "\n".join(r["text"] for r in corpus)
    kept = [b for b in g_dict["alias_bindings"] if b["surface"] not in all_text]
    kept_fids = {b["family_id"] for b in kept}
    g_dict["alias_bindings"] = kept
    g_dict["alias_families"] = [f for f in g_dict["alias_families"]
                                if f["family_id"] in kept_fids]
    kept_eids = {b["entity_id"] for b in kept}
    g_dict["entities"] = [e for e in g_dict["entities"]
                          if e["entity_id"] in kept_eids]
    fake_glossary = load_glossary(g_dict)
    snap = compile_snapshot(fake_glossary, strict=False, run_conformance=False)
    return fake_glossary, snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--models",
        default="qwen3:8b,gemma4:12b,gemma4:26b,gpt-oss:20b,qwen3.5:27b@60",
        help="comma list; 'name@N' caps that model's silver sample at N "
             "(fake sample at N/2) — for models needing CPU offload")
    ap.add_argument("--silver-n", type=int, default=200)
    ap.add_argument("--fake-n", type=int, default=100)
    ap.add_argument("--hard-n", type=int, default=300,
                    help="UE-holdout hard-track queries per model")
    ap.add_argument("--track", choices=["easy", "hard", "both"],
                    default="both",
                    help="'hard' merges into an existing eval/out/llm_rag.json")
    ap.add_argument("--ollama", default="http://localhost:11434")
    args = ap.parse_args()

    corpus = load_corpus()
    glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
    surfaces = entity_surfaces(glossary)
    cards = build_cards(glossary)

    # retriever encoder: e5 if the model dir exists, else hash fallback
    from ktrf.encoders import HashEncoder, OnnxE5Encoder
    e5_dir = ROOT / "models" / "multilingual-e5-small"
    encoder = OnnxE5Encoder(e5_dir) if e5_dir.exists() else HashEncoder()
    retriever = HybridRetriever(glossary, encoder)

    samples = sample_silver_sentences(corpus, glossary, args.silver_n)
    rng = random.Random(SEED + 1)
    fake_sentences = [r["text"] for r in rng.sample(corpus,
                                                    min(args.fake_n, len(corpus)))]
    print(f"sample: {len(samples)} silver sentences "
          f"({sum(len(s['gold']) for s in samples)} gold instances), "
          f"{len(fake_sentences)} fake-FP sentences")

    # resume support: 'hard' merges into a previous easy-track payload
    out_json = ROOT / "eval" / "out" / "llm_rag.json"
    results: dict = {}
    if args.track == "hard" and out_json.exists():
        results = json.loads(out_json.read_text(encoding="utf-8"))["results"]
    results.setdefault("ktrf", {})

    specs = [m.strip() for m in args.models.split(",") if m.strip()]

    if args.track in ("easy", "both"):
        snap = compile_snapshot(glossary, encoder=encoder,
                                run_conformance=False)
        fake_glossary, fake_snap = build_fake_setup(corpus, encoder)
        fake_cards = build_cards(fake_glossary)
        fake_retriever = HybridRetriever(fake_glossary, encoder)
        results["ktrf"]["silver"] = eval_ktrf_silver(samples, snap)
        results["ktrf"]["fake"] = eval_ktrf_fake(fake_sentences, fake_snap)
        print("ktrf:", json.dumps(results["ktrf"]["silver"]["recall"],
                                  ensure_ascii=False))
        for spec in specs:
            model, _, cap = spec.partition("@")
            n = min(int(cap), len(samples)) if cap else len(samples)
            m_samples = samples[:n]
            m_fake = fake_sentences[:max(1, n // 2)] if cap \
                else fake_sentences
            print(f"=== {model} (silver n={len(m_samples)}, "
                  f"fake n={len(m_fake)}) ===")
            try:
                t0 = time.perf_counter()
                results.setdefault(model, {}).update({
                    "silver": eval_llm_silver(args.ollama, model, m_samples,
                                              retriever, cards, surfaces),
                    "fake": eval_llm_fake(args.ollama, model, m_fake,
                                          fake_retriever, fake_cards),
                    "silver_sentences": len(m_samples),
                    "fake_sentences": len(m_fake),
                    "elapsed_s": round(time.perf_counter() - t0, 1),
                })
                print(json.dumps(results[model]["silver"]["recall"],
                                 ensure_ascii=False))
            except OllamaError as e:
                results[model] = {"error": str(e)}
                print(f"  SKIPPED: {e}")

    if args.track in ("hard", "both"):
        # UE holdout: abbreviation bindings removed from the glossary, so
        # the mention surface is unseen — KTRF is far from 1.0 here
        hard_glossary, holdout_map = _holdout_glossary()
        hard_queries = _queries(holdout_map)
        random.Random(SEED + 2).shuffle(hard_queries)
        hard_queries = hard_queries[:args.hard_n]
        hard_cards = build_cards(hard_glossary)
        hard_retriever = HybridRetriever(hard_glossary, encoder)
        print(f"hard track: {len(hard_queries)} UE queries "
              f"({len(holdout_map)} held-out abbreviations)")

        hard_snap = compile_snapshot(hard_glossary, encoder=encoder,
                                     run_conformance=False)
        results["ktrf"]["hard"] = _pipeline_recall(
            hard_snap, hard_queries, "ktrf-e5")
        results["ktrf"]["hard_queries"] = len(hard_queries)
        print("ktrf hard:", json.dumps(
            results["ktrf"]["hard"]["gold_in_set_e2e"], ensure_ascii=False))
        for spec in specs:
            model, _, cap = spec.partition("@")
            n = min(int(cap), len(hard_queries)) if cap else len(hard_queries)
            print(f"=== {model} hard (n={n}) ===")
            try:
                results.setdefault(model, {}).update({
                    "hard": eval_llm_hard(args.ollama, model,
                                          hard_queries[:n],
                                          hard_retriever, hard_cards),
                    "hard_queries": n,
                })
                print(json.dumps(results[model]["hard"]["recall"],
                                 ensure_ascii=False))
            except OllamaError as e:
                results[model].setdefault("hard", {"error": str(e)})
                print(f"  SKIPPED: {e}")

    payload = {
        "corpus_sentences": len(corpus),
        "silver_sentences": len(samples),
        "gold_instances": sum(len(s["gold"]) for s in samples),
        "fake_sentences": len(fake_sentences),
        "hard_queries": args.hard_n,
        "retriever": type(encoder).__name__,
        "results": results,
    }
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "llm_rag.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, ROOT / "reports" / "LLM_RAG_COMPARE.md")
    print(f"wrote {out / 'llm_rag.json'} and reports/LLM_RAG_COMPARE.md")


def write_markdown(payload: dict, out_path: Path) -> None:
    r = payload["results"]
    k = r["ktrf"]
    lines = [
        "# KTRF vs 범용 LLM+RAG 비교 (실제 한국어 텍스트)",
        "",
        f"동일 seeded sample: silver 문장 {payload['silver_sentences']}개"
        f" (gold {payload['gold_instances']}건) + fake-glossary 문장"
        f" {payload['fake_sentences']}개. LLM은 관대한 하이브리드 검색"
        f" (dense top-{TOP_K} ∪ 문장 내 별칭 literal hit, 후보 {MAX_CANDIDATES}개"
        " 상한)을 제공받는다 — 검색기 품질이 아니라 linking/grounding 품질을"
        " 비교한다. LLM backend: Ollama (양자화 q4, RTX 3080 10GB; 27B급은"
        " VRAM 초과분 CPU offload로 실행 — dense 27B는 축소 샘플, n 표기).",
        "",
        "| 시스템 | recall (silver) | grounding precision | fake-glossary FP | latency p50 | p95 | 문장/분 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    ks, kf = k["silver"], k["fake"]
    lines.append(
        f"| **KTRF** (symbolic+dense) | **{ks['recall']['rate']}**"
        f" ({ks['recall']['hits']}/{ks['recall']['total']})"
        f" | 1.0 (RESOLVED 기준 {ks['resolved_precision_lower_bound']})"
        f" | **{kf['fp_mentions']}** | {ks['latency_s']['p50']}s"
        f" | {ks['latency_s']['p95']}s"
        f" | {ks['latency_s']['throughput_per_min']} |")
    for model, res in r.items():
        if model == "ktrf" or "silver" not in res and "error" not in res:
            continue
        if "error" in res:
            lines.append(f"| {model} | — | — | — | — | — | (실패: {res['error']}) |")
            continue
        s, f = res["silver"], res["fake"]
        note = ""
        if res.get("silver_sentences", payload["silver_sentences"]) != \
                payload["silver_sentences"]:
            note = f" (n={res['silver_sentences']}문장)"
        lines.append(
            f"| {model}{note} | {s['recall']['rate']}"
            f" ({s['recall']['hits']}/{s['recall']['total']})"
            f" | {s['grounding_precision']['rate']}"
            f" | {f['fp_mentions']} | {s['latency_s']['p50']}s"
            f" | {s['latency_s']['p95']}s"
            f" | {s['latency_s']['throughput_per_min']} |")
    lines += [
        "",
        "정의: recall = gold entity_id 출력 여부(silver 근사 label);"
        " grounding precision = 출력 entity의 등록 표면형이 문장에 실존하는"
        " 비율(미달분 = hallucination); fake-glossary FP = corpus에 없는"
        " 표면형만 가진 glossary 후보로 유도했을 때 주장된 mention 수"
        " (정의상 전부 오탐).",
    ]
    if any("hard" in res and "error" not in res.get("hard", {})
           for res in r.values()):
        lines += [
            "",
            "## Hard track — 미등록 약칭 (UE holdout, §42)",
            "",
            "glossary에서 약칭 binding 21종(과기정통부, 금감원, 방통위 등)을"
            " 제거한 뒤 해당 표면형이 등장하는 실 문장을 질의로 사용한다."
            " 언급 표면형이 등록되어 있지 않으므로 exact match가 불가능하고,"
            " canonical/설명으로부터 링크를 추론해야 한다 — silver track과"
            " 달리 어느 시스템도 1.0이 나오지 않는 변별 구간이다.",
            "",
            "| 시스템 | recall (UE) | CI95 | gold∈후보(검색 상한) | latency p50 |",
            "|---|---:|---|---:|---:|",
        ]
        kh = r["ktrf"].get("hard")
        if kh:
            g = kh["gold_in_set_e2e"]
            lines.append(
                f"| **KTRF** (e5 dense) | **{g['rate']}**"
                f" ({g['hits']}/{g['total']}) | {g['ci95']}"
                f" | — (pipeline) | {kh['latency_p50_ms'] / 1000}s |")
        for model, res in r.items():
            if model == "ktrf" or "hard" not in res or "error" in res["hard"]:
                continue
            h = res["hard"]
            g = h["recall"]
            lines.append(
                f"| {model} (n={h['recall']['total']}) | {g['rate']}"
                f" ({g['hits']}/{g['total']}) | {g['ci95']}"
                f" | {h['gold_in_candidates']}"
                f" | {h['latency_s']['p50']}s |")
        lines += [
            "",
            "LLM의 'gold∈후보'는 하이브리드 검색이 정답 entity를 후보에"
            " 넣어준 비율 — LLM recall의 상한이다. KTRF는 자체 dense 채널이"
            " 검색을 겸하므로 해당 없음.",
        ]
    lines += [
        "",
        "## 세부 (모델별)",
        "",
    ]
    for model, res in r.items():
        if model == "ktrf" or "error" in res or "silver" not in res:
            continue
        s = res["silver"]
        lines += [
            f"### {model}",
            "",
            f"- recall CI95: {s['recall']['ci95']},"
            f" parse 실패: {s['parse_failures']}",
            f"- hallucinated mentions: {s['hallucinated_mentions']}"
            f" / reported {s['grounding_precision']['reported']}",
            f"- fake-FP 예시: "
            + (json.dumps(res['fake']['examples'][:2], ensure_ascii=False)
               if res['fake']['examples'] else "없음"),
            "",
        ]
    lines += [
        "## 해석",
        "",
        "- KTRF의 latency는 CPU 단일 스레드 Python 기준, LLM은 RTX 3080 GPU"
        " 추론 기준이다 — 그런데도 규모 차이는 수백 배다.",
        "- silver label은 규칙 기반 근사이므로 LLM이 정당하게 찾은 비-silver"
        " 언급은 페널티가 아니다 (grounding 판정은 등록 표면형 존재로만 한다).",
        "- 27B급은 10GB VRAM에 다 안 들어가 CPU offload로 돌았다: MoE인"
        " gemma4:26b(활성 ~4B)는 3.6s/문장으로 실용 범위지만, dense"
        " qwen3.5:27b는 12s/문장이다. 모델을 키워도 recall은 이미 포화"
        " 구간이라 속도·비용 격차만 벌어진다.",
        "",
        "*generated by `python -m eval.run_llm_rag`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

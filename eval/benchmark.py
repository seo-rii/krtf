"""Scale benchmark (spec §53 축소판): synthetic glossaries at growing sizes.

Usage: python -m eval.benchmark

Measures compile time, conformance throughput, and resolve latency
(commit/fast) against deterministic synthetic glossaries. Reference numbers
for the Python implementation — the production Rust core (§34) is expected
to be 1-2 orders faster.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

from ktrf.conformance import generate_fixtures, run_fixtures
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

ROOT = Path(__file__).resolve().parent.parent

_PRE = ["한국", "대한", "국가", "중앙", "지역", "미래", "국제", "동부", "서부", "남부"]
_MID = ["전력", "정보", "기술", "도로", "철도", "환경", "안전", "금융", "데이터",
        "품질", "에너지", "통신", "보안", "물류", "재난"]
_SUF = ["공사", "연구원", "진흥원", "협회", "공단", "위원회", "센터", "재단"]


def synthetic_glossary(n: int, seed: int = 7) -> dict:
    rng = random.Random(seed)
    entities, families, bindings = [], [], []
    seen_names = set()
    i = 0
    while len(entities) < n:
        name = (_PRE[i % len(_PRE)] + _MID[(i // len(_PRE)) % len(_MID)]
                + _SUF[(i // (len(_PRE) * len(_MID))) % len(_SUF)])
        i += 1
        if name in seen_names:
            name = name + str(i)
        seen_names.add(name)
        eid = f"E{len(entities):05d}"
        entities.append({"entity_id": eid, "canonical": name,
                         "description": f"{name} 관련 업무를 담당하는 조직",
                         "domain_ids": [_MID[i % len(_MID)]]})
        fid_full = f"F{eid}_FULL"
        families.append({"family_id": fid_full, "representative": name,
                         "normalization_profile": "korean_org_name"})
        bindings.append({"alias_id": f"A{eid}_FULL", "family_id": fid_full,
                         "entity_id": eid, "surface": name})
        # 축약 alias (앞 두 어근의 첫 음절): 충돌 유도 -> 다의 alias
        abbr = name[0] + name[2]
        fid_ab = f"F{eid}_AB"
        families.append({"family_id": fid_ab, "representative": abbr,
                         "normalization_profile": "korean_org_name"})
        bindings.append({"alias_id": f"A{eid}_AB", "family_id": fid_ab,
                         "entity_id": eid, "surface": abbr})
        # 일부 entity에 Latin acronym (작은 알파벳 공간 -> 충돌 유도)
        if rng.random() < 0.3:
            acr = "".join(rng.choice("ABCDEFGH") for _ in range(rng.choice((2, 3))))
            fid_l = f"F{eid}_L"
            families.append({"family_id": fid_l, "representative": acr,
                             "normalization_profile": "latin_acronym"})
            bindings.append({
                "alias_id": f"A{eid}_L", "family_id": fid_l,
                "entity_id": eid, "surface": acr,
                "boundary_policy": {"left": "latin_token_boundary"},
            })
    return {"glossary_id": f"synthetic-{n}", "version": "1",
            "schema_version": "3", "entities": entities,
            "alias_families": families, "alias_bindings": bindings}


_TEMPLATES = [
    "{a}에서 발표한 자료를 검토했다.",
    "이번 조치는 {a}까지는 적용되지 않는다.",
    "{a} 담당자에게 회신 바랍니다.",
    "관련 규정은 {a}의 지침을 따른다.",
    "{a}은(는) 해당 사안과 무관하다고 밝혔다.",
]


def bench_size(n: int, run_conf: bool) -> dict:
    data = synthetic_glossary(n)
    glossary = load_glossary(data)

    t0 = time.perf_counter()
    snap = compile_snapshot(glossary, strict=False, run_conformance=False)
    compile_s = time.perf_counter() - t0

    conf_result = None
    if run_conf:
        t0 = time.perf_counter()
        fixtures = generate_fixtures(glossary)
        report = run_fixtures(snap, fixtures)
        conf_s = time.perf_counter() - t0
        conf_result = {"fixtures": report.total, "failed": report.failed,
                       "seconds": round(conf_s, 2),
                       "fixtures_per_sec": round(report.total / conf_s)}

    rng = random.Random(11)
    sentences = []
    for k in range(100):
        b = data["alias_bindings"][rng.randrange(len(data["alias_bindings"]))]
        sentences.append(_TEMPLATES[k % len(_TEMPLATES)].format(a=b["surface"]))

    lat = {}
    for mode in ("commit", "fast"):
        times = []
        for s in sentences:
            t0 = time.perf_counter()
            resolve(snap, s, mode=mode)
            times.append(time.perf_counter() - t0)
        times.sort()
        lat[mode] = {"p50_ms": round(1000 * times[50], 2),
                     "p95_ms": round(1000 * times[95], 2)}

    return {"entities": n, "bindings": len(data["alias_bindings"]),
            "compile_seconds": round(compile_s, 2),
            "conformance": conf_result, "latency": lat}


def main():
    results = [
        bench_size(100, run_conf=True),
        bench_size(500, run_conf=True),
        bench_size(2000, run_conf=False),
    ]
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "benchmark.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

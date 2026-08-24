"""Unicode fuzzing and pathological-input stress (spec §45.5, §45.6).

- seeded unicode fuzz: aliases wrapped in NFD decomposition, zero-width
  characters, fullwidth punctuation, emoji, combining marks → the resolver
  must not crash, must keep offset invariants (INV-002 asserts internally),
  and must still find catalog-covered variants;
- pathological inputs: particle-chain bombs, punctuation floods, mention-
  dense documents near the sync limit → bounded latency, degraded-not-dead.
"""

from __future__ import annotations

import random
import time
import unicodedata

from ktrf.resolver import resolve

_ZW = ["​", "‌", "‍"]
_NOISE = ["😀", "🙂", "★", "『", "』", "…", "‥", "〃", "́"]


def _mention_entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def run_unicode_fuzz(snapshot, meta, rng: random.Random,
                     n_cases: int = 200) -> dict:
    crashes = offset_failures = 0
    catalog_total = catalog_found = 0
    surfaces = sorted(meta.full_names) + sorted(meta.hangul_abbrevs)
    for i in range(n_cases):
        surface = surfaces[i % len(surfaces)]
        gold = (meta.full_names.get(surface)
                or (meta.hangul_abbrevs.get(surface) or [None])[0])
        style = i % 4
        catalog_variant = True
        if style == 0:  # NFD decomposition (T-01)
            variant = unicodedata.normalize("NFD", surface)
        elif style == 1:  # zero-width injection (T-09)
            pos = rng.randrange(1, len(surface))
            variant = surface[:pos] + rng.choice(_ZW) + surface[pos:]
        elif style == 2:  # noise wrapping (boundary chars, out of span)
            variant = surface
        else:  # random noise inside → out of catalog, only crash-checked
            pos = rng.randrange(1, len(surface))
            variant = surface[:pos] + rng.choice(_NOISE) + surface[pos:]
            catalog_variant = False
        pre = rng.choice(_NOISE) + " " if style == 2 else ""
        post = " " + rng.choice(_NOISE) if style == 2 else ""
        text = f"{pre}{variant}{post} 관련 검토 의견입니다."
        try:
            resp = resolve(snapshot, text, mode="commit",
                           options={"return_all_mentions": True,
                                    "max_prediction_set": 50})
        except AssertionError:
            offset_failures += 1
            continue
        except Exception:
            crashes += 1
            continue
        if catalog_variant and gold:
            catalog_total += 1
            start = text.index(variant)
            end = start + len(variant)
            if any(s < end and start < e and gold in _mention_entities(m)
                   for m in resp["mentions"]
                   for s, e in [(m["span"]["codepoint"]["start"],
                                 m["span"]["codepoint"]["end"])]):
                catalog_found += 1
    return {
        "name": "unicode_fuzz",
        "cases": n_cases,
        "crashes": crashes,
        "offset_invariant_failures": offset_failures,
        "catalog_variant_recall": round(catalog_found / catalog_total, 4)
        if catalog_total else None,
        "catalog_variants": catalog_total,
        "interpretation": "crashes/offset failures must be 0; NFD/zero-width "
                          "variants are catalog transforms and must be recalled",
    }


def run_pathological(snapshot, meta) -> dict:
    abbrev = sorted(meta.hangul_abbrevs)[0]
    full = sorted(meta.full_names)[0]
    cases = {
        "particle_bomb": abbrev + "에서" * 60,
        "punct_flood": ".".join(abbrev) + "." * 200,
        "zero_width_flood": "​".join(full) + "​" * 100,
        "repeat_alias_flood": (abbrev + " ") * 500,
    }
    # mention-dense document near the 64KB sync limit
    sentence = f"{full}에서도 {abbrev} 관련 회의를 진행했다. "
    dense = sentence * (60000 // len(sentence.encode("utf-8")))
    cases["near_limit_document"] = dense

    results = {}
    for name, text in cases.items():
        t0 = time.perf_counter()
        try:
            resp = resolve(snapshot, text, mode="commit",
                           options={"return_all_mentions": True})
            elapsed = time.perf_counter() - t0
            results[name] = {
                "ms": round(1000 * elapsed, 1),
                "mentions": len(resp["mentions"]),
                "degraded": resp["degraded"],
                "crashed": False,
            }
        except Exception as e:
            results[name] = {"crashed": True, "error": type(e).__name__}
    return {"name": "pathological", "cases": results,
            "interpretation": "no crashes; bounded latency; truncation "
                              "surfaces as degraded=true (INV-013)"}

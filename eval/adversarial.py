"""Adversarial benchmark suites (anti-overfitting evaluation).

The conformance suite and datagen derive from the same §14.7/§16 catalogs as
the implementation, so they can't reveal memorized behavior. These suites are
generated *independently*:

- **boundary traps**: alias embedded in longer words (대한전선-style) — the
  Level A boundary guarantee says these must never surface the entity at the
  embedded span;
- **composed transforms**: stacks of catalog transforms (width+case+spacing+
  prefix+particle chain) that conformance never combines;
- **out-of-catalog tails**: unregistered suffixes — spec behavior is *keep
  the core at low confidence, don't commit blindly* (§16.5), reported as
  retention vs overcommit;
- **negative corpus**: term-free sentences → false positives per 1k chars;
- **fuzzy distractors**: near-miss sibling full names typed with 1-jamo
  errors of *the other* sibling — measures fuzzy channel confusion;
- **commit discipline on multi-sense aliases at scale**.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ktrf.hangul import CHOSEONG, compose_syllable, decompose_syllable
from ktrf.resolver import resolve

from .synthetic import SynthMeta

_TRAP_SYLLABLES = list("가나다라마바사자차카타파하도무배소온")
_OOC_TAILS = ["스럽게", "같은", "다운", "쪽으로의", "류의"]  # not in any catalog
_NEG_TEMPLATES = [
    "오늘 {a}에 관한 {b}가 예정되어 있다.",
    "{a}는 지난주 {b}보다 훨씬 나아졌다.",
    "담당자가 {a}와 {b}를 함께 검토하기로 했다.",
    "이번 분기 {a} 결과는 {b}에 정리되어 있다.",
    "{a}를 마치고 나서 {b}를 시작할 예정이다.",
]
_NEG_WORDS = ["회의", "보고서", "일정", "점심시간", "휴가철", "출장길",
              "발표자료", "예산안", "간담회", "워크숍", "설문조사", "교육과정",
              "채용공고", "성과급", "야근", "회식자리", "주차장", "구내식당"]


@dataclass
class SuiteResult:
    name: str
    total: int = 0
    hits: int = 0  # meaning depends on suite; see `interpretation`
    interpretation: str = ""
    details: list = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "total": self.total, "hits": self.hits,
                "rate": round(self.rate, 4),
                "interpretation": self.interpretation,
                "details": self.details[:8]}


def _mention_entities(m: dict) -> set[str]:
    ids = {x.get("entity_id") for x in
           m.get("prediction_set", {}).get("members", [])
           if x.get("kind", "ENTITY") == "ENTITY"}
    if "resolved_entity" in m:
        ids.add(m["resolved_entity"]["entity_id"])
    return ids - {None}


def _cp(m: dict) -> tuple[int, int]:
    cp = m["span"]["codepoint"]
    return (cp["start"], cp["end"])


# ---------------------------------------------------------------------------
# 1. boundary traps — MUST be 0 (hard Level A guarantee)
# ---------------------------------------------------------------------------


def run_boundary_traps(snapshot, meta: SynthMeta, rng: random.Random,
                       max_aliases: int = 120) -> SuiteResult:
    res = SuiteResult(
        "boundary_traps", interpretation="hits = guarantee violations (must be 0)")
    abbrevs = sorted(meta.hangul_abbrevs)
    rng.shuffle(abbrevs)
    for abbrev in abbrevs[:max_aliases]:
        gold = set(meta.hangul_abbrevs[abbrev])
        # left-attach: 도한전, 소한전 ... (prev char hangul, not a prefix modifier)
        for syl in rng.sample(_TRAP_SYLLABLES, 3):
            trap_word = syl + abbrev + rng.choice(_TRAP_SYLLABLES)
            text = f"{trap_word} 관련 논의가 있었다."
            res.total += 1
            resp = resolve(snapshot, text, mode="aggressive",
                           options={"return_all_mentions": True})
            trap_start = 1  # abbrev position inside trap_word
            for m in resp["mentions"]:
                s, e = _cp(m)
                if (s, e) == (trap_start, trap_start + len(abbrev)) \
                        and _mention_entities(m) & gold:
                    res.hits += 1
                    res.details.append({"text": text, "surface": m["surface"]})
                    break
    acronyms = sorted(meta.acronyms)
    rng.shuffle(acronyms)
    for acr in acronyms[:max_aliases]:
        gold = set(meta.acronyms[acr])
        for wrap in (f"X{acr}", f"{acr}XR", f"V{acr}W"):
            text = f"{wrap} 지표를 검토했다."
            res.total += 1
            resp = resolve(snapshot, text, mode="aggressive",
                           options={"return_all_mentions": True})
            inner = wrap.index(acr)
            for m in resp["mentions"]:
                s, e = _cp(m)
                if (s, e) == (inner, inner + len(acr)) \
                        and _mention_entities(m) & gold:
                    res.hits += 1
                    res.details.append({"text": text, "surface": m["surface"]})
                    break
    return res


# ---------------------------------------------------------------------------
# 2. composed transforms — recall on stacked catalog variants
# ---------------------------------------------------------------------------


def run_composed_transforms(snapshot, meta: SynthMeta, rng: random.Random,
                            max_cases: int = 150) -> SuiteResult:
    res = SuiteResult(
        "composed_transforms",
        interpretation="hits = gold in prediction set (E2E recall; higher is better)")
    chains = ["에서도", "까지는", "만이라도", "으로부터", "과의"]
    prefixes = ["구 ", "전 ", "구", "현 "]
    names = sorted(meta.full_names)
    rng.shuffle(names)
    for name in names:
        if res.total >= max_cases:
            break
        eid = meta.full_names[name]
        # stack: prefix + internal space + particle chain
        mid = len(name) // 2
        spaced = name[:mid] + " " + name[mid:]
        pfx = rng.choice(prefixes)
        chain = rng.choice(chains)
        variant = f"{pfx}{spaced}{chain}"
        text = f"해당 안건은 {variant} 이관되었다."
        res.total += 1
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        start = text.index(spaced)
        span = (start, start + len(spaced))
        ok = any(
            s < span[1] and span[0] < e and eid in _mention_entities(m)
            for m in resp["mentions"] for s, e in [_cp(m)]
        )
        res.hits += int(ok)
        if not ok:
            res.details.append({"text": text, "gold": eid})
    # Latin acronyms: fullwidth + lowercase + dots + particle chain
    acronyms = sorted(meta.acronyms)
    rng.shuffle(acronyms)
    for acr in acronyms[: max(0, max_cases - res.total)]:
        gold = set(meta.acronyms[acr])
        style = rng.choice(range(3))
        if style == 0:
            variant = "".join(chr(ord(c) + 0xFEE0) for c in acr.lower())
        elif style == 1:
            variant = ".".join(acr) + "."
        else:
            variant = acr.lower()
        chain = rng.choice(chains)
        text = f"보고서는 {variant}{chain} 공유되었다."
        res.total += 1
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        start = text.index(variant)
        ok = any(
            s < start + len(variant) and start < e
            and _mention_entities(m) & gold
            for m in resp["mentions"] for s, e in [_cp(m)]
        )
        res.hits += int(ok)
        if not ok:
            res.details.append({"text": text, "gold": sorted(gold)})
    return res


# ---------------------------------------------------------------------------
# 3. out-of-catalog tails — retention (diagnostic) + overcommit (gate)
# ---------------------------------------------------------------------------


def run_ooc_tails(snapshot, meta: SynthMeta, rng: random.Random,
                  max_cases: int = 100) -> tuple[SuiteResult, SuiteResult]:
    retention = SuiteResult(
        "ooc_tail_retention",
        interpretation="hits = core kept in candidates (§16.5; diagnostic)")
    overcommit = SuiteResult(
        "ooc_tail_overcommit",
        interpretation="hits = RESOLVED commits on unknown-tail spans (lower is better)")
    abbrevs = sorted(a for a in meta.hangul_abbrevs)
    rng.shuffle(abbrevs)
    for abbrev in abbrevs[:max_cases]:
        gold = set(meta.hangul_abbrevs[abbrev])
        tail = rng.choice(_OOC_TAILS)
        text = f"{abbrev}{tail} 행동은 자제해야 한다."
        retention.total += 1
        overcommit.total += 1
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        kept = committed = False
        for m in resp["mentions"]:
            s, e = _cp(m)
            if (s, e) == (0, len(abbrev)) and _mention_entities(m) & gold:
                kept = True
                if m.get("link_decision") == "RESOLVED":
                    committed = True
        retention.hits += int(kept)
        overcommit.hits += int(committed)
        if committed:
            overcommit.details.append({"text": text})
    return retention, overcommit


# ---------------------------------------------------------------------------
# 4. negative corpus — false positives per 1k chars
# ---------------------------------------------------------------------------


def run_negative_corpus(snapshot, meta: SynthMeta, rng: random.Random,
                        n_sentences: int = 200) -> dict:
    total_chars = 0
    resolved = candidates = sentences = 0
    for i in range(n_sentences * 2):
        if sentences >= n_sentences:
            break
        a = _NEG_WORDS[i % len(_NEG_WORDS)]
        b = rng.choice(_NEG_WORDS)
        text = _NEG_TEMPLATES[i % len(_NEG_TEMPLATES)].format(a=a, b=b)
        if any(s in text for s in meta.all_surfaces):
            continue  # keep the corpus genuinely term-free
        sentences += 1
        total_chars += len(text)
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True})
        for m in resp["mentions"]:
            candidates += 1
            if m.get("link_decision") == "RESOLVED":
                resolved += 1
    return {
        "name": "negative_corpus",
        "sentences": sentences,
        "chars": total_chars,
        "resolved_fp_per_1k_chars": round(1000 * resolved / total_chars, 3),
        "candidate_mentions_per_1k_chars": round(1000 * candidates / total_chars, 3),
        "interpretation": "commit-mode false positives on term-free text (lower is better)",
    }


# ---------------------------------------------------------------------------
# 5. fuzzy distractors — sibling confusion under 1-jamo typos
# ---------------------------------------------------------------------------


def _typo_variants(name: str, rng: random.Random) -> list[str]:
    out = []
    idxs = [i for i, c in enumerate(name) if decompose_syllable(c)]
    rng.shuffle(idxs)
    for i in idxs[:2]:
        cho, jung, jong = decompose_syllable(name[i])
        alt = CHOSEONG[(CHOSEONG.index(cho) + rng.choice((1, 2)))
                       % len(CHOSEONG)]
        out.append(name[:i] + compose_syllable(alt, jung, jong) + name[i + 1:])
    return out


def run_fuzzy_distractors(snapshot, meta: SynthMeta, rng: random.Random,
                          max_pairs: int = 60) -> dict:
    """Typos of sibling A must recover A (recall) and not commit to B
    (confusion)."""
    recovered = confused = committed_wrong = total = 0
    pairs = list(meta.near_miss_pairs)
    rng.shuffle(pairs)
    for name_a, name_b in pairs[:max_pairs]:
        gold = meta.full_names[name_a]
        sibling = meta.full_names[name_b]
        for typo in _typo_variants(name_a, rng)[:1]:
            if typo in meta.all_surfaces:
                continue
            total += 1
            text = f"{typo} 명의의 공문이 접수되었다."
            resp = resolve(snapshot, text, mode="commit",
                           options={"return_all_mentions": True,
                                    "max_prediction_set": 50})
            span = (0, len(typo))
            got_gold = got_sib = False
            for m in resp["mentions"]:
                s, e = _cp(m)
                if s < span[1] and span[0] < e:
                    ids = _mention_entities(m)
                    got_gold |= gold in ids
                    got_sib |= sibling in ids
                    if m.get("link_decision") == "RESOLVED" and \
                            m.get("resolved_entity", {}).get("entity_id") == sibling:
                        committed_wrong += 1
            recovered += int(got_gold)
            confused += int(got_sib and not got_gold)
    return {
        "name": "fuzzy_distractors",
        "total": total,
        "recovered_rate": round(recovered / total, 4) if total else None,
        "sibling_only_rate": round(confused / total, 4) if total else None,
        "wrong_sibling_commits": committed_wrong,
        "interpretation": "1-jamo typos of near-miss pairs: recover gold (higher), "
                          "never RESOLVED-commit the sibling (must be 0)",
    }


# ---------------------------------------------------------------------------
# 6. multi-sense commit discipline at scale
# ---------------------------------------------------------------------------


def run_multisense_discipline(snapshot, meta: SynthMeta, rng: random.Random,
                              max_aliases: int = 80) -> dict:
    """Context-free multi-sense mentions must stay AMBIGUOUS with every
    sense preserved (INV-004), never arbitrary top-1 commits."""
    total = wrong_commits = missing_sense = 0
    multi = [(a, e) for a, e in meta.hangul_abbrevs.items() if len(e) > 1]
    multi += [(a, e) for a, e in meta.acronyms.items() if len(e) > 1]
    rng.shuffle(multi)
    for alias, entity_ids in multi[:max_aliases]:
        text = f"{alias} 관련 사항을 확인해 주세요."
        total += 1
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 100})
        span = (0, len(alias))
        m = next((x for x in resp["mentions"] if _cp(x) == span), None)
        if m is None:
            missing_sense += 1
            continue
        ids = _mention_entities(m)
        if not set(entity_ids) <= ids:
            missing_sense += 1
        if m.get("link_decision") == "RESOLVED":
            wrong_commits += 1
    return {
        "name": "multisense_discipline",
        "total": total,
        "arbitrary_commits": wrong_commits,
        "sense_loss": missing_sense,
        "interpretation": "context-free multi-sense aliases: commits and sense "
                          "loss must both be 0 (INV-004, §4.6)",
    }

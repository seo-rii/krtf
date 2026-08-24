"""Fuzzy surface recovery (spec §17): Jamo channel + keyboard channel.

Level B statistical path — never part of the Level A catalog guarantee
(§17.1) and never allowed to displace exact results (INV-010; enforced in
candidates.py).

Two-stage retrieval (§17.3): jamo n-gram inverted index -> shortlist ->
weighted Damerau-Levenshtein verification with the §17.2 cost table.
The minimum-cost single-application principle (REQ-FUZ-001) holds because
every atomic operation is charged min() over the applicable rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from .glossary import AliasBinding, Glossary
from .hangul import (
    hangul_to_keys,
    is_compat_jamo,
    is_syllable,
    jamo_keys_adjacent,
    keys_to_hangul,
    to_jamo_seq,
)
from .normalization import normalize_alias

# §17.2 initial cost config (not normative constants)
COST_SPACE = 0.05
COST_PUNCT = 0.05
COST_ADJACENT_KEY = 0.20
COST_JONG_INDEL = 0.25
COST_TRANSPOSE = 0.30
COST_CV_SUBST = 0.70  # 초성/중성 치환 (일반)
COST_OTHER_SUBST = 1.00
COST_VOWEL_INDEL = 0.50
KEYBOARD_MODE_COST = 0.30  # english/hangul input-mode conversion

_CONSONANTS = set("ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_VOWELS = set("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")


def _indel_cost(ch: str) -> float:
    if ch.isspace():
        return COST_SPACE
    if ch in ".-·":
        return COST_PUNCT
    if ch in _CONSONANTS:
        return COST_JONG_INDEL
    if ch in _VOWELS:
        return COST_VOWEL_INDEL
    return COST_OTHER_SUBST


def _subst_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    costs = [COST_OTHER_SUBST]
    if jamo_keys_adjacent(a, b):
        costs.append(COST_ADJACENT_KEY)
    if (a in _CONSONANTS and b in _CONSONANTS) or (a in _VOWELS and b in _VOWELS):
        costs.append(COST_CV_SUBST)
    # REQ-FUZ-001: cheapest (most specific) applicable rule only
    return min(costs)


def weighted_edit_distance(a: str, b: str, cutoff: float = 2.0) -> float:
    """Weighted Damerau-Levenshtein over jamo sequences."""
    la, lb = len(a), len(b)
    INF = float("inf")
    prev2: list[float] = []
    prev = [0.0]
    for j in range(1, lb + 1):
        prev.append(prev[j - 1] + _indel_cost(b[j - 1]))
    for i in range(1, la + 1):
        cur = [prev[0] + _indel_cost(a[i - 1])]
        best_row = cur[0]
        for j in range(1, lb + 1):
            c = min(
                prev[j] + _indel_cost(a[i - 1]),
                cur[j - 1] + _indel_cost(b[j - 1]),
                prev[j - 1] + _subst_cost(a[i - 1], b[j - 1]),
            )
            if (
                i > 1 and j > 1
                and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]
                and a[i - 1] != a[i - 2]
            ):
                c = min(c, prev2[j - 2] + COST_TRANSPOSE)
            cur.append(c)
            best_row = min(best_row, c)
        if best_row > cutoff:
            return INF
        prev2, prev = prev, cur
    return prev[lb]


def _ngrams(s: str, n: int = 2) -> set[str]:
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


@dataclass
class FuzzyCandidate:
    binding: AliasBinding
    span: tuple[int, int]  # raw codepoint span of the query window
    surface: str
    cost: float
    channel: str  # "jamo" | "keyboard"


def _default_max_cost(key_len_jamo: int, syllable_len: int) -> float | None:
    """§10.6 length-based default fuzzy policy. None = fuzzy disabled."""
    if syllable_len <= 2:
        return None  # 1-2 chars: generic edit fuzzy off (REQ-FUZ-002)
    if syllable_len <= 4:
        return 0.35  # very low edit cost only
    return min(1.2, 0.25 + 0.06 * key_len_jamo)  # length-normalized


class FuzzyIndex:
    def __init__(self, glossary: Glossary, shortlist_size: int = 32):
        self.glossary = glossary
        self.shortlist_size = shortlist_size
        self._entries: list[dict] = []
        self._ngram_index: dict[str, list[int]] = {}
        self._keyboard_latin: dict[str, list[AliasBinding]] = {}
        self._keyboard_hangul: dict[str, list[AliasBinding]] = {}
        for b in glossary.alias_bindings:
            prof = glossary.binding_profile(b)
            key = normalize_alias(b.surface, prof)
            if not key:
                continue
            jamo = to_jamo_seq(key)
            syl_len = len(key)
            max_cost = (
                b.fuzzy_policy.max_edit_cost
                if b.fuzzy_policy.max_edit_cost is not None
                else _default_max_cost(len(jamo), syl_len)
            )
            if b.fuzzy_policy.enabled is False:
                max_cost = None
            entry_id = len(self._entries)
            self._entries.append(
                {"binding": b, "key": key, "jamo": jamo, "max_cost": max_cost}
            )
            if max_cost is not None:
                for g in _ngrams(jamo):
                    self._ngram_index.setdefault(g, []).append(entry_id)
            # keyboard channel maps (§17.4); allowed even for short aliases
            if b.fuzzy_policy.keyboard_recovery:
                if any(is_syllable(c) or is_compat_jamo(c) for c in key):
                    self._keyboard_latin.setdefault(
                        hangul_to_keys(key), []).append(b)
                elif key.isascii():
                    self._keyboard_hangul.setdefault(key, []).append(b)

    # -- jamo channel -------------------------------------------------------

    def query_jamo(self, window: str, span: tuple[int, int],
                   max_results: int = 8) -> list[FuzzyCandidate]:
        qjamo = to_jamo_seq(window)
        counts: dict[int, int] = {}
        for g in _ngrams(qjamo):
            for eid in self._ngram_index.get(g, ()):
                counts[eid] = counts.get(eid, 0) + 1
        shortlist = sorted(counts, key=counts.get, reverse=True)[: self.shortlist_size]
        out: list[FuzzyCandidate] = []
        for eid in shortlist:
            e = self._entries[eid]
            cutoff = e["max_cost"]
            d = weighted_edit_distance(qjamo, e["jamo"], cutoff=cutoff + 0.01)
            if d <= cutoff:
                out.append(FuzzyCandidate(e["binding"], span, window, d, "jamo"))
        out.sort(key=lambda c: c.cost)
        return out[:max_results]

    # -- keyboard channel ---------------------------------------------------

    def query_keyboard(self, token: str, span: tuple[int, int]) -> list[FuzzyCandidate]:
        out: list[FuzzyCandidate] = []
        if token.isascii() and token.isalpha():
            # english input mode: gkswjs -> 한전
            for b in self._keyboard_latin.get(token.lower(), ()):
                out.append(FuzzyCandidate(b, span, token, KEYBOARD_MODE_COST, "keyboard"))
        elif any(is_syllable(c) or is_compat_jamo(c) for c in token):
            # hangul input mode of a Latin alias: 븐 -> qms 계열
            keys = hangul_to_keys(token)
            for b in self._keyboard_hangul.get(keys, ()):
                out.append(FuzzyCandidate(b, span, token, KEYBOARD_MODE_COST, "keyboard"))
        return out

"""Abbreviation alignment channel (spec §21.7) — Pass 2 only.

Aligns unresolved Hangul tokens against entity canonicals as subsequences
(과기정통부 -> 과학기술정보통신부) and Latin acronyms against word initials.
Deterministic, but a Level B statistical channel: no catalog guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass

from .glossary import Glossary
from .hangul import is_syllable


@dataclass
class AbbrevCandidate:
    entity_id: str
    span: tuple[int, int]
    surface: str
    score: float  # 0..1 alignment quality
    channel: str = "abbrev"


def _subsequence_positions(short: str, long: str) -> list[int] | None:
    pos: list[int] = []
    j = 0
    for ch in short:
        while j < len(long) and long[j] != ch:
            j += 1
        if j >= len(long):
            return None
        pos.append(j)
        j += 1
    return pos


class AbbrevAligner:
    def __init__(self, glossary: Glossary):
        self.entries = []
        for e in glossary.entities:
            canonical = e.canonical
            self.entries.append((e.entity_id, canonical, canonical.split()))

    def align_token(self, token: str, span: tuple[int, int],
                    max_results: int = 5) -> list[AbbrevCandidate]:
        out: list[AbbrevCandidate] = []
        if len(token) < 2:
            return out
        if all(is_syllable(c) for c in token):
            out.extend(self._align_hangul(token, span))
        elif token.isascii() and token.isalpha():
            out.extend(self._align_latin_acronym(token, span))
        out.sort(key=lambda c: -c.score)
        return out[:max_results]

    def _align_hangul(self, token: str, span) -> list[AbbrevCandidate]:
        out = []
        for entity_id, canonical, _ in self.entries:
            compact = canonical.replace(" ", "")
            if len(compact) <= len(token) or not all(
                is_syllable(c) for c in compact
            ):
                continue
            pos = _subsequence_positions(token, compact)
            if pos is None:
                continue
            score = len(token) / len(compact)  # coverage
            if token[0] == compact[0]:
                score += 0.25
            if token[-1] == compact[-1]:
                score += 0.25
            # word-initial syllable bonus (어절 첫 음절 조합)
            word_starts = {0}
            acc = 0
            for w in canonical.split():
                word_starts.add(acc)
                acc += len(w)
            score += 0.1 * sum(1 for p in pos if p in word_starts) / len(pos)
            if score >= 0.55:
                out.append(AbbrevCandidate(entity_id, span, token, min(score, 1.0)))
        return out

    def _align_latin_acronym(self, token: str, span) -> list[AbbrevCandidate]:
        out = []
        upper = token.upper()
        for entity_id, canonical, words in self.entries:
            if len(words) < 2:
                continue
            initials = "".join(w[0] for w in words if w).upper()
            if initials == upper:
                out.append(AbbrevCandidate(entity_id, span, token, 0.9))
        return out

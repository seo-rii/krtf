"""Abbreviation alignment channel (spec §21.7) — Pass 2 only.

Aligns unresolved tokens against registered surfaces as subsequences
(과기정통부 -> 과학기술정보통신부) and Latin acronyms against word initials.
Deterministic, but a Level B statistical channel: no catalog guarantee, and
an aligned candidate never carries commit authority of its own — the guard
in :mod:`ktrf.segmentation` judges it like any other Level B evidence.

Three things changed in M3 (VARIANTS_PLAN):

**The index.** Every token used to be compared against every entity. An
abbreviation is a *subsequence* of the name, so its first character has to
appear somewhere in the name — index every character of every target and
look up the token's first one. That is a cheap necessary condition, which is
all a signature may ever be.

The obvious sharper key, "starts with the name's first syllable", is wrong
for Korean and cost 3pp of unseen-abbreviation recall before the neural
track caught it: `고용노동부` abbreviates to `노동부` and `보건복지부` to
`복지부`, dropping the leading morpheme entirely. A signature that is merely
*usually* true is a recall bug wearing a performance costume.

**The alignment targets.** The aligner read ``entity.canonical`` only, so a
tenant that registered `한국전력` as a second name got no abbreviation
coverage from it. Registered ``name``-kind bindings are aligned too, and the
signature that matched is reported so provenance can say which surface the
abbreviation was read against.

**Mixed script.** `SK하닉` is neither all-Hangul nor all-Latin, so it fell
between the two branches and matched nothing. Subsequence alignment does not
care about script; only the two entry points did.

``resolve`` reaches this now: :func:`ktrf.resolver._abbrev_tokens` offers the
mixed run alongside the script runs, for this channel only. What is still
*not* handled is the same wrong premise one layer up — a Hangul→Latin
transition is treated as a clean token boundary by the matcher, so `한전KDN`
reports a bare `한전` with no wider surface at all. That lives in Level A
boundary policy with conformance fixtures behind it and needs its own
measurement cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .glossary import Glossary
from .hangul import is_syllable

# §21.7 signature kinds. Each maps a *surface* to a key, and a token that
# could abbreviate that surface produces the same key. They are filters:
# a signature miss removes an entity from the shortlist, a signature hit
# proves nothing on its own and still has to pass subsequence alignment.
SIGNATURES: tuple[str, ...] = ("contains_first", "first_last",
                              "type_terminal")

# 기관 유형 종결 signature (REVIEW_3 §4.7). An abbreviation almost always
# keeps the type ending it inherited: 과기정통부 from 과학기술정보통신부,
# 공정위 from 공정거래위원회.
TYPE_TERMINALS: tuple[str, ...] = (
    "위원회", "본부", "공사", "공단", "은행", "연구원", "진흥원",
    "부", "처", "청", "원", "국", "실", "회", "단", "소",
)

MIN_TOKEN = 2
# REVIEW_3 §4.6: short Latin acronyms get almost no fuzzy latitude. Two
# letters carry so little information that subsequence alignment will find
# them inside almost any longer name, and the result is a *shorter* mention
# competing with the right one: `KB S` (a spaced `KBS`) started reporting a
# mention at `KB` once alignment stopped being script-specific. The variant
# suite caught this as a jump in `core_span_wrong` on the `spaced` formation.
MIN_LATIN_TOKEN = 3


@dataclass
class AbbrevCandidate:
    entity_id: str
    span: tuple[int, int]
    surface: str
    score: float  # 0..1 alignment quality
    channel: str = "abbrev"
    # which registered surface the token was aligned against, and how it was
    # shortlisted — provenance for §21.7, not an input to any decision
    target: str = ""
    signature: str = ""


@dataclass
class _Entry:
    entity_id: str
    surface: str      # the registered surface, as written
    compact: str      # spaces removed — what alignment runs over
    words: list[str]
    word_starts: frozenset[int] = field(default_factory=frozenset)


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


def _type_terminal(s: str) -> str:
    """The longest institutional ending ``s`` carries, or ""."""
    for t in TYPE_TERMINALS:
        if len(s) > len(t) and s.endswith(t):
            return t
    return ""


class AbbrevAligner:
    """A compiled signature index over every registered name-bearing surface."""

    def __init__(self, glossary: Glossary):
        self.entries: list[_Entry] = []
        seen: set[tuple[str, str]] = set()

        def add(entity_id: str, surface: str) -> None:
            key = (entity_id, surface)
            if not surface or key in seen:
                return
            seen.add(key)
            words = surface.split()
            starts, acc = {0}, 0
            for w in words:
                starts.add(acc)
                acc += len(w)
            self.entries.append(_Entry(entity_id, surface,
                                       surface.replace(" ", ""), words,
                                       frozenset(starts)))

        for e in glossary.entities:
            add(e.entity_id, e.canonical)
        # a registered long *name* is as good an alignment target as the
        # canonical; abbreviations are coined from whatever people write
        for b in glossary.alias_bindings:
            if b.kind == "name":
                add(b.entity_id, b.surface)

        # character-occurrence shortlist: an entry is reachable from every
        # character it contains, because a subsequence match needs the
        # token's first character to appear *somewhere*. Case-folded so a
        # Latin token and a Latin name meet in the same bucket.
        self._by_char: dict[str, list[_Entry]] = {}
        for entry in self.entries:
            for ch in dict.fromkeys(entry.compact.lower()):
                self._by_char.setdefault(ch, []).append(entry)

    def signature_stats(self) -> dict:
        """Index shape, for the snapshot manifest and for eval reports."""
        buckets = {k: len(v) for k, v in self._by_char.items()}
        return {"entries": len(self.entries), "buckets": len(buckets),
                "largest_bucket": max(buckets.values(), default=0),
                "signatures": list(SIGNATURES)}

    def align_token(self, token: str, span: tuple[int, int],
                    max_results: int = 5) -> list[AbbrevCandidate]:
        if len(token) < MIN_TOKEN:
            return []
        out = self._align_subsequence(token, span)
        if token.isascii() and token.isalpha():
            out.extend(self._align_latin_acronym(token, span))
        # one candidate per entity: the best-scoring target wins, so a tenant
        # that registers three spellings of a name does not get three votes
        best: dict[str, AbbrevCandidate] = {}
        for c in out:
            if c.entity_id not in best or c.score > best[c.entity_id].score:
                best[c.entity_id] = c
        ranked = sorted(best.values(), key=lambda c: (-c.score, c.entity_id))
        return ranked[:max_results]

    def _align_subsequence(self, token: str, span) -> list[AbbrevCandidate]:
        """Score ``token`` as a subsequence of any shortlisted surface.

        Script-agnostic on purpose: `SK하닉` is a subsequence of `SK하이닉스`
        and nothing about that reasoning needs the two to share an alphabet.
        """
        out: list[AbbrevCandidate] = []
        if token.isascii() and len(token) < MIN_LATIN_TOKEN:
            return out
        token_terminal = _type_terminal(token)
        for entry in self._by_char.get(token[:1].lower(), ()):
            compact = entry.compact
            if len(compact) <= len(token):
                continue
            pos = _subsequence_positions(token, compact)
            if pos is None:
                continue
            score = len(token) / len(compact)  # coverage
            sig = "contains_first"
            if token[-1] == compact[-1]:
                score += 0.25
                sig = "first_last"
            terminal = _type_terminal(compact)
            if terminal and terminal == token_terminal:
                # the whole institutional ending survived, not just its last
                # syllable — a stronger signal than either bonus alone
                score += 0.10
                sig = "type_terminal"
            if token[0] == compact[0]:
                score += 0.25
            score += 0.1 * sum(1 for p in pos if p in entry.word_starts) / len(pos)
            if score >= 0.55:
                out.append(AbbrevCandidate(entry.entity_id, span, token,
                                           min(score, 1.0),
                                           target=entry.surface, signature=sig))
        return out

    def _align_latin_acronym(self, token: str, span) -> list[AbbrevCandidate]:
        out = []
        upper = token.upper()
        for entry in self.entries:
            if len(entry.words) < 2:
                continue
            initials = "".join(w[0] for w in entry.words if w).upper()
            if initials == upper:
                out.append(AbbrevCandidate(entry.entity_id, span, token, 0.9,
                                           target=entry.surface,
                                           signature="latin_initials"))
        return out

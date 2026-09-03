"""Document-local alias detection (spec §18) and in-document definitions (M6).

Detects in-document definitions such as:

    한국과학기술연구원(KIST)
    한국과학기술연구원, 이하 KIST
    KIST(한국과학기술연구원)
    한국과학기술연구원(이하 "연구원")

Local aliases live only in the request scope (INV-008/REQ-LOC-002), can only
*add* candidates — never remove or overwrite global bindings (INV-009 /
REQ-LOC-001; enforced in candidates.py by union semantics).

Two things changed in M6 (VARIANTS_PLAN).

**이하 has to open an 어절.** ``_PAT_IHA`` matched the two syllables anywhere,
so `용이하게`, `맞이하게` and `같이하여` were read as definitions — the long
form ending at `용`, the alias being `게`. Three fifths of everything that
pattern fired on in the wild corpus was a word cut in half.

**A definition of an unregistered name is no longer discarded.**
:meth:`DocLocalDetector.extract` only ever produced a binding when the long
form already resolved to a registered entity, and that gate is anti-correlated
with the reason documents write definitions at all: a text writes `X(Y)`
precisely to introduce a name the reader does not have. Measured over the
114,605-sentence corpus the module produced **zero** bindings — it can only
fire where it adds nothing. :meth:`extract_new_terms` reports those pairs
instead, as :class:`NewTermDefinition` records for
:mod:`ktrf.registry.proposals`; the resolver is not involved and its behaviour
is unchanged, because an unregistered name has no entity to bind to yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .abbrev import TYPE_TERMINALS, _subsequence_positions
from .matcher import ExactIndex
from .normalization import build_canonical_stream

_NAME = r"[가-힣A-Za-z0-9·\- ]{2,40}"
_SHORT = r"[가-힣A-Za-z0-9·\-]{1,20}"

# X(Y) / X(이하 "Y") / X, 이하 Y
_PAT_PAREN = re.compile(rf"({_NAME})\(\s*(?:이하\s*)?[\"'“”]?({_SHORT})[\"'“”]?\s*\)")
# `이하` must open its own 어절: 용/이하/게 is one word, not a definition.
_PAT_IHA = re.compile(
    rf"({_NAME})[,，]?\s+이하\s+[\"'“”]?({_SHORT})[\"'“”]?")

MIN_ABBREV_CHARS = 2


@dataclass
class DocLocalBinding:
    alias_surface: str
    entity_ids: list[str]
    definition_span: tuple[int, int]  # raw codepoint span of the definition
    long_form: str
    trust_level: str = "UNTRUSTED_DOCUMENT"


@dataclass
class DocLocalOccurrence:
    binding: DocLocalBinding
    span: tuple[int, int]
    surface: str


@dataclass(frozen=True)
class NewTermDefinition:
    """A name the document defines and the glossary does not hold.

    The contrast with :mod:`ktrf.mining` is the point of this record. A mined
    residual knows a name *exists* and nothing else, so its canonical has to
    come from a reviewer. A definition pattern is the document stating the
    canonical itself — that is what makes it a definition — so
    :attr:`canonical` is evidence rather than a guess.

    What the document does **not** say is what the thing *is*. A definition
    gives a name, not a meaning, so ``short_definition`` still has to come
    from a reviewer and :meth:`to_proposal` refuses to invent one.
    """

    surface: str                        # what the rest of the document uses
    canonical: str                      # the name the document supplies
    definition_span: tuple[int, int]    # raw codepoint span of the definition
    aligned_positions: tuple[int, ...]  # characters that carried the alignment
    pattern: str                        # "paren" | "iha"

    def to_proposal(self, *, short_definition: str, entry_id: str,
                    requested_scope: str = "project") -> dict:
        """Keyword arguments for :meth:`TermProposalStore.submit`.

        ``requested_scope`` defaults to ``project`` rather than ``session``
        deliberately. :func:`ktrf.registry.proposals.decide_admission` counts
        ``document_definition`` as an *explicit* origin, so a session-scoped
        proposal activates without anyone saying yes — which is right when a
        host is processing a document the user handed it, and wrong for a
        document this detector merely found. The caller who knows which case
        it is chooses; the detector does not choose for them.
        """
        from .registry.proposals import EvidenceRef

        if not short_definition.strip():
            raise ValueError(
                "a definition pattern gives a name, not a meaning: "
                "short_definition must come from a reviewer")
        return {
            "surface": self.surface,
            "canonical": self.canonical,
            "short_definition": short_definition,
            "requested_scope": requested_scope,
            "origin": "document_definition",
            "evidence_refs": (EvidenceRef(entry_id=str(entry_id),
                                          surface_present=True,
                                          definition_pattern=True),),
        }


def reversed_pair_defines(outside: str, inside: str) -> bool:
    """`Y(X)` — does the token outside the parens abbreviate what is inside?

    The reversed branch of :meth:`DocLocalDetector.extract` used to accept any
    pair where the parenthetical was merely *longer*, and length is not
    evidence. Over the wild corpus that branch fired three times and was wrong
    three times, each on a different Korean apposition convention:
    `노선영(강원도청)` is 선수(소속팀), `현대캐피탈(현대자동차그룹)` is
    자회사(모기업), `저는 공공기관(한국토지주택공사)` is neither. Each one bound
    a surface to an entity it does not name and handed it a scoring boost.

    A Hangul short form has to show its work — the same subsequence alignment
    :func:`align_definition` requires. A Latin acronym cannot: `KIST` is coined
    from a romanization of `한국과학기술연구원` that this library has no way to
    compute, so for that documented form the convention itself is the evidence.
    """
    token = outside.strip()
    if (token.isascii() and token.isalpha()
            and len(token) >= MIN_ABBREV_CHARS):
        return True
    return align_definition(inside, token) is not None


def align_definition(long_form: str, short: str, *,
                     definition_span: tuple[int, int] = (0, 0),
                     pattern: str = "", rejections=None) -> NewTermDefinition | None:
    """Do these two surfaces stand in an abbreviation relation?

    The same evidence :class:`ktrf.abbrev.AbbrevAligner` demands of a token
    before it may name an entity, asked here of the document's own pair — the
    only difference is that the target comes from the text instead of the
    glossary. Subsequence alignment does not care about script, so
    `PPR`/`Portland Pattern Repository` passes for the reason
    `국공노`/`국가공무원노동조합` does.

    Three conditions on top of alignment, each measured against the wild
    corpus before it was adopted:

    **An abbreviation skips.** `초등학교` is a subsequence of `서원초등학교`
    and abbreviates nothing — it is the head noun with the name cut off, as
    `변제` is of `대물변제` and `선물` of `선물옵션`. A contiguous run is a
    truncation; taking syllables from across the name is what makes an
    abbreviation one.

    **The alignment says where the name starts.** `X(Y)` captures whatever
    precedes the paren, which is usually a clause: `위한 중앙재난안전대책본부`,
    `탈당하여 후보 단일화 추진 협의회`. The first aligned character is the
    first character the abbreviation claims, so everything left of it belongs
    to the sentence and not to the name. This is the mirror of M4's rule that
    the residual says where a name ends.

    **And where it stops.** If whole words trail after the last aligned
    character the alignment sprawled across a sentence instead of covering a
    name — `미국` "abbreviating"
    `미사일에 대한 국제사회와 트럼프대통령과 트럼프행정부`.

    Returns ``None`` unless all of it holds. The false positives that remain
    are real and are reported as such: this feeds a review queue, never the
    glossary.

    ``definition_span`` and ``pattern`` are carried through onto the record
    for callers that read the pair out of a document; alone, the function is
    a pure question about two surfaces and they default to empty.

    ``rejections`` is an optional counter the evaluation harness passes in so
    the published report can say what was *refused* and why. A miner that only
    shows its hits is unfalsifiable, and the alternative — restating these
    conditions in ``eval/`` — is a second copy that drifts.
    """
    def _no(reason: str) -> None:
        if rejections is not None:
            rejections[reason] += 1
        return None

    a, b = long_form.strip(), short.strip()
    x, y = ((a, b) if len(a.replace(" ", "")) <= len(b.replace(" ", ""))
            else (b, a))
    compact = x.replace(" ", "")
    if len(compact) < MIN_ABBREV_CHARS or len(compact) >= len(y.replace(" ", "")):
        return _no("too_short_to_abbreviate")
    if compact in TYPE_TERMINALS:
        # `미세먼지특별대책위원회(위원회)` is a short reference, and `위원회`
        # is the worst surface anyone could register — it names everything.
        return _no("bare_type_terminal")
    pos = _subsequence_positions(compact, y)
    if pos is None:
        return _no("not_a_subsequence")
    if pos[-1] - pos[0] + 1 == len(compact):
        return _no("contiguous_substring")
    if " " in y[pos[-1]:]:
        return _no("name_does_not_end_there")
    canonical = y[pos[0]:].strip(" ·-")
    if not canonical or canonical == x:
        return _no("degenerate")
    return NewTermDefinition(surface=x, canonical=canonical,
                             definition_span=definition_span,
                             aligned_positions=tuple(pos), pattern=pattern)


class DocLocalDetector:
    def __init__(self, exact_index: ExactIndex):
        self.exact_index = exact_index

    def _resolve_long_form(self, long_form: str) -> list[str]:
        """Entity ids the long form resolves to via the global glossary."""
        stream = build_canonical_stream(long_form.strip())
        matches = self.exact_index.find(stream)
        full = [
            m for m in matches
            if (m.core_span[1] - m.core_span[0]) >= len(long_form.strip()) * 0.7
        ]
        return sorted({m.binding.entity_id for m in full})

    @staticmethod
    def _pairs(text: str):
        """(pattern name, long form, short form, span) for every definition."""
        for name, pat in (("paren", _PAT_PAREN), ("iha", _PAT_IHA)):
            for m in pat.finditer(text):
                long_form, short = m.group(1).strip(), m.group(2).strip()
                if not long_form or not short or short == long_form:
                    continue
                yield name, long_form, short, m.span()

    def extract(self, text: str) -> list[DocLocalBinding]:
        bindings: list[DocLocalBinding] = []
        seen: set[tuple[str, tuple[int, int]]] = set()
        for _name, long_form, short, span in self._pairs(text):
            entity_ids = self._resolve_long_form(long_form)
            pair_entity_ids = entity_ids
            alias = short
            if not entity_ids:
                # reversed pattern: SHORT(LONG) — long form inside parens.
                # Longer is not evidence; see `reversed_pair_defines`.
                rev_ids = self._resolve_long_form(short)
                if (rev_ids and len(short) > len(long_form)
                        and reversed_pair_defines(long_form, short)):
                    pair_entity_ids, alias = rev_ids, long_form
                else:
                    continue
            key = (alias, span)
            if key in seen:
                continue
            seen.add(key)
            bindings.append(
                DocLocalBinding(
                    alias_surface=alias,
                    entity_ids=pair_entity_ids,
                    definition_span=span,
                    long_form=long_form if alias == short else short,
                )
            )
        return bindings

    def extract_new_terms(self, text: str, *,
                          rejections=None) -> list[NewTermDefinition]:
        """Definitions of names the glossary does not hold (M6).

        Disjoint from :meth:`extract` by construction: a pair either names a
        registered entity, and is a doc-local *alias* this returns nothing
        for, or it does not, and there is no entity to bind — so the pair is
        a *proposal* instead.
        """
        out: list[NewTermDefinition] = []
        seen: set[tuple[str, str]] = set()
        for name, long_form, short, span in self._pairs(text):
            if (self._resolve_long_form(long_form)
                    or self._resolve_long_form(short)):
                continue
            found = align_definition(long_form, short, definition_span=span,
                                     pattern=name, rejections=rejections)
            if found is None:
                continue
            key = (found.surface, found.canonical)
            if key in seen:
                continue
            seen.add(key)
            out.append(found)
        return out

    def find_occurrences(self, text: str,
                         bindings: list[DocLocalBinding]) -> list[DocLocalOccurrence]:
        occurrences: list[DocLocalOccurrence] = []
        for b in bindings:
            start = 0
            while True:
                i = text.find(b.alias_surface, start)
                if i < 0:
                    break
                end = i + len(b.alias_surface)
                start = end
                # skip the defining occurrence itself
                if b.definition_span[0] <= i < b.definition_span[1]:
                    continue
                prev = text[i - 1] if i > 0 else ""
                nxt = text[end] if end < len(text) else ""
                if prev and (prev.isalnum() or "가" <= prev <= "힣"):
                    continue
                if nxt and nxt.isascii() and nxt.isalnum():
                    continue
                occurrences.append(DocLocalOccurrence(b, (i, end), b.alias_surface))
        return occurrences

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
# A Korean name this long is written with spaces; without them it is a
# description someone ran together. See `align_definition`.
_MAX_UNSPACED_NAME = 16


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

    Two conditions before alignment is even asked, each measured across
    every proposal four corpora produce:

    **Both sides need a letter.** `30(320k)` aligns — 3 then 0 do occur in
    order — and abbreviates nothing; the digits merely recur.

    **A name that long is written with spaces.**
    `청년들의취업을돕기위해만든청년구직활동지원금` is a description with the
    spaces removed. The longest correct space-free name in those proposals is
    12 characters and this is 22, so the cut sits in a gap rather than beside
    a real name.

    Three more on top of alignment, each measured against the wild corpus
    before it was adopted:

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
    if not (any(ch.isalpha() for ch in a) and any(ch.isalpha() for ch in b)):
        # `30(320k)` aligns as a subsequence and is a pair of numbers.
        # Digits carry no abbreviation relation - nothing was shortened,
        # the characters simply recur.
        return _no("no_letters")
    x, y = ((a, b) if len(a.replace(" ", "")) <= len(b.replace(" ", ""))
            else (b, a))
    if " " not in y and len(y) >= _MAX_UNSPACED_NAME:
        # `청년들의취업을돕기위해만든청년구직활동지원금` is a description with
        # the spaces taken out, not a name. Measured rather than guessed:
        # across 47 proposals from four corpora the longest *correct*
        # space-free name is 12 characters and this is 22, so the threshold
        # sits in a ten-character gap where nothing lives.
        return _no("unspaced_description")
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
        # Words trailing the alignment usually mean it crossed a sentence
        # rather than covered a name — `미국` "abbreviating"
        # `미사일에 대한 국제사회와 트럼프대통령과 트럼프행정부`.
        #
        # One shape is not that. Korean press writing introduces a body as
        # `기관명(직책 이름, 이하 약칭)`, and a corpus that strips the
        # parentheses leaves `기관명 직책 이름` in front of the marker. There
        # the alignment sits entirely inside the first 어절 and what trails is
        # a separate phrase, so the name simply ends where the 어절 does:
        # `한국콘텐츠진흥원 원장 조현래` → `한콘진` names 한국콘텐츠진흥원.
        #
        # An alignment scattered over several words with more words after it
        # stays refused. That split was checked against the corpus these gates
        # were chosen on, where it changes nothing at all (15 findings before
        # and after), and against unseen articles.
        if " " in y[pos[0]:pos[-1] + 1]:
            return _no("name_does_not_end_there")
        y = y[:y.index(" ", pos[-1])]
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

    def _anchored_long_form(self, capture: str) -> tuple[str, list[str]]:
        """The registered name a definition's left side actually ends with.

        The left side of `X(이하 Y)` is everything before the parenthesis,
        and in real prose that is rarely the name by itself. Measuring the
        match against the *whole* capture made a document's own definition
        depend on how many characters of unrelated words happened to precede
        the name:

            `이날 과학기술정보통신부(이하 "과기정통부")`   9/12 chars -> kept
            `정부는 과학기술정보통신부(이하 "과기정통부")`  9/13 chars -> lost

        Three characters of preamble decided whether the document got to
        define its own abbreviation. Worse, losing it is silent: the pack
        simply carries the glossary's meaning instead, so a document that
        says `고급빌링콘솔(이하 "ABC")` is told, as fact, that ABC is
        활동기준원가.

        The name is what sits immediately before the parenthesis, so anchor
        there — the longest registered match that ends at the end of the
        capture and starts on a word boundary. Preceding words are outside
        the definition rather than part of a name that failed to be covered.
        The old proportional rule stays as a fallback so nothing that used
        to be recognised stops being recognised.
        """
        text = capture.strip()
        if not text:
            return "", []
        matches = self.exact_index.find(build_canonical_stream(text))
        best: tuple[int, list[str]] | None = None
        for m in matches:
            start, end = m.core_span
            if end != len(text):
                continue  # not what the parenthesis is defining
            if start and text[start - 1] not in " 	·":
                continue  # mid-token: not a name of its own
            if best is None or start < best[0]:
                best = (start, [])
            if start == best[0]:
                best[1].append(m.binding.entity_id)
        if best is not None:
            return text[best[0]:], sorted(set(best[1]))
        return text, self._resolve_long_form(text)

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
        for _name, capture, short, span in self._pairs(text):
            long_form, entity_ids = self._anchored_long_form(capture)
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
            candidate = DocLocalBinding(
                alias_surface=alias,
                entity_ids=pair_entity_ids,
                definition_span=span,
                long_form=long_form if alias == short else short,
            )
            if alias == short and not self._paren_defines(text, candidate,
                                                          long_form, span):
                continue
            seen.add(key)
            bindings.append(candidate)
        return bindings

    def _paren_defines(self, text: str, binding: DocLocalBinding,
                       long_form: str, span: tuple[int, int]) -> bool:
        """Is `X(Y)` defining Y, or qualifying X?

        Korean prose puts both in the same brackets, and the corpus has both:

            한국철도공사(코레일)              a name the document will use
            서울특별시(사실상), 세종특별자치시(행정)   which capital, in what sense

        Nothing about the bracket separates them. Three things do, and any
        one is enough:

        `이하` says so outright — that is what the word is for.

        The short form reads as an abbreviation of the long one (질본 of
        질병관리본부, 공수처 of 고위공직자범죄수사처). 사실상 is not an
        abbreviation of 서울특별시 and 행정 is not one of 세종특별자치시.

        Or the document goes on to *use* it, which is what a definition is
        for. This is what keeps 코레일 — a brand name, not an abbreviation —
        in any document that uses it. In one that does not, the binding
        would produce no occurrences and change no resolution anyway; all
        it would do is put a definition in the pack that the document never
        relied on.
        """
        if "이하" in text[span[0]:span[1]]:
            return True
        if align_definition(long_form, binding.alias_surface) is not None:
            return True
        return bool(self.find_occurrences(text, [binding]))

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

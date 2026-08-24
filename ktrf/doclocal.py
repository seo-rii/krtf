"""Document-local alias detection (spec §18).

Detects in-document definitions such as:

    한국과학기술연구원(KIST)
    한국과학기술연구원, 이하 KIST
    KIST(한국과학기술연구원)
    한국과학기술연구원(이하 "연구원")

Local aliases live only in the request scope (INV-008/REQ-LOC-002), can only
*add* candidates — never remove or overwrite global bindings (INV-009 /
REQ-LOC-001; enforced in candidates.py by union semantics).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .matcher import ExactIndex
from .normalization import build_canonical_stream

_NAME = r"[가-힣A-Za-z0-9·\- ]{2,40}"
_SHORT = r"[가-힣A-Za-z0-9·\-]{1,20}"

# X(Y) / X(이하 "Y") / X, 이하 Y
_PAT_PAREN = re.compile(rf"({_NAME})\(\s*(?:이하\s*)?[\"'“”]?({_SHORT})[\"'“”]?\s*\)")
_PAT_IHA = re.compile(rf"({_NAME}),?\s*이하\s*[\"'“”]?({_SHORT})[\"'“”]?")


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

    def extract(self, text: str) -> list[DocLocalBinding]:
        bindings: list[DocLocalBinding] = []
        seen: set[tuple[str, tuple[int, int]]] = set()
        for pat, swap in ((_PAT_PAREN, False), (_PAT_IHA, False)):
            for m in pat.finditer(text):
                long_form, short = m.group(1).strip(), m.group(2).strip()
                if not long_form or not short or short == long_form:
                    continue
                entity_ids = self._resolve_long_form(long_form)
                pair_entity_ids = entity_ids
                alias = short
                if not entity_ids:
                    # reversed pattern: SHORT(LONG) — long form inside parens
                    rev_ids = self._resolve_long_form(short)
                    if rev_ids and len(short) > len(long_form):
                        pair_entity_ids, alias = rev_ids, long_form
                    else:
                        continue
                key = (alias, m.span())
                if key in seen:
                    continue
                seen.add(key)
                bindings.append(
                    DocLocalBinding(
                        alias_surface=alias,
                        entity_ids=pair_entity_ids,
                        definition_span=m.span(),
                        long_form=long_form if alias == short else short,
                    )
                )
        return bindings

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

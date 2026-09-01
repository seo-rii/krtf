"""Normalization and provenance (spec §14).

Two layers are kept separate (§14.1):

1. A conservative *canonical stream* (§14.2): NFC (T-01), allowlisted width
   folding (T-02), conditional compat-jamo run composition (T-08), allowlisted
   zero-width removal (T-09). No global NFKC, no case folding — Latin case is
   an alias-profile concern applied per search channel.
2. Purpose-specific *search channels* (§14.3): per normalization profile,
   derived views that drop ignorable punctuation (T-04), drop spacing for
   tolerant profiles (T-05) and casefold Latin (T-03). Channels reference the
   canonical units, never materialized variant strings (INV-012, §14.5).

Every normalized unit carries raw codepoint provenance (MappedUnit, §14.4).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .hangul import compose_jamo_run, is_compat_jamo

# ---------------------------------------------------------------------------
# Profiles (§14.6, normative defaults; REQ-NRM-002)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizationProfile:
    id: str
    nfc: bool = True
    width_fold: str = "ascii_compat"  # or "none"
    case_fold: str = "none"  # "ascii" or "none"
    ignore_punctuation: tuple[str, ...] = ()
    spacing_mode: str = "strict"  # "strict" or "tolerant"
    latin_morph: bool = False
    # §4.5 OCR/PDF confusable folding. Off everywhere by default: it is only
    # correct when the caller asserts the text came from OCR.
    ocr_fold: bool = False

    def merged(self, override: dict) -> "NormalizationProfile":
        """Field-level override (AliasBinding.normalization_policy, REQ-NRM-001)."""
        allowed = {
            "nfc", "width_fold", "case_fold", "ignore_punctuation",
            "spacing_mode", "latin_morph", "case_sensitive", "ocr_fold",
        }
        data = {
            "id": self.id,
            "nfc": self.nfc,
            "width_fold": self.width_fold,
            "case_fold": self.case_fold,
            "ignore_punctuation": self.ignore_punctuation,
            "spacing_mode": self.spacing_mode,
            "latin_morph": self.latin_morph,
            "ocr_fold": self.ocr_fold,
        }
        for k, v in override.items():
            if k not in allowed:
                raise ValueError(f"unknown normalization_policy field: {k}")
            if k == "case_sensitive":  # schema sugar (§10.4 example)
                data["case_fold"] = "none" if v else "ascii"
            elif k == "ignore_punctuation":
                data["ignore_punctuation"] = tuple(v)
            else:
                data[k] = v
        data["id"] = self.id + "+override"
        return NormalizationProfile(**data)


# §14.7 punctuation classes (M3).
#
# A profile that tolerates "-" has to tolerate every dash a keyboard, a word
# processor's autocorrect, or a PDF extractor can produce, or the tolerance
# becomes a lottery on which hyphen the author happened to type. `S-Oil`
# copied out of a PDF arrives as `S‐Oil` (U+2010) and used to miss.
#
# `/`, `&`, `+`, `#` deliberately have **no class**: each can be a load-bearing
# part of a name (`KT&G`, `S/W`, `C#`), so a profile opts into them one at a
# time rather than inheriting a group.
HYPHEN_CLASS: tuple[str, ...] = (
    "-", "‐", "‑", "‒", "–", "—", "―",
    "−", "﹘", "﹣",
)
MIDDOT_CLASS: tuple[str, ...] = ("·", "・", "•", "‧", "∙")

DEFAULT_PROFILES: dict[str, NormalizationProfile] = {
    p.id: p
    for p in [
        NormalizationProfile(
            id="latin_acronym", case_fold="ascii",
            ignore_punctuation=(".", *HYPHEN_CLASS), spacing_mode="strict",
        ),
        NormalizationProfile(
            id="latin_word", case_fold="ascii",
            ignore_punctuation=HYPHEN_CLASS, spacing_mode="strict",
            latin_morph=True,
        ),
        NormalizationProfile(
            id="korean_org_name", case_fold="none",
            ignore_punctuation=(*HYPHEN_CLASS, *MIDDOT_CLASS),
            spacing_mode="tolerant",
        ),
        NormalizationProfile(
            id="korean_term", case_fold="none",
            ignore_punctuation=(), spacing_mode="strict",
        ),
        NormalizationProfile(
            id="mixed_alnum", case_fold="ascii",
            ignore_punctuation=(*HYPHEN_CLASS, "&", "/"),
            spacing_mode="tolerant",
        ),
        # §4.5: OCR and PDF confusables are **not** a default. A resolver that
        # folds 0/O and 1/l for everyone turns every serial number into a
        # near-miss of every other one. This profile exists to be named by a
        # binding whose input provenance says the text came from OCR — the
        # tenant asserts the source, KTRF does not guess it.
        NormalizationProfile(
            id="ocr_tolerant", case_fold="ascii",
            ignore_punctuation=(".", *HYPHEN_CLASS, *MIDDOT_CLASS),
            spacing_mode="tolerant", ocr_fold=True,
        ),
    ]
}

# §4.5 OCR confusable folding, applied only under ``ocr_fold``. Each group
# collapses to its first member. Hangul is absent on purpose: syllable-level
# OCR confusion is a *cost* question for the fuzzy channel (§17.2), not an
# equality question, and folding it here would make distinct names equal.
OCR_FOLD_GROUPS: tuple[str, ...] = ("0OoDQ", "1lIi|", "5S", "8B", "2Z", "6G")
OCR_FOLD: dict[str, str] = {c: g[0] for g in OCR_FOLD_GROUPS for c in g}

# ---------------------------------------------------------------------------
# Canonical stream (§14.2)
# ---------------------------------------------------------------------------

# T-09 allowlist: ZWSP, ZWNJ, ZWJ, BOM
ZERO_WIDTH_ALLOWLIST = {"​", "‌", "‍", "﻿"}

# transform cost per class (initial config, §17.2 spirit; exact-preserving = 0)
TRANSFORM_COST = {
    "T-01": 0.0, "T-02": 0.0, "T-03": 0.0,
    "T-04": 0.05, "T-05": 0.05, "T-08": 0.0, "T-09": 0.0,
    # T-10 OCR confusable fold: opt-in only, and priced well above the
    # exact-preserving transforms because it makes distinct strings equal.
    "T-10": 0.15,
}


@dataclass
class MappedUnit:
    """One canonical character with raw provenance (§14.4)."""

    ch: str
    raw_start: int  # codepoint offset into raw text
    raw_end: int
    transforms: tuple[str, ...] = ()


@dataclass
class CanonicalStream:
    raw_text: str
    units: list[MappedUnit]
    gaps: list[dict] = field(default_factory=list)  # removed zero-width chars

    @property
    def text(self) -> str:
        return "".join(u.ch for u in self.units)


def _fold_width(ch: str) -> str | None:
    """ascii_compat allowlist width folding (T-02)."""
    cp = ord(ch)
    if 0xFF01 <= cp <= 0xFF5E:  # fullwidth ASCII
        return chr(cp - 0xFF00 + 0x20)
    if cp == 0x3000:  # ideographic space
        return " "
    return None


def _is_nfc_boundary(ch: str) -> bool:
    cp = ord(ch)
    if unicodedata.combining(ch):
        return False
    if 0x1160 <= cp <= 0x11FF:  # conjoining jungseong/jongseong
        return False
    return True


def build_canonical_stream(text: str, width_fold: bool = True) -> CanonicalStream:
    units: list[MappedUnit] = []
    gaps: list[dict] = []

    # 1) segment at NFC boundaries and normalize each segment (T-01)
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        while j < n and not _is_nfc_boundary(text[j]):
            j += 1
        seg = text[i:j]
        norm = unicodedata.normalize("NFC", seg)
        transformed = ("T-01",) if norm != seg else ()
        for ch in norm:
            units.append(MappedUnit(ch, i, j, transformed))
        i = j

    # 2) width folding (T-02)
    if width_fold:
        for u in units:
            folded = _fold_width(u.ch)
            if folded is not None:
                u.ch = folded
                u.transforms = u.transforms + ("T-02",)

    # 3) zero-width removal (T-09) with gap provenance
    kept: list[MappedUnit] = []
    for u in units:
        if u.ch in ZERO_WIDTH_ALLOWLIST:
            gaps.append({"raw_start": u.raw_start, "raw_end": u.raw_end,
                         "transform": "T-09", "char": u.ch})
        else:
            kept.append(u)
    units = kept

    # 4) compat jamo run composition (T-08)
    units = _compose_compat_runs(units)

    return CanonicalStream(text, units, gaps)


def _compose_compat_runs(units: list[MappedUnit]) -> list[MappedUnit]:
    out: list[MappedUnit] = []
    i, n = 0, len(units)
    while i < n:
        if not is_compat_jamo(units[i].ch):
            out.append(units[i])
            i += 1
            continue
        j = i
        while j < n and is_compat_jamo(units[j].ch):
            j += 1
        run = units[i:j]
        composed = compose_jamo_run("".join(u.ch for u in run))
        # align output chars to consumed input units
        k = 0
        for ch in composed:
            if k < len(run) and ch == run[k].ch:  # passthrough jamo
                out.append(MappedUnit(ch, run[k].raw_start, run[k].raw_end,
                                      run[k].transforms))
                k += 1
                continue
            consumed = None
            for width in (2, 3, 4):
                seg = run[k:k + width]
                if len(seg) == width and compose_jamo_run(
                    "".join(u.ch for u in seg)
                ) == ch:
                    consumed = seg
                    break
            if consumed is None:  # defensive: emit remaining as-is
                consumed = run[k:k + 1]
            out.append(
                MappedUnit(ch, consumed[0].raw_start, consumed[-1].raw_end,
                           consumed[0].transforms + ("T-08",))
            )
            k += len(consumed)
        i = j
    return out


# ---------------------------------------------------------------------------
# Search channels (§14.3)
# ---------------------------------------------------------------------------


@dataclass
class Channel:
    """A derived matching view over the canonical stream for one profile."""

    profile: NormalizationProfile
    chars: str  # channel string (matched against alias keys)
    unit_idx: list[int]  # channel position -> canonical unit index
    # channel position -> transform applied at that position ("" if none)
    pos_transform: list[str]


def build_channel(stream: CanonicalStream, profile: NormalizationProfile) -> Channel:
    chars: list[str] = []
    unit_idx: list[int] = []
    pos_transform: list[str] = []
    for idx, u in enumerate(stream.units):
        ch = u.ch
        if ch in profile.ignore_punctuation:
            continue  # T-04 deletion (gap tracked via unit_idx discontinuity)
        if profile.spacing_mode == "tolerant" and ch.isspace():
            continue  # T-05 deletion
        t = ""
        if profile.case_fold == "ascii" and "A" <= ch <= "Z":
            ch = ch.lower()
            t = "T-03"
        if profile.ocr_fold and ch in OCR_FOLD:
            ch = OCR_FOLD[ch]
            t = t or "T-10"
        chars.append(ch)
        unit_idx.append(idx)
        pos_transform.append(t)
    return Channel(profile, "".join(chars), unit_idx, pos_transform)


def normalize_alias(surface: str, profile: NormalizationProfile) -> str:
    """Produce the match key of an alias surface under a profile.

    Applies the same transforms as the corresponding search channel so that
    key equality == channel match. Spacing is always removed from keys for
    tolerant profiles; for strict profiles inner spaces are kept.
    """
    stream = build_canonical_stream(surface, width_fold=profile.width_fold != "none")
    out = []
    for u in stream.units:
        ch = u.ch
        if ch in profile.ignore_punctuation:
            continue
        if profile.spacing_mode == "tolerant" and ch.isspace():
            continue
        if profile.case_fold == "ascii" and "A" <= ch <= "Z":
            ch = ch.lower()
        if profile.ocr_fold and ch in OCR_FOLD:
            ch = OCR_FOLD[ch]
        out.append(ch)
    return "".join(out)

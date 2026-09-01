"""Normalization tests (spec §14). REQ-NRM-001, REQ-NRM-002, REQ-NRM-003, INV-012."""

import unicodedata

import pytest

from ktrf.normalization import (
    DEFAULT_PROFILES,
    build_canonical_stream,
    build_channel,
    normalize_alias,
)


def test_default_profiles_present():
    # §14.6: the system profiles are normative (REQ-NRM-002)
    assert set(DEFAULT_PROFILES) == {
        "latin_acronym", "latin_word", "korean_org_name", "korean_term",
        "mixed_alnum", "ocr_tolerant",
    }
    assert DEFAULT_PROFILES["latin_word"].latin_morph is True
    assert DEFAULT_PROFILES["latin_acronym"].latin_morph is False


def test_ocr_folding_is_opt_in_only():
    """§4.5: only the profile that names itself OCR folds confusables.

    Shipping the profile is not the same as enabling it. A default that
    folded 0/O for everyone would make every serial number a near-miss of
    every other one, so the tenant has to assert the source.
    """
    assert [k for k, v in DEFAULT_PROFILES.items() if v.ocr_fold] == ["ocr_tolerant"]
    ocr = DEFAULT_PROFILES["ocr_tolerant"]
    assert normalize_alias("S-0IL", ocr) == normalize_alias("S-OIL", ocr)
    plain = DEFAULT_PROFILES["latin_word"]
    assert normalize_alias("S-0IL", plain) != normalize_alias("S-OIL", plain)


def test_hyphen_class_covers_every_dash_a_pdf_produces():
    """§14.7: tolerating "-" but not U+2010 makes tolerance a lottery."""
    p = DEFAULT_PROFILES["korean_org_name"]
    key = normalize_alias("한국전력공사", p)
    for dash in ("-", "‐", "‑", "–", "—", "−"):
        assert normalize_alias("한국전력" + dash + "공사", p) == key, dash


def test_nfc_composition_with_provenance():
    # T-01: NFD input composes, provenance covers the full raw segment
    nfd = unicodedata.normalize("NFD", "한전")
    assert len(nfd) == 6
    stream = build_canonical_stream(nfd)
    assert stream.text == "한전"
    u0 = stream.units[0]
    assert (u0.raw_start, u0.raw_end) == (0, 3)
    assert "T-01" in u0.transforms
    # raw text is never destroyed (INV-012)
    assert stream.raw_text == nfd


def test_width_folding_fullwidth_ascii():
    # T-02: ＡＰ -> AP, provenance to original chars
    stream = build_canonical_stream("ＡＰ 점검")
    assert stream.text == "AP 점검"
    assert stream.units[0].transforms == ("T-02",)
    assert (stream.units[0].raw_start, stream.units[0].raw_end) == (0, 1)


def test_no_global_nfkc():
    # §14.2: unconditional NFKC is forbidden; e.g. ㎢ must NOT be expanded
    stream = build_canonical_stream("면적 ㎢ 단위")
    assert "㎢" in stream.text


def test_compat_jamo_run_composition():
    # T-08: compat jamo run composes into syllables with provenance
    stream = build_canonical_stream("ㅎㅏㄴ전 방문")
    assert stream.text == "한전 방문"
    u = stream.units[0]
    assert u.ch == "한"
    assert (u.raw_start, u.raw_end) == (0, 3)
    assert "T-08" in u.transforms


def test_compat_jamo_leftover_preserved():
    # non-composable jamo remain in the canonical stream (T-08 condition)
    stream = build_canonical_stream("ㅋㅋ 재밌다")
    assert stream.text == "ㅋㅋ 재밌다"


def test_zero_width_removed_with_gap_provenance():
    stream = build_canonical_stream("한​전")
    assert stream.text == "한전"
    assert len(stream.gaps) == 1
    assert stream.gaps[0]["transform"] == "T-09"
    assert stream.gaps[0]["raw_start"] == 1


def test_channel_latin_acronym():
    # case folding + punctuation removal in channel, not canonical stream
    stream = build_canonical_stream("A.P. 장애")
    assert stream.text == "A.P. 장애"  # canonical keeps punctuation
    ch = build_channel(stream, DEFAULT_PROFILES["latin_acronym"])
    assert ch.chars == "ap 장애"
    # channel position maps back to canonical units -> raw offsets
    assert stream.units[ch.unit_idx[1]].ch == "P"


def test_channel_tolerant_spacing():
    stream = build_canonical_stream("한 전 담당자")
    ch = build_channel(stream, DEFAULT_PROFILES["korean_org_name"])
    assert ch.chars == "한전담당자"


def test_normalize_alias_matches_channel():
    prof = DEFAULT_PROFILES["latin_acronym"]
    assert normalize_alias("A.P.", prof) == "ap"
    assert normalize_alias("ＡＰ", prof) == "ap"
    assert normalize_alias("AP", prof) == "ap"
    prof_kr = DEFAULT_PROFILES["korean_org_name"]
    assert normalize_alias("한국 전력공사", prof_kr) == "한국전력공사"


def test_profile_field_override():
    # REQ-NRM-001: binding policy overrides only the named fields
    base = DEFAULT_PROFILES["latin_acronym"]
    o = base.merged({"case_sensitive": True})
    assert o.case_fold == "none"
    assert o.ignore_punctuation == base.ignore_punctuation  # untouched
    with pytest.raises(ValueError):
        base.merged({"bogus_field": 1})

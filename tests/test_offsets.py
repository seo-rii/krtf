"""Offset contract tests (spec §13). REQ-OFF-001, REQ-OFF-002, REQ-OFF-003."""

import pytest

from ktrf.offsets import OffsetMap, check_roundtrip, check_span_invariant


REFERENCE = "한전KDN은 AP 장애 내용을 QMS에 등록했다."


def test_reference_example_codepoint_spans():
    # §13.4 reference example
    assert REFERENCE[0:5] == "한전KDN"
    assert REFERENCE[7:9] == "AP"
    assert REFERENCE[17:20] == "QMS"


def test_reference_example_byte_spans():
    m = OffsetMap(REFERENCE)
    assert (m.cp_to_byte(0), m.cp_to_byte(5)) == (0, 9)
    assert (m.cp_to_byte(7), m.cp_to_byte(9)) == (13, 15)
    assert (m.cp_to_byte(17), m.cp_to_byte(20)) == (33, 36)


def test_utf16_matches_codepoint_for_bmp():
    m = OffsetMap(REFERENCE)
    for i in range(len(REFERENCE) + 1):
        assert m.cp_to_utf16(i) == i


def test_utf16_diverges_after_supplementary_plane():
    text = "😀한전 AP"
    m = OffsetMap(text)
    # 😀 is one codepoint but two UTF-16 units
    assert m.cp_to_utf16(1) == 2
    assert m.cp_to_byte(1) == 4
    check_roundtrip(text, 1, 3)  # 한전


def test_span_dict_three_coordinates():
    m = OffsetMap("한전 AP 점검")
    d = m.span_dict(3, 5)
    assert d == {
        "byte": {"start": 7, "end": 9},
        "codepoint": {"start": 3, "end": 5},
        "utf16": {"start": 3, "end": 5},
    }


def test_invariant_checker_raises_on_mismatch():
    with pytest.raises(AssertionError):
        check_span_invariant("한전 AP", 0, 2, "AP")
    check_span_invariant("한전 AP", 3, 5, "AP")


def test_byte_to_cp_rejects_non_boundary():
    m = OffsetMap("한전")
    with pytest.raises(ValueError):
        m.byte_to_cp(1)  # middle of 한 (3-byte char)


def test_roundtrip_mixed_content():
    text = "구 한전KDN에서도 ＡＰ 장애… 확인 🙂"
    for s in range(0, len(text)):
        check_roundtrip(text, s, min(s + 3, len(text)))

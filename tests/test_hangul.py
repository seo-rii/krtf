"""Hangul jamo / keyboard channel tests (spec §17.2, §17.4, T-08)."""

from ktrf.hangul import (
    compose_jamo_run,
    compose_syllable,
    decompose_syllable,
    hangul_to_keys,
    has_batchim,
    jamo_keys_adjacent,
    keys_to_hangul,
    to_jamo_seq,
)


def test_decompose_compose_roundtrip():
    for ch in "한전공사국밥값닭":
        cho, jung, jong = decompose_syllable(ch)
        assert compose_syllable(cho, jung, jong) == ch


def test_decompose_non_hangul_none():
    assert decompose_syllable("A") is None
    assert decompose_syllable("ㅎ") is None


def test_batchim():
    assert has_batchim("전") is True
    assert has_batchim("하") is False
    assert has_batchim("A") is None


def test_jamo_seq():
    assert to_jamo_seq("한전") == "ㅎㅏㄴㅈㅓㄴ"
    assert to_jamo_seq("AP") == "AP"
    assert to_jamo_seq("값") == "ㄱㅏㅂㅅ"  # compound jong splits
    assert to_jamo_seq("의") == "ㅇㅡㅣ"  # compound jung splits


def test_compose_jamo_run_basic():
    # T-08: compat jamo run composes into syllables
    assert compose_jamo_run("ㅎㅏㄴㅈㅓㄴ") == "한전"


def test_compose_jamo_run_dokkaebi():
    # 한 + ㅈㅓㄴ: the ㄴ stays as jong because next is consonant;
    # ㄱㅏㅁㅏ -> 가마 (ㅁ moves to next syllable when followed by vowel)
    assert compose_jamo_run("ㄱㅏㅁㅏ") == "가마"


def test_compose_jamo_run_compound_jong():
    assert compose_jamo_run("ㄱㅏㅂㅅ") == "값"
    assert compose_jamo_run("ㄷㅏㄹㄱ") == "닭"


def test_compose_jamo_run_leftover_preserved():
    # incomplete jamo remain (spec: 합성 불가 잔여 자모는 보존)
    assert compose_jamo_run("ㅎㅎㅎ") == "ㅎㅎㅎ"
    assert compose_jamo_run("ㅎㅏㄴㅅ") == "한ㅅ"


def test_keyboard_roundtrip():
    # §17.4 reference: 한전 -> gkswjs
    assert hangul_to_keys("한전") == "gkswjs"
    assert keys_to_hangul("gkswjs") == "한전"
    # compound vowel: 과 = ㄱ+ㅗ+ㅏ = r h k
    assert hangul_to_keys("과기정통부") == "rhkrlwjdxhdqn"
    assert keys_to_hangul("rhkrlwjdxhdqn") == "과기정통부"


def test_keyboard_mixed_passthrough():
    assert hangul_to_keys("한전KDN") == "gkswjsKDN"


def test_adjacency():
    assert jamo_keys_adjacent("ㅏ", "ㅓ")  # k and j are adjacent
    assert not jamo_keys_adjacent("ㅂ", "ㅡ")  # q and m are far

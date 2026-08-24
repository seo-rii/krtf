"""Morphology tests: particle FST, suffixes, prefixes (spec §16).

REQ-TAIL-001 (FST composition, no enumeration), REQ-BND-002 (prefix-accept),
depth cap (§52.13).
"""

from ktrf.morphology import (
    ParticleFST,
    analyze_residual,
    match_latin_tail,
    match_prefix_modifier,
)


fst = ParticleFST()


def test_single_particles_parse():
    for tail in ["은", "이", "을", "에서", "으로", "까지", "조차", "마저", "처럼",
                 "보다", "한테", "께서", "도", "만"]:
        parses = fst.parse_full(tail, prev_char="전")  # 전 has batchim
        assert parses, tail


def test_chain_composition_not_enumeration():
    # 에서도, 까지는, 만이라도 must parse as chains (REQ-TAIL-001)
    p = fst.parse_full("에서도", prev_char="전")
    assert any(x.particles == ("에서", "도") for x in p)
    p = fst.parse_full("까지는", prev_char="전")
    assert any(x.particles == ("까지", "는") for x in p)
    p = fst.parse_full("만이라도", prev_char="전")
    assert any(x.particles == ("만", "이라도") for x in p)
    p = fst.parse_full("으로부터", prev_char="국")
    assert any(x.particles == ("으로", "부터") for x in p)


def test_depth_cap():
    fst2 = ParticleFST(max_depth=2)
    assert not fst2.parse_full("에서만은", prev_char="전")  # needs depth 3
    assert fst.parse_full("에서만은", prev_char="전")


def test_allomorph_grammaticality_soft():
    # 한전 + 가 is ungrammatical (전 has batchim -> needs 이); still parses
    p = fst.parse_full("가", prev_char="전")
    assert p and all(not x.grammatical for x in p)
    p = fst.parse_full("이", prev_char="전")
    assert p and all(x.grammatical for x in p)


def test_rieul_allomorph():
    # 서울 (ㄹ batchim) + 로 is grammatical; + 으로 is not
    assert fst.parse_full("로", prev_char="울")[0].grammatical
    assert not fst.parse_full("으로", prev_char="울")[0].grammatical
    # 국 (non-ㄹ batchim) + 으로 grammatical
    assert fst.parse_full("으로", prev_char="국")[0].grammatical


def test_non_hangul_core_constraint_unknown():
    # "AP에서": constraint unknown -> treated as satisfied
    p = fst.parse_full("에서", prev_char="P")
    assert p and p[0].grammatical


def test_accepts_prefix_boundary_interface():
    # REQ-BND-002: prefix-accept only, no decomposition
    assert fst.accepts_prefix("에서도 확인")
    assert fst.accepts_prefix("은 다음")
    assert not fst.accepts_prefix("서울본부")


def test_residual_suffix():
    r = analyze_residual("본부")
    assert r.kind == "SUFFIX"
    r = analyze_residual("서울본부")
    assert r.kind == "SUFFIX_WITH_MODIFIER"
    assert r.parts == ("서울", "본부")
    r = analyze_residual("담당자")
    assert r.kind == "SUFFIX"
    r = analyze_residual("호랑이")
    assert r.kind == "UNKNOWN"


def test_prefix_modifier():
    # §16.6: spaced and unspaced, catalog-limited
    assert match_prefix_modifier("공지: 구 ") == ("구", "TEMPORAL", True)
    assert match_prefix_modifier("구") == ("구", "TEMPORAL", False)
    assert match_prefix_modifier("가칭 ") == ("가칭", "NAMING", True)
    assert match_prefix_modifier("대") is None  # 대한전선 must not split
    assert match_prefix_modifier("의전") is None  # 전 preceded by hangul


def test_latin_tail():
    assert match_latin_tail("s 교체") == ("s", "LATIN_PLURAL")
    assert match_latin_tail("'s 상태") == ("'s", "LATIN_POSSESSIVE")
    assert match_latin_tail("es") == ("es", "LATIN_PLURAL")
    assert match_latin_tail("tation") is None  # continues into a word

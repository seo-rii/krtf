"""Exact matcher + boundary tests (spec §15). REQ-BND-001..003, INV-004."""

import pytest

from ktrf.glossary import load_glossary
from ktrf.matcher import ExactIndex
from ktrf.morphology import ParticleFST
from ktrf.normalization import build_canonical_stream
from ktrf.tailparser import parse_matches


@pytest.fixture(scope="module")
def glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "ORG_KEPCO", "canonical": "한국전력공사",
             "description": "전력 공기업"},
            {"entity_id": "ORG_KEPCO_KDN", "canonical": "한전KDN",
             "description": "전력 ICT 기업"},
            {"entity_id": "NETWORK_ACCESS_POINT", "canonical": "Access Point",
             "domain_ids": ["NETWORK"]},
            {"entity_id": "WORKFLOW_APPROVAL", "canonical": "Approval Process",
             "domain_ids": ["WORKFLOW"]},
            {"entity_id": "SRV", "canonical": "Server", "domain_ids": ["IT"]},
            {"entity_id": "DEPT_PLANNING", "canonical": "기획부"},
            {"entity_id": "TEAM_PLANNING", "canonical": "기획"},
        ],
        "alias_families": [
            {"family_id": "F_KEPCO", "representative": "한전",
             "normalization_profile": "korean_org_name"},
            {"family_id": "F_KDN", "representative": "한전KDN",
             "normalization_profile": "mixed_alnum"},
            {"family_id": "F_AP", "representative": "AP",
             "normalization_profile": "latin_acronym"},
            {"family_id": "F_SERVER", "representative": "server",
             "normalization_profile": "latin_word"},
            {"family_id": "F_PLAN_DEPT", "representative": "기획부",
             "normalization_profile": "korean_term"},
            {"family_id": "F_PLAN", "representative": "기획",
             "normalization_profile": "korean_term"},
        ],
        "alias_bindings": [
            {"alias_id": "A_KEPCO", "family_id": "F_KEPCO",
             "entity_id": "ORG_KEPCO", "surface": "한전"},
            {"alias_id": "A_KDN", "family_id": "F_KDN",
             "entity_id": "ORG_KEPCO_KDN", "surface": "한전KDN"},
            {"alias_id": "A_AP_NET", "family_id": "F_AP",
             "entity_id": "NETWORK_ACCESS_POINT", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary",
                                 "right": "particle_or_token_boundary",
                                 "allow_inside_latin_run": False}},
            {"alias_id": "A_AP_WF", "family_id": "F_AP",
             "entity_id": "WORKFLOW_APPROVAL", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
            {"alias_id": "A_SERVER", "family_id": "F_SERVER",
             "entity_id": "SRV", "surface": "server",
             "boundary_policy": {"left": "latin_token_boundary"}},
            {"alias_id": "A_PLAN_DEPT", "family_id": "F_PLAN_DEPT",
             "entity_id": "DEPT_PLANNING", "surface": "기획부"},
            {"alias_id": "A_PLAN", "family_id": "F_PLAN",
             "entity_id": "TEAM_PLANNING", "surface": "기획"},
        ],
    })


@pytest.fixture(scope="module")
def index(glossary):
    return ExactIndex(glossary, ParticleFST())


def _find(index, text):
    return index.find(build_canonical_stream(text))


def surfaces(matches, text):
    return {text[m.core_span[0]:m.core_span[1]] for m in matches}


def test_basic_exact_match(index):
    text = "AP 장애 발생"
    ms = _find(index, text)
    assert surfaces(ms, text) == {"AP"}


def test_all_senses_preserved(index):
    # INV-004: both AP senses in the pool
    ms = _find(index, "AP 장애")
    assert {m.binding.entity_id for m in ms} == {
        "NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL"}


def test_particle_attachment_passes_boundary(index):
    for text in ["AP에서 확인", "한전은 발표했다", "한전에서도 참여한다"]:
        assert _find(index, text), text


def test_inside_latin_run_rejected(index):
    # §15.2: SAP, CAPEX must not produce AP
    assert not _find(index, "SAP 시스템 점검")
    assert not _find(index, "CAPEX 검토")


def test_hangul_left_attachment_rejected(index):
    # §15.2: 대한전선 must not match 한전
    text = "대한전선 관계자"
    ms = _find(index, text)
    assert "한전" not in surfaces(ms, text)


def test_nested_overlapping_matches_kept(index):
    # §15.2: 한전KDN -> both 한전 and 한전KDN, overlapping preserved
    text = "한전KDN은 발표했다"
    ms = _find(index, text)
    assert surfaces(ms, text) == {"한전", "한전KDN"}


def test_normalized_variants(index):
    # T-02/T-03/T-04 variants of AP
    for text in ["ＡＰ 장애", "ap 장애", "A.P. 장애", "A-P 장애"]:
        ms = _find(index, text)
        assert any(m.binding.surface == "AP" for m in ms), text


def test_tolerant_spacing_korean_org(index):
    text = "한 전 담당자와 통화"
    ms = _find(index, text)
    kepco = [m for m in ms if m.binding.alias_id == "A_KEPCO"]
    assert kepco
    m = kepco[0]
    assert len(m.matched_segments) == 2
    assert m.transform_cost > 0


def test_latin_morph_plural(index):
    # §16.7: servers matches server under latin_word (REQ-TAIL-006)
    text = "servers 점검 완료"
    ms = _find(index, text)
    assert any(m.binding.alias_id == "A_SERVER" for m in ms)
    # APs must NOT match AP (latin_acronym has latin_morph false)
    assert not any(m.binding.surface == "AP" for m in _find(index, "APs 교체"))


def test_prefix_modifier_unspaced_left_boundary(index):
    # 구한전: prefix catalog allows attached-left (§16.6)
    text = "구한전 자료"
    ms = _find(index, text)
    kepco = [m for m in ms if m.binding.alias_id == "A_KEPCO"]
    assert kepco
    assert kepco[0].boundary.left_prefix is not None


def test_homograph_collision_both_kept(index):
    # §16.5 / REQ-TAIL-003: 기획부터 -> [기획]+부터 and [기획부]+터
    text = "기획부터 검토했다"
    ms = _find(index, text)
    assert surfaces(ms, text) == {"기획", "기획부"}


def test_residual_soft_boundary(index):
    # 한전서울본부: hangul residual continuation is SOFT-kept (§16.5)
    text = "한전서울본부에서도 회의"
    ms = _find(index, text)
    kepco = [m for m in ms if m.binding.alias_id == "A_KEPCO"]
    assert kepco
    assert kepco[0].boundary.status == "SOFT"


def test_parse_full_pipeline(index, glossary):
    # §7.6 reference: 전 한전서울본부에서도
    text = "전 한전서울본부에서도 회의를 했다"
    stream = build_canonical_stream(text)
    proposals = parse_matches(stream, index.find(stream), ParticleFST())
    kepco = [p for p in proposals if p.binding_id == "A_KEPCO"]
    assert kepco
    p = kepco[0]
    assert p.surface == "한전"
    assert p.prefix and p.prefix["surface"] == "전" and p.prefix["kind"] == "TEMPORAL"
    best = p.best_tail
    assert best.residual == "서울본부"
    assert best.residual_kind == "SUFFIX_WITH_MODIFIER"
    assert best.particles == ("에서", "도")
    # full span covers prefix through particles
    assert text[p.full_span[0]:p.full_span[1]] == "전 한전서울본부에서도"


def test_particle_chain_tail(index):
    text = "한전에서도 참여"
    stream = build_canonical_stream(text)
    from ktrf.tailparser import parse_matches as pm
    fst = ParticleFST()
    idx_matches = index.find(stream)
    proposals = pm(stream, idx_matches, fst)
    kepco = [p for p in proposals if p.binding_id == "A_KEPCO"]
    assert kepco
    assert kepco[0].best_tail.particles == ("에서", "도")
    assert text[kepco[0].full_span[0]:kepco[0].full_span[1]] == "한전에서도"

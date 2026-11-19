import runpy
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest


min_api = runpy.run_path(str(Path(__file__).resolve().parents[1] / "min" / "krtf.py"))


def make_snapshot(*terms):
    return min_api["compile_snapshot"]({"terms": list(terms)})


def resolve(snapshot, text, **options):
    return min_api["resolve"](snapshot, text, **options)["mentions"]


@pytest.mark.parametrize("definition", [
    '한국과학기술연구원(이하 "연구원")',
    "한국과학기술연구원(이하 ‘연구원’이라 한다)",
    '한국과학기술연구원, 이하 "연구원"',
    "한국과학기술연구원(연구원)",
    "연구원(한국과학기술연구원)",
])
def test_document_local_declaration_stays_in_request(definition):
    snapshot = make_snapshot({"key": "kist", "canonical": "한국과학기술연구원"})
    text = definition + ". 연구원에서 발표했다."
    mention = next(m for m in resolve(snapshot, text, recover=False)
                   if m["surface"] == "연구원")
    assert mention["resolved_entity"]["entity_id"] == "project:kist"
    assert mention["generation_channels"] == ["doc_local"]
    segment = mention["full_span"]["codepoint"]
    assert text[segment["start"]:segment["end"]] == "연구원에서"
    assert not resolve(snapshot, "연구원에서 발표했다.", recover=False)


def test_conflicting_declarations_keep_global_and_both_local_senses():
    snapshot = make_snapshot(
        {"key": "billing", "canonical": "과금관리시스템"},
        {"key": "finance", "canonical": "재무관리시스템"},
        {"key": "other", "canonical": "다른 시스템", "surfaces": ["XYZ"]},
    )
    text = "과금관리시스템(XYZ). 재무관리시스템(XYZ). XYZ를 조회한다."
    mention = [m for m in resolve(snapshot, text) if m["surface"] == "XYZ"][-1]
    assert mention["link_decision"] == "AMBIGUOUS"
    assert "resolved_entity" not in mention
    assert mention["link_reason"] == "shared_alias"
    assert {m["entity_id"] for m in mention["prediction_set"]["members"]} == {
        "project:billing", "project:finance", "project:other",
    }
    assert resolve(snapshot, "XYZ")[0]["resolved_entity"]["entity_id"] == "project:other"


def test_recovery_returns_candidates_with_original_offsets():
    snapshot = make_snapshot(
        {"key": "power", "canonical": "한국전력", "surfaces": ["한전"]},
        {"key": "ministry", "canonical": "과학기술정보통신부"},
        {"key": "server", "canonical": "Domain Name System"},
    )
    text = "🔌 gkswjs, 한국전려에서도, 과기정통부는 DNS와 논의했다."
    mentions = resolve(snapshot, text)
    assert len(mentions) == 4
    for mention, (surface, full, channel, key) in zip(mentions, [
        ("gkswjs", "gkswjs", "keyboard", "power"),
        ("한국전려", "한국전려에서도", "jamo", "power"),
        ("과기정통부", "과기정통부는", "abbrev", "ministry"),
        ("DNS", "DNS와", "abbrev", "server"),
    ]):
        assert mention["surface"] == surface
        assert channel in mention["generation_channels"]
        assert mention["link_decision"] == "AMBIGUOUS"
        assert mention["link_reason"] == "recovery_candidate_only"
        assert mention["prediction_set"]["members"] == [{"kind": "ENTITY", "entity_id": f"project:{key}"}]
        offsets = mention["full_span"]["codepoint"]
        assert text[offsets["start"]:offsets["end"]] == full
    assert not resolve(snapshot, text, recover=False)
    assert not resolve(snapshot, "한 명, 한 개. 국부. AB.")


def test_disabled_recovery_and_restricted_local_remain_uncommitted():
    snapshot = min_api["compile_snapshot"]({
        "schema_version": 3,
        "entities": [{"entity_id": "power", "canonical": "한국전력"}],
        "alias_bindings": [{"entity_id": "power", "surface": "한국전력",
                            "fuzzy_policy": {"enabled": False, "keyboard_recovery": False},
                            "scope": {"allow": {"departments": ["energy"]}}}],
    })
    assert not resolve(snapshot, "한국전려 gksrnrwjsfur", department="energy")
    mentions = resolve(snapshot, "한국전력(BX). BX는 응답했다.", recover=False)
    assert len(mentions) == 2 and all(m["link_decision"] == "AMBIGUOUS" for m in mentions)


def test_doc_local_does_not_bypass_normalized_registered_restriction():
    snapshot = min_api["compile_snapshot"]({
        "schema_version": 3,
        "entities": [{"entity_id": "org", "canonical": "긴이름기관"}],
        "alias_bindings": [{"entity_id": "org", "surface": "긴이름기관"},
                           {"entity_id": "org", "surface": "AP",
                            "scope": {"allow": {"departments": ["energy"]}}}],
    })
    text = "긴이름기관(ap). ＡＰ와 ap는 참여했다."
    m = [m for m in resolve(snapshot, text) if m["surface"] == "ＡＰ"][0]
    assert m["link_decision"] == "AMBIGUOUS"
    assert m["link_reason"] == "eligibility_unconfirmed"
    excluded = resolve(snapshot, text, department="finance")
    assert [m["surface"] for m in excluded] == ["긴이름기관"]


def test_dense_edit_bucket_retains_all_one_jamo_neighbors():
    names = {"한국공공기관" + chr(0xAC00 + i): {} for i in range(550)}
    index = min_api["_RecoveryIndex"](SimpleNamespace(aliases=names))
    query = unicodedata.normalize("NFD", "한국공공기관각")
    expected = {name for name in names
                if min_api["_one_edit"](query, unicodedata.normalize("NFD", name))}
    assert expected
    assert index.typos(query) == expected

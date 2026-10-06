"""A company name in a sports sentence names the team, not the company.

`대한항공 7연승`, `프로배구 한국전력 KB손보 꺾고`, `kt 박세진 2⅔이닝 5실점`:
the string is exactly the registered company, so the exact channel
committed the company — every one of 244 such occurrences across the six
cached corpora. The glossary declares which entities have a namesake
(`metadata.namesakes`); `ktrf.context_cues` says what the namesake's
sentences look like. The commit is withheld and the candidate kept.

The cases below are taken from those corpora, including the ones the cues
had to be narrowed for.
"""

from __future__ import annotations

import pytest

from ktrf import compile_snapshot, load_glossary, resolve
from ktrf.context_cues import namesake_cue
from ktrf.glossary import GlossaryError


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary("examples/realorg_glossary.yaml"),
                            strict=False)


def _first(snap, text, surface):
    for m in resolve(snap, text)["mentions"]:
        if m["surface"] == surface:
            return m
    raise AssertionError(f"{surface!r} not found in {text!r}")


TEAM = [
    ("프로배구 한국전력 KB손보 꺾고 탈꼴찌…가빈 45점 원맨쇼", "한국전력"),
    ("앞으로 가는 대한항공 7연승…뒤로 가는 KB손보 10연패", "대한항공"),
    ("kt 박세진 2⅔이닝 5실점…2경기 연속 조기 강판", "kt"),
    ("박기원 대한항공 감독 통합우승 위해 남은 경기 총력전", "대한항공"),
    ("한전 장병철 감독 가빈 큰 부상 아니야…일주일 휴식", "한전"),
    ("김진욱 kt 감독 니퍼트 부진 예상했던 결과", "kt"),
    ("수원청년지원센터kt wiz 청소년문화활성화 협약", "kt"),
    ("리브 샌드박스가 2주차 KT 롤스터를 상대로 승리를 거뒀다.", "KT"),
    ("이스트로가 KT 핑거붐을 꺾고 프로리그 정상에 올랐다.", "KT"),
]


@pytest.mark.parametrize("text,surface", TEAM)
def test_a_team_use_withholds_the_company(snap, text, surface):
    m = _first(snap, text, surface)
    assert m["link_decision"] != "RESOLVED", m
    blocked = [x.get("commit_blocked") for x in m["prediction_set"]["members"]]
    assert "namesake_context:sports_team" in blocked
    # the reading is kept, only the commit is withheld (invariant ④)
    assert any(x.get("entity_id") for x in m["prediction_set"]["members"])


COMPANY = [
    # the cue words the first version matched inside other words
    ("KT 기가지니 홈트레이닝 서비스 출시", "KT"),         # 이닝 in 트레이닝
    ("KT 휴대형 위즈스틱 앞세워 보안 사업 확대", "KT"),  # 위즈 in a product
    ("KT 수원KT위즈파크 5G 스타디움 구축", "KT"),        # the stadium network
    ("열연강판 등 가격 하락 한전 전기요금 인상도 부담", "한전"),  # 강판 = steel
    # partnership stories: `잡고` lives inside `손잡고`
    ("KT가 리벨리온과 손잡고 국산 AI 반도체를 이용해 GPU팜을 구축한다.", "KT"),
    ("현대카드가 대한항공과 손잡고 직원용 특별 유니폼을 제작했다.", "대한항공"),
    # finance: `경기`, `시즌`, `감독` are not cues
    ("올 여름은 경기회복으로 한전 전력 사용량이 크게 증가할 전망이다.", "한전"),
    ("KT는 OTT 플랫폼 시즌을 운영한다.", "KT"),
    ("금융감독원은 KT의 공시를 검토했다.", "KT"),
]


@pytest.mark.parametrize("text,surface", COMPANY)
def test_company_news_still_commits(snap, text, surface):
    m = _first(snap, text, surface)
    blocked = [x.get("commit_blocked") for x in m["prediction_set"]["members"]]
    assert "namesake_context:sports_team" not in blocked, (text, blocked)


def test_the_cue_is_read_in_the_mentions_own_sentence():
    text = "한전은 전기요금을 동결했다. 프로배구 우리카드는 5연승을 달렸다."
    assert namesake_cue(text, (0, 2), ["sports_team"]) is None
    assert namesake_cue("프로배구 한전 5연승.", (5, 7), ["sports_team"])


def test_undeclared_entities_are_untouched(snap):
    """`삼성전자` has no namesake declared — its teams are 삼성 라이온즈 and
    삼성 썬더스, not 삼성전자 — so a sports cue in its sentence is noise."""
    m = _first(snap, "삼성전자 임직원 야구단 5연승 기념 행사", "삼성전자")
    assert m["link_decision"] == "RESOLVED"


def test_a_namesake_kind_must_exist():
    doc = {"schema_version": 3,
           "entities": [{"entity_id": "E1", "canonical": "가나다",
                         "metadata": {"namesakes": ["sport_team"]}}],
           "alias_families": [], "alias_bindings": []}
    with pytest.raises(GlossaryError, match="unknown namesake"):
        load_glossary(doc)
    doc["entities"][0]["metadata"]["namesakes"] = "sports_team"
    with pytest.raises(GlossaryError, match="list of strings"):
        load_glossary(doc)


def test_declaring_a_namesake_changes_the_snapshot_identity():
    """It changes answers, so it must change the id that names them."""
    import copy

    import yaml

    with open("examples/realorg_glossary.yaml", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    plain = copy.deepcopy(doc)
    for e in plain["entities"]:
        e.get("metadata", {}).pop("namesakes", None)
    a = compile_snapshot(load_glossary(doc), strict=False).snapshot_id
    b = compile_snapshot(load_glossary(plain), strict=False).snapshot_id
    assert a != b


@pytest.mark.parametrize("text,surface,blocked", [
    ("프로배구 대한항궁 삼성화재에 역전승", "대한항궁", True),    # jamo
    ("gkswjs 장병철 감독 가빈 만족", "gkswjs", True),            # keyboard
    ("한국전럭이 전기요금을 올렸다", "한국전럭", False),         # control
])
def test_recovered_typos_face_the_same_rule(snap, text, surface, blocked):
    """A typo of the name arrives through jamo or keyboard recovery, not the
    exact channel, and only fell below the commit threshold by accident of
    calibration. The rule is applied after every merge so no channel, and
    no merge of unblocked evidence, can carry the company past it."""
    m = _first(snap, text, surface)
    reasons = {x.get("commit_blocked") for x in m["prediction_set"]["members"]
               if x.get("entity_id")}
    assert ("namesake_context:sports_team" in reasons) is blocked, reasons

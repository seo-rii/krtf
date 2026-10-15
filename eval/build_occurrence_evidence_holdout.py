"""Author a source-first holdout for occurrence-specific Korean evidence.

All prose and glossary meanings below are AI-authored synthetic material, not
collected service documents or an independent human audit. Labels and source
quotes are specified before any selector or model is run. This module imports
neither ranking nor evidence-selection code and never reads model outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

VERSION = "occurrence_evidence_holdout_authoring_v1"
DEFAULT_OUTPUT = Path(__file__).parent / "fixtures" / "occurrence_evidence_holdout" / "families.jsonl"

# Alias, domain, then two distinct catalog entries. The final two strings of
# each entry are authored source paraphrases, not copied dictionary definitions.
FAMILY_SPECS = (
    ("은결", "manuscript_conservation", (
        ("고문서 산성 중화팀", "오래된 종이의 산도를 측정하고 산성 성분을 줄여 훼손을 늦추는 팀",
         "오래된 종이가 누렇게 부스러지는 문제를 다룬다. 종이 조각의 pH를 재고 손상을 줄일 약액 처리 여부를 정해 달라.",
         "책장을 더 넘기기 전에 종이에 남은 산 성분을 낮추는 처치를 검토한다. 글씨의 뜻을 읽어 주는 일은 요청하지 않았다."),
        ("고문서 필체 판독팀", "옛 문서의 흘림 글씨를 읽고 현대 문자로 옮겨 내용을 확인하는 팀",
         "조선 시대 편지에 흘려 쓴 획을 읽기 어렵다. 확대 사진에서 글자 모양을 비교해 오늘날 글자로 풀어 적어 달라.",
         "번진 먹 자국 때문에 읽지 못한 이름을 주변 문장과 대조한다. 종이의 화학적 상태를 바꾸는 작업은 하지 않는다."))),
    ("시온", "observatory", (
        ("관측 영상 시각 정렬팀", "천체 사진의 기록 시각을 표준 시계와 맞추어 관측 순서를 바로잡는 팀",
         "별을 찍은 파일에 표시된 시계가 기준보다 몇 초씩 늦다. 같은 섬광이 나타난 순간을 맞춰 촬영 순서를 바로잡아 달라.",
         "하늘의 밝기가 바뀐 순간을 여러 파일에서 찾아 시간표를 겹친다. 렌즈 표면을 닦는 작업은 별도 일정으로 둔다."),
        ("망원경 거울 세척팀", "망원경 반사경의 먼지와 오염을 제거하고 표면 상태를 확인하는 팀",
         "둥근 반사판에 먼지가 붙어 별빛이 번져 보인다. 코팅을 긁지 않도록 표면의 이물질을 씻어 내고 얼룩을 살펴 달라.",
         "빛을 모으는 거울에 남은 자국을 없애되 보호막이 벗겨지지 않게 한다. 사진의 촬영 시간을 수정하는 일은 없다."))),
    ("루아", "glass_workshop", (
        ("유리 가마 소성팀", "유리 작품을 가마에서 가열하고 식히는 온도 곡선을 운용하는 팀",
         "완성품에 금이 가지 않게 화덕의 열을 천천히 낮춰야 한다. 두꺼운 유리의 속과 겉이 비슷하게 식도록 시간을 잡아 달라.",
         "불을 켠 뒤 최고 열까지 올리는 속도와 식혀 둘 시간을 작업표에 적는다. 색을 내는 가루의 조합은 건드리지 않는다."),
        ("유리 색안료 배합팀", "유리 제작에 사용할 색 재료의 비율을 정하고 시험 색상을 비교하는 팀",
         "투명한 재료에 섞을 푸른색과 노란색 가루의 양을 달리해 작은 견본을 만든다. 원하는 초록빛에 가까운 비율을 골라 달라.",
         "같은 조명 아래서 견본의 빛깔을 대조해 색 재료를 얼마나 넣을지 정한다. 화덕을 달구는 시간표는 이번 대상이 아니다."))),
    ("나린", "coastal_geoscience", (
        ("해저 지진파 해석팀", "해저 계측기의 진동 기록을 분석해 지진 발생 위치와 특성을 추정하는 팀",
         "바다 밑 센서마다 흔들림이 도착한 시각이 다르다. 파형 사이 간격을 비교해 어느 해역에서 진동이 시작됐는지 계산해 달라.",
         "파도가 만든 잡음을 빼고 땅속에서 전해 온 흔들림을 골라낸다. 해변 모래가 줄어든 폭을 재는 일과는 구별한다."),
        ("연안 모래 침식 측량팀", "해안선과 모래층의 변화를 반복 측정하여 해변 침식 범위를 파악하는 팀",
         "지난달보다 백사장의 폭이 좁아졌다는 신고가 왔다. 물이 빠진 때 같은 기준점에서 모래턱까지 거리를 다시 재어 달라.",
         "해변 단면을 전과 같은 선에서 측량해 사라진 모래의 양을 비교한다. 바다 밑 진동 파형을 해석할 필요는 없다."))),
    ("수안", "performing_arts", (
        ("공연 악보 대여팀", "합주에 필요한 파트별 악보의 대여 부수와 반환 상태를 관리하는 팀",
         "이번 합주에 쓸 바이올린과 첼로 파트 종이가 부족하다. 연주자 수만큼 빌려 주고 공연 뒤 돌아온 부수를 확인해 달라.",
         "연주용 종이에 표시한 활 방향이 사라지지 않게 보관하며 누가 어느 파트를 가져갔는지 기록한다. 의상은 접수하지 않는다."),
        ("무대 의상 수선팀", "공연 의상의 치수와 손상 부위를 고쳐 출연자가 착용할 수 있게 하는 팀",
         "배우의 옷소매가 동작 중 걸리고 단추도 하나 빠졌다. 몸에 맞게 길이를 줄이고 뜯어진 곳을 다시 꿰매 달라.",
         "출연자가 입어 본 뒤 허리선을 조정하고 다음 장면 전에 찢어진 천을 덧댄다. 연주용 종이를 빌리는 요청은 없다."))),
    ("여민", "animal_fieldwork", (
        ("반려동물 접종 예약팀", "반려동물의 예방 접종 방문 예약과 접종 이력 확인을 담당하는 팀",
         "보호자가 기르는 강아지를 데려올 날짜를 묻는다. 이전에 맞은 예방 주사 기록을 확인한 뒤 수의사가 보는 시간을 잡아 달라.",
         "보호자의 연락처와 방문 가능한 날을 받아 진료 예약표에 적는다. 야외에서 새의 이동을 따라가는 조사와는 관계없다."),
        ("야생 조류 이동 관찰팀", "야생 새의 표식과 관찰 위치를 기록하여 계절별 이동 경로를 조사하는 팀",
         "갯벌에서 다리에 번호표를 찬 새를 보았다. 망원경으로 숫자를 읽고 발견 위치와 날짜를 남겨 다음 관찰 지점과 이어 달라.",
         "같은 표식이 다른 지역에 나타났는지 비교해 계절에 따라 옮겨 간 길을 그린다. 집에서 기르는 동물의 진료는 받지 않는다."))),
    ("가림", "orchard_ecology", (
        ("꿀벌 군체 월동팀", "벌통의 겨울 먹이와 보온 상태를 살펴 꿀벌 군체의 월동을 돕는 팀",
         "추위가 오기 전 벌집 안에 겨울 먹이가 충분한지 살핀다. 통풍을 막지 않는 선에서 벌통의 빈틈을 줄이고 보온 덮개를 마련해 달라.",
         "밖으로 나갈 수 없는 날에도 벌 무리가 버틸 저장량을 확인한다. 과수 꽃에 가루를 묻히는 작업은 아직 시작하지 않는다."),
        ("과수 꽃가루 수분팀", "과수의 개화 시기에 맞춰 꽃가루를 확보하고 인공 수분 작업을 진행하는 팀",
         "배나무 꽃이 열린 짧은 기간에 열매가 맺히도록 해야 한다. 다른 품종에서 받은 가루를 암술에 고르게 묻히는 순서를 정해 달라.",
         "비가 오기 전에 피어 있는 꽃을 골라 작은 붓으로 작업한다. 겨울철 벌통을 감싸는 일은 이번 요청에 없다."))),
    ("이솔", "fluid_experiments", (
        ("항공 풍동 실험팀", "바람 통로에서 항공기 모형에 작용하는 힘과 유동을 측정하는 팀",
         "작은 비행기 모형을 고정하고 정면에서 바람을 보낸다. 날개 각도를 바꿀 때 위로 뜨는 힘과 공기 흐름이 어떻게 달라지는지 재어 달라.",
         "연기를 흘려 날개 뒤에 소용돌이가 생기는 위치를 살핀다. 물에 띄운 배를 끌어당기는 실험은 수행하지 않는다."),
        ("선체 수조 저항팀", "시험 수조에서 선박 모형을 끌어 선체가 받는 물의 저항을 측정하는 팀",
         ("긴 물탱크에 작은 배를 띄우고 같은 속도로 끌어 본다. 앞부분 모양을 바꿨을 때 줄에 걸리는 힘이 얼마나 달라지는지 기록해 달라."),
         "배 옆에서 생기는 물결을 촬영하고 움직이는 데 필요한 힘을 비교한다. 비행기 날개에 바람을 보내는 시험과는 별개다."))),
    ("오름", "space_communications", (
        ("전파 간섭 주파수팀", "송신 설비 사이의 전파 간섭을 분석하고 사용할 주파수를 조정하는 팀",
         "서로 가까운 송신기가 같은 대역을 써서 수신음이 깨진다. 스펙트럼에서 겹치는 구간을 찾고 한쪽 채널을 옮길 범위를 정해 달라.",
         "안테나별 출력과 사용 대역을 비교해 섞여 들어오는 신호를 줄인다. 우주 물체가 지나가는 길을 계산하는 요청은 아니다."),
        ("위성 궤도 충돌팀", "인공위성과 우주 물체의 예상 궤적을 비교해 충돌 접근 위험을 계산하는 팀",
         "위성과 오래된 파편이 비슷한 시각에 같은 구간을 지날 수 있다. 앞으로의 위치를 계산해 둘 사이의 가장 가까운 거리를 구해 달라.",
         "관측 때마다 달라진 위치를 반영해 접근 경보를 다시 확인한다. 지상 송신기의 채널을 바꾸는 일은 포함하지 않는다."))),
    ("소율", "accessible_media", (
        ("촉지도 점자 교정팀", "손으로 읽는 안내도의 점자와 돌출 표기가 올바른지 교정하는 팀",
         "손끝으로 읽는 층별 안내판에 몇 점이 빠져 방 번호가 다르게 읽힌다. 돌출된 점의 배열과 방향 표기를 원본과 대조해 고쳐 달라.",
         "벽에 붙이기 전에 이용자가 만져 볼 견본을 준비하고 잘못 찍힌 기호를 수정한다. 방송 출연자의 손동작을 옮기는 작업은 없다."),
        ("수어 방송 통역팀", "방송 발언을 수어로 통역하고 화면 속 통역 전달 상태를 확인하는 팀",
         "재난 안내를 귀로 듣기 어려운 시청자도 바로 이해해야 한다. 진행자의 말을 손동작과 표정으로 전달할 통역사를 배치해 달라.",
         "화면 한쪽에서 통역사의 손이 잘리지 않게 구도를 맞추고 발언과 동작의 흐름을 점검한다. 돌출된 안내판의 점 배열은 다루지 않는다."))),
    ("리안", "sport_integrity", (
        ("경기 결승선 사진팀", "결승선 고속 사진의 통과 위치를 판독하여 선수 도착 순서를 확인하는 팀",
         "두 선수가 거의 동시에 선을 넘어 육안으로 순서를 가릴 수 없다. 마지막 선을 찍은 고속 화면에서 몸통이 닿은 위치를 확대해 달라.",
         "카메라의 같은 세로선을 기준으로 통과한 순간을 비교해 심판에게 순서를 전달한다. 검사 용기를 봉하는 절차는 요청하지 않았다."),
        ("선수 도핑 시료 봉인팀", "선수 검사 시료의 용기를 봉인하고 식별 번호와 인계 기록을 확인하는 팀",
         "검사 때 받은 소변을 두 개의 전용 병에 나눠 담은 뒤 뚜껑이 다시 열리지 않게 잠근다. 병 번호와 인수 서명이 같은지 확인해 달라.",
         "받은 사람에게 넘어갈 때까지 용기의 손상 여부를 기록하고 봉인 번호를 맞춘다. 결승선을 찍은 사진은 판독하지 않는다."))),
    ("다율", "civil_monitoring", (
        ("터널 지반 침하팀", "터널 주변 지표의 높이 변화를 측정하여 지반 침하를 감시하는 팀",
         "지하 굴착 뒤 도로의 높이가 조금씩 낮아지는지 확인해야 한다. 기준점에서 지표 표식을 다시 재어 지난주 수치와 차이를 적어 달라.",
         "같은 위치에서 반복해 측정한 높이를 시간순으로 묶고 갑자기 내려간 곳을 알린다. 다리를 매단 줄의 힘은 이번 관측 대상이 아니다."),
        ("교량 케이블 장력팀", "다리를 지지하는 케이블의 장력 변화를 측정하고 이상 여부를 감시하는 팀",
         "강을 건너는 다리의 굵은 줄이 평소와 다르게 흔들린다. 진동 주기를 재어 줄에 걸린 힘이 설계 때와 얼마나 다른지 확인해 달라.",
         "주변 온도를 함께 기록하며 지지선마다 당기는 힘을 비교한다. 지하 굴착 주변의 땅 높이를 재는 일과 구분한다."))),
)

NEUTRAL_NOTES = (
    ("[문서 보관]\n접수 원본은 날짜별 묶음에 넣었다. 첨부의 순서가 바뀌어도 본문의 단락 번호는 유지한다. 수정 이력에는 실제로 고친 줄만 남긴다.",
     "[전달 방식]\n담당자가 자리를 비우면 공용함에 같은 자료를 한 번만 올린다. 확인 회신에는 접수 번호를 쓰되 개인 연락처를 추가하지 않는다."),
    ("[회의 운영]\n서기는 논의 항목마다 별도 페이지를 만들었다. 중간에 쉬는 시간이 있었지만 의결된 범위는 바뀌지 않았다. 회의 참석 여부는 별지에서 확인한다.",
     "[후속 기록]\n추가 사진은 촬영 날짜 순서대로 묶는다. 표지가 빠진 자료는 보내기 전에 보완하고, 확인되지 않은 숫자에는 검토 표시를 남긴다."),
    ("[티켓 이력]\n첨부가 여러 번 도착해도 새 번호를 만들지 않는다. 이전에 받은 파일은 삭제하지 않고 새 파일과 나란히 두며, 수정 이유를 한 줄 적는다.",
     "[마감 안내]\n급하지 않은 질문은 다음 근무일에 묶어 회신한다. 인수자가 바뀌면 아직 답하지 않은 항목을 넘기고, 완료 시각은 처리 뒤에 기입한다."),
)


def _opaque_key(family_id, side):
    return "e_" + hashlib.sha256(f"occurrence-evidence-new-family:{family_id}:{side}".encode()).hexdigest()[:16]


def _target(document_id, alias, terms, side, stratum, quotes, rationale, *,
            occurrence=0, label="LINK", surface=None):
    return {
        "target_id": f"{document_id}-t{occurrence + 1:02d}",
        "surface": surface or alias,
        "occurrence": occurrence,
        "gold": {"label": label, "entity_ref": "global:" + terms[side]["key"] if label == "LINK" else None},
        "stratum": stratum,
        "decisive_evidence": [{"document": "source", "quote": quote} for quote in quotes],
        "rationale": rationale,
    }


def _document(document_id, title, paragraphs, targets):
    return {"document_id": document_id, "title": title,
            "text": "\n\n".join(paragraphs), "targets": targets}


def build_families():
    """Return new source prose and gold without importing any inference code."""
    families = []
    for index, (alias, domain, meanings) in enumerate(FAMILY_SPECS, 1):
        family_id = f"ev{index:02d}"
        terms = [{"key": _opaque_key(family_id, side), "canonical": meaning[0],
                  "surfaces": [alias, meaning[0]], "short_definition": meaning[1]}
                 for side, meaning in enumerate(meanings)]
        note1, note2 = NEUTRAL_NOTES[(index - 1) % len(NEUTRAL_NOTES)]
        documents = []

        for kind in ("local", "remote"):
            for side, meaning in enumerate(meanings):
                document_id = f"{family_id}-d{len(documents) + 1:02d}"
                quoted_name = (kind, side) in {("local", 0), ("remote", 1)}
                if quoted_name:
                    opening = f"[수신 확인]\n이 문서에서 ‘{alias}’로 적은 수신자는 아래 작업을 맡는 부서다. 따옴표는 짧은 이름의 범위를 표시한 것이며 실제로 이쪽에 요청한다."
                elif index % 2:
                    opening = f"[업무 메일]\n아래 건을 {alias}에 배정해 달라. 발신자는 설명한 실무가 끝났다는 회신을 기다리며, 인수자는 같은 접수 번호를 사용한다."
                else:
                    opening = f"[진행 메모]\n이번 티켓의 수신 부서는 {alias}로 기입한다. 아래에 적은 일을 수행하는 쪽으로 자료를 넘기기로 참석자들이 합의했다."
                evidence = "[요청 내용]\n" + meaning[2] + " " + meaning[3]
                if kind == "local":
                    paragraphs = [opening, evidence, note1]
                else:
                    unrelated = (f"[별도 안건 색인]\n{meanings[1 - side][0]}의 예산 표지는 다른 회의 묶음에 있다. "
                                 f"{meanings[1 - side][0]}은 이 티켓의 수신처가 아니며 여기에는 그 안건을 합치지 않는다.")
                    paragraphs = [opening, note1, note2, unrelated, evidence]
                documents.append(_document(document_id, "처리 범위를 지정한 전달문", paragraphs, [
                    _target(document_id, alias, terms, side, f"paraphrase_{kind}_{'AB'[side]}",
                            [meaning[2], meaning[3]],
                            "해당 발생 위치의 배정문과 작업 설명이 같은 요청에 속한다. 이름만 인용한 경우도 바깥의 긍정 배정은 유효하다.")]))

        for order in ((0, 1), (1, 0)):
            document_id = f"{family_id}-d{len(documents) + 1:02d}"
            paragraphs = ["[독립 안건 두 건]\n서로 다른 요청을 같은 회의 메모에 적었다. 각 절의 수신자와 작업은 그 절 안에서만 짝을 이루며 다른 절에 넘겨 적용하지 않는다."]
            targets = []
            for occurrence, side in enumerate(order):
                section = f"[안건 {occurrence + 1}]\n수신자는 {alias}로 확정한다. " + meanings[side][2] + " " + meanings[side][3]
                paragraphs.append(section)
                targets.append(_target(document_id, alias, terms, side,
                    "multi_target_" + "".join("AB"[part] for part in order), [section],
                    "동일한 글자가 두 업무에 각각 쓰였다. 지시한 발생 위치가 포함된 안건의 업무만 정답을 결정한다.", occurrence=occurrence))
            paragraphs.append("[분리 처리]\n결과 파일도 안건별로 보관한다. 한쪽 수신자의 회신이 왔더라도 나머지 요청을 끝낸 것으로 표시하지 않는다.")
            documents.append(_document(document_id, "두 안건의 수신자별 조치", paragraphs, targets))

        for side, meaning in enumerate(meanings):
            document_id = f"{family_id}-d{len(documents) + 1:02d}"
            other = meanings[1 - side][0]
            exclusion = (f"[수신 제외]\n{other}에 넘기는 안은 채택하지 않았다. "
                         f"{other}은 이번 요청을 받지 않으며, 첨부 표지에 남은 {other} 표기는 실제 배정을 뜻하지 않는다.")
            binding = f"[실제 배정]\n현재 요청을 받는 쪽은 {alias}다. " + meaning[2] + " " + meaning[3]
            # Counterbalance whether the exclusion comes before or after the
            # positive paragraph. The source still gives one unambiguous job.
            paragraphs = [exclusion, note1, binding] if index % 2 else [binding, note1, exclusion]
            documents.append(_document(document_id, "접수 대상 정정 통지", paragraphs, [
                _target(document_id, alias, terms, side, f"negated_decoy_{'AB'[side]}",
                        [exclusion, binding],
                        "반복된 다른 후보의 이름은 명시적으로 제외됐다. 긍정 배정과 구체적인 작업을 함께 읽어 실제 조직을 고른다.")]))

        document_id = f"{family_id}-d09"
        quoted = f"[교정 원문]\n‘{alias}는 {meanings[0][0]}이다’라는 한 문장을 시험용 오류 예문으로 인쇄했다."
        rejected = "[검토자의 판정]\n인용된 문장 전체는 지워야 할 허위 단정이다. 여기서는 글자열의 삭제 여부만 검사하며, 실제 업무 수신자를 가리키거나 사전의 의미를 승인하지 않는다."
        documents.append(_document(document_id, "인용된 오류 문장의 삭제 검사", [quoted, rejected, note2], [
            _target(document_id, alias, terms, 0, "quoted_rejected_definition", [quoted, rejected],
                    "인용 전체가 거부된 교정 문자열이다. 실제 조직을 지칭하는 배정이 없으므로 이름 부분만 떼어 연결하면 안 된다.", label="NON_MENTION")]))

        document_id = f"{family_id}-d10"
        role = alias + "팀장"
        personal = f"[결재선 확인]\n최종 서명자는 {role}으로 정했다. " + meanings[0][2]
        person_scope = "[서명자의 범위]\n이 칸에는 그 부서를 이끄는 개인 한 명이 서명해야 한다. 조직 전체나 부서 공용함의 식별자는 개인 결재자의 신분을 대신할 수 없다."
        documents.append(_document(document_id, "조직과 개인 서명자의 분리", [personal, person_scope, note1], [
            _target(document_id, alias, terms, 0, "role_derivative", [personal, person_scope],
                    "조직 약칭을 포함하지만 전체 표면형은 책임자 개인을 뜻한다. core가 연결될 여지와 별개로 조직 ID를 전체 대상에 넣을 수 없다.",
                    label="COMPOSITIONAL", surface=role)]))

        document_id = f"{family_id}-d11"
        object_kind = ("도예 작품", "보드게임", "실내 화분")[index % 3]
        named = f"[외부 소식]\n동호회에서 만든 {object_kind}에 {alias}라는 이름을 붙였다. 이 대목은 물건 자체를 소개하며 부서의 별칭을 사용한 것이 아니다."
        absent = "[분류 확인]\n그 대상은 외부 모임의 소유물이고 회사 용어 사전에는 등록돼 있지 않다. 이름이 같아도 업무 조직으로 분류하지 않으며 문의는 모임 운영자에게 돌린다."
        documents.append(_document(document_id, "등록되지 않은 외부 대상의 소개", [named, absent, note2], [
            _target(document_id, alias, terms, 0, "unregistered_named_object", [named, absent],
                    "이 발생 위치는 실제 이름이 붙은 외부 물건을 지칭하지만 두 등록 조직 어느 쪽도 아니다. 비언급과 구별되는 NIL이다.", label="NIL")]))

        document_id = f"{family_id}-d12"
        unclear = f"[전달 보류]\n작성자가 수신자 칸에 {alias}만 써 놓았고 요청 본문은 비워 뒀다. 제목에도 해야 할 일이나 연락 목적을 남기지 않았다."
        both = f"[현재 명부]\n{meanings[0][0]}과 {meanings[1][0]}은 모두 운영 중인 부서이며 같은 짧은 이름을 쓴다. 어느 쪽을 택했는지 알려 줄 첨부나 이전 대화는 없다."
        documents.append(_document(document_id, "수신 부서가 미확인인 빈 요청", [unclear, both, note1], [
            _target(document_id, alias, terms, 0, "genuinely_ambiguous", [unclear, both],
                    "두 등록 후보 모두 가능하며 발생 위치에 결부된 실무 근거가 없다. 임의의 하나를 정답으로 지정하지 않는다.", label="AMBIGUOUS")]))

        knowledge_text = (f"공유 약칭 {alias}는 서로 다른 두 부서에 등록돼 있다. 본문에서 맡은 일을 확인한 뒤 대상을 구별해야 한다.\n\n"
                          + "\n\n".join(f"{term['canonical']}: {term['short_definition']}. 등록 ID global:{term['key']}." for term in terms)
                          + "\n\n책임자 개인, 외부 물건, 거부된 인용문은 위 조직 ID에 자동으로 합치지 않는다.")
        families.append({
            "family_id": family_id, "domain": domain, "protocol_version": VERSION,
            "annotation_origin": "AI_AUTHORED_SYNTHETIC", "human_verified": False,
            "authoring_method": "New source prose and glossary meanings with labels and quotations authored before any selector or inference; no score or prediction was consulted.",
            "evaluation_history": "Fresh family-disjoint synthetic holdout; not an independent human audit or deployment risk estimate.",
            "terms": terms,
            "knowledge_document": {"document_id": "kb-" + family_id, "title": alias + "의 등록 의미", "text": knowledge_text},
            "documents": documents,
        })
    validate_families(families)
    return families


def validate_families(families):
    if len(families) != 12 or {family["family_id"] for family in families} != {f"ev{i:02d}" for i in range(1, 13)}:
        raise ValueError("12 fresh complete glossary families are required")
    expected_labels = Counter({"LINK": 10, "NON_MENTION": 1, "COMPOSITIONAL": 1, "NIL": 1, "AMBIGUOUS": 1})
    expected_strata = Counter({"paraphrase_local_A": 1, "paraphrase_local_B": 1,
        "paraphrase_remote_A": 1, "paraphrase_remote_B": 1, "multi_target_AB": 2,
        "multi_target_BA": 2, "negated_decoy_A": 1, "negated_decoy_B": 1,
        "quoted_rejected_definition": 1, "role_derivative": 1,
        "unregistered_named_object": 1, "genuinely_ambiguous": 1})
    alias_names, catalog_keys, canonical_names, document_ids, target_ids = set(), set(), set(), set(), set()
    for family in families:
        if family["annotation_origin"] != "AI_AUTHORED_SYNTHETIC" or family["human_verified"] is not False:
            raise ValueError("AI authorship and lack of human validation must be disclosed")
        terms = family["terms"]
        if len(terms) != 2 or terms[0]["surfaces"][0] != terms[1]["surfaces"][0]:
            raise ValueError("each fixed catalog must contain two colliding meanings")
        alias = terms[0]["surfaces"][0]
        if alias in alias_names:
            raise ValueError("new families require distinct aliases")
        alias_names.add(alias)
        for term in terms:
            if term["key"] in catalog_keys or term["canonical"] in canonical_names:
                raise ValueError("catalog keys and canonical names must be unique")
            catalog_keys.add(term["key"])
            canonical_names.add(term["canonical"])
        if len(family["documents"]) != 12:
            raise ValueError("each family requires 12 source documents")
        targets = [target for document in family["documents"] for target in document["targets"]]
        if Counter(target["gold"]["label"] for target in targets) != expected_labels:
            raise ValueError("each family requires 10 positive and four distinct abstention events")
        if Counter(target["stratum"] for target in targets) != expected_strata:
            raise ValueError("all occurrence and polarity strata must be present")
        valid_refs = {"global:" + term["key"] for term in terms}
        for document in family["documents"]:
            if document["document_id"] in document_ids:
                raise ValueError("source IDs must be unique")
            document_ids.add(document["document_id"])
            text = document["text"]
            if not 100 <= len(text) <= 650:
                raise ValueError("source texts must contain 100–650 meaningful characters")
            if text.count(alias) != len(document["targets"]):
                raise ValueError("every alias occurrence must have exactly one authored target")
            for target in document["targets"]:
                if target["target_id"] in target_ids:
                    raise ValueError("target IDs must be unique")
                target_ids.add(target["target_id"])
                positions = [offset for offset in range(len(text)) if text.startswith(target["surface"], offset)]
                if target["occurrence"] >= len(positions):
                    raise ValueError("the designated surface occurrence must exist")
                gold = target["gold"]
                if ((gold["label"] == "LINK" and gold["entity_ref"] not in valid_refs)
                        or (gold["label"] != "LINK" and gold["entity_ref"] is not None)):
                    raise ValueError("gold must identify an exact catalog candidate or explicitly abstain")
                for evidence in target["decisive_evidence"]:
                    if evidence["document"] != "source" or evidence["quote"] not in text:
                        raise ValueError("all decisive evidence must be a source substring")
                if target["stratum"].startswith("paraphrase_"):
                    winner = next(term for term in terms if "global:" + term["key"] == gold["entity_ref"])
                    if winner["canonical"] in text or any(term["short_definition"] in text for term in terms):
                        raise ValueError("positive source paraphrases must not copy the answer name or dictionary definition")


def encoded_fixture(families):
    return "".join(json.dumps(family, ensure_ascii=False, separators=(",", ":")) + "\n" for family in families)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Verify the frozen fixture matches authored source")
    args = parser.parse_args(argv)
    families = build_families()
    encoded = encoded_fixture(families)
    if args.check:
        if args.output.read_text(encoding="utf-8") != encoded:
            raise SystemExit("fixture differs from deterministic authoring")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({"protocol_version": VERSION, "families": len(families),
                      "documents": 144, "targets": 168, "link_targets": 120,
                      "abstention_targets": 48, "human_verified": False,
                      "fixture_sha256": hashlib.sha256(encoded.encode()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

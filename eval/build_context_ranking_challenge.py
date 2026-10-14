"""Author a deterministic, new-family Korean target-context challenge.

This is AI-authored synthetic evaluation data, not independently collected
service documents or a human audit. No model scores, resolver outputs, or old
experiment results are consulted when constructing documents and labels.
All 24 glossary families are new; every target retains the full two-entity
catalog rather than selecting candidates using its authored answer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

VERSION = "context_ranking_challenge_authoring_v1"
DEFAULT_OUTPUT = Path(__file__).parent / "fixtures" / "context_ranking_challenge" / "families.jsonl"

# alias, domain, and two independently specified meanings. Each meaning has a
# canonical name, dictionary definition, and two source-document paraphrases.
# Paraphrases intentionally avoid copying the canonical or definition verbatim.
FAMILY_SPECS = (
    ("솔비", "inventory", (
        ("원자재 입고 조정팀", "공급된 원자재의 도착 시간을 조율하고 하역 순서를 정하는 팀",
         "오늘 들어오는 금속판을 어느 하역장부터 내릴지 정하고, 공급업체와 트럭 도착 시각을 맞추는 부서가 이 일을 맡는다.",
         "납품 차량이 한꺼번에 몰리지 않도록 시간을 나누며, 재료를 내려놓을 자리도 미리 배정한다."),
        ("실물 재고 실사팀", "창고에 보관된 물품의 실제 수량을 세고 장부 차이를 확인하는 팀",
         "선반마다 상자를 직접 세어 전산에 적힌 개수와 맞추고, 수치가 다른 품목을 다시 확인하는 부서가 이 일을 맡는다.",
         "창고 칸을 순서대로 돌며 남은 물건을 세고, 기록보다 많거나 적은 이유를 별도 표에 적는다."))),
    ("보담", "equipment_energy", (
        ("장비 교정 예약팀", "측정 장비의 정확도 교정 일정을 예약하고 대체 기기를 배정하는 팀",
         "저울과 온도계를 기준 기기와 비교할 날짜를 잡고, 그동안 사용할 여분 기계를 마련하는 부서가 이 일을 맡는다.",
         "측정 오차를 확인하는 외부 작업이 겹치지 않게 예약을 나누고, 작업자는 빈 기기를 빌려 쓴다."),
        ("작업장 전력 절감팀", "공장의 전기 사용 패턴을 분석하고 불필요한 전력 소비를 줄이는 팀",
         "생산이 멈춘 시간에도 켜진 설비를 찾아 전기를 덜 쓰게 하고, 시간대별 소비량을 살피는 부서가 이 일을 맡는다.",
         "빈 작업실의 조명과 유휴 모터가 쓰는 전기를 합산해, 꺼도 되는 설비의 운전 시간을 바꾼다."))),
    ("라온", "packaging", (
        ("친환경 포장 설계팀", "일회용 포장의 소재와 구조를 바꾸어 자원 사용을 줄이는 팀",
         "종이 상자의 접는 모양과 완충재 종류를 다시 정해, 한 번 쓰고 버리는 재료를 줄이는 부서가 이 일을 맡는다.",
         "같은 물건을 보호하면서도 테이프와 비닐을 적게 쓰도록 새 포장 도안을 만든다."),
        ("회수 용기 순환팀", "배송에 쓴 다회용 용기를 거두어 세척하고 다시 공급하는 팀",
         "배달 뒤 빈 통을 돌려받아 씻고, 다음 주문에 사용할 깨끗한 통을 점포에 보내는 부서가 이 일을 맡는다.",
         "한 번 사용한 플라스틱 상자는 버리지 않고 거둬 소독한 뒤 다른 배송에도 쓸 수 있게 배분한다."))),
    ("해솔", "language", (
        ("다국어 문안 번역팀", "국내 작성 문안을 해외 독자가 읽을 언어로 옮기는 팀",
         "한국어로 쓴 안내를 일본어와 프랑스어 독자가 이해하도록 다시 쓰는 부서가 이 일을 맡는다.",
         "각 나라 독자가 오해할 표현을 확인하며 원고를 다른 언어로 옮기고, 현지 담당자에게 뜻이 맞는지 묻는다."),
        ("음성 자료 전사팀", "녹음된 발화를 문자로 옮기고 말한 사람과 시각을 표시하는 팀",
         "인터뷰 소리를 들으면서 한 말을 글로 적고, 누가 언제 말했는지 줄마다 붙이는 부서가 이 일을 맡는다.",
         "녹음 파일에서 빠진 대목을 다시 듣고, 발언을 시작한 시각과 화자 이름을 문장 옆에 기록한다."))),
    ("도담", "storage_transport", (
        ("냉장 운송 편성팀", "온도 유지가 필요한 식품의 냉장 차량 운행을 편성하는 팀",
         "신선 식품이 이동하는 동안 차갑게 유지되도록 차량별 배송 구간과 출발 시각을 정하는 부서가 이 일을 맡는다.",
         "우유와 생선을 실을 차의 냉기를 확인하고, 이동 중 온도가 오르지 않을 노선에 배차한다."),
        ("상온 보관 배치팀", "냉각이 필요 없는 상품의 창고 보관 위치를 배정하는 팀",
         "굳이 차갑게 둘 필요가 없는 통조림과 건조 식품을 어느 선반에 쌓을지 정하는 부서가 이 일을 맡는다.",
         "실내 온도에서 두어도 되는 물건을 입출고 빈도에 따라 창고 칸에 나누어 놓는다."))),
    ("가온", "resource_circulation", (
        ("폐기물 분리 반출팀", "사업장 폐기물을 종류별로 나누어 적법한 수거처로 보내는 팀",
         "작업 뒤 남은 종이와 폐유를 섞지 않고 모아, 종류에 맞는 수거 업체에 인계하는 부서가 이 일을 맡는다.",
         "버릴 자재의 성질을 확인해 전용 통에 나누고, 반출 차량에는 인계 내역을 함께 넘긴다."),
        ("공업 용수 재이용팀", "사용한 공정수를 정화하여 다른 제조 공정에서 다시 쓰게 하는 팀",
         "설비를 씻고 나온 물에서 불순물을 걸러 다른 생산 단계에서도 쓸 수 있게 만드는 부서가 이 일을 맡는다.",
         "새 물을 더 받기 전에 이미 사용한 물을 처리해 세척용 배관으로 되돌려 보낸다."))),
    ("온새", "engineering", (
        ("도면 치수 개정팀", "설계 도면의 치수 변경 사항을 반영하고 개정판을 관리하는 팀",
         "설계자가 바꾼 길이와 구멍 간격을 그림에 반영하고, 현장에 예전 도안이 남지 않게 하는 부서가 이 일을 맡는다.",
         "새로 승인된 수치를 도면에 적어 판 번호를 올리고, 제작자에게 달라진 위치를 표시해 전달한다."),
        ("제품 부품 표준화팀", "여러 제품에 쓰는 부품의 규격을 통일하고 공용 품목을 정하는 팀",
         "기종마다 달랐던 나사와 브래킷 크기를 맞춰, 여러 모델이 같은 자재를 쓰게 하는 부서가 이 일을 맡는다.",
         "제품별로 따로 구매하던 작은 부품을 공통 규격으로 묶고, 어떤 모델에 함께 쓸 수 있는지 표로 만든다."))),
    ("별하", "learning_library", (
        ("온라인 강좌 제작팀", "직무 학습용 동영상 강의를 기획하고 촬영하는 팀",
         "신입 직원이 화면으로 배울 수 있도록 수업 순서를 짜고 강사의 설명을 촬영하는 부서가 이 일을 맡는다.",
         "작업 요령을 집에서도 볼 수 있는 짧은 강의로 만들고, 실습 장면을 찍어 편집자에게 넘긴다."),
        ("사내 도서 대출팀", "회사 소장 책의 대여와 반납을 관리하는 팀",
         "회사 책장에서 필요한 책을 빌려 주고, 가져간 사람이 돌려줄 날짜를 확인하는 부서가 이 일을 맡는다.",
         "어떤 책이 누구에게 나갔는지 기록하고, 돌아온 책을 정리해 다른 직원도 빌릴 수 있게 한다."))),
    ("예담", "accounting_tax", (
        ("영수증 증빙 정리팀", "지출 영수증을 모아 사용 목적과 회계 증빙을 확인하는 팀",
         "직원이 비용을 쓴 뒤 받은 종이를 모아, 어디에 쓴 돈인지 근거가 충분한지 살피는 부서가 이 일을 맡는다.",
         "카드 사용 내역에 빠진 영수증을 받아 거래마다 증거를 붙이고, 불분명한 용도는 제출자에게 확인한다."),
        ("세무 신고 일정팀", "납세 신고 기한과 제출 순서를 관리하는 팀",
         "국가에 세금을 신고할 마지막 날짜를 달력에 표시하고, 서류를 어느 순서로 낼지 정하는 부서가 이 일을 맡는다.",
         "신고 마감이 휴일과 겹치는지 확인해 준비 날짜를 앞당기고, 세목별 제출 담당자를 정한다."))),
    ("우림", "intellectual_property", (
        ("특허 선행 조사팀", "새 발명과 유사한 기존 특허를 찾아 기술 범위를 비교하는 팀",
         "새 장치와 비슷한 발명이 이미 출원됐는지 찾아보고, 기존 권리의 기술 범위와 대조하는 부서가 이 일을 맡는다.",
         "설명서를 읽어 핵심 구조를 나눈 뒤, 먼저 공개된 발명 문헌 중 겹치는 부분을 발명자에게 알려 준다."),
        ("상표 사용 점검팀", "제품명과 표지의 상표 사용이 등록 권리와 충돌하는지 확인하는 팀",
         "상자에 넣을 이름과 그림이 다른 회사가 등록한 브랜드 표시와 헷갈리지 않는지 보는 부서가 이 일을 맡는다.",
         "새 제품 표지를 검색해 비슷한 등록 상표가 있는지 확인하고, 혼동될 수 있는 이름은 바꾸도록 안내한다."))),
    ("세움", "food", (
        ("사내 식단 구성팀", "구내 식사의 메뉴와 영양 균형을 계획하는 팀",
         "구내식당에서 이번 주에 무엇을 먹을지 정하며, 채소와 단백질이 한쪽으로 치우치지 않게 하는 부서가 이 일을 맡는다.",
         "매일 같은 반찬이 나오지 않도록 요리를 바꾸고, 알레르기가 있는 직원을 위한 선택지도 마련한다."),
        ("농산물 원산지 추적팀", "납품 농산물의 생산 지역과 유통 이력을 확인하는 팀",
         "식당에 들어온 쌀과 채소가 어느 농가에서 나왔는지 증서를 따라 확인하는 부서가 이 일을 맡는다.",
         "상자에 적힌 생산 지역을 납품 서류와 대조하고, 유통 단계에서 출처가 바뀌지 않았는지 확인한다."))),
    ("다솜", "workforce_safety", (
        ("야간 교대 편성팀", "밤 시간 근무자의 교대 순서와 인원 배치를 정하는 팀",
         "밤에 일할 사람 수를 맞추고, 늦은 시간 담당자가 순서대로 바뀌게 근무표를 짜는 부서가 이 일을 맡는다.",
         "같은 사람이 연속해서 야간 일을 맡지 않도록 조를 나누고, 결원이 생긴 시간에 대신 일할 사람을 정한다."),
        ("현장 안전 교육팀", "작업자를 대상으로 사고 예방 교육과 보호구 사용 훈련을 진행하는 팀",
         "작업을 시작할 사람에게 위험한 행동을 설명하고, 헬멧과 방호 장치를 제대로 쓰도록 가르치는 부서가 이 일을 맡는다.",
         "끼임 사고를 피하는 동작을 함께 연습하고, 새 직원이 보호 장비를 직접 착용해 보게 한다."))),
    ("아람", "vehicle_logistics", (
        ("물류 차량 경로팀", "화물 차량의 배송 순서와 이동 경로를 계산하는 팀",
         "물건을 실은 차가 어느 거래처부터 갈지 정하고, 막히는 길을 피할 이동 순서를 짜는 부서가 이 일을 맡는다.",
         "도착 희망 시각과 도로 사정을 함께 고려해 차마다 방문 순서를 다시 배정한다."),
        ("운전 기사 휴식팀", "운송 기사들의 연속 운전 시간을 확인하고 휴식 시간을 배정하는 팀",
         "운전자가 너무 오래 쉬지 않고 달리지 않도록 시간을 살피고, 중간에 멈춰 쉴 구간을 마련하는 부서가 이 일을 맡는다.",
         "출발 뒤 운전한 시간을 더해 한도를 넘기기 전에 휴게소에서 충분히 쉬도록 근무 일정을 바꾼다."))),
    ("하람", "retail", (
        ("점포 진열 배치팀", "매장 상품의 진열 위치와 고객 이동 동선을 설계하는 팀",
         "매장에서 손님이 물건을 보기 쉽게 선반 위치를 바꾸고, 통로가 막히지 않게 배치하는 부서가 이 일을 맡는다.",
         "함께 사는 상품을 가까이 놓으며, 들어오는 사람과 계산대에 가는 사람이 부딪히지 않게 길을 낸다."),
        ("판매 가격표 관리팀", "매장 가격표의 금액과 적용 기간을 갱신하는 팀",
         "선반에 붙은 금액이 계산할 때와 같은지 확인하고, 할인 종료일에 표를 바꾸는 부서가 이 일을 맡는다.",
         "오래된 행사 금액을 제거한 뒤 새 표를 붙이며, 적용 날짜가 서로 다른 품목은 따로 표시한다."))),
    ("늘찬", "media", (
        ("촬영 조명 대여팀", "영상 촬영용 조명 장비의 대여와 회수를 관리하는 팀",
         "촬영할 때 필요한 램프와 스탠드를 빌려 주고, 끝난 뒤 기기가 모두 돌아왔는지 보는 부서가 이 일을 맡는다.",
         "촬영 장소에 맞는 빛 장비를 골라 출고하며, 반납 시에는 전구와 전원선을 함께 확인한다."),
        ("영상 자막 편집팀", "동영상 발언을 자막으로 다듬고 화면에 표시할 시점을 맞추는 팀",
         "영상에 나오는 말을 읽기 좋은 짧은 글로 줄이고, 말하는 순간에 화면에 뜨게 맞추는 부서가 이 일을 맡는다.",
         "화면을 가리는 긴 문장은 나눠 넣고, 등장인물의 말이 끝나면 글자도 자연스럽게 사라지도록 조정한다."))),
    ("채움", "prototype_exhibition", (
        ("시제품 부품 제작팀", "새 제품 시험 조립에 필요한 소량 부품을 가공하는 팀",
         "새 모델을 먼저 조립해 볼 수 있도록 적은 수의 판과 축을 깎아 만드는 부서가 이 일을 맡는다.",
         "대량 생산 금형을 만들기 전에 설계자가 확인할 부품 몇 개를 소형 공작기계에서 가공한다."),
        ("전시 견본 운송팀", "박람회에 사용할 제품 견본을 포장하여 전시장으로 운반하는 팀",
         "행사장에서 보여 줄 물건을 상자에 안전하게 넣고, 박람회 부스까지 보내는 부서가 이 일을 맡는다.",
         "실물 견본이 전시 개장 전에 도착하도록 차를 예약하고, 이동 중 표면이 긁히지 않게 싸서 싣는다."))),
    ("새론", "international_trade", (
        ("수출 통관 준비팀", "해외로 보낼 상품의 세관 제출 자료를 준비하는 팀",
         "국외에 보내는 물건이 세관을 통과할 수 있도록 품목과 금액을 적은 자료를 모으는 부서가 이 일을 맡는다.",
         "출항 전에 신고에 필요한 송장과 포장 명세를 맞추고, 세관이 추가로 요구한 증명을 첨부한다."),
        ("해외 원료 주문팀", "외국 공급처에 제조 원료를 주문하고 구매 조건을 협의하는 팀",
         "외국 업체에서 생산 재료를 사기 위해 수량과 단가를 협의하고 주문서를 보내는 부서가 이 일을 맡는다.",
         "해외 공급자의 최소 판매량을 확인한 뒤 필요한 재료의 납기와 결제 조건을 구매 주문에 반영한다."))),
    ("여담", "customer_research", (
        ("고객 설문 분석팀", "고객이 응답한 설문을 집계하여 의견과 만족도를 분석하는 팀",
         "손님이 체크한 응답을 모아 어떤 불편이 자주 나왔는지와 만족 수준을 살피는 부서가 이 일을 맡는다.",
         "문항별 선택 수를 세고 자유 의견을 주제별로 묶어, 개선을 요구한 내용을 보고서에 적는다."),
        ("매장 대기열 개선팀", "매장 방문객의 줄 서는 시간을 측정하고 대기 동선을 개선하는 팀",
         "방문객이 계산 전 얼마나 기다리는지 재고, 줄이 꼬이지 않게 안내 위치를 바꾸는 부서가 이 일을 맡는다.",
         "붐비는 시간마다 기다리는 사람 수를 기록해 추가 계산대를 열 시점과 줄의 방향을 조정한다."))),
    ("한결", "building", (
        ("시설 누수 보수팀", "건물 배관과 지붕의 누수 지점을 찾아 수리하는 팀",
         "천장에서 물이 떨어진 원인을 따라 배관과 지붕을 살피고, 새는 곳을 막는 부서가 이 일을 맡는다.",
         "비가 온 뒤 젖은 자국을 확인하며, 물이 스며든 틈을 보수재로 메운 뒤 다시 새는지 본다."),
        ("승강기 운행 점검팀", "건물 승강기의 운행 상태와 정지 장치를 정기 점검하는 팀",
         "엘리베이터가 층마다 제대로 멈추는지 타 보며, 문과 비상 정지 기능을 살피는 부서가 이 일을 맡는다.",
         "문이 닫히는 시간과 층 높이 차이를 기록하고, 비상 버튼을 눌렀을 때 대응 장치가 작동하는지 확인한다."))),
    ("미르", "software_assets", (
        ("소프트웨어 이용권 등록팀", "업무용 소프트웨어의 구매 이용권과 사용 좌석을 관리하는 팀",
         "회사가 산 프로그램을 몇 명까지 쓸 수 있는지 기록하고, 새 사용자에게 빈 이용 자리를 배정하는 부서가 이 일을 맡는다.",
         "구매한 프로그램의 사용 계약 수와 설치된 컴퓨터 수를 맞추며, 좌석이 남았을 때만 새 설치를 허용한다."),
        ("문서 글꼴 배포팀", "회사 문서에 사용할 글꼴 파일과 설치 안내를 배포하는 팀",
         "회사 자료에서 같은 글자 모양을 쓰도록 폰트 파일과 설치 방법을 직원에게 보내는 부서가 이 일을 맡는다.",
         "새 서체가 깨지지 않게 컴퓨터에 넣는 방법을 안내하고, 외부 문서에도 쓸 수 있는 파일을 따로 제공한다."))),
    ("푸름", "environment", (
        ("공기질 환기 운영팀", "실내 오염 물질 농도를 확인하여 환기 장치를 운전하는 팀",
         "실내 이산화탄소와 먼지 수치를 보고 바깥 공기가 들어오도록 팬을 켜는 부서가 이 일을 맡는다.",
         "사람이 많이 모인 방의 공기를 측정하고, 답답해지기 전에 외기 유입량을 늘린다."),
        ("옥상 텃밭 운영팀", "옥상 재배 공간의 작물 심기와 물주기 일정을 관리하는 팀",
         "건물 위 작은 밭에 채소를 심고, 날씨에 따라 물을 줄 차례를 정하는 부서가 이 일을 맡는다.",
         "옥상 화분의 흙이 마르지 않았는지 살피며, 계절에 맞는 모종을 심을 자리를 나눈다."))),
    ("초아", "delivery_documentation", (
        ("납품 설치 일정팀", "고객 현장에 제품을 납품하고 설치할 날짜를 조율하는 팀",
         "고객 사무실에 새 기계를 가져가 놓을 날을 맞추고, 설치 기사가 방문할 시간을 정하는 부서가 이 일을 맡는다.",
         "건물 사용 가능 시간과 운반 차량 도착을 맞춰, 제품을 들여놓고 고정할 작업자를 배치한다."),
        ("사용 설명서 개정팀", "제품 사용 안내문의 오류를 고치고 새 기능 설명을 추가하는 팀",
         "제품을 쓰는 방법을 적은 책자에서 잘못된 순서를 고치고, 새 버튼의 기능을 덧붙이는 부서가 이 일을 맡는다.",
         "사용자가 헷갈린 문장을 다시 쓰며, 화면이 바뀐 부분은 새 그림을 넣어 안내문을 갱신한다."))),
    ("윤슬", "laboratory", (
        ("연구 표본 배송팀", "연구용 표본의 보존 조건을 지켜 실험 기관에 전달하는 팀",
         "분석할 시료가 변하지 않게 담아 지정된 연구소로 보내는 부서가 이 일을 맡는다.",
         "채집한 표본이 마르거나 녹지 않도록 용기를 고른 뒤, 실험 담당자가 받을 때까지 운송 상태를 기록한다."),
        ("실험 시약 구매팀", "실험에 필요한 화학 시약의 종류와 수량을 확인하여 구매하는 팀",
         "실험에 쓸 화학 물질이 무엇인지와 필요한 양을 확인해 판매처에 주문하는 부서가 이 일을 맡는다.",
         "실험자가 요구한 순도와 포장 크기를 공급 목록에서 비교하고, 부족한 약품을 구매 요청한다."))),
    ("슬기", "personnel", (
        ("채용 면접 일정팀", "지원자의 면접 시각과 면접관 배정을 조율하는 팀",
         "입사를 원하는 사람이 언제 면접을 볼지 맞추고, 그 시간에 질문할 담당자를 정하는 부서가 이 일을 맡는다.",
         "지원자가 가능한 시간과 심사자 일정을 대조해 겹치지 않게 면접방을 예약한다."),
        ("퇴직 장비 반납팀", "퇴직자가 사용하던 회사 장비의 반환과 인계 상태를 확인하는 팀",
         "회사를 떠나는 직원이 쓰던 노트북과 휴대전화를 돌려받고, 다음 사람에게 넘길 상태인지 보는 부서가 이 일을 맡는다.",
         "마지막 근무일 전에 빌려 준 기기 목록을 대조하며, 돌아오지 않은 물건은 반환 일자를 다시 확인한다."))),
)

FILLERS = (
    ("접수 번호는 이미 배정했다. 보완 자료는 새 요청을 만들지 말고 같은 번호에 덧붙인다.",
     "담당자는 확인한 사실과 아직 정하지 못한 사항을 나눠 적는다. 처리 시각은 일이 끝난 뒤 기록한다."),
    ("오늘 회의에는 진행 담당자 세 명이 참석했다. 의사결정의 이유는 서기에게 전달해 공통 기록에 남긴다.",
     "다음 확인은 금요일에 한다. 담당자가 바뀌더라도 이번 요청의 번호와 남은 작업을 인계한다."),
    ("실무 안내는 공유 게시판에 올렸다. 각 담당자는 자신이 확인한 항목 옆에 날짜를 적어 달라.",
     "긴급하지 않은 변경은 오후에 한 번 모아 알린다. 완료한 내용은 주간 회의에서 요약한다."),
)


def _opaque_key(family_id, side):
    return "e_" + hashlib.sha256(f"new-target-family:{family_id}:{side}".encode()).hexdigest()[:16]


def _target(document_id, alias, side, stratum, quotes, rationale, *, occurrence=0,
            label="LINK", surface=None, terms=None):
    ref = "global:" + terms[side]["key"] if label == "LINK" else None
    return {
        "target_id": f"{document_id}-t{occurrence + 1:02d}",
        "surface": surface or alias, "occurrence": occurrence,
        "gold": {"label": label, "entity_ref": ref}, "stratum": stratum,
        "decisive_evidence": [{"document": "source", "quote": quote} for quote in quotes],
        "rationale": rationale,
    }


def _document(document_id, title, paragraphs, targets):
    return {"document_id": document_id, "title": title,
            "text": "\n\n".join(paragraphs), "targets": targets}


def build_families():
    """Return authored source documents and labels, without running a model."""
    families = []
    for index, (alias, domain, meanings) in enumerate(FAMILY_SPECS, 1):
        family_id = f"ch{index:02d}"
        terms = [{"key": _opaque_key(family_id, side), "canonical": meaning[0],
                  "surfaces": [alias, meaning[0]], "short_definition": meaning[1]}
                 for side, meaning in enumerate(meanings)]
        filler1, filler2 = FILLERS[(index - 1) % len(FILLERS)]
        documents = []

        for kind in ("local", "remote"):
            for side, meaning in enumerate(meanings):
                suffix = len(documents) + 1
                document_id = f"{family_id}-d{suffix:02d}"
                stratum = f"paraphrase_{kind}_{'AB'[side]}"
                if index % 3 == 1:
                    opening = f"이번 요청의 수신처는 {alias}로 정했다. 회의에서 결정한 처리 범위를 아래에 남긴다."
                elif index % 3 == 2:
                    opening = f"업무 전달 메모: {alias}에 새 요청을 보낸다. 받는 쪽이 맡을 일이 무엇인지 확인하고 진행해 달라."
                else:
                    opening = f"작업표의 담당 칸에는 {alias}를 적었다. 담당자를 고른 이유와 전달할 자료를 함께 기록한다."
                evidence = meaning[2] + " " + meaning[3]
                if kind == "local":
                    paragraphs = [opening, evidence, filler1, filler2]
                else:
                    # The actual business cue follows >150 characters of neutral
                    # process text, rather than sitting in a 60-character window.
                    paragraphs = [opening, filler1, filler2,
                                  "첨부 목록은 서기가 별도로 관리한다. 순서가 바뀌더라도 처음 합의한 업무 범위는 그대로 유지한다.",
                                  evidence]
                documents.append(_document(document_id, "요청 범위와 처리 담당 확인", paragraphs, [
                    _target(document_id, alias, side, stratum, [meaning[2], meaning[3]],
                            "업무를 풀어 쓴 두 문장이 등록 의미를 특정한다. 정식 이름과 사전 정의는 본문에 복사하지 않았다.",
                            terms=terms)]))

        for order in ((0, 1), (1, 0)):
            document_id = f"{family_id}-d{len(documents) + 1:02d}"
            stratum = "multi_target_" + "".join("AB"[side] for side in order)
            paragraphs = ["서로 다른 두 요청을 한 회의록에 정리했다. 같은 짧은 이름이 나오더라도 각 절에서 설명한 업무를 따로 읽어야 한다."]
            targets = []
            for occurrence, side in enumerate(order):
                meaning = meanings[side]
                section = "첫 번째" if occurrence == 0 else "두 번째"
                quoted = f"{section} 요청은 {alias}에 전달한다. " + meaning[2] + " " + meaning[3]
                paragraphs.append(quoted)
                targets.append(_target(document_id, alias, side, stratum, [quoted],
                                       "동일 약칭이 같은 문서에서 두 의미를 각각 지칭한다. 해당 발생 위치가 속한 절의 업무만 적용한다.",
                                       occurrence=occurrence, terms=terms))
            paragraphs.append("각 요청의 자료는 서로 다른 접수 번호에 붙인다. 한쪽 부서의 결과를 다른 쪽 작업의 완료로 처리하지 않는다.")
            documents.append(_document(document_id, "두 업무의 개별 수신처", paragraphs, targets))

        for side, meaning in enumerate(meanings):
            document_id = f"{family_id}-d{len(documents) + 1:02d}"
            decoy = meanings[1 - side][0]
            exclusion = f"{decoy}은 이번 건의 담당이 아니다. {decoy}의 이름은 이전 양식에 남은 것이며, {decoy}에 전달하라는 안내는 취소했다."
            binding = f"이번 실제 요청은 {alias}에 보낸다. " + meaning[2] + " " + meaning[3]
            documents.append(_document(document_id, "옛 수신처 표기의 정정", [exclusion, filler1, binding, filler2], [
                _target(document_id, alias, side, f"negated_decoy_{'AB'[side]}", [exclusion, binding],
                        "다른 후보의 정식 명칭이 세 번 등장하지만 모두 수신처에서 배제된다. 실제 업무에 대한 긍정 서술이 정답을 정한다.", terms=terms)]))

        document_id = f"{family_id}-d09"
        unclear = f"새 문의의 담당을 {alias}라고만 적었다. 작성자는 어느 업무에 관한 문의인지를 남기지 않았다."
        both = f"{meanings[0][0]}과 {meanings[1][0]}은 모두 현재 운영 중이며, 둘 다 이 짧은 이름을 사용한다."
        documents.append(_document(document_id, "수신처 확인이 필요한 문의", [unclear, both, filler1,
            "요청 내용과 첨부 자료가 없어 어느 쪽으로 보내야 할지 알 수 없다. 이름이 확인되기 전에는 두 부서 중 하나를 임의로 선택하지 않는다.", filler2], [
            _target(document_id, alias, 0, "genuinely_ambiguous", [unclear, both],
                    "두 등록 의미가 모두 유효하지만 대상 발생 위치를 구별할 정보가 없다. 정답 하나를 부여하면 안 된다.",
                    label="AMBIGUOUS", terms=terms)]))

        document_id = f"{family_id}-d10"
        named = f"외부 공방이 만든 휴대용 독서등 {alias}의 사진을 홍보 담당자에게 보냈다. 이번 이름은 새 조명 상품에 붙은 상표다."
        exclusion = "제품은 손으로 접어 가방에 넣는 개인용 램프다. 사내 부서나 업무 절차를 가리키지 않으며 현재 회사 용어 사전에 등록돼 있지 않다."
        documents.append(_document(document_id, "외부 상품의 소개 자료", [named, exclusion, filler1,
            "홍보물에는 제조사의 연락처만 싣는다. 구입 문의를 회사의 업무 담당 부서로 연결하지 않도록 유통사의 주소를 확인한다.", filler2], [
            _target(document_id, alias, 0, "unregistered_named_object", [named, exclusion],
                    "발생 위치는 새 외부 상품의 고유명이다. 동형인 두 등록 조직 중 어느 것도 지칭하지 않는다.", label="NIL", terms=terms)]))

        document_id = f"{family_id}-d11"
        quotation = f"문장 편집 시험지에는 “{alias}는 {meanings[0][0]}이다”라는 틀린 예문을 넣었다."
        rejection = "이 문장은 실제 조직을 설명하는 진술이 아니라, 검토자가 삭제해야 할 가짜 정의의 문자열 예시다. 화면 밖의 수신처를 지칭하거나 업무를 배정하는 용도가 아니다."
        documents.append(_document(document_id, "삭제할 인용 예문의 교정", [quotation, rejection, filler1,
            "교정자는 인용부호 안에 있는 글자를 지우는지만 확인한다. 틀린 예문을 사전의 새 정의로 승인하거나 회사 부서를 연결하지 않는다.", filler2], [
            _target(document_id, alias, 0, "quoted_rejected_definition", [quotation, rejection],
                    "거짓 정의를 담은 인용 문자열 자체를 교정하는 문맥이다. 실제 대상에 대한 용어 연결이 요구되지 않는다.", label="NON_MENTION", terms=terms)]))

        document_id = f"{family_id}-d12"
        role = alias + ("팀장" if index % 2 else "장")
        personal = f"서명란의 검토자는 {role}으로 적었다. " + meanings[0][2]
        role_scope = "이 칸은 해당 팀을 이끄는 책임자 한 사람이 서명하는 자리다. 조직의 공용 접수함이나 팀 전체를 뜻하는 칸이 아니며, 인사 발령 뒤에는 사람을 다시 확인한다."
        documents.append(_document(document_id, "개인 서명자와 조직의 구별", [personal, role_scope, filler1,
            "조직 코드와 개인 결재자의 직함은 각각 별도 필드에 적는다. 이름이 비슷하다는 이유로 팀의 ID를 사람 칸에 넣지 않는다.", filler2], [
            _target(document_id, alias, 0, "role_derivative", [personal, role_scope],
                    "약칭 core는 조직 이름과 연결될 수 있지만 전체 대상 표면형은 책임자 개인의 역할이다. 조직 ID로 전체를 확정할 수 없다.",
                    label="COMPOSITIONAL", surface=role, terms=terms)]))

        document_id = f"{family_id}-d13"
        proposal = f"이름을 붙이는 연습에서 {alias}라는 후보 글자를 적었지만 그 안은 즉시 폐기했다. 실제 부서나 새 서비스에 이 이름을 부여한 적은 없다."
        never_bound = "회의는 철자 모양만 비교하는 연습이었다. 업무 담당자를 뜻하는 표현도 아니고, 시행을 앞둔 사업을 가리키는 약칭도 아니다."
        documents.append(_document(document_id, "채택하지 않은 이름 후보", [proposal, never_bound, filler1,
            "남은 메모는 이름 선정 훈련의 예시로만 보관한다. 실제 용어 목록이나 운영 문서에는 이 후보를 추가하지 않기로 했다.", filler2], [
            _target(document_id, alias, 0, "cancelled_definition_or_plan", [proposal, never_bound],
                    "채택되지 않은 글자 후보 자체에 대한 메타 언급이다. 이미 존재하는 조직을 취소한 것이 아니며 실제 지칭 대상도 없다.",
                    label="NON_MENTION", terms=terms)]))

        document_id = f"{family_id}-d14"
        independent = f"영화 동아리가 단편 영화 {alias}의 상영 포스터를 만들었다. 제목은 감독이 정한 작품 이름으로, 회사에서 등록한 업무 대상이 아니다."
        unrelated = f"별도 사전 안내에는 {meanings[0][0]}은 {meanings[0][1]}이라고 적혀 있다. 또 {meanings[1][0]}은 {meanings[1][1]}이라고 적혀 있다. 이 안내는 포스터 내용과 관계없다."
        documents.append(_document(document_id, "작품 제목과 별도 사전 안내", [independent, filler1, unrelated,
            "상영 안내는 동아리 연락처로 받는다. 작품 제목을 회사 조직 이름으로 바꾸거나 포스터를 업무 요청으로 처리하지 않는다."], [
            _target(document_id, alias, 0, "irrelevant_definition_decoy", [independent, unrelated],
                    "본문의 실제 대상은 미등록 영화다. 두 등록 정의가 별도 단락에 있어도 해당 발생 위치를 조직으로 바꾸지 않는다.", label="NIL", terms=terms)]))

        knowledge_text = (f"이 사전에서 약칭 {alias}는 아래 두 조직에 각각 등록돼 있다. 같은 약칭만으로 대상 조직을 하나로 확정하지 않는다.\n\n"
                          + "\n\n".join(f"{term['canonical']}: {term['short_definition']}. 등록 ID는 global:{term['key']}이다."
                                           for term in terms)
                          + "\n\n외부 작품이나 상품, 채택하지 않은 글자 후보, 책임자 개인은 위 조직 ID와 구별한다.")
        families.append({
            "family_id": family_id, "domain": domain,
            "protocol_version": VERSION, "annotation_origin": "AI_AUTHORED_SYNTHETIC", "human_verified": False,
            "authoring_method": "New authored glossary families and source documents; no resolver output or model prediction was used.",
            "evaluation_history": "New synthetic family-disjoint challenge authored before inference; not a real-world or independent human audit.",
            "terms": terms,
            "knowledge_document": {"document_id": "kb-" + family_id, "title": alias + " 등록 용어 안내", "text": knowledge_text},
            "documents": documents,
        })
    validate_families(families)
    return families


def validate_families(families):
    if len(families) != 24 or {family["family_id"] for family in families} != {f"ch{i:02d}" for i in range(1, 25)}:
        raise ValueError("24 new complete glossary families are required")
    catalog_keys, canonical_names, alias_names, document_ids, target_ids = set(), set(), set(), set(), set()
    expected_labels = Counter({"LINK": 10, "NIL": 2, "NON_MENTION": 2, "AMBIGUOUS": 1, "COMPOSITIONAL": 1})
    expected_strata = Counter({"paraphrase_local_A": 1, "paraphrase_local_B": 1,
        "paraphrase_remote_A": 1, "paraphrase_remote_B": 1, "multi_target_AB": 2, "multi_target_BA": 2,
        "negated_decoy_A": 1, "negated_decoy_B": 1, "genuinely_ambiguous": 1, "unregistered_named_object": 1,
        "quoted_rejected_definition": 1, "role_derivative": 1, "cancelled_definition_or_plan": 1,
        "irrelevant_definition_decoy": 1})
    for family in families:
        if family["annotation_origin"] != "AI_AUTHORED_SYNTHETIC" or family["human_verified"] is not False:
            raise ValueError("authorship must be disclosed")
        terms = family["terms"]
        if len(terms) != 2 or terms[0]["surfaces"][0] != terms[1]["surfaces"][0]:
            raise ValueError("each family must retain exactly two colliding registered meanings")
        alias = terms[0]["surfaces"][0]
        if alias in alias_names:
            raise ValueError("families must have distinct aliases")
        alias_names.add(alias)
        for term in terms:
            if term["key"] in catalog_keys or term["canonical"] in canonical_names:
                raise ValueError("new glossary entries must be unique")
            catalog_keys.add(term["key"])
            canonical_names.add(term["canonical"])
        if len(family["documents"]) != 14:
            raise ValueError("each family requires 14 source documents")
        family_targets = [target for doc in family["documents"] for target in doc["targets"]]
        if Counter(target["gold"]["label"] for target in family_targets) != expected_labels:
            raise ValueError("each family requires 10 LINK and 6 abstention targets")
        if Counter(target["stratum"] for target in family_targets) != expected_strata:
            raise ValueError("challenge strata are incomplete")
        valid_refs = {"global:" + term["key"] for term in terms}
        for doc in family["documents"]:
            if doc["document_id"] in document_ids:
                raise ValueError("document IDs must be unique")
            document_ids.add(doc["document_id"])
            text = doc["text"]
            if not 200 <= len(text) <= 650:
                raise ValueError("source documents must be bounded, meaningful business texts")
            if text.count(alias) != len(doc["targets"]):
                raise ValueError("source alias occurrences must correspond exactly to targets")
            for target in doc["targets"]:
                if target["target_id"] in target_ids:
                    raise ValueError("target IDs must be unique")
                target_ids.add(target["target_id"])
                surface = target["surface"]
                positions = [i for i in range(len(text)) if text.startswith(surface, i)]
                if target["occurrence"] >= len(positions):
                    raise ValueError("designated target occurrence is absent")
                gold = target["gold"]
                if (gold["label"] == "LINK" and gold["entity_ref"] not in valid_refs
                        or gold["label"] != "LINK" and gold["entity_ref"] is not None):
                    raise ValueError("authored gold must refer only to a registered exact target or abstention")
                for evidence in target["decisive_evidence"]:
                    if evidence["document"] != "source" or evidence["quote"] not in text:
                        raise ValueError("gold evidence must be a verbatim source substring")
                if target["stratum"].startswith("paraphrase_"):
                    for term in terms:
                        if term["canonical"] in text or term["short_definition"] in text:
                            raise ValueError("paraphrase source must not copy any registered canonical or definition")


def encoded_fixture(families):
    return "".join(json.dumps(family, ensure_ascii=False, separators=(",", ":")) + "\n" for family in families)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Verify the committed fixture matches deterministic authoring")
    args = parser.parse_args(argv)
    families = build_families()
    encoded = encoded_fixture(families)
    if args.check:
        if args.output.read_text(encoding="utf-8") != encoded:
            raise SystemExit("fixture differs from deterministic authoring")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({"protocol_version": VERSION, "families": len(families), "documents": 336,
                      "targets": 384, "link_targets": 240, "abstention_targets": 144,
                      "fixture_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                      "human_verified": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()

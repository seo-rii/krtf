"""Serialize directly authored fictional glossary worlds and source scenarios.

This file contains no resolver or model access. Text patterns are shared across
families and are deliberately disclosed as an artificial generalization limit.
The generated JSON, not this builder, is the frozen review/inference artifact.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Author-declared split before any resolver/model outputs. Eight development
# families are interleaved across the four source scenario styles.
DEVELOPMENT = {1, 4, 7, 10, 13, 16, 19, 22}
# unique alias A/B, shared alias, jurisdictions A/B, scope A/B, purpose A/B,
# referent kind A/B. All company names and procedures are fictional.
WORLDS = [
    ('비취문', '모래봉', 'VBQ', '대한민국', '캐나다', '설비심사반', '해외창고반', '냉각 설비 교체 승인', '해외 재고 이관 접수', '절차', '시스템'),
    ('솔빛터', '연필항', 'SLQ', '일본', '대한민국', '품질계측반', '도면관리반', '측정 장비 오차 기록', '설계 도면 변경 검토', '기록부', '절차'),
    ('보리울', '자개숲', 'BRQ', '독일', '호주', '배송점검반', '수리계약반', '운송 경로 점검', '수리 계약 접수', '시스템', '시스템'),
    ('초롱샘', '누리턱', 'CRQ', '대한민국', '일본', '원료검수반', '포장감사반', '원료 검수 이견 심의', '포장 자재 재사용 심사', '심의체', '절차'),
    ('물결솔', '사금별', 'MGQ', '캐나다', '독일', '전력계획반', '장비대여반', '실험실 전력 배분', '공용 장비 대여 기록', '절차', '기록부'),
    ('꽃잎돌', '윤슬판', 'KIQ', '호주', '대한민국', '샘플보관반', '협약관리반', '시험 샘플 폐기 검토', '연구 협약 갱신 접수', '절차', '시스템'),
    ('산호길', '여백문', 'SHQ', '일본', '캐나다', '선적검토반', '검사예약반', '화물 선적 일자 조정', '검사 장비 예약', '심의체', '시스템'),
    ('구름못', '참새칸', 'GMQ', '대한민국', '독일', '배관관리반', '공정교육반', '배관 누수 점검 기록', '공정 교육 이수 확인', '기록부', '절차'),
    ('단풍숫', '소나등', 'DPQ', '독일', '일본', '압력시험반', '금형수급반', '압력 시험 승인', '금형 수급 일정 기록', '절차', '기록부'),
    ('노을빗', '이슬돛', 'NUQ', '캐나다', '호주', '용수감사반', '소음측정반', '용수 사용량 감사', '작업장 소음 측정 접수', '심의체', '시스템'),
    ('벼리섬', '해솔굽', 'BSQ', '호주', '대한민국', '냉매검토반', '방재훈련반', '냉매 교체 검토', '방재 훈련 참석 기록', '절차', '기록부'),
    ('금빛울', '재빛곶', 'GBQ', '일본', '독일', '세척감사반', '조명개선반', '세척 공정 감사', '조명 교체 제안 접수', '심의체', '시스템'),
    ('버들턱', '햇귀선', 'BDQ', '대한민국', '호주', '품목폐기반', '화물분류반', '불량 품목 폐기 승인', '화물 등급 분류', '절차', '시스템'),
    ('옹달궤', '달무리쇠', 'ODQ', '독일', '캐나다', '냉장점검반', '견본제작반', '냉장고 점검 기록', '견본 제작 요청 검토', '기록부', '심의체'),
    ('풀무꽃', '눈꽃뿔', 'PMQ', '호주', '일본', '풍량시험반', '도금검토반', '환기 풍량 시험 접수', '도금 재료 변경 심사', '시스템', '절차'),
    ('먹구슬', '흰자락', 'MKQ', '캐나다', '대한민국', '수질관측반', '차폐설계반', '수질 관측 결과 기록', '전자파 차폐 설계 검토', '기록부', '심의체'),
    ('갈잎날', '푸른싹', 'GLQ', '대한민국', '독일', '진동분석반', '접착검증반', '회전 장비 진동 분석', '접착제 성능 검증 승인', '시스템', '절차'),
    ('꽃비루', '뭉게턱', 'KBQ', '일본', '호주', '단열시험반', '윤활관리반', '단열재 성능 시험 심의', '윤활유 교체 이력 기록', '심의체', '기록부'),
    ('숲그릇', '별다랑', 'SGQ', '독일', '대한민국', '부식검토반', '진공예약반', '부식 방지 작업 승인', '진공 장비 예약', '절차', '시스템'),
    ('아지랑솥', '새벽벼', 'AJQ', '호주', '캐나다', '내열검사반', '장력측정반', '내열 재료 검사 접수', '장력 측정 결과 기록', '시스템', '기록부'),
    ('해질돌', '찬물결', 'HJQ', '캐나다', '일본', '환기설계반', '부품분배반', '작업장 환기 설계 심사', '교체 부품 배정', '심의체', '절차'),
    ('잣나루', '은하턱', 'JNQ', '대한민국', '호주', '인장시험반', '포집점검반', '재료 인장 시험 기록', '분진 포집 설비 점검', '기록부', '시스템'),
    ('두루깃', '외솔담', 'DRQ', '일본', '독일', '건조검토반', '수압감사반', '건조 공정 변경 검토', '배수관 수압 감사', '절차', '심의체'),
    ('한낮실', '고운닻', 'HNQ', '호주', '대한민국', '적재심사반', '용접기록반', '컨테이너 적재 계획 심사', '용접 결함 이력 기록', '심의체', '기록부'),
]


def particle(value, forms):
    """Choose an ordinary Korean particle for an authored proper noun."""
    consonant, vowel = forms.split('/')
    final = (ord(value[-1]) - 0xAC00) % 28 if 0xAC00 <= ord(value[-1]) <= 0xD7A3 else 0
    if forms == '으로/로' and final == 8:
        return vowel
    return consonant if final else vowel


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def target(marked):
    left, rest = marked.split('‹', 1)
    marked_target, right = rest.split('›', 1)
    core, sep, suffix = marked_target.partition('|')
    surface = core + suffix
    text = left + surface + right
    start = len(left)
    return text, surface, {'start': start, 'end': start + len(core)}, {'start': start, 'end': start + len(surface)}


def make_source():
    families = []
    for n, (a, b, shared, ja, jb, sa, sb, pa, pb, ka, kb) in enumerate(WORLDS, 1):
        family_id = f'rc26-family-{n:02d}'
        keya, keyb = f'{family_id}-a', f'{family_id}-b'
        ca, cb = f'{a} {pa}', f'{b} {pb}'
        # Status is fixed glossary metadata, not a per-case label. Half the B
        # worlds deliberately describe a still-active pilot rather than the A
        # mainstream service, forcing the model to retain the status wording.
        ta, tb = '현행', ('시범' if n % 2 else '현행')
        da = f'가상 기업 누온사의 {ja} {sa}{particle(sa, "이/가")} 운영하는 {ta} {ka}{particle(ka, "이다/다")}. 정식 이름은 {ca}이며 {pa}에 사용한다. {a} 또는 {shared}라고 줄여 부른다. 다른 국가의 독립 업무, 폐지된 동명 대상, 담당자라는 사람, 별도의 실행 허가증은 이 항목이 아니다.'
        db = f'가상 기업 누온사의 {jb} {sb}{particle(sb, "이/가")} 운영하는 {tb} {kb}{particle(kb, "이다/다")}. 정식 이름은 {cb}이며 {pb}에 사용한다. {b} 또는 {shared}라고 줄여 부른다. 과거 조직의 동명 대상이나 직원 역할 및 이름만 같은 외부 제품은 포함하지 않는다.'
        terms = [
            {'key': keya, 'canonical': ca, 'surfaces': [a, shared], 'short_definition': da,
             'applicability': {'jurisdiction': [ja], 'temporal_status': [ta], 'referent_kind': [ka], 'scope': [sa]}},
            {'key': keyb, 'canonical': cb, 'surfaces': [b, shared], 'short_definition': db,
             'applicability': {'jurisdiction': [jb], 'temporal_status': [tb], 'referent_kind': [kb], 'scope': [sb]}},
        ]
        if n % 4 == 1:
            authored = [
                (f'누온사 {ja} {sa} 업무일지다. 오늘 {ta} {ka}인 ‹{a}›에 {pa} 안건을 올렸다. 접수 번호는 17번이며 처리 결과는 다음 회의에서 알린다.', 'a', 'unique_alias', '이 발생은 국가·현행성·대상 종류·담당 조직과 업무가 A 정의에 모두 일치한다.'),
                (f'{jb} {sb}의 공지: ‹{cb}›{particle(cb, "은/는")} 현재 사용하는 {tb} {kb}{particle(kb, "이다/다")}. 이번 주 접수는 수요일에 마감한다.', 'b', 'canonical', '정식 명칭과 B의 국가·담당 조직·상태·종류가 명시되어 있다.'),
                (f'이번 기록에서 ‹{shared}›는 누온사 {ja} {sa}의 {ta} {ka}{particle(ka, "을/를")} 뜻한다. 담당자는 {pa} 안건 두 건을 여기에 접수했다. 다른 부서의 같은 약자는 이 기록의 대상이 아니다.', 'a', 'shared_alias_resolvable', '충돌 약칭이지만 본문이 A의 국가·조직·종류와 업무를 명시한다.'),
                (f'회의록은 담당자의 설명을 그대로 인용했다. “{jb} {sb}{particle(sb, "이/가")} 쓰는 {tb} {kb} ‹{b}›의 점검이 끝났다.” 기록자는 이 설명을 사실로 확인했다. 별도 부품의 납품 지연은 {b}의 존재를 부정하는 말이 아니다.', 'b', 'asserted_quote_positive', '인용 속 대상은 명시적으로 B이며 서술자도 사실로 확인했다. 다른 부품의 부정적 소식은 무관하다.'),
                (f'브라질의 독립 공장은 자기들이 만든 {ka}{particle(ka, "을/를")} ‹{a}›{particle(a, "이라고/라고")} 이름 붙였다. 이 공장의 담당 조직은 현지정비실이고 누온사 {sa}{particle(sa, "과/와")}는 별개다. {ja}에서 쓰는 업무와 이름만 같다고 설명했다.', None, 'jurisdiction_nil', '브라질의 독립 대상이다. A와 같은 표기여도 국가·주체가 명시적으로 다르다.'),
                (f'{jb} 지점 채용 공고에는 ‹{b}|관리자›를 한 명 뽑는다고 적혀 있다. 표적은 {kb}{particle(kb, "이/가")} 아니라 그 업무를 맡는 직원이라는 역할이다. 지원자의 근무 시간은 오전조다.', None, 'role_composition', '전체 표현은 B의 관리 업무를 맡는 사람이다. B 자체의 ID로 전체를 연결할 수 없다.'),
                (f'{ja} {sa}{particle(sa, "은/는")} {ta} {ka}인 {a}{particle(a, "을/를")} 운영한다. 같은 날 외부 계약사는 자기 회사의 독립 제품 ‹{a}›{particle(a, "을/를")} 전시했다. 두 번째 이름은 누온사의 업무 대상이 아니라 계약사가 판매하는 조립 장난감을 가리킨다.', None, 'repeated_homonym', '앞의 정상 발생과 달리 지정한 두 번째 발생은 외부 장난감 제품이다.'),
                (f'업무 인계 메모에는 “‹{shared}› 담당자에게 문의”라고만 적혀 있다. 작성 부서, 국가, 업무 종류는 빠져 있고 두 등록 항목 중 어느 것을 말하는지 묻자 작성자도 기억하지 못했다.', None, 'shared_alias_ambiguous', '두 항목이 같은 약칭을 쓰며 어느 항목인지 구별할 근거가 없다.'),
            ]
        elif n % 4 == 2:
            authored = [
                (f'작업 표준의 대상은 {ja} {sa}에서 쓰는 {ta} {ka} ‹{a}›{particle(a, "이다/다")}. {pa} 신청서 세 장을 처리했다. 과거의 종이 양식은 이번 기록에 사용하지 않았다.', 'a', 'unique_alias_irrelevant_negative', 'A의 네 적용 속성이 모두 명시된다. 사용하지 않았다는 말은 별도의 옛 종이 양식에만 적용된다.'),
                (f'누온사 {jb} {sb}{particle(sb, "은/는")} {tb} {kb}인 ‹{cb}›{particle(cb, "을/를")} 이번 분기에도 사용한다고 밝혔다. 월간 점검 담당자는 같은 조직에 남는다.', 'b', 'canonical', '정식 명칭을 가진 B가 해당 국가·부서의 명시된 상태로 운영 중이다.'),
                (f'{ja} {sa}의 실무자는 {pa}용 {ta} {ka}{particle(ka, "을/를")} ‹{shared}›라고 적었다. 이 약자가 다른 지점에서도 쓰인다는 사실은 알지만, 이 문서의 대상은 앞서 밝힌 업무에 한정했다.', 'a', 'shared_alias_resolvable', '같은 약칭의 충돌을 인정하면서 이번 발생은 A의 국가·담당 조직·목적이라고 특정했다.'),
                (f'검토자는 “‹{b}›{particle(b, "은/는")} {jb} {sb}의 {tb} {kb}{particle(kb, "이다/다")}”라고 보고했다. 현장 확인에서도 그 설명이 맞았다. 확인되지 않은 것은 회의실 예약 시간이며 대상의 정체가 아니다.', 'b', 'asserted_quote_positive', 'B의 정체에 관한 인용은 확인된 사실이다. 무관한 예약 시간의 미확정과 혼동하면 안 된다.'),
                (f'2016년 문서의 ‹{a}›{particle(a, "은/는")} 당시 폐지된 지역 소모임 이름이다. 현재의 {sa}{particle(sa, "이/가")} 생기기 전부터 쓰였고 지금은 해산했다. 이 문서는 옛 소모임 회비를 정산한 기록이다.', None, 'historical_nil', '현행 A가 아니라 이미 해산한 동명의 과거 소모임을 지칭한다.'),
                (f'외부 감사인은 사전의 {b}{particle(b, "과/와")} 별개인 반출 허가증을 ‹{b}›{particle(b, "이라고/라고")} 부른다는 사내 은어를 설명했다. 여기서 표적은 허가증이라는 권한 증서이고 {kb} 자체를 뜻하지 않는다. 그 증서는 누온사의 등록 대상이 아니다.', None, 'exception_distinct_permission', '행위가 허용되는지의 문제가 아니라 별도 허가증을 지칭한다는 명시적 의미 차이다.'),
                (f'{ja} {sa}{particle(sa, "이/가")} 쓰는 {ta} {ka} {a}{particle(a, "은/는")} 정상 운영 중이다. 이어진 번역 기사에서 인도 업체가 독자적으로 만든 ‹{a}›{particle(a, "을/를")} 소개했다. 기사 속 두 번째 대상의 운영 주체는 인도 업체이며 누온사와 계약 관계도 없다.', None, 'repeated_jurisdiction', '요청된 두 번째 발생은 첫 번째 정상 발생과 별개의 인도 업체 대상이다.'),
                (f'보관 상자에 ‹{shared}›라는 글자와 날짜만 남아 있다. 어느 나라 어느 부서의 자료인지는 지워졌다. 두 등록 항목 중 하나라고 추정할 근거도 없다.', None, 'shared_alias_ambiguous', '공유 약칭만 남아 두 등록 대상을 구별할 수 없다.'),
            ]
        elif n % 4 == 3:
            authored = [
                (f'누온사 {ja} {sa}의 {ta} {ka} ‹{a}›{particle(a, "은/는")} {pa}{particle(pa, "을/를")} 맡는다. 담당자는 오늘 접수 목록을 내려받았다. 외부 축제 취소 공지는 이 업무와 관련이 없다.', 'a', 'unique_alias_irrelevant_negative', 'A에 대한 적극적 지지와 무관한 행사 취소가 함께 있다. 취소 표현을 A에 전이하면 안 된다.'),
                (f'{jb} {sb}{particle(sb, "이/가")} 관리하는 {tb} {kb}의 정식 이름은 ‹{cb}›{particle(cb, "이다/다")}. 점검표에는 누락 없이 그 이름을 적고 담당자 서명을 받았다.', 'b', 'canonical', '정식 명칭과 B의 국가·조직·상태·종류가 한 문단에 있다.'),
                (f'오늘 ‹{shared}›라고 부르는 것은 {ja} {sa}의 {ta} {ka}, 곧 {pa}에 사용하는 대상이다. 다른 국가의 같은 약칭은 이 요청에 포함하지 않는다.', 'a', 'shared_alias_resolvable', '국가·부서·상태·종류·업무를 통해 A를 특정한 충돌 약칭이다.'),
                (f'공식 점검 기록은 “{jb} {sb}의 {tb} {kb} ‹{b}›{particle(b, "이/가")} 정상 운영된다”라고 결론냈다. 현장 사진과 담당자 확인이 그 결론을 뒷받침한다. 미승인 상태인 것은 별도 출장 요청이다.', 'b', 'asserted_quote_positive', 'B에 대한 인용 주장은 현장 근거와 확인이 있는 적극적 진술이다.'),
                (f'칠레 업체의 발언을 그대로 옮긴다. “우리 전시용 장난감 ‹{a}›{particle(a, "을/를")} 보러 오세요.” 기자는 이것이 누온사의 {ka}{particle(ka, "과/와")} 무관한 상품임을 확인했다. 표적은 인용 안의 상품명이다.', None, 'quoted_external_homonym', '인용 안의 이름이 가리키는 것은 명시적으로 다른 회사의 장난감이다.'),
                (f'사내 어휘 수업은 ‹{b}›{particle(b, "이라는/라는")} 문자열의 첫 글자를 비교한다. 교사는 실제 {kb}{particle(kb, "이나/나")} 담당 조직을 지칭하는 예문이 아니라 철자 자체를 다룬다고 말했다.', None, 'non_mention_metalinguistic', '실제 대상을 언급하지 않고 문자열의 철자만 대상으로 삼는다.'),
                (f'{ja} {sa}의 {ta} {ka} {a}{particle(a, "이/가")} 등록된 것은 맞다. 그러나 이 대화의 마지막 ‹{a}›{particle(a, "은/는")} 퇴직자 모임이 만든 독립 보드게임 이름이다. 진행자는 마지막 발생을 업무 시스템으로 해석하지 말라고 설명했다.', None, 'repeated_homonym', '정상 등록 설명 뒤에 놓인 요청 발생은 별도의 보드게임 이름이다.'),
                (f'의뢰인은 ‹{shared}› 관련 자료가 필요하다고만 말했다. 업무 목적과 담당 조직을 물었지만 답하지 않았다. 두 등록 항목 모두 이 약칭을 써서 현 단계에서는 선택할 수 없다.', None, 'shared_alias_ambiguous', '둘 모두 가능한 공유 약칭이며 선택에 필요한 정보가 없다.'),
            ]
        else:
            authored = [
                (f'{ja} {sa}{particle(sa, "은/는")} {pa}{particle(pa, "을/를")} 위해 {ta} {ka} ‹{a}›{particle(a, "을/를")} 사용한다. 이번 요청은 그 등록 업무 대상 자체에 관한 것이다. 별도로 논의한 담당자 휴가는 대상의 운영 중단을 의미하지 않는다.', 'a', 'unique_alias_irrelevant_negative', '정의와 일치하는 A가 명시되며 담당자 휴가라는 무관한 상태를 분리했다.'),
                (f'이번 안내에서 ‹{cb}›{particle(cb, "은/는")} {jb} {sb}의 {tb} {kb}{particle(kb, "으로/로")} 소개된다. 안내문 작성자는 해당 조직에서 실제 사용하는 정식 명칭임을 확인했다.', 'b', 'canonical', 'B 정식 명칭의 국가·조직·상태·종류가 모두 일치한다.'),
                (f'{ja} {sa}의 보고서는 {ta} {ka}인 ‹{shared}›에 {pa} 안건을 보냈다고 적었다. 보고서는 같은 약칭의 다른 업무가 아닌 이 조직의 등록 대상을 지칭한다.', 'a', 'shared_alias_resolvable', '공유 약칭이지만 앞의 구체적 속성과 업무가 A를 특정한다.'),
                (f'책임자는 “{jb} {sb}{particle(sb, "이/가")} 맡는 {tb} {kb} ‹{b}›{particle(b, "을/를")} 계속 운영한다”라고 설명했다. 회의는 그 사실을 확인하고 기록했다. 폐기한 것은 회의 자료의 중복 사본뿐이다.', 'b', 'asserted_quote_positive', '확인된 B 운영 진술이며 폐기 표현은 자료 사본에만 해당한다.'),
                (f'보관 사진의 ‹{a}›{particle(a, "은/는")} 2011년에 폐지된 주민 합창단을 뜻한다. 당시 공연 안내에 쓰인 이름이며 현재 누온사 {sa}의 업무 대상과 조직·기능·시점이 모두 다르다.', None, 'historical_nil', '폐지된 동명의 합창단으로서 현재 등록 A와 다르다.'),
                (f'인사 문서가 지칭하는 ‹{b}|담당자›는 {jb} 지점에서 근무하는 사람이다. {kb} 자체를 등록하는 요청이 아니라 이 사람의 교대 시간을 정하는 요청이다.', None, 'role_composition', '표적의 전체 표현이 담당자라는 사람을 가리키므로 B의 ID를 사용할 수 없다.'),
                (f'{ja} {sa}{particle(sa, "은/는")} {ta} {ka}인 {a}{particle(a, "을/를")} 쓴다. 고객이 뒤이어 언급한 ‹{a}›{particle(a, "은/는")} 고객사가 별도로 발행한 출입 허가증 이름이다. 등록 업무 대상과 그 허가증은 서로 다른 물건이며 같은 이름을 쓸 뿐이다.', None, 'repeated_exception_permission', '요청된 두 번째 발생은 실제로 별개인 고객사의 출입 허가증이다.'),
                (f'제목이 ‹{shared}›인 파일에는 대상 설명이 없다. 작성자의 소속도 빠져 있으며 두 등록 업무 중 어느 것인지 확인할 추가 자료가 아직 없다.', None, 'shared_alias_ambiguous', '공유 약칭 파일 제목만으로 대상 업무를 구별할 수 없다.'),
            ]
        cases = []
        for i, (marked, entity, stratum, rationale) in enumerate(authored, 1):
            text, surface, core, full = target(marked)
            eid = f'global:{keya if entity == "a" else keyb}' if entity else None
            label = ('LINK' if entity else 'AMBIGUOUS' if stratum == 'shared_alias_ambiguous'
                     else 'COMPOSITIONAL' if stratum == 'role_composition'
                     else 'NON_MENTION' if stratum == 'non_mention_metalinguistic' else 'NIL')
            cases.append({'case_id': f'{family_id}:{i}', 'document_id': f'{family_id}:doc{i}',
                'text': text, 'document_sha256': sha(text), 'target_surface': surface,
                'target_core_span': core, 'target_full_span': full,
                'expected_entity_id': eid, 'stratum': stratum,
                'gold': {'label': label, 'entity_ref': eid,
                         'full_identity': 'SAME' if entity else 'DISTINCT_OR_UNSUPPORTED'},
                'qa': {'question': '표시된 발생 위치가 가리키는 사전 대상의 정식 명칭은?',
                       'answers': [ca if entity == 'a' else cb] if entity else [],
                       'is_impossible': entity is None, 'requires_terminology': True},
                'rationale': rationale})
        families.append({'family_id': family_id,
            'evaluation_split': 'development' if n in DEVELOPMENT else 'confirmation',
            'source_facts': f'두 항목은 가상 기업 누온사의 서로 다른 업무다. {a}{particle(a, "과/와")} {b}{particle(b, "은/는")} 고유 이름이고 {shared}는 양쪽 모두에 등록한 충돌 약칭이다. 지정한 발생 위치의 전체 표현을 항목 자체로 연결하는 과제다.',
            'terms': terms, 'cases': cases})
    return {'schema_version': 1, 'dataset_id': 'ktrf-routing-confirmation-source-v1',
        'annotation_origin': 'AI_AUTHORED', 'authored_by': 'codex-fresh-routing-gold-agent',
        'human_verified': False,
        'gold_source': 'Fictional glossary worlds and source-authored occurrence labels, written before any resolver/model output.',
        'source_scenario_styles': 4,
        'split_design': {'unit': 'family', 'development_families': 8,
                         'confirmation_families': 16, 'determined_before_inference': True},
        'limitations': [
            'AI-authored synthetic source gold with a second AI reviewer; not human gold or a real deployment sample.',
            '192 documents share 24 lexical families and four scenario writing styles; family counts are the primary resampling unit.',
            'Glossary applicability facts deliberately use explicit source literals. An evidence-literal guard is not a general semantic guarantee.',
            'Every LINK target has a registered source-world entity, but candidates must still come from production retrieval without gold insertion.',
            'No global end-to-end or accepted-ID risk guarantee follows from this fixed synthetic confirmation sample.',
        ], 'families': families}


if __name__ == '__main__':
    artifact = make_source()
    Path(__file__).with_name('source_gold.json').write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')

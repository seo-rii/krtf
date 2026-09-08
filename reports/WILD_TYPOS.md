# 실제 텍스트에 조직명 오타는 얼마나 있는가 (§5.2, OQ-001)

등록 표면형(한글 3자 이상) 208개에 대해 캐시된 코퍼스 6개, 한글 토큰 1,988,119개를 편집거리 1로 훑었다. **resolver를 쓰지 않는다** — resolver의 채널로 재면 이미 회수하는 오타만 보이므로, 입력 분포를 묻는 질문에 회수율로 답하게 된다. 여기 쓰인 기계장치는 편집거리뿐이다.

| 코퍼스 | 문장 | 한글 토큰 | 근접 | INFLECTION | OTHER |
|---|---:|---:|---:|---:|---:|
| `holdout` | 29,735 | 252,705 | 3,474 | 1,555 | 1,919 |
| `holdout2` | 18,000 | 175,572 | 2,569 | 1,147 | 1,422 |
| `holdout3` | 46,000 | 447,083 | 6,817 | 3,313 | 3,504 |
| `law` | 21,061 | 257,633 | 1,689 | 347 | 1,342 |
| `web` | 34,000 | 185,404 | 1,337 | 273 | 1,064 |
| `wild` | 114,605 | 669,722 | 6,875 | 1,354 | 5,521 |

**INFLECTION** = 표면형 + 1음절이고 tail parser가 조사·접미로 설명하는 것(`삼성전자가`). **OTHER** = 나머지 — 오타라면 여기 있다.

## 1. 오타는 관측되지 않는다

OTHER를 빈도순으로 읽으면 오타가 아니라 **한 글자 차이의 평범한 단어**다. 총계를 믿지 말고 목록을 읽어야 하는 이유가 이것이다:

- `스마트 ~ 이마트` × 518
- `이벤트 ~ 이마트` × 422
- `서울대 ~ 서울시` × 348
- `기재와 ~ 기재부` × 315
- `카카오톡 ~ 카카오` × 303
- `유플러스 ~ 홈플러스` × 301
- `대법관 ~ 대법원` × 221
- `환경을 ~ 환경부` × 209
- `기업은 ~ 기업은행` × 208
- `교육을 ~ 교육부` × 189
- `경우도 ~ 경기도` × 189
- `서울의 ~ 서울시` × 177
- `미래를 ~ 미래부` × 176
- `산업의 ~ 산업부` × 144
- `한국은 ~ 한국은행` × 139
- `기재에 ~ 기재부` × 134
- `공정한 ~ 공정위` × 133
- `기재된 ~ 기재부` × 132
- `사이버 ~ 네이버` × 115
- `플러스 ~ 홈플러스` × 111
- `금융권 ~ 금융위` × 110
- `경기가 ~ 경기도` × 103
- `노동자 ~ 노동부` × 101
- `금융위기 ~ 금융위` × 95
- `환경에 ~ 환경부` × 91

빈도 상위는 흔한 단어이므로, 오타가 숨는다면 **1회 등장** 쪽이다. 그쪽에서 뽑은 표본:

- `학사원 ~ 감사원`
- `금융뿐 ~ 금융위`
- `제어도 ~ 제주도`
- `서울만 ~ 서울시`
- `한국석탄공사 ~ 한국석유공사`
- `받기도 ~ 경기도`
- `과천시 ~ 인천시`
- `한두원 ~ 한수원`
- `경기나 ~ 경기도`
- `네이트 ~ 네이버`
- `서울특별시교육감 ~ 서울특별시교육청`
- `노동계 ~ 노동부`
- `부산역 ~ 부산시`
- `전수원 ~ 한수원`
- `산업통산자원부 ~ 산업통상자원부`
- `해수는 ~ 해수부`
- `해수로 ~ 해수부`
- `대우해선 ~ 대우조선`
- `세종대 ~ 세종시`
- `제작도 ~ 제주도`
- `금융은 ~ 금융위`
- `미래는 ~ 미래부`
- `강정원 ~ 국정원`
- `경남도 ~ 경기도`
- `서울산 ~ 서울시`

**이 중 오타처럼 보이는 것들을 문맥에서 직접 읽었다. 전부 오타가 아니었다:**

- `한두원` — "한두원 코웨이 AirCare필터개발팀장". **사람 이름**이다. `한수원`의 오타가 아니다.
- `학사원` — "일본 학사원상 수상자". 실재하는 기관이다.
- `제어도`, `금융뿐` — `제어`·`금융` + 조사. 형태론이 tail parser의 1음절 규칙에 걸리지 않았을 뿐이다.
- `한국석탄공사` — `한국석유공사`의 오타가 아니라 **다른 실재 기업**이고, 두 이름이 *같은 문장에* 함께 나온다: "한국석유공사와 한국광해광업공단 한국가스공사 한국석탄공사 등 자원 공기업".
- `과천시` — 경기도의 실재 도시, 17회. `인천시`의 오타가 아니다.

즉 오타처럼 보이는 후보를 **전수로 읽고 나면 남는 오타가 없다**. 총계가 손으로 읽을 만한 크기일 때 총계만 인용하면 이 결론에 도달할 수 없다.

## 2. 완화의 비용은 코퍼스와 무관하다

등록 표면형끼리 편집거리 1인 쌍이 **9개** 있다. 이것은 어떤 코퍼스도 필요 없는 사실이고, typo 임계값을 낮출 때 정확히 이 쌍들이 서로 회수된다:

- `경상남도` ↔ `경상북도`
- `관세청` ↔ `국세청`
- `국방부` ↔ `국토부`
- `기업은행` ↔ `산업은행`
- `대구광역시` ↔ `대전광역시`
- `부산광역시` ↔ `울산광역시`
- `전라남도` ↔ `전라북도`
- `충청남도` ↔ `충청북도`
- `행안부` ↔ `행자부`

## 3. 오타 채널이 실제로 무엇에 반응하는가

실문장 24,000개에 resolver를 돌려 `jamo`/`keyboard` 채널이 제안한 mention을 전부 모았다: **122건**.

| 코퍼스 | 표면형 | 채널 | 판정 | 후보 |
|---|---|---|---|---|
| `holdout` | `인천공항으` | jamo | KB_MISSING | ORG_IIAC, KB_MISSING |
| `holdout` | `사업부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `한국석탄공사` | jamo | KB_MISSING | ORG_KNOC, KB_MISSING |
| `holdout` | `한국석탄공사` | jamo | KB_MISSING | ORG_KNOC, KB_MISSING |
| `holdout` | `마카오` | jamo | AMBIGUOUS | ORG_KAKAO, KB_MISSING |
| `holdout` | `마카오` | jamo | AMBIGUOUS | ORG_KAKAO, KB_MISSING |
| `holdout` | `마카오` | jamo | AMBIGUOUS | ORG_KAKAO, KB_MISSING |
| `holdout` | `미래자동차` | jamo | KB_MISSING | ORG_KIA, KB_MISSING |
| `holdout` | `광주과학기` | jamo | KB_MISSING | ORG_GWANGJU_C, KB_MISSING |
| `holdout` | `한국석유공업` | jamo | KB_MISSING | ORG_KNOC, KB_MISSING |
| `holdout` | `한국석유공업` | jamo | KB_MISSING | ORG_KNOC, KB_MISSING |
| `holdout` | `한국석유공` | jamo | AMBIGUOUS | ORG_KNOC, KB_MISSING |
| `holdout` | `한국석유공` | jamo | AMBIGUOUS | ORG_KNOC, KB_MISSING |
| `holdout` | `한국석유공업` | jamo | KB_MISSING | ORG_KNOC, KB_MISSING |
| `holdout` | `한국석유공` | jamo | AMBIGUOUS | ORG_KNOC, KB_MISSING |
| `holdout` | `사업부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `시선바이오` | jamo | KB_MISSING | ORG_SSBIO, KB_MISSING |
| `holdout` | `시선바이오` | jamo | KB_MISSING | ORG_SSBIO, KB_MISSING |
| `holdout` | `중소벤처기업진` | jamo | KB_MISSING | ORG_MSS, KB_MISSING |
| `holdout` | `가농바이오` | jamo | KB_MISSING | ORG_SSBIO, KB_MISSING |
| `holdout` | `사업부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `사업부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `산업통산자원부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `산업통산자원부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `삼성증권` | jamo | KB_MISSING | ORG_SSHEAVY, KB_MISSING |
| `holdout` | `상용차` | jamo | AMBIGUOUS | ORG_SYMC, KB_MISSING |
| `holdout` | `상용차` | jamo | AMBIGUOUS | ORG_SYMC, KB_MISSING |
| `holdout` | `삼성증권` | jamo | KB_MISSING | ORG_SSHEAVY, KB_MISSING |
| `holdout` | `삼성증권` | jamo | KB_MISSING | ORG_SSHEAVY, KB_MISSING |
| `holdout` | `전국상인연합회` | jamo | KB_MISSING | ORG_FKI, KB_MISSING |
| `holdout` | `서울중앙지법` | jamo | AMBIGUOUS | ORG_SCDC, ORG_SCDPO |
| `holdout` | `인천관광공사` | jamo | KB_MISSING | ORG_IIAC, KB_MISSING |
| `holdout` | `인천관광공사` | jamo | KB_MISSING | ORG_IIAC, KB_MISSING |
| `holdout` | `산업분` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout` | `이천시` | jamo | AMBIGUOUS | ORG_INCHEON, KB_MISSING |
| `holdout` | `사업부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |
| `holdout2` | `삼성증권` | jamo | KB_MISSING | ORG_SSHEAVY, KB_MISSING |
| `holdout2` | `마카오` | jamo | AMBIGUOUS | ORG_KAKAO, KB_MISSING |
| `holdout2` | `삼성증권` | jamo | KB_MISSING | ORG_SSHEAVY, KB_MISSING |
| `holdout2` | `사업부` | jamo | AMBIGUOUS | ORG_MOTIE, KB_MISSING |

**확정된 것은 하나도 없다**: AMBIGUOUS 62건, KB_MISSING 60건. 서로 다른 표면형 52종.

그리고 회수된 오타도 하나도 없다. 발화한 표면형은 두 종류다:

- **등록되지 않은 다른 실재 조직** — `삼성증권`(→삼성중공업), `서울중앙지법`(법원 →`서울중앙지검` 검찰청), `한국석탄공사`(→한국석유공사), `마카오`(→`카카오`). 오타가 아니라 이웃이다.
- **잘린 조각** — `인천공항으`, `광주과학기`, `한국석유공`, `중소벤처기업진`. 경계가 어긋난 문자열이지 사람이 잘못 친 것이 아니다.

두 종류 모두 AMBIGUOUS 또는 KB_MISSING으로 남는 것이 옳은 동작이고, 실제로 122건 전부 그렇게 남았다. 임계값을 낮추면 회수되는 것은 오타가 아니라 이 목록이다.

## 무엇을 뜻하는지

- `VARIANT_RECALL.md`의 typo 66.6% / typo+particle 64.9%는 **주입된** 변형에 대한 값이다. 뉴스·웹·판례·커뮤니티 분포에서 그 입력은 관측되지 않는다.
- 그러므로 그 두 셀을 근거로 임계값을 완화하면, 관측되지 않는 것을 얻기 위해 위 목록의 실재하는 쌍을 잃는다. `관세청`↔`국세청`, `경상남도`↔`경상북도`는 한 글자 차이의 서로 다른 기관이다.
- 트랙을 폐기하자는 뜻은 아니다. OCR·입력기·필사 경로에서는 오타가 실재하며, 그런 입력을 받는 배치에서는 이 트랙이 옳은 지표다. 다만 **일반 텍스트 파이프라인의 우선순위 근거로는 쓸 수 없다.**

*측정 시점: commit `b0d5b9b`, 2026-09-08 · 코퍼스 `50c47aec4e66acf1` (114,605문장, 11개 출처). 리포트와 코드가 어긋나면 코드가 맞다 — 재생성해서 확인할 것.*

*generated by `python -m eval.run_wild_typos`*
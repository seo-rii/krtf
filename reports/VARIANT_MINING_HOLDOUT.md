# 미등록 변형 채굴 — 카탈로그·사전 백로그

resolver는 이미 `full_surface`로 **자기가 가지지 못한 이름이 여기 있다**고 말하고 있다. 이 리포트는 그 진술을 모아 순위를 매긴 것이며, 새로운 분석을 하지 않는다 — 공개 응답 필드만 읽는다.

재현: `python -m eval.run_variant_mining` · 리포트만 다시 쓰려면 `--render-only`.

표본: 실문장 **20,000문장**, realorg glossary.

## 0. 무엇을 보고 무엇을 버렸나

| 단계 | 건수 |
|---|---:|
| mention | 13,948 |
| core보다 넓은 표면형 | 1,342 |
| 그중 등록된 `COMPOSES_TO`가 이름을 준 것 | 0 |
| 서로 다른 (entity, 잔여부) 자리 | 283 |
| 그중 **1회성** | 169 |
| 서로 다른 잔여부 | 206 |
| 그중 여러 entity에 붙는 것 | 14 |
| 그중 이미 카탈로그에 있는 것 | 11 |

**버린 쪽이 리포트의 절반이다.** 채굴기가 맞힌 것만 보이면 반증할 수 없다.

자리별 빈도 분포(1회성이 대부분이라는 것이 이 백로그의 성질이다):

| 관측 횟수 | 자리 수 |
|---|---:|
| 1 | 169 |
| 2 | 44 |
| 3 | 21 |
| 4 | 14 |
| 5 | 6 |
| 6 | 5 |
| 7 | 4 |
| 8 | 1 |
| 9 | 2 |
| 10+ | 17 |

## 1. 종결어 공백 — 카탈로그가 읽지 못하는 끝

**여러 entity 뒤에 반복해서 나타나는 잔여부**다. 우연이라면 서로 무관한 이름들에서 같은 끝이 반복되어야 하므로, entity 수가 곧 증거다. M3까지 손으로 하던 taxonomy 작업이 여기서는 측정값이다.

> §5는 `wild tail 목록을 검토 없이 전역 SUFFIXES에 추가`하는 것을 금지한다. 이 표는 **검토 대상 목록**이지 패치가 아니다. class를 고르는 것은 사람의 일이고, 잘못된 class는 대칭이 아니다 — `NAME_PART`/`REFERENTIAL`은 전체 표면형의 확정을 **허용**한다.

- 발견: **3건**

| 잔여부 | entity 수 | 관측 | 문서 | tail 파서가 읽은 관계 | 예시 |
|---|---:|---:|---:|---|---|
| `시장` | 4 | 5 | 5 | `ROLE_OF` 5 | 사진 제공 CJ제일제당 서울경제 CJ제일제당이 미국에서 이뤄낸… |
| `기` | 3 | 26 | 26 | `UNKNOWN` 26 | 2008년 글로벌 금융위기 이후 가장 큰 감소 폭이다.… |
| `들` | 3 | 3 | 3 | `UNKNOWN` 3 | 아울러 체험형 과학도서관 과학실험 체험관 운영 등에 전문가가 … |

## 2. 이름 공백 — 사전이 가지지 못한 이름

**한 entity 뒤에서만 반복되는 잔여부**다. 이쪽이 M4가 원래 노린 것이고, 둘 중 **약한** 증거다: 약어 채널은 우연히 겹치는 접두를 진짜만큼 안정적으로 반복해서 맞힌다(`해수` + `욕장`이 9개 문서에서 버텼다). 흔한 것은 이름이 아니라 **단어**이기 때문이다.

그래서 이름 공백은 **exact 채널이 찾은 core 뒤에서만** 채굴한다 — 등록된 표면형이지 부분수열이 아니라는 뜻이고, `카카오`+`톡`과 `해수`+`욕장`을 가르는 것이 정확히 그 차이다.

- 발견: **26건**

| 표면형 | core entity | 잔여부 | 관계 | 판정 | 관측 | 문서 |
|---|---|---|---|---|---:|---:|
| `카카오톡` | `ORG_KAKAO` | `톡` | UNKNOWN | UNKNOWN | 75 | 64 |
| `카카오모빌리티` | `ORG_KAKAO` | `모빌리티` | UNKNOWN | UNKNOWN | 39 | 35 |
| `카카오게임즈` | `ORG_KAKAO` | `게임즈` | UNKNOWN | UNKNOWN | 36 | 33 |
| `네이버웹툰` | `ORG_NAVER` | `웹툰` | UNKNOWN | UNKNOWN | 23 | 21 |
| `카카오엔터테인먼트` | `ORG_KAKAO` | `엔터테인먼트` | UNKNOWN | UNKNOWN | 16 | 16 |
| `카카오페이` | `ORG_KAKAO` | `페이` | UNKNOWN | UNKNOWN | 13 | 10 |
| `카카오뱅크` | `ORG_KAKAO` | `뱅크` | UNKNOWN | UNKNOWN | 10 | 10 |
| `포스코홀딩스` | `ORG_POSCO` | `홀딩스` | AFFILIATE_OF | DISTINCT_FROM_CORE | 7 | 7 |
| `경기도지사` | `ORG_GYEONGGI` | `지사` | ROLE_OF | DISTINCT_FROM_CORE | 6 | 6 |
| `전경련회관` | `ORG_FKI` | `회관` | UNKNOWN | UNKNOWN | 6 | 6 |
| `연합뉴스TV` | `ORG_YONHAP` | `TV` | UNKNOWN | UNKNOWN | 5 | 5 |
| `카카오내비` | `ORG_KAKAO` | `내비` | UNKNOWN | UNKNOWN | 5 | 5 |
| `카카오메이커스` | `ORG_KAKAO` | `메이커스` | UNKNOWN | UNKNOWN | 5 | 4 |
| `KT클라우드` | `ORG_KT` | `클라우드` | UNKNOWN | UNKNOWN | 4 | 4 |
| `금융위원장` | `ORG_FSC` | `원장` | ROLE_OF | DISTINCT_FROM_CORE | 4 | 4 |
| `네이버웹툰과` | `ORG_NAVER` | `웹툰과` | UNKNOWN | DISTINCT_FROM_CORE | 4 | 4 |
| `셀트리온제약` | `ORG_CELLTRION` | `제약` | AFFILIATE_OF | DISTINCT_FROM_CORE | 4 | 4 |
| `카카오페이증권` | `ORG_KAKAO` | `페이증권` | AFFILIATE_OF | DISTINCT_FROM_CORE | 4 | 4 |
| `현대차지부` | `ORG_HYUNDAI_MOTOR` | `지부` | UNKNOWN | DISTINCT_FROM_CORE | 4 | 4 |
| `KT스튜디오지니` | `ORG_KT` | `스튜디오지니` | UNKNOWN | UNKNOWN | 3 | 3 |
| `공정위원장` | `ORG_FTC` | `원장` | ROLE_OF | DISTINCT_FROM_CORE | 3 | 3 |
| `네이버클라우드` | `ORG_NAVER` | `클라우드` | UNKNOWN | UNKNOWN | 3 | 3 |
| `셀트리온헬스케어` | `ORG_CELLTRION` | `헬스케어` | AFFILIATE_OF | DISTINCT_FROM_CORE | 3 | 3 |
| `카카오지회` | `ORG_KAKAO` | `지회` | PART_OF | DISTINCT_FROM_CORE | 3 | 3 |
| `카카오페이포인트` | `ORG_KAKAO` | `페이포인트` | UNKNOWN | UNKNOWN | 3 | 3 |

## 이 리포트가 말하지 않는 것

- **어떤 class인지, 무엇을 뜻하는지.** 채굴기는 이름이 *있다*는 것만 말한다. canonical과 class는 사람이나 LLM이 제안하고 `ktrf.registry.proposals`의 검증·승인을 거친다. 모델 추론만으로 영구 사전이 바뀌지 않는다.
- **core 매칭이 옳았는지.** 이름 공백의 core는 확정된 것도 있고 후보에 그친 것도 있다. 확정 정확도는 `WILD_CORPUS.md`가 잰다.

*측정 시점: commit `f7ec657-dirty`, 2026-09-03 · 표본 20,000문장 · held-out 코퍼스 `009669e9c1085642` (29,735문장, 2개 출처). **작업 트리가 커밋과 다르다 — 이 수치는 어떤 커밋에도 없는 코드의 것이다.** 리포트와 코드가 어긋나면 코드가 맞다 — 재생성해서 확인할 것.*
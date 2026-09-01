# 변형 회수 — variant family 단위 평가

이 리포트의 단위는 mention이 아니라 **등록 용어**다. glossary의 각 entity에 대해 표면형을 formation 하나씩 변형해 실문장에 넣고, 그 용어가 돌아오는지를 묻는다. headline은 family 매크로 평균이라 천 번 언급되는 부처와 한 번 언급되는 용어가 같은 무게를 갖는다.

재현: `python -m eval.run_variant_recall` · seed 20260901 · 170 families × 16 formations = **3059 cases** · host 문장 6000개.

대조군은 같은 스크립트·같은 seed를 다른 체크아웃에서 돌린 것이다 (`--compare`). 두 arm은 같은 표본·같은 case를 본다.

## 0. 한눈에

| 지표 | 조건 | 값 |
|---|---|---:|
| **variant-family macro recall** | `\|candidate` | 0.932 → **0.9397** (+0.0077) |
| ├ Level A formation | `\|candidate` | 0.9868 → **0.9868** (0.0) |
| └ **Level B formation** | `\|candidate` | 0.7296 → **0.7626** (+0.033) |
| commit macro (§2 SAME 형성) | `\|commit` | 0.9865 → **0.9865** (0.0) |
| core span 오분해율 | `\|mention` | 0.0075 → **0.0072** (-0.0003) |
| 잘못된 entity 확정 | `\|commit` | 0 → **0** (0) |
| **불변조건 ② 위반** | `\|commit` | 0 → **0** (0) |

마지막 두 줄은 비율이 아니라 건수다. 0이 아니면 그 자체가 결함이고, 재현율과 교환할 수 있는 값이 아니다.

Level A는 결정적 정규화·분해로 닿는 formation(원형·띄어쓰기·전각·조사·자모 분리)이고, Level B는 fuzzy 채널로만 닿는 것(오타·키보드)이다. **전체 매크로는 Level A가 끌어올린다** — 움직임이 보이는 곳은 B다.

## 1. formation별

`§2 계약` 열은 VARIANTS_PLAN §2에서 왔다 — 리졸버의 guard 규칙이 아니라 계획 문서다. guard에서 가져오면 정의상 통과하는 시험이 된다.

| formation | tier | §2 계약 | cases | candidate macro | micro | commit macro | span 정확 | `UNKNOWN` 판정 | 위반 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `bare` | A | SAME | 233 | 1.0 → **1.0** (0.0) | 1.0 | 1.0 | 1.0 | — | 0 |
| `spaced` | A | SAME | 233 | 0.9588 → **0.9588** (0.0) | 0.9657 | 0.9588 | 0.9657 | — | 0 |
| `fullwidth` | A | SAME | 19 | 1.0 → **1.0** (0.0) | 1.0 | 1.0 | 1.0 | — | 0 |
| `particle` | A | SAME | 214 | 1.0 → **1.0** (0.0) | 1.0 | 1.0 | 1.0 | — | 0 |
| `particle_chain` | A | SAME | 214 | 1.0 → **1.0** (0.0) | 1.0 | 1.0 | 1.0 | — | 0 |
| `typo` | B | CONDITIONAL | 214 | 0.6688 → **0.6688** (0.0) | 0.6682 | 0.0 | 0.6682 | — | 0 |
| `typo_particle` | B | CONDITIONAL | 214 | 0.6201 → **0.6201** (0.0) | 0.6308 | 0.0 | 0.6355 | — | 0 |
| `keyboard` | B | CONDITIONAL | 214 | 0.974 → **0.974** (0.0) | 0.9766 | 0.0 | 0.9766 | — | 0 |
| `jamo` | A | SAME | 214 | 1.0 → **1.0** (0.0) | 1.0 | 1.0 | 1.0 | — | 0 |
| `mixed_abbrev` | B | CONDITIONAL | 6 | 0.0 → **1.0** (+1.0) | 1.0 | 0.0 | 1.0 | — | 0 |
| `base_modifier` | A | CONDITIONAL | 214 | 1.0 → **1.0** (0.0) | 1.0 | 1.0 | 1.0 | — | 0 |
| `derivative_org` | A | FORBIDDEN | 214 | 1.0 → **1.0** (0.0) | 1.0 | 0.3019 | 1.0 | 118 → **118** (0) | 0 |
| `derivative_role` | A | FORBIDDEN | 214 | 1.0 → **1.0** (0.0) | 1.0 | 0.3831 | 1.0 | 86 → **86** (0) | 0 |
| `derivative_particle` | A | FORBIDDEN | 214 | 1.0 → **1.0** (0.0) | 1.0 | 0.4091 | 1.0 | 85 → **85** (0) | 0 |
| `org_unit` | A | FORBIDDEN | 214 | 1.0 → **1.0** (0.0) | 1.0 | 0.8571 | 1.0 | 32 → **32** (0) | 0 |
| `artifact` | A | FORBIDDEN | 214 | 1.0 → **1.0** (0.0) | 1.0 | 0.8506 | 1.0 | 33 → **33** (0) | 0 |

FORBIDDEN 행의 `commit macro`는 재현율이 아니라 **보수성**이다: core에 확정을 건 비율이며, 낮을수록 guard가 많이 보류했다는 뜻이다. CONDITIONAL 행의 0.0도 결함이 아니다 — §2가 확정을 요구하지 않는다.

## 2. FORBIDDEN 계약 — 막았는가, 그리고 뭐라고 불렀는가

`한전노조`는 다른 조직이고 `금감원장`은 사람이다. 두 가지를 따로 센다: **확정을 막았는가**(불변조건 ②, 위 표의 `위반` 열)와 **관계를 이름으로 말했는가**. 앞은 계약이라 0이어야 하고, 뒤는 카탈로그 커버리지라 개선 대상이다 — 카탈로그를 넓히면 뒤가 오르고 앞은 그대로여야 한다.

- FORBIDDEN cases: **1070**
- 넓은 표면형을 응답에 실은 것: 1070
- 그중 `UNKNOWN` 판정: 354 → **354** (0) (카탈로그 확장 여지)

관계 라벨 분포: `UNKNOWN` 354, `ROLE_OF` 192, `PART_OF` 182, `ARTIFACT_OF` 181, `DERIVED_FROM` 110, `NAMED_VARIANT` 51

## 3. Confusion — 닮은 것 중에 고르기

fake glossary는 코퍼스와 형태소를 공유하지 않는 이름을 쓴다. 거기서의 0은 '엉뚱한 것을 만들지 않는다'는 뜻이지 '둘 중 맞는 것을 고른다'는 뜻이 아니다. 여기 decoy는 전부 **실제 등록 entity에 붙여** 만든다.

- decoy entity 110개 (근접 표면형 60, 약칭 충돌 25, 접두 확장 25)
- decoy가 **후보로 올라온** mention: 184 — 0이면 이 시험은 무의미하다(decoy에 닿지도 못했다는 뜻)
- **decoy 확정(FP): 0건**

### 3.1 decoy를 넣으면 진짜 확정이 줄어드는가

같은 문장·같은 silver span을 decoy 있는 스냅샷과 없는 스냅샷에서 각각 돌린 쌍 비교다.

- silver mention 343건, gold-in-set 1.0
- 확정: decoy 없음 332 → decoy 있음 280 (**차이 52**)

### 3.2 약칭 충돌 — 두 뜻이 생기면 확정을 미루는가

decoy가 실제 약칭을 **같이** 등록한다. 그러면 그 약칭의 올바른 답은 AMBIGUOUS(두 뜻 모두 후보)이지 어느 한쪽의 확정이 아니다.

- 충돌 약칭 mention: 93
- 두 뜻이 모두 prediction set에: 93
- **그럼에도 확정: 0 (과확정률 0.0)**

## 4. 최악 family

매크로 평균이 감추는 것이 여기 있다 — 이 용어들은 어떤 변형에서도 잘 돌아오지 않는다.

| entity | family recall |
|---|---:|
| `ORG_JTBC` | 0.6667 |
| `ORG_KBS` | 0.6667 |
| `ORG_KT` | 0.6667 |
| `ORG_MBC` | 0.6667 |
| `ORG_SBS` | 0.6667 |
| `ORG_YTN` | 0.6667 |
| `ORG_KOTRA` | 0.8333 |
| `ORG_CELLTRION` | 0.8571 |
| `ORG_GWL` | 0.8571 |
| `ORG_GYEONGGI` | 0.8571 |
| `ORG_HANJIN` | 0.8571 |
| `ORG_HMM` | 0.8571 |

## 5. 읽는 법과 한계

- **매크로와 마이크로가 갈리면 매크로를 본다.** 마이크로는 case를 많이 만든 family가 지배하고, 이 스위트는 family마다 같은 수를 만들므로 둘의 차이는 곧 family 간 편차다.
- 변형은 합성이고 **문맥은 실제**다. 사람이 라벨한 실문장 gold는 [VARIANT_GOLD.md](VARIANT_GOLD.md)에서 따로 잰다.
- formation은 §2 표의 행에 대응한다. `CONDITIONAL` 행은 확정해도 안 해도 계약 위반이 아니므로 **판정을 내리지 않고 비율만** 싣는다.
- 적용 불가 cell(라틴 표면형에 중성 오타)은 0점이 아니라 **분모에서 빠진다**. 문자 체계 때문에 family가 손해 보면 안 된다.
- decoy는 합성이지만 실제 등록 표면형에서 **1 중성 거리**로 만든다. 형태소를 공유하지 않는 fake glossary와는 난이도가 다르다.

*측정 시점: commit `5203ac5`, 2026-09-01. 리포트와 코드가 어긋나면 코드가 맞다 — 재생성해서 확인할 것.*

*generated by `python -m eval.run_variant_recall`*
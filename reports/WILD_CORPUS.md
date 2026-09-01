# KTRF Wild-Corpus 벤치마크 (실제 한국어 텍스트)

코퍼스: HuggingFace 공개 한국어 텍스트 114605문장 (뉴스 헤드라인·국민청원·판례 전문·위키 지문 — 다중 도메인). 합성 데이터와 달리 구현 카탈로그와 독립적인 실 분포다. 재현: `python -m eval.run_wild` (최초 실행 시 다운로드).

소스 구성: `klue:ynat:train` 45634, `korean-petitions:default:train` 12000, `korean_law_open_data_precedents:default:train` 12000, `klue:sts:train` 11652, `klue:ynat:validation` 9096, `wikipedia:20231101.ko:train` 8000, `squad_kor_v1:squad_kor_v1:train` 6670, `klue:nli:train` 5036, `kobest_v1:boolq:train` 3000, `klue:nli:validation` 1000, `klue:sts:validation` 517

> [!WARNING]
> **아래 수치는 commit `8d6f427` 시점 측정이며, 이후 resolver가 세 번
> 바뀌었다** — M1 공유 segmentation(`decfb3d`), M2 typed tail, M3 카탈로그
> 확장(`975056b`). 전체 재생성은 114,605문장 ×6 pass로 약 6시간이라 아직
> 돌리지 않았다. 대신 각 변경을 표본으로 쌍 비교했다.
>
> **침묵의 값 (설명된 tail이 core의 확정을 깎지 않는다)** — 20,000문장,
> 두 체크아웃에서 `run_wild_regression --single`:
>
> | 지표 | M3 | +calibration |
> |---|---:|---:|
> | silver mentions / 탐지 / gold-in-set | 1,176 / 1.0 / 1.0 | 1,176 / 1.0 / 1.0 |
> | **RESOLVED commits** | 1,051 | **1,141** |
> | **commit precision** | **1.0** | **1.0** |
> | silver 커버리지 | 0.8937 | **0.9702** |
> | commit ledger (silver 위 / 밖) | 1,051 / 469 | 1,141 / 482 |
> | tail coverage | 0.9273 | 0.9273 |
> | **fake-glossary RESOLVED FP** | **0** | **0** |
> | candidate mentions /1k chars | 5.459 | 5.459 |
>
> **후보를 하나도 더 만들지 않고** silver span 위 확정이 90건 늘었다. 이미
> 찾아 놓고 threshold 아래에 머물던 것들이며, precision은 1.0 그대로다.
>
> **M3 (tail taxonomy / punctuation class / abbreviation signature)** —
> 20,000문장, 두 체크아웃에서 `run_wild_regression --single`:
>
> | 지표 | M2 | M3 |
> |---|---:|---:|
> | silver mentions / 탐지 / gold-in-set | 1,176 / 1.0 / 1.0 | 1,176 / 1.0 / 1.0 |
> | RESOLVED commits | 1,047 | **1,051** |
> | commit precision | 1.0 | 1.0 |
> | commit ledger (silver 위 / 밖) | 1,047 / 468 | 1,051 / 469 |
> | **tail coverage** | 0.8634 | **0.9273** |
> | **fake-glossary RESOLVED FP** | **0** | **0** |
> | candidate mentions /1k chars | 5.044 | **5.459** |
>
> 카탈로그가 넓어져 후보가 8% 늘었고, 그 대가로 tail coverage가 +6.4%p,
> 확정이 4건 늘었다. 재현율과 구조적 오탐은 움직이지 않았다. (전체 코퍼스
> 114,605문장 기준 tail coverage는 `docs/VARIANTS_PLAN.md` M3 절의
> 0.8538 → 0.9112이며, 표본 크기가 달라 절대값이 다르다. 지연은 두 arm 모두
> CPU를 나눠 쓴 상태에서 재어 생략했다.)
>
> **M2 (typed tail / core_link·full_surface)** — 10,000문장, 두 체크아웃에서
> `run_wild`의 같은 스위트:
>
> | 지표 | M1 | M2 |
> |---|---:|---:|
> | silver mentions / 탐지 / gold-in-set | 609 / 1.0 / 1.0 | 609 / 1.0 / 1.0 |
> | RESOLVED commits | 538 | **540** |
> | commit precision | 1.0 | 1.0 |
> | commit ledger (silver 위 / 밖) | 538 / 204 | 540 / **204** |
> | tail coverage | 0.8400 | **0.8514** |
> | **fake-glossary RESOLVED FP** | **0** | **0** |
> | 지연 p50 / p95 (ms) | 34.57 / 260.8 | 34.94 / 259.6 |
> | candidate mentions /1k chars | 5.114 | 5.114 |
>
> 확정이 2건 늘었고 **그 2건이 전부 silver span 위에 떨어졌다**(silver 밖
> 확정은 204로 동일). 후보 밀도와 지연은 움직이지 않았다 — M2는 측정
> 가능한 비용이 없다.
>
> **M1 (공유 segmentation)** — 20,000문장, 한 프로세스에서 두 동작
> (`python -m eval.run_wild_regression`, `max_segmentation_paths` 1 vs 4).
> 품질 지표는 **전부 동일**했다:
>
> | 지표 | 변경 전 | 변경 후 |
> |---|---:|---:|
> | silver mentions | 1176 | 1176 |
> | core 탐지 / gold-in-set | 1.0 / 1.0 | 1.0 / 1.0 |
> | RESOLVED commits | 1045 | 1045 |
> | commit precision | 1.0 | 1.0 |
> | commit ledger (전체 / silver 위 / 밖) | 1513 / 1045 / 468 | 1513 / 1045 / 468 |
> | tail coverage | 0.8576 | 0.8576 |
> | **fake-glossary RESOLVED FP** | **0** | **0** |
> | 지연 p50 / p95 (ms) | 31.67 / 174.86 | 33.00 / 226.39 |
> | candidate mentions /1k chars | 2.943 | 5.044 |
>
> 후보 밀도는 1.7배로 늘었는데 commit은 **한 건도 늘지 않았다** — ledger의
> off-span commit이 468로 동일하다. 늘어난 후보가 확정까지 가지 않았다는
> 뜻이며, 이것이 `ResolutionGuard`가 실제로 하는 일이다.
>
> 참고: §3의 fake-glossary 필터에 결함이 있었다. 표면형 부재를 **대소문자
> 구분 부분문자열**로 검사했는데 matcher는 case-fold하므로, corpus에 `GB`만
> 있어도 `gb`가 "부재"로 남아 matcher가 맞춘다. 아래 표의 `FP 0`은 그 결함이
> 있는 필터로 얻은 값이다. 필터는 정규화 공간에서 검사하도록 고쳤고
> (`eval/synthetic.py::absent_bindings_only`), **고친 필터로도 20,000문장에서
> FP 0**임을 위 표에서 재확인했다.


## 1. Silver recall — 실존 조직 표면형 (E2E, commit mode)

무모호 표면형(정부기관 전체명·3자 이상 약칭)의 뉴스 내 출현은 사실상 확실한 mention이다(silver label). 좌측 문자 결합·상위 alias 내포 출현은 분모에서 제외한다.

- silver mentions: **6916**
- core 탐지 (E2E): **1.0** (6916/6916)
- gold-in-prediction-set (E2E): **1.0** (6916/6916, CI95 [0.9994, 1.0])
- RESOLVED precision (|commit): **1.0** (6126 commits, silver 대비 coverage 0.8858)
- 짧은/다의 표면형(한전·한은·KT 등) 탐지 mention: 3118건 (recall 분모 제외)
- latency p50/p95: 20.67 / 110.38 ms

## 2. 조사·어미 실분포 커버리지 (§5.2)

silver mention 직후의 한글 run 1969건 중 카탈로그(조사 연쇄·기관 suffix)로 완전히 설명되는 비율: **0.8431** (CI95 [0.8263, 0.8585])

카탈로그 미포함 상위 tail (확장 우선순위 신호, §3.5):

- `법` × 21
- `노조` × 16
- `서` × 14
- `기` × 9
- `교향악단` × 6
- `이사회` × 6
- `써비스` × 6
- `판결은` × 5
- `헬스케어` × 4
- `케미칼` × 4
- `교도통신` × 4
- `민일보` × 4
- `구범위에` × 4
- `투자` × 3
- `콘텐츠허브` × 3

## 3. Fake-glossary 오탐 (구조적 FP 측정)

corpus에 존재하지 않는 표면형만 남긴 합성 glossary(500 bindings)로 실 텍스트를 처리 — 모든 RESOLVED commit은 정의상 오탐이다.

- candidate mentions /1k chars: 4.388 (fuzzy/keyboard 채널의 실 텍스트 자극 밀도)
- **RESOLVED FP: 0건** (0.0 /1k chars, 4896272 chars)

## 3.5 V2 dense 구성 비교 (실 텍스트)

| 구성 | silver gold-in-set | RESOLVED precision | fake-glossary RESOLVED FP |
|---|---:|---:|---:|
| symbolic (기본) | 1.0 | 1.0 | 0 |
| hash_dense | 1.0 | 1.0 | 0 |
| e5_dense | 1.0 | 1.0 | 0 |

dense 채널은 recall 신호만 추가해야 하며(silver 비열화), 가짜 glossary에서 RESOLVED commit을 만들면 안 된다(0 유지).

## 4. 해석과 한계

- silver label은 수동 검증이 아닌 규칙 기반 근사다. 미포함(짧은 약칭, 좌측 결합형)은 보수적으로 제외했으므로 recall 분모가 실제보다 좁다.
- KLUE 헤드라인은 문어체 뉴스 도메인이다. 사내 문서·구어체 분포는 tenant golden set(§48.6)으로만 검증할 수 있다.
- tail 커버리지의 미포함 항목은 §16 카탈로그 확장의 실측 우선순위 신호로 사용한다 (OQ-001).

*generated by `python -m eval.run_wild`*
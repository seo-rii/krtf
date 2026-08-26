# KTRF Downstream A/B — LLM 답변 개선 효과

동일 seeded 450사례 (paired), context budget 800 tokens (B/C/D 동일 — 선택 방식만 다름). 과제: 문장 속 약칭이 가리키는 대상의 정식 명칭 답하기 (Track 1). gold label은 silver/UE 규칙 기반 근사다. 재현: `python -m eval.run_ab_grounding --model <name>`.

**전체 평균을 인용하지 말 것.** 효과가 슬라이스별로 정반대이므로 평균은 세 슬라이스의 구성비를 반영할 뿐이다. 슬라이스별로 읽는다:

- `private_glossary` — 사전학습에 존재할 수 없는 사내 용어. **제품이 실제로 노리는 경우**이며, 여기서만 KTRF가 대체 불가능한 정보를 제공한다.
- `known_abbrev` — 모델이 이미 아는 공개 기관 약칭이 glossary에도 등록된 경우. context는 잘해야 본전이다.
- `unseen_abbrev` — 공개 기관이지만 binding을 숨겨 KTRF가 *후보만* 제시할 수 있는 경우. 지시를 잘 따르는 모델은 후보 목록 앞에서 기권하므로 오히려 손해가 날 수 있다.

## 슬라이스별 요약 (A → C)

| 모델 | 슬라이스 | A. LLM only | B. retrieval | C. KTRF | D. gold | helpful | harmful | GBR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| qwen3:8b | `known_abbrev` | 0.6133 | 1.0 | **0.94** | 1.0 | +55 | −6 | 0.8448 |
| qwen3:8b | `private_glossary` | 0.0 | 1.0 | **1.0** | 1.0 | +150 | −0 | 1.0 |
| qwen3:8b | `unseen_abbrev` | 0.7867 | 0.8267 | **0.9467** | 1.0 | +29 | −5 | 0.7501 |
| gemma4:12b | `known_abbrev` | 0.8867 | 0.9933 | **0.8** | 1.0 | +14 | −27 | -0.7652 |
| gemma4:12b | `private_glossary` | 0.0 | 1.0 | **0.92** | 1.0 | +138 | −0 | 0.92 |
| gemma4:12b | `unseen_abbrev` | 0.8467 | 0.6067 | **0.34** | 1.0 | +0 | −76 | -3.3053 |

## qwen3:8b

### 전체

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.4667 (210/450) | [0.421, 0.5128] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 0.9422 (424/450) | [0.9167, 0.9603] | 229 | 15 | 0.0 | 297.7 | 1.0 |
| C. KTRF context pack | 0.9622 (433/450) | [0.9403, 0.9763] | 234 | 11 | 0.0 | 174.4 | 0.951 |
| D. gold context (oracle) | 1.0 (450/450) | [0.9915, 1.0] | 240 | 0 | 0.0 | 118.8 | 1.0 |

**Gold Benefit Recovery: 0.9291** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

### known_abbrev

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.6133 (92/150) | [0.5335, 0.6875] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 1.0 (150/150) | [0.975, 1.0] | 58 | 0 | 0.0 | 320.4 | 1.0 |
| C. KTRF context pack | 0.94 (141/150) | [0.8899, 0.9681] | 55 | 6 | 0.0 | 167.2 | 1.0 |
| D. gold context (oracle) | 1.0 (150/150) | [0.975, 1.0] | 58 | 0 | 0.0 | 113.6 | 1.0 |

**Gold Benefit Recovery: 0.8448** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

### private_glossary

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.0 (0/150) | [0.0, 0.025] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 1.0 (150/150) | [0.975, 1.0] | 150 | 0 | 0.0 | 240.0 | 1.0 |
| C. KTRF context pack | 1.0 (150/150) | [0.975, 1.0] | 150 | 0 | 0.0 | 142.8 | 1.0 |
| D. gold context (oracle) | 1.0 (150/150) | [0.975, 1.0] | 150 | 0 | 0.0 | 122.5 | 1.0 |

**Gold Benefit Recovery: 1.0** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

### unseen_abbrev

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.7867 (118/150) | [0.7144, 0.8446] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 0.8267 (124/150) | [0.7581, 0.8789] | 21 | 15 | 0.405 | 332.8 | 1.0 |
| C. KTRF context pack | 0.9467 (142/150) | [0.8983, 0.9727] | 29 | 5 | 0.0 | 213.2 | 0.853 |
| D. gold context (oracle) | 1.0 (150/150) | [0.975, 1.0] | 32 | 0 | 0.0 | 120.2 | 1.0 |

**Gold Benefit Recovery: 0.7501** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

## gemma4:12b

### 전체

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.5778 (260/450) | [0.5317, 0.6226] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 0.8667 (390/450) | [0.8321, 0.895] | 184 | 54 | 0.0 | 297.7 | 1.0 |
| C. KTRF context pack | 0.6867 (309/450) | [0.6424, 0.7278] | 152 | 103 | 0.0026 | 174.4 | 0.951 |
| D. gold context (oracle) | 1.0 (450/450) | [0.9915, 1.0] | 190 | 0 | 0.0 | 118.8 | 1.0 |

**Gold Benefit Recovery: 0.2579** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

### known_abbrev

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.8867 (133/150) | [0.826, 0.928] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 0.9933 (149/150) | [0.9632, 0.9988] | 17 | 1 | 0.0001 | 320.4 | 1.0 |
| C. KTRF context pack | 0.8 (120/150) | [0.7289, 0.8562] | 14 | 27 | 0.0596 | 167.2 | 1.0 |
| D. gold context (oracle) | 1.0 (150/150) | [0.975, 1.0] | 17 | 0 | 0.0 | 113.6 | 1.0 |

**Gold Benefit Recovery: -0.7652** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

### private_glossary

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.0 (0/150) | [0.0, 0.025] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 1.0 (150/150) | [0.975, 1.0] | 150 | 0 | 0.0 | 240.0 | 1.0 |
| C. KTRF context pack | 0.92 (138/150) | [0.8654, 0.9536] | 138 | 0 | 0.0 | 142.8 | 1.0 |
| D. gold context (oracle) | 1.0 (150/150) | [0.975, 1.0] | 150 | 0 | 0.0 | 122.5 | 1.0 |

**Gold Benefit Recovery: 0.92** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

### unseen_abbrev

| 조건 | accuracy | CI95 | helpful | harmful | McNemar p | ctx tokens | 주입률 |
|---|---:|---|---:|---:|---:|---:|---:|
| A. LLM only | 0.8467 (127/150) | [0.7804, 0.8956] | — | — | — | 0.0 | 0.0 |
| B. retrieval glossary (RAG) | 0.6067 (91/150) | [0.5268, 0.6812] | 17 | 53 | 0.0 | 332.8 | 1.0 |
| C. KTRF context pack | 0.34 (51/150) | [0.269, 0.419] | 0 | 76 | 0.0 | 213.2 | 0.853 |
| D. gold context (oracle) | 1.0 (150/150) | [0.975, 1.0] | 23 | 0 | 0.0 | 120.2 | 1.0 |

**Gold Benefit Recovery: -3.3053** — KTRF context가 이상적 context 효과의 몇 %를 회수하는가 ((C−A)/(D−A); D−A가 미미하면 N/A).

## 해석과 한계

- paired 설계: 같은 사례에 네 조건을 적용해 flip을 직접 센다. Harmful flip(원래 맞던 답을 context가 망친 사례)은 도입 결정의 핵심 지표다.
- **채점은 strict**다: 허용 정답(정식 명칭 또는 등록된 non-약칭 alias)이 모델 출력에 포함돼야 한다. 역방향 포함(`현대`→현대자동차)은 인정하지 않는다.
- **조건 B는 검색 기반**(dense top-k ∪ 문장 내 alias literal hit)이며 C와 동일 token budget을 쓴다 — 검색 기회는 같고 선별·구조만 다르다.
- **주입률**은 C가 실제로 context를 넣은 비율이다. pack이 질문 대상을 grounding하지 못하면 주입하지 않는 계약(`should_inject`) 때문에 1.0보다 작을 수 있으며, 그 사례에서 C는 A와 동일한 프롬프트를 쓴다.
- McNemar p는 **보조 지표**다. 사례가 alias family 단위로 군집되어 있는데 이 검정은 그걸 모델링하지 않으므로, 작은 p 하나로 효과를 주장하지 않는다 (cluster bootstrap은 ROADMAP 백로그).
- **후보 제시의 억제 비용**: KTRF가 확정하지 못하고 후보만 제시하면, 고정 정책의 '근거가 충분하지 않으면 임의로 확정하지 않는다'를 충실히 따르는 모델은 기권(`canonical: null`)한다. 실측에서 gemma4:12b harmful flip 109건 중 106건이 기권이었고, 같은 사례를 무맥락에서는 전부 맞혔다. 이 억제는 프롬프트 문구로 교정되지 않았고 (허용 문구 추가 시 1/14), 무관한 모호성 제거로 절반만 회복됐다. 단일 정답이 필요한 과제라면 host가 `PreparedContext.resolves_query`(확정 사실이 있을 때만 주입)를 쓰는 편이 안전하다 — 다만 지시를 덜 따르는 모델에서는 후보 제시가 이득이므로(qwen3 unseen 0.787→0.947) 라이브러리 기본값으로 강제하지 않는다.
- **B(검색 덤프)가 known에서 C보다 높은 것**은 B가 이 안전 계약을 지고 있지 않기 때문이다. 구조화·확정 분리·기권 유도를 뺀 평평한 사전 덤프는 벤치마크 점수에는 유리하고, 잘못된 확정을 막는 계약은 없다.
- gold label은 규칙 기반 근사이며 사람 주석이 아니다. 표본 확대와 human-gold 구축은 ROADMAP 백로그 참조.

## Provenance

- git commit: `ef4b2217d20f7e1b89beef81796e96a0a02e4978`
- corpus: 114605문장, sha256 `a9328475107ba227e1a16c4736a5acff`
- glossary: 235 bindings, sha256 `ed39351aecbc1b3ad26a94753b9a71f3`
- prompt sha256 `32732d36d06c4e9c`, policy sha256 `025c3bfa7b786ae4`, seed 11

*generated by `python -m eval.run_ab_grounding`*
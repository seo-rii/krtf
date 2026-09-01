# 배포 — 휠은 코드를, 스냅샷은 약속을 나른다

KTRF를 `pip install` 가능한 물건으로 만드는 방법과, **모델 가중치를 왜
패키지에 넣지 않는지**를 적는다. 두 번째가 이 문서의 실제 주제다.

## 빌드

```bash
# Linux / macOS
./scripts/build_wheel.sh

# Windows
.\scripts\build_wheel.ps1
```

두 래퍼는 인터프리터를 고르고 UTF-8을 강제한 뒤 `scripts/build_wheel.py`에
넘긴다. **실제 로직은 파이썬 쪽에만 있다** — 셸 방언 두 벌로 나눠 두면
반드시 한쪽만 고쳐지고 서로 갈라진다.

래퍼는 후보를 **순서대로 실행해 보고 3.11 이상인 첫 번째를 고른다.** 이름을
믿지 않는 이유가 있다 — Windows의 Git Bash에서 `python3`은 Microsoft Store
스텁으로 잡히고, 이건 인터프리터가 아니면서 호출에는 응답한다. 처음에는
`python3`을 무조건 우선했다가 이 환경에서 바로 걸렸다.

UTF-8 강제도 장식이 아니다. 이 저장소의 소스와 픽스처는 한국어투성이고,
Windows에서 자식 파이썬은 `PYTHONUTF8`이 없으면 여전히 ANSI 코드 페이지로
떨어진다.

산출물은 `dist/`에 떨어진다:

```
ktrf-0.1.0-py3-none-any.whl   137 KiB
ktrf-0.1.0.tar.gz             222 KiB
```

`py3-none-any` — C 확장이 없으므로 플랫폼별 휠이 필요 없다. 형태론 테이블
(`SUFFIX_CLASSES`, `TAIL_CLASSES`, `_RESIDUAL_BASE`)도 `.py` 안의 리터럴이라
동봉할 데이터 파일 자체가 없다. 이건 운이 아니라 **규칙을 코드로 둔 설계의
배당금**이다.

### 빌드보다 검증이 중요하다

`build_wheel.py`는 빌드 후 **일회용 venv에 설치해서 실제로 돌려 본다.**
그리고 그 스모크 테스트를 **저장소 밖 디렉터리에서** 실행한다.

이게 핵심이다. 저장소 루트에서 `import ktrf`를 하면 소스 트리가 잡히고
휠은 손도 안 닿는다. **모듈이 하나도 안 들어간 휠조차 통과한다.** 패키징
사고의 대부분이 이 한 줄에서 나온다.

검사하는 것:

| 검사 | 잡아내는 사고 |
|---|---|
| `site-packages`에서 import됐는지 | 소스 트리를 재 놓고 통과하는 가짜 성공 |
| 36개 모듈 전부 import | setuptools가 조용히 빠뜨린 서브패키지 |
| `py.typed` 실재 확인 | 선언만 있고 파일은 안 실린 경우 |
| 한국어 문장 end-to-end resolve | 남의 기계에서의 인코딩 사고 |
| `ktrf-pi` 콘솔 스크립트 실행 | 진입점이 못 걸리는 경우 |
| 휠 8 MiB 초과 시 실패 | **모델·코퍼스가 딸려 들어간 경우** |

`tests/test_packaging.py`가 같은 계약을 빌드 없이 8개 테스트로 지킨다 —
`__init__.py` 없는 서브패키지, `eval/`을 import하는 런타임 코드, 선언 안 된
데이터 파일, 무거워진 기본 의존성, 이중화된 버전 리터럴, 분해된 자모.

## 무엇이 실리지 않는가

sdist는 **재빌드에 필요한 소스**이지 작업 트리가 아니다. `MANIFEST.in`은
`prune`도 `exclude`도 없는 **순수 allowlist**다 — 명시하지 않은 것은 애초에
안 실린다. 그래서 실리면 안 되는 것들은 **침묵으로 이미 제외**되어 있다:

- **`models/` (1.5G)** — 아래 참조
- **`eval/data/`** — 라이선스 있는 서드파티 다운로드. `eval/wild_data.py`가
  *다운로더를 배포하고 텍스트는 배포하지 않는다*. 손으로 라벨링한
  `variant_gold.jsonl` 160행만 예외로 명시한다 — 이건 받을 수 있는 게 아니라
  **사람이 읽은 결과**다.
- **`reports/`, `eval/out/`** — 측정 결과는 소스가 아니다
- **`out.bundle`, `REVIEW*.md`** — 작업 중 부산물

**침묵은 증거가 아니다.** 그래서 `prune` 줄을 믿는 대신 검사한다 —
`build_wheel.py`가 sdist를 열어 `models/`·`reports/`·`.onnx`·`.safetensors`가
한 건이라도 있으면 빌드를 실패시키고, 크기가 몇 MB를 넘어도 실패시킨다.
`prune`은 경고만 뱉고 아무것도 보장하지 않지만 이건 보장한다.

휠은 더 좁다: `ktrf/`와 `py.typed`뿐. `eval/`·`tests/`·`training/` 없음.

sdist가 **바이트 동일한 휠을 다시 만들어 내는지**도 확인했다 — 43개 항목,
저장소에서 빌드한 것과 파일 집합이 정확히 일치한다. MANIFEST에서 필요한
파일을 빠뜨리지 않았다는 가장 강한 증거다.

## 모델 가중치는 넣지 않는다

**넣고 싶은 유혹이 자연스럽다** — 그래야 `pip install`만으로 dense 채널이
돈다. 그런데 세 가지가 동시에 막는다.

| 근거 | 실측 |
|---|---|
| `models/`가 `.gitignore`에 통째로 등록 | 추적 파일 **0개** |
| 전체 크기 | **1.5G** (e5-small 130M / fp32 465M / xenc 423M) |
| PyPI 파일당 한도 | 100 MB — **가장 작은 것도 초과** |

크기만의 문제가 아니다. **계층이 뒤집힌다.** dense는 `_CHANNEL_BASE`에서
0.55, 설계상 가장 못 믿는 채널이다. 가중치를 휠에 구우면 Level A만 쓸
소비자까지 수백 MB를 지불한다. `run_neural_eval`이 인코더 **3개 구성**을
돌린다는 사실이 이미 답을 말한다 — 모델은 고정값이 아니라 *선택지*고,
선택지는 패키지에 굽는 게 아니다.

그래서 extras로 갈라 놓았고, **기본 설치의 의존성은 PyYAML 하나다:**

```bash
pip install ktrf              # Level A + fuzzy + abbrev. 무거운 의존성 0
pip install ktrf[neural]      # ONNX 백엔드. 가중치는 별도
pip install ktrf[gpu]         # CUDA 추론
pip install ktrf[training]    # cross-encoder 파인튜닝
```

### 재현성은 바이트가 아니라 신원으로 고정한다

여기서 당연한 반론이 나온다 — 가중치가 떠다니면 dense 수치의 재현성은
어떻게 되나?

**이미 해결되어 있다.** `OnnxE5Encoder.encoder_id`는 ONNX 파일 전체 +
`tokenizer.json` + `config.json`의 sha256이고, 이게 스냅샷 manifest의
`entity_encoder_hash`로 들어간다. 불일치하는 번들을 로드하면 조용히
넘어가지 않고 **거부한다**:

```
KtrfApiError | SNAPSHOT_UNAVAILABLE: encoder mismatch:
    bundle=hash-jamo-ngram-v1-d256 given=hash-jamo-ngram-v1-d512 (INV-015)
```

가중치가 content-addressed 되어 있으므로, 이건 **가중치를 동봉했을 때 얻는
재현성과 동일한 보장**을 크기 없이 준다. 올바른 계층은 이렇다:

> **휠은 코드를 배포하고, 스냅샷 번들은 약속을 배포한다.**
> 가중치는 스냅샷 컴파일의 *입력*이지 패키지의 내용물이 아니다.

### 아직 비어 있는 자리: 받을 방법

`neural` extra는 **`huggingface_hub`를 선언해 놓고 코드베이스 어디서도
import하지 않는다.** 의도했던 페처가 안 써진 채 의존성만 남아 있다.

그래서 지금 README는 "`Xenova/multilingual-e5-small`을 `models/`에
받으라"고만 하고 **명령을 주지 않는다.** `load_encoder("onnx:<dir>")`는
사용자가 디렉터리를 손으로 조립했다고 가정한다. `pip install ktrf[neural]`
한 사람은 여기서 멈춘다.

선례는 같은 저장소 안에 있다 — `eval/wild_data.py`가 코퍼스에 대해 정확히
이 문제를 이미 풀었다. 모델도 같은 규칙을 따르면 된다: **다운로더를
배포하고 가중치는 배포하지 않는다.** `huggingface_hub`가 이미 선언되어
있으니 새 의존성도 필요 없고, 오히려 지금의 죽은 의존성이 살아난다.

권하는 모양: `ktrf.encoders.fetch_encoder(repo_id, dest)` — `snapshot_download`로
받고, 받은 디렉터리로 `OnnxE5Encoder`를 열어 `encoder_id`를 찍어 준다.
그러면 사용자가 **자기 스냅샷에 무엇이 고정됐는지 즉시 본다.**

## 남은 항목

- **LICENSE 파일이 없다.** 그래서 `pyproject.toml`에 `license` 필드를 넣지
  않았다 — 아무도 고르지 않은 조건을 메타데이터가 주장하면 안 된다. 조건이
  정해지면 파일과 필드를 **같이** 추가한다. 그 전까지 공개 배포는 불가.
- 위의 `fetch_encoder`.
- 저장소 URL이 없어 `[project.urls]`도 비어 있다.

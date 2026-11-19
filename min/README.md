# KTRF 단일 파일 간편판

한국어 문장에서 사전에 등록한 기관명·약칭을 찾아 원문 위치와 용어 ID를 반환한다. Python 3.11 이상에서 [krtf.py](krtf.py)와 용어집을 같은 폴더에 두면 바로 사용할 수 있다. JSON·CSV·TSV와 컴파일한 스냅샷은 표준 라이브러리만 사용한다.

## 첫 조회

다음 내용을 `terms.json`으로 저장한다. `canonical`은 대표 이름, `surfaces`는 같은 대상을 가리키는 표기다. 예제의 AP는 네트워크 부서에서 2025년부터 쓰는 약칭이다.

```json
{
  "terms": [
    {"key": "kepco", "canonical": "한국전력공사", "surfaces": ["한전"]},
    {"key": "radio", "canonical": "Access Point", "surfaces": ["AP"],
     "scope": {"allow": {"departments": ["network"]}}, "valid_from": "2025-01-01"}
  ]
}
```

```bash
python krtf.py terms.json "한전에서 발표했다."
python krtf.py resolve terms.json "Ａｐ를 점검했다." --department network --as-of 2026-10-01
python krtf.py terms.json < document.txt
```

첫 명령은 `한전`을 `project:kepco`로 연결한다. JSON 응답의 `mentions`에서 `span`은 용어 자체, `full_span`은 조사를 포함한 `한전에서`를 가리킨다. 두 범위 모두 시작은 포함하고 끝은 제외하며, 원문의 코드포인트·UTF-8 바이트·UTF-16 코드 단위 위치를 제공한다. 두 번째 명령은 전각 영문과 대소문자를 정규화해 `Ａｐ`를 `project:radio`로 연결한다.

| 원문에서 일어나는 일 | 결과를 읽는 법 |
|---|---|
| `한전에서도`처럼 조사가 이어진다 | 받침과 조사 순서를 검사한다. 등록 표기가 겹치면 같은 시작 위치에서 조건에 맞는 가장 긴 표기를 고른다. |
| `한전노조`처럼 접미 표현이 대상을 바꾼다 | `core_link`는 내부 용어, `full_surface`는 전체 표현이다. 사전에 `COMPOSES_TO`가 등록되고 대상의 적용 조건까지 충족되면 `full_surface.composes_to`에서 파생 대상 ID를 읽을 수 있다. |
| `한국전력공사(전력사)` 다음에 `전력사`가 다시 나온다 | 문서 안에 선언된 별칭을 그 문서에서 사용한다. 기존 사전의 경쟁 후보와 적용 조건도 함께 검사한다. |
| 두벌식으로 잘못 입력한 `gkswjs`처럼 복원이 필요하다 | 자모 한 번의 편집, 두벌식 오입력, 약칭 추론은 후보를 제시한다. `--no-recovery`로 이 추론을 끌 수 있다. |

`RESOLVED`는 간편판의 규칙으로 하나의 ID를 골랐다는 뜻이다. 같은 표기가 여러 대상을 가리키거나 적용 조건이 불명확하면 `AMBIGUOUS`와 `prediction_set.members`를 반환한다. 부서·프로젝트·기준일은 호출자가 제공하는 문맥이다. 업무상 검토가 필요한 연결은 원문과 함께 확인한다. LLM 질의응답용 문맥 생성과 실행 권한 검증은 [전체 KTRF](../README.md)를 참고한다.

## 원본 형식과 오프라인 스냅샷

간편 용어집(v1)의 `terms`와 전체 용어집(v3)의 `alias_bindings`를 읽는다. YAML 원본을 읽을 때만 `python -m pip install PyYAML`이 필요하다. 표 형식에서는 UTF-8 CSV·TSV의 필수 헤더가 `id`, `canonical`이고, 선택 헤더가 `alias`, `definition`이다. 별칭 하나당 한 행을 쓰며 같은 ID의 대표 이름과 정의는 일관되게 적는다. UTF-8 BOM과 따옴표로 감싼 필드를 지원한다. 다음은 `project.csv` 예제다.

```csv
id,canonical,alias,definition
APPROVAL,승인 절차,AP,"구매, 결재에 쓰는 절차"
APPROVAL,승인 절차,결재흐름,"구매, 결재에 쓰는 절차"
```

```bash
python krtf.py compile terms.json terms.krtf
python krtf.py load terms.krtf "한전에서 발표했다."
python krtf.py load terms.krtf < document.txt
```

다른 컴퓨터에서는 `krtf.py`와 `terms.krtf` 두 파일만으로 조회할 수 있다. YAML에서 컴파일했어도 원본과 PyYAML은 조회에 필요하지 않다. 간편판 전용 v2 스냅샷은 검색 트라이와 적용 조건을 저장하고 로드할 때 체크섬을 확인한다. v1 스냅샷도 읽을 수 있다. v1에 기록되지 않은 조건이나 갱신된 원본을 반영하려면 다시 컴파일한다.

용어집을 겹쳐 쓸 때는 `--layer 범위=파일`을 추가한다. 이때 첫 파일은 `base`이고 우선순위는 `base < global < project < session < document`이다. 정규화한 표기가 겹치면 좁은 범위가 그 표기를 맡는다. 좁은 범위의 조건이 맞지 않아도 넓은 범위의 뜻으로 되돌아가지 않는다.

```bash
python krtf.py compile terms.json team.krtf --layer project=project.csv
python krtf.py info team.krtf
python krtf.py load team.krtf "AP를 확인했다."
```

이 예제에서는 프로젝트 용어집의 `APPROVAL`이 선택된다. `info`의 `conflicts`에서 어떤 ID가 대체되었는지 확인할 수 있다.

## 점검과 일괄 처리

| 명령 | 확인할 내용 |
|---|---|
| `python krtf.py lint terms.json` | 원본 필드, 참조, 유효기간과 공유 별칭을 점검한다. 오류는 종료 코드 1이며 경고만 있으면 0이다. |
| `python krtf.py lookup terms.krtf AP` | 등록 표기의 후보 ID, 대표 이름, 정의, 무조건 적용 가능한 연결인지 확인한다. |
| `python krtf.py explain terms.krtf "AP를 확인했다."` | 문장에서 일치한 표기, 탐지 경로, 후보와 연결·보류 사유를 확인한다. |
| `python krtf.py info team.krtf` | 용어와 별칭 수, 모호하거나 제한된 연결 수, 레이어 충돌을 확인한다. |
| `python krtf.py diff terms.krtf team.krtf` | 두 용어집이나 스냅샷에서 추가·삭제·변경된 ID와 표기를 확인한다. |

`resolve`, `load`, `explain`, `batch`는 `--department`, `--project`, `--as-of YYYY-MM-DD`, `--no-recovery`를 받는다. `batch`는 UTF-8 JSONL을 한 줄씩 읽는다. `documents.jsonl`의 각 행에 문자열 또는 정수 `id`와 문자열 `text`를 넣는다.

```jsonl
{"id":"notice-1","text":"한전에서 발표했다."}
{"id":"ticket-2","text":"AP를 점검했다."}
```

```bash
python krtf.py batch terms.krtf documents.jsonl --department network --as-of 2026-10-01
python krtf.py batch terms.krtf < documents.jsonl
```

정상 행은 문서 ID와 조회 결과를, 잘못된 행은 줄 번호와 오류를 출력한다. 오류 뒤의 행도 계속 처리하고, 한 행이라도 실패하면 종료 코드 1을 반환한다.

## Python에서 사용하기

`krtf.py`와 같은 폴더의 스크립트에서 스냅샷을 한 번 만든 후 여러 문장에 재사용할 수 있다.

```python
from krtf import compile_snapshot, load_glossary, load_snapshot, resolve, save_snapshot

snapshot = compile_snapshot(load_glossary("terms.json"))
save_snapshot(snapshot, "terms.krtf")

saved = load_snapshot("terms.krtf")
mention = resolve(saved, "한전에서 발표했다.")["mentions"][0]
print(mention["surface"], mention["resolved_entity"]["entity_id"])
# 한전 project:kepco
```

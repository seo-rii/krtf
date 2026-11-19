# KTRF 단일 파일 간편판

한국어 문장에서 용어집에 등록한 이름과 약칭을 찾아 ID에 연결한다. Python 3.11 이상에서 [krtf.py](krtf.py)와 JSON 용어집만 있으면 실행할 수 있다.

## 명령줄에서 실행하기

`krtf.py`와 같은 폴더에 아래 내용을 `terms.json`으로 저장한다.

```json
{
  "terms": [
    {"key": "kepco", "canonical": "한국전력공사", "surfaces": ["한전"]}
  ]
}
```

그 폴더에서 문장을 인자로 전달하거나 UTF-8 문서를 표준 입력으로 읽는다.

```bash
python krtf.py terms.json "한전에서 발표했다."
python krtf.py terms.json < document.txt
```

첫 명령은 JSON의 `mentions`에 `한전`을 `RESOLVED`로 반환한다. 연결된 ID는 `project:kepco`다. `span`은 원문의 `한전`을, `full_span`은 조사를 포함한 `한전에서`를 가리킨다. 두 범위 모두 시작 위치를 포함하고 끝 위치를 제외하며, 코드포인트·UTF-8 바이트·UTF-16 코드 단위로 제공한다.

기존 YAML 용어집을 쓰려면 `python -m pip install PyYAML`로 읽기 기능을 설치한다. 간편 용어집(v1)의 `terms`와 전체 용어집(v3)의 `alias_bindings`에 등록된 표기를 지원한다.

## 용어집을 컴파일해 오프라인에서 조회하기

용어집을 준비하는 컴퓨터에서 `compile` 명령으로 검색에 쓸 스냅샷을 만든다.

```bash
python krtf.py compile terms.json terms.krtf
```

조회할 컴퓨터에는 `krtf.py`와 `terms.krtf` 두 파일만 복사한다. YAML 원본으로 컴파일한 경우에도 조회에는 Python 표준 라이브러리만 필요하다. `load`는 스냅샷에서 문장의 용어를 찾아 직접 조회와 같은 JSON 형식으로 출력한다.

```bash
python krtf.py load terms.krtf "한전에서 발표했다."
python krtf.py load terms.krtf < document.txt
```

`.krtf`는 형식 버전이 있는 간편판 전용 스냅샷이다. 원본에서 이름이나 약칭을 수정하면 다시 컴파일해 새 스냅샷을 복사한다.

## Python에서 사용하기

`krtf.py`와 같은 폴더의 Python 스크립트에서는 용어집을 한 번 읽어 여러 문장에 재사용할 수 있다.

```python
from krtf import compile_snapshot, load_glossary, resolve

snapshot = compile_snapshot(load_glossary("terms.json"))
mention = resolve(snapshot, "한전에서 발표했다.")["mentions"][0]
print(mention["surface"], mention["resolved_entity"]["entity_id"])
# 한전 project:kepco
```

Python에서 스냅샷 파일을 만들 때는 `save_snapshot()`을 사용한다.

```python
from krtf import compile_snapshot, load_glossary, save_snapshot

snapshot = compile_snapshot(load_glossary("terms.json"))
save_snapshot(snapshot, "terms.krtf")
```

조회할 때는 파일에서 한 번 읽은 스냅샷을 여러 문장에 재사용할 수 있다.

```python
from krtf import load_snapshot, resolve

snapshot = load_snapshot("terms.krtf")
result = resolve(snapshot, "한전에서 발표했다.")
```

간편판은 대소문자와 띄어쓰기를 구분하고, 흔한 한국어 조사를 인식한다. 같은 위치에서 여러 표기가 일치하면 가장 긴 표기를 선택한다. 같은 약칭을 여러 ID가 공유하거나 적용 범위·유효기간을 확인해야 하면 `AMBIGUOUS`로 표시하고 `prediction_set.members`에 후보를 담는다. 오타 복원, 파생 표현 분석, 문맥을 이용한 후보 판별에는 [전체 KTRF](../README.md)를 사용한다.

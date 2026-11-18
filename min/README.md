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

## Python에서 사용하기

`krtf.py`와 같은 폴더의 Python 스크립트에서는 용어집을 한 번 읽어 여러 문장에 재사용할 수 있다.

```python
from krtf import compile_snapshot, load_glossary, resolve

snapshot = compile_snapshot(load_glossary("terms.json"))
mention = resolve(snapshot, "한전에서 발표했다.")["mentions"][0]
print(mention["surface"], mention["resolved_entity"]["entity_id"])
# 한전 project:kepco
```

간편판은 대소문자와 띄어쓰기를 구분하고, 흔한 한국어 조사를 인식한다. 같은 위치에서 여러 표기가 일치하면 가장 긴 표기를 선택한다. 같은 약칭을 여러 ID가 공유하거나 적용 범위·유효기간을 확인해야 하면 `AMBIGUOUS`로 표시하고 `prediction_set.members`에 후보를 담는다. 오타 복원, 파생 표현 분석, 문맥을 이용한 후보 판별에는 [전체 KTRF](../README.md)를 사용한다.

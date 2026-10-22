# 승인 상한과 보류 원인: CPU 진단

이미 공개된 합성 자료의 봉인된 원시 응답을 재채점한 뒤 정답 ID와 근거를 넣어 검증기 상한을 계산했다.
정답을 아는 oracle 진단이며 모델 성능·새 독립 검증·운영 승인으로 사용하지 않는다.

| 모델 | 정상 사례 | 정답 후보 회수 | 기존 승인 검증 상한 | 네 속성 검사 포함 상한 | 실제 정상 승인 |
|---|---:|---:|---:|---:|---:|
| gemma12b | 32 | 32 | 23 | 7 | 7 |
| qwen27b | 32 | 32 | 23 | 7 | 7 |

모델 `gemma12b`의 정상 사례별 첫 차단 원인:

```json
{
  "approved": 7,
  "production_occurrence_guard_blocked": 9,
  "no_complete_same_paragraph_four_attribute_bundle": 16
}
```

모델 `qwen27b`의 정상 사례별 첫 차단 원인:

```json
{
  "approved": 7,
  "production_occurrence_guard_blocked": 9,
  "no_complete_same_paragraph_four_attribute_bundle": 16
}
```

후속 비교에서는 여러 문장·문단의 근거 결합, 누락 속성과 직접 모순의 분리,
문맥으로 구분되는 모호 후보를 각각 다룬다. 기존 운영 승인과 실험용 shadow 결과는 분리한다.

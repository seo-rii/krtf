# 요청에 결합한 간결한 실행 선택

모델은 긴 문서 hash·snapshot·발생 위치를 다시 쓰는 대신 요청별 `ref`와
`entity_id`를 반환할 수 있다. 서버의 `CompactExecutionRequest`가 원래 정보를
복원하고 기존 `validate_llm_grounding(..., execution_contract="occurrence_v1")`로
검증한다. 이 함수는 실제 업무 동작을 실행하지 않는다.

```python
from ktrf import create_compact_request

# pack은 서버가 현재 문서와 올바른 tenant/scope의 snapshot으로 생성한 automation pack이다.
request = create_compact_request(
    pack,
    document_text=text,
    tenant_id=trusted_tenant_id,
    scope_id=trusted_scope_id,
    request_id=trusted_request_id,
    ttl_seconds=60,
)
# 모델에게 원문, request.catalog, request.response_schema를 전달한다.
# 모델 반환 예: {"selections": [{"ref": "발급된 참조", "entity_id": "등록 ID"}]}
result = request.consume(
    model_output,
    document_text=current_text,
    snapshot_id=current_snapshot.snapshot_id,
    tenant_id=trusted_tenant_id,
    scope_id=trusted_scope_id,
    request_id=trusted_request_id,
)
if result["valid"]:
    verified_selections = [s for s in result["selections"] if s["entity_id"] is not None]
    # 실제 업무 변경 여부와 트랜잭션은 호스트가 결정한다.
```

`catalog`에는 확정되고 손상되지 않은 발생 위치만 포함된다. 모호한 후보는 선택
권한을 얻지 않는다. `target_occurrences=[{"mention_id": ..., "core_span": ...,
"full_span": ...}]`로 특정 발생만 요청할 수 있다. 각 span은 원문 codepoint 기준
`{"start": ..., "end": ...}`이고 요청 대상은 정확히 일치해야 한다.

호스트는 문서·snapshot·tenant·scope·request ID와 pack의 출처를 인증해야 한다.
이 값들을 모델 출력에서 가져오면 안 된다. 현재 문서 본문으로 hash를 다시
검사하고, snapshot이나 요청 범위가 달라지면 거절한다. TTL은 서버의 monotonic
clock으로 검사한다. 참조는 요청마다 새로 생성되며 다른 요청에서 사용할 수 없다.

팩과 매핑은 생성 시 복사해 보존한다. `catalog`와 `response_schema`도 분리된
값이므로 호출자가 수정해도 서버의 검증 자료는 바뀌지 않는다. 소비는 객체별
lock으로 한 번만 허용한다. 잘못된 응답, 문서·범위 불일치, 만료로 실패해도
그 요청은 소비되므로 재시도하려면 새 요청을 만들어야 한다. 빈 선택 또는 null은
기권이며 실행 승인이 아니다.

이 객체의 중복 소비 차단은 동일 프로세스에서 동일 객체를 유지할 때 적용된다.
여러 worker나 서버 재시작을 거치는 서비스는 요청 저장과 소비 상태를 원자적으로
관리하고, 실제 업무 동작에도 별도의 durable idempotency를 적용해야 한다.
이번 구현은 HTTP 서비스 배포나 분산 요청 저장소를 포함하지 않는다.

이전 실험의 간결한 출력은 모델 요청 지연을 줄였지만, 이 API의 운영 규모 부하나
독립적인 의미 정확도를 보장하지 않는다. 사용 예의 TTL도 실제 모델 지연·서비스
정책에 맞춰 호스트가 정해야 한다.

"""Compact transport preserves strict occurrence authority and request isolation."""

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Barrier

import pytest

from ktrf import CompactExecutionRequest, create_compact_request
from ktrf.context import ContextPolicy, prepare_llm_context, validate_llm_grounding
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.registry import compile_simple_terms
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def snapshot():
    terms = {"terms": [
        {"key": "fss", "canonical": "금융감독원", "surfaces": ["금감원"],
         "short_definition": "금융기관을 감독하는 기관"},
        {"key": "billing", "canonical": "청구 관리팀", "surfaces": ["공통"],
         "short_definition": "월별 청구 오류를 검토하는 조직"},
        {"key": "entry", "canonical": "방문 승인팀", "surfaces": ["공통"],
         "short_definition": "방문자의 출입을 승인하는 조직"}]}
    return compile_snapshot(load_glossary(compile_simple_terms(
        terms, scope="global", glossary_id="compact")), run_conformance=False)


def prepare(snapshot, text="금감원 발표", **kwargs):
    pack = prepare_llm_context(snapshot, text, context_policy=ContextPolicy(
        profile="automation", max_tokens=10000)).context_pack
    request = create_compact_request(
        pack, document_text=text, tenant_id="tenant-a", scope_id="project-a",
        request_id="request-a", **kwargs)
    return request, pack, text


def output(request, index=0, **changes):
    choice = request.catalog[index]
    return {"selections": [{"ref": choice["ref"],
                            "entity_id": choice["entity_id"], **changes}]}


def consume(request, response, text="금감원 발표", **changes):
    current = dict(document_text=text, snapshot_id=request.snapshot_id,
                   tenant_id="tenant-a", scope_id="project-a", request_id="request-a")
    return request.consume(response, **{**current, **changes})


def test_real_resolver_roundtrip_matches_existing_occurrence_contract(snapshot):
    request, pack, text = prepare(snapshot, "🔒 금감원은 발표했다. 금감원도 확인했다.")
    assert isinstance(request, CompactExecutionRequest)
    assert len(request.catalog) == 2
    response = {"selections": [output(request, i)["selections"][0] for i in range(2)]}
    result = consume(request, response, text)
    assert result["valid"] and result["violations"] == []
    assert len(result["selections"]) == 2
    assert result["selections"][0]["core_span"]["start"] == 2
    assert result["selections"][1]["core_span"]["start"] == text.rindex("금감원")
    assert result["selections"][0]["mention_id"] != result["selections"][1]["mention_id"]
    assert validate_llm_grounding({"selections": result["selections"]}, pack,
                                  purpose="execution")["valid"]


def test_repeated_surface_never_lends_a_resolved_occurrence_to_derivative(snapshot):
    text = "금감원은 발표했다. 금감원ICT가 별도로 발표했다."
    prepared = prepare_llm_context(snapshot, text, context_policy=ContextPolicy(
        profile="automation", max_tokens=10000))
    unresolved = next(m for m in prepared.resolve_response["mentions"]
                      if m["surface"] == "금감원" and m["link_decision"] != "RESOLVED")
    target = {"mention_id": unresolved["mention_id"],
              "core_span": unresolved["span"]["codepoint"],
              "full_span": unresolved["full_span"]["codepoint"]}
    request = create_compact_request(
        prepared.context_pack, document_text=text, tenant_id="tenant-a",
        scope_id="project-a", request_id="request-a", target_occurrences=[target])
    assert request.catalog == []
    assert consume(request, {"selections": []}, text)["valid"]


def test_target_subset_is_exact_in_all_three_components(snapshot):
    request, pack, text = prepare(snapshot, "금감원 발표. 금감원 확인.")
    target = {k: request.catalog[1]["occurrence"][k]
              for k in ("mention_id", "core_span", "full_span")}
    limited = create_compact_request(
        pack, document_text=text, tenant_id="tenant-a", scope_id="project-a",
        request_id="request-a", target_occurrences=[target])
    assert len(limited.catalog) == 1
    assert limited.catalog[0]["occurrence"]["core_span"] == target["core_span"]
    target["mention_id"] = "some-other-mention"
    missing = create_compact_request(
        pack, document_text=text, tenant_id="tenant-a", scope_id="project-a",
        request_id="request-a", target_occurrences=[target])
    assert missing.catalog == []


def test_ambiguity_and_degraded_facts_never_enter_catalog(snapshot):
    text = "금감원과 공통의 발표"
    prepared = prepare_llm_context(snapshot, text, context_policy=ContextPolicy(
        profile="qa_grounding", ambiguity_scope="all", max_tokens=10000))
    pack = prepared.context_pack
    assert pack["ambiguous_mentions"]
    request = create_compact_request(pack, document_text=text, tenant_id="tenant-a",
                                     scope_id="project-a", request_id="request-a")
    assert {c["entity_id"] for c in request.catalog} == {"global:fss"}
    result = consume(request, output(request, entity_id="global:billing"), text)
    assert not result["valid"] and not result["selections"]
    pack["resolved_terms"][0]["resolution"]["degraded"] = True
    degraded = create_compact_request(pack, document_text=text, tenant_id="tenant-a",
                                      scope_id="project-a", request_id="request-a")
    assert degraded.catalog == []


def test_original_pack_catalog_schema_and_identity_cannot_rewrite_authority(snapshot):
    request, pack, _ = prepare(snapshot)
    response = output(request)
    pack["resolved_terms"][0]["entity_id"] = "forged"
    pack["resolved_terms"][0]["mentions"][0]["core_span"]["start"] = 100
    catalog = request.catalog
    catalog[0]["entity_id"] = "forged"
    catalog[0]["occurrence"]["core_span"]["start"] = 100
    schema = request.response_schema
    schema["properties"]["selections"]["items"]["properties"]["entity_id"] = {}
    assert request.catalog[0]["entity_id"] == "global:fss"
    assert request.catalog[0]["occurrence"]["core_span"]["start"] == 0
    with pytest.raises(FrozenInstanceError):
        request.document_hash = "forged"
    with pytest.raises(TypeError):
        request._bindings[response["selections"][0]["ref"]] = "{}"
    assert consume(request, response)["valid"]


@pytest.mark.parametrize("field,value,kind", [
    ("tenant_id", "tenant-b", "compact_request_context_mismatch"),
    ("scope_id", "project-b", "compact_request_context_mismatch"),
    ("request_id", "request-b", "compact_request_context_mismatch"),
    ("snapshot_id", "activated-new-snapshot", "compact_snapshot_mismatch"),
    ("document_text", "금감원 발표 ", "compact_document_mismatch"),
])
def test_stale_host_context_closes_request(snapshot, field, value, kind):
    request, _, _ = prepare(snapshot)
    response = output(request)
    result = consume(request, response, **{field: value})
    assert result == {"valid": False, "violations": [{"kind": kind}], "selections": []}
    assert consume(request, response)["violations"] == [{"kind": "compact_request_consumed"}]


def test_same_host_ids_do_not_make_handles_transferable(snapshot):
    first, _, _ = prepare(snapshot)
    second, _, _ = prepare(snapshot)
    assert first.catalog[0]["ref"] != second.catalog[0]["ref"]
    foreign = consume(second, output(first))
    assert foreign["violations"] == [{"kind": "unknown_compact_reference"}]
    assert consume(first, output(first))["valid"]


@pytest.mark.parametrize("later", [110, 111, 99, float("nan"), float("inf")])
def test_expiry_boundary_and_clock_rollback_fail_closed(snapshot, later):
    times = iter([100, later])
    request, _, _ = prepare(snapshot, ttl_seconds=10, clock=lambda: next(times))
    assert consume(request, output(request))["violations"] == [
        {"kind": "compact_request_expired"}]
    assert consume(request, output(request))["violations"] == [
        {"kind": "compact_request_consumed"}]


def test_before_deadline_and_explicit_null_are_valid_abstention(snapshot):
    times = iter([100, 109.999])
    request, _, _ = prepare(snapshot, ttl_seconds=10, clock=lambda: next(times))
    result = consume(request, output(request, entity_id=None))
    assert result["valid"] and result["selections"][0]["entity_id"] is None
    assert consume(request, output(request))["violations"] == [
        {"kind": "compact_request_consumed"}]


@pytest.mark.parametrize("output_mutation", [
    lambda r: None,
    lambda r: {"answer": "금감원", **r},
    lambda r: {"selections": None},
    lambda r: {"selections": [None]},
    lambda r: {"selections": [dict(r["selections"][0], entity_id=1)]},
    lambda r: {"selections": [dict(r["selections"][0], mention_id="m2")]},
    lambda r: {"selections": [dict(r["selections"][0], ref=[])]},
    lambda r: {"selections": [dict(r["selections"][0], ref="unknown", entity_id=None)]},
])
def test_malformed_mixed_qa_or_extra_authority_fields_fail_closed(snapshot, output_mutation):
    request, _, _ = prepare(snapshot)
    result = consume(request, output_mutation(output(request)))
    assert not result["valid"] and result["selections"] == []
    assert consume(request, output(request))["violations"] == [
        {"kind": "compact_request_consumed"}]


def test_duplicate_or_partly_invalid_selection_does_not_return_partial_actions(snapshot):
    request, _, text = prepare(snapshot, "금감원 발표. 금감원 확인.")
    selection = output(request)["selections"][0]
    duplicate = consume(request, {"selections": [selection, selection]}, text)
    assert duplicate["violations"] == [{"kind": "duplicate_compact_reference"}]
    another, _, _ = prepare(snapshot, text)
    result = consume(another, {"selections": [output(another)["selections"][0],
        output(another, 1, entity_id="global:entry")["selections"][0]]}, text)
    assert not result["valid"] and result["selections"] == []


def test_concurrent_replays_can_consume_only_once(snapshot):
    request, _, _ = prepare(snapshot)
    response = output(request)
    barrier = Barrier(8)

    def attempt(_):
        barrier.wait(timeout=5)
        return consume(request, response)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(r["valid"] for r in results) == 1
    assert all(r["valid"] or r["violations"] == [{"kind": "compact_request_consumed"}]
               for r in results)


def test_concurrent_requests_preserve_their_own_document_and_scope(snapshot):
    barrier = Barrier(8)

    def independent(i):
        text = "서두 " * i + "금감원 발표"
        pack = prepare_llm_context(snapshot, text).context_pack
        request = create_compact_request(
            pack, document_text=text, tenant_id=f"tenant-{i}", scope_id=f"scope-{i}",
            request_id=f"request-{i}")
        barrier.wait(timeout=5)
        result = request.consume(
            output(request), document_text=text, snapshot_id=snapshot.snapshot_id,
            tenant_id=f"tenant-{i}", scope_id=f"scope-{i}", request_id=f"request-{i}")
        assert result["valid"]
        return result["selections"][0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(independent, range(8)))
    assert len({r["document_hash"] for r in results}) == 8
    assert [r["core_span"]["start"] for r in results] == [3 * i for i in range(8)]


@pytest.mark.parametrize("ttl", [0, -1, True, "60", float("inf"), float("nan")])
def test_invalid_lifetime_is_rejected_before_issuing_handles(snapshot, ttl):
    with pytest.raises(KtrfApiError, match="ttl_seconds"):
        prepare(snapshot, ttl_seconds=ttl)


def test_pack_identity_and_conflicting_authority_are_rejected(snapshot):
    _, pack, text = prepare(snapshot)
    args = dict(document_text=text, tenant_id="tenant-a", scope_id="project-a",
                request_id="request-a")
    different = copy.deepcopy(pack)
    different["document_hash"] = "0" * 64
    with pytest.raises(KtrfApiError, match="document hash"):
        create_compact_request(different, **args)
    conflicting = copy.deepcopy(pack)
    card = copy.deepcopy(pack["resolved_terms"][0])
    card["entity_id"] = "global:entry"
    conflicting["resolved_terms"].append(card)
    with pytest.raises(KtrfApiError, match="conflicting occurrence authority"):
        create_compact_request(conflicting, **args)


def test_bad_boolean_span_cannot_be_used_to_target_an_occurrence(snapshot):
    _, pack, text = prepare(snapshot)
    target = {k: copy.deepcopy(pack["resolved_terms"][0]["mentions"][0][k])
              for k in ("mention_id", "core_span", "full_span")}
    target["core_span"]["start"] = False
    with pytest.raises(KtrfApiError, match="invalid occurrence span"):
        create_compact_request(pack, document_text=text, tenant_id="tenant-a",
                               scope_id="project-a", request_id="request-a",
                               target_occurrences=[target])

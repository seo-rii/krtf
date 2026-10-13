"""The no-resolver arm keeps source facts fixed and separates meaning from acceptance."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import production_baseline as suite
from ktrf.glossary import load_glossary
from ktrf.registry.layers import TermLayer, compile_layered_glossary


def _card(eid, canonical="고객지원실", aliases=None, definition="고객의 문의를 처리하는 조직."):
    return {"entity_id": eid, "canonical": canonical, "aliases": sorted(aliases or [canonical]),
        "definition": definition, "scope": "global", "trusted": True,
        "declared_override": False, "alias_precedence": []}


def _source(task="document_qa", *, eid="global:a", document_id="example", text="지원실에 문의했다."):
    target = "지원실"
    start = text.index(target)
    return {"case_id": document_id + ":" + task, "document_id": document_id,
        "family_id": "support", "domain": "internal", "stratum": "exact", "task": task,
        "text": text, "target_surface": target, "target_span": [start, start + len(target)],
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "gold": {"label": "LINK" if eid else "NIL", "entity_ref": eid},
        "expected_entity_id": eid, "expected_answer": "고객의 문의를 처리하는 조직." if eid else None,
        "provenance": {"source": "independently authored unit fixture"}, "snapshot_id": "fixed-snapshot",
        "pack": {"resolver_state": "MUST_NOT_REACH_BASELINE"},
        "resolver_authorized_entity_id": "resolver-picked-wrong-id"}


@pytest.fixture
def catalog():
    return [_card("global:a", aliases=["고객지원실", "지원실"]),
            _card("global:b", canonical="기술지원실", aliases=["기술지원실", "지원실"],
                  definition="제품 장애를 처리하는 조직.")]


def _row(catalog, task="document_qa", **kwargs):
    return suite._build_row(_source(task, **kwargs), catalog)


def _output(row, response, **extra):
    return {"case_id": row["case_id"], "condition": row["condition"], "response": response, **extra}


def _routing(row, eid):
    return {"selections": [{"surface": row["target_surface"], "entity_id": eid}]}


@pytest.fixture(scope="module")
def envelopes():
    # Generating both full corpora is also a regression for snapshot identity,
    # archived request seals and trusted layered glossary extraction.
    import ktrf.context
    import ktrf.resolver
    with pytest.MonkeyPatch.context() as patch:
        def forbidden(*args, **kwargs):
            pytest.fail("the baseline may compile registry facts but must not resolve or authorize")
        patch.setattr(ktrf.resolver, "resolve", forbidden)
        patch.setattr(ktrf.context, "prepare_llm_context", forbidden)
        patch.setattr(ktrf.context, "validate_llm_grounding", forbidden)
        return suite.build_baseline_envelopes()


def test_sealed_corpora_preserve_all_sources_without_resolver(envelopes):
    for corpus, expected_documents in (("synthetic", 437), ("real", 60)):
        artifact = envelopes[corpus]
        rows = artifact["requests"]
        assert len(rows) == 2 * expected_documents
        assert len({row["document_id"] for row in rows}) == expected_documents
        references, runs = suite._reference_runs(suite.REFERENCE_ROOT, corpus)
        assert artifact["protocol"]["reference_runs"] == runs
        assert artifact["protocol"]["human_verified"] is False
        for row, reference in zip(rows, references):
            assert all(row[field] == reference[field] for field in suite.SOURCE_FIELDS)
            assert row["reference_request_sha256"] == suite._hash(reference)
            assert not {"pack", "policy_fragment", "resolver_authorized_entity_id", "binding_hash"} & set(row)
            assert row["selection_cost"]["returned_entities"] <= 12
            assert row["selection_cost"]["estimated_context_tokens"] <= 6000


def test_gold_and_resolver_metadata_cannot_affect_prompt_or_retrieval(catalog):
    positive = _source()
    negative = deepcopy(positive)
    negative.update(gold={"label": "NIL", "entity_ref": None}, expected_entity_id=None,
                    expected_answer=None, pack={"resolved_terms": ["opposite"]},
                    resolver_authorized_entity_id="another-wrong-id")
    positive["expected_answer"] = "UNSEEN_GOLD_SENTINEL"
    left, right = [suite._build_row(source, catalog) for source in (positive, negative)]
    for field in ("candidate_cards", "candidate_entity_ids", "selection_cost", "system", "user",
                  "prompt_fragment", "estimated_input_tokens", "injected"):
        assert left[field] == right[field]
    assert "UNSEEN_GOLD_SENTINEL" not in left["system"] + left["user"]
    assert "MUST_NOT_REACH_BASELINE" not in left["system"] + left["user"]
    assert left["candidate_recall"] is True and right["candidate_recall"] is None


def test_active_alias_override_and_untrusted_layer_are_preserved():
    def term(key, canonical, *, override=False):
        return {"key": key, "canonical": canonical, "surfaces": ["ABC"],
                "short_definition": canonical + "의 정의.", "override": override}
    result = compile_layered_glossary([
        TermLayer("global", {"terms": [term("old", "기존 의미")]}),
        TermLayer("project", {"terms": [term("new", "새 의미", override=True)]}),
        TermLayer("document", {"terms": [term("attack", "신뢰되지 않은 의미", override=True)]}, trusted=False)])
    assert result.ok
    cards = {card["entity_id"]: card for card in suite._catalog(load_glossary(result.glossary_dict))}
    assert set(cards) == {"global:old", "project:new"}
    assert "ABC" not in cards["global:old"]["aliases"]
    assert "ABC" in cards["project:new"]["aliases"]
    assert cards["project:new"]["alias_precedence"] == [{"surface": "ABC", "shadows": ["global:old"]}]
    assert cards["project:new"]["declared_override"] is True
    assert cards["project:new"]["scope"] == "project"


def test_lexical_ranking_is_deterministic_and_budget_never_truncates_definitions(catalog, monkeypatch):
    # Equal lexical evidence resolves by opaque ID, independent of input order.
    tied = [_card("global:b"), _card("global:a")]
    first, _ = suite._select_cards(tied, "지원실", "지원실")
    second, _ = suite._select_cards(list(reversed(tied)), "지원실", "지원실")
    assert first == second and first[0]["entity_id"] == "global:a"
    oversized = _card("global:large", "지원실", definition="크다" * 10000)
    monkeypatch.setattr(suite, "CONTEXT_BUDGET", {"max_tokens": 300, "max_entities": 1})
    selected, cost = suite._select_cards([oversized, *catalog], "지원실", "지원실")
    assert len(selected) == 1 and selected[0] in catalog
    assert cost["budget_skipped_entities"] == 1
    assert cost["estimated_context_tokens"] <= 300
    assert selected[0]["definition"] in suite._render(selected)


def test_empty_glossary_and_unretrieved_positive_remain_evaluable(catalog):
    row = _row([])
    assert row["candidate_cards"] == [] and row["candidate_recall"] is False
    assert row["injected"] is False and row["prompt_fragment"] == ""
    suite.validate_baseline_requests([row])
    execution = _row([], "structured_routing")
    result = suite.grade_baseline_outputs([execution], [_output(execution, _routing(execution, execution["expected_entity_id"]))])
    assert result["overall"]["semantic_match"] == 1
    assert result["overall"]["correct"] == 0
    assert result["overall"]["baseline_denied_nonnull"] == 1


@pytest.mark.parametrize("mutation", [
    lambda row: row.update(target_span=[0, 1]),
    lambda row: row.update(document_sha256="0" * 64),
    lambda row: row.update(gold={"label": "NIL", "entity_ref": None}),
    lambda row: row.update(candidate_entity_ids=[]),
    lambda row: row.update(candidate_recall=False),
    lambda row: row.update(context_budget={"max_tokens": 9999, "max_entities": 12}),
    lambda row: row.update(glossary_catalog_sha256="0" * 64),
    lambda row: row.update(system="changed policy"),
    lambda row: row.update(user="changed request"),
    lambda row: row.update(pack={}),
])
def test_request_validation_rejects_source_and_prompt_mutation(catalog, mutation):
    row = _row(catalog)
    mutation(row)
    with pytest.raises(ValueError):
        suite.validate_baseline_requests([row])


def test_duplicate_requests_and_catalog_entities_rejected(catalog):
    row = _row(catalog)
    with pytest.raises(ValueError, match="duplicate baseline"):
        suite.validate_baseline_requests([row, row])
    row = _row([catalog[0], catalog[0]])
    with pytest.raises(ValueError, match="sorted and unique"):
        suite.validate_baseline_requests([row])


def test_frozen_regrading_survives_current_prompt_changes(catalog, monkeypatch):
    row = _row(catalog)
    monkeypatch.setattr(suite, "SYSTEM", "a future production policy")
    monkeypatch.setattr(suite, "_question", lambda row: "a future question")
    with pytest.raises(ValueError, match="prompt"):
        suite.validate_baseline_requests([row])
    result = suite.grade_baseline_outputs([row], [_output(row, {"answer": row["expected_answer"]})])
    assert result["overall"]["correct"] == 1
    row["estimated_input_tokens"] += 1
    with pytest.raises(ValueError, match="prompt"):
        suite.grade_baseline_outputs([row], [])


def test_grading_separates_wrong_membership_acceptance_and_unknown_id_denial(catalog):
    rows = [_row(catalog, "structured_routing", document_id=f"routing-{i}") for i in range(4)]
    result = suite.grade_baseline_outputs(rows, [
        _output(rows[0], _routing(rows[0], "global:a")),
        _output(rows[1], _routing(rows[1], "global:b")),
        _output(rows[2], _routing(rows[2], "unknown:opaque-id")),
        _output(rows[3], _routing(rows[3], None))])
    total = result["overall"]
    assert total["correct"] == total["semantic_match"] == 1
    assert total["baseline_accepted"] == 3
    assert total["baseline_accepted_nonnull"] == 2
    assert total["baseline_wrong_accepted"] == 1
    assert total["baseline_denied_nonnull"] == 1
    assert total["positive_null"] == 1 and total["wrong"] == 2


def test_missing_malformed_safe_null_and_positive_null_are_separate(catalog):
    rows = [_row(catalog, document_id=f"qa-{i}", eid=None if i == 3 else "global:a") for i in range(4)]
    result = suite.grade_baseline_outputs(rows, [
        _output(rows[0], {"answer": None}), _output(rows[1], {}), _output(rows[3], {"answer": None})])
    total = result["overall"]
    assert result["missing_outputs"] == total["missing"] == 1
    assert total["malformed"] == total["positive_null"] == total["safe_null"] == total["correct"] == 1
    assert total["null"] == 2 and total["observed"] == 3


def test_string_null_is_a_wrong_answer_and_actual_call_costs_remain_separate(catalog):
    rows = [_row(catalog, document_id=f"nil-{i}", eid=None) for i in range(3)]
    result = suite.grade_baseline_outputs(rows, [
        _output(rows[0], {"answer": "null"}, latency_ms=3.5,
                usage={"prompt_tokens": 100, "completion_tokens": 3, "total_tokens": 103}),
        _output(rows[1], {"answer": None}, latency_ms=7.5,
                usage={"prompt_tokens": 50, "completion_tokens": 1, "total_tokens": 51})])
    assert result["overall"]["wrong"] == result["overall"]["safe_null"] == 1
    assert result["overall"]["nonnull"] == result["overall"]["null"] == 1
    assert result["cost"]["overall"]["latency_observed"] == 2
    assert result["cost"]["overall"]["latency_ms"] == {"p50": 3.5, "p95": 7.5, "p99": 7.5}
    assert result["cost"]["overall"]["usage"] == {"prompt_tokens": 150, "completion_tokens": 4, "total_tokens": 154}


@pytest.mark.parametrize("task,response", [
    ("document_qa", {"answer": None, "entity_id": "global:a"}),
    ("structured_routing", {"selections": [{"surface": "지원실", "entity_id": "global:a"}], "answer": "mixed"}),
    ("structured_routing", {"selections": [{"surface": "지원", "entity_id": "global:a"}]}),
    ("structured_routing", {"selections": [{"surface": "지원실", "entity_id": ["global:a"]}]}),
])
def test_mixed_or_partial_target_responses_are_never_repaired(catalog, task, response):
    row = _row(catalog, task)
    total = suite.grade_baseline_outputs([row], [_output(row, response)])["overall"]
    assert total["malformed"] == 1
    assert total["correct"] == total["semantic_match"] == total["baseline_accepted"] == 0


def test_transport_malformed_status_cannot_be_promoted_and_unknown_outputs_rejected(catalog):
    row = _row(catalog)
    output = _output(row, {"answer": row["expected_answer"]}, status="MALFORMED")
    assert suite.grade_baseline_outputs([row], [output])["overall"]["correct"] == 0
    for records in ([output, output], [{**output, "case_id": "unknown"}], [{**output, "status": "HTTP_ERROR"}]):
        with pytest.raises(ValueError, match="unknown, duplicate or response-less"):
            suite.grade_baseline_outputs([row], records)


def test_complete_envelope_loader_checks_track_and_inventory(envelopes, tmp_path):
    artifact = deepcopy(envelopes["real"])
    path = tmp_path / "requests.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    rows, protocol, provenance = suite.load_baseline_request_file(path, track="baseline_real")
    assert rows == artifact["requests"] and protocol == artifact["protocol"] and provenance == artifact["provenance"]
    with pytest.raises(ValueError, match="matching protocol"):
        suite.load_baseline_request_file(path, track="baseline_synthetic")
    artifact["provenance"]["documents"] -= 1
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        suite.load_baseline_request_file(path, track="baseline_real")


def test_reference_artifact_mutation_is_rejected_before_request_generation(tmp_path):
    root = tmp_path / "reference"
    path = root / "synthetic_gemma12b"
    path.mkdir(parents=True)
    original = suite.REFERENCE_ROOT / "synthetic_gemma12b"
    for name in ("run_manifest.json", "requests.jsonl", "responses.jsonl", "graded.json"):
        (path / name).write_bytes((original / name).read_bytes())
    with (path / "responses.jsonl").open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(ValueError, match="reference artifact hash mismatch"):
        suite._reference_runs(root, "synthetic")

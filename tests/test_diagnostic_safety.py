"""Robustness variants preserve the frozen semantic source and guard contract."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json

import pytest

from eval import diagnostic_safety as suite
from eval import extended_safety
from eval.hf_qa import canonical


class Tokenizer:
    def __init__(self, length=100):
        self.length, self.calls = length, []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return list(range(self.length))


MODELS = {key: {"path": "/fixture/" + key} for key in ("gemma12b", "qwen27b")}


@pytest.fixture(scope="module")
def prior():
    return extended_safety.prepare_safety(code_revision="prior-fixture-revision",
        tokenizers={key: Tokenizer() for key in MODELS}, models=MODELS)[0]


@pytest.fixture(scope="module")
def prepared(prior):
    tokenizers = {key: Tokenizer() for key in MODELS}
    envelope, aggregate = suite.prepare_robustness(prior_safety_envelope=prior,
        code_revision="fixture-revision", tokenizers=tokenizers, models=MODELS)
    return envelope, aggregate, tokenizers


def test_new_gold_balanced_disjoint_and_authored_before_resolution():
    data, old = suite.load_cases(), extended_safety.load_cases()
    assert data["annotation_origin"] == "AI_AUTHORED" and data["human_verified"] is False
    assert len(data["families"]) == 16
    assert {f["family_id"] for f in data["families"]}.isdisjoint(f["family_id"] for f in old["families"])
    assert {t["canonical"] for f in data["families"] for t in f["terms"]}.isdisjoint(
        t["canonical"] for f in old["families"] for t in f["terms"])
    assert Counter(f["stratum"] for f in data["families"]) == {s: 4 for s in suite.STRATA}
    for f in data["families"]:
        assert sum(c["gold"]["label"] == "LINK" for c in f["cases"]) == 2
        for c in f["cases"]:
            start, end = c["target_span"]
            assert c["text"][start:end] == c["target_surface"]
            if c["gold"]["label"] == "COMPOSITIONAL":
                assert c["gold"]["full_identity"] == "DISTINCT"
                assert c["gold"]["entity_ref"] is None
                assert c["gold"]["core_surface"] != c["target_surface"]


def test_complete_matrix_counts_sources_and_actual_tokenizers(prepared, prior):
    envelope, aggregate, tokenizers = prepared
    rows = envelope["requests"]
    assert envelope["protocol"]["kind"] == "ktrf_extended_v1"
    assert envelope["protocol"]["conditions"] == list(suite.CONDITIONS)
    assert envelope["protocol"]["evaluation_splits"] == {"exposed_diagnostic": 96, "fresh_family": 64}
    assert aggregate["request_count"] == 640 and aggregate["question_count"] == 160
    assert aggregate["family_count"] == 40 and aggregate["positive_questions"] == 80
    assert aggregate["strata"] == {s: 40 for s in suite.STRATA}
    assert aggregate["envelope_sha256"] == hashlib.sha256(canonical(envelope)).hexdigest()
    assert aggregate["prior_envelope_sha256"] == hashlib.sha256(canonical(prior)).hexdigest()
    assert aggregate["requests_sha256"] == hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest()
    assert Counter(r["evaluation_split"] for r in rows) == {"exposed_diagnostic": 384, "fresh_family": 256}
    old_by_id = {r["case_id"]: r for r in prior["requests"]}
    for row in rows:
        if row["evaluation_split"] == "exposed_diagnostic":
            assert suite._production_row(row) == old_by_id[row["case_id"]]
    for key, tokenizer in tokenizers.items():
        assert len(tokenizer.calls) == 640
        assert aggregate["models"][key]["request_count"] == 640
        for row, (messages, settings) in zip(rows, tokenizer.calls):
            assert messages == [{"role": "system", "content": row["system"]},
                                {"role": "user", "content": row["user"]}]
            assert settings == {"tokenize": True, "add_generation_prompt": True,
                "enable_thinking": False, "return_dict": False}


def test_placement_and_semantic_instruction_are_the_only_prompt_changes(prepared):
    rows = prepared[0]["requests"]
    by_case = defaultdict(dict)
    for row in rows:
        by_case[row["case_id"]][row["condition"]] = row
    for group in by_case.values():
        first, last = group["pack_first_baseline"], group["pack_last_baseline"]
        assert first["system"] == first["production_system"] == last["system"]
        assert first["user"] == first["production_user"]
        if first["injected"]:
            prefix = first["prompt_fragment"] + "\n"
            assert first["user"].startswith(prefix)
            assert last["user"] == first["user"][len(prefix):] + "\n" + first["prompt_fragment"]
        else:
            assert last["user"] == first["user"]
        for baseline in (first, last):
            checked = group[baseline["placement"] + "_semantic_check"]
            assert checked["user"] == baseline["user"]
            assert checked["system"] == baseline["system"] + "\n" + suite.SEMANTIC_POLICY
            assert checked["pack"] == baseline["pack"]
            assert checked["gold"] == baseline["gold"]
        for row in group.values():
            assert suite.reconstruct_variant(row, row["condition"]) == (row["system"], row["user"])


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows[0].update(user=rows[0]["user"] + " changed"),
    lambda rows: rows[0].update(production_user="different source"),
    lambda rows: rows[0]["pack"].update(resolved_terms=[]),
    lambda rows: rows[0].update(evaluation_split="fresh_family"),
    lambda rows: rows[0].update(condition="pack_last_baseline"),
    lambda rows: rows[0].update(estimated_input_tokens=1),
    lambda rows: rows[0].update(target_span=[0, 1]),
    lambda rows: rows[0]["gold"].update(label="NON_MENTION", entity_ref=None),
    lambda rows: rows[0].update(source_text="unrelated original document"),
    lambda rows: rows[0].update(semantic_check=True),
])
def test_variant_or_sealed_source_tampering_rejected(prepared, mutation):
    rows = deepcopy(prepared[0]["requests"])
    mutation(rows)
    with pytest.raises(ValueError):
        suite.validate_robustness_requests(rows)


def test_underlying_production_contract_is_validated_once_per_case(prepared, monkeypatch):
    seen = []
    real = suite.validate_production_requests

    def observe(rows, **kwargs):
        seen.extend(rows)
        assert kwargs == {"check_current_policy": False}
        return real(rows, **kwargs)

    monkeypatch.setattr(suite, "validate_production_requests", observe)
    suite.validate_robustness_requests(prepared[0]["requests"])
    assert len(seen) == 160
    assert {row["condition"] for row in seen} == {"production"}


def test_fresh_source_seal_is_fixed_before_resolver_and_no_case_is_filtered(prior, monkeypatch):
    gold = suite.load_cases()
    seal = hashlib.sha256(canonical(gold)).hexdigest()
    seen = []
    original = suite.build_document_requests

    def observe(*args, **kwargs):
        assert kwargs["provenance"]["authored_gold_sha256"] == seal
        seen.append(kwargs["document_id"])
        return original(*args, **kwargs)

    monkeypatch.setattr(suite, "build_document_requests", observe)
    result, _ = suite.prepare_robustness(prior_safety_envelope=prior, code_revision="fixture",
        models=MODELS, tokenizers={key: Tokenizer() for key in MODELS})
    assert set(seen) == {c["case_id"] for f in gold["families"] for c in f["cases"]}
    assert len(seen) == 64
    assert len(result["requests"]) == 640


def test_gold_review_required_before_any_resolution(prior, monkeypatch):
    monkeypatch.setattr(suite, "REVIEWED_CASE_FILE_SHA256", "not-reviewed")
    def forbidden(*args, **kwargs):
        raise AssertionError("resolver must not run before independent source review")
    monkeypatch.setattr(suite, "compile_snapshot", forbidden)
    with pytest.raises(ValueError, match="independent gold review"):
        suite.prepare_robustness(prior_safety_envelope=prior, code_revision="fixture",
            models=MODELS, tokenizers={key: Tokenizer() for key in MODELS})


def test_complete_malformed_raw_routing_response_still_reaches_execution_guard(prepared, monkeypatch):
    row = prepared[0]["requests"][0]
    raw = {"selections": [{"surface": row["target_surface"], "entity_id": row["expected_entity_id"]}],
           "answer": "a field that must not be projected away"}
    seen = []
    original = extended_safety.validate_llm_grounding
    def observe(response, pack, *, purpose, execution_contract):
        seen.append(response)
        return original(response, pack, purpose=purpose, execution_contract=execution_contract)
    monkeypatch.setattr(extended_safety, "validate_llm_grounding", observe)
    result = extended_safety.grade_safety(row, raw)
    assert seen == [raw] and seen[0] is raw
    assert result["malformed"] and not result["correct"]
    assert not result["accepted_correct_id"] and not result["accepted_wrong_id"]
    assert result["guard_violations"] == [{"kind": "qa_output_not_executable"}]


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(human_verified=True),
    lambda data: data["families"][0].update(family_id="geo-haeon"),
    lambda data: data["families"][0]["terms"][0].update(canonical="해온시"),
    lambda data: data["families"][0]["cases"][0].update(target_span=[0, 1]),
    lambda data: data["families"][4]["cases"][2]["gold"].update(full_identity="SAME"),
    lambda data: data["families"][0]["cases"].pop(),
])
def test_invalid_authored_source_rejected(tmp_path, mutation):
    data = suite.load_cases()
    mutation(data)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        suite.load_cases(path)


def test_complete_prior_cases_required(prior):
    changed = deepcopy(prior)
    changed["requests"].pop()
    with pytest.raises(ValueError, match="all 96"):
        suite.prepare_robustness(prior_safety_envelope=changed, code_revision="fixture",
            models=MODELS, tokenizers={key: Tokenizer() for key in MODELS})


def test_actual_prompt_overflow_rejects_whole_experiment(prior):
    with pytest.raises(ValueError, match="token capacity"):
        suite.prepare_robustness(prior_safety_envelope=prior, code_revision="fixture",
            models=MODELS, tokenizers={key: Tokenizer(8065) for key in MODELS})

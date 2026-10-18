"""Authored, offline checks for the fresh article-disjoint combined sample."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from eval import prepare_combined_followup as combined
from eval import prepare_fresh_combined as prepare
from eval import run_followup_llm as runner
from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import canonical
from eval.hf_retrieval_followup import build_variants
from tests.test_prepare_followup import _record, prepared_inputs


@pytest.fixture
def fresh_inputs(prepared_inputs, monkeypatch):
    calls = []

    def no_pack(snapshot, text, *, query, mode, context_policy):
        assert mode == "commit" and context_policy.max_tokens == 800
        calls.append((snapshot, text, query))
        return SimpleNamespace(should_inject=False, context_pack={"source": text},
                               prompt_fragment="고정 보조 용어", policy_fragment="고정 용어 정책")

    monkeypatch.setattr(combined, "prepare_llm_context", no_pack)
    kwargs = deepcopy(prepared_inputs)
    kwargs["quotas"] = kwargs.pop("retrieval_quotas")
    kwargs.pop("expected_old_questions")
    snapshot = SimpleNamespace(snapshot_id="authored-fresh-snapshot")
    exposed = [_record("retrieval-exposed-span"), _record("retrieval-exposed-null", "NO_ANSWER")]
    parent_copy = _record("different-id-same-exposed-parent")
    parent_copy["parent_document_id"] = exposed[0]["parent_document_id"]
    hash_copy = deepcopy(exposed[1])
    hash_copy.update(document_id="different-id-same-exposed-content",
                     parent_document_id="different-parent-same-exposed-content")
    kwargs["records"].extend(exposed + [parent_copy, hash_copy])
    kwargs["prior_retrieval"] = [row for record in exposed for row in build_variants(record)]
    kwargs["prior_combined"] = combined.build_combined(
        kwargs["prior_retrieval"], snapshot, expected_questions=2)
    kwargs["snapshot"] = snapshot
    kwargs["input_hashes"].update(prior_retrieval="e" * 64, prior_combined="f" * 64)
    calls.clear()
    return kwargs, calls


def test_excludes_every_prior_parent_and_exact_content_even_with_different_ids(fresh_inputs):
    kwargs, _ = fresh_inputs
    envelope, manifest = prepare.prepare_from_records(**kwargs)
    rows = runner.validate_requests(envelope["requests"], "combined")
    assert len(rows) == 60
    assert len({row["document_id"] for row in rows}) == 5
    assert all(row["document_id"].startswith("new-") for row in rows)
    assert all(row["independent_from_prior_declared_articles"] is True for row in rows)
    assert all(row["reused_original_question"] is False and row["independent_validation"] is False
               for row in rows)
    excluded = manifest["prior_exclusions"]
    assert excluded["old_screening_pool_questions"] == 4
    assert excluded["prior_evidence_questions"] == 2
    assert excluded["blind_document_rows"] == 1
    assert excluded["prior_retrieval_questions"] == excluded["prior_combined_questions"] == 2
    assert excluded["all_prior_followup_articles_excluded"] is True
    assert manifest["selection"]["exclusions"]["prior_parent_or_content_overlap"] == 11
    assert manifest["total_requests_per_model"] == 60
    assert manifest["total_planned_model_calls"] == 120
    assert manifest["experiments"]["combined"]["strata"] == kwargs["quotas"]


@pytest.mark.parametrize("prior", ["prior_retrieval", "prior_combined"])
def test_rejects_consistently_changed_prior_gold_against_source(fresh_inputs, prior):
    kwargs, _ = fresh_inputs
    for row in kwargs[prior]:
        if row["positive_gold"]:
            row["expected_answers"] = ["변조된 정답"]
    # The complete matrix still agrees internally; the source comparison must
    # reject it rather than accepting self-consistent but altered exclusions.
    runner.validate_requests(kwargs[prior], "retrieval" if prior.endswith("retrieval") else "combined")
    with pytest.raises(ValueError, match="source or gold differs"):
        prepare.prepare_from_records(**kwargs)


def test_rejects_prior_combined_sample_that_omits_retrieval_article(fresh_inputs):
    kwargs, _ = fresh_inputs
    kwargs["prior_combined"] = [row for row in kwargs["prior_combined"] if row["positive_gold"]]
    runner.validate_requests(kwargs["prior_combined"], "combined")
    with pytest.raises(ValueError, match="complete retrieval sample"):
        prepare.prepare_from_records(**kwargs)


def test_reversing_source_order_preserves_selected_requests_and_seals(fresh_inputs):
    kwargs, _ = fresh_inputs
    expected = prepare.prepare_from_records(**kwargs)
    assert prepare.prepare_from_records(**{**kwargs, "records": list(reversed(kwargs["records"]))}) == expected


def test_insufficient_distinct_articles_fail_without_reusing_exposed_articles(fresh_inputs):
    kwargs, calls = fresh_inputs
    kwargs["quotas"] = {"SPAN": 5, "YES_NO": 1, "NO_ANSWER": 2}
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA") as caught:
        prepare.prepare_from_records(**kwargs)
    assert caught.value.inventory["quotas"] == kwargs["quotas"]
    assert caught.value.inventory["selected_by_stratum"] == {"SPAN": 4, "YES_NO": 1, "NO_ANSWER": 2}
    assert caught.value.inventory["exclusions"]["prior_parent_or_content_overlap"] == 11
    assert calls == []  # No pack or retrieval-success filtering precedes selection.


def test_pack_without_injection_preserves_prompt_and_ranker_source_pair(fresh_inputs):
    kwargs, calls = fresh_inputs
    envelope, manifest = prepare.prepare_from_records(**kwargs)
    rows = envelope["requests"]
    indexed = {(row["document_id"], row["context_condition"], row["repeat_id"]): row for row in rows}
    expected_calls = []
    for row in rows:
        if row["context_condition"].endswith("_pack"):
            plain = indexed[(row["document_id"], row["context_condition"].removesuffix("_pack"), row["repeat_id"])]
            assert row["pack_injected"] is False
            for field in ("system", "user", "source_spans", "source_gold_visible", "source_text",
                          "document_sha256", "parent_document_id"):
                assert row[field] == plain[field]
            assert row["pack_prompt"] is row["pack_policy"] is None
        elif row["repeat_id"] == 0:
            source = "\n\n".join(row["source_text"][start:end] for start, end in row["source_spans"])
            expected_calls.append((row["question"] + "\n" + source, row["question"]))
    assert len(calls) == 10
    assert all(snapshot is kwargs["snapshot"] for snapshot, _, _ in calls)
    assert sorted((text, query) for _, text, query in calls) == sorted(expected_calls)
    assert manifest["snapshot_id"] == kwargs["snapshot"].snapshot_id
    assert manifest["experiments"]["combined"]["pack_injected_questions_by_ranker"] == {
        "lexical": 0, "bm25": 0}


def test_no_oracle_capacity_or_pack_eligibility_filter_removes_selected_positive(fresh_inputs):
    kwargs, _ = fresh_inputs
    record = _record("new-overlong-oracle")
    text = "목표 답안은 사과나무다." + "긴문단" * 1200
    record.update(text=text, document_sha256=hashlib.sha256(text.encode()).hexdigest(),
        passage_candidates=[[0, len(text)]], answer_passage_spans=[[0, len(text)]])
    kwargs["records"].append(record)
    kwargs["quotas"] = {"SPAN": 5, "YES_NO": 0, "NO_ANSWER": 1}
    envelope, manifest = prepare.prepare_from_records(**kwargs)
    assert any(row["document_id"] == record["document_id"] for row in envelope["requests"])
    assert "predeclared_capacity_rule" not in manifest["selection"]["exclusions"]
    assert manifest["experiments"]["combined"]["strata"] == {"SPAN": 5, "YES_NO": 0, "NO_ANSWER": 1}


def test_preparation_never_calls_generation_and_public_manifest_has_no_raw_material(fresh_inputs, monkeypatch):
    kwargs, _ = fresh_inputs

    def forbidden(*args, **kw):
        pytest.fail("request preparation must not call the model API")

    monkeypatch.setattr(runner, "_request_json", forbidden)
    envelope, manifest = prepare.prepare_from_records(**kwargs)
    validate_public_json(manifest)
    public = json.dumps(manifest, ensure_ascii=False)
    for record in kwargs["records"]:
        assert record["document_id"] not in public
        assert record["parent_document_id"] not in public
        assert record["text"] not in public
        assert record["question"] not in public
    assert "사과나무" not in public and "expected_answers" not in public
    proof = manifest["experiments"]["combined"]
    assert proof["envelope_sha256"] == hashlib.sha256(canonical(envelope)).hexdigest()
    assert proof["requests_sha256"] == hashlib.sha256(b"".join(canonical(row) for row in envelope["requests"])).hexdigest()
    assert envelope["protocol"]["selection_before_generation_outputs"] is True
    assert all(item["overflow_count"] == 0 and item["max_source_tokens"] <= 1536
               for item in proof["models"].values())


@pytest.mark.parametrize("changed_input", sorted(prepare.INPUT_NAMES))
def test_pinned_input_mismatch_fails_before_source_load_or_tokenizer(tmp_path, monkeypatch, changed_input):
    inputs = {}
    for name in sorted(prepare.INPUT_NAMES):
        path = tmp_path / name
        content = ("authored input " + name).encode()
        path.write_bytes(content)
        inputs[name] = {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}
    inputs[changed_input]["sha256"] = "0" * 64

    def forbidden(*args, **kwargs):
        pytest.fail("input seals must be checked before data or models are loaded")

    monkeypatch.setattr(prepare, "load_tydi_records", forbidden)
    monkeypatch.setattr(prepare, "load_tokenizers", forbidden)
    out = tmp_path / "prepared"
    with pytest.raises(ValueError, match="pinned input hash differs: " + changed_input):
        prepare.prepare({"inputs": inputs, "models": {}}, out, code_revision="authored")
    assert not out.exists()


def test_source_hash_must_also_match_the_registered_dataset(tmp_path, monkeypatch):
    path = tmp_path / "unregistered-source"
    path.write_text("authored input with a valid declared file seal")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()

    def forbidden(*args, **kwargs):
        pytest.fail("unregistered source cannot reach the source reader")

    monkeypatch.setattr(prepare, "load_tydi_records", forbidden)
    inputs = {name: {"path": str(path), "sha256": sha} for name in prepare.INPUT_NAMES}
    with pytest.raises(ValueError, match="declared TyDiQA revision"):
        prepare.prepare({"inputs": inputs, "models": {}}, tmp_path / "out", code_revision="authored")


def test_generation_outputs_are_not_an_accepted_preparation_input(tmp_path, monkeypatch):
    inputs = {name: {"path": "unused", "sha256": "0" * 64} for name in prepare.INPUT_NAMES}
    inputs["responses"] = {"path": "unused-model-outputs", "sha256": "1" * 64}

    def forbidden(*args, **kwargs):
        pytest.fail("unknown inputs must be rejected before any file access")

    monkeypatch.setattr(prepare, "_sha_file", forbidden)
    with pytest.raises(ValueError, match="all source, glossary and prior exposure inputs"):
        prepare.prepare({"inputs": inputs, "models": {}}, tmp_path / "out", code_revision="authored")

"""Reused-source diagnostics retain seals without claiming new validation."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json

import pytest

from eval import prepare_evidence_robustness as wrapper
from eval.evidence_efficiency_data import (
    CASES_FILE, REVIEW_FILE, SOURCE_SHA256, REVIEW_SHA256, load_evidence_efficiency_records,
)
from eval.evidence_robustness import CONDITIONS, POPULATION
from eval.hf_qa import canonical
from eval.run_extended_suite import load_request_file
from test_evidence_efficiency import FixtureTokenizer


def config():
    return {"source_sha256": SOURCE_SHA256, "review_sha256": REVIEW_SHA256,
        "models": {key: {"path": "fixture:" + key} for key in ("gemma12b", "qwen27b")}}


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("robustness-wrapper") / "prepared"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(wrapper, "load_tokenizers",
                      lambda models: {key: FixtureTokenizer() for key in models})
        manifest = wrapper.prepare(config(), output, code_revision="f" * 40)
    return output, manifest


@pytest.mark.parametrize("field", ["source_sha256", "review_sha256"])
def test_changed_seal_rejected_before_resolution_or_tokenizers(tmp_path, monkeypatch, field):
    selected = config()
    selected[field] = "0" * 64
    monkeypatch.setattr(wrapper, "load_evidence_efficiency_records",
                        lambda: pytest.fail("changed source must fail before loader"))
    monkeypatch.setattr(wrapper, "load_tokenizers",
                        lambda _: pytest.fail("changed source must fail before inference preparation"))
    with pytest.raises(ValueError, match="source gold or independent review changed"):
        wrapper.prepare(selected, tmp_path / "absent", code_revision="f" * 40)
    assert not (tmp_path / "absent").exists()


def test_immutable_revision_and_exact_model_pair_required(tmp_path):
    with pytest.raises(ValueError, match="immutable code revision"):
        wrapper.prepare(config(), tmp_path / "moving", code_revision="main")
    for removed in ("gemma12b", "qwen27b"):
        selected = config()
        selected["models"].pop(removed)
        with pytest.raises(ValueError, match="both frozen model tokenizers"):
            wrapper.prepare(selected, tmp_path / removed, code_revision="f" * 40)
    selected = config()
    selected["models"]["unplanned"] = {"path": "fixture:unplanned"}
    with pytest.raises(ValueError, match="both frozen model tokenizers"):
        wrapper.prepare(selected, tmp_path / "extra", code_revision="f" * 40)


@pytest.mark.parametrize("mutation", ["duplicate_case", "wrong_count", "split_counts", "split_family"])
def test_changed_historical_source_split_fails_before_tokenizers(tmp_path, monkeypatch, mutation):
    records = load_evidence_efficiency_records()
    if mutation == "duplicate_case":
        records[-1] = deepcopy(records[0])
    elif mutation == "wrong_count":
        records.pop()
    elif mutation == "split_counts":
        records[0]["evaluation_split"] = ("development" if records[0]["evaluation_split"]
                                             == "confirmation" else "confirmation")
    else:
        dev = next(row for row in records if row["evaluation_split"] == "development")
        confirmation = next(row for row in records if row["evaluation_split"] == "confirmation")
        dev["evaluation_split"], confirmation["evaluation_split"] = (
            confirmation["evaluation_split"], dev["evaluation_split"])
    monkeypatch.setattr(wrapper, "load_evidence_efficiency_records", lambda: records)
    monkeypatch.setattr(wrapper, "load_tokenizers",
                        lambda _: pytest.fail("invalid source must fail before tokenizer"))
    with pytest.raises(ValueError, match="source documents|historical .* family split"):
        wrapper.prepare(config(), tmp_path / mutation, code_revision="f" * 40)


def test_manifest_explicitly_identifies_reused_historical_source(prepared):
    output, manifest = prepared
    assert hashlib.sha256(CASES_FILE.read_bytes()).hexdigest() == SOURCE_SHA256
    assert hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest() == REVIEW_SHA256
    source = manifest["source"]
    assert source["kind"] == "reused_ai_authored_evidence_efficiency"
    assert source["evaluation_population"] == POPULATION == "REUSED_SEALED_SOURCE_DIAGNOSTIC"
    assert source["prior_source_run"] == "ktrf-efficiency-20261021T145325Z"
    assert source["reused_source"] and not source["independent_validation"]
    assert not source["human_verified"] and not source["private_workplace_distribution_measured"]
    assert source["source_gold_before_resolver"]
    assert source["independent_ai_review"]["cases_reviewed"] == 64
    assert source["independent_ai_review"]["resolved_before_resolver"]
    assert source["methods_predeclared_without_reading_prior_run_responses"]
    assert not manifest["independent_validation"]
    assert manifest["total_planned_model_calls"] == 768
    assert manifest["source_origin_split_case_counts"] == {"development": 16, "confirmation": 48}
    assert manifest["split_counts_describe"] == "historical_source_origin_only_no_new_holdout"
    assert manifest["real_business_shadow_status"] == "WAITING_FOR_INPUT"
    assert json.loads((output / "manifest.json").read_text()) == manifest


def test_complete_six_arm_matrix_preserves_original_source_and_seals(prepared):
    output, manifest = prepared
    rows, protocol, provenance = load_request_file(output / "evidence_robustness.json")
    sources = {row["case_id"]: row for row in load_evidence_efficiency_records()}
    grouped = defaultdict(list)
    assert len(rows) == 384
    assert protocol["experiment"] == "evidence_robustness"
    for row in rows:
        grouped[row["case_id"]].append(row)
        source = sources[row["case_id"]]
        for key in ("text", "document_sha256", "target_surface", "target_core_span", "target_full_span",
                    "gold", "expected_entity_id", "family_id", "document_id", "parent_document_id",
                    "evaluation_split"):
            assert row[key] == source[key]
        assert row["source_origin_split"] == source["evaluation_split"]
        assert row["evaluation_population"] == POPULATION
        assert not row["independent_validation"]
        assert row["evidence_required"]
    assert set(grouped) == set(sources)
    assert all(len(group) == 6 and {row["condition"] for row in group} == set(CONDITIONS)
               for group in grouped.values())
    assert Counter(group[0]["source_origin_split"] for group in grouped.values()) == {
        "development": 16, "confirmation": 48}
    assert provenance["source"] == manifest["source"]
    proof = manifest["experiments"]["evidence_robustness"]
    assert proof["request_count"] == 384 and proof["question_count"] == 64
    assert proof["envelope_sha256"] == hashlib.sha256((output / "evidence_robustness.json").read_bytes()).hexdigest()
    assert proof["requests_sha256"] == hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest()


@pytest.mark.parametrize("mutation", ["missing_arm", "duplicate_arm", "unpaired_source", "fresh_population", "fresh_split"])
def test_wrapper_checks_complete_pairing_independently_of_adapter(
        prepared, tmp_path, monkeypatch, mutation):
    output, manifest = prepared
    envelope = json.loads((output / "evidence_robustness.json").read_text())
    rows = envelope["requests"]
    if mutation == "missing_arm":
        rows.pop()
    elif mutation == "duplicate_arm":
        same_case = [row for row in rows if row["case_id"] == rows[0]["case_id"]]
        same_case[0]["condition"] = same_case[1]["condition"]
    elif mutation == "unpaired_source":
        rows[0]["expected_entity_id"] = "global:changed-gold"
    elif mutation == "fresh_population":
        rows[0]["evaluation_population"] = "FRESH_AI_AUTHORED_CONFIRMATION"
    else:
        rows[0]["source_origin_split"] = "new_confirmation"
    monkeypatch.setattr(wrapper, "load_tokenizers", lambda models: {})
    monkeypatch.setattr(wrapper, "prepare_evidence_robustness", lambda **kwargs: (
        envelope, deepcopy(manifest["experiments"]["evidence_robustness"])))
    monkeypatch.setattr(wrapper, "validate_requests", lambda requests, protocol: requests)
    with pytest.raises(ValueError, match="complete .* matrix|paired requests changed"):
        wrapper.prepare(config(), tmp_path / mutation, code_revision="f" * 40)
    assert not (tmp_path / mutation).exists()

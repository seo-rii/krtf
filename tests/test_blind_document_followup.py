"""Protocol checks use synthetic fixtures; they are never evaluation gold."""
import hashlib
import json
from pathlib import Path

import pytest

from eval.blind_document_followup import (PARTITIONS, evaluate, seal_bundle,
                                          validate_inputs, verify_bundle)

GLOSSARY = Path(__file__).resolve().parents[1] / "examples/realorg_glossary.yaml"


def fixture_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    documents, first, second = [], [], []
    for index in range(24):
        text = f"원천 문단 {index}: 명시적 대상 없음."
        sha = hashlib.sha256(text.encode()).hexdigest()
        document = {"document_id": f"doc-{index}", "parent_document_id": f"parent-{index}",
            "source_document_id": f"source-{index}", "source_document_sha256": sha,
            "source_span": [0, len(text)], "source_row_id": str(index), "dataset_revision": "revision",
            "source_file_sha256": "source-sha", "text": text, "document_sha256": sha,
            "family_ids": [], "partition": PARTITIONS[index // 8], "collected_at": "2026-10-18T00:00:00Z"}
        documents.append(document)
        for target, name in ((first, "a"), (second, "b")):
            target.append({"document_id": document["document_id"], "text": text,
                "document_sha256": sha, "annotator": name, "annotation_kind": "AI",
                "resolver_outputs_seen": False, "complete": True, "mentions": [],
                "review_note": f"Independent exhaustive negative review {name}."})
    for filename, rows in (("documents.jsonl", documents), ("annotator-a.jsonl", first),
                           ("annotator-b.jsonl", second), ("decisions.jsonl", [])):
        (bundle / filename).write_text("".join(json.dumps(row) + "\n" for row in rows))
    (bundle / "exclusions.json").write_text('{"prior_parents":[],"prior_content_hashes":[]}')
    return bundle, documents, first, second


def test_negative_documents_require_both_exhaustive_reviews(tmp_path):
    _, documents, first, second = fixture_bundle(tmp_path)
    validate_inputs(documents, first, second, GLOSSARY)
    with pytest.raises(ValueError, match="exhaustively"):
        validate_inputs(documents, first, second[:-1], GLOSSARY)
    second[0].pop("review_note")
    with pytest.raises(ValueError, match="review note"):
        validate_inputs(documents, first, second, GLOSSARY)


@pytest.mark.parametrize("mutation,match", [
    (lambda d, a: d[1].update(parent_document_id=d[0]["parent_document_id"]), "parent-disjoint"),
    (lambda d, a: d[0].update(partition="test"), "eight complete"),
    (lambda d, a: a[0].update(resolver_outputs_seen=True), "blind AI"),
    (lambda d, a: a[0].update(text="changed"), "hash mismatch"),
])
def test_protocol_rejects_leakage_and_unblinded_inputs(tmp_path, mutation, match):
    _, documents, first, second = fixture_bundle(tmp_path)
    mutation(documents, first)
    with pytest.raises(ValueError, match=match):
        validate_inputs(documents, first, second, GLOSSARY)


def test_semantic_agreement_ignores_independent_note_prose_and_seals_originals(tmp_path):
    bundle, _, _, _ = fixture_bundle(tmp_path)
    manifest = seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")
    assert manifest["semantic_disagreement_documents"] == 0
    assert manifest["bundle_files"]["annotator-a.jsonl"] != manifest["bundle_files"]["annotator-b.jsonl"]
    assert all(row["adjudicated"] for row in
               map(json.loads, (bundle / "gold.jsonl").read_text().splitlines()))
    with pytest.raises(ValueError, match="already sealed"):
        seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")


def test_disagreement_requires_manual_decision(tmp_path):
    bundle, _, first, second = fixture_bundle(tmp_path)
    first[0]["mentions"] = [{"span": [0, 2], "surface": "원천", "label": "NIL",
        "entity_id": None, "should_commit": False, "full_span": [0, 2], "full_identity": "SAME"}]
    (bundle / "annotator-a.jsonl").write_text("".join(json.dumps(row) + "\n" for row in first))
    with pytest.raises(ValueError, match="decisions"):
        seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")
    decision = {**first[0], "annotator": "adjudicator", "adjudication_note": "Fixture semantic judgment."}
    (bundle / "decisions.jsonl").write_text(json.dumps(decision) + "\n")
    assert seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")["semantic_disagreement_documents"] == 1


def test_seal_detects_annotation_drift_before_source_loading(tmp_path):
    bundle, _, _, _ = fixture_bundle(tmp_path)
    seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")
    (bundle / "annotator-b.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="input file changed"):
        verify_bundle(bundle, glossary=GLOSSARY, source=tmp_path / "not-needed")


@pytest.mark.parametrize("failure", ["offset", "prior_parent"])
def test_source_offsets_and_prior_parent_are_verified(tmp_path, monkeypatch, failure):
    from eval import hf_sources

    bundle, documents, _, _ = fixture_bundle(tmp_path)
    source = tmp_path / "source.parquet"
    source.write_bytes(b"fixture source")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    for document in documents:
        document["source_file_sha256"] = source_sha
    (bundle / "documents.jsonl").write_text("".join(json.dumps(row) + "\n" for row in documents))
    if failure == "prior_parent":
        (bundle / "exclusions.json").write_text(json.dumps({
            "prior_parents": [documents[0]["parent_document_id"]], "prior_content_hashes": []}))
    seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")
    originals = [{**doc, "document_id": doc["source_document_id"]} for doc in documents]
    monkeypatch.setattr(hf_sources, "load_tydi_records", lambda *a, **kw: (originals, []))
    if failure == "prior_parent":
        with pytest.raises(ValueError, match="prior document leakage"):
            verify_bundle(bundle, glossary=GLOSSARY, source=source)
        return
    verify_bundle(bundle, glossary=GLOSSARY, source=source)
    originals[0]["text"] = "shifted original source"
    with pytest.raises(ValueError, match="offset/provenance drift"):
        verify_bundle(bundle, glossary=GLOSSARY, source=source)


def test_aggregate_evaluation_retains_negative_docs_without_fake_coverage(tmp_path, monkeypatch):
    from eval import blind_document_followup as module
    import ktrf

    bundle, documents, first, second = fixture_bundle(tmp_path)
    seal_bundle(bundle, glossary=GLOSSARY, code_revision="fixture")
    manifest = json.loads((bundle / "manifest.json").read_text())
    gold = [json.loads(line) for line in (bundle / "gold.jsonl").read_text().splitlines()]
    monkeypatch.setattr(module, "verify_bundle", lambda *a, **kw: (manifest, documents, gold))
    monkeypatch.setattr(ktrf, "resolve", lambda *a, **kw: {"mentions": []})
    out = tmp_path / "evaluated"
    summary = evaluate(bundle, glossary=GLOSSARY, source=tmp_path / "unused",
                       code_revision="fixture", out_dir=out)
    assert summary["documents"] == summary["negative_documents"] == 24
    assert summary["calibration_fit_status"] == "INSUFFICIENT_DATA"
    assert summary["set_confidence"] is None and summary["coverage_valid"] is False
    assert summary["calibration_fit_performed"] is False
    serialized = json.dumps(summary)
    # No source text, annotation surfaces or per-document records in aggregates.
    assert not any(key in serialized for key in ("doc-0", "원천 문단", '"text"', '"surface"'))
    for mode in ("fast", "commit"):
        assert summary["modes"][mode]["partitions"]["test"]["documents"] == 8
        assert (out / f"{mode}-predictions.json").is_file()

import copy
import hashlib

import pytest

from eval.blind_gold import (adjudicate, annotation_packets, grouped_split,
                            seal_manifest, verify_manifest)
from eval.fixed_risk import AuditEvent, binomial_error_ucb, validate_thresholds
from eval import wild_data


def document(i, families=()):
    text = f"문서 {i}에서 금감원장을 언급했다."
    sha = hashlib.sha256(text.encode()).hexdigest()
    return {"document_id": str(i), "parent_document_id": str(i), "source_row_id": str(i),
            "dataset_revision": "revision-a", "collected_at": "2026-10-13T00:00:00Z",
            "document_sha256": sha, "text": text, "family_ids": list(families)}


def completed(doc, annotator):
    packet = annotation_packets([doc], annotator)[0]
    packet["complete"] = True
    start = packet["text"].index("금감원")
    packet["mentions"] = [{"span": [start, start + 3], "surface": "금감원", "label": "LINK",
                           "entity_id": "ORG_FSS", "should_commit": True,
                           "full_span": [start, start + 4], "full_identity": "DISTINCT"}]
    return packet


def test_blind_packets_exclude_predictions_and_require_provenance():
    doc = document(1)
    doc["resolver_predictions"] = [{"entity": "leaked"}]
    packet = annotation_packets([doc], "a")[0]
    assert "resolver_predictions" not in packet and packet["mentions"] == []
    doc["dataset_revision"] = None
    with pytest.raises(ValueError, match="provenance"):
        annotation_packets([doc], "a")


def test_adjudication_preserves_missed_mentions_and_requires_independent_people():
    first, second = completed(document(1), "a"), completed(document(1), "b")
    assert adjudicate(first, second)["mentions"] == first["mentions"]
    with pytest.raises(ValueError, match="independent"):
        adjudicate(first, first)
    second["mentions"] = []  # missed annotation must be explicitly adjudicated
    with pytest.raises(ValueError, match="adjudication"):
        adjudicate(first, second)
    decision = {**first, "annotator": "c", "adjudication_note": "Core names the institution; full expression names its head."}
    assert adjudicate(first, second, decision)["had_disagreement"]


def test_family_and_parent_components_are_order_invariant_and_sealed():
    docs = [document(1, ["A"]), document(2, ["A", "B"]), document(3, ["B"]), document(4)]
    docs[3]["parent_document_id"] = "3"
    split = grouped_split(docs)
    assert len(set(split.values())) == 1
    assert grouped_split(list(reversed(docs))) == split
    manifest = seal_manifest(docs, split, glossary_hash="glossary", seed="blind-v1",
                             code_revision="commit", protocol={"risk_limit": .01})
    verify_manifest(manifest, docs)
    changed = copy.deepcopy(docs)
    changed[0]["dataset_revision"] = "other"
    with pytest.raises(ValueError, match="provenance"):
        verify_manifest(manifest, changed)
    manifest["protocol"]["risk_limit"] = .9
    with pytest.raises(ValueError, match="seal"):
        verify_manifest(manifest, docs)


def test_wild_download_preserves_raw_document_and_offsets(monkeypatch, tmp_path):
    raw = "  첫 문장에는 금감원이 있다.  둘째 문장은 은행이다. "
    monkeypatch.setattr(wild_data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(wild_data, "CACHE", tmp_path / "corpus.jsonl")
    monkeypatch.setattr(wild_data, "DOCUMENTS", tmp_path / "documents.jsonl")
    monkeypatch.setattr(wild_data, "SOURCES", [("demo/data", "default", "train", "text", 1, True, 9, 0)])
    monkeypatch.setattr(wild_data, "_dataset_revision", lambda _: "immutable-sha")
    monkeypatch.setattr(wild_data, "_fetch_page", lambda *a: {"rows": [{"row_idx": 4, "row": {"id": "original", "text": raw}}]})
    monkeypatch.setattr(wild_data.time, "sleep", lambda _: None)
    from eval.blind_gold import load_jsonl
    rows = load_jsonl(wild_data.download(verbose=False))[1:]
    docs = load_jsonl(wild_data.DOCUMENTS)
    assert len(rows) == 2 and len(docs) == 1
    assert docs[0]["text"] == raw
    assert {r["source_row_id"] for r in rows} == {"original"}
    assert {r["document_id"] for r in rows} == {docs[0]["document_id"]}
    for row in rows:
        start, end = row["sentence_span"]
        assert raw[start:end] == row["text"]
        assert row["dataset_revision"] == "immutable-sha"


def test_exact_binomial_ucb_and_no_claim_on_small_sample():
    assert binomial_error_ucb(0, 0) == 1
    assert binomial_error_ucb(0, 100) == pytest.approx(1 - .05**.01)
    assert binomial_error_ucb(5, 100) > .05
    assert binomial_error_ucb(100, 100) == 1
    args = dict(thresholds=[.5, .8], groups=["exact"], epsilon=.05)
    events = [AuditEvent("d", "e", "exact", .9, False)]
    assert validate_thresholds(events, [], **args)["groups"]["exact"]["status"] == "INSUFFICIENT_DATA"


def test_risk_protocol_rejects_document_overlap_and_correlated_mentions():
    args = dict(thresholds=[.5], groups=["exact"], epsilon=.05)
    a = AuditEvent("d", "a", "exact", .9, False)
    b = AuditEvent("d", "b", "exact", .9, False)
    with pytest.raises(ValueError, match="disjoint"):
        validate_thresholds([a], [b], **args)
    with pytest.raises(ValueError, match="correlated"):
        validate_thresholds([a, b], [], **args)


def test_risk_selection_never_optimizes_on_test():
    tune = [AuditEvent(f"train-{i}", f"t{i}", "exact", .9, False) for i in range(500)]
    test = [AuditEvent(f"test-{i}", f"v{i}", "exact", .9, False) for i in range(500)]
    args = dict(thresholds=[.5, .8], groups=["exact", "dense"], epsilon=.05)
    safe = validate_thresholds(tune, test, **args)
    assert safe["groups"]["exact"]["status"] == "PASS"
    assert safe["groups"]["dense"]["status"] == "INSUFFICIENT_DATA"
    unsafe = validate_thresholds(tune, [AuditEvent(e.document_id, e.event_id, e.group, e.score, True) for e in test], **args)
    assert unsafe["groups"]["exact"]["selected_threshold"] == safe["groups"]["exact"]["selected_threshold"]
    assert unsafe["groups"]["exact"]["status"] == "FAIL"


def test_e2e_gold_counts_unretrieved_mentions_and_extra_commits():
    from eval.blind_gold import score_documents
    a, b = completed(document(1), "a"), completed(document(1), "b")
    gold = adjudicate(a, b)
    report = score_documents([gold], {"1": {"document_sha256": gold["document_sha256"], "mentions": []}})
    assert report["counts"]["linked_mentions"] == 1
    assert report["candidate_exact_link_recall"] == 0
    assert report["eligible_commit_recall"] == 0
    assert report["risk_status"] == "UNVALIDATED"
    prediction = {"span": {"codepoint": {"start": 0, "end": 2}}, "link_decision": "RESOLVED",
                  "resolved_entity": {"entity_id": "ORG_FSS"}}
    report = score_documents([gold], {"1": {"document_sha256": gold["document_sha256"], "mentions": [prediction]}})
    assert report["counts"]["commit_errors"] == 1
    assert report["commit_error_rate"] == 1


def test_cli_prepare_adjudicate_and_sealed_score(tmp_path):
    import json
    import subprocess
    import sys
    from eval.blind_gold import load_jsonl
    docs = [document(i) for i in range(20)]
    source = tmp_path / "source.jsonl"
    source.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs))
    glossary = tmp_path / "glossary.json"
    glossary.write_text("{}")
    protocol = tmp_path / "protocol.json"
    protocol.write_text('{"risk_limit": 0.05, "thresholds": [0.7, 0.8]}')
    out = tmp_path / "packets"
    def run(*args):
        subprocess.run([sys.executable, "-m", "eval.blind_gold", *args], check=True, capture_output=True)
    run("prepare", "--documents", str(source), "--out", str(out), "--count", "20",
        "--glossary", str(glossary), "--protocol", str(protocol), "--code-revision", "fixture")
    manifest = json.loads((out / "manifest.json").read_text())
    test_ids = {d["document_id"] for d in manifest["documents"] if d["partition"] == "test"}
    assert test_ids
    # Test fixtures represent completed annotations; they are not project gold.
    for name in ("annotator-a", "annotator-b"):
        packets = [completed(d, name) for d in docs if d["document_id"] in test_ids]
        (out / f"{name}.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in packets))
    gold = out / "gold.jsonl"
    run("adjudicate", "--first", str(out / "annotator-a.jsonl"), "--second", str(out / "annotator-b.jsonl"), "--out", str(gold))
    predicted = out / "predictions.jsonl"
    predicted.write_text("".join(json.dumps({"document_id": d["document_id"],
        "document_sha256": d["document_sha256"], "mentions": []}) + "\n" for d in docs if d["document_id"] in test_ids))
    report = out / "report.json"
    run("score", "--documents", str(out / "documents.jsonl"), "--manifest", str(out / "manifest.json"),
        "--gold", str(gold), "--predictions", str(predicted), "--out", str(report))
    result = json.loads(report.read_text())
    assert result["documents"] == len(test_ids)
    assert result["candidate_exact_link_recall"] == 0
    assert result["manifest_seal_sha256"] == manifest["seal_sha256"]


def test_external_ner_import_preserves_original_id_types_and_shared_parent():
    from eval.external_gold import import_ner_tsv
    sample = "## klue-ner-v1_train_00025_nsmc 이름\n금\tB-OG\n감\tI-OG\n원\tI-OG\n \tO\n장\tO\n"
    klue = import_ner_tsv(sample, source="klue", revision="sha-a", collected_at="now")[0]
    konec = import_ner_tsv(sample.replace("-OG", "-OG_FINANCE"), source="konec", revision="sha-b", collected_at="now")[0]
    assert klue["text"] == "금감원 장"
    assert klue["ner_annotations"] == [{"span": [0, 3], "type": "OG", "surface": "금감원"}]
    assert konec["ner_annotations"][0]["type"] == "OG_FINANCE"
    assert klue["parent_document_id"] == konec["parent_document_id"]
    split = grouped_split([klue, konec])
    assert split[klue["document_id"]] == split[konec["document_id"]]
    assert "ner_annotations" not in annotation_packets([klue], "a")[0]
    with pytest.raises(ValueError, match="BIO"):
        import_ner_tsv(sample.replace("B-OG", "I-OG"), source="klue", revision="sha-a", collected_at="now")


def test_wild_changed_revision_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(wild_data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(wild_data, "CACHE", tmp_path / "corpus.jsonl")
    monkeypatch.setattr(wild_data, "DOCUMENTS", tmp_path / "documents.jsonl")
    monkeypatch.setattr(wild_data, "SOURCES", [("demo/data", "default", "train", "text", 1, False, 1, 0)])
    revisions = iter(["before", "after"])
    monkeypatch.setattr(wild_data, "_dataset_revision", lambda _: next(revisions))
    monkeypatch.setattr(wild_data, "_fetch_page", lambda *a: {"rows": [{"row": {"text": "금감원장이 인터뷰에 참여했다."}}]})
    monkeypatch.setattr(wild_data.time, "sleep", lambda _: None)
    with pytest.raises(wild_data.WildDataUnavailable, match="revision changed"):
        wild_data.download(verbose=False)
    assert not wild_data.CACHE.exists()


def test_koneobench_import_filters_formations_and_tracks_component_families():
    import csv
    import io
    from eval.external_gold import import_koneobench_csv
    stream = io.StringIO()
    fields = ["IDX", "단어 형성법", "정답 (표제어)", "형태소 분석", "용례 (표제어 [MASK])", "뜻풀이", "수집 연도"]
    writer = csv.DictWriter(stream, fields)
    writer.writeheader()
    for i, formation in enumerate(["축약", "혼성", "파생"]):
        writer.writerow(dict(zip(fields, [str(i), formation, "신어", "공통+원형", "실제 [MASK] 용례", "시험 정의", "2026"])))
    docs = import_koneobench_csv(stream.getvalue(), revision="sha", collected_at="now")
    assert len(docs) == 2
    assert docs[0]["text"] == "실제 신어 용례"
    assert docs[0]["transformation"] == "replace_MASK_with_gold_headword"
    assert docs[0]["linking_gold_status"] == "UNANNOTATED"
    split = grouped_split(docs)
    assert len(set(split.values())) == 1


def test_ner_import_records_empty_headers_as_exclusions():
    from eval.external_gold import import_ner_tsv
    rows = import_ner_tsv("## empty ignored\n\n## valid text\n가\tO\n", source="konec", revision="sha", collected_at="now")
    assert len(rows) == 1 and rows[0]["text"] == "가"
    assert rows[0]["import_exclusions"] == {"empty_source_sentence_ids": ["empty"]}


def test_fixed_risk_declared_budget_covers_both_tails_and_stages():
    from eval.fixed_risk import validate_thresholds
    result = validate_thresholds([], [], thresholds=[.5, .9], groups=['exact', 'fuzzy'], epsilon=.1)
    total_tail_budget = (result['tune_alpha_per_hypothesis'] * 2 * 2 * 2
                         + result['test_alpha_per_group'] * 2 * 2)
    assert total_tail_budget == result['familywise_alpha']

"""Private-source integrity and no-action shadow replay contracts."""
import hashlib
import json
from pathlib import Path

import pytest

from eval.shadow_routing import load_shadow_documents, prepare_shadow


GLOSSARY = Path(__file__).resolve().parents[1] / "examples/demo_glossary.yaml"


def source(tmp_path, rows):
    path = tmp_path / "documents.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return path


def row(document_id="d1", family_id="f1", text="한전KDN은 계획을 발표했다.", **extra):
    return dict(document_id=document_id, family_id=family_id, text=text, **extra)


def test_blind_packet_is_source_first_and_preserves_exact_input(tmp_path, monkeypatch):
    import ktrf.resolver
    monkeypatch.setattr(ktrf.resolver, "resolve",
                        lambda *args, **kwargs: pytest.fail("resolver ran before annotation packet"))
    original = row(text="  한전KDN은\r\n계획을 발표했다.  ", source_revision="rev-1",
                   source_row_id="source:7", proposed_entity_id="must-not-enter-blind-packet",
                   annotations=[{"label": "LINK"}])
    path = source(tmp_path, [original])
    out = tmp_path / "export"
    manifest = prepare_shadow(path, GLOSSARY, out)
    packet = json.loads((out / "blind_annotation.json").read_text())
    assert packet["resolver_output_visible"] is False
    assert packet["human_verified"] is False
    assert packet["documents"][0]["text"] == original["text"]
    assert packet["documents"][0]["annotations"] == []
    assert "proposed_entity_id" not in packet["documents"][0]
    assert packet["documents"][0]["source_revision"] == "rev-1"
    assert packet["documents"][0]["source_row_id"] == "source:7"
    assert (out / "source.jsonl").read_bytes() == path.read_bytes()
    assert manifest["resolver_calls"] == manifest["actions_performed"] == 0
    assert manifest["semantic_accuracy"] is None
    for filename, digest in manifest["files"].items():
        assert hashlib.sha256((out / filename).read_bytes()).hexdigest() == digest
        assert (out / filename).stat().st_mode & 0o777 == 0o600
    assert out.stat().st_mode & 0o777 == 0o700


def test_source_components_are_transitive_and_order_invariant(tmp_path):
    rows = [
        row("a", "first", "첫 문서", event_id="event-1"),
        row("b", "second", "둘째 문서", event_id="event-1"),
        row("c", "second", "셋째 문서"),
        row("d", "fourth", "넷째 문서", parent_document_id="c"),
        row("e", "fifth", "다섯째 문서"),
    ]
    documents, _ = load_shadow_documents(source(tmp_path, rows))
    ids = {r["document_id"]: r["source_component_id"] for r in documents}
    assert len(set(ids.values())) == 2
    assert ids["a"] == ids["b"] == ids["c"] == ids["d"] != ids["e"]
    reversed_documents, _ = load_shadow_documents(source(tmp_path, list(reversed(rows))))
    assert ids == {r["document_id"]: r["source_component_id"] for r in reversed_documents}


@pytest.mark.parametrize("rows,match", [
    ([row(), row(text="다른 문서")], "duplicate document_id"),
    ([row(), row(document_id="d2")], "duplicate source text"),
    ([row(document_sha256="0" * 64)], "does not match"),
    ([row("a", "family", "첫 문서", partition="development"),
      row("b", "family", "둘째 문서", partition="audit")], "crosses"),
    ([row(partition="unknown")], "partition"),
    ([row(family_id="")], "requires family_id"),
])
def test_duplicate_tampered_or_partition_leaking_sources_fail(tmp_path, rows, match):
    with pytest.raises(ValueError, match=match):
        load_shadow_documents(source(tmp_path, rows))


def test_shadow_replay_never_executes_or_fills_gold(tmp_path):
    path = source(tmp_path, [row(origin="AI_AUTHORED", human_verified=True)])
    out = tmp_path / "replay"
    manifest = prepare_shadow(path, GLOSSARY, out, replay=True, repeats=1)
    proposal = json.loads((out / "shadow_proposals.jsonl").read_text())
    assert proposal["resolver_response"]["mentions"]
    assert proposal["execution_enabled"] is False and proposal["action_performed"] is False
    assert proposal["semantic_correctness"] is None
    assert manifest["resolver_calls"] == 2
    assert manifest["actions_performed"] == 0 and not manifest["human_verified"]
    assert manifest["source_origin_counts"] == {"AI_AUTHORED": 1}
    assert manifest["real_business_pilot_status"] == "NOT_ACTUAL_BUSINESS_INPUT"
    assert manifest["actual_business_data_verified"] is False
    packet = json.loads((out / "blind_annotation.json").read_text())
    assert packet["documents"][0]["annotations"] == []
    assert packet["documents"][0]["human_verified"] is False
    assert packet["documents"][0]["source_origin"] == "AI_AUTHORED"
    timing = json.loads((out / "resolver_latency.json").read_text())
    assert timing["scope"] == "in_process_symbolic_resolve_only"
    assert timing["llm_included"] is False and timing["human_review_time_ms"] is None
    assert timing["independent_samples"] is False
    summary = json.loads((out / "summary.json").read_text())
    assert summary["publication"] == "AGGREGATE_ONLY_NO_SOURCE_TEXT_OR_INDIVIDUAL_TIMINGS"
    assert summary["latency"]["repeat_call_ms"]["observations"] == 1
    assert summary["latency"]["repeat_call_ms"]["p95"] >= 0
    assert summary["real_business_pilot_status"] == "NOT_ACTUAL_BUSINESS_INPUT"
    assert "한전KDN" not in (out / "summary.json").read_text()
    assert "document_id" not in summary and "machine" not in summary
    with pytest.raises(FileExistsError):
        prepare_shadow(path, GLOSSARY, out)


def test_bounded_work_and_no_implicit_source_truncation(tmp_path):
    path = source(tmp_path, [row(), row("d2", "f2", "별도의 문서")])
    with pytest.raises(ValueError, match="document limit"):
        prepare_shadow(path, GLOSSARY, tmp_path / "too-many", max_documents=1)
    with pytest.raises(ValueError, match="repeats"):
        prepare_shadow(path, GLOSSARY, tmp_path / "too-many-repeats", repeats=100)
    path = source(tmp_path, [row(text="긴 문서" * 30000)])
    with pytest.raises(ValueError, match="no automatic text truncation"):
        prepare_shadow(path, GLOSSARY, tmp_path / "too-large")


def test_confirmation_partition_remains_separate_from_development(tmp_path):
    rows = [row("dev", "family-dev", "개발 문서", partition="development"),
            row("confirm", "family-confirm", "확인 문서", partition="confirmation")]
    documents, _ = load_shadow_documents(source(tmp_path, rows))
    assert {r["partition"] for r in documents} == {"development", "confirmation"}
    rows[1]["event_id"] = rows[0]["event_id"] = "shared-event"
    with pytest.raises(ValueError, match="crosses"):
        load_shadow_documents(source(tmp_path, rows))

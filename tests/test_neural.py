"""M4 tests: bi-encoder dense retrieval (§22.3), conditional cross-encoder
(§22.4), learned fusion (§23), artifact compatibility (§11.3).

Runs entirely on the pure-Python HashEncoder / LexicalCrossEncoder backends
(the ONNX e5 path shares every integration point and is exercised by
eval/run_neural_eval.py when the model directory exists).
"""

import pytest

from ktrf.artifacts import finetune, load_snapshot, save_snapshot
from ktrf.corrections import CorrectionStore
from ktrf.dense import VectorIndex, entity_profile_text
from ktrf.encoders import HashEncoder, load_encoder
from ktrf.errors import KtrfApiError
from ktrf.fusion import FEATURE_NAMES, FusionModel, fit_fusion
from ktrf.glossary import load_glossary
from ktrf.rerank import LexicalCrossEncoder
from ktrf.resolver import resolve
from ktrf.snapshot import RuntimePolicy, compile_snapshot


def _glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_KEPCO", "canonical": "한국전력공사",
             "description": "대한민국의 전력 공기업"},
            {"entity_id": "E_AP_NET", "canonical": "Access Point",
             "description": "무선 단말을 유선 네트워크에 연결하는 네트워크 장비",
             "domain_ids": ["NETWORK"]},
            {"entity_id": "E_AP_WF", "canonical": "Approval Process",
             "description": "결재 승인 업무 절차", "domain_ids": ["WORKFLOW"]},
            {"entity_id": "E_DATA", "canonical": "데이터관리시스템",
             "description": "사내 데이터 자산을 관리하는 시스템"},
        ],
        "alias_families": [
            {"family_id": "F_K", "representative": "한전",
             "normalization_profile": "korean_org_name"},
            {"family_id": "F_AP", "representative": "AP",
             "normalization_profile": "latin_acronym"},
        ],
        "alias_bindings": [
            {"alias_id": "A_K", "family_id": "F_K", "entity_id": "E_KEPCO",
             "surface": "한전"},
            {"alias_id": "A_AP1", "family_id": "F_AP", "entity_id": "E_AP_NET",
             "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
            {"alias_id": "A_AP2", "family_id": "F_AP", "entity_id": "E_AP_WF",
             "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
        ],
    })


@pytest.fixture(scope="module")
def dense_snap():
    return compile_snapshot(_glossary(), encoder=HashEncoder(),
                            reranker=LexicalCrossEncoder())


# ---------------------------------------------------------------------------
# encoders + index
# ---------------------------------------------------------------------------


def test_hash_encoder_deterministic_normalized():
    e = HashEncoder()
    a = e.encode_query("한국전력공사")
    assert a == e.encode_query("한국전력공사")
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    assert e.encode_passages(["한전"]) != e.encode_passages(["과기부"])


def test_vector_index_top1():
    e = HashEncoder()
    texts = ["한국전력공사 전력 공기업", "과학기술정보통신부 행정기관", "품질 관리 시스템"]
    idx = VectorIndex(["A", "B", "C"], e.encode_passages(texts))
    hits = idx.search(e.encode_query("전력공사 관련"), top_k=2)
    assert hits[0][0] == "A"
    assert hits[0][1] >= hits[1][1]


def test_load_encoder_specs():
    assert load_encoder(None) is None
    assert load_encoder("hash").dim == 256
    assert load_encoder("hash:64").dim == 64
    with pytest.raises(ValueError):
        load_encoder("bogus")


# ---------------------------------------------------------------------------
# compile + manifest (§11.2)
# ---------------------------------------------------------------------------


def test_manifest_dense_fields(dense_snap):
    m = dense_snap.manifest
    assert m["entity_encoder_hash"].startswith("hash-jamo-ngram")
    assert m["vector_dimension"] == 256
    assert m["index_type"] == "flat_ip"
    assert m["reranker_id"] == "lexical-xenc-v1"


def test_level_a_only_manifest_nulls():
    snap = compile_snapshot(_glossary())
    assert snap.manifest["entity_encoder_hash"] is None
    assert snap.dense is None


# ---------------------------------------------------------------------------
# dense Pass 2 in the resolver (§21.6)
# ---------------------------------------------------------------------------


def test_dense_enriches_low_confidence_mentions(dense_snap):
    # AP is multi-sense -> low top marginal -> Pass 2 dense evidence lands
    resp = resolve(dense_snap, "AP 확인 요청드립니다.", mode="commit",
                   options={"return_trace": True})
    ap = resp["mentions"][0]
    assert resp["trace"]["pass2_executed"]
    assert resp["trace"]["dense_queries"] >= 1
    channels = {ch for x in ap["prediction_set"]["members"]
                for ch in x.get("generation_channels", [])}
    assert "dense" in channels
    # INV-004/INV-010: both exact senses still present
    ids = {x.get("entity_id") for x in ap["prediction_set"]["members"]}
    assert {"E_AP_NET", "E_AP_WF"} <= ids


def test_open_world_dense_behind_flag(dense_snap):
    # §19.1: unregistered-span proposals only with the feature flag
    text = "데이터관리 업무를 개선한다."
    off = resolve(dense_snap, text, mode="commit",
                  options={"return_all_mentions": True})
    on = resolve(dense_snap, text, mode="commit",
                 options={"return_all_mentions": True,
                          "detect_unregistered_mentions": True})
    assert len(on["mentions"]) >= len(off["mentions"])


def test_fast_mode_never_dense(dense_snap):
    # REQ-CAND-005 / REQ-API-001
    resp = resolve(dense_snap, "AP 확인. 데이터관리 개선.", mode="fast",
                   options={"return_all_mentions": True,
                            "return_trace": True})
    assert resp["trace"]["pass2_executed"] is False
    for m in resp["mentions"]:
        for x in m.get("prediction_set", {}).get("members", []):
            assert "dense" not in x.get("generation_channels", [])


def test_dense_query_budget_degrades(dense_snap):
    import dataclasses

    tight = dataclasses.replace(dense_snap, policy=RuntimePolicy(
        max_dense_queries_per_request=0))
    resp = resolve(tight, "AP 확인 요청", mode="commit",
                   options={"return_trace": True})
    assert "dense_query_budget" in resp["trace"]["drops"]
    assert resp["degraded"] is True  # INV-013


# ---------------------------------------------------------------------------
# cross-encoder rerank (§22.4)
# ---------------------------------------------------------------------------


def test_rerank_conditional_and_bounded(dense_snap):
    resp = resolve(dense_snap, "AP 결재 부탁드립니다.", mode="commit",
                   options={"return_trace": True})
    ap = resp["mentions"][0]
    pairs = resp["trace"]["cross_encoder_pairs"]
    assert 0 < pairs <= dense_snap.policy.max_cross_encoder_pairs
    # 결재-context should rank the approval sense first
    top = ap["prediction_set"]["members"][0]
    assert top["entity_id"] == "E_AP_WF"


def test_rerank_pair_budget(dense_snap):
    import dataclasses

    tight = dataclasses.replace(dense_snap, policy=RuntimePolicy(
        max_cross_encoder_pairs=0, max_dense_queries_per_request=0))
    resp = resolve(tight, "AP 결재 부탁드립니다.", mode="commit",
                   options={"return_trace": True})
    assert "cross_encoder_budget" in resp["trace"]["drops"]
    assert resp["degraded"] is True


def test_entity_profile_text():
    g = _glossary()
    assert "결재 승인" in entity_profile_text(g.entity("E_AP_WF"))


# ---------------------------------------------------------------------------
# learned fusion (§23)
# ---------------------------------------------------------------------------


def _rows(n=60):
    rows = []
    for i in range(n):
        pos = {"exact_score": 0.9 + 0.001 * i, "context_overlap": 0.1,
               "is_exact": 1.0, "single_sense": 0.5, "xenc": 0.7}
        neg = {"exact_score": 0.9, "context_overlap": 0.0,
               "is_exact": 1.0, "single_sense": 0.5, "xenc": 0.3}
        rows.append((pos, 1))
        rows.append((neg, 0))
    return rows


def test_fit_fusion_learns_signal():
    model = fit_fusion(_rows())
    hi = model.predict({"exact_score": 0.9, "context_overlap": 0.1,
                        "is_exact": 1.0, "single_sense": 0.5, "xenc": 0.7})
    lo = model.predict({"exact_score": 0.9, "context_overlap": 0.0,
                        "is_exact": 1.0, "single_sense": 0.5, "xenc": 0.3})
    assert hi > lo


def test_fusion_schema_mismatch_rejected():
    m = fit_fusion(_rows())
    d = m.to_dict()
    d["feature_names"] = ["something_else"]
    with pytest.raises(ValueError):
        FusionModel.from_dict(d)
    assert FEATURE_NAMES == m.to_dict()["feature_names"]


def test_fusion_used_by_resolver(dense_snap):
    import dataclasses

    model = fit_fusion(_rows())
    fused = dataclasses.replace(dense_snap, fusion=model)
    resp = resolve(fused, "한전에서 회의했다.", mode="commit")
    member = resp["mentions"][0]["prediction_set"]["members"][0]
    # ranking_score is the fusion logistic output (0..1 scale)
    assert 0.0 <= member["ranking_score"] <= 1.0
    assert member["calibrated_probability"] <= 0.95  # conservative cap


# ---------------------------------------------------------------------------
# artifact roundtrip + compatibility (§11.3, INV-015)
# ---------------------------------------------------------------------------


def test_bundle_roundtrip_with_dense(dense_snap, tmp_path):
    bundle = save_snapshot(dense_snap, tmp_path / "b")
    loaded = load_snapshot(bundle, encoder=HashEncoder(),
                           reranker=LexicalCrossEncoder())
    assert loaded.dense is not None
    text = "AP 결재 요청과 한전 회의"
    assert resolve(loaded, text, mode="commit") == \
        resolve(dense_snap, text, mode="commit")


def test_bundle_refuses_encoder_mismatch(dense_snap, tmp_path):
    bundle = save_snapshot(dense_snap, tmp_path / "b")
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(bundle, encoder=HashEncoder(dim=64),
                      reranker=LexicalCrossEncoder())
    assert "encoder mismatch" in e.value.message
    with pytest.raises(KtrfApiError):
        load_snapshot(bundle, reranker=LexicalCrossEncoder())  # encoder 필요


def test_finetune_with_fusion(dense_snap):
    store = CorrectionStore()
    texts_gold = [("무선 AP 장애가 발생했다.", "E_AP_NET"),
                  ("AP 결재 부탁드립니다.", "E_AP_WF")] * 15
    for i, (text, gold) in enumerate(texts_gold):
        resp = resolve(dense_snap, text, mode="commit",
                       options={"return_features": True})
        mention = next(m for m in resp["mentions"] if m["surface"] == "AP")
        c = store.submit(
            tenant_id=dense_snap.tenant_id,
            request_ref={"snapshot_id": resp["snapshot"]["snapshot_id"],
                         "request_id": f"r{i}", "mention_id":
                             mention["mention_id"]},
            correction_type="WRONG_ENTITY",
            corrected={"entity_id": gold},
            verifier={"kind": "REVIEWER", "principal_ref": f"rev{i % 3}"},
            mention_state=mention,
        )
        store.review(dense_snap.tenant_id, c.correction_id, "ACCEPTED",
                     reviewer="adm")
    tuned = finetune(dense_snap, store, alpha=0.1, n_min=20,
                     fit_fusion_model=True)
    assert tuned.fusion is not None
    assert tuned.manifest["fusion_hash"] is not None
    assert dense_snap.fusion is None  # input untouched
    # fused+calibrated resolver separates the senses by context
    resp = resolve(tuned, "무선 AP 장애 확인", mode="commit")
    ap = resp["mentions"][0]
    ids = [x["entity_id"] for x in ap["prediction_set"]["members"]
           if x.get("kind") == "ENTITY"]
    assert "E_AP_NET" in ids

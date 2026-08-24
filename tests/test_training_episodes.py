"""Episode builder tests (§36, §40.5) — pure-Python part of the G2 scaffold.

torch/transformers are training-only dependencies; these tests cover the
data path that feeds them.
"""

from ktrf.glossary import load_glossary

from training.episodes import episodes_from_corrections, episodes_from_silver


def _glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_NET", "canonical": "Access Point",
             "description": "네트워크 장비", "domain_ids": ["NETWORK"]},
            {"entity_id": "E_WF", "canonical": "Approval Process",
             "description": "결재 절차", "domain_ids": ["WORKFLOW"]},
            {"entity_id": "E_QMS", "canonical": "품질관리시스템",
             "description": "품질 관리", "domain_ids": ["QUALITY"]},
        ],
        "alias_families": [
            {"family_id": "F", "representative": "AP",
             "normalization_profile": "latin_acronym"}],
        "alias_bindings": [
            {"alias_id": "A1", "family_id": "F", "entity_id": "E_NET",
             "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}}],
    })


def test_correction_episodes_same_surface_hard_negatives():
    g = _glossary()
    accepted = [{
        "correction_type": "WRONG_ENTITY",
        "corrected": {"entity_id": "E_WF"},
        "evidence_text": "AP 결재 부탁드립니다",
        "request_ref": {},
        "mention_state": {"prediction_set": {"members": [
            {"kind": "ENTITY", "entity_id": "E_NET"},
            {"kind": "ENTITY", "entity_id": "E_WF"},
        ]}},
    }]
    eps = episodes_from_corrections(accepted, g)
    labels = {(e.label, "Approval" in e.profile) for e in eps}
    # gold -> positive; same-surface competitor -> hard negative (§40.5)
    assert (1, True) in labels
    assert (0, False) in labels
    assert all(e.context == "AP 결재 부탁드립니다" for e in eps)


def test_correction_without_context_skipped():
    # §30.2: no raw text stored by default and no resolver -> no episode
    g = _glossary()
    accepted = [{"correction_type": "WRONG_ENTITY",
                 "corrected": {"entity_id": "E_WF"}, "request_ref": {},
                 "mention_state": {"prediction_set": {"members": [
                     {"kind": "ENTITY", "entity_id": "E_WF"}]}}}]
    assert episodes_from_corrections(accepted, g) == []


def test_silver_episodes_deterministic():
    g = load_glossary("examples/realorg_glossary.yaml")
    corpus = [{"text": "과기정통부에서 관련 계획을 발표했다."},
              {"text": "금감원이 검사에 착수했다."}]
    a = episodes_from_silver(g, corpus)
    b = episodes_from_silver(g, corpus)
    assert [vars(e) for e in a] == [vars(e) for e in b]  # seeded
    positives = [e for e in a if e.label == 1]
    assert len(positives) == 2
    assert all(e.label == 0 for e in a if e not in positives)
    # 3 negatives per positive (§36.3 sampling)
    assert len(a) == 2 * (1 + 3)

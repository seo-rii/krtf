"""Candidate pool invariants (§21) and injection escaping (§49.2).

INV-004, INV-005, INV-010, REQ-SEC-001.
"""

from ktrf.candidates import Candidate, CandidateBudget, CandidatePool
from ktrf.glossary import load_glossary
from ktrf.injection import render_resolved_terms


def _cand(eid, is_exact, channel="exact", score=1.0):
    return Candidate(entity_id=eid, alias_id=f"A_{eid}", family_id="F",
                     generation_channels={channel},
                     channel_scores={channel: score}, is_exact=is_exact)


def test_fuzzy_never_displaces_exact():
    # INV-010: fuzzy evidence merges into the exact candidate, never replaces
    pool = CandidatePool(CandidateBudget())
    pool.add(_cand("E1", True))
    pool.add(_cand("E1", False, "jamo", 0.5))
    assert list(pool.exact) == ["E1"]
    assert not pool.non_exact
    c = pool.exact["E1"]
    assert c.generation_channels == {"exact", "jamo"}
    assert c.is_exact


def test_exact_promotion():
    pool = CandidatePool(CandidateBudget())
    pool.add(_cand("E1", False, "jamo", 0.5))
    pool.add(_cand("E1", True))
    assert list(pool.exact) == ["E1"] and not pool.non_exact


def test_budget_never_cuts_exact():
    # INV-005: exact pool ignores max_non_exact_candidates entirely
    pool = CandidatePool(CandidateBudget(max_non_exact_candidates=1))
    for i in range(10):
        pool.add(_cand(f"EX{i}", True))
    for i in range(5):
        pool.add(_cand(f"NX{i}", False, "jamo", 0.4))
    assert len(pool.exact) == 10
    assert len(pool.non_exact) == 1
    assert pool.truncated  # surfaced as degraded (INV-013)


def test_injection_escaping():
    # REQ-SEC-001: attribute values escaped, description truncated
    g = load_glossary({
        "glossary_id": "g", "version": "1", "schema_version": "3",
        "entities": [{
            "entity_id": "E1", "canonical": 'Evil "Corp" <script>',
            "description": '"/><injected attr="x' + "긴설명" * 200,
        }],
        "alias_families": [{"family_id": "F", "representative": "EC",
                            "normalization_profile": "latin_acronym"}],
        "alias_bindings": [{"alias_id": "A1", "family_id": "F",
                            "entity_id": "E1", "surface": "EC",
                            "boundary_policy": {"left": "latin_token_boundary"}}],
    })
    response = {
        "snapshot": {"glossary_id": "g", "glossary_version": "1"},
        "mentions": [{
            "surface": "EC", "link_decision": "RESOLVED",
            "resolved_entity": {"entity_id": "E1",
                                "calibrated_probability": 0.9},
        }],
    }
    xml = render_resolved_terms(response, g)
    assert "<script>" not in xml
    assert "<injected" not in xml
    assert "&lt;script&gt;" in xml or "&lt;script&gt;" in xml.replace('"', "")
    assert "CDATA" not in xml
    # description capped at 200 chars before escaping
    assert xml.count("긴설명") <= 70

"""Precision over partly-labelled documents is a ceiling, not a measurement.

The scorer used to drop any RESOLVED commit that landed outside a gold span on
a positive document, on the grounds that the annotation there was partial
(§38.1 UNLABELED). Dropping is not neutral: a commit that is dropped is a
commit that cannot lower precision, so the reported figure was the best case
and was published as though it were the measurement.

Two things close that. Documents whose annotation is verified to cover the
whole text score an extra commit as the false positive it is; documents where
it cannot be verified report the commit as unjudged, and the release gate
refuses to pass while any commit is unjudged.
"""

import pytest

from eval.datagen import (
    EvalExample,
    GoldMention,
    _catalog_keys,
    mark_exhaustive,
    verify_exhaustive,
)
from eval.run_eval import RELEASE_GATE, compute_gate
from eval.metrics import Metric
from ktrf.glossary import load_glossary

GLOSSARY = "examples/realorg_glossary.yaml"


@pytest.fixture(scope="module")
def glossary():
    return load_glossary(GLOSSARY)


@pytest.fixture(scope="module")
def catalog(glossary):
    return _catalog_keys(glossary)


def _alias(glossary):
    return glossary.alias_bindings[0].surface


# ------------------------------------------------------------- verification

def test_a_clean_filler_verifies_as_exhaustive(glossary, catalog):
    surface = _alias(glossary)
    text = f"{surface} 관련 회의를 진행했다."
    ex = EvalExample(text, "s", "A",
                     [GoldMention((0, len(surface)), "E", surface)])
    assert verify_exhaustive(ex, catalog) is True


def test_an_unannotated_alias_in_the_filler_blocks_the_claim(glossary, catalog):
    a, b = (glossary.alias_bindings[0].surface,
            glossary.alias_bindings[1].surface)
    if a == b:
        pytest.skip("need two distinct aliases")
    # the second alias is present and not annotated, so a commit made there
    # cannot be judged and this document must not claim to be exhaustive
    text = f"{a} 관련 {b} 회의를 진행했다."
    ex = EvalExample(text, "s", "A", [GoldMention((0, len(a)), "E", a)])
    assert verify_exhaustive(ex, catalog) is False


def test_verification_is_not_fooled_by_a_match_spanning_a_cut(glossary,
                                                              catalog):
    # the annotated span is removed before scanning, and a newline is left in
    # its place, so no substring can form across the cut and be counted
    surface = _alias(glossary)
    text = f"{surface}{surface} 보고."
    ex = EvalExample(text, "s", "A",
                     [GoldMention((0, len(surface)), "E", surface)])
    # the SECOND occurrence really is unannotated, so this is not exhaustive
    assert verify_exhaustive(ex, catalog) is False


def test_marking_a_corpus_reports_how_many_it_could_verify(glossary):
    surface = _alias(glossary)
    good = EvalExample(f"{surface} 관련 회의를 진행했다.", "s", "A",
                       [GoldMention((0, len(surface)), "E", surface)])
    bad = EvalExample(f"{surface} 관련 회의를 진행했다.", "s", "A", [])
    n = mark_exhaustive([good, bad], glossary)
    assert n == 1
    assert good.exhaustive is True
    assert bad.exhaustive is False


def test_the_generated_corpus_is_mostly_but_not_wholly_verifiable(glossary):
    from eval.datagen import generate

    examples = generate(glossary)
    share = sum(1 for e in examples if e.exhaustive) / len(examples)
    # the embedded-negative slices plant an alias inside a longer token, which
    # is deliberately left unverifiable rather than assumed away
    assert 0.5 < share < 1.0


# -------------------------------------------------------------- the gate

def _gate(**over):
    args = dict(
        conformance_failures=0,
        golden_violations=0,
        recall_metric=Metric("r", "E2E", 300, 300),
        in_set_metric=Metric("i", "|mention", 300, 300),
        resolved_correct=300,
        resolved_total=300,
        forbidden_entity_hits=0,
        offset_invariant_failures=0,
        unlabeled_commits=0,
        exhaustive_documents=100,
        total_documents=100,
    )
    args.update(over)
    return compute_gate(**args)


def test_a_gate_with_every_commit_judged_can_pass():
    gate = _gate()
    assert gate["checks"]["precision_is_measurable"] is True
    assert gate["values"]["resolved_precision_is_upper_bound"] is False
    assert gate["pass"] is True


def test_one_unjudged_commit_fails_the_gate():
    gate = _gate(unlabeled_commits=1, exhaustive_documents=99)
    assert gate["checks"]["precision_is_measurable"] is False
    assert gate["pass"] is False


def test_an_unjudged_commit_marks_precision_as_an_upper_bound():
    gate = _gate(unlabeled_commits=4, exhaustive_documents=96)
    assert gate["values"]["resolved_precision_is_upper_bound"] is True
    # the precision itself is still reported — the point is to label it, not
    # to withhold it
    assert gate["values"]["resolved_precision_commit"] == 1.0


def test_annotation_coverage_is_reported():
    gate = _gate(exhaustive_documents=96, total_documents=120)
    assert gate["values"]["exhaustive_document_share"] == 0.8


def test_the_criterion_is_on_the_data_not_the_resolver():
    # zero is the only defensible bar: an unjudged commit is missing evidence,
    # and a tolerance would be a licence to leave some of it missing
    assert RELEASE_GATE["unlabeled_commits_max"] == 0

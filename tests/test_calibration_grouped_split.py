"""The split has to separate correlated rows, not just distinct rows.

Split conformal needs the Platt fold and the conformal fold to be disjoint
*and* independent. Disjointness is easy and was already enforced. Independence
is the part a row-index split silently fails: the same document, the same
entity and the same alias family put near-identical rows on both sides, so the
quantile is measured on data the probability map has effectively already seen.

These tests pin the group split, the fact that a row split still reports
itself as one, and the boundary the four-way split draws around the locked
evaluation fold.
"""

import pytest

from ktrf.calibration import (
    DEFAULT_SHARES,
    FOLDS,
    LINK_DIMS,
    TrainingExample,
    TunedCalibrator,
    cluster_components,
    fit_calibrator,
    fit_calibrator_from_folds,
    holdout_by,
    split_examples,
)


def _ex(score, label, group="exact|multi", **groups):
    return TrainingExample(ranking_score=score, group=group, label=label,
                           groups=groups)


def _corpus(n_docs=12, per_doc=4):
    """n_docs documents, each contributing several correlated rows."""
    out = []
    for d in range(n_docs):
        for k in range(per_doc):
            out.append(_ex(0.9 - 0.01 * k, int(k == 0),
                           document=f"doc{d}", entity=f"E{d}",
                           alias_family=f"fam{d}"))
    return out


def _fold_of(report, row):
    return next(f for f, rows in report.folds.items() if row in rows)


# --------------------------------------------------------------- clustering

def test_a_documents_rows_never_straddle_two_folds():
    examples = _corpus()
    report = split_examples(examples)
    for doc in {e.groups["document"] for e in examples}:
        folds = {_fold_of(report, i) for i, e in enumerate(examples)
                 if e.groups["document"] == doc}
        assert len(folds) == 1, f"{doc} was cut across {folds}"


def test_correlation_is_transitive_across_dimensions():
    # A-B share a document, B-C share an entity. A and C have nothing directly
    # in common, but they are still correlated and must not be separated.
    examples = [
        _ex(0.9, 1, document="d1", entity="E1"),
        _ex(0.8, 0, document="d1", entity="E2"),
        _ex(0.7, 0, document="d2", entity="E2"),
    ]
    comps = cluster_components(examples)
    assert comps[0] == comps[1] == comps[2]


def test_tenant_is_not_a_link_dimension():
    # Every row of a tenant shares its tenant id. Linking on it would collapse
    # the tenant into one component and make any split impossible — the review
    # lists tenant alongside document, but it belongs on a different axis.
    assert "tenant" not in LINK_DIMS
    examples = [_ex(0.9, 1, tenant="t1", document=f"d{i}") for i in range(8)]
    report = split_examples(examples)
    assert report.n_components == 8


def test_a_giant_component_is_reported_not_hidden():
    # One entity running through every document links the whole corpus. The
    # split is then not a split, and the caller has to be able to see that.
    examples = [_ex(0.9, 1, document=f"d{i}", entity="E_SHARED")
                for i in range(20)]
    report = split_examples(examples)
    assert report.n_components == 1
    assert report.largest_component_share == 1.0


# ------------------------------------------------------------- the four folds

def test_the_four_way_split_covers_every_row_exactly_once():
    examples = _corpus(n_docs=40)
    report = split_examples(examples)
    assert set(report.folds) == set(FOLDS)
    seen = [i for rows in report.folds.values() for i in rows]
    assert sorted(seen) == list(range(len(examples)))


def test_the_locked_fold_is_not_touched_by_the_fit():
    examples = _corpus(n_docs=40)
    report = split_examples(examples)
    locked = set(report.folds["test"])
    assert locked, "a locked evaluation fold that is empty locks nothing"
    # the fit is handed two folds by name; the locked rows are not among them
    used = set(report.folds["platt"]) | set(report.folds["conformal"])
    assert not (used & locked)


def test_shares_are_approximately_honoured():
    examples = _corpus(n_docs=100, per_doc=2)
    report = split_examples(examples)
    n = len(examples)
    for fold, share in DEFAULT_SHARES.items():
        got = len(report.folds[fold]) / n
        assert abs(got - share) < 0.1, f"{fold}: {got:.3f} vs {share}"


def test_fold_membership_does_not_track_input_order():
    # Data arriving sorted by document must not put a contiguous block of
    # documents into one fold; otherwise a date-ordered export leaks time.
    examples = _corpus(n_docs=60, per_doc=1)
    report = split_examples(examples)
    first_ten = {_fold_of(report, i) for i in range(10)}
    assert len(first_ten) > 1


# ------------------------------------------------------------ what is claimed

def test_grouped_examples_produce_a_grouped_basis():
    cal = fit_calibrator(_corpus(n_docs=30), alpha=0.1, n_min=1)
    assert cal.split_basis == "grouped"
    assert cal.split_report["grouped"] is True


def test_ungrouped_examples_say_so_rather_than_claiming_a_group_split():
    plain = [TrainingExample(0.9 - 0.01 * i, "exact|multi", int(i % 4 in (0, 1)))
             for i in range(40)]
    cal = fit_calibrator(plain, alpha=0.1, n_min=1)
    assert cal.split_basis == "row"
    assert cal.split_report is None


def test_the_basis_survives_a_roundtrip():
    cal = fit_calibrator(_corpus(n_docs=30), alpha=0.1, n_min=1)
    back = TunedCalibrator.from_dict(cal.to_dict())
    assert back.split_basis == "grouped"
    assert back.split_report == cal.split_report


def test_a_calibrator_persisted_before_grouping_reads_back_as_a_row_split():
    # Absent the field, the honest reading is the weaker one: it was fit
    # before grouping existed, so it was fit on a row split.
    d = fit_calibrator(_corpus(n_docs=30), alpha=0.1, n_min=1).to_dict()
    del d["split_basis"]
    del d["split_report"]
    assert TunedCalibrator.from_dict(d).split_basis == "row"


def test_from_folds_reports_the_basis_it_was_given_and_never_resplits():
    examples = _corpus(n_docs=40)
    report = split_examples(examples)
    cal = fit_calibrator_from_folds(
        report.rows(examples, "platt"), report.rows(examples, "conformal"),
        alpha=0.1, n_min=1, split_basis="grouped",
        split_report=report.to_dict())
    assert cal.split_basis == "grouped"
    assert cal.split_disjoint is True


def test_a_degenerate_fold_still_reports_the_lost_disjointness():
    # Grouping does not rescue a fold with no positive in it: the guarantee is
    # gone for the same reason as before, and must still be reported.
    examples = [_ex(0.9, 1, document="d0")] + [
        _ex(0.4, 0, document=f"d{i}") for i in range(1, 30)]
    cal = fit_calibrator(examples, alpha=0.1, n_min=1)
    assert cal.split_disjoint is False


# ------------------------------------------------------------- holdout axis

def test_holdout_by_separates_whole_tenants():
    examples = ([_ex(0.9, 1, tenant="t1", document=f"a{i}") for i in range(5)]
                + [_ex(0.8, 0, tenant="t2", document=f"b{i}") for i in range(5)])
    fit, held = holdout_by(examples, "tenant", {"t2"})
    assert {e.groups["tenant"] for e in fit} == {"t1"}
    assert {e.groups["tenant"] for e in held} == {"t2"}


def test_holdout_by_leaves_rows_without_the_dimension_on_the_fit_side():
    examples = [_ex(0.9, 1, tenant="t1"), _ex(0.8, 0)]
    fit, held = holdout_by(examples, "tenant", {"t2"})
    assert len(fit) == 2 and held == []


def test_fit_still_refuses_data_it_cannot_calibrate_from():
    with pytest.raises(ValueError):
        fit_calibrator([_ex(0.5, 0, document=f"d{i}") for i in range(20)])


# ------------------------------ what a fold is allowed to claim about itself

def test_holdout_only_identities_do_not_buy_a_grouped_basis():
    # tenant and time are holdout axes, not link dimensions. Rows carrying
    # only those are separable, but separating them separates nothing —
    # calling the result "grouped" would claim a guarantee the identities
    # never supported.
    from ktrf.calibration import fit_with_folds

    rows = [_ex(0.9 - 0.01 * i, int(i % 4 in (0, 1)), tenant="t1",
                time_bucket="2026-09-05") for i in range(40)]
    fitted = fit_with_folds(rows, alpha=0.1, n_min=1)
    assert fitted.calibrator.split_basis == "row"
    assert fitted.calibrator.split_report["grouped"] is False


def test_an_ungrouped_fit_locks_nothing_because_it_used_every_row():
    # the row split takes examples[0::2] and examples[1::2] — that is all of
    # them. A fold called "test" would hold rows the fit had already seen, and
    # coverage measured there is the number this change exists to stop
    # reporting.
    from ktrf.calibration import fit_with_folds

    plain = [TrainingExample(0.9 - 0.01 * i, "exact|multi", int(i % 4 in (0, 1)))
             for i in range(40)]
    fitted = fit_with_folds(plain, alpha=0.1, n_min=1,
                            shares=DEFAULT_SHARES)
    assert fitted.locked == []


def test_a_grouped_fit_does_lock_its_test_fold():
    from ktrf.calibration import fit_with_folds

    examples = _corpus(n_docs=40)
    fitted = fit_with_folds(examples, alpha=0.1, n_min=1,
                            shares=DEFAULT_SHARES)
    assert fitted.locked, "a grouped four-way split has rows to lock"
    assert fitted.calibrator.split_basis == "grouped"

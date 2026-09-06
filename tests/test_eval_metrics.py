"""Evaluation metric contract tests (spec §43). REQ-EVAL-001/002, REQ-LVL-003."""

import pytest

from eval.metrics import EvalReport, wilson_interval


def test_metrics_require_conditioning():
    # REQ-EVAL-001: unconditioned metric reporting is forbidden
    r = EvalReport()
    with pytest.raises(ValueError):
        r.add_metric("recall", "overall", 9, 10)
    m = r.add_metric("recall", "E2E", 9, 10)
    assert m.conditioning == "E2E"
    assert m.to_dict()["conditioning"] == "E2E"


def test_conformance_and_coverage_not_merged():
    # REQ-LVL-003/§3.5: conformance is a failure count, never a coverage %
    r = EvalReport()
    with pytest.raises(ValueError):
        r.add_metric("conformance_rate", "E2E", 100, 100)
    r.set_conformance(total=100, failed=0)
    d = r.to_dict()
    assert d["conformance"]["failure_count"] == 0
    assert all("conformance" not in m["name"] for m in d["metrics"])


def test_wilson_interval():
    # REQ-EVAL-002: CIs accompany point estimates
    lo, hi = wilson_interval(95, 100)
    assert lo < 0.95 < hi
    assert 0.88 < lo < 0.92
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0 and lo < 1.0


def test_report_includes_ci():
    r = EvalReport()
    m = r.add_metric("recall", "E2E", 99, 100)
    d = m.to_dict()
    assert "ci95" in d and d["ci95"][0] < d["value"] <= d["ci95"][1]


# ---------------------------------------------------------------------------
# Evaluation-construction defects found while measuring M1
# ---------------------------------------------------------------------------


def test_fake_glossary_absence_is_checked_in_the_matcher_space():
    """A case-sensitive absence test scores a construction error as an FP.

    The resolver matches through a case-folding normalized channel, so a
    surface like `gb` is reachable in a corpus that only ever writes `GB`.
    Keeping it makes the resolver commit on it, and the fake-glossary suite
    reports a product false positive that the product did not cause.
    """
    from eval.synthetic import absent_bindings_only, build_synthetic_glossary

    g_dict, _ = build_synthetic_glossary(400, seed=5)
    acronym = next(b["surface"] for b in g_dict["alias_bindings"]
                   if b["surface"].isascii() and b["surface"].isalpha())

    # the corpus writes it in the *other* case only
    kept, removed = absent_bindings_only(
        dict(g_dict), [f"오늘 {acronym.lower()} 단위로 저장했다."])
    assert removed >= 1
    assert acronym not in {b["surface"] for b in kept["alias_bindings"]}


def test_absence_filter_keeps_genuinely_absent_surfaces():
    from eval.synthetic import absent_bindings_only, build_synthetic_glossary

    g_dict, _ = build_synthetic_glossary(50, seed=7)
    before = len(g_dict["alias_bindings"])
    kept, removed = absent_bindings_only(dict(g_dict), ["아무 관련 없는 문장."])
    assert removed == 0
    assert len(kept["alias_bindings"]) == before


def test_coverage_verdict_is_three_valued():
    """A point estimate inside the CI is not a pass (VARIANTS_PLAN M0 item 4)."""
    from eval.run_benchmarks import run_calibration_holdout

    res = run_calibration_holdout()["results"]
    for key, v in res.items():
        assert v["verdict"] in ("PASS", "FAIL", "INSUFFICIENT_DATA")
        lo, hi = v["ci95"]
        assert lo <= v["pooled_coverage"] <= hi
        if v["verdict"] == "PASS":
            assert lo >= v["target"]
        elif v["verdict"] == "FAIL":
            assert hi < v["target"]
        else:  # the sample cannot decide, and must not be reported as a pass
            assert lo < v["target"] <= hi
        # pooled over trials, not a single draw that seed noise can swing
        assert v["trials"] >= 4 and v["n_holdout_pooled"] > 1000


# ---------------------------------------------------------------------------
# provenance: a report has to name its code *and* its data
# ---------------------------------------------------------------------------


def _init_repo(path):
    import subprocess

    def git(*a):
        subprocess.run(["git", *a], cwd=str(path), capture_output=True,
                       check=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (path / "a.txt").write_text("one", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-qm", "first")
    return git


def test_a_dirty_tree_is_named_in_the_stamp(tmp_path):
    """A report regenerated before its code was committed stamps the parent
    commit and looks authoritative. The suffix is what says otherwise."""
    from eval.metrics import git_commit

    git = _init_repo(tmp_path)
    clean = git_commit(tmp_path)
    assert clean and not clean.endswith("-dirty")

    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    assert git_commit(tmp_path) == clean + "-dirty"

    git("add", "a.txt")
    assert git_commit(tmp_path) == clean + "-dirty"  # staged is still not HEAD


def test_untracked_scratch_does_not_make_a_tree_dirty(tmp_path):
    """Review notes and scratch files beside the repo are not what ran."""
    from eval.metrics import git_commit

    _init_repo(tmp_path)
    clean = git_commit(tmp_path)
    (tmp_path / "NOTES.md").write_text("scratch", encoding="utf-8")
    assert git_commit(tmp_path) == clean


def test_the_footer_warns_when_the_numbers_match_no_commit(tmp_path):
    from eval.metrics import provenance_line

    _init_repo(tmp_path)
    assert "작업 트리가 커밋과 다르다" not in provenance_line(tmp_path)
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    assert "작업 트리가 커밋과 다르다" in provenance_line(tmp_path)


def test_the_data_line_is_asked_for_not_declared(monkeypatch):
    """A harness with synthetic inputs stamps no corpus; one that read the
    corpus cannot forget to. The stamp says what was read."""
    from eval import metrics, wild_data

    monkeypatch.setattr(wild_data, "_LOADED", None)
    assert metrics.data_provenance() == ""

    monkeypatch.setattr(wild_data, "_LOADED", {
        "sha256": "abc123", "sentences": 1000,
        "declared_sentences": 1000, "sources": 3})
    line = metrics.data_provenance()
    assert "abc123" in line and "1,000" in line and "3개 출처" in line
    assert "불일치" not in line


def test_a_truncated_cache_is_visible_in_the_footer(monkeypatch):
    """Row count against the count the cache declares — a hand-edited or
    half-written cache otherwise reads as a smaller corpus on purpose."""
    from eval import metrics, wild_data

    monkeypatch.setattr(wild_data, "_LOADED", {
        "sha256": "abc123", "sentences": 900,
        "declared_sentences": 1000, "sources": 3})
    assert "불일치" in metrics.data_provenance()


def test_corpus_fingerprint_is_a_copy(monkeypatch):
    from eval import wild_data

    monkeypatch.setattr(wild_data, "_LOADED", {"sha256": "x", "sentences": 1,
                                               "sources": 1})
    fp = wild_data.corpus_fingerprint()
    fp["sha256"] = "tampered"
    assert wild_data.corpus_fingerprint()["sha256"] == "x"


def test_a_rerendered_report_keeps_the_corpus_that_produced_it(monkeypatch):
    """`--render-only` re-renders markdown from a saved payload and loads
    nothing, so asking this process would quietly drop the data line from a
    report that certainly had one. The payload carries the answer."""
    from eval import metrics, wild_data

    monkeypatch.setattr(wild_data, "_LOADED", None)
    saved = {"sha256": "deadbeef", "sentences": 114605,
             "declared_sentences": 114605, "sources": 11}
    assert "deadbeef" not in metrics.provenance_line(".", "표본")
    assert "deadbeef" in metrics.provenance_line(".", "표본", corpus=saved)


def test_writing_a_report_does_not_make_the_stamp_cry_wolf(tmp_path):
    """Regenerating a report modifies a tracked file. Without excluding
    generated output every report would stamp itself as proof the code had
    diverged, and an alarm that fires every run says nothing on the run that
    matters."""
    from eval.metrics import git_commit

    git = _init_repo(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "R.md").write_text("v1", encoding="utf-8")
    git("add", "reports/R.md")
    git("commit", "-qm", "report")
    clean = git_commit(tmp_path)

    (tmp_path / "reports" / "R.md").write_text("v2", encoding="utf-8")
    assert git_commit(tmp_path) == clean          # output, not an input

    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    assert git_commit(tmp_path) == clean + "-dirty"   # anything else counts


# ---------------------------------------------------------------- corpora

def test_every_declared_corpus_names_a_license_for_every_source():
    """The repository ships a downloader rather than text so each source can
    name its terms. A source with no declared license cannot go in whatever
    it would have scored — `sieu-n/korean-newstext-dump` measured 6-47 silver
    occurrences per 10k characters over 2.4M rows and is not here for exactly
    that reason."""
    from eval.wild_data import CORPORA

    for name, (sources, _cache, licenses) in CORPORA.items():
        for source in sources:
            dataset = source[0]
            assert licenses.get(dataset), f"{name}: {dataset} has no license"


def test_every_corpus_has_its_own_cache_file():
    """Two corpora sharing a cache would silently be one corpus, and the
    held-out ones exist precisely because they are separate."""
    from eval.wild_data import CORPORA

    caches = [cache for _s, cache, _l in CORPORA.values()]
    assert len(caches) == len(set(caches)), caches


def test_the_source_tuples_are_the_shape_the_downloader_reads():
    from eval.wild_data import CORPORA

    for name, (sources, _cache, _l) in CORPORA.items():
        for source in sources:
            assert len(source) == 8, f"{name}: {source}"
            (dataset, config, split, field, max_rows, do_split,
             max_keep, start_offset) = source
            assert all(isinstance(x, str)
                       for x in (dataset, config, split, field)), source
            assert isinstance(max_rows, int) and max_rows > 0, source
            assert isinstance(do_split, bool), source
            assert max_keep is None or (isinstance(max_keep, int)
                                        and max_keep > 0), source
            assert isinstance(start_offset, int) and start_offset >= 0, source

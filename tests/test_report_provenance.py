"""A report must say what produced it — and must not guess when it can't.

Three defects these cover, each found in a shipped report:

1. `AB_GROUNDING.md` accumulates one row per `--model` invocation and printed
   the *first* run's manifest as the provenance of the whole table. Two models
   measured a week and four commits apart rendered identically to two measured
   back to back.
2. `LLM_RAG_COMPARE.md` carried no provenance at all, while `--track hard`
   merges into an earlier easy-track payload.
3. `run_wild --render-only` re-renders a saved payload and stamped *today's*
   HEAD and today's date on it — the footer that exists to prevent drift was
   asserting the drift away.
"""

import importlib
import json
import pkgutil
import subprocess
import sys

import pytest

import eval as eval_pkg
from eval.metrics import (manifest_agreement, manifest_provenance,
                          provenance_line, run_manifest)


def test_every_eval_module_imports():
    # `silver_occurrences` was renamed on 2026-09-01 and two entry points
    # kept importing `_silver_occurrences`: run_llm_rag and run_ab_grounding
    # were dead on arrival for six days and nothing said so, because no test
    # imports them.
    broken = []
    for mod in sorted(m.name for m in pkgutil.iter_modules(eval_pkg.__path__)):
        try:
            importlib.import_module(f"eval.{mod}")
        except Exception as exc:  # pragma: no cover - the failure is the point
            broken.append(f"eval.{mod}: {type(exc).__name__}: {exc}")
    assert not broken, "eval entry points that cannot even import:\n" + \
        "\n".join(broken)


def test_agreement_splits_shared_from_differing():
    m = {"a": {"commit": "x", "seed": 1, "measured_at": "2026-08-01"},
         "b": {"commit": "x", "seed": 1, "measured_at": "2026-09-01"}}
    shared, differing = manifest_agreement(m)
    assert shared == {"commit": "x", "seed": 1}
    assert list(differing) == ["measured_at"]
    assert differing["measured_at"] == {"a": "2026-08-01", "b": "2026-09-01"}


def test_a_key_missing_from_one_row_is_a_disagreement():
    # absence is not agreement: a row measured before a field existed did
    # not agree with the rows that have it, it simply cannot say.
    shared, differing = manifest_agreement(
        {"a": {"commit": "x", "seed": 1}, "b": {"commit": "x"}})
    assert shared == {"commit": "x"}
    assert differing == {"seed": {"a": 1, "b": None}}


def test_agreeing_rows_render_one_provenance_block():
    lines = manifest_provenance({"a": {"commit": "x"}, "b": {"commit": "x"}})
    assert lines == ["- commit: `x`"]


def test_differing_rows_render_a_per_row_table_and_say_so():
    lines = manifest_provenance(
        {"a": {"commit": "x"}, "b": {"commit": "y"}})
    text = "\n".join(lines)
    assert "행마다 측정 조건이 다르다" in text
    # every row's value is reachable, not just the first
    assert "`x`" in text and "`y`" in text
    assert "| commit | `x` | `y` |" in text


def test_no_manifests_render_nothing_rather_than_a_false_claim():
    assert manifest_provenance({}) == []
    assert manifest_agreement({}) == ({}, {})


def test_run_manifest_stamps_commit_and_date():
    m = run_manifest(".", track="easy")
    assert m["track"] == "easy"
    assert m["git_commit"]
    # date resolution, so two rows minutes apart in one invocation agree
    assert len(m["measured_at"]) == len("2026-09-07")


def test_provenance_line_prefers_the_manifest_over_this_process():
    line = provenance_line(".", manifest={"git_commit": "deadbee",
                                          "measured_at": "2026-08-25"})
    assert "`deadbee`" in line and "2026-08-25" in line


def test_provenance_line_carries_the_dirty_warning_from_the_manifest():
    line = provenance_line(".", manifest={"git_commit": "deadbee-dirty",
                                          "measured_at": "2026-08-25"})
    assert "작업 트리가 커밋과 다르다" in line


def test_provenance_line_falls_back_to_this_process_without_a_manifest():
    assert "unknown" not in provenance_line(".")


def _run_wild(*args):
    return subprocess.run([sys.executable, "-m", "eval.run_wild", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)


def test_render_only_refuses_a_payload_with_no_manifest(tmp_path):
    # the alternative is a footer that stamps today's HEAD on numbers of
    # unknown age, which is worse than no report
    stale = tmp_path / "wild_stale.json"
    stale.write_text(json.dumps({"corpus": "wild", "silver": {}}),
                     encoding="utf-8")
    out = _run_wild("--render-only", str(stale))
    assert out.returncode != 0
    assert "no run manifest" in (out.stderr + out.stdout)


def _ab_run(manifest: dict) -> dict:
    cond = {"rate": 0.5, "hits": 1, "total": 2, "ci95": [0.1, 0.9],
            "flips_vs_A": {"helpful": 0, "harmful": 0,
                           "mcnemar_exact_p": 1.0}}
    block = {k: dict(cond) for k in ("A_llm_only", "B_full_glossary",
                                     "C_ktrf", "D_gold")}
    block |= {"gold_benefit_recovery": None, "context_tokens_mean": {},
              "context_injection_rate": {}}
    return {"cases": 2, "budget_tokens": 400, "manifest": manifest,
            "summary": {"overall": block, "slices": {"known_abbrev": block}}}


def test_ab_grounding_reports_each_model_run_it_merged(tmp_path):
    from eval.run_ab_grounding import write_markdown

    payload = {"runs": {
        "old:8b": _ab_run({"git_commit": "aaaaaaa",
                           "measured_at": "2026-08-01", "seed": 11}),
        "new:12b": _ab_run({"git_commit": "bbbbbbb",
                            "measured_at": "2026-09-01", "seed": 11})}}
    out = tmp_path / "AB.md"
    write_markdown(payload, out)
    text = out.read_text(encoding="utf-8")
    assert "행마다 측정 조건이 다르다" in text
    # both commits reachable — the old renderer showed only the first
    assert "`aaaaaaa`" in text and "`bbbbbbb`" in text
    assert "- seed: `11`" in text  # agreeing fields stay in one line


def test_ab_grounding_stays_quiet_when_the_runs_agree(tmp_path):
    from eval.run_ab_grounding import write_markdown

    m = {"git_commit": "aaaaaaa", "measured_at": "2026-09-01", "seed": 11}
    payload = {"runs": {"a:8b": _ab_run(dict(m)),
                        "b:12b": _ab_run(dict(m))}}
    out = tmp_path / "AB.md"
    write_markdown(payload, out)
    text = out.read_text(encoding="utf-8")
    assert "행마다 측정 조건이 다르다" not in text
    assert "- git_commit: `aaaaaaa`" in text


def _rag_side(manifest_key: str, manifest: dict) -> dict:
    lat = {"p50": 0.1, "p95": 0.2, "throughput_per_min": 60.0}
    return {
        "silver": {"recall": {"rate": 1.0, "hits": 2, "total": 2,
                              "ci95": [0.3, 1.0]},
                   "grounding_precision": {"rate": 1.0, "reported": 2},
                   "resolved_precision_lower_bound": 0.97,
                   "hallucinated_mentions": 0, "parse_failures": 0,
                   "latency_s": lat},
        "fake": {"fp_mentions": 0, "examples": []},
        manifest_key: manifest,
    }


def test_llm_rag_reports_the_track_each_row_came_from(tmp_path):
    from eval.run_llm_rag import write_markdown

    payload = {
        "silver_sentences": 2, "gold_instances": 2, "fake_sentences": 1,
        "results": {
            "ktrf": _rag_side("manifest_easy",
                              {"git_commit": "aaaaaaa",
                               "measured_at": "2026-08-01"}),
            "qwen3:8b": _rag_side("manifest_hard",
                                  {"git_commit": "bbbbbbb",
                                   "measured_at": "2026-09-01"}),
        },
    }
    out = tmp_path / "RAG.md"
    write_markdown(payload, out)
    text = out.read_text(encoding="utf-8")
    assert "## Provenance" in text
    assert "행마다 측정 조건이 다르다" in text
    assert "ktrf (easy)" in text and "qwen3:8b (hard)" in text


def test_llm_rag_says_so_when_the_payload_predates_manifests(tmp_path):
    from eval.run_llm_rag import write_markdown

    payload = {"silver_sentences": 2, "gold_instances": 2,
               "fake_sentences": 1,
               "results": {"ktrf": _rag_side("unused", {})}}
    out = tmp_path / "RAG.md"
    write_markdown(payload, out)
    text = out.read_text(encoding="utf-8")
    assert "per-run manifest 도입 전에 생성되었다" in text


def test_a_merged_report_never_stamps_one_measurement_time(tmp_path):
    # `*측정 시점: commit X, <today>*` is the footer every single-run report
    # carries. On a table whose rows came from different processes on
    # different days it is simply false, however honest it looks.
    from eval.run_ab_grounding import write_markdown

    payload = {"runs": {
        "old:8b": _ab_run({"git_commit": "aaaaaaa",
                           "measured_at": "2026-08-01"}),
        "new:12b": _ab_run({"git_commit": "bbbbbbb",
                            "measured_at": "2026-09-01"})}}
    out = tmp_path / "AB.md"
    write_markdown(payload, out)
    text = out.read_text(encoding="utf-8")
    assert "측정 시점: commit" not in text
    assert "렌더링되었다" in text


def test_the_run_manifest_is_taken_before_the_measurement(monkeypatch):
    # These suites run for hours (`wild` took 21,347s, `web` 8,063s). Taking
    # the stamp at the end lets a commit landing meanwhile retag a finished
    # measurement with code it never ran.
    import eval.run_wild as rw

    order = []

    def fake_manifest(root=None, **kw):
        order.append("manifest")
        return {"git_commit": "aaaaaaa", "measured_at": "2026-09-07"}

    class Stop(Exception):
        pass

    def fake_load(name):
        order.append("load_corpus")
        raise Stop

    monkeypatch.setattr(rw, "run_manifest", fake_manifest)
    monkeypatch.setattr(rw, "load_corpus", fake_load)
    monkeypatch.setattr(sys, "argv", ["run_wild", "--corpus", "wild"])
    with pytest.raises(Stop):
        rw.main()
    assert order == ["manifest", "load_corpus"]

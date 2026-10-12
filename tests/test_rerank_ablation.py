"""Target/path ranking must preserve spans, candidate sets and guard authority."""

import json
import hashlib
import sys

import pytest

from eval.run_rerank_ablation import (DEFAULT_CASES, evaluate, hard_negative_pairs,
                                     hypotheses, load_cases)
from ktrf.rerank import (LinkingHypothesis, LexicalCrossEncoder, maxsim,
                         rank_hypotheses, rerank_query)
from ktrf.segmentation import StructuralPath
from ktrf.abbrev import AbbrevCandidate
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import RuntimePolicy, compile_snapshot


def test_target_marks_only_selected_occurrence():
    text = "ABC의 요금 뒤 ABC의 출입 승인"
    span = (text.rindex("ABC"), text.rindex("ABC") + 3)
    assert rerank_query(text, span) == "ABC의 요금 뒤 [TARGET]ABC[/TARGET]의 출입 승인"
    assert rerank_query(text, span, "surface") == "ABC"
    assert rerank_query(text, span, "context") == text


def test_path_input_keeps_full_surface_contract():
    path = StructuralPath("금감원장", (0, 4), "금감원", (0, 3), kind="SUFFIX",
                          residual="장", residual_kind="SUFFIX", full_identity="DISTINCT",
                          relation="HEAD_OF")
    query = rerank_query("금감원장", (0, 3), "path", path)
    features = json.loads(query.split("\nPATH ")[1])
    assert features["full_identity"] == "DISTINCT"
    assert features["relation"] == "HEAD_OF"
    assert features["surface_span"] == [0, 4]


def test_high_model_score_cannot_lift_derivative_guard():
    class Scores:
        def score_pairs(self, pairs):
            return [100., -100.]

    cases = load_cases(DEFAULT_CASES)
    case = next(c for c in cases if c["case_id"] == "role_path_guard")
    ranked = rank_hypotheses(case["text"], hypotheses(case, 8), Scores(), "path")
    assert len(ranked) == 2
    assert ranked[0].score == 100.
    assert not ranked[0].commit_allowed
    assert "typed_derivative" in ranked[0].guard_reasons
    assert ranked[1].commit_allowed


def test_ablation_uses_identical_fixed_hypotheses():
    results = evaluate(load_cases(DEFAULT_CASES), LexicalCrossEncoder(), budget=2, repeats=1)
    sets = [[(r["case_id"], r["candidate_count"], r["gold_in_shortlist"])
             for r in v["cases"]] for v in results.values()]
    assert all(s == sets[0] for s in sets)
    assert all(v["measured_pair_calls"] == 24 for v in results.values())
    assert all(v["resolvable_cases"] == 9 for v in results.values())


def test_budget_recall_loss_is_reported():
    results = evaluate(load_cases(DEFAULT_CASES), LexicalCrossEncoder(), budget=1, repeats=1)
    assert all(any(r["truncated"] for r in v["cases"]) for v in results.values())
    assert all(v["candidate_exact_link_recall"] < 1 for v in results.values())


def test_confusion_pairs_preserve_grouping_and_true_ambiguity():
    cases = load_cases(DEFAULT_CASES)
    pairs = hard_negative_pairs(cases, variant="path")
    ambiguous = [p for p in pairs if p["case_id"] == "same_alias_ambiguous"]
    assert [p["label"] for p in ambiguous] == [1, 1]
    nil = [p for p in pairs if p["ambiguity"] == "nil"]
    assert all(p["label"] == 0 for p in nil)
    assert all(p["document_id"] and p["family_id"] and p["source"] for p in pairs)
    assert len(pairs) == 24
    targets = [p for p in pairs if p["case_id"].startswith("two_targets_")]
    assert len({p["document_id"] for p in targets}) == 1


def test_report_hash_uses_the_evaluated_bytes(tmp_path, monkeypatch):
    from eval import run_rerank_ablation as runner
    payload = DEFAULT_CASES.read_bytes()
    cases_file, output = tmp_path / "cases.jsonl", tmp_path / "result.json"
    cases_file.write_bytes(payload)
    original_evaluate = runner.evaluate
    def mutate_after_scoring(*args, **kwargs):
        results = original_evaluate(*args, **kwargs)
        cases_file.write_bytes(payload.replace(b"synthetic:two_targets_document", b"changed:document"))
        return results
    monkeypatch.setattr(runner, "evaluate", mutate_after_scoring)
    monkeypatch.setattr(sys, "argv", ["rerank", "--cases", str(cases_file), "--out", str(output),
                                     "--repeats", "1"])
    runner.main()
    report = json.loads(output.read_text())
    assert report["cases_sha256"] == hashlib.sha256(payload).hexdigest()
    assert report["cases_sha256"] != hashlib.sha256(cases_file.read_bytes()).hexdigest()
    for variant in report["variants"].values():
        assert all(r["document_id"] == "synthetic:two_targets_document"
                   for r in variant["cases"] if r["case_id"].startswith("two_targets_"))


def test_maxsim_is_tokenwise_not_pooled_dot_product():
    assert maxsim([[1., 0.], [0., 1.]], [[1., 0.], [0., 1.]]) == 2.
    assert maxsim([[1., 0.]], [[-1., 0.], [0., -1.]]) == 0.
    with pytest.raises(ValueError, match="dimension"):
        maxsim([[1., 0.]], [[1.]])
    with pytest.raises(ValueError, match="nonempty"):
        maxsim([], [[1.]])


@pytest.mark.parametrize("scores", ([1.], [1., float('nan')]))
def test_invalid_scorer_output_rejected(scores):
    class Bad:
        def score_pairs(self, pairs):
            return scores

    hs = [LinkingHypothesis(StructuralPath("ABC", (0, 3), "ABC", (0, 3)),
                            eid, eid) for eid in ("A", "B")]
    with pytest.raises(ValueError):
        rank_hypotheses("ABC", hs, Bad())


def test_path_cannot_silently_describe_another_target():
    with pytest.raises(ValueError, match="describe"):
        rerank_query("ABC DEF", (0, 3), "path",
                     StructuralPath("DEF", (4, 7), "DEF", (4, 7)))


def _integration_glossary(surface="ABC"):
    return load_glossary({
        "glossary_id": "rerank-integration", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "BILLING", "canonical": "결제관리도구", "description": "과금"},
                     {"entity_id": "ACCESS", "canonical": "출입승인절차", "description": "방문자"}],
        "alias_families": [{"family_id": "F", "representative": surface,
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": eid, "entity_id": eid, "family_id": "F", "surface": surface}
                           for eid in ("BILLING", "ACCESS")],
    })


def test_resolver_retains_candidates_from_later_decomposition(monkeypatch):
    import importlib
    resolver_module = importlib.import_module("ktrf.resolver")
    snapshot = compile_snapshot(_integration_glossary())
    paths = [StructuralPath("가나다", (0, 3), "가나다", (0, 3)),
             StructuralPath("가나다", (0, 3), "가나", (0, 2), kind="SUFFIX",
                            residual="다", residual_kind="UNKNOWN", full_identity="UNRESOLVED")]
    monkeypatch.setattr(resolver_module, "_paths_for", lambda *args: paths)
    def align(token, span, max_results=5):
        return [AbbrevCandidate("BILLING" if token == "가나다" else "ACCESS", span, token, .9)]
    monkeypatch.setattr(snapshot.abbrev, "align_token", align)
    response = resolve(snapshot, "가나다", options={"return_all_mentions": True})
    by_surface = {m["surface"]: m for m in response["mentions"]}
    assert {"가나다", "가나"} <= set(by_surface)
    ids = {c["entity_id"] for c in by_surface["가나"]["prediction_set"]["members"] if "entity_id" in c}
    assert "ACCESS" in ids
    assert by_surface["가나"]["link_decision"] != "RESOLVED"


@pytest.mark.parametrize("variant", ("context", "target", "path"))
def test_resolver_input_policy_and_typed_guard(variant):
    class Spy:
        reranker_id = "test-constant-scorer"
        def __init__(self):
            self.pairs = []
        def score_pairs(self, pairs):
            self.pairs.extend(pairs)
            return [.99] * len(pairs)
    spy = Spy()
    snapshot = compile_snapshot(_integration_glossary("금감원"),
                                policy=RuntimePolicy(rerank_input=variant), reranker=spy)
    response = resolve(snapshot, "금감원장이 발표했다.", options={"return_all_mentions": True})
    assert spy.pairs
    query = spy.pairs[0][0]
    if variant == "context":
        assert query == "금감원장이 발표했다."
    else:
        assert "[TARGET]금감원[/TARGET]장이" in query
    if variant == "path":
        features = json.loads(query.split("\nPATH ")[1])
        assert features["full_identity"] == "DISTINCT"
        assert features["residual"] == "장"
    assert all(m["link_decision"] != "RESOLVED" for m in response["mentions"])

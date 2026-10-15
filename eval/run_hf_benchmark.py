"""Pinned external HF boundary and QA-evidence diagnostics; no invented link gold.

Usage: python -m eval.run_hf_benchmark --out-dir eval/out/hf-benchmark
Raw source text and per-case inputs remain in the ignored cache/output directory.
Only aggregate results are suitable for the public report.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import time

from ktrf import compile_snapshot, load_glossary, resolve
from ktrf.normalization import DEFAULT_PROFILES, normalize_alias

from .hf_sources import acquire_sources, load_ner_records, load_tydi_records

ROOT = Path(__file__).resolve().parents[1]
SEED = "hf-external-v1-20261016"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
                                    sort_keys=True).encode()).hexdigest()


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def partition_ner(records, seed=SEED):
    """Content-identical rows stay together; selection never inspects predictions."""
    unique = {}
    for record in records:
        key = record["document_sha256"]
        if key in unique:
            if unique[key]["ner_annotations"] != record["ner_annotations"]:
                raise ValueError("duplicate source text has conflicting NER labels")
        else:
            unique[key] = record
    training, heldout = [], []
    for sha, record in sorted(unique.items()):
        bucket = int(hashlib.sha256((seed + sha).encode()).hexdigest(), 16) % 5
        (heldout if bucket == 0 else training).append(record)
    return training, heldout, len(records) - len(unique)


def exclude_conflicting_ner(records):
    """Quarantine every copy of a text with inconsistent source annotations."""
    grouped = defaultdict(list)
    for record in records:
        grouped[record["document_sha256"]].append(record)
    conflicts = []
    invalid = set()
    for sha, rows in sorted(grouped.items()):
        if len({digest(row["ner_annotations"]) for row in rows}) > 1:
            invalid.add(sha)
            conflicts.append({"document_sha256": sha,
                              "source_row_ids": [row["source_row_id"] for row in rows],
                              "reason": "conflicting_annotations_for_identical_text"})
    return [row for row in records if row["document_sha256"] not in invalid], conflicts


def select_records(records, limit, seed=SEED):
    if limit < 1:
        raise ValueError("positive document limit required")
    return sorted(records, key=lambda r: (digest([seed, r["document_id"]]),
                                         r["document_id"]))[:limit]


def reference_catalog(training, limit=512):
    """Train-only type/surface lexicon, deliberately NOT real entity identities."""
    counts = Counter((a["type"], a["surface"])
                     for row in training for a in row["ner_annotations"]
                     if len(a["surface"].strip()) >= 2)
    selected = sorted(counts, key=lambda key: (-counts[key], key))[:limit]
    entries = [(kind, surface, "LEX_" + digest([kind, surface])[:24])
               for kind, surface in selected]
    data = {
        "glossary_id": "kbmc-training-lexical-reference", "version": "1",
        "schema_version": "3",
        "entities": [{"entity_id": eid, "canonical": surface,
                      "type_ids": [kind], "domain_ids": ["KBMC"],
                      "metadata": {"identity_scope": "type_surface_reference_only"}}
                     for kind, surface, eid in entries],
        "alias_families": [{"family_id": eid, "representative": surface}
                           for _, surface, eid in entries],
        "alias_bindings": [{"alias_id": eid, "family_id": eid,
                            "entity_id": eid, "surface": surface}
                           for _, surface, eid in entries],
    }
    return load_glossary(data), data


def literal_mentions(text, surfaces):
    spans = set()
    for surface in surfaces:
        start = 0
        while True:
            start = text.find(surface, start)
            if start < 0:
                break
            spans.add((start, start + len(surface)))
            start += 1
    return [{"span": {"codepoint": {"start": span[0], "end": span[1]}},
             "link_decision": "UNJUDGED"}
            for span in sorted(spans)]


def boundary_counts(record, mentions, surfaces):
    """Count reference hits; off-reference outputs are unjudged, not false links."""
    refs = record["ner_annotations"]
    predicted = {(m["span"]["codepoint"]["start"], m["span"]["codepoint"]["end"])
                 for m in mentions}
    resolved = {(m["span"]["codepoint"]["start"], m["span"]["codepoint"]["end"])
                for m in mentions
                if m.get("link_decision") == "RESOLVED"}
    reference_spans = {tuple(ref["span"]) for ref in refs}
    result = Counter(reference_spans=len(refs), prediction_spans=len(predicted),
                     off_reference_predictions_unjudged=len(predicted - reference_spans),
                     resolved_outputs_unjudged=len(resolved))
    by_type = defaultdict(Counter)
    for ref in refs:
        span = tuple(ref["span"])
        seen = normalize_alias(ref["surface"], DEFAULT_PROFILES["korean_term"]) in surfaces
        counts = Counter(reference_spans=1, exact_reference_hits=int(span in predicted),
                         overlap_reference_hits=int(any(s < span[1] and span[0] < e
                                                        for s, e in predicted)),
                         resolved_exact_reference_hits=int(span in resolved),
                         alias_representable_reference_count=int(seen),
                         exact_representable_hits=int(seen and span in predicted))
        result.update(counts)
        by_type[ref["type"]].update(counts)
    # reference_spans already includes the document's annotations above.
    result["reference_spans"] = len(refs)
    return dict(result), {key: dict(value) for key, value in sorted(by_type.items())}


def evaluate_boundaries(records, glossary, modes=("literal", "fast", "commit", "aggressive")):
    started = time.perf_counter()
    snapshot = compile_snapshot(glossary)
    compile_ms = (time.perf_counter() - started) * 1000
    literal_surfaces = sorted({binding.surface for binding in glossary.alias_bindings})
    surfaces = {normalize_alias(s, DEFAULT_PROFILES["korean_term"]) for s in literal_surfaces}
    summaries, ledgers, decisions = {}, {}, {}
    for mode in modes:
        totals, by_type, errors = Counter(), defaultdict(Counter), Counter()
        latencies, candidate_sizes, docs = [], [], []
        decisions[mode] = {}
        for record in records:
            started = time.perf_counter()
            error = None
            try:
                if mode == "literal":
                    mentions = literal_mentions(record["text"], literal_surfaces)
                    response = {}
                else:
                    response = resolve(snapshot, record["text"], mode=mode,
                                       options={"return_all_mentions": True})
                    mentions = response["mentions"]
                decisions[mode][record["document_id"]] = digest(mentions)
            except Exception as exc:
                mentions, response = [], {}
                error = getattr(exc, "code", type(exc).__name__)
                errors[str(error)] += 1
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            counts, types = boundary_counts(record, mentions, surfaces)
            totals.update(counts)
            for kind, values in types.items():
                by_type[kind].update(values)
            for mention in mentions:
                pset = mention.get("prediction_set", {})
                candidate_sizes.append(pset.get("total_member_count", len(pset.get("members", [])))
                                       or int("resolved_entity" in mention))
                totals["truncated_prediction_sets"] += bool(pset.get("truncated"))
            totals["degraded_documents"] += bool(response.get("degraded"))
            docs.append({"document_id": record["document_id"],
                         "document_sha256": record["document_sha256"],
                         "counts": counts, "error": error, "latency_ms": elapsed})
        total_refs = totals["reference_spans"]
        summaries[mode] = {
            "documents": len(records), **dict(totals),
            "exact_reference_recall": ratio(totals["exact_reference_hits"], total_refs),
            "overlap_reference_recall": ratio(totals["overlap_reference_hits"], total_refs),
            "catalog_reference_coverage": ratio(totals["alias_representable_reference_count"], total_refs),
            "exact_recall_within_catalog": ratio(totals["exact_representable_hits"],
                                                totals["alias_representable_reference_count"]),
            "by_type": {kind: dict(counts) for kind, counts in sorted(by_type.items())},
            "errors": dict(errors), "failure_count": sum(errors.values()),
            "latency_ms": {"p50": percentile(latencies, .5),
                           "p95": percentile(latencies, .95),
                           "p99": percentile(latencies, .99)},
            "candidate_count_p95": percentile(candidate_sizes, .95),
            "snapshot_id": snapshot.snapshot_id,
            "semantic_precision_evaluated": False, "entity_linking_evaluated": False,
        }
        ledgers[mode] = docs
    shared = set(decisions.get("commit", {})) & set(decisions.get("aggressive", {}))
    agreement = {"compared_successful_documents": len(shared),
                 "different_mention_responses": sum(decisions["commit"][key] !=
                                                   decisions["aggressive"][key] for key in shared)}
    return {"snapshot_compile_ms": compile_ms, "modes": summaries,
            "commit_aggressive_agreement": agreement}, ledgers


def lexical_terms(text):
    cleaned = re.sub(r"[^0-9a-z가-힣]+", "", text.lower())
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def select_evidence(text, question, passages, *, budget=3000, top_k=3):
    """Question-only lexical ranking over source candidates, never over gold."""
    if budget < 1 or top_k < 1:
        raise ValueError("positive retrieval budget and top_k required")
    candidates = set()
    for start, end in passages:
        if not 0 <= start < end <= len(text):
            raise ValueError("passage outside source")
        cursor = start
        while cursor < end:
            finish = min(cursor + 1000, end)
            candidates.add((cursor, finish))
            if finish == end:
                break
            cursor = finish - 100
    query = lexical_terms(question)
    ranked = []
    for start, end in candidates:
        terms = lexical_terms(text[start:end])
        score = len(query & terms) / math.sqrt(max(1, len(terms)))
        ranked.append((-score, start, end))
    selected, used = [], 0
    for _, start, end in sorted(ranked):
        # Avoid spending the same budget on overlapping source chunks.
        if any(start < previous_end and previous_start < end
               for previous_start, previous_end in selected):
            continue
        if used + end - start > budget:
            continue
        selected.append((start, end))
        used += end - start
        if len(selected) == top_k:
            break
    return sorted(selected)


def contains_span(selected, span):
    return any(start <= span[0] and span[1] <= end for start, end in selected)


def evidence_counts(record, selected):
    """Keep minimal-answer and annotated passage preservation distinct."""
    answer_spans = record["answer_spans"]
    passages = record["answer_passage_spans"]
    answer_types = {answer["answer_type"] for answer in record.get("annotation_answers", [])}
    minimal_evaluable = record.get("minimal_answer_evaluable", True)
    return {
        "minimal_answerable_questions": int(minimal_evaluable and bool(answer_spans)),
        "minimal_answer_preserved": int(minimal_evaluable and bool(answer_spans) and any(
            contains_span(selected, span) for span in answer_spans)),
        "annotated_passage_questions": int(bool(passages)),
        "annotated_passage_preserved": int(bool(passages) and any(
            contains_span(selected, span) for span in passages)),
        "no_minimal_answer_questions": int(minimal_evaluable and not answer_spans),
        "invalid_minimal_annotation_questions": int(not minimal_evaluable),
        "questions_with_yes_no_annotation": int(any(
            answer in {"YES", "NO"} for answer in record["yes_no_answers"])),
        "unanimous_no_answer_questions": int(record.get("no_answer", False)),
        "questions_with_no_answer_vote": int("NO_ANSWER" in answer_types),
        "questions_with_passage_only_annotation": int("PASSAGE_ONLY" in answer_types),
        "questions_with_mixed_annotation_types": int(len(answer_types) > 1),
        "selected_characters": sum(end - start for start, end in selected),
    }


def evaluate_evidence(records, glossary, *, budget=3000, top_k=3):
    snapshot = compile_snapshot(glossary)
    summaries, ledgers = {}, {}
    for condition in ("none", "full", "retrieved", "ktrf_expanded"):
        totals, errors, latencies, rows = Counter(), Counter(), [], []
        for record in records:
            started = time.perf_counter()
            expanded = record["question"]
            added = []
            if condition == "ktrf_expanded":
                try:
                    result = resolve(snapshot, record["question"], mode="commit")
                    for mention in result["mentions"]:
                        if mention.get("link_decision") == "RESOLVED":
                            canonical = mention["resolved_entity"].get("canonical")
                            if canonical and canonical not in expanded and canonical not in added:
                                added.append(canonical)
                    expanded += " " + " ".join(added[:4])
                except Exception as exc:
                    errors[str(getattr(exc, "code", type(exc).__name__))] += 1
                    # Retrieval still runs on the original question; failures stay visible.
            if condition == "none":
                selected = []
            elif condition == "full":
                selected = [(0, len(record["text"]))] if record["text"] else []
            else:
                selected = select_evidence(record["text"], expanded,
                                           record["passage_candidates"], budget=budget, top_k=top_k)
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            counts = evidence_counts(record, selected)
            totals.update(counts)
            totals["query_expansion_questions"] += bool(added)
            rows.append({"document_id": record["document_id"],
                         "parent_document_id": record["parent_document_id"],
                         "document_sha256": record["document_sha256"],
                         "selected_spans": selected, "counts": counts,
                         "query_expansion_count": min(4, len(added)), "latency_ms": elapsed})
        summaries[condition] = {
            "questions": len(records), **dict(totals),
            "minimal_answer_preservation": ratio(totals["minimal_answer_preserved"],
                                                 totals["minimal_answerable_questions"]),
            "annotated_passage_preservation": ratio(totals["annotated_passage_preserved"],
                                                    totals["annotated_passage_questions"]),
            "errors": dict(errors), "failure_count": sum(errors.values()),
            "mean_selected_characters": ratio(totals["selected_characters"], len(records)),
            "latency_ms": {"p50": percentile(latencies, .5), "p95": percentile(latencies, .95),
                           "p99": percentile(latencies, .99)},
            "llm_answer_accuracy_evaluated": False,
        }
        ledgers[condition] = rows
    before = {row["document_id"]: row for row in ledgers["retrieved"]}
    after = {row["document_id"]: row for row in ledgers["ktrf_expanded"]}
    paired = Counter()
    for key, row in before.items():
        first, second = row["counts"]["minimal_answer_preserved"], after[key]["counts"]["minimal_answer_preserved"]
        paired["helpful_answer_preservation_flips"] += second > first
        paired["harmful_answer_preservation_flips"] += first > second
        paired["different_source_selection"] += row["selected_spans"] != after[key]["selected_spans"]
    return {"conditions": summaries, "paired_retrieved_vs_ktrf": dict(paired),
            "snapshot_id": snapshot.snapshot_id}, ledgers


def known_prior_documents(paths):
    hashes, parents, inspected, missing = set(), set(), [], []
    for path in paths:
        if not path.exists():
            missing.append(str(path))
            continue
        inspected.append({"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for line in path.read_text().splitlines():
            row = json.loads(line)
            text = row.get("text")
            sha = row.get("document_sha256")
            if sha:
                hashes.add(sha)
            if isinstance(text, str):
                hashes.add(hashlib.sha256(text.encode()).hexdigest())
            for key in ("parent_document_id", "document_url"):
                if row.get(key):
                    parents.add(row[key])
    return hashes, parents, {"inspected": inspected, "unavailable": missing,
                             "near_duplicate_check_performed": False}


def render_report(report):
    ner = report["kbmc_boundaries"]
    qa = report["tydiqa_evidence"]
    lines = ["# External Hugging Face benchmark", "",
             f"Measured: {report['measured_at']}; inference revision: `{report['code_revision']}`.", "",
             "KBMC measures span-reference recovery with a train-only lexical catalog. "
             "TyDiQA measures whether selected source passages retain annotated answers. "
             "Neither track measures semantic linking precision, LLM answer accuracy or production risk.", "",
             "## KBMC boundary reference", "",
             f"{report['selection']['kbmc']['selected_documents']} evaluated documents; "
             f"{report['selection']['kbmc']['training_documents']} training documents; "
             f"{report['selection']['kbmc']['catalog_entries']} lexical reference entries.", "",
             "| Mode | Exact reference hits | Overlap hits | Catalog coverage | Exact recall within catalog | Failures | p95 ms |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    def pct(value):
        return f"{value:.2%}" if value is not None else "n/a"
    for mode, row in ner["modes"].items():
        lines.append(f"| {mode} | {row.get('exact_reference_hits', 0)}/{row.get('reference_spans', 0)} "
                     f"({pct(row['exact_reference_recall'])}) | {row.get('overlap_reference_hits', 0)} | "
                     f"{pct(row['catalog_reference_coverage'])} | {pct(row['exact_recall_within_catalog'])} | "
                     f"{row['failure_count']} | {row['latency_ms']['p95']:.2f} |")
    agreement = ner["commit_aggressive_agreement"]
    lines += ["", f"Commit/aggressive mention-response differences: {agreement['different_mention_responses']} "
              f"over {agreement['compared_successful_documents']} successful matched documents.", "",
              "KBMC source sentences are LLM-generated and human-reviewed, with morpheme spacing preserved. "
              "Reference IDs denote type/surface entries, not real-world entities. "
              "Off-reference resolver output remains unjudged; no false-link precision is inferred. "
              "The split groups exact duplicate text, but allows terms/templates across partitions. "
              "It is not a family holdout or representative clinical-document test.", "",
              "## TyDiQA Korean evidence retention", "",
              f"{report['selection']['tydiqa']['selected_questions']} questions from "
              f"{report['selection']['tydiqa']['selected_parent_documents']} parent articles. "
              "All selected no-answer and yes/no questions remain in the ledger.", "",
              "| Context | Minimal answer retained | Entire annotated passage retained | Mean characters | Failures | p95 ms |",
              "|---|---:|---:|---:|---:|---:|"]
    for condition, row in qa["conditions"].items():
        lines.append(f"| {condition} | {row['minimal_answer_preserved']}/{row['minimal_answerable_questions']} "
                     f"({pct(row['minimal_answer_preservation'])}) | "
                     f"{row['annotated_passage_preserved']}/{row['annotated_passage_questions']} | "
                     f"{row['mean_selected_characters']:.1f} | {row['failure_count']} | "
                     f"{row['latency_ms']['p95']:.2f} |")
    lines += ["", "`full` is an unbudgeted information ceiling, not an equal-cost baseline. "
              "`retrieved` and `ktrf_expanded` share the candidate passages, 3,000-character allowance "
              "and three-passage cap; the latter adds up to four resolved canonical names from the question. "
              "It does not inject a production context pack or use the experimental assertion checker.", "",
              f"Selected questions with invalid source minimal-answer offsets: "
              f"{qa['conditions']['full']['invalid_minimal_annotation_questions']}. "
              "These stay in the question ledger but are unevaluable for minimal-answer retention; "
              "their positions are not guessed or corrected.", "",
              f"Paired changes: `{json.dumps(qa['paired_retrieved_vs_ktrf'], sort_keys=True)}`.", "",
              "No-context retention is zero by construction, and full-source retention is a ceiling by construction. "
              "Neither is an LLM accuracy measurement. Null/yes-no annotations are not counted as correct abstentions "
              "without an answer generator. Multiple questions from one article are correlated. "
              "Exact content and available parent IDs are checked against available prior fixtures; "
              "missing caches, Wikipedia source overlap and near-duplicates limit independence claims.", "",
              "## Reproduction and provenance", "",
              "Install `.[dev,benchmark]`, then run:", "", "```sh",
              "python -m eval.run_hf_benchmark --out-dir eval/out/hf-benchmark", "```", "",
              "See [protocol](../docs/HF_BENCHMARK.md), [dataset inventory](../docs/HF_DATASETS.md), "
              "[mode guide](../docs/MODE_EVALUATION.md) and [aggregate JSON](HF_BENCHMARK.json). "
              "The JSON records source revisions/hashes, sample and catalog hashes, counts, per-type statistics "
              "and observed runtime. Raw source text and individual ledgers are not redistributed.", "",
              "`coverage_valid=false`; `production_authorized=false`. "
              "Fixed lexical scoring and shared-host timings do not establish an operational risk or latency guarantee.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "eval/data/hf_external_v1")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ner-count", type=int, default=512)
    parser.add_argument("--qa-count", type=int, default=256)
    parser.add_argument("--catalog-size", type=int, default=512)
    parser.add_argument("--exclude-documents", type=Path, action="append", default=[])
    args = parser.parse_args()
    if min(args.ner_count, args.qa_count, args.catalog_size) < 1:
        parser.error("positive counts required")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source_manifest = acquire_sources(args.cache_dir)
    sources = source_manifest["sources"]
    ner, ner_exclusions = load_ner_records("kbmc", Path(sources["kbmc"]["path"]))
    qa, qa_exclusions = load_tydi_records(Path(sources["tydiqa_ko"]["path"]),
                                        invalid_minimal="record")
    prior_paths = [ROOT / "eval/data/wild_documents.jsonl", ROOT / "eval/data/wild_corpus.jsonl",
                   ROOT / "eval/fixtures/production_real_holdout/documents.jsonl",
                   ROOT / "eval/data/blind_review_20261013/konec/documents.jsonl",
                   ROOT / "eval/data/blind_review_20261013/koneobench/documents.jsonl",
                   *[p.resolve() for p in args.exclude_documents]]
    hashes, parents, overlap_audit = known_prior_documents(prior_paths)
    filtered_ner = [r for r in ner if r["document_sha256"] not in hashes
                    and r["parent_document_id"] not in parents]
    filtered_qa = [r for r in qa if r["document_sha256"] not in hashes
                   and r["parent_document_id"] not in parents and r["document_url"] not in parents]
    partitionable_ner, conflicting_ner = exclude_conflicting_ner(filtered_ner)
    training, heldout, duplicates = partition_ner(partitionable_ner)
    selected_ner = select_records(heldout, args.ner_count)
    selected_qa = select_records(filtered_qa, args.qa_count)
    if not training or not selected_ner or not selected_qa:
        raise ValueError("nonempty train and both evaluation cohorts required")
    reference_glossary, catalog_data = reference_catalog(training, args.catalog_size)
    selection = {
        "seed": SEED,
        "kbmc": {"loaded_documents": len(ner), "excluded_source_rows": len(ner_exclusions),
                 "prior_overlap_exclusions": len(ner) - len(filtered_ner),
                 "conflicting_annotation_text_groups": len(conflicting_ner),
                 "conflicting_annotation_source_rows": len(filtered_ner) - len(partitionable_ner),
                 "training_documents": len(training), "eligible_heldout_documents": len(heldout),
                 "exact_duplicate_rows_removed": duplicates, "selected_documents": len(selected_ner),
                 "catalog_entries": len(reference_glossary.entities), "catalog_sha256": digest(catalog_data),
                 "selection_sha256": digest([r["document_id"] for r in selected_ner]),
                 "train_parent_overlap": len({r["document_sha256"] for r in training} &
                                             {r["document_sha256"] for r in selected_ner})},
        "tydiqa": {"loaded_korean_questions": len(qa), "source_exclusions": len(qa_exclusions),
                   "prior_overlap_exclusions": len(qa) - len(filtered_qa),
                   "selected_questions": len(selected_qa),
                   "selected_parent_documents": len({r["parent_document_id"] for r in selected_qa}),
                   "selection_sha256": digest([r["document_id"] for r in selected_qa])},
    }
    # Freeze the sampling/catalog protocol before the first resolver call.
    protocol = {"schema_version": 1, "selection": selection, "source_manifest": source_manifest,
                "modes": ["literal", "fast", "commit", "aggressive"],
                "qa_conditions": ["none", "full", "retrieved", "ktrf_expanded"],
                "qa_budget_characters": 3000, "qa_max_passages": 3,
                "catalog_identity_scope": "training_type_surface_reference_only",
                "label_scope": "NER_boundaries_and_QA_evidence_only", "code_revision": revision,
                "qa_glossary_sha256": hashlib.sha256(
                    (ROOT / "examples/realorg_glossary.yaml").read_bytes()).hexdigest(),
                "evaluation_scope_git_status": subprocess.check_output(
                    ["git", "status", "--porcelain", "--", "ktrf", "eval/hf_sources.py",
                     "eval/run_hf_benchmark.py", "examples/realorg_glossary.yaml", "pyproject.toml"],
                    cwd=ROOT, text=True).splitlines(),
                "source_files": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in (Path(__file__).resolve(), ROOT / "eval/hf_sources.py")}}
    (args.out_dir / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n")
    boundaries, ner_ledger = evaluate_boundaries(selected_ner, reference_glossary)
    evidence, qa_ledger = evaluate_evidence(selected_qa, load_glossary(str(ROOT / "examples/realorg_glossary.yaml")))
    import pyarrow
    report = {"schema_version": 1, "measured_at": datetime.now(timezone.utc).isoformat(),
              "code_revision": revision,
              "protocol_sha256": hashlib.sha256((args.out_dir / "protocol.json").read_bytes()).hexdigest(),
              "source_manifest": source_manifest, "selection": selection, "prior_overlap_audit": overlap_audit,
              "kbmc_boundaries": boundaries, "tydiqa_evidence": evidence,
              "runtime": {"python": platform.python_version(), "pyarrow": pyarrow.__version__,
                          "platform": platform.platform()},
              "source_exclusion_counts": {
                  "kbmc": dict(Counter(row["reason"] for row in ner_exclusions)),
                  "tydiqa": dict(Counter(row["reason"] for row in qa_exclusions))},
              "conflicting_ner_annotations": conflicting_ner,
              "invalid_minimal_annotation_questions": [
                  {"document_id": row["document_id"], "errors": row["annotation_errors"]}
                  for row in qa if row.get("annotation_errors")],
              "coverage_valid": False, "production_authorized": False}
    (args.out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (args.out_dir / "REPORT.md").write_text(render_report(report))
    (args.out_dir / "ledgers.json").write_text(json.dumps({"ner": ner_ledger, "qa": qa_ledger},
                                                          ensure_ascii=False, indent=2) + "\n")
    (args.out_dir / "source_exclusions.json").write_text(json.dumps(
        {"kbmc": ner_exclusions, "tydiqa": qa_exclusions}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(args.out_dir / "report.json"), "selection": selection}, ensure_ascii=False))


if __name__ == "__main__":
    main()

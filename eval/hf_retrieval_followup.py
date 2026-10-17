"""Source-only retrieval follow-up, plus an explicitly gold-informed oracle.

Rankers never inspect answer annotations. The oracle is a nondeployable
diagnostic which provides one complete original annotated passage; it never
extracts, centres, or truncates a passage around a gold answer. Callers may
enforce a common actual-token source budget through ``budget_fits``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
import re
import unicodedata

from .hf_qa import EVIDENCE_POLICY, QUOTAS, classify_gold
from .run_hf_benchmark import contains_span, digest, lexical_terms


METHODS = ("lexical", "bm25", "adjacent", "oracle")
SEED = "hf-qa-retrieval-followup-v1-20261018"
PROTOCOL_ID = "hf_retrieval_followup_v1"
DEFAULT_CHAR_BUDGET = 3000
DEFAULT_TOP_K = 3


def _validated_spans(record, key):
    text = record["text"]
    spans = set()
    for span in record[key]:
        if (not isinstance(span, (list, tuple)) or len(span) != 2
                or any(type(value) is not int for value in span)):
            raise ValueError("integer source span pairs required")
        start, end = span
        if not 0 <= start < end <= len(text):
            raise ValueError("passage outside source")
        spans.add((start, end))
    return sorted(spans)


def _chunks(record):
    # Match the existing lexical selector's 1000-character windows, 100 overlap.
    candidates = set()
    for start, end in _validated_spans(record, "passage_candidates"):
        cursor = start
        while cursor < end:
            finish = min(cursor + 1000, end)
            candidates.add((cursor, finish))
            if finish == end:
                break
            cursor = finish - 100
    return sorted(candidates)


def _bm25_terms(text):
    """Frequency-bearing words and Hangul bigrams, without a model dependency."""
    terms = Counter()
    normalized = unicodedata.normalize("NFC", text).casefold()
    for word in re.findall(r"[가-힣]+|[a-z0-9]+", normalized):
        terms["word:" + word] += 1
        if re.fullmatch(r"[가-힣]+", word):
            terms.update("gram:" + word[i:i + 2] for i in range(len(word) - 1))
    return terms


def _oracle_ranked_passages(record):
    gold = classify_gold(record)
    if not gold["positive"]:
        return []
    original = _validated_spans(record, "passage_candidates")
    allowed = set(_validated_spans(record, "answer_passage_spans"))
    # Annotation indexes address the original, unsorted candidate list.
    votes = Counter()
    for annotation in record["annotation_answers"]:
        index = annotation.get("passage_index", -1)
        if annotation["answer_type"] in {"SPAN", "YES_NO"} and index >= 0:
            if type(index) is not int or index >= len(record["passage_candidates"]):
                raise ValueError("gold passage index outside source candidates")
            votes[tuple(record["passage_candidates"][index])] += 1
    # Only original annotated passages qualify. A minimal span can never be
    # fabricated into a source passage, even if its parent annotation is absent.
    candidates = [span for span in original if span in allowed and votes[span]]
    if gold["stratum"] == "SPAN":
        answers = _validated_spans(record, "answer_spans")
        candidates = [span for span in candidates
                      if any(contains_span([span], answer) for answer in answers)]
    return sorted(candidates, key=lambda span: (-votes[span], span[0], span[1]))


def ranked_passages(record, method):
    """Return deterministic source spans ordered by question-only relevance.

    ``adjacent`` visits each lexical centre, then its preceding and following
    source windows, before visiting the next centre. Greedy nonoverlap checks
    happen during selection. ``oracle`` is the sole gold-informed method.
    """
    if method not in METHODS:
        raise ValueError("unknown retrieval method")
    if method == "oracle":
        return _oracle_ranked_passages(record)
    candidates = _chunks(record)
    if method in {"lexical", "adjacent"}:
        query = lexical_terms(record["question"])
        scored = []
        for start, end in candidates:
            terms = lexical_terms(record["text"][start:end])
            score = len(query & terms) / math.sqrt(max(1, len(terms)))
            scored.append((-score, start, end))
        centres = [(start, end) for _, start, end in sorted(scored)]
        if method == "lexical":
            return centres
        neighbours, seen = [], set()
        indexes = {span: index for index, span in enumerate(candidates)}
        for centre in centres:
            index = indexes[centre]
            for candidate_index in (index, index - 1, index + 1):
                if 0 <= candidate_index < len(candidates):
                    span = candidates[candidate_index]
                    if span not in seen:
                        neighbours.append(span)
                        seen.add(span)
        return neighbours
    query = _bm25_terms(record["question"])
    bags = [_bm25_terms(record["text"][start:end]) for start, end in candidates]
    frequency = Counter(term for bag in bags for term in bag)
    average_length = sum(sum(bag.values()) for bag in bags) / max(1, len(bags))
    scored = []
    for (start, end), bag in zip(candidates, bags):
        length = sum(bag.values())
        score = 0.0
        for term in query:
            count = bag[term]
            if not count:
                continue
            inverse_frequency = math.log1p((len(bags) - frequency[term] + .5)
                                           / (frequency[term] + .5))
            normalizer = count + 1.2 * (.25 + .75 * length / max(1, average_length))
            score += inverse_frequency * count * 2.2 / normalizer
        scored.append((-score, start, end))
    return [(start, end) for _, start, end in sorted(scored)]


def _select(record, method, *, budget_fits, char_budget, top_k):
    ranked = ranked_passages(record, method)
    selected, used = [], 0
    for start, end in ranked:
        if any(start < previous_end and previous_start < end
               for previous_start, previous_end in selected):
            continue
        if used + end - start > char_budget:
            continue
        proposed = sorted(selected + [(start, end)])
        if budget_fits is not None and not budget_fits(proposed):
            continue
        selected, used = proposed, used + end - start
        if len(selected) == top_k or method == "oracle":
            break
    return selected


def build_variants(record, snapshot=None, *, budget_fits=None,
                   char_budget=DEFAULT_CHAR_BUDGET, top_k=DEFAULT_TOP_K):
    """Build four matched evidence-only generation rows without model calls.

    ``snapshot`` is accepted for preparation-call compatibility but is unused;
    none of these four rows injects a glossary pack. ``budget_fits`` receives
    sorted source spans and must accept only budgets fitting *both* models.
    All spans preserve original Python codepoint offsets and document order.
    A positive oracle that cannot fit a complete annotated passage stays empty
    and is explicitly marked; it is never silently replaced or truncated.
    """
    if type(char_budget) is not int or char_budget < 1 or type(top_k) is not int or top_k < 1:
        raise ValueError("positive integer character budget and top_k required")
    gold = classify_gold(record)
    if gold["reason"]:
        raise ValueError("unscorable source gold cannot enter generation requests")
    text = record["text"]
    if hashlib.sha256(text.encode()).hexdigest() != record["document_sha256"]:
        raise ValueError("source text changed")
    selections = {method: _select(record, method, budget_fits=budget_fits,
                                  char_budget=char_budget, top_k=top_k)
                  for method in METHODS if method != "oracle"}
    oracle_candidates = _oracle_ranked_passages(record)
    selections["oracle"] = (_select(record, "oracle", budget_fits=budget_fits,
                                    char_budget=char_budget, top_k=top_k)
                            if gold["positive"] else selections["lexical"])
    rows = []
    for method in METHODS:
        spans = selections[method]
        relevant = record["answer_passage_spans"] if gold["stratum"] == "YES_NO" else record["answer_spans"]
        rendered = "\n\n".join(text[start:end] for start, end in spans)
        oracle_status = ("NOT_ORACLE" if method != "oracle" else
                         "NEGATIVE_MATCHED_LEXICAL" if not gold["positive"] else
                         "GOLD_PASSAGE_FITS" if spans else
                         "GOLD_PASSAGE_OVER_BUDGET" if oracle_candidates else
                         "NO_ANNOTATED_PASSAGE")
        rows.append({"case_id": record["document_id"] + "::followup",
            "condition": method + "__free__r0", "experiment": "retrieval",
            "context_condition": method, "decoding_mode": "free", "repeat_id": 0,
            "task": "document_qa", "document_id": record["document_id"],
            "parent_document_id": record["parent_document_id"],
            "document_sha256": record["document_sha256"], "source_text": text,
            "question": record["question"], "stratum": gold["stratum"],
            "positive_gold": gold["positive"], "expected_answers": gold["expected_answers"],
            "nonnull_votes": gold["nonnull_votes"], "source_spans": spans,
            "answer_spans": record["answer_spans"],
            "answer_passage_spans": record["answer_passage_spans"],
            "source_gold_visible": any(contains_span(spans, span) for span in relevant)
                                   if gold["positive"] else None,
            "source_character_count": sum(end - start for start, end in spans),
            "source_character_budget": char_budget, "source_top_k": top_k,
            "oracle_budget_fit": bool(spans) if method == "oracle" and gold["positive"] else None,
            "oracle_status": oracle_status,
            "oracle_uses_gold": bool(method == "oracle" and gold["positive"]),
            "deployable_condition": method != "oracle",
            "pack_injected": False, "pack_prompt": None, "pack_policy": None,
            "system": EVIDENCE_POLICY,
            "user": "질문: " + record["question"] + "\n\n<source>\n" + rendered + "\n</source>"})
    return rows


def choose_heldout(records, *, excluded_parents=(), excluded_hashes=(),
                   quotas=None, eligible=None):
    """Freeze independent parent articles in deterministic source-ID order.

    Call only before held-out model outputs. ``eligible`` may test previously
    declared capacity rules, including complete-oracle feasibility. Counts and
    reasons remain aggregate; IDs/text are returned only in the private rows.
    """
    quotas = dict(QUOTAS if quotas is None else quotas)
    if not quotas or set(quotas) - set(QUOTAS) or any(type(n) is not int or n < 0 for n in quotas.values()):
        raise ValueError("known nonnegative stratum quotas required")
    parents, hashes = set(excluded_parents), set(excluded_hashes)
    groups, exclusions = defaultdict(list), Counter()
    unique = set()
    for record in records:
        if record["document_id"] in unique:
            raise ValueError("duplicate source question ID")
        unique.add(record["document_id"])
        if record["parent_document_id"] in parents or record["document_sha256"] in hashes:
            exclusions["prior_parent_or_content_overlap"] += 1
            continue
        gold = classify_gold(record)
        if gold["reason"]:
            exclusions[gold["reason"]] += 1
            continue
        if gold["stratum"] not in quotas or quotas[gold["stratum"]] == 0:
            continue
        if eligible is not None and not eligible(record):
            exclusions["predeclared_capacity_rule"] += 1
            continue
        groups[gold["stratum"]].append(record)
    chosen, used_parents, used_hashes = [], set(), set()
    for kind in ("YES_NO", "SPAN", "NO_ANSWER"):
        quota = quotas.get(kind, 0)
        count = 0
        for record in sorted(groups[kind], key=lambda row: (digest([SEED, row["document_id"]]), row["document_id"])):
            if count == quota:
                break
            parent, sha = record["parent_document_id"], record["document_sha256"]
            if parent in used_parents or sha in used_hashes:
                continue
            chosen.append(record)
            used_parents.add(parent)
            used_hashes.add(sha)
            count += 1
    counts = Counter(classify_gold(row)["stratum"] for row in chosen)
    inventory = {"seed": SEED, "source_questions": len(records), "quotas": quotas,
        "eligible_by_stratum": {kind: len(groups[kind]) for kind in quotas},
        "selected_by_stratum": {kind: counts[kind] for kind in quotas},
        "exclusions": dict(exclusions), "excluded_parent_count": len(parents),
        "excluded_content_hash_count": len(hashes), "parent_articles": len(used_parents),
        "one_question_per_parent_article": True, "unique_content_hashes": len(used_hashes),
        "selection_before_generation_outputs": True,
        "question_ids_sha256": digest(sorted(row["document_id"] for row in chosen))}
    if any(counts[kind] != quota for kind, quota in quotas.items()):
        error = ValueError("INSUFFICIENT_DATA: not enough independent parent articles for declared quotas")
        error.inventory = inventory
        raise error
    chosen.sort(key=lambda row: (digest([SEED, row["document_id"]]), row["document_id"]))
    return chosen, inventory


def evaluate_retrieval(records, *, budget_fits_factory=None,
                       char_budget=DEFAULT_CHAR_BUDGET, top_k=DEFAULT_TOP_K):
    """Aggregate gold visibility only; no LLM correctness or link-ID claim."""
    counts = {method: Counter() for method in METHODS}
    strata = {method: defaultdict(Counter) for method in METHODS}
    source_selections = {method: [] for method in METHODS}
    for record in records:
        budget_fits = budget_fits_factory(record) if budget_fits_factory else None
        rows = build_variants(record, budget_fits=budget_fits, char_budget=char_budget, top_k=top_k)
        lexical = rows[0]["source_spans"]
        for row in rows:
            method = row["context_condition"]
            values = {"questions": 1, "positive_questions": int(row["positive_gold"]),
                "gold_visible": int(row["source_gold_visible"] is True),
                "source_characters": row["source_character_count"],
                "source_passages": len(row["source_spans"]),
                "empty_sources": int(not row["source_spans"]),
                "changed_from_lexical": int(row["source_spans"] != lexical),
                "oracle_unavailable": int(row["context_condition"] == "oracle"
                                          and row["positive_gold"] and not row["oracle_budget_fit"])}
            counts[method].update(values)
            strata[method][row["stratum"]].update(values)
            source_selections[method].append([record["document_id"], row["source_spans"]])
    summaries = {}
    for method in METHODS:
        total = counts[method]
        summaries[method] = {**dict(total),
            "gold_visibility_rate": total["gold_visible"] / total["positive_questions"]
                                    if total["positive_questions"] else None,
            "by_stratum": {kind: dict(values) for kind, values in sorted(strata[method].items())},
            "selected_source_spans_sha256": digest(source_selections[method]),
            "gold_informed_diagnostic": method == "oracle"}
    winner = min(("lexical", "bm25", "adjacent"),
                 key=lambda method: (-counts[method]["gold_visible"], METHODS.index(method)))
    return {"protocol": PROTOCOL_ID, "questions": len(records), "methods": summaries,
        "character_budget": char_budget, "top_k": top_k,
        "additional_actual_token_budget_enforced": budget_fits_factory is not None,
        "deployable_winner_by_visibility": winner,
        "winner_tie_policy": "lexical_then_bm25_then_adjacent",
        "selection_metric": "positive_question_any_gold_span_or_yesno_passage_visible",
        "llm_accuracy_measured": False, "entity_linking_measured": False,
        "oracle_deployable": False}

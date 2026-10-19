"""Freeze four bounded QA diagnostics without generation or gold-aware retrieval.

The transfer sample is selected once. Budget, corpus, and format/policy tracks
reuse declared nested subsets; they are not four independent validation sets.
Raw texts, questions, packs and per-question diagnostics remain private.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import unicodedata

from ktrf import ContextPolicy, prepare_llm_context, render_context_pack
from .hf_qa import EVIDENCE_POLICY, canonical
from .hf_retrieval_followup import _bm25_terms, ranked_passages
from .prepare_followup import MAX_MODEL_LEN, RESERVED_OUTPUT_TOKENS, SOURCE_TOKEN_CAP, _token_ids
from .run_hf_benchmark import contains_span, digest, lexical_terms

PROTOCOL_ID = "ktrf_extended_v1"
SEED = "ktrf-extended-qa-v1-20261019"
TRANSFER_PER_STRATUM = 128
SUBSET_PER_STRATUM = 64
CORPUS_DOCUMENTS = 512
CHAR_CAP = 3000
WINDOW_CAP = 3
BUDGET_CAPS = (1024, 1536)
OVERLAP_POLICY = {"normalization": "NFC casefold alphanumeric", "ngram": 5,
                  "containment_threshold": .9, "min_normalized_chars": 40,
                  "exact_sentence_min_normalized_chars": 40}


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _normalize(text):
    return "".join(c for c in unicodedata.normalize("NFC", text).casefold() if c.isalnum())


def _sentences(text):
    return {_normalize(part) for part in re.split(r"[.!?。！？\n]+", text)
            if len(_normalize(part)) >= OVERLAP_POLICY["exact_sentence_min_normalized_chars"]}


class OverlapIndex:
    """Exact/sentence overlap plus complete 5-gram containment candidate counts.

    Inverted postings avoid comparing every pair of long source documents.
    Shared-gram counts are exact; no approximate shortlist can hide a document
    meeting the declared containment threshold.
    """

    def __init__(self, texts=()):
        self.normalized, self.exact, self.sentences = [], set(), set()
        self.postings, self.sizes = defaultdict(set), []
        for text in texts:
            self.add(text)

    @staticmethod
    def _grams(text):
        return {text[i:i + 5] for i in range(max(0, len(text) - 4))}

    def add(self, text):
        normalized = _normalize(text)
        if not normalized or normalized in self.exact:
            return
        index = len(self.normalized)
        self.normalized.append(normalized)
        self.exact.add(normalized)
        self.sentences.update(_sentences(text))
        grams = self._grams(normalized) if len(normalized) >= 40 else set()
        self.sizes.append(len(grams))
        for gram in grams:
            self.postings[gram].add(index)

    def reason(self, text):
        normalized = _normalize(text)
        if normalized in self.exact:
            return "normalized_exact_overlap"
        if self.sentences & _sentences(text):
            return "exact_sentence_overlap"
        if len(normalized) < 40:
            return None
        grams = self._grams(normalized)
        hits = Counter(index for gram in grams for index in self.postings.get(gram, ()))
        for index, count in hits.items():
            denominator = min(len(grams), self.sizes[index])
            if denominator and count / denominator >= .9:
                return "character_5gram_containment"
        return None


def load_mrc_records(path):
    """Read local KLUE MRC data, validating codepoint gold before selection.

    Impossible questions may carry plausible distractor answers. Their strings
    and offsets are intentionally discarded, never promoted to positive gold.
    """
    path = Path(path)
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        rows = pq.read_table(path).to_pylist()
    elif path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    else:
        value = json.loads(path.read_text())
        rows = value if isinstance(value, list) else value.get("data", value.get("records", []))
    accepted, invalid, seen = [], Counter(), set()
    for row in rows:
        try:
            text, question = row["context"], row["question"]
            identifier = row.get("guid", row.get("id", row.get("document_id")))
            if not isinstance(identifier, str) or not identifier or identifier in seen:
                raise ValueError("missing_or_duplicate_question_id")
            seen.add(identifier)
            if not isinstance(text, str) or not text.strip() or not isinstance(question, str) or not question.strip():
                raise ValueError("empty_text_or_question")
            impossible = row["is_impossible"]
            if type(impossible) is not bool:
                raise ValueError("invalid_impossible_label")
            answer_spans, answers = [], []
            if not impossible:
                gold = row["answers"]
                if not isinstance(gold, dict) or len(gold["text"]) != len(gold["answer_start"]):
                    raise ValueError("invalid_answer_arrays")
                for answer, start in zip(gold["text"], gold["answer_start"]):
                    if not isinstance(answer, str) or not answer or type(start) is not int:
                        raise ValueError("invalid_answer_span")
                    end = start + len(answer)
                    if not 0 <= start < end <= len(text) or text[start:end] != answer:
                        raise ValueError("invalid_answer_span")
                    answer_spans.append([start, end])
                    answers.append(answer)
                if not answers:
                    raise ValueError("positive_without_answer")
            sha = _sha(text)
            # KLUE exposes passage contexts, not a reliable original article ID.
            # Context identity is retained honestly rather than fabricated from title.
            parent = row.get("parent_document_id") or "klue-mrc-context:" + sha
            accepted.append({"document_id": identifier, "parent_document_id": parent,
                "document_sha256": sha, "text": text, "question": question,
                "stratum": "NO_ANSWER" if impossible else "SPAN", "positive_gold": not impossible,
                "expected_answers": sorted(set(answers)), "answer_spans": sorted(set(map(tuple, answer_spans))),
                "title": row.get("title", ""), "source": "klue/klue:mrc",
                "parent_identity_scope": "provided_parent" if row.get("parent_document_id") else "context_hash"})
        except (KeyError, TypeError, ValueError) as exc:
            invalid[str(exc) if isinstance(exc, ValueError) else "malformed_fields"] += 1
    return accepted, {"source_rows": len(rows), "valid_rows": len(accepted),
        "rejected_rows": sum(invalid.values()), "rejections": dict(sorted(invalid.items())),
        "valid_strata": dict(Counter(row["stratum"] for row in accepted)),
        "impossible_plausible_answers_never_used_as_gold": True,
        "parent_identity_limit": "Absent source parent IDs are context hashes, not verified original articles."}


def _validate_record(record):
    if not record.get("document_id") or not record.get("parent_document_id") or not record.get("question"):
        raise ValueError("source question and parent identities required")
    if not isinstance(record.get("text"), str) or _sha(record["text"]) != record["document_sha256"]:
        raise ValueError("source text hash differs")
    if record["stratum"] not in {"SPAN", "NO_ANSWER"} or record["positive_gold"] != (record["stratum"] == "SPAN"):
        raise ValueError("source stratum disagrees with gold")
    if bool(record["expected_answers"]) != record["positive_gold"]:
        raise ValueError("source answers disagree with gold")
    if not record["positive_gold"] and record["answer_spans"]:
        raise ValueError("impossible plausible spans cannot be positive gold")
    found = set()
    for span in record["answer_spans"]:
        if (not isinstance(span, (list, tuple)) or len(span) != 2 or
                any(type(n) is not int for n in span) or not 0 <= span[0] < span[1] <= len(record["text"])):
            raise ValueError("invalid codepoint answer span")
        found.add(record["text"][span[0]:span[1]])
    if found != set(record["expected_answers"]):
        raise ValueError("answer spans disagree with expected answers")


def select_samples(records, exclusion_texts=()):
    """Select fixed strata before any ranking, pack construction or token fitting."""
    excluded_parents, excluded_texts = set(), []
    for value in exclusion_texts:
        if isinstance(value, str):
            excluded_texts.append(value)
        elif isinstance(value, dict):
            if value.get("parent_document_id"):
                excluded_parents.add(value["parent_document_id"])
            text = value.get("text", value.get("source_text"))
            if isinstance(text, str):
                excluded_texts.append(text)
        else:
            raise ValueError("exclusion inputs require text or source records")
    prior = OverlapIndex(excluded_texts)
    eligible, exclusions, identifiers = [], Counter(), set()
    overlap_cache = {}
    for row in sorted(records, key=lambda row: (digest([SEED, row["document_id"]]), row["document_id"])):
        _validate_record(row)
        if row["document_id"] in identifiers:
            raise ValueError("duplicate source question ID")
        identifiers.add(row["document_id"])
        if row["parent_document_id"] in excluded_parents:
            exclusions["prior_parent_overlap"] += 1
            continue
        sha = row["document_sha256"]
        if sha not in overlap_cache:
            overlap_cache[sha] = prior.reason(row["text"])
        reason = overlap_cache[sha]
        if reason:
            exclusions[reason] += 1
            continue
        eligible.append(row)
    chosen, parents, hashes = [], set(), set()
    selected_overlap = OverlapIndex()
    counts = Counter()
    for stratum in ("SPAN", "NO_ANSWER"):
        for row in eligible:
            if row["stratum"] != stratum or counts[stratum] == TRANSFER_PER_STRATUM:
                continue
            if row["parent_document_id"] in parents or row["document_sha256"] in hashes:
                continue
            if selected_overlap.reason(row["text"]):
                continue
            chosen.append(row)
            parents.add(row["parent_document_id"])
            hashes.add(row["document_sha256"])
            selected_overlap.add(row["text"])
            counts[stratum] += 1
    inventory = {"seed": SEED, "source_questions": len(records),
        "eligible_questions": len(eligible), "selected_strata": dict(counts),
        "quotas": {"SPAN": TRANSFER_PER_STRATUM, "NO_ANSWER": TRANSFER_PER_STRATUM},
        "exclusions": dict(exclusions), "exclusion_unique_texts": len(set(excluded_texts)),
        "exclusion_text_hashes_sha256": digest(sorted({_sha(text) for text in excluded_texts})),
        "excluded_parent_count": len(excluded_parents), "overlap_policy": OVERLAP_POLICY,
        "selection_before_generation_outputs": True, "pack_eligibility_used_for_selection": False,
        "retrieval_success_used_for_selection": False, "parent_units": len(parents),
        "selected_question_ids_sha256": digest(sorted(row["document_id"] for row in chosen))}
    if any(counts[kind] != TRANSFER_PER_STRATUM for kind in ("SPAN", "NO_ANSWER")):
        error = ValueError("INSUFFICIENT_DATA: distinct nonoverlapping parent contexts for declared strata")
        error.inventory = inventory
        raise error
    subset = [row for kind in ("SPAN", "NO_ANSWER")
              for row in [r for r in chosen if r["stratum"] == kind][:SUBSET_PER_STRATUM]]
    return chosen, subset, eligible, inventory


class PromptBudget:
    def __init__(self, tokenizers):
        self.tokenizers, self.prompt_cache, self.source_cache = tokenizers, {}, {}

    def source_lengths(self, text):
        if text not in self.source_cache:
            self.source_cache[text] = {key: len(_token_ids(tok.encode(text, add_special_tokens=False)))
                                      for key, tok in self.tokenizers.items()}
        return self.source_cache[text]

    def prompt_lengths(self, system, user):
        key = (system, user)
        if key not in self.prompt_cache:
            self.prompt_cache[key] = {name: len(_token_ids(tok.apply_chat_template(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False)))
                for name, tok in self.tokenizers.items()}
        return self.prompt_cache[key]


def source_only_record(text, question):
    """Construct a retrieval input that cannot reveal parent IDs or answer gold."""
    return {"text": text, "question": question, "passage_candidates": [[0, len(text)]]}


def select_windows(text, question, method, budget, *, fits=None):
    selected = []
    for start, end in ranked_passages(source_only_record(text, question), method):
        if any(start < b and a < end for a, b in selected):
            continue
        remaining = CHAR_CAP - sum(b - a for a, b in selected) - 2 * len(selected)
        end = min(end, start + remaining)
        if end <= start:
            continue

        def valid(finish):
            spans = sorted([*selected, (start, finish)])
            source = "\n\n".join(text[a:b] for a, b in spans)
            return (all(n <= SOURCE_TOKEN_CAP for n in budget.source_lengths(source).values())
                    and (fits is None or fits(source)))

        if not valid(end):
            # Source prefixes are independent of gold. Always measure the final
            # candidate, even when tokenization/pack changes are nonmonotonic.
            low, high, best = start + 1, end - 1, None
            while low <= high:
                middle = (low + high) // 2
                if valid(middle):
                    best, low = middle, middle + 1
                else:
                    high = middle - 1
            if best is None:
                continue
            end = best
        if not valid(end):
            raise ValueError("selected source prefix failed final budget measurement")
        selected.append((start, end))
        selected.sort()
        if len(selected) == WINDOW_CAP:
            break
    return selected


class CorpusIndex:
    """Document retrieval API accepts only a query; it never sees anchor gold."""
    def __init__(self, documents):
        self.documents = sorted(({key: row[key] for key in (
            "parent_document_id", "document_sha256", "text")} for row in documents),
            key=lambda row: row["document_sha256"])
        self.lexical = [lexical_terms(row["text"]) for row in self.documents]
        self.bags = [_bm25_terms(row["text"]) for row in self.documents]
        self.frequency = Counter(term for bag in self.bags for term in bag)
        self.lengths = [sum(bag.values()) for bag in self.bags]
        self.average = sum(self.lengths) / max(1, len(self.bags))

    def search(self, question, method):
        scores = []
        query = lexical_terms(question) if method == "lexical" else _bm25_terms(question)
        for index, row in enumerate(self.documents):
            if method == "lexical":
                score = len(query & self.lexical[index]) / math.sqrt(max(1, len(self.lexical[index])))
            elif method == "bm25":
                bag, score = self.bags[index], 0.0
                for term in query:
                    count = bag[term]
                    if count:
                        idf = math.log1p((len(self.bags) - self.frequency[term] + .5) /
                                        (self.frequency[term] + .5))
                        normalizer = count + 1.2 * (.25 + .75 * self.lengths[index] / max(1, self.average))
                        score += idf * count * 2.2 / normalizer
            else:
                raise ValueError("unsupported document ranker")
            scores.append((-score, row["document_sha256"], index))
        return [self.documents[index] for _, _, index in sorted(scores)]


def _corpus_pool(positives, eligible):
    chosen = list(positives)
    parents = {row["parent_document_id"] for row in chosen}
    hashes = {row["document_sha256"] for row in chosen}
    for row in eligible:
        if len(chosen) == CORPUS_DOCUMENTS:
            break
        if row["parent_document_id"] in parents or row["document_sha256"] in hashes:
            continue
        chosen.append(row)
        parents.add(row["parent_document_id"])
        hashes.add(row["document_sha256"])
    if len(chosen) != CORPUS_DOCUMENTS:
        raise ValueError("INSUFFICIENT_DATA: bounded corpus needs declared unique contexts")
    return chosen


def _fact_projection(pack):
    """Exactly the facts consumed by the production text renderer, in both arms."""
    resolved, ambiguous = [], []
    for card in pack["resolved_terms"]:
        mentions = []
        for mention in card["mentions"]:
            value = {"surface": mention["surface"]}
            if mention.get("appears_inside"):
                value["appears_inside"] = {"surface": mention["appears_inside"]["surface"]}
            if value not in mentions:
                mentions.append(value)
        resolved.append({"canonical": card["canonical"], "short_definition": card["short_definition"],
                         "mentions": mentions})
    for mention in pack["ambiguous_mentions"]:
        value = {"surface": mention["surface"], "candidates": [
            {key: card[key] for key in ("canonical", "short_definition")}
            for card in mention["candidates"]]}
        if mention.get("appears_inside"):
            value["appears_inside"] = {"surface": mention["appears_inside"]["surface"]}
        ambiguous.append(value)
    return {"resolved_terms": resolved, "ambiguous_mentions": ambiguous}


def _pack_render(pack, format):
    rendered = render_context_pack(pack, format)
    if format == "json":
        return rendered.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return escape(rendered, quote=False)


class RequestBuilder:
    def __init__(self, snapshot, budget):
        self.snapshot, self.budget, self.prepared = snapshot, budget, {}

    def pack(self, question, source):
        key = (question, source)
        if key not in self.prepared:
            self.prepared[key] = prepare_llm_context(self.snapshot, question + "\n" + source,
                query=question, mode="commit", context_policy=ContextPolicy(profile="qa_grounding", max_tokens=800))
        return self.prepared[key]

    def prompts(self, question, source, *, with_pack=False, format="xml", conservative=True):
        prepared = self.pack(question, source) if with_pack else None
        injected = bool(prepared and prepared.should_inject)
        system = EVIDENCE_POLICY
        user = "질문: " + escape(question, quote=False) + "\n\n<source>\n" + escape(source, quote=False) + "\n</source>"
        facts = _fact_projection(prepared.context_pack) if injected and format in {"text", "json"} else None
        pack = facts if facts is not None else prepared.context_pack if injected else None
        fragment = (prepared.prompt_fragment if format == "xml" else _pack_render(pack, format)) if injected else None
        if injected:
            user += "\n\n<terminology>\n" + fragment + "\n</terminology>"
            if conservative:
                system += "\n\n" + prepared.policy_fragment
        return {"system": system, "user": user, "pack_injected": injected,
            "pack_sha256": digest(prepared.context_pack) if prepared else None,
            "fact_cards_sha256": digest(facts) if facts is not None else None,
            "fact_cards": facts, "pack_prompt": fragment,
            "pack_policy": prepared.policy_fragment if injected and conservative else None,
            "pack_format": format if with_pack else None,
            "policy_factor": "conservative" if with_pack and conservative else "neutral",
            "prompt_tokens": self.budget.prompt_lengths(system, user)}

    def row(self, record, experiment, condition, source, spans, **prompt_args):
        prompts = self.prompts(record["question"], source, **prompt_args)
        return {"case_id": record["document_id"] + "::" + experiment,
            "condition": condition, "experiment": experiment, "task": "document_qa", "repeat_id": 0,
            "decoding_mode": "json_schema", "document_id": record["document_id"],
            "parent_document_id": record["parent_document_id"], "document_sha256": record["document_sha256"],
            "source_text": record["text"], "question": record["question"], "stratum": record["stratum"],
            "positive_gold": record["positive_gold"], "expected_answers": record["expected_answers"],
            "answer_spans": record["answer_spans"], "source_spans": spans,
            "source_gold_visible": any(contains_span(spans, span) for span in record["answer_spans"])
                                   if record["positive_gold"] else None,
            "rendered_source_sha256": _sha(source), "source_character_count": len(source),
            "source_tokens": self.budget.source_lengths(source), **prompts}


def _ordered(rows, experiment):
    cases = defaultdict(list)
    for row in rows:
        cases[row["case_id"]].append(row)
    result = []
    for index, identifier in enumerate(sorted(cases, key=lambda value: digest([SEED, experiment, value]))):
        case = sorted(cases[identifier], key=lambda row: row["condition"])
        offset = index % len(case)
        result.extend(case[offset:] + case[:offset])
    return result


def prepare_qa(records, snapshot, tokenizers, models, *, code_revision, source_identity, exclusion_texts=()):
    if not code_revision or not tokenizers or set(models) != set(tokenizers):
        raise ValueError("frozen revision and matching actual model tokenizers required")
    selected, subset, eligible, selection = select_samples(records, exclusion_texts)
    positives = [row for row in selected if row["positive_gold"]]
    corpus_pool = _corpus_pool(positives, eligible)
    corpus = CorpusIndex(corpus_pool)
    budget = PromptBudget(tokenizers)
    builder = RequestBuilder(snapshot, budget)
    tracks = {name: [] for name in ("transfer", "budget", "corpus", "pack")}
    windows = {}
    for record in selected:
        for ranker in ("lexical", "bm25"):
            spans = select_windows(record["text"], record["question"], ranker, budget)
            windows[(record["document_id"], ranker)] = spans
            source = "\n\n".join(record["text"][a:b] for a, b in spans)
            for with_pack in (False, True):
                condition = ranker + ("_pack" if with_pack else "")
                tracks["transfer"].append(builder.row(record, "transfer", condition, source, spans,
                                                        with_pack=with_pack))
    for record in subset:
        for cap in BUDGET_CAPS:
            for with_pack in (False, True):
                def fits(source):
                    return all(n <= cap for n in builder.prompts(record["question"], source,
                        with_pack=with_pack)["prompt_tokens"].values())
                if not fits(""):
                    raise ValueError("fixed policy/question/pack exceeds total prompt cap even without source")
                spans = select_windows(record["text"], record["question"], "bm25", budget, fits=fits)
                source = "\n\n".join(record["text"][a:b] for a, b in spans)
                row = builder.row(record, "budget", f"cap{cap}_bm25" + ("_pack" if with_pack else ""),
                                  source, spans, with_pack=with_pack)
                row.update(total_prompt_token_cap=cap, prompt_budget_utilization={
                    model: n / cap for model, n in row["prompt_tokens"].items()})
                tracks["budget"].append(row)
        spans = windows[(record["document_id"], "bm25")]
        source = "\n\n".join(record["text"][a:b] for a, b in spans)
        tracks["pack"].append(builder.row(record, "pack", "none", source, spans))
        for format in ("text", "json"):
            for conservative in (False, True):
                condition = format + ("_conservative" if conservative else "_neutral")
                tracks["pack"].append(builder.row(record, "pack", condition, source, spans,
                    with_pack=True, format=format, conservative=conservative))
    for record in positives:
        for ranker in ("lexical", "bm25"):
            ranked = corpus.search(record["question"], ranker)
            selected_documents, source_parts, source_spans = [], [], []
            for document in ranked[:WINDOW_CAP]:
                candidate_spans = ranked_passages(source_only_record(document["text"], record["question"]), ranker)
                if not candidate_spans:
                    continue
                start, end = candidate_spans[0]
                available = CHAR_CAP - len("\n\n".join(source_parts)) - (2 if source_parts else 0)
                end = min(end, start + available)
                while end > start:
                    part = document["text"][start:end]
                    proposed = "\n\n".join([*source_parts, part])
                    if all(n <= SOURCE_TOKEN_CAP for n in budget.source_lengths(proposed).values()):
                        break
                    end -= max(1, (end - start) // 8)
                if end <= start:
                    continue
                source_parts.append(document["text"][start:end])
                selected_documents.append({"parent_document_id": document["parent_document_id"],
                    "document_sha256": document["document_sha256"], "spans": [[start, end]],
                    "text": document["text"][start:end]})
                if document["document_sha256"] == record["document_sha256"]:
                    source_spans.append((start, end))
            source = "\n\n".join(source_parts)
            for with_pack in (False, True):
                condition = ranker + ("_pack" if with_pack else "")
                row = builder.row(record, "corpus", condition, source, source_spans, with_pack=with_pack)
                row.update(selected_documents=deepcopy(selected_documents),
                    anchor_document_rank=next(i + 1 for i, doc in enumerate(ranked)
                                              if doc["document_sha256"] == record["document_sha256"]),
                    anchor_document_retrieved=any(doc["document_sha256"] == record["document_sha256"]
                                                  for doc in selected_documents),
                    corpus_document_count=len(corpus_pool))
                tracks["corpus"].append(row)
    identity = {"code_revision": code_revision, "source": source_identity,
        "snapshot_id": snapshot.snapshot_id, "selection": selection,
        "corpus_document_hashes_sha256": digest(sorted(row["document_sha256"] for row in corpus_pool))}
    limitations = [
        "Stratified contexts do not represent the original KLUE MRC question distribution.",
        "Absent original article IDs use context hashes; parent contexts are not verified independent original articles.",
        "Declared prior exact, normalized, sentence and 5-gram overlap is excluded; semantic and pretraining overlap remain possible.",
        "All tracks reuse nested subsets of one frozen sample and are not independent replication datasets.",
        "Corpus retrieval uses positive questions only because impossible labels apply only to the original source context.",
        "The bounded 512-context corpus deliberately contains every positive anchor; it is not open-web retrieval.",
        "Equal prompt caps measure complete actual chat templates; consumption may differ and no padding is added.",
        "Budget prefixes are source-only deterministic choices, not gold-centered windows or an optimal knapsack solution.",
        "Format comparison renders the same minimal fact cards; full production metadata is deliberately absent from both formats.",
        "Neutral and conservative policies both remain evidence-only; no arm grants execution authority.",
        "No output-based, retrieval-hit-based or pack-injection-based sample filtering is performed.",
        "All conditions use JSON Schema and one generation; normalized EM is a diagnostic, not an official leaderboard score."]
    envelopes, experiments = {}, {}
    for name, unordered in tracks.items():
        rows = _ordered(unordered, name)
        proofs = {}
        for model in models:
            lengths = [row["prompt_tokens"][model] for row in rows]
            overflow = sum(n + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN for n in lengths)
            if overflow or any(max(row["source_tokens"].values()) > SOURCE_TOKEN_CAP for row in rows):
                raise ValueError("final frozen prompts exceed actual model or source capacity")
            if any(row["prompt_tokens"][model] > row.get("total_prompt_token_cap", MAX_MODEL_LEN) for row in rows):
                raise ValueError("total chat-template budget overflow")
            proofs[model] = {"path": models[model]["path"], "request_count": len(rows),
                "max_prompt_tokens": max(lengths), "min_prompt_tokens": min(lengths), "overflow_count": overflow,
                "apply_chat_template": True, "tokenizer_local_files_only": True, "enable_thinking": False,
                "reserved_output_tokens": RESERVED_OUTPUT_TOKENS}
        if name in {"transfer", "corpus"}:
            pairs = [(ranker, ranker + "_pack") for ranker in ("lexical", "bm25")]
            pairs += [("lexical", "bm25"), ("lexical_pack", "bm25_pack")]
        elif name == "budget":
            pairs = [(f"cap{cap}_bm25", f"cap{cap}_bm25_pack") for cap in BUDGET_CAPS]
        else:
            pairs = [("none", "text_neutral"), ("none", "json_neutral")]
            pairs += [("text_" + policy, "json_" + policy) for policy in ("neutral", "conservative")]
            pairs += [(format + "_neutral", format + "_conservative") for format in ("text", "json")]
        protocol = {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": name,
            "comparisons": [[baseline, candidate] for baseline, candidate in pairs],
            "conditions": sorted({row["condition"] for row in rows}), "repeat_count": 1,
            "max_model_len": MAX_MODEL_LEN, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS,
            "source_only_token_cap_per_model": SOURCE_TOKEN_CAP, "source_character_cap": CHAR_CAP,
            "source_passage_cap": WINDOW_CAP, "temperature": 0, "seed_for_generation": 0,
            "enable_thinking": False, "decoding_mode": "json_schema", "limitations": limitations}
        envelope = {"protocol": protocol, "provenance": identity, "requests": rows}
        unique = {row["document_id"]: row for row in rows}
        conditions = {}
        for condition in protocol["conditions"]:
            subset_rows = [row for row in rows if row["condition"] == condition]
            conditions[condition] = {"request_count": len(subset_rows),
                "pack_injected": sum(row["pack_injected"] for row in subset_rows),
                "positive_source_visible": sum(row["source_gold_visible"] is True for row in subset_rows),
                "positive_questions": sum(row["positive_gold"] for row in subset_rows),
                "anchor_document_retrieved": sum(row.get("anchor_document_retrieved", False) for row in subset_rows),
                "mean_prompt_tokens": {model: sum(row["prompt_tokens"][model] for row in subset_rows) / len(subset_rows)
                                       for model in models},
                "mean_budget_utilization": {model: sum(row["prompt_budget_utilization"][model] for row in subset_rows) / len(subset_rows)
                                            for model in models} if name == "budget" else None}
        experiments[name] = {"file": name + ".json", "request_count": len(rows), "question_count": len(unique),
            "parent_articles": len({row["parent_document_id"] for row in rows}),
            "parent_unit_scope": "source context; original article independence unverified",
            "strata": dict(Counter(row["stratum"] for row in unique.values())),
            "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
            "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(), "models": proofs,
            "conditions": conditions}
        envelopes[name] = envelope
    manifest = {"schema_version": 1, "protocol": PROTOCOL_ID, "phase": "FINAL_FROZEN", **identity,
        "experiments": experiments, "total_requests_per_model": sum(len(rows) for rows in tracks.values()),
        "total_planned_model_calls": len(models) * sum(len(rows) for rows in tracks.values()),
        "raw_source_and_individual_answers_remain_private": True}
    return envelopes, manifest

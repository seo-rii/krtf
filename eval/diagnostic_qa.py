"""Freeze follow-on QA diagnostics before looking at new generation outputs.

The factorial deliberately reuses an earlier sample to isolate source loss from
pack overhead. A second track samples unseen contexts before retrieval or pack
construction. Neither track changes resolver thresholds or execution authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
from html import escape

from ktrf.context import QA_CONTEXT_POLICY
from .extended_qa import (
    CHAR_CAP, OVERLAP_POLICY, PROTOCOL_ID, WINDOW_CAP, OverlapIndex, PromptBudget,
    RequestBuilder, _fact_projection, _pack_render, _sha, _validate_record, select_windows,
)
from .hf_qa import EVIDENCE_POLICY, canonical
from .prepare_followup import MAX_MODEL_LEN, RESERVED_OUTPUT_TOKENS, SOURCE_TOKEN_CAP
from .run_hf_benchmark import contains_span, digest

SEED = "ktrf-diagnostic-qa-v1-20261020"
REUSED_PER_STRATUM = 64
FRESH_PER_STRATUM = 64
PRIOR_TRANSFER_PER_STRATUM = 128
FACTORIAL_CONDITIONS = [f"{source}_{pack}" for source in ("full", "shrunken")
                        for pack in ("none", "compact", "full")]
FRESH_CONDITIONS = ["none", "full", "compact"]


def _source(record, spans):
    if not isinstance(spans, list) or len(spans) > WINDOW_CAP:
        raise ValueError("invalid frozen source span list")
    previous = 0
    for span in spans:
        if (not isinstance(span, (tuple, list)) or len(span) != 2
                or any(type(n) is not int for n in span)
                or not 0 <= span[0] < span[1] <= len(record["text"])
                or span[0] < previous):
            raise ValueError("invalid or overlapping frozen source spans")
        previous = span[1]
    return "\n\n".join(record["text"][a:b] for a, b in spans)


def _prior(envelope, experiment, per_stratum):
    protocol = envelope.get("protocol", {})
    if (protocol.get("kind") != PROTOCOL_ID or protocol.get("phase") != "FINAL_FROZEN"
            or protocol.get("experiment") != experiment or protocol.get("repeat_count") != 1):
        raise ValueError("frozen prior experiment required: " + experiment)
    expected = ({"cap1024_bm25", "cap1024_bm25_pack", "cap1536_bm25", "cap1536_bm25_pack"}
                if experiment == "budget" else {"bm25", "bm25_pack", "lexical", "lexical_pack"})
    if set(protocol.get("conditions", [])) != expected:
        raise ValueError("prior conditions differ from declared source experiment")
    records, groups = {}, defaultdict(dict)
    fields = ("document_id", "parent_document_id", "document_sha256", "question", "stratum",
              "positive_gold", "expected_answers", "answer_spans")
    for row in envelope["requests"]:
        if (row.get("task") != "document_qa" or row.get("experiment") != experiment
                or type(row.get("positive_gold")) is not bool):
            raise ValueError("invalid frozen prior task or experiment")
        record = {key: deepcopy(row[key]) for key in fields}
        record["text"] = row["source_text"]
        _validate_record(record)
        identifier, condition = record["document_id"], row["condition"]
        if condition not in expected or condition in groups[identifier] or row.get("repeat_id") != 0:
            raise ValueError("duplicate or unknown frozen prior condition")
        if identifier in records and canonical(records[identifier]) != canonical(record):
            raise ValueError("prior variants disagree on source or gold")
        if _sha(_source(record, row["source_spans"])) != row["rendered_source_sha256"]:
            raise ValueError("frozen source spans disagree with source hash")
        records[identifier], groups[identifier][condition] = record, row
    if any(set(group) != expected for group in groups.values()):
        raise ValueError("prior source matrix is incomplete")
    if Counter(row["stratum"] for row in records.values()) != {"SPAN": per_stratum, "NO_ANSWER": per_stratum}:
        raise ValueError("prior source sample differs from declared strata")
    if len({row["parent_document_id"] for row in records.values()}) != len(records):
        raise ValueError("prior source repeats a parent context")
    return records, groups


def select_fresh(records, prior_records, exclusion_texts=()):
    """Select only by frozen identity, overlap and stratum; never resolver output."""
    excluded_parents = {r["parent_document_id"] for r in prior_records}
    excluded_ids = {r["document_id"] for r in prior_records}
    texts = [r["text"] for r in prior_records]
    for value in exclusion_texts:
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            if value.get("parent_document_id"):
                excluded_parents.add(value["parent_document_id"])
            if value.get("document_id"):
                excluded_ids.add(value["document_id"])
            text = value.get("text", value.get("source_text"))
            if not isinstance(text, str) or not text:
                raise ValueError("exclusion source requires nonempty text")
            texts.append(text)
        else:
            raise ValueError("exclusion inputs require text or source records")
    prior, overlap_cache = OverlapIndex(texts), {}
    eligible, seen, exclusions = [], set(), Counter()
    for record in sorted(records, key=lambda r: (digest([SEED, r["document_id"]]), r["document_id"])):
        _validate_record(record)
        if record["document_id"] in seen:
            raise ValueError("duplicate source question ID")
        seen.add(record["document_id"])
        if record["document_id"] in excluded_ids:
            exclusions["prior_question_identity"] += 1
            continue
        if record["parent_document_id"] in excluded_parents:
            exclusions["prior_parent_overlap"] += 1
            continue
        sha = record["document_sha256"]
        if sha not in overlap_cache:
            overlap_cache[sha] = prior.reason(record["text"])
        reason = overlap_cache[sha]
        if reason:
            exclusions[reason] += 1
            continue
        eligible.append(record)
    chosen, parents, hashes, selected_overlap = [], set(), set(), OverlapIndex()
    counts = Counter()
    for stratum in ("SPAN", "NO_ANSWER"):
        for record in eligible:
            if record["stratum"] != stratum or counts[stratum] == FRESH_PER_STRATUM:
                continue
            if record["parent_document_id"] in parents or record["document_sha256"] in hashes:
                continue
            if selected_overlap.reason(record["text"]):
                continue
            chosen.append(record)
            parents.add(record["parent_document_id"])
            hashes.add(record["document_sha256"])
            selected_overlap.add(record["text"])
            counts[stratum] += 1
    inventory = {"seed": SEED, "source_questions": len(records), "eligible_questions": len(eligible),
        "selected_strata": dict(counts), "quotas": {"SPAN": FRESH_PER_STRATUM, "NO_ANSWER": FRESH_PER_STRATUM},
        "exclusions": dict(exclusions), "exclusion_unique_texts": len(set(texts)),
        "exclusion_text_hashes_sha256": digest(sorted({_sha(text) for text in texts})),
        "excluded_parent_count": len(excluded_parents), "overlap_policy": OVERLAP_POLICY,
        "prior_question_count": len(excluded_ids), "prior_question_ids_sha256": digest(sorted(excluded_ids)),
        "selected_question_ids_sha256": digest(sorted(r["document_id"] for r in chosen)),
        "selection_before_generation_outputs": True, "pack_eligibility_used_for_selection": False,
        "retrieval_success_used_for_selection": False, "parent_units": len(parents)}
    if any(counts[kind] != FRESH_PER_STRATUM for kind in ("SPAN", "NO_ANSWER")):
        error = ValueError("INSUFFICIENT_DATA: unseen nonoverlapping contexts for declared fresh strata")
        error.inventory = inventory
        raise error
    return chosen, inventory


def _compact(prepared):
    """Shorten transport metadata while retaining status and semantic caveats."""
    pack = prepared.context_pack
    facts = _fact_projection(pack)
    # Preserve full compound notes in the audit projection; the standard text
    # renderer already emits the crucial 'not the same entity' warning.
    extras = {"complete": pack.get("coverage", {}).get("complete", False),
              "omissions": dict(Counter(item["reason"] for item in pack.get("omissions", []))),
              "compound_relations": [], "disambiguation_hints": [],
              "document_definitions": [{key: item[key] for key in ("surface", "authority") if key in item}
                                       for item in pack.get("document_definitions", [])],
              "unknown_mentions": [{key: item[key] for key in ("surface", "reason") if key in item}
                                   for item in pack.get("unknown_mentions", [])]}
    for card in pack["resolved_terms"]:
        if card.get("disambiguation_hints"):
            extras["disambiguation_hints"].append({"canonical": card["canonical"],
                                                 "hints": card["disambiguation_hints"]})
        for mention in card["mentions"]:
            note = mention.get("appears_inside")
            if note and note.get("relation"):
                item = {"surface": mention["surface"], "appears_inside": note["surface"],
                        "relation": note["relation"], "same_entity": False}
                if item not in extras["compound_relations"]:
                    extras["compound_relations"].append(item)
    for mention in pack["ambiguous_mentions"]:
        note = mention.get("appears_inside")
        if note and note.get("relation"):
            item = {"surface": mention["surface"], "appears_inside": note["surface"],
                    "relation": note["relation"], "same_entity": False}
            if item not in extras["compound_relations"]:
                extras["compound_relations"].append(item)
    lines = [_pack_render(facts, "text")]
    lines.append("complete=" + str(bool(extras["complete"])).lower()
                 + ("" if extras["complete"] else " (문서의 모든 용어를 포함하지 않음)"))
    for key in ("compound_relations", "disambiguation_hints", "document_definitions", "unknown_mentions", "omissions"):
        if extras[key]:
            lines.append(escape(key + "=" + canonical(extras[key]).decode().strip(), quote=False))
    return {**facts, "semantic_caveats": extras}, "\n".join(lines)


def _prompts(question, source, prepared, budget, pack_variant, constant_policy):
    """No answer gold or target span can enter prompt construction."""
    if prepared.policy_fragment != QA_CONTEXT_POLICY:
        raise ValueError("prepared policy differs from fixed QA_CONTEXT_POLICY")
    facts, compact = _compact(prepared) if prepared.should_inject else (None, None)
    injected = prepared.should_inject and pack_variant != "none"
    system = EVIDENCE_POLICY
    if constant_policy or injected:
        system += "\n\n" + QA_CONTEXT_POLICY
    user = "질문: " + escape(question, quote=False) + "\n\n<source>\n" + escape(source, quote=False) + "\n</source>"
    fragment = (compact if pack_variant == "compact" else prepared.prompt_fragment) if injected else None
    if injected:
        user += "\n\n<terminology>\n" + fragment + "\n</terminology>"
    return {"system": system, "user": user, "pack_injected": bool(injected),
        "pack_sha256": digest(prepared.context_pack), "fact_cards": facts,
        "fact_cards_sha256": digest(facts) if facts is not None else None,
        "pack_prompt": fragment, "pack_policy": QA_CONTEXT_POLICY if constant_policy or injected else None,
        "pack_format": {"none": None, "compact": "text", "full": "xml"}[pack_variant],
        "policy_factor": "constant_conservative" if constant_policy else "production_conditional",
        "prompt_tokens": budget.prompt_lengths(system, user)}


def _row(record, experiment, condition, source, spans, prepared, budget, *, source_variant,
         pack_variant, pack_source_sha256, constant_policy):
    prompts = _prompts(record["question"], source, prepared, budget, pack_variant, constant_policy)
    return {"case_id": record["document_id"] + "::" + experiment, "condition": condition,
        "experiment": experiment, "task": "document_qa", "repeat_id": 0, "decoding_mode": "json_schema",
        "document_id": record["document_id"], "parent_document_id": record["parent_document_id"],
        "document_sha256": record["document_sha256"], "family_id": "context:" + record["document_sha256"],
        "evaluation_split": "adaptive_reused" if constant_policy else "fresh_context_holdout",
        "source_text": record["text"], "question": record["question"], "stratum": record["stratum"],
        "positive_gold": record["positive_gold"], "expected_answers": deepcopy(record["expected_answers"]),
        "answer_spans": deepcopy(record["answer_spans"]), "source_spans": deepcopy(spans),
        "source_gold_visible": any(contains_span(spans, span) for span in record["answer_spans"])
                               if record["positive_gold"] else None,
        "source_variant": source_variant, "pack_variant": pack_variant,
        "pack_source_sha256": pack_source_sha256, "rendered_source_sha256": _sha(source),
        "source_character_count": len(source), "source_tokens": budget.source_lengths(source), **prompts}


def _freeze(name, rows, identity, models, comparisons, limitations):
    groups = defaultdict(list)
    for row in rows:
        groups[row["case_id"]].append(row)
    ordered = []
    for index, key in enumerate(sorted(groups, key=lambda key: digest([SEED, name, key]))):
        group = sorted(groups[key], key=lambda row: row["condition"])
        offset = index % len(group)
        ordered.extend(group[offset:] + group[:offset])
    proofs = {}
    for model, spec in models.items():
        lengths = [row["prompt_tokens"][model] for row in ordered]
        if any(n + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN for n in lengths):
            raise ValueError("final actual chat template exceeds model capacity")
        if any(row["source_tokens"][model] > SOURCE_TOKEN_CAP or row["source_character_count"] > CHAR_CAP
               for row in ordered):
            raise ValueError("frozen source exceeds declared capacity")
        proofs[model] = {"path": spec["path"], "request_count": len(ordered), "max_prompt_tokens": max(lengths),
            "min_prompt_tokens": min(lengths), "overflow_count": 0, "apply_chat_template": True,
            "tokenizer_local_files_only": True, "enable_thinking": False, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS}
    conditions = sorted({row["condition"] for row in ordered})
    protocol = {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": name,
        "comparisons": comparisons, "conditions": conditions, "repeat_count": 1,
        "max_model_len": MAX_MODEL_LEN, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS,
        "source_only_token_cap_per_model": SOURCE_TOKEN_CAP, "source_character_cap": CHAR_CAP,
        "source_passage_cap": WINDOW_CAP, "temperature": 0, "seed_for_generation": 0,
        "enable_thinking": False, "decoding_mode": "json_schema", "limitations": limitations}
    envelope = {"protocol": protocol, "provenance": identity, "requests": ordered}
    unique = {row["document_id"]: row for row in ordered}
    diagnostics = {}
    for condition in conditions:
        subset = [row for row in ordered if row["condition"] == condition]
        diagnostics[condition] = {"request_count": len(subset), "pack_injected": sum(row["pack_injected"] for row in subset),
            "positive_source_visible": sum(row["source_gold_visible"] is True for row in subset),
            "positive_questions": sum(row["positive_gold"] for row in subset),
            "mean_prompt_tokens": {model: sum(row["prompt_tokens"][model] for row in subset) / len(subset)
                                   for model in models}}
    proof = {"file": name + ".json", "request_count": len(ordered), "question_count": len(unique),
        "parent_articles": len({row["parent_document_id"] for row in ordered}),
        "parent_unit_scope": "source context; original article independence unverified",
        "strata": dict(Counter(row["stratum"] for row in unique.values())),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in ordered)).hexdigest(),
        "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(), "models": proofs, "conditions": diagnostics}
    return envelope, proof


def prepare_qa_diagnostics(*, prior_budget_envelope, prior_transfer_envelope, records, snapshot,
                           tokenizers, models, code_revision, source_identity, exclusion_texts=()):
    if not code_revision or not tokenizers or set(models) != set(tokenizers):
        raise ValueError("frozen revision and matching actual model tokenizers required")
    prior, groups = _prior(prior_budget_envelope, "budget", REUSED_PER_STRATUM)
    transfer, _ = _prior(prior_transfer_envelope, "transfer", PRIOR_TRANSFER_PER_STRATUM)
    if not set(prior) <= set(transfer) or any(canonical(record) != canonical(transfer[key]) for key, record in prior.items()):
        raise ValueError("prior budget is not a consistent transfer subset")
    for envelope in (prior_budget_envelope, prior_transfer_envelope):
        if envelope.get("provenance", {}).get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("prior glossary snapshot differs from diagnostic snapshot")
    # Finish independent selection before the first pack or retrieval call.
    fresh, selection = select_fresh(records, list(transfer.values()), exclusion_texts)
    budget = PromptBudget(tokenizers)
    builder = RequestBuilder(snapshot, budget)
    tracks = {"source_pack_factorial": [], "fresh_compact": []}
    for identifier, record in sorted(prior.items()):
        full_spans = groups[identifier]["cap1536_bm25"]["source_spans"]
        shrunken_spans = groups[identifier]["cap1024_bm25_pack"]["source_spans"]
        full_source = _source(record, full_spans)
        prepared = builder.pack(record["question"], full_source)
        for source_variant, spans in (("full", full_spans), ("shrunken", shrunken_spans)):
            source = _source(record, spans)
            for pack_variant in ("none", "compact", "full"):
                tracks["source_pack_factorial"].append(_row(record, "source_pack_factorial",
                    source_variant + "_" + pack_variant, source, spans, prepared, budget,
                    source_variant=source_variant, pack_variant=pack_variant, pack_source_sha256=_sha(full_source),
                    constant_policy=True))
    for record in fresh:
        spans = select_windows(record["text"], record["question"], "bm25", budget)
        source = _source(record, spans)
        prepared = builder.pack(record["question"], source)
        for pack_variant in FRESH_CONDITIONS:
            tracks["fresh_compact"].append(_row(record, "fresh_compact", pack_variant, source, spans,
                prepared, budget, source_variant="fixed", pack_variant=pack_variant,
                pack_source_sha256=_sha(source), constant_policy=False))
    identity = {"code_revision": code_revision, "source": source_identity, "snapshot_id": snapshot.snapshot_id,
        "selection": selection,
        "prior_budget_envelope_sha256": hashlib.sha256(canonical(prior_budget_envelope)).hexdigest(),
        "prior_transfer_envelope_sha256": hashlib.sha256(canonical(prior_transfer_envelope)).hexdigest(),
        "prior_transfer_question_ids_sha256": digest(sorted(transfer)),
        "prior_transfer_question_count": len(transfer), "adaptive_reused_question_count": len(prior)}
    common_limits = [
        "Follow-on design is adaptive to prior results; the reused factorial sample is not independent confirmation.",
        "Fresh contexts exclude all prior transfer contexts and supplied corpus exposures using declared exact and near overlap checks.",
        "Fresh selection precedes retrieval and resolver calls; no retrieval-hit, pack-injection or output filtering is used.",
        "Context hashes are not verified original article IDs; semantic and model-pretraining overlap remain possible.",
        "Full and compact packs share essential definitions, observed surfaces, candidates and semantic caveats; metadata verbosity differs.",
        "Compact omits executable IDs; this diagnostic concerns explanatory QA and grants no execution authority.",
        "One generation per condition with normalized EM is a diagnostic, not an official KLUE leaderboard score.",
        "No equal total token cap is claimed: measured full chat templates must fit the 8192 context with 128 output tokens reserved."]
    pairs = [[source + "_none", source + "_" + pack] for source in ("full", "shrunken")
             for pack in ("compact", "full")]
    pairs += [[source + "_full", source + "_compact"] for source in ("full", "shrunken")]
    pairs += [["full_" + pack, "shrunken_" + pack] for pack in ("none", "compact", "full")]
    factorial_limits = common_limits + [
        "Full source uses prior cap1536_bm25 spans; shrunken source uses prior cap1024_bm25_pack spans without reranking.",
        "Every factorial arm receives the same evidence plus QA context policy, including no-pack and ungrounded cases.",
        "All factorial packs are computed from full source; a shrunken-source arm may retain terminology from omitted source."]
    fresh_limits = common_limits + [
        "Fresh arms share fixed BM25 source windows; full and compact use the same production QA policy only when should_inject.",
        "The no-pack fresh arm uses the evidence policy; comparing it to injected arms includes the production policy effect."]
    envelopes, experiments = {}, {}
    for name, comparisons, limits in (("source_pack_factorial", pairs, factorial_limits),
            ("fresh_compact", [["none", "full"], ["none", "compact"], ["full", "compact"]], fresh_limits)):
        envelopes[name], experiments[name] = _freeze(name, tracks[name], identity, models, comparisons, limits)
    full = {row["document_id"]: row for row in tracks["source_pack_factorial"] if row["condition"] == "full_none"}
    shrunken = {row["document_id"]: row for row in tracks["source_pack_factorial"] if row["condition"] == "shrunken_none"}
    experiments["source_pack_factorial"]["source_contrast"] = {
        "changed_questions": sum(full[key]["rendered_source_sha256"] != shrunken[key]["rendered_source_sha256"] for key in full),
        "positive_visibility_lost": sum(full[key]["source_gold_visible"] is True and shrunken[key]["source_gold_visible"] is False for key in full),
        "positive_visibility_gained": sum(full[key]["source_gold_visible"] is False and shrunken[key]["source_gold_visible"] is True for key in full)}
    manifest = {"schema_version": 1, "protocol": PROTOCOL_ID, "phase": "FINAL_FROZEN", **identity,
        "experiments": experiments, "total_requests_per_model": sum(len(rows) for rows in tracks.values()),
        "total_planned_model_calls": len(models) * sum(len(rows) for rows in tracks.values()),
        "raw_source_and_individual_answers_remain_private": True}
    return envelopes, manifest

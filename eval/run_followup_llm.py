"""Run frozen retrieval/stability QA diagnostics without retries or answer repair.

Only system/user strings and fixed decoding fields reach the completion API.
Gold, source offsets, document identities and grading remain private artifacts.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from .hf_qa import (EVIDENCE_POLICY, canonical, character_f1, normalize_answer,
                    response_error)
from .run_product_llm import _request_json, parse_model_json

PROTOCOL_ID = "hf_followup_v1"
ARTIFACTS = ("frozen_envelope.json", "requests.jsonl", "responses.jsonl", "graded.json")
DECODING = {"temperature": 0, "seed": 0, "max_tokens": 128,
            "chat_template_kwargs": {"enable_thinking": False}}
ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {
    "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]}},
    "required": ["answer"], "additionalProperties": False}
CONTEXTS = {"retrieval": ("lexical", "bm25", "adjacent", "oracle"),
            "stability": ("retrieved", "ktrf_pack"),
            "combined": ("lexical", "lexical_pack", "bm25", "bm25_pack")}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _matrix(experiment):
    return {(context, decoding, repeat) for context in CONTEXTS[experiment]
            for decoding in (("free", "json_schema") if experiment == "stability" else
                             ("json_schema",) if experiment == "combined" else ("free",))
            for repeat in (range(3) if experiment in {"stability", "combined"} else (0,))}


def validate_requests(rows, experiment=None):
    """Reject partial matrices, inconsistent gold and prompts outside frozen source."""
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise ValueError("nonempty request object list required")
    experiment = experiment or rows[0].get("experiment")
    if experiment not in CONTEXTS:
        raise ValueError("unknown followup experiment")
    grouped, seen = defaultdict(list), set()
    fixed = ("stratum", "positive_gold", "expected_answers", "parent_document_id", "document_sha256",
             "source_text", "question", "answer_spans", "answer_passage_spans")
    for row in rows:
        for field in ("case_id", "condition", "parent_document_id", "document_sha256", "system", "user",
                      "source_text", "question"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError("nonempty string field required: " + field)
        if row.get("experiment") != experiment or row.get("task") != "document_qa":
            raise ValueError("mixed experiment or unknown task")
        triple = (row.get("context_condition"), row.get("decoding_mode"), row.get("repeat_id"))
        if type(triple[2]) is not int or triple not in _matrix(experiment):
            raise ValueError("unknown context/decoding/repeat")
        if row["condition"] != f"{triple[0]}__{triple[1]}__r{triple[2]}":
            raise ValueError("condition must encode context, decoding and repeat")
        key = (row["case_id"], row["condition"])
        if key in seen:
            raise ValueError("duplicate request key")
        seen.add(key)
        kind = row.get("stratum")
        positive = row.get("positive_gold")
        answers = row.get("expected_answers")
        if (kind not in {"SPAN", "YES_NO", "NO_ANSWER"} or type(positive) is not bool
                or positive != (kind != "NO_ANSWER") or not isinstance(answers, list)
                or any(not isinstance(a, str) or not a.strip() for a in answers)
                or bool(answers) != positive):
            raise ValueError("invalid source gold")
        if kind == "YES_NO" and any(a not in {"YES", "NO"} for a in answers):
            raise ValueError("YES_NO gold must contain YES/NO")
        if _hash(row["source_text"].encode()) != row["document_sha256"]:
            raise ValueError("source document hash differs")
        spans = row.get("source_spans")
        if not isinstance(spans, list):
            raise ValueError("source spans required")
        for span in spans:
            if (not isinstance(span, (list, tuple)) or len(span) != 2
                    or any(type(v) is not int for v in span)
                    or not 0 <= span[0] < span[1] <= len(row["source_text"])):
                raise ValueError("invalid source span")
        visible = row.get("source_gold_visible")
        if (positive and type(visible) is not bool) or (not positive and visible is not None):
            raise ValueError("source visibility must match gold stratum")
        answer_spans = row.get("answer_passage_spans" if kind == "YES_NO" else "answer_spans")
        if positive and answer_spans is not None:
            expected_visible = any(s <= a <= b <= e for s, e in spans for a, b in answer_spans)
            if visible != expected_visible:
                raise ValueError("source visibility disagrees with source offsets")
        source = "\n\n".join(row["source_text"][s:e] for s, e in spans)
        system = EVIDENCE_POLICY
        user = "질문: " + row["question"] + "\n\n<source>\n" + source + "\n</source>"
        if type(row.get("pack_injected", False)) is not bool:
            raise ValueError("pack injection state must be boolean")
        if row.get("pack_injected", False):
            pack_contexts = {"ktrf_pack"} if experiment == "stability" else {"lexical_pack", "bm25_pack"} if experiment == "combined" else set()
            if (triple[0] not in pack_contexts or not isinstance(row.get("pack_policy"), str)
                    or not row["pack_policy"] or not isinstance(row.get("pack_prompt"), str)
                    or not row["pack_prompt"]):
                raise ValueError("injected pack requires frozen pack fragments")
            system += "\n\n" + row["pack_policy"]
            user += "\n\n<terminology>\n" + row["pack_prompt"] + "\n</terminology>"
        if row["system"] != system or row["user"] != user:
            raise ValueError("prompt differs from frozen source and policy")
        grouped[row["case_id"]].append(row)
    for case in grouped.values():
        if len(case) != len(_matrix(experiment)) or {
                (r["context_condition"], r["decoding_mode"], r["repeat_id"]) for r in case} != _matrix(experiment):
            raise ValueError("complete unique experiment matrix required")
        if any(any(r.get(field) != case[0].get(field) for field in fixed) for r in case):
            raise ValueError("variants disagree on source or gold")
        for context in CONTEXTS[experiment]:
            variants = [r for r in case if r["context_condition"] == context]
            if any((r["system"], r["user"], r["source_spans"], r["source_gold_visible"]) != (
                    variants[0]["system"], variants[0]["user"], variants[0]["source_spans"],
                    variants[0]["source_gold_visible"]) for r in variants):
                raise ValueError("repeats and decoding modes must preserve identical prompts")
        if experiment == "stability":
            first, second = (next(r for r in case if r["context_condition"] == context)
                             for context in CONTEXTS[experiment])
            if first["source_spans"] != second["source_spans"]:
                raise ValueError("stability pack must retain matched retrieved source")
        if experiment == "combined":
            for ranker in ("lexical", "bm25"):
                plain, packed = (next(r for r in case if r["context_condition"] == context)
                                 for context in (ranker, ranker + "_pack"))
                if (plain["source_spans"] != packed["source_spans"]
                        or plain["source_gold_visible"] != packed["source_gold_visible"]):
                    raise ValueError("combined pack must retain matched ranker source")
                if not packed.get("pack_injected", False) and (
                        plain["system"], plain["user"]) != (packed["system"], packed["user"]):
                    raise ValueError("non-injected combined pack must keep identical prompt")
    return rows


def load_request_file(path):
    envelope = json.loads(Path(path).read_text())
    protocol = envelope.get("protocol", {})
    if (protocol.get("kind") != PROTOCOL_ID or protocol.get("phase") != "FINAL_FROZEN"
            or protocol.get("experiment") not in CONTEXTS):
        raise ValueError("FINAL_FROZEN followup envelope required")
    if (not isinstance(protocol.get("limitations"), list) or not protocol["limitations"]
            or any(not isinstance(v, str) or not v for v in protocol["limitations"])
            or not isinstance(envelope.get("provenance"), dict)):
        raise ValueError("limitations and source provenance required")
    rows = validate_requests(envelope.get("requests"), protocol.get("experiment"))
    return rows, protocol, envelope["provenance"]


def _metrics(cases):
    positive = [r for r in cases if r["positive_gold"]]
    negative = [r for r in cases if not r["positive_gold"]]
    per_question = defaultdict(list)
    for row in cases:
        per_question[row["case_id"]].append(row)
    positive_means = [math.fsum(r["exact_match"] for r in group) / len(group)
                      for group in per_question.values() if group[0]["positive_gold"]]
    negative_means = [math.fsum(r["null"] for r in group) / len(group)
                      for group in per_question.values() if not group[0]["positive_gold"]]
    return {"planned": len(cases), "questions": len(per_question), "positive_planned": len(positive),
        "no_answer_planned": len(negative), "positive_exact": sum(r["exact_match"] for r in positive),
        "positive_exact_rate": math.fsum(positive_means) / len(positive_means) if positive_means else None,
        "positive_character_f1_sum": math.fsum(r["character_f1"] for r in positive),
        "positive_character_f1_mean": math.fsum(r["character_f1"] for r in positive) / len(positive) if positive else None,
        "article_no_answer_null": sum(r["null"] for r in negative),
        "article_no_answer_null_rate": math.fsum(negative_means) / len(negative_means) if negative_means else None,
        "article_no_answer_nonnull": sum(r["nonnull"] for r in negative),
        "positive_null": sum(r["null"] for r in positive),
        "missing": sum(r["missing"] for r in cases), "errors": sum(r["error"] for r in cases),
        "malformed": sum(r["malformed"] for r in cases),
        "source_positive_visible": sum(r["source_gold_visible"] is True for r in positive),
        "positive_exact_with_visible_source": sum(r["exact_match"] and r["source_gold_visible"] is True for r in positive),
        "positive_exact_without_visible_source": sum(r["exact_match"] and r["source_gold_visible"] is False for r in positive),
        "by_stratum": {kind: {"planned": sum(r["stratum"] == kind for r in cases),
            "exact": sum(r["exact_match"] for r in cases if r["stratum"] == kind)}
            for kind in ("SPAN", "YES_NO", "NO_ANSWER")},
        "repeat_inference_unit": "question; repeats are descriptive measurements, not independent samples",
        **({"pack_injected_requests": sum(r["pack_injected"] for r in cases),
            "pack_injected_questions": sum(any(r["pack_injected"] for r in group)
                                            for group in per_question.values())}
           if cases and "pack_injected" in cases[0] else {})}


def grade_outputs(rows, outputs):
    validate_requests(rows)
    known = {(r["case_id"], r["condition"]): r for r in rows}
    observed = {}
    for output in outputs:
        key = (output["case_id"], output["condition"])
        if key not in known or key in observed:
            raise ValueError("unknown or duplicate output")
        if output.get("status") not in {"RECEIVED", "MALFORMED", "HTTP_ERROR", "TRANSPORT_ERROR"}:
            raise ValueError("unknown output status")
        observed[key] = output
    cases, predictions = [], {}
    for key, row in known.items():
        output = observed.get(key)
        missing = output is None
        error = not missing and output["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"}
        malformed = not missing and not error and (output["status"] != "RECEIVED"
                         or response_error(output.get("response")) is not None)
        valid = not missing and not error and not malformed
        value = output["response"]["answer"] if valid else None
        yes_no = row["stratum"] == "YES_NO"
        exact = valid and (value is None if not row["positive_gold"] else value is not None and any(
            normalize_answer(value, yes_no=yes_no) == normalize_answer(a, yes_no=yes_no)
            for a in row["expected_answers"]))
        f1 = max((character_f1(value, a, yes_no=yes_no) for a in row["expected_answers"]), default=0.0) if valid and value is not None else 0.0
        cases.append({k: row[k] for k in ("case_id", "condition", "context_condition", "decoding_mode", "repeat_id",
            "parent_document_id", "stratum", "positive_gold", "source_gold_visible")} | {
            "missing": missing, "error": bool(error), "malformed": bool(malformed), "valid": valid,
            "exact_match": bool(exact), "character_f1": f1,
            "null": bool(valid and value is None), "nonnull": bool(valid and value is not None)})
        if row["experiment"] == "combined":
            cases[-1]["pack_injected"] = row.get("pack_injected", False)
        if valid:
            predictions[key] = None if value is None else normalize_answer(value, yes_no=yes_no)
    by_variant, by_repeat = {}, {}
    for context in CONTEXTS[rows[0]["experiment"]]:
        modes = sorted({r["decoding_mode"] for r in rows if r["context_condition"] == context})
        for mode in modes:
            group = [c for c in cases if c["context_condition"] == context and c["decoding_mode"] == mode]
            key = context + "__" + mode
            by_variant[key] = _metrics(group)
            by_repeat[key] = {str(repeat): _metrics([c for c in group if c["repeat_id"] == repeat])
                              for repeat in sorted({c["repeat_id"] for c in group})}
    indexed = {(c["case_id"], c["context_condition"], c["decoding_mode"], c["repeat_id"]): c for c in cases}
    comparisons = []
    if rows[0]["experiment"] == "retrieval":
        comparisons = [("lexical", "free", context, "free") for context in ("bm25", "adjacent", "oracle")]
    elif rows[0]["experiment"] == "combined":
        comparisons = [(left, "json_schema", right, "json_schema") for left, right in (
            ("lexical", "bm25"), ("lexical", "lexical_pack"), ("bm25", "bm25_pack"),
            ("lexical_pack", "bm25_pack"), ("lexical", "bm25_pack"))]
    else:
        comparisons = [("retrieved", mode, "ktrf_pack", mode) for mode in ("free", "json_schema")]
        comparisons += [(context, "free", context, "json_schema") for context in CONTEXTS["stability"]]
    paired = {}
    for left_context, left_mode, right_context, right_mode in comparisons:
        pairs = [(left, indexed[(left["case_id"], right_context, right_mode, left["repeat_id"])])
                 for left in cases if left["context_condition"] == left_context and left["decoding_mode"] == left_mode]
        comparable = [(a, b) for a, b in pairs if a["valid"] and b["valid"]]
        per_question = defaultdict(list)
        for a, b in pairs:
            per_question[a["case_id"]].append((a, b))
        deltas = [math.fsum(int(b["exact_match"]) - int(a["exact_match"]) for a, b in group) / len(group)
                  for group in per_question.values()]
        identical_prompt_pairs = [(a, b) for a, b in pairs if all(
            known[(a["case_id"], a["condition"])][field] == known[(b["case_id"], b["condition"])][field]
            for field in ("system", "user"))]
        identical_valid = [(a, b) for a, b in identical_prompt_pairs if a["valid"] and b["valid"]]
        paired[left_context + "__" + left_mode + "_to_" + right_context + "__" + right_mode] = {
            "planned": len(pairs), "questions": len(per_question), "comparable": len(comparable),
            "incomplete_or_malformed": len(pairs) - len(comparable),
            "helpful": sum(not a["exact_match"] and b["exact_match"] for a, b in comparable),
            "harmful": sum(a["exact_match"] and not b["exact_match"] for a, b in comparable),
            "per_question_mean_exact_delta": math.fsum(deltas) / len(deltas),
            "question_mean_improved": sum(d > 0 for d in deltas),
            "question_mean_worsened": sum(d < 0 for d in deltas),
            "identical_prompt_pairs": len(identical_prompt_pairs),
            "identical_prompt_valid_pairs": len(identical_valid),
            "identical_prompt_answer_disagreements": sum(
                predictions[(a["case_id"], a["condition"])] != predictions[(b["case_id"], b["condition"])]
                for a, b in identical_valid),
            "no_independence_claim_for_repeats": True}
    agreement = {}
    for variant in by_variant:
        context, mode = variant.split("__")
        groups = defaultdict(list)
        for case in cases:
            if case["context_condition"] == context and case["decoding_mode"] == mode:
                groups[case["case_id"]].append(case)
        complete = [group for group in groups.values() if all(c["valid"] for c in group)]
        agreement[variant] = {"question_groups": len(groups), "fully_valid_groups": len(complete),
            "incomplete_or_malformed_groups": len(groups) - len(complete),
            "identical_normalized_answer_groups": sum(len({predictions[(c["case_id"], c["condition"])] for c in group}) == 1 for group in complete),
            "identical_correctness_groups": sum(len({c["exact_match"] for c in group}) == 1 for group in complete),
            "repeat_count": len(next(iter(groups.values())))}
    return {"cases": cases, "missing_outputs": sum(c["missing"] for c in cases),
            "by_variant": by_variant, "by_repeat": by_repeat, "paired": paired, "repeat_agreement": agreement}


def run_benchmark(*, requests_file, endpoint, model, out_dir, code_revision, timeout=180):
    rows, protocol, provenance = load_request_file(requests_file)
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username
            or parsed.password or parsed.query or parsed.fragment or not model or not code_revision or timeout <= 0):
        raise ValueError("valid endpoint, model, code revision and positive timeout required")
    endpoint = endpoint.rstrip("/")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out_dir / "frozen_envelope.json").write_bytes(Path(requests_file).read_bytes())
    (out_dir / "requests.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    manifest = {"protocol": PROTOCOL_ID, "track": "hf_followup", "experiment": protocol["experiment"],
        "declared_protocol": protocol, "request_provenance": provenance, "code_revision": code_revision,
        "started_at": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint, "requested_model": model,
        "request_count": len(rows), "decoding": DECODING, "answer_schema": ANSWER_SCHEMA,
        "schema_transport": "response_format.json_schema.strict", "timeout_seconds": timeout,
        "prompt_fields": ["system", "user"], "request_order": "frozen builder order; serial; stateless",
        "response_parser": "JSON object bare or one enclosing JSON code fence; no prose/repair",
        "retries": 0, "request_corpus_sha256": _hash((out_dir / "requests.jsonl").read_bytes()),
        "frozen_request_file_sha256": _hash((out_dir / "frozen_envelope.json").read_bytes()),
        "declared_protocol_sha256": _hash(canonical(protocol)), "served_models": None, "setup_error": None}
    try:
        served = _request_json(endpoint + "/models", timeout=timeout)
        manifest["served_models"] = served
        if (not isinstance(served, dict) or not isinstance(served.get("data"), list)
                or model not in {entry.get("id") for entry in served["data"] if isinstance(entry, dict)}):
            raise ValueError("requested model is not advertised by /models")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        manifest["setup_error"] = {"type": type(error).__name__, "message": str(error)}
    records = []
    with (out_dir / "responses.jsonl").open("wb") as stream:
        if manifest["setup_error"] is None:
            for row in rows:
                payload = {"model": model, "messages": [{"role": "system", "content": row["system"]},
                    {"role": "user", "content": row["user"]}], **DECODING}
                if row["decoding_mode"] == "json_schema":
                    payload["response_format"] = {"type": "json_schema", "json_schema": {
                        "name": "qa_answer", "strict": True, "schema": ANSWER_SCHEMA}}
                record = {"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
                    "response": {}, "raw_text": None, "raw_response": None, "parse_error": None,
                    "error": None, "finish_reason": None, "usage": None}
                before = time.perf_counter()
                try:
                    raw = _request_json(endpoint + "/chat/completions", payload=payload, timeout=timeout)
                    record["raw_response"] = raw
                    if (not isinstance(raw, dict) or not isinstance(raw.get("choices"), list)
                            or not raw["choices"] or not isinstance(raw["choices"][0], dict)):
                        raise ValueError("completion response has no first choice")
                    choice = raw["choices"][0]
                    record["usage"] = raw.get("usage")
                    record["finish_reason"] = choice.get("finish_reason")
                    message = choice.get("message")
                    record["raw_text"] = message.get("content") if isinstance(message, dict) else None
                    record["response"] = parse_model_json(record["raw_text"])
                    invalid = response_error(record["response"])
                    if invalid:
                        raise ValueError(invalid)
                except HTTPError as error:
                    record["status"] = "HTTP_ERROR"
                    record["error"] = {"type": type(error).__name__, "http_status": error.code, "message": str(error)}
                    record.pop("response")
                except (URLError, TimeoutError, OSError) as error:
                    record["status"] = "TRANSPORT_ERROR"
                    record["error"] = {"type": type(error).__name__, "message": str(error)}
                    record.pop("response")
                except ValueError as error:
                    record["status"] = "MALFORMED"
                    record["parse_error"] = {"type": type(error).__name__, "message": str(error)}
                record["latency_ms"] = round((time.perf_counter() - before) * 1000, 3)
                stream.write(canonical(record))
                stream.flush()
                records.append(record)
    graded = grade_outputs(rows, records)
    (out_dir / "graded.json").write_bytes(canonical(graded))
    errors = sum(r["status"] in {"HTTP_ERROR", "TRANSPORT_ERROR"} for r in records)
    manifest.update({"finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE" if not manifest["setup_error"] and not errors and not graded["missing_outputs"] else "INCOMPLETE",
        "received_count": sum(r["status"] in {"RECEIVED", "MALFORMED"} for r in records),
        "record_count": len(records), "missing_count": graded["missing_outputs"], "error_count": errors,
        "malformed_count": sum(r["status"] == "MALFORMED" for r in records)})
    manifest["artifact_sha256"] = {name: _hash((out_dir / name).read_bytes()) for name in ARTIFACTS}
    manifest["seal_sha256"] = _hash(canonical(manifest))
    (out_dir / "run_manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests-file", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    manifest = run_benchmark(**vars(args))
    print(json.dumps({key: manifest[key] for key in ("status", "request_count", "received_count", "missing_count", "error_count", "malformed_count")}))
    return 0 if manifest["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the frozen synthetic product intervention track against a live endpoint.

Only each case's system/user strings reach the model. Ground truth and grading
metadata stay in the request artifact; a full-pack condition explicitly renders
the resolver pack in its user prompt. No retries or answer repair are performed:
malformed outputs and transport failures remain distinct.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from eval.product_utility import (build_requests, grade_outputs, local_swap_checks,
                                 malformed_response_field)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _request_json(url, *, payload=None, timeout):
    request = Request(url, data=None if payload is None else _json_bytes(payload),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_model_json(content):
    """Accept a JSON object bare or inside one enclosing JSON code fence.

    The parser is identical in every condition. Extra prose and partial JSON
    extraction are rejected; the unchanged source text is stored separately.
    """
    if not isinstance(content, str):
        raise ValueError("model content is not a string")
    text = content.strip()
    fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    response = json.loads(text)
    if not isinstance(response, dict):
        raise ValueError("model JSON is not an object")
    return response


def run_benchmark(*, endpoint, model, out_dir, code_revision, max_tokens=128,
                  timeout=180, seed=0, enable_thinking=False, track="factorial",
                  requests_file=None):
    """Serial requests to an existing server, returning a sealed run manifest."""
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("endpoint must be an HTTP(S) base URL without credentials or query")
    if max_tokens <= 0 or timeout <= 0 or not code_revision:
        raise ValueError("positive token/timeout budgets and code revision are required")
    production = track in {"production_synthetic", "production_real"}
    baseline = track in {"baseline_synthetic", "baseline_real"}
    document_context = track == "document_context"
    definition_control = track == "definition_control"
    strict_tasks = production or baseline or document_context or definition_control
    if requests_file is not None and not strict_tasks:
        raise ValueError("frozen request files are supported only for production, baseline, document context and definition control tracks")
    request_provenance = None
    if track == "factorial":
        request_builder, grader = build_requests, grade_outputs
        protocol_id, declared_protocol = "product_utility_live_v1", None
    elif track == "contract_probe":
        from eval.product_contract_probe import (
            CONTRACT_PROTOCOL, build_contract_requests, grade_contract_outputs)
        request_builder, grader = build_contract_requests, grade_contract_outputs
        protocol_id, declared_protocol = "product_contract_probe_v1", CONTRACT_PROTOCOL
    elif track == "synthetic_expansion":
        from eval.synthetic_grounding import (
            EXPANSION_PROTOCOL, build_expanded_requests, grade_expanded_outputs)
        request_builder, grader = build_expanded_requests, grade_expanded_outputs
        protocol_id, declared_protocol = "synthetic_grounding_expansion_v1", EXPANSION_PROTOCOL
    elif track == "synthetic_expansion_v2":
        from eval.synthetic_grounding import grade_expanded_outputs
        from eval.synthetic_grounding_v2 import BALANCED_PROTOCOL, build_balanced_requests
        request_builder, grader = build_balanced_requests, grade_expanded_outputs
        protocol_id, declared_protocol = "synthetic_grounding_expansion_v2", BALANCED_PROTOCOL
    elif track == "qa_policy_probe":
        from eval.qa_policy_probe import PROTOCOL, build_policy_requests, grade_policy_outputs
        request_builder, grader = build_policy_requests, grade_policy_outputs
        protocol_id, declared_protocol = "qa_policy_separation_v1", PROTOCOL
    elif definition_control:
        from eval.definition_control import load_request_file, grade_outputs
        from eval.production_grounding import production_response_error
        if requests_file is None:
            raise ValueError("definition control requires a frozen --requests-file")
        frozen_requests, declared_protocol, request_provenance = load_request_file(requests_file)
        request_builder, grader = lambda: frozen_requests, grade_outputs
        protocol_id = declared_protocol["kind"]
    elif document_context:
        from eval.document_context import load_document_context_request_file, grade_document_context_outputs
        from eval.production_grounding import production_response_error
        if requests_file is None:
            raise ValueError("document context requires a frozen --requests-file")
        frozen_requests, declared_protocol, request_provenance = load_document_context_request_file(
            requests_file, track=track)
        request_builder, grader = lambda: frozen_requests, grade_document_context_outputs
        protocol_id = declared_protocol["kind"]
    elif baseline:
        from eval.production_baseline import load_baseline_request_file, grade_baseline_outputs
        from eval.production_grounding import production_response_error
        if requests_file is None:
            raise ValueError("baseline tracks require a frozen --requests-file")
        frozen_requests, declared_protocol, request_provenance = load_baseline_request_file(
            requests_file, track=track)
        request_builder, grader = lambda: frozen_requests, grade_baseline_outputs
        protocol_id = declared_protocol["kind"]
    elif production:
        from eval.production_grounding import (
            PROTOCOL, build_production_requests, grade_production_outputs,
            load_production_request_file, production_response_error)
        grader = grade_production_outputs
        if requests_file is not None:
            frozen_requests, declared_protocol, request_provenance = load_production_request_file(
                requests_file, track=track)
            request_builder = lambda: frozen_requests
        elif track == "production_real":
            raise ValueError("production_real requires a frozen --requests-file")
        else:
            request_builder, declared_protocol = build_production_requests, PROTOCOL
        protocol_id = declared_protocol["kind"]
    else:
        raise ValueError("unknown experiment track")
    endpoint = endpoint.rstrip("/")
    # Validate all frozen rows before creating artifacts or contacting a server.
    requests = request_builder()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    requests_path = out_dir / "requests.jsonl"
    requests_path.write_bytes(b"".join(_json_bytes(row) for row in requests))
    decoding = {"temperature": 0, "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": enable_thinking}}
    if seed is not None:
        decoding["seed"] = seed
    manifest = {"protocol": protocol_id, "track": track,
                "declared_protocol": declared_protocol, "code_revision": code_revision,
                "started_at": started, "endpoint": endpoint, "requested_model": model,
                "request_count": len(requests), "decoding": decoding, "timeout_seconds": timeout,
                "prompt_fields": ["system", "user"], "request_order": "builder order; serial; stateless",
                "response_parser": "JSON object, bare or one enclosing JSON code fence; no extra prose",
                "retries": 0, "request_corpus_sha256": hashlib.sha256(requests_path.read_bytes()).hexdigest(),
                "served_models": None, "setup_error": None}
    if strict_tasks:
        manifest["request_provenance"] = request_provenance
        manifest["frozen_request_file_sha256"] = (hashlib.sha256(Path(requests_file).read_bytes()).hexdigest()
                                                  if requests_file is not None else None)
    records, outputs = [], []
    try:
        served = _request_json(endpoint + "/models", timeout=timeout)
        manifest["served_models"] = served
        if (not isinstance(served, dict) or not isinstance(served.get("data"), list)
                or model not in {entry.get("id") for entry in served["data"] if isinstance(entry, dict)}):
            raise ValueError("requested model is not advertised by /models")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        manifest["setup_error"] = {"type": type(error).__name__, "message": str(error)}

    responses_path = out_dir / "responses.jsonl"
    with responses_path.open("wb") as response_file:
        if manifest["setup_error"] is None:
            for row in requests:
                payload = {"model": model, "messages": [
                    {"role": "system", "content": row["system"]},
                    {"role": "user", "content": row["user"]}], **decoding}
                record = {"case_id": row["case_id"], "condition": row["condition"],
                          "status": "RECEIVED", "response": {}, "parse_error": None,
                          "raw_text": None, "raw_response": None, "finish_reason": None,
                          "usage": None, "error": None}
                before = time.perf_counter()
                try:
                    raw = _request_json(endpoint + "/chat/completions", payload=payload, timeout=timeout)
                    record["raw_response"] = raw
                    if not isinstance(raw, dict):
                        raise ValueError("completion API response is not an object")
                    record["usage"] = raw.get("usage")
                    choices = raw.get("choices")
                    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                        raise ValueError("completion API response has no first choice")
                    choice = choices[0]
                    record["finish_reason"] = choice.get("finish_reason")
                    message = choice.get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    record["raw_text"] = content
                    record["response"] = parse_model_json(content)
                    if strict_tasks:
                        error = production_response_error(record["response"], row)
                        if error:
                            raise ValueError(error)
                    else:
                        field = "answer" if row["task"] == "document_qa" else "entity_id"
                        if malformed_response_field(record["response"], field):
                            raise ValueError(f"response {field} must be present and string or null")
                except HTTPError as error:
                    record["status"] = "HTTP_ERROR"
                    record["error"] = {"type": type(error).__name__, "http_status": error.code,
                                       "message": str(error)}
                    record.pop("response")
                except (URLError, TimeoutError, OSError) as error:
                    record["status"] = "TRANSPORT_ERROR"
                    record["error"] = {"type": type(error).__name__, "message": str(error)}
                    record.pop("response")
                except ValueError as error:
                    record["status"] = "MALFORMED"
                    record["parse_error"] = {"type": type(error).__name__, "message": str(error)}
                record["latency_ms"] = round((time.perf_counter() - before) * 1000, 3)
                response_file.write(_json_bytes(record))
                response_file.flush()
                records.append(record)
                if "response" in record:
                    outputs.append(record)

    local_checks = ({"request_contract_validated": True,
                     "execution_uses_raw_complete_response": True} if strict_tasks else local_swap_checks())
    if baseline:
        local_checks.update(ktrf_resolver_used=False, ktrf_guard_used=False,
                            execution_validation="schema and provided glossary ID membership only")
    if document_context or definition_control:
        local_checks.update(execution_validation="condition-specific; KTRF guard only for KTRF knowledge",
                            original_documents_preserved=True)
    graded = {"local_checks": local_checks,
              "model_results": grader(requests, outputs)}
    if strict_tasks:
        graded["model_results"]["limitations"] = list(declared_protocol["limitations"])
    missing = graded["model_results"]["missing_outputs"]
    errors = sum(record["error"] is not None for record in records)
    manifest.update({"finished_at": datetime.now(timezone.utc).isoformat(),
                     "status": "COMPLETE" if not missing and not errors else "INCOMPLETE",
                     "received_count": len(outputs), "missing_count": missing,
                     "error_count": errors, "malformed_count": sum(r["status"] == "MALFORMED" for r in records),
                     "finish_reason_counts": {}, "actual_usage": {}})
    for record in records:
        reason = str(record["finish_reason"])
        manifest["finish_reason_counts"][reason] = manifest["finish_reason_counts"].get(reason, 0) + 1
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [r["usage"][key] for r in records if isinstance(r["usage"], dict)
                  and isinstance(r["usage"].get(key), int) and not isinstance(r["usage"][key], bool)
                  and r["usage"][key] >= 0]
        manifest["actual_usage"][key] = {"total": sum(values), "observed_responses": len(values)}
    (out_dir / "graded.json").write_bytes(_json_bytes(graded))
    manifest["artifact_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in (requests_path, responses_path, out_dir / "graded.json")}
    manifest["seal_sha256"] = hashlib.sha256(_json_bytes(manifest)).hexdigest()
    (out_dir / "run_manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Existing server base URL including /v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--out-dir", type=Path, required=True, help="New exclusive artifact directory")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--omit-seed", action="store_true", help="Only when endpoint lacks seed support")
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--track", choices=("factorial", "contract_probe", "synthetic_expansion",
                                           "synthetic_expansion_v2", "qa_policy_probe",
                                           "production_synthetic", "production_real",
                                           "baseline_synthetic", "baseline_real", "document_context", "definition_control"), default="factorial")
    parser.add_argument("--requests-file", type=Path,
                        help="Frozen production, baseline, document context or definition control envelope with protocol, provenance and requests")
    args = parser.parse_args()
    manifest = run_benchmark(endpoint=args.endpoint, model=args.model, out_dir=args.out_dir,
        code_revision=args.code_revision, max_tokens=args.max_tokens, timeout=args.timeout,
        seed=None if args.omit_seed else 0, enable_thinking=args.enable_thinking,
        track=args.track, requests_file=args.requests_file)
    print(json.dumps({"out_dir": str(args.out_dir), "status": manifest["status"],
                      "received": manifest["received_count"], "missing": manifest["missing_count"],
                      "errors": manifest["error_count"], "malformed": manifest["malformed_count"]}))
    return 0 if manifest["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

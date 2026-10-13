"""Run the frozen synthetic product intervention track against a live endpoint.

Only each case's system/user strings reach the model. Ground truth and resolver
packs stay in the local request artifact and grader. No retries or answer repair
are performed: malformed outputs and transport failures remain distinct.
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

from eval.product_utility import build_requests, grade_outputs, local_swap_checks


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
                  timeout=180, seed=0, enable_thinking=False):
    """Serial requests to an existing server, returning a sealed run manifest."""
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("endpoint must be an HTTP(S) base URL without credentials or query")
    if max_tokens <= 0 or timeout <= 0 or not code_revision:
        raise ValueError("positive token/timeout budgets and code revision are required")
    endpoint = endpoint.rstrip("/")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    requests = build_requests()
    requests_path = out_dir / "requests.jsonl"
    requests_path.write_bytes(b"".join(_json_bytes(row) for row in requests))
    decoding = {"temperature": 0, "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": enable_thinking}}
    if seed is not None:
        decoding["seed"] = seed
    manifest = {"protocol": "product_utility_live_v1", "code_revision": code_revision,
                "started_at": started, "endpoint": endpoint, "requested_model": model,
                "request_count": len(requests), "decoding": decoding, "timeout_seconds": timeout,
                "prompt_fields": ["system", "user"], "request_order": "build_requests order; serial",
                "response_parser": "JSON object, bare or one enclosing JSON code fence; no extra prose",
                "retries": 0, "request_corpus_sha256": hashlib.sha256(requests_path.read_bytes()).hexdigest(),
                "served_models": None, "setup_error": None}
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

    graded = {"local_checks": local_swap_checks(), "model_results": grade_outputs(requests, outputs)}
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
    args = parser.parse_args()
    manifest = run_benchmark(endpoint=args.endpoint, model=args.model, out_dir=args.out_dir,
        code_revision=args.code_revision, max_tokens=args.max_tokens, timeout=args.timeout,
        seed=None if args.omit_seed else 0, enable_thinking=args.enable_thinking)
    print(json.dumps({"out_dir": str(args.out_dir), "status": manifest["status"],
                      "received": manifest["received_count"], "missing": manifest["missing_count"],
                      "errors": manifest["error_count"], "malformed": manifest["malformed_count"]}))
    return 0 if manifest["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

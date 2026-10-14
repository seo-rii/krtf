"""Freeze the document matrix and check real model context lengths before inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from eval.run_production_queue import canonical, file_hash, save_json


def freeze(out_dir, code_revision):
    from eval.document_context import build_document_context_envelope
    envelope = build_document_context_envelope()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / 'documents.json'
    path.write_bytes(canonical(envelope))
    rows = envelope['requests']
    manifest = {'code_revision': code_revision, 'corpora': {'documents': {
        'file': path.name, 'envelope_sha256': file_hash(path),
        'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
        'request_count': len(rows), 'document_count': len({r['document_id'] for r in rows})}}}
    save_json(out_dir / 'manifest.json', manifest)
    return manifest


def check_tokens(plan):
    """Use the checkpoints' real templates; reject overflow instead of truncating."""
    from transformers import AutoTokenizer
    from eval.run_production_queue import validate_requests
    result = {'code_revision': plan['code_revision'], 'models': {}, 'exit_code': None,
              'max_model_len': 8192, 'reserved_output_tokens': 128}
    for stage in plan['stages']:
        model = plan['models'][stage['model_key']]
        rows = validate_requests(stage)['requests']
        tokenizer = AutoTokenizer.from_pretrained(model['path'], local_files_only=True)
        lengths = []
        for row in rows:
            token_ids = tokenizer.apply_chat_template(
                [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['user']}],
                tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False)
            # Transformers may otherwise return BatchEncoding, whose length counts
            # fields (e.g. input_ids and attention_mask), not tokens.
            if not isinstance(token_ids, list) or not token_ids or any(type(t) is not int for t in token_ids):
                raise ValueError('tokenizer must return a nonempty flat list of token IDs')
            lengths.append(len(token_ids))
        result['models'][stage['model_key']] = {
            'model_path': model['path'], 'requests_sha256': stage['requests_sha256'],
            'request_count': len(rows), 'min_prompt_tokens': min(lengths),
            'max_prompt_tokens': max(lengths), 'all_prompt_tokens': lengths,
            'overflow_count': sum(n + 128 > 8192 for n in lengths)}
    result['exit_code'] = int(any(m['overflow_count'] for m in result['models'].values()))
    save_json(plan['token_status'], result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--code-revision')
    parser.add_argument('--check-tokens-plan', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.check_tokens_plan:
        result = check_tokens(json.loads(args.check_tokens_plan.read_text()))
        print(json.dumps({'exit_code': result['exit_code'], 'models': {
            k: {f: v[f] for f in ('request_count', 'max_prompt_tokens', 'overflow_count')}
            for k, v in result['models'].items()}}))
        return result['exit_code']
    if args.out_dir is None or not args.code_revision:
        parser.error('--out-dir and --code-revision are required for freezing')
    print(json.dumps(freeze(args.out_dir, args.code_revision)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

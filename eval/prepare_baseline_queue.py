"""Freeze no-resolver glossary controls and their sealed KTRF references."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from eval.production_baseline import build_baseline_envelopes
from eval.run_production_queue import canonical, file_hash


def freeze_requests(out_dir, *, code_revision):
    envelopes = build_baseline_envelopes()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    summary = {"code_revision": code_revision, "corpora": {}}
    for corpus, envelope in envelopes.items():
        path = out_dir / (corpus + '.json')
        path.write_bytes(canonical(envelope))
        rows = envelope['requests']
        summary['corpora'][corpus] = {
            'file': path.name, 'envelope_sha256': file_hash(path),
            'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
            'request_count': len(rows), 'document_count': len({r['document_id'] for r in rows}),
        }
    (out_dir / 'manifest.json').write_bytes(canonical(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--code-revision', required=True)
    args = parser.parse_args()
    print(json.dumps(freeze_requests(args.out_dir, code_revision=args.code_revision)))


if __name__ == '__main__':
    main()

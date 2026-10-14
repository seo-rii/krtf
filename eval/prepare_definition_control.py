"""Freeze old contextual cases and separately authored definition cases together."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from eval.definition_control import build_envelope
from eval.document_context import FIXTURE
from eval.run_production_queue import canonical, file_hash, save_json

NEW_FIXTURE = FIXTURE.parent.parent/'context_definitions'/'families.jsonl'


def freeze(out_dir, code_revision):
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=False)
    families = {}
    hashes = {}
    original_ids = set()
    for fixture in (FIXTURE, NEW_FIXTURE):
        hashes[str(fixture.relative_to(Path(__file__).parent))] = file_hash(fixture)
        for line in fixture.read_text().splitlines():
            family = json.loads(line)
            if fixture == FIXTURE:
                original_ids.update(d['document_id'] for d in family['documents'])
            key = family['family_id']
            if key in families:
                prior = families[key]
                if any(prior[field] != family[field] for field in ('terms', 'knowledge_document')):
                    raise ValueError('new documents must use the identical registered glossary')
                prior['documents'].extend(deepcopy(family['documents']))
            else:
                families[key] = deepcopy(family)
    source = root/'source_corpus.jsonl'
    source.write_bytes(b''.join(canonical(f) for f in families.values()))
    envelope = build_envelope(source)
    for row in envelope['requests']:
        row['collection'] = 'original_context' if row['document_id'] in original_ids else 'fresh_definition'
    documents = {row['document_id']: row for row in envelope['requests']}
    if len(documents) != 64 or len(envelope['requests']) != 768:
        raise ValueError('predeclared corpus requires 64 documents and 768 requests')
    envelope['provenance'].update(source_fixture_sha256=hashes,
        original_document_count=32, fresh_document_count=32,
        source_collection_split={did: row['collection'] for did, row in documents.items()})
    path = root/'documents.json'
    path.write_bytes(canonical(envelope))
    manifest = {'code_revision': code_revision, 'corpora': {'documents': {
        'file': path.name, 'envelope_sha256': file_hash(path),
        'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in envelope['requests'])).hexdigest(),
        'request_count': len(envelope['requests']), 'document_count': len(documents),
        'gold_labels': dict(Counter(row['gold']['label'] for row in documents.values()))}},
        'source_fixture_sha256': hashes, 'combined_source_sha256': file_hash(source)}
    save_json(root/'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--code-revision', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(freeze(args.out_dir,args.code_revision)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

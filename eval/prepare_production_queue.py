"""Freeze production requests for both models before any model response exists."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from eval.production_grounding import PROTOCOL, build_document_requests, build_production_requests
from eval.run_production_queue import canonical, file_hash
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot

FIXTURE = Path(__file__).parent / 'fixtures' / 'production_real_holdout'


def build_real_envelope(fixture=FIXTURE):
    fixture = Path(fixture)
    files = ('documents.jsonl', 'annotations.ai.jsonl', 'annotations.review.jsonl',
             'annotations.adjudicated.jsonl', 'adjudication.json', 'glossary.yaml', 'manifest.json')
    hashes = {name: file_hash(fixture / name) for name in files}
    manifest = json.loads((fixture / 'manifest.json').read_text())
    if not manifest.get('adjudicated') or not manifest.get('independent_ai_review'):
        raise ValueError('real holdout review must be sealed before preparing requests')
    for name, expected in manifest['files'].items():
        if Path(name).name != name or file_hash(fixture / name) != expected['sha256']:
            raise ValueError('sealed holdout file mismatch: ' + name)
    documents = [json.loads(line) for line in (fixture / 'documents.jsonl').read_text().splitlines() if line]
    annotations = [json.loads(line) for line in (fixture / 'annotations.adjudicated.jsonl').read_text().splitlines() if line]
    by_id = {a['document_id']: a for a in annotations}
    if len(by_id) != len(annotations) or set(by_id) != {d['document_id'] for d in documents}:
        raise ValueError('all selected documents need exactly one frozen annotation')
    if len(documents) != len({d['document_id'] for d in documents}):
        raise ValueError('duplicate real document')
    snapshot = compile_snapshot(load_glossary(str(fixture / 'glossary.yaml')), run_conformance=False)
    rows = []
    for doc in documents:
        if hashlib.sha256(doc['text'].encode()).hexdigest() != doc['document_sha256']:
            raise ValueError('source document hash mismatch')
        annotation = by_id[doc['document_id']]
        if annotation.get('human_verified') is not False or annotation.get('annotation_origin') != 'AI_AUTHORED_NOT_HUMAN':
            raise ValueError('real annotations must declare AI origin and no human verification')
        if annotation.get('adjudicated') is not True:
            raise ValueError('independent AI review and adjudication must be closed before freezing')
        target = annotation['primary_target']
        entity = snapshot.glossary.entity(target['gold'].get('entity_ref')) if target['gold'].get('entity_ref') else None
        if entity and target['expected_answer'] != entity.description:
            raise ValueError('linked answer must retain the frozen source definition')
        rows.extend(build_document_requests(snapshot,
            document_id=doc['document_id'],
            family_id='real:' + (target['gold'].get('entity_ref') or target['gold'].get('core_entity_ref') or doc['document_id']),
            domain='real_document', stratum='real_' + target['gold']['label'].lower(),
            text=doc['text'], target_surface=target['target_surface'], target_span=target['target_span'],
            gold=target['gold'], expected_answer=target['expected_answer'],
            provenance={key: value for key, value in doc.items() if key != 'text'} | {
                'annotation_origin': annotation['annotation_origin'], 'human_verified': False,
                'annotation_sha256': hashlib.sha256(canonical(annotation)).hexdigest(),
                'fixture_file_sha256': hashes, 'rationale': target['rationale']}))
    protocol = {**deepcopy(PROTOCOL), 'kind': 'production_grounding_real_holdout_v1',
        'source_corpus': 'fresh_konec_sentence_holdout', 'gold_origin': 'AI_AUTHORED_NOT_HUMAN',
        'gold_source': 'AI annotations of real source sentences and frozen glossary before resolver or model outputs.',
        'limitations': [
            'Real text, AI-authored gold; not independent human gold or a deployment risk bound.',
            'Declared lexical/NER stratified sentence sample; not a random deployment audit.',
            'Source article IDs are unavailable; sentence-level IDs do not establish article-level independence.',
            'One primary target per selected sentence; not exhaustive end-to-end mention recall.',
            'Local prior-data hash exclusion does not establish absence from model pretraining.',
            'Domestic administrative-unit territorial names follow the declared glossary convention; three primary labels required adjudication.',
            *[x for x in PROTOCOL['limitations'] if not x.startswith('Previously evaluated')]]}
    return {'protocol': protocol, 'provenance': {'fixture': str(fixture.name), 'file_sha256': hashes,
            'documents': len(documents), 'human_verified': False}, 'requests': rows}


def freeze_requests(out_dir, *, code_revision):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    envelopes = {
        'synthetic': {'protocol': PROTOCOL, 'provenance': {'source': 'balanced_synthetic_v2',
            'code_revision': code_revision, 'frozen_before_live_inference': True},
            'requests': build_production_requests()},
        'real': build_real_envelope(),
    }
    summary = {'code_revision': code_revision, 'corpora': {}}
    for name, envelope in envelopes.items():
        path = out_dir / (name + '.json')
        path.write_bytes(canonical(envelope))
        summary['corpora'][name] = {'file': path.name, 'envelope_sha256': file_hash(path),
            'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in envelope['requests'])).hexdigest(),
            'request_count': len(envelope['requests']),
            'document_count': len({r['document_id'] for r in envelope['requests']})}
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

import hashlib
import json
import shutil
import sys
from pathlib import Path

from eval.occurrence_evidence_corpus import build_cases
from eval.run_rerank_ablation import model_digest

meta = json.loads(Path(sys.argv[1]).read_text())
root = Path(meta['source'])
out = Path(meta['remote_root']) / 'results'
fixture_dir = root / 'eval/fixtures/occurrence_evidence_holdout'
cases = []
for cohort, relative in [('development', 'eval/fixtures/context_ranking_challenge/families.jsonl'),
                         ('heldout', 'eval/fixtures/occurrence_evidence_holdout/families.jsonl')]:
    events = build_cases(root / relative, cohort=cohort)
    cases.extend(events)
    payload = ''.join(json.dumps(case, ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':')) + '\n' for case in events)
    (out / (cohort + '_cases.jsonl')).write_text(payload, encoding='utf-8')
for name in ['protocol.json', 'annotation_manifest.json', 'blind_review.jsonl',
             'annotation_adjudication.json']:
    shutil.copyfile(fixture_dir / name, out / name)
annotation = json.loads((out / 'annotation_manifest.json').read_text())
if annotation['review_status'] != 'ADJUDICATED_BEFORE_INFERENCE':
    raise RuntimeError('annotation review did not complete before inference')
fixture_hash = hashlib.sha256((fixture_dir / 'families.jsonl').read_bytes()).hexdigest()
if fixture_hash != annotation['final_fixture_sha256']:
    raise RuntimeError('annotation review refers to a different fixture')
selector_hash = hashlib.sha256((root / 'ktrf/occurrence_evidence.py').read_bytes()).hexdigest()
if selector_hash != annotation['selector_source_sha256']:
    raise RuntimeError('selector changed after held-out annotation')
digest = model_digest(Path(meta['model_dir']))
(out / 'checkpoint.json').write_text(json.dumps({
    'model_id': meta['model_id'], 'revision': meta['model_revision'],
    'content_sha256': digest}, indent=2) + '\n')
if digest != meta['expected_model_sha256']:
    raise RuntimeError('pinned checkpoint differs from earlier comparison')
print(json.dumps({'development_events': 384, 'heldout_events': 168,
                  'events': len(cases), 'fixture_sha256': fixture_hash,
                  'selector_sha256': selector_hash, 'model_sha256': digest}))

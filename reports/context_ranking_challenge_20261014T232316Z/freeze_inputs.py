import hashlib
import json
import shutil
import sys
from pathlib import Path

from eval.context_ranking_challenge import build_cases
from eval.run_rerank_ablation import model_digest

meta = json.loads(Path(sys.argv[1]).read_text())
root = Path(meta['source'])
out = Path(meta['remote_root']) / 'results'
cases = build_cases()
payload = ''.join(json.dumps(case, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')) + '\n' for case in cases)
(out / 'cases.jsonl').write_text(payload, encoding='utf-8')
fixture_dir = root / 'eval/fixtures/context_ranking_challenge'
for name in ['protocol.json', 'annotation_manifest.json', 'blind_review.jsonl',
             'annotation_adjudication.json']:
    shutil.copyfile(fixture_dir / name, out / name)
annotation = json.loads((out / 'annotation_manifest.json').read_text())
if annotation['review_status'] != 'ADJUDICATED_BEFORE_INFERENCE':
    raise RuntimeError('annotation review has not completed before inference')
fixture_hash = hashlib.sha256((fixture_dir / 'families.jsonl').read_bytes()).hexdigest()
if fixture_hash != annotation['final_fixture_sha256']:
    raise RuntimeError('annotation review refers to different fixture')
digest = model_digest(Path(meta['model_dir']))
(out / 'checkpoint.json').write_text(json.dumps({
    'model_id': meta['model_id'], 'revision': meta['model_revision'],
    'content_sha256': digest}, indent=2) + '\n')
if digest != meta['expected_model_sha256']:
    raise RuntimeError('pinned checkpoint content hash differs from prior run')
print(json.dumps({'cases': len(cases),
                  'cases_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                  'fixture_sha256': fixture_hash, 'model_sha256': digest}))

import hashlib
import json
import sys
from pathlib import Path

from eval.context_ranking_corpus import build_cases
from eval.context_ranking_risk import predeclared_protocol
from eval.run_context_ranking import INPUT_VARIANTS, model_digest

meta = json.loads(Path(sys.argv[1]).read_text())
out = Path(meta['remote_root']) / 'results'
cases = build_cases()
payload = ''.join(json.dumps(case, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')) + '\n' for case in cases)
(out / 'cases.jsonl').write_text(payload, encoding='utf-8')
protocols = {kind: predeclared_protocol(kind, INPUT_VARIANTS)
             for kind in ('lexical', 'nano')}
(out / 'protocols.json').write_text(json.dumps(protocols, indent=2) + '\n')
digest = model_digest(Path(meta['model_dir']))
(out / 'checkpoint.json').write_text(json.dumps({
    'model_id': meta['model_id'], 'revision': meta['model_revision'],
    'content_sha256': digest}, indent=2) + '\n')
if digest != meta['expected_model_sha256']:
    raise RuntimeError('pinned checkpoint content hash differs from earlier run')
print(json.dumps({'cases': len(cases),
                  'cases_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                  'model_sha256': digest}))

# Decision and calibration safety

Commit decisions use all policy-valid retrieved candidates, before any
prediction-set/output truncation. The second-best probability and margin are
computed even when a competitor is excluded by conformal membership. Reducing
`max_prediction_set` cannot promote an uncertain link. `total_member_count`,
`truncated`, and `decision_margin` describe the uncut decision and delivered
list. Retrieval-pool truncation continues to block commitments.

Prediction-set metadata distinguishes a target from a verified guarantee:

- `calibration_status`: `HEURISTIC` or `FITTED` in a successful response.
  Failed fitting reports `INSUFFICIENT_DATA` in API error details and preserves
  the active snapshot.
- `set_confidence`: null in the heuristic path; fitted nominal target otherwise.
- `target_set_confidence`: configured nominal target, including heuristic mode.
- `coverage_scope`: `candidate_conditional`, never end-to-end or commit precision.
- `coverage_valid`: false for heuristics, correction-selected or legacy fits,
  unsupported groups, retrieval truncation, or response truncation.

`KB_MISSING` is retained for wire compatibility, but carries
`reason=NO_COMPATIBLE_RETRIEVED_CANDIDATE` and `kb_absence_verified=false`.
It must not be interpreted as proof that the glossary lacks an entity.

## Source-event splitting

TrainingExample carries event/document/request/mention/correction IDs. Shared
IDs connect rows transitively, and complete connected groups enter a
label-independent deterministic split. IDs must be namespaced by corpus and
tenant. Missing source IDs or insufficient independent groups/labels refuse
fitting; there is no whole-data fallback. Extraction accepts only approved
corrections and preserves source references. Verifier repetitions affect
Platt fitting but positive calibration observations are deduplicated per
source mention. Learned fusion trains on the same fitting partition as Platt,
so its own training rows cannot leak into the conformal partition.

Fit and runtime use one stable, full-precision sigmoid. Probability clipping
and rounding do not affect conformal boundaries. Old calibrator artifacts
remain loadable but have unvalidated coverage; refit them to migrate.

Correction selection is not random sampling. `sample_source=random_audit` is
reserved for separately collected, representative random audit data with a
frozen upstream model/retrieval pipeline. Declaring it is a caller contract,
not statistical evidence created by the software. Group support and split
provenance are necessary checks; distribution shift, correlated samples, or
adaptive reuse invalidate coverage. Calibrator manifests record partitions,
not end-to-end accuracy. Use independent blind documents for final risk tests.

## Verification

`python -m pytest -q tests/test_calibration_safety.py tests/test_artifacts_finetune.py tests/test_adversarial_regressions.py tests/test_resolver_api.py`

These are structural regressions, not measurements of deployment precision.

# Compiled snapshot immutability

Compilation detaches the glossary, policy, guard, and diagnostic configuration
from authoring objects. The resulting `Snapshot` is a frozen dataclass; its
nested configuration has sealed attributes and immutable dictionary/list
containers. Calibrators and learned fusion attached with `dataclasses.replace`
are also copied and sealed. Changing an authoring entity, alias boundary,
policy budget, or guard rule after compilation cannot alter the compiled
snapshot's decisions. Normal authoring dataclasses remain mutable.

`SnapshotRuntime` holds exact/fuzzy/abbreviation indexes, the particle FST,
document-local detector, dense retrieval artifacts, reranker sessions, and a
mutable cache dictionary. Existing backend accessors such as
`snapshot.exact_index` remain available. Its holder references are frozen;
backend internals and native sessions are runtime objects and are not claimed
to be immutable or protected against direct modification. Cache keys must
include snapshot identity when a runtime is shared. Existing segmentation
memoization remains outside configuration and includes the FST in its key.
Configuration mutation guards are a Python API contract, not a security
boundary against `object.__setattr__`, base-class container mutation, or native
memory writes.

To change configuration, compile a new snapshot or create a replacement with
`dataclasses.replace` and recompute its identity from an updated manifest.
Activation remains a separate registry operation. Layered compilation and
artifact loading construct replacements instead of mutating a published
snapshot. Existing request code continues to pin one snapshot reference for
its complete resolution.

JSON serialization and `dataclasses.asdict` retain the schema's dictionary/list
shapes. Artifact save converts immutable containers to ordinary containers for
YAML. `ktrf.immutable.thaw` provides a detached mutable export when an authoring
workflow needs editable container data.

## Bundle compatibility and guards

Bundles now preserve the guard in `guard.json`; loading recompiles with that
guard and verifies `segmentation_guard_hash`. A missing guard file is compatible
only with the default guard whose hash matches the manifest. Tampering with a
custom guard is rejected.

The manifest includes `resolver_semantics_version`, currently
`safety-2-path-union-1`, so the output-budget safety and path-union rules have an
explicit content identity. Bundles missing this version, or carrying another
version, are rejected by `load_snapshot`; rebuild from their original glossary
and policy and rerun conformance before activation. A bundle without the new
field is not silently accepted under new resolver semantics.

`RuntimePolicy.rerank_input` accepts `surface`, `context`, `target`, or `path`;
its default is `context`. The selected input variant is included in the policy
hash and changes snapshot identity.

## Validation

Regressions cover mutations of authoring data and nested compiled configuration,
calibrator/fusion copying, YAML/JSON bundle roundtrips, custom guard roundtrips
and tampering, cold/warm cache equivalence, old-snapshot stability after
activation, concurrent registry reads, candidate insertion-order ties, and
legacy manifest rejection. Focused snapshot, artifact, registry, neural,
product, and offset validation passed 108 tests.

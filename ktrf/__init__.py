"""KTRF — Korean Terminology Resolver Framework (V1 symbolic core)."""

__all__ = ["__version__"]

# Single-sourced from the package metadata so the wheel and the runtime can
# never disagree about which version this is. An editable/source checkout
# that was never installed has no metadata; report that honestly rather
# than inventing a number a bug report would then cite.
try:  # pragma: no cover - trivial, and untestable in both states at once
    from importlib.metadata import PackageNotFoundError, version as _version

    __version__ = _version("ktrf")
except Exception:  # PackageNotFoundError, or no metadata at all
    __version__ = "0.0.0+unknown"


def __getattr__(name):
    # Lazy re-exports so subsets of the package are importable during builds.
    if name in ("load_glossary", "validate_glossary", "GlossaryError"):
        from . import glossary as m
        return getattr(m, name)
    if name in ("compile_snapshot", "SnapshotRegistry"):
        from . import snapshot as m
        return getattr(m, name)
    if name == "resolve":
        from .resolver import resolve
        return resolve
    if name == "KtrfApiError":
        from .errors import KtrfApiError
        return KtrfApiError
    if name in ("save_snapshot", "load_snapshot", "finetune"):
        from . import artifacts as m
        return getattr(m, name)
    if name == "CorrectionStore":
        from .corrections import CorrectionStore
        return CorrectionStore
    if name in ("VariantMiner", "MiningReport", "SuffixGap", "NameGap"):
        from . import mining as m
        return getattr(m, name)
    if name in ("NewTermDefinition", "align_definition"):
        from . import doclocal as m
        return getattr(m, name)
    if name in ("TunedCalibrator", "fit_calibrator", "empirical_coverage"):
        from . import calibration as m
        return getattr(m, name)
    if name in ("HashEncoder", "OnnxE5Encoder", "load_encoder"):
        from . import encoders as m
        return getattr(m, name)
    if name in ("LexicalCrossEncoder", "OnnxCrossEncoder", "load_reranker"):
        from . import rerank as m
        return getattr(m, name)
    if name in ("FusionModel", "fit_fusion"):
        from . import fusion as m
        return getattr(m, name)
    if name == "ResolveJobManager":
        from .jobs import ResolveJobManager
        return ResolveJobManager
    if name == "TieredSnapshotStore":
        from .tiers import TieredSnapshotStore
        return TieredSnapshotStore
    if name == "RuntimeMetrics":
        from .metrics import RuntimeMetrics
        return RuntimeMetrics
    if name in ("ContextPolicy", "build_context_pack", "render_context_pack",
                "prepare_llm_context", "validate_llm_grounding",
                "TERMINOLOGY_POLICY"):
        from . import context as m
        return getattr(m, name)
    if name in ("explain_resolution", "lookup_surface"):
        from . import explain as m
        return getattr(m, name)
    if name in ("compile_simple_terms", "TermLayer", "load_term_layers",
                "compile_layered_glossary", "TermProposalStore",
                "TermAdmissionPolicy"):
        from . import registry as m
        return getattr(m, name)
    if name == "compile_layered_snapshot":
        from .registry.layers import compile_layered_snapshot
        return compile_layered_snapshot
    raise AttributeError(name)

"""KTRF — Korean Terminology Resolver Framework (V1 symbolic core)."""

__all__ = []


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
    raise AttributeError(name)

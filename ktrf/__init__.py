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
    raise AttributeError(name)

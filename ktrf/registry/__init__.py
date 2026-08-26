"""Terminology registry: simple authoring schema, layered scopes, and the
proposal/admission workflow for agent integrations (see PLAN_PI.md).

The resolver core stays unchanged — this package only produces glossaries
and governs *what may enter them*:

- :mod:`ktrf.registry.simple_schema` compiles a human-authored
  ``terms.yaml`` into a full KTRF glossary (stable ids, alias families,
  normalization profiles, provenance).
- :mod:`ktrf.registry.layers` merges Base → Global → Project → Session →
  Document scopes with explicit precedence and shadowing provenance.
- :mod:`ktrf.registry.proposals` implements the term lifecycle
  (OBSERVED → PROPOSED → VALIDATED → PROVISIONAL/ACTIVE) with
  deterministic validation, so an LLM can propose terms but never
  self-activate them.
"""

from __future__ import annotations

__all__ = [
    "compile_simple_terms",
    "SimpleTermsError",
    "LAYER_ORDER",
    "TermLayer",
    "load_term_layers",
    "compile_layered_glossary",
    "TermProposal",
    "TermProposalStore",
    "TermAdmissionPolicy",
]


def __getattr__(name):
    if name in ("compile_simple_terms", "SimpleTermsError"):
        from . import simple_schema as m
        return getattr(m, name)
    if name in ("LAYER_ORDER", "TermLayer", "load_term_layers",
                "compile_layered_glossary"):
        from . import layers as m
        return getattr(m, name)
    if name in ("TermProposal", "TermProposalStore", "TermAdmissionPolicy"):
        from . import proposals as m
        return getattr(m, name)
    raise AttributeError(name)

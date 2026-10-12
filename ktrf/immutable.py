"""Detached immutable configuration copies with JSON-compatible containers.

Authoring objects stay mutable; only compiled copies are sealed. These are API
mutation guards, not a sandbox against object.__setattr__ or native backends.
"""
from __future__ import annotations
from dataclasses import FrozenInstanceError


def _blocked(*args, **kwargs):
    raise TypeError("compiled snapshot configuration is immutable")


class FrozenDict(dict):
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _blocked
    def __deepcopy__(self, memo):
        return self


class FrozenList(list):
    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = __iadd__ = __imul__ = _blocked
    def __deepcopy__(self, memo):
        return self


_SEALED_TYPES = {}


def _sealed_setattr(self, name, value):
    if getattr(self, "_snapshot_sealed", False):
        raise FrozenInstanceError("compiled snapshot configuration is immutable")
    object.__setattr__(self, name, value)


def _sealed_delattr(self, name):
    if getattr(self, "_snapshot_sealed", False):
        raise FrozenInstanceError("compiled snapshot configuration is immutable")
    object.__delattr__(self, name)


def freeze(value, memo=None):
    """Clone/seal a config graph, retaining methods. Never pass live backends."""
    if isinstance(value, (FrozenDict, FrozenList)) or getattr(value, "_snapshot_sealed", False):
        return value
    if memo is None:
        memo = {}
    if id(value) in memo:
        return memo[id(value)]
    if isinstance(value, dict):
        result = FrozenDict((freeze(k, memo), freeze(v, memo)) for k, v in value.items())
    elif isinstance(value, list):
        result = FrozenList(freeze(v, memo) for v in value)
    elif isinstance(value, tuple):
        result = tuple(freeze(v, memo) for v in value)
    elif isinstance(value, (set, frozenset)):
        result = frozenset(freeze(v, memo) for v in value)
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        cls = type(value)
        sealed_type = _SEALED_TYPES.get(cls)
        if sealed_type is None:
            sealed_type = type(f"Sealed{cls.__name__}", (cls,), {
                "__setattr__": _sealed_setattr, "__delattr__": _sealed_delattr,
                "__module__": __name__})
            _SEALED_TYPES[cls] = sealed_type
        result = object.__new__(sealed_type)
        memo[id(value)] = result
        for name, member in vars(value).items():
            object.__setattr__(result, name, freeze(member, memo))
        object.__setattr__(result, "_snapshot_sealed", True)
    else:
        return value
    memo[id(value)] = result
    return result


def thaw(value):
    """Return plain mutable containers for serialization/export."""
    if isinstance(value, dict):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, list):
        return [thaw(v) for v in value]
    if isinstance(value, tuple):
        return tuple(thaw(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return set(thaw(v) for v in value)
    return value

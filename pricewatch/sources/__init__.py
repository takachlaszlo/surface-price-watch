"""Source adapter registry. Every module in this package registers its adapter(s)."""
from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

from .base import Source, SourceContext

REGISTRY: dict[str, type[Source]] = {}


def register(name: str) -> Callable[[type[Source]], type[Source]]:
    def decorator(cls: type[Source]) -> type[Source]:
        REGISTRY[name] = cls
        return cls
    return decorator


def load_adapters() -> dict[str, type[Source]]:
    for module in pkgutil.iter_modules(__path__):
        if module.name != "base":
            importlib.import_module(f"{__name__}.{module.name}")
    return REGISTRY


__all__ = ["REGISTRY", "Source", "SourceContext", "load_adapters", "register"]

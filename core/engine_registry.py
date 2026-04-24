"""
atlas_viewer.core.engine_registry
===================================
Static engine registry — zero importlib, zero dynamic dispatch.

Why this file exists
--------------------
The previous ``PluginKernel`` used ``importlib.import_module`` to load engine
modules by string name at runtime.  Under a Nuitka ``--onefile`` build the
optimizer can:

  1. Inline modules aggressively, changing their runtime module names.
  2. Reorder initialization, breaking side-effect-based registrations.
  3. Drop ``importlib`` calls it cannot statically trace.

This replacement uses ONLY explicit top-level ``import`` statements.
Nuitka follows explicit imports at compile time and guarantees they are
present in the binary.

Usage
-----
::

    # main.py — replace PluginKernel.initialize() with:
    from core.engine_registry import EngineRegistry

    # DocumentService — replace EngineRegistry import:
    from core.engine_registry import EngineRegistry

No initialization call needed.  The registry is populated at import time.

Adding a new engine
-------------------
1. Write your engine class (subclasses AbstractDocumentEngine).
2. Add a top-level import here.
3. Add a line to _STATIC_ENGINES.
That is all.  No decorators, no manifest lists, no importlib.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from core.document_engine import AbstractDocumentEngine

# ── Static engine imports — Nuitka will always compile these ─────────────────
# ADD NEW ENGINES HERE as explicit imports.
from core.qtpdf_engine import QtPdfEngine

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static mapping: extension → engine class
# ONE engine per extension.  No fallbacks, no loops.
# ---------------------------------------------------------------------------
_STATIC_ENGINES: Dict[str, Type[AbstractDocumentEngine]] = {
    ".pdf": QtPdfEngine,
}


class EngineRegistry:
    """
    Immutable at runtime — populated from _STATIC_ENGINES at import time.

    Thread-safe for reads (dict is never mutated after module load).
    """

    _registry: Dict[str, Type[AbstractDocumentEngine]] = {}

    @classmethod
    def _bootstrap(cls) -> None:
        """Called once at module load.  Normalises keys and populates registry."""
        for raw_ext, engine_cls in _STATIC_ENGINES.items():
            norm = _normalise(raw_ext)
            cls._registry[norm] = engine_cls
            _log.debug("EngineRegistry: %s → %s", norm, engine_cls.__name__)

    @classmethod
    def get_engine_for(cls, extension: str) -> Optional[Type[AbstractDocumentEngine]]:
        """Return engine class for the given extension, or None."""
        return cls._registry.get(_normalise(extension))

    @classmethod
    def supported_extensions(cls) -> List[str]:
        """Return a list of all registered extensions."""
        return list(cls._registry.keys())

    @classmethod
    def is_supported(cls, extension: str) -> bool:
        """Return True if an engine is registered for this extension."""
        return _normalise(extension) in cls._registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(ext: str) -> str:
    """Normalise extension to lowercase with leading dot: ``PDF`` → ``.pdf``."""
    ext = ext.strip().lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    return ext


# ---------------------------------------------------------------------------
# Backward-compat shim so existing imports of PluginKernel / PluginInitializationError
# in main.py and document_service.py keep working without changes.
# ---------------------------------------------------------------------------

class PluginInitializationError(Exception):
    """Kept for backward compatibility with main.py error handling."""


class PluginKernel:
    """
    Backward-compatible shim.

    The real work is done by EngineRegistry._bootstrap() above.
    initialize() is now a no-op but safe to call.
    """

    _initialized: bool = True  # Always true — static registry needs no init

    @classmethod
    def initialize(cls) -> None:  # noqa: D102
        """No-op.  Registry is populated at import time."""

    @classmethod
    def is_initialized(cls) -> bool:  # noqa: D102
        return True

    @classmethod
    def list_engines(cls) -> List[str]:  # noqa: D102
        return EngineRegistry.supported_extensions()


# Bootstrap at import time — runs exactly once.
EngineRegistry._bootstrap()

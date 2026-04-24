"""
atlas_viewer.core.plugin_kernel  (REBUILT — shim over static engine_registry)
===============================================================================
Backward-compatible shim.

All real engine registration now lives in ``core.engine_registry``.
This module re-exports EngineRegistry, PluginKernel, and
PluginInitializationError so that existing imports in main.py,
document_service.py, and any other files keep working without changes.

NO importlib calls remain here.
"""

from __future__ import annotations

# Re-export everything from the static registry
from core.engine_registry import (   # noqa: F401  (re-exported)
    EngineRegistry,
    PluginKernel,
    PluginInitializationError,
    _normalise as normalize_extension,
)
from pathlib import Path


def extension_from_path(path: str | Path) -> str:
    """Extract and normalise extension from a path."""
    return normalize_extension(Path(path).suffix)


def register_engine(extension: str):
    """
    Class decorator kept for backward compatibility with QtPdfEngine.

    In the new design this is a no-op metadata tag.
    The real registration happens in core.engine_registry._STATIC_ENGINES.
    """
    def decorator(cls):
        cls._extension_metadata = normalize_extension(extension)
        return cls
    return decorator

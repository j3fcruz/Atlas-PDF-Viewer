"""
atlas_viewer.core
==================
Core engine abstraction layer (Next Gen - QtPdf).
"""

# ── Exceptions ────────────────────────────────────────────────────────────────
from core.exceptions import (
    AtlasViewerError,
    AttachmentExtractionError,
    CryptoError,
    DecryptionError,
    DocumentEncryptedError,
    DocumentLoadError,
    DocumentValidationError,
    MissingDependencyError,
    PageRenderError,
    PluginError,
    PluginRegistrationError,
    ProtectionError,
    ServiceError,
    ServiceNotReadyError,
    ThumbnailError,
    UnsupportedFormatError,
)

# ── Engine interface ──────────────────────────────────────────────────────────
from core.document_engine import AbstractDocumentEngine

# ── Plugin kernel ─────────────────────────────────────────────────────────────
from core.plugin_kernel import (
    EngineRegistry,
    PluginKernel,
    PluginInitializationError,
    register_engine,
    normalize_extension,
    extension_from_path,
)

# ── ATLAS format + crypto ─────────────────────────────────────────────────────
from core.atlas_format import (
    AtlasConstants,
    atlas_read_file,
    atlas_write_file,
    safe_temp_file,
    parse_atlas_header,
)
from core.crypto_engine import CryptoEngine, build_atlas_container, check_crypto_deps

# ── Engine class (RE-EXPORT QtPdfEngine) ──────────────────────────────────────
from core.qtpdf_engine import QtPdfEngine

__all__ = [
    # exceptions
    "AtlasViewerError",
    "AttachmentExtractionError",
    "CryptoError",
    "DecryptionError",
    "DocumentEncryptedError",
    "DocumentLoadError",
    "DocumentValidationError",
    "MissingDependencyError",
    "PageRenderError",
    "PluginError",
    "PluginInitializationError",
    "PluginRegistrationError",
    "ProtectionError",
    "ServiceError",
    "ServiceNotReadyError",
    "ThumbnailError",
    "UnsupportedFormatError",
    # engine interface
    "AbstractDocumentEngine",
    "EngineRegistry",
    "QtPdfEngine",
    # plugin kernel
    "PluginKernel",
    "register_engine",
    "normalize_extension",
    "extension_from_path",
    # ATLAS / crypto
    "AtlasConstants",
    "atlas_read_file",
    "atlas_write_file",
    "safe_temp_file",
    "parse_atlas_header",
    "CryptoEngine",
    "build_atlas_container",
    "check_crypto_deps",
]

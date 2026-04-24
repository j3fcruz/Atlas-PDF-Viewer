"""
atlas_viewer.core.exceptions
==============================
Application-specific exception hierarchy.

All exceptions derive from :class:`AtlasViewerError` so callers can choose
between catching the base type for a safety net or individual sub-types for
targeted handling.

Hierarchy
---------
::

    AtlasViewerError
    ├── DocumentLoadError
    │   └── DocumentEncryptedError
    ├── DocumentValidationError
    ├── PageRenderError
    ├── AttachmentExtractionError
    ├── ThumbnailError
    ├── UnsupportedFormatError
    ├── ServiceError
    │   └── ServiceNotReadyError
    ├── PluginError
    │   └── PluginRegistrationError
    └── CryptoError  (protection / ATLAS format)
        ├── ProtectionError
        ├── DecryptionError
        └── MissingDependencyError

Extension Points
----------------
Derive new exceptions from the appropriate parent.  Keep exception messages
free of sensitive information (no passwords, keys, or full paths).
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
#  BASE
# ─────────────────────────────────────────────────────────────────────────────

class AtlasViewerError(Exception):
    """
    Base exception for all ATLAS Viewer errors.

    Catch this type for a blanket error handler::

        try:
            doc_svc.open(path)
        except AtlasViewerError as exc:
            show_error_dialog(str(exc))
    """


# ─────────────────────────────────────────────────────────────────────────────
#  DOCUMENT ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class DocumentLoadError(AtlasViewerError):
    """
    Raised when a document cannot be opened or parsed.

    Covers I/O errors, corrupted file data, and unsupported PDF features.
    Does *not* cover missing passwords (see :class:`DocumentEncryptedError`)
    or validation failures (see :class:`DocumentValidationError`).
    """


class DocumentValidationError(AtlasViewerError):
    """
    Raised when a document fails pre-load validation checks.

    Covers: file-too-large, file-too-small, wrong magic bytes, page-count
    limit exceeded, unsupported extension.
    """


class DocumentEncryptedError(DocumentLoadError):
    """
    Raised when a document requires a password that was not provided,
    or when the provided password is incorrect.
    """


# ─────────────────────────────────────────────────────────────────────────────
#  RENDERING ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class PageRenderError(AtlasViewerError):
    """Raised when a page cannot be rendered to pixels."""


# ─────────────────────────────────────────────────────────────────────────────
#  ATTACHMENT ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class AttachmentExtractionError(AtlasViewerError):
    """
    Raised when an embedded attachment cannot be extracted safely.

    Covers: size-limit exceeded, path traversal detected, write failure.
    """


# ─────────────────────────────────────────────────────────────────────────────
#  THUMBNAIL ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class ThumbnailError(AtlasViewerError):
    """Raised when thumbnail generation fails for a page."""


# ─────────────────────────────────────────────────────────────────────────────
#  FORMAT / ENGINE ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class UnsupportedFormatError(AtlasViewerError):
    """
    Raised when a document format has no registered engine.

    Include the unsupported extension and a list of supported extensions
    in the message so the user knows what is accepted.
    """


# ─────────────────────────────────────────────────────────────────────────────
#  SERVICE ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class ServiceError(AtlasViewerError):
    """
    Base class for service-layer errors.

    Raised when a service method is called in an invalid state or receives
    invalid arguments.
    """


class ServiceNotReadyError(ServiceError):
    """
    Raised when a service method is called before the service is ready.

    Example: calling :meth:`~atlas_viewer.services.BookmarkService.get_tree`
    before a document is open.
    """


# ─────────────────────────────────────────────────────────────────────────────
#  PLUGIN / EXTENSION ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class PluginError(AtlasViewerError):
    """Base class for plugin and extension-point errors."""


class PluginRegistrationError(PluginError):
    """
    Raised when a plugin or engine cannot be registered.

    Covers: duplicate extension, incompatible engine class.
    """


# ─────────────────────────────────────────────────────────────────────────────
#  CRYPTO / PROTECTION ERRORS
# ─────────────────────────────────────────────────────────────────────────────

class CryptoError(AtlasViewerError):
    """Base class for cryptographic operation errors."""


class ProtectionError(CryptoError):
    """Raised when a protection (encryption) operation fails."""


class DecryptionError(CryptoError):
    """
    Raised when decryption fails.

    Typical causes: wrong password, wrong keyfile, wrong TOTP secret,
    or corrupted ATLAS container payload.
    """


class MissingDependencyError(CryptoError):
    """
    Raised when a required optional dependency is not installed.

    The exception message includes the ``pip install`` command needed to
    resolve the issue.
    """

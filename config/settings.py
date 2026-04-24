"""
atlas_viewer.config.settings
==============================
Centralized application configuration.

All tunable constants are defined here as typed, frozen dataclasses.
Never scatter magic numbers or hard-coded limits through the codebase.

Configuration Hierarchy
-----------------------
::

    AppSettings
    ├── DocumentLimits    — file size, page count, extension whitelist
    ├── SecurityConfig    — path traversal limits, input sanitation rules
    ├── ThumbnailConfig   — thread count, cache size, render quality
    ├── AttachmentConfig  — extraction size limits, safe character set
    ├── LoggingConfig     — file path, rotation, level
    └── UIConfig          — window dimensions, zoom range, step sizes

Extension Points
----------------
Add new sub-config classes and compose them into :class:`AppSettings`.
The module-level :data:`settings` singleton is the single import target::

    from atlas_viewer.config.settings import settings
    print(settings.document.max_page_count)

Nuitka Compatibility
--------------------
Pure Python, no Qt imports, no ``__file__`` usage — safe to import in
any context including a compiled onefile binary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Tuple


# ─────────────────────────────────────────────────────────────────────────────
#  DOCUMENT LIMITS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DocumentLimits:
    """
    Hard limits for document loading and validation.

    These values are enforced by :class:`~atlas_viewer.core.mupdf_engine.MuPDFEngine`
    *before* passing data to fitz, preventing resource exhaustion from
    malformed or malicious PDF files.

    Attributes:
        max_file_size_bytes: Upper bound on source file size (default 500 MB).
        max_page_count:      Maximum pages per document (default 10,000).
        min_file_size_bytes: Minimum valid file size — anything smaller cannot
                             be a well-formed PDF (default 64 bytes).
        supported_extensions: Frozen set of lower-case extensions the viewer
                              accepts. The Engine Registry must have a matching
                              engine for each extension listed here.
    """

    max_file_size_bytes: int = 500 * 1024 * 1024   # 500 MB
    max_page_count: int = 10_000
    min_file_size_bytes: int = 64
    supported_extensions: Tuple[str, ...] = (".pdf",)


# ─────────────────────────────────────────────────────────────────────────────
#  SECURITY CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SecurityConfig:
    """
    Security-specific configuration for input validation and path handling.

    Attributes:
        max_path_length:      Maximum absolute path length accepted from user
                              input (Windows MAX_PATH is 260 chars; we allow
                              more for network paths and UNC paths).
        max_filename_length:  Maximum safe filename length after sanitization.
        allow_network_paths:  Whether UNC (``\\\\server\\share``) paths are
                              accepted as document sources.
        log_sensitive_data:   If ``False`` (default), file paths in log
                              messages are basename-only — no full paths that
                              could expose directory structure.
        pdf_magic_bytes:      Expected leading bytes of a valid PDF stream.
                              Used for magic-byte validation before opening.
        max_metadata_display: Maximum characters of PDF metadata shown in the
                              UI (prevents XSS-style injection via metadata).
    """

    max_path_length: int = 4096
    max_filename_length: int = 200
    allow_network_paths: bool = False
    log_sensitive_data: bool = False
    pdf_magic_bytes: bytes = b"%PDF"
    max_metadata_display: int = 512


# ─────────────────────────────────────────────────────────────────────────────
#  THUMBNAIL CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ThumbnailConfig:
    """
    Thumbnail generation configuration.

    Attributes:
        width:           Target thumbnail width in pixels.
        height:          Target thumbnail height in pixels.
        cache_max_size:  Maximum number of QPixmap entries in the LRU cache.
                         Each entry is roughly ``width × height × 3`` bytes
                         (≈ 80 KB for 140×190).  300 entries ≈ 24 MB.
        worker_threads:  QThreadPool thread count for thumbnail workers.
                         Each worker opens its own MuPDF engine instance.
                         Set to 1 on machines with < 4 CPU cores.
        render_dpi_scale: Zoom factor for thumbnail renders relative to the
                          target pixel size.  Lower = faster but blurrier.
        request_batch_size: How many thumbnails to pre-fetch on scroll events.
    """

    width: int = 140
    height: int = 190
    cache_max_size: int = 300
    worker_threads: int = 2
    render_dpi_scale: float = 0.8
    request_batch_size: int = 5


# ─────────────────────────────────────────────────────────────────────────────
#  ATTACHMENT CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AttachmentConfig:
    """
    Attachment extraction configuration.

    Attributes:
        max_attachment_size_bytes: Hard limit per extracted file (100 MB).
                                   Prevents DoS from PDFs with huge attachments.
        safe_filename_chars:       Characters preserved by
                                   :func:`~atlas_viewer.utils.ui_helpers.sanitize_filename`.
                                   Everything else is stripped.
        default_export_dir:        Default folder name when exporting to a
                                   directory relative to the document location.
        max_attachments:           Maximum number of attachments enumerated per
                                   document.  Prevents degenerate PDFs from
                                   hanging the UI.
    """

    max_attachment_size_bytes: int = 100 * 1024 * 1024   # 100 MB
    safe_filename_chars: str = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_. "
    )
    default_export_dir: str = "attachments"
    max_attachments: int = 500


# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LoggingConfig:
    """
    Structured logging configuration.

    Attributes:
        log_file:      Path to the rotating log file, relative to the working
                       directory (or Nuitka onefile temp dir at runtime).
        max_bytes:     Maximum single log-file size before rotation (5 MB).
        backup_count:  Number of rotated log files retained.
        log_level:     Initial log level string (``"DEBUG"``, ``"INFO"``, …).
        redact_paths:  If ``True``, replace full file paths in log records
                       with their basename only, preventing accidental
                       disclosure of directory structure or usernames.
    """

    log_file: str = "atlas_viewer.log"
    max_bytes: int = 5 * 1024 * 1024   # 5 MB
    backup_count: int = 3
    log_level: str = "INFO"
    redact_paths: bool = True


# ─────────────────────────────────────────────────────────────────────────────
#  UI CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UIConfig:
    """
    UI layout and sizing constants.

    All pixel sizes target a 96 DPI baseline.  High-DPI scaling is handled
    by Qt's ``AA_UseHighDpiPixmaps`` attribute rather than manual scaling.

    Attributes:
        sidebar_width:         Width of the icon sidebar panel.
        thumbnail_panel_width: Default width of the thumbnail splitter pane.
        toolbar_height:        Fixed height of the main toolbar.
        statusbar_height:      Fixed height of the status bar.
        min_window_width:      Minimum resizable window width.
        min_window_height:     Minimum resizable window height.
        default_zoom:          Initial zoom percent (100 = 1:1).
        zoom_min:              Minimum allowed zoom percent.
        zoom_max:              Maximum allowed zoom percent.
        zoom_step:             Zoom increment per keyboard shortcut step.
        recent_files_max:      Maximum entries in the Recent Files list.
    """

    sidebar_width: int = 58
    thumbnail_panel_width: int = 180
    toolbar_height: int = 52
    statusbar_height: int = 28
    min_window_width: int = 1100
    min_window_height: int = 720
    default_zoom: int = 100
    zoom_min: int = 25
    zoom_max: int = 400
    zoom_step: int = 25
    recent_files_max: int = 10


# ─────────────────────────────────────────────────────────────────────────────
#  ROOT SETTINGS — COMPOSED SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AppSettings:
    """
    Root application settings object.

    Composed from all sub-configuration dataclasses.  Import the module-level
    :data:`settings` singleton rather than constructing this class directly::

        from atlas_viewer.config.settings import settings

        if settings.document.max_page_count > 5000:
            ...

    Extension Point
    ---------------
    To add new configuration categories, define a new frozen dataclass,
    add it as a field here, and update the ``default_factory`` accordingly.
    No other code needs to change — all consumers import ``settings``.
    """

    document:    DocumentLimits    = field(default_factory=DocumentLimits)
    security:    SecurityConfig    = field(default_factory=SecurityConfig)
    thumbnails:  ThumbnailConfig   = field(default_factory=ThumbnailConfig)
    attachments: AttachmentConfig  = field(default_factory=AttachmentConfig)
    logging:     LoggingConfig     = field(default_factory=LoggingConfig)
    ui:          UIConfig          = field(default_factory=UIConfig)


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

#: Global application settings singleton.  Import this directly::
#:
#:     from atlas_viewer.config.settings import settings
settings: AppSettings = AppSettings()

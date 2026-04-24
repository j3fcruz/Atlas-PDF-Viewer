"""
atlas_viewer.models
====================
Pure data models — no Qt, no PDF library imports.

All models are plain Python dataclasses.  They act as typed value objects
passed between the core, service, and UI layers.

Models
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Class
     - Purpose
   * - :class:`DocumentInfo`
     - Metadata for a loaded document (path, page count, title, …)
   * - :class:`PageInfo`
     - Per-page dimensions and page label
   * - :class:`BookmarkNode`
     - Node in the hierarchical PDF outline tree
   * - :class:`AttachmentInfo`
     - Metadata for an embedded file attachment
   * - :class:`ThumbnailRequest`
     - Parameters for a thumbnail render job
   * - :class:`ThumbnailResult`
     - Result of a completed thumbnail render
   * - :class:`ValidationResult`
     - Outcome of a document validation check

Design Rules
------------
* No imports except ``from __future__`` and the Python standard library.
* No mutable class-level state.
* Equality comparison via default dataclass ``__eq__`` is intentional.
* All string fields that come from untrusted PDF metadata are already
  clamped by the engine layer before reaching these models.

Extension Point
---------------
Add new model classes here.  They will be automatically available to all
layers since models have no dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
#  DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentInfo:
    """
    Metadata describing a successfully loaded document.

    Created by :class:`~atlas_viewer.core.document_engine.AbstractDocumentEngine`
    and returned to the service layer.  All string fields are clamped to
    ``settings.security.max_metadata_display`` characters by the engine.

    Attributes:
        path:         Absolute path to the source file.
        page_count:   Total number of pages.
        file_size:    File size in bytes.
        title:        Document title from PDF metadata (may be empty).
        author:       Document author from PDF metadata (may be empty).
        subject:      Document subject / description.
        creator:      Application that created the document.
        producer:     PDF producer library / tool.
        is_encrypted: ``True`` if a password was required to open.
        pdf_version:  PDF specification version string (e.g. ``"PDF 1.7"``).
    """

    path: str
    page_count: int
    file_size: int
    title: str = ""
    author: str = ""
    subject: str = ""
    creator: str = ""
    producer: str = ""
    is_encrypted: bool = False
    pdf_version: str = ""

    @property
    def filename(self) -> str:
        """Return the filename part of :attr:`path` without directories."""
        from pathlib import Path
        return Path(self.path).name

    @property
    def file_size_mb(self) -> float:
        """Return :attr:`file_size` as megabytes (2 decimal places)."""
        return round(self.file_size / 1_048_576, 2)

    def display_title(self) -> str:
        """Return the best human-readable title: metadata title or filename."""
        return self.title.strip() or self.filename


@dataclass
class PageInfo:
    """
    Lightweight per-page metadata.

    Attributes:
        index:   0-based page index.
        width:   Page width in PDF points (1 point = 1/72 inch).
        height:  Page height in PDF points.
        label:   Page label (may be Roman numerals, letters, or numbers).
    """

    index: int
    width: float
    height: float
    label: str = ""

    @property
    def aspect_ratio(self) -> float:
        """Return ``width / height`` aspect ratio, or 1.0 if height is zero."""
        return self.width / self.height if self.height > 0 else 1.0

    @property
    def is_landscape(self) -> bool:
        """Return ``True`` if the page is wider than it is tall."""
        return self.width > self.height


# ─────────────────────────────────────────────────────────────────────────────
#  BOOKMARKS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BookmarkNode:
    """
    A node in the hierarchical PDF bookmark (outline) tree.

    Attributes:
        title:      Display title of the bookmark entry.
        page:       0-based target page index (``-1`` if unresolvable).
        level:      Nesting depth (``0`` = top level).
        children:   Child :class:`BookmarkNode` entries.
        page_index: Alias for ``page`` — accepted for backward compatibility
                    with engine callers that use the ``page_index=`` keyword.
                    When provided it takes precedence over ``page``.

    Notes:
        ``page_index`` is an optional construction alias only.  All
        downstream code (dialogs, services, search helpers) reads
        ``node.page`` — the canonical attribute.
    """

    title: str
    page: int = -1
    level: int = 0
    children: List["BookmarkNode"] = field(default_factory=list)
    # Engine-side alias: some callers pass page_index= instead of page=.
    # Stored privately; __post_init__ normalises it into self.page.
    page_index: Optional[int] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Normalise: if page_index was supplied, it wins over the page default.
        if self.page_index is not None:
            # Only override page when page is still the sentinel default (-1)
            # or when page_index was explicitly supplied alongside a real page.
            self.page = self.page_index
        # Always clear the alias so it never leaks into equality comparisons
        # or serialisation — canonical state lives in self.page only.
        object.__setattr__(self, "page_index", None)

    def is_leaf(self) -> bool:
        """Return ``True`` if this node has no children."""
        return len(self.children) == 0

    def total_descendants(self) -> int:
        """Return the total number of descendant nodes (recursive)."""
        return sum(1 + c.total_descendants() for c in self.children)

    def find(self, page: int) -> Optional["BookmarkNode"]:
        """
        Return the first node pointing to *page*, or ``None``.

        Args:
            page: 0-based target page index.

        Returns:
            BookmarkNode or ``None``.
        """
        if self.page == page:
            return self
        for child in self.children:
            found = child.find(page)
            if found:
                return found
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  ATTACHMENTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AttachmentInfo:
    """
    Metadata for a PDF embedded file (attachment).

    The ``safe_name`` field is pre-sanitized by the engine; it is the name
    that should be used for filesystem operations.

    Attributes:
        name:          Original filename from PDF metadata (may be unsafe).
        safe_name:     Sanitized filename produced by
                       :func:`~atlas_viewer.utils.sanitize_filename`.
        size:          File size in bytes (``-1`` if unknown).
        mime_type:     MIME type string (may be empty).
        description:   Optional description string from PDF metadata.
        raw_index:     Internal engine index used for extraction.
    """

    name: str
    safe_name: str
    size: int
    mime_type: str = ""
    description: str = ""
    raw_index: int = 0

    @property
    def size_display(self) -> str:
        """Return a human-readable size string, or ``"Unknown"`` if ``-1``."""
        if self.size < 0:
            return "Unknown"
        for unit in ("B", "KB", "MB", "GB"):
            if self.size < 1024:
                return f"{self.size:.0f} {unit}" if unit == "B" else f"{self.size:.1f} {unit}"
            self.size //= 1024  # type: ignore[assignment]
        return f"{self.size} GB"


# ─────────────────────────────────────────────────────────────────────────────
#  THUMBNAILS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ThumbnailRequest:
    """
    Parameters for a single thumbnail render job.

    Passed from :class:`~atlas_viewer.services.thumbnail_service.ThumbnailService`
    to :class:`~atlas_viewer.services.thumbnail_service._ThumbnailWorker`.

    Attributes:
        page_index: 0-based page index to render.
        width:      Target thumbnail width in pixels.
        height:     Target thumbnail height in pixels.
    """

    page_index: int
    width: int
    height: int


@dataclass
class ThumbnailResult:
    """
    Result of a completed thumbnail render operation.

    Attributes:
        page_index: 0-based page index that was rendered.
        image_data: Raw RGB24 bytes of the rendered thumbnail.
        width:      Actual rendered width in pixels.
        height:     Actual rendered height in pixels.
        success:    ``True`` if rendering succeeded.
        error:      Human-readable error message when ``success`` is ``False``.
    """

    page_index: int
    image_data: bytes
    width: int
    height: int
    success: bool = True
    error: str = ""


# ─────────────────────────────────────────────────────────────────────────────
#  VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Outcome of a document or path validation check.

    Attributes:
        is_valid:      ``True`` if all checks passed.
        error_code:    Machine-readable identifier for the failure (empty if valid).
                       Examples: ``"NOT_FOUND"``, ``"FILE_TOO_LARGE"``,
                       ``"INVALID_MAGIC"``, ``"UNSUPPORTED_FORMAT"``.
        error_message: Human-readable description of the failure.
    """

    is_valid: bool
    error_code: str = ""
    error_message: str = ""

    @classmethod
    def ok(cls) -> "ValidationResult":
        """Return a passing validation result."""
        return cls(is_valid=True)

    @classmethod
    def fail(cls, code: str, message: str) -> "ValidationResult":
        """
        Return a failing validation result.

        Args:
            code:    Machine-readable error identifier.
            message: Human-readable description.

        Returns:
            ValidationResult: ``is_valid=False`` with the given code and message.
        """
        return cls(is_valid=False, error_code=code, error_message=message)

    def __bool__(self) -> bool:
        """Allow ``if result:`` syntax as shorthand for ``if result.is_valid:``."""
        return self.is_valid

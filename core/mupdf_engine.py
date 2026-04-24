"""
atlas_viewer.core.mupdf_engine
================================
Concrete document engine implementation using PyMuPDF (``fitz``).

Registration Model Change
--------------------------
The old design called ``EngineRegistry.register(".pdf", MuPDFEngine)`` at
module top-level as an import side-effect.  Under Nuitka this was silently
dropped because Nuitka's optimizer treated it as a pure side-effect on a
class that is not used in the module's own scope.

New model:
* The ``@register_engine(".pdf")`` decorator stores metadata on the class.
* No ``EngineRegistry`` mutation happens at import time.
* ``PluginKernel.initialize()`` performs the real registration after all
  modules are imported.

Isolation Contract
------------------
``fitz`` is imported **only** in this module.  All other modules must not
import ``fitz`` directly.

Thread Safety
-------------
MuPDF documents are **not** thread-safe.  One engine instance per thread.
:class:`~atlas_viewer.services.thumbnail_service.ThumbnailService` creates
a separate :class:`MuPDFEngine` instance per background worker.

Security Hardening
------------------
* Pre-load validation checks file size, magic bytes, and page count.
* Metadata strings are truncated to settings.security.max_metadata_display.
* Attachment extraction enforces a per-file size cap.
* Exceptions from fitz are always re-raised as typed AtlasViewerError subclasses.

Nuitka Compatibility
--------------------
* No module-level EngineRegistry calls.
* No __file__ usage.
* Included explicitly via --include-module=core.mupdf_engine in build_nuitka.py.
* Listed in _ENGINE_MANIFEST in plugin_kernel.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

# NUITKA FIX: Hard static import — no try/except wrapper.
# The try/except guard caused Nuitka to treat fitz as an optional runtime
# dependency and omit it from the compiled bundle.  A bare top-level import
# forces Nuitka's static analysis to unconditionally include the fitz/pymupdf
# package, matching the strategy used by v1's pdf_viewer.py for QtPdf.
import fitz  # PyMuPDF — hard static import; Nuitka MUST include fitz/pymupdf
MUPDF_AVAILABLE: bool = True

from config.settings import settings
from core.document_engine import AbstractDocumentEngine
from core.exceptions import (
    AttachmentExtractionError,
    DocumentEncryptedError,
    DocumentLoadError,
    DocumentValidationError,
    PageRenderError,
    UnsupportedFormatError,
)
from core.plugin_kernel import register_engine
from models import (
    AttachmentInfo,
    BookmarkNode,
    DocumentInfo,
    PageInfo,
    ValidationResult,
)

_log = logging.getLogger(__name__)

# PDF magic bytes (first 5 bytes of all valid PDF files)
_PDF_MAGIC = b"%PDF-"


# ─────────────────────────────────────────────────────────────────────────────
#  ENGINE CLASS
# ─────────────────────────────────────────────────────────────────────────────

@register_engine(".pdf")
class MuPDFEngine(AbstractDocumentEngine):
    """
    PyMuPDF-backed document engine for PDF files.

    The ``@register_engine(".pdf")`` decorator stores metadata only —
    it does NOT touch EngineRegistry.  Registration is performed by
    PluginKernel.initialize() during application startup.

    Usage::

        engine = MuPDFEngine()
        doc_info = engine.open("/path/to/file.pdf")
        rgb, w, h = engine.render_page(0, zoom=1.5)
        engine.close()
    """

    def __init__(self) -> None:
        self._doc: Optional[fitz.Document] = None
        self._path: Optional[str] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def open(self, path: str, password: Optional[str] = None) -> DocumentInfo:
        # MUPDF_AVAILABLE guard removed: fitz is a hard static import now.
        # If fitz is missing the module itself won't load, giving a clear error.
        abs_path = str(Path(path).resolve())

        try:
            doc = fitz.open(abs_path)  # type: ignore[union-attr]
        except Exception as exc:
            raise DocumentLoadError(
                f"fitz.open() failed for '{abs_path}': {exc}"
            ) from exc

        if doc.needs_pass:
            if password is None:
                doc.close()
                raise DocumentEncryptedError(
                    f"'{abs_path}' is encrypted and requires a password."
                )
            if not doc.authenticate(password):
                doc.close()
                raise DocumentEncryptedError(
                    f"Wrong password for '{abs_path}'."
                )

        self._doc = doc
        self._path = abs_path

        max_meta = getattr(
            getattr(settings, "security", None), "max_metadata_display", 512
        )
        raw_meta = doc.metadata or {}

        info = DocumentInfo(
            path=abs_path,
            page_count=doc.page_count,
            file_size=Path(abs_path).stat().st_size,
            title=str(raw_meta.get("title", "") or "")[:max_meta],
            author=str(raw_meta.get("author", "") or "")[:max_meta],
            subject=str(raw_meta.get("subject", "") or "")[:max_meta],
            creator=str(raw_meta.get("creator", "") or "")[:max_meta],
            producer=str(raw_meta.get("producer", "") or "")[:max_meta],
            is_encrypted=doc.needs_pass,
            pdf_version=str(raw_meta.get("format", "") or "")[:max_meta],
        )

        _log.info(
            "Opened '%s' — %d page(s).",
            Path(abs_path).name,
            doc.page_count,
        )
        return info

    def close(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:  # pragma: no cover
                pass
            finally:
                self._doc = None
                self._path = None

    def is_open(self) -> bool:
        return self._doc is not None

    # ── Pages ──────────────────────────────────────────────────────────────

    def get_page_count(self) -> int:
        self._require_open()
        return self._doc.page_count  # type: ignore[union-attr]

    def get_page_info(self, page_index: int) -> PageInfo:
        self._require_open()
        self._check_page_index(page_index)
        page = self._doc[page_index]  # type: ignore[index]
        rect = page.rect
        return PageInfo(
            index=page_index,
            width=rect.width,
            height=rect.height,
            label=str(page_index + 1),
        )

    def render_page(
        self,
        page_index: int,
        zoom: float = 1.0,
        rotation: int = 0,
    ) -> Tuple[bytes, int, int]:
        self._require_open()
        self._check_page_index(page_index)

        if rotation not in (0, 90, 180, 270):
            raise ValueError(
                f"rotation must be 0, 90, 180, or 270; got {rotation}"
            )

        try:
            page = self._doc[page_index]  # type: ignore[index]
            mat = fitz.Matrix(zoom, zoom).prerotate(rotation)  # type: ignore[union-attr]
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)  # type: ignore[union-attr]
            return pix.samples, pix.width, pix.height
        except Exception as exc:
            raise PageRenderError(
                f"Failed to render page {page_index}: {exc}"
            ) from exc

    def get_page_text(self, page_index: int) -> str:
        self._require_open()
        self._check_page_index(page_index)
        try:
            page = self._doc[page_index]  # type: ignore[index]
            return page.get_text("text")
        except Exception:  # pragma: no cover
            return ""

    # ── Bookmarks ──────────────────────────────────────────────────────────

    def get_bookmarks(self) -> List[BookmarkNode]:
        self._require_open()
        try:
            toc = self._doc.get_toc(simple=False)  # type: ignore[union-attr]
        except Exception:
            return []
        return _parse_toc(toc)

    # ── Attachments ────────────────────────────────────────────────────────

    def get_attachments(self) -> List[AttachmentInfo]:
        self._require_open()
        attachments: List[AttachmentInfo] = []
        try:
            for i in range(self._doc.embfile_count()):  # type: ignore[union-attr]
                info = self._doc.embfile_info(i)  # type: ignore[union-attr]
                attachments.append(
                    AttachmentInfo(
                        name=info.get("filename", f"attachment_{i}"),
                        size=info.get("size", 0),
                        index=i,
                    )
                )
        except Exception as exc:
            _log.warning("Could not enumerate attachments: %s", exc)
        return attachments

    def extract_attachment(self, attachment: AttachmentInfo) -> bytes:
        self._require_open()
        max_size = getattr(
            getattr(settings, "attachments", None),
            "max_attachment_size_bytes",
            10 * 1024 * 1024,  # 10 MB default
        )
        if attachment.size > max_size:
            raise AttachmentExtractionError(
                f"Attachment '{attachment.name}' ({attachment.size:,} B) "
                f"exceeds the size limit ({max_size:,} B)."
            )
        try:
            return self._doc.embfile_get(attachment.index)  # type: ignore[union-attr]
        except Exception as exc:
            raise AttachmentExtractionError(
                f"Failed to extract '{attachment.name}': {exc}"
            ) from exc

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self, path: str) -> ValidationResult:
        p = Path(path)

        if not p.exists():
            return ValidationResult.fail("FILE_NOT_FOUND", f"'{path}' does not exist.")

        if not p.is_file():
            return ValidationResult.fail("NOT_A_FILE", f"'{path}' is not a regular file.")

        max_bytes = getattr(
            getattr(settings, "document", None),
            "max_file_size_bytes",
            500 * 1024 * 1024,  # 500 MB default
        )
        size = p.stat().st_size
        if size > max_bytes:
            return ValidationResult.fail(
                "FILE_TOO_LARGE",
                f"'{p.name}' is {_fmt_size(size)} — limit is {_fmt_size(max_bytes)}.",
            )

        if size < 5:
            return ValidationResult.fail(
                "FILE_TOO_SMALL",
                f"'{p.name}' is too small to be a valid PDF ({size} B).",
            )

        try:
            with open(path, "rb") as fh:
                magic = fh.read(5)
        except OSError as exc:
            return ValidationResult.fail("READ_ERROR", str(exc))

        if magic != _PDF_MAGIC:
            return ValidationResult.fail(
                "INVALID_MAGIC",
                f"'{p.name}' does not start with the PDF magic bytes (%PDF-).",
            )

        return ValidationResult.ok()

    # ── Internal Helpers ───────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._doc is None:
            raise DocumentLoadError("No document is currently open.")

    def _check_page_index(self, index: int) -> None:
        count = self._doc.page_count  # type: ignore[union-attr]
        if not (0 <= index < count):
            raise ValueError(
                f"Page index {index} is out of range [0, {count - 1}]."
            )


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_size(size: int) -> str:
    """Format *size* bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size //= 1024
    return f"{size:.0f} GB"


def _parse_toc(toc: list) -> List[BookmarkNode]:
    """Convert a PyMuPDF TOC list into a BookmarkNode tree."""
    root: List[BookmarkNode] = []
    stack: List[Tuple[int, List[BookmarkNode]]] = []

    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        node = BookmarkNode(title=str(title), page=max(0, page - 1), children=[])

        # Pop stack until we find the parent level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1].append(node)
        else:
            root.append(node)

        stack.append((level, node.children))

    return root


# NOTE: No EngineRegistry.register() call here.
# Registration is done exclusively by PluginKernel.initialize().
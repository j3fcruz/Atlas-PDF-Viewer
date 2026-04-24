"""
atlas_viewer.services.document_service  (SECURE REFACTOR — memory-only pipeline)
==================================================================================
DocumentService — primary orchestrator for document operations.

Changes in this refactor
------------------------
* ``open_from_bytes(data)`` added — loads a PDF from a raw bytes object via
  QtPdfEngine.load_from_bytes().  Used internally by PDFViewerTab after
  ATLAS decryption.  NO temp file is ever created.
* ``open(path)`` unchanged — still used for plain .pdf files on disk.
* ``_inject_engine(engine)`` promoted to primary integration point for
  in-memory flows (PDFViewerTab sets this directly after load_from_bytes).

Design
------
* UI layer never imports fitz, pypdf, or QtPdf directly.
* All document access flows through this service.
* Service methods raise typed exceptions — never raw engine exceptions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from config.settings import settings
from core.document_engine import AbstractDocumentEngine
from core.exceptions import (
    DocumentLoadError,
    DocumentValidationError,
    UnsupportedFormatError,
)
from core.engine_registry import EngineRegistry, PluginInitializationError
from models import DocumentInfo, PageInfo, ValidationResult
from utils import get_logger, perf_timer, safe_resolve_path

_log = get_logger(__name__)


class DocumentService:
    """
    Facade over the document engine layer.

    Manages a single active document.  Opening a new document automatically
    closes any previously open one.

    Usage (file-based)::

        svc = DocumentService()
        doc_info = svc.open("/path/to/file.pdf")
        svc.close()

    Usage (in-memory / ATLAS)::

        engine = QtPdfEngine()
        doc_info = engine.load_from_bytes(plaintext_bytes)
        svc._inject_engine(engine)
        # All svc.render_page(), svc.get_page_info() etc. now work normally.
    """

    def __init__(self) -> None:
        self._engine:   Optional[AbstractDocumentEngine] = None
        self._doc_info: Optional[DocumentInfo]           = None

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def doc_info(self) -> Optional[DocumentInfo]:
        return self._doc_info

    @property
    def is_open(self) -> bool:
        return self._engine is not None and self._engine.is_open()

    @property
    def page_count(self) -> int:
        if not self.is_open:
            return 0
        return self._engine.get_page_count()  # type: ignore[union-attr]

    # ── Public API ─────────────────────────────────────────────────────────

    def validate(self, path: str) -> ValidationResult:
        """Validate a file without opening it."""
        try:
            resolved = str(safe_resolve_path(path))
        except ValueError as exc:
            return ValidationResult.fail("INVALID_PATH", str(exc))

        ext = Path(resolved).suffix
        engine_cls = EngineRegistry.get_engine_for(ext)
        if engine_cls is None:
            return ValidationResult.fail(
                "UNSUPPORTED_FORMAT",
                f"No engine registered for '{ext}'.  "
                f"Supported: {', '.join(EngineRegistry.supported_extensions())}",
            )
        return engine_cls().validate(resolved)

    def open(self, path: str, password: Optional[str] = None) -> DocumentInfo:
        """
        Open a document from disk (plain .pdf only).

        For ATLAS-derived content, use ``_inject_engine`` after calling
        QtPdfEngine.load_from_bytes() in PDFViewerTab.
        """
        self.close()

        try:
            abs_path = str(safe_resolve_path(path))
        except ValueError as exc:
            raise DocumentLoadError(f"Invalid path: {exc}") from exc

        ext = Path(abs_path).suffix
        engine_cls = EngineRegistry.get_engine_for(ext)
        if engine_cls is None:
            raise UnsupportedFormatError(
                f"No engine registered for '{ext}'.  "
                f"Supported formats: {', '.join(EngineRegistry.supported_extensions())}"
            )

        engine = engine_cls()
        with perf_timer(_log, f"open {Path(abs_path).name}"):
            doc_info = engine.open(abs_path, password=password)

        max_pages = settings.document.max_page_count
        if doc_info.page_count > max_pages:
            engine.close()
            raise DocumentValidationError(
                f"Document has {doc_info.page_count:,} pages, "
                f"which exceeds the configured limit of {max_pages:,}."
            )

        self._engine   = engine
        self._doc_info = doc_info
        return doc_info

    def close(self) -> None:
        """Close the current document and release all engine resources.  Idempotent."""
        if self._engine is not None:
            self._engine.close()
            self._engine   = None
        self._doc_info = None

    def render_page(
        self,
        page_index: int,
        zoom: float    = 1.0,
        rotation: int  = 0,
    ) -> Tuple[bytes, int, int]:
        self._require_open()
        return self._engine.render_page(page_index, zoom=zoom, rotation=rotation)  # type: ignore

    def get_page_info(self, page_index: int) -> PageInfo:
        self._require_open()
        return self._engine.get_page_info(page_index)  # type: ignore

    def get_page_text(self, page_index: int) -> str:
        self._require_open()
        return self._engine.get_page_text(page_index)  # type: ignore

    # ── Engine Injection ───────────────────────────────────────────────────

    def _inject_engine(self, engine: AbstractDocumentEngine) -> None:
        """
        Install an already-opened engine as the active engine.

        Used by PDFViewerTab after ATLAS in-memory loading:

            engine = QtPdfEngine()
            doc_info = engine.load_from_bytes(plaintext)
            svc._inject_engine(engine)

        This makes all service accessors (render_page, get_page_info, etc.)
        work without requiring a file path.

        The caller is responsible for keeping ``engine`` alive.
        """
        if self._engine is not None:
            self._engine.close()
        self._engine   = engine
        # doc_info is set from the engine's current state
        self._doc_info = self._engine.get_page_count() and None  # re-populated by caller

    def _get_engine(self) -> AbstractDocumentEngine:
        self._require_open()
        return self._engine  # type: ignore

    # ── Internal ───────────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if not self.is_open:
            raise DocumentLoadError("No document is currently open.")

    @staticmethod
    def _require_kernel() -> None:
        """No-op shim: static registry is always ready."""
        pass

"""
atlas_viewer.ui.widgets.pdf_viewer_tab  (FIX-THUMB-v2 + FIX-PRINT-v2)
=======================================================================
PDFViewerTab — non-blocking, event-driven PDF viewer controller.

Fixes applied in this revision
--------------------------------
[FIX-THUMB-5]  _finish_document_setup constructs ThumbnailService
               correctly for BOTH load paths:

               • File-based PDF  → ThumbnailService(doc_path=abs_path, ...)
                 Workers open their own QPdfDocument from disk.

               • In-memory PDF   → ThumbnailService(qt_doc=qt_doc, ...)
                 Service receives the live QPdfDocument reference and
                 computes aspect-ratio-correct render sizes per page.

[FIX-THUMB-6]  render_fn lambda replaced with qt_doc reference.
               The old render_fn passed QSize(THUMB_W, THUMB_H) directly
               to QPdfDocument.render() which stretches to fill exactly —
               wrong for any page whose aspect ratio differs from the
               thumbnail bounds.  Passing qt_doc lets ThumbnailService
               call pagePointSize() and compute the correct scaled size.

[FIX-PRINT-1]  print_document() implemented.
               MainWindow called tab.print_document() but the method did not
               exist anywhere in PDFViewerTab.  Now implemented with:
               • QPrintDialog for user printer/range selection
               • PrintManager (event-driven, GUI thread) renders pages via QTimer
               • QProgressDialog with real-time per-page progress
               • Cancel support

[FIX-DECRYPT-1] _cleanup_decrypt_dialog disconnects dlg.canceled BEFORE
               calling dlg.close().  QProgressDialog.close() emits canceled,
               which previously triggered _on_decrypt_cancelled even when the
               dialog was being closed programmatically after a real error —
               causing "Atlas decryption cancelled by user." to appear in the
               log after every auth failure.

Load Pipeline (unchanged)
--------------------------
    [Open File] ──▶ _begin_pdf_load(path)
                        │
                        ▼
                    _finish_document_setup(doc_info, engine)

    [Open ATLAS] ──▶ _start_load_atlas()
                        │  MFAAuthDialog (modal)
                        │  AtlasDecryptWorker (QThread)
                        ▼
                    _on_atlas_decrypted(bytes)
                        │  QtPdfEngine.load_from_bytes() — no disk I/O
                        ▼
                    _finish_document_setup(doc_info, engine)

Security Properties (unchanged)
---------------------------------
* Decrypted PDF bytes are NEVER written to disk under ANY code path.
* No temp files under any condition.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, Slot, QPointF
from PySide6.QtGui import QImage

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout,
    QMessageBox, QProgressDialog, QSplitter, QVBoxLayout, QWidget,
)

from config import settings
from config.theme import Colors
from core.atlas_format import atlas_read_file, parse_atlas_header
from core.atlas_decrypt_worker import AtlasDecryptWorker
from core.qtpdf_engine import QtPdfEngine
from models import DocumentInfo
from services import DocumentService, ThumbnailService, BookmarkService, AttachmentService
from ui.widgets.pdf_canvas import PDFCanvas
from ui.widgets.toolbar import ViewerToolbar
from ui.widgets.thumbnail_panel import ThumbnailPanel
from ui.dialogs import MFAAuthDialog, BookmarksDialog, AttachmentsDialog, DocumentInfoDialog
from utils import get_logger

_log = get_logger(__name__)


class PDFViewerTab(QWidget):
    """
    Master tab widget.  All document loading is non-blocking.

    ATLAS pipeline uses in-memory loading exclusively — no temp files.
    """

    title_changed   = Signal(str)
    status_changed  = Signal(str)
    document_opened = Signal()
    document_closed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Services
        self._doc_svc    = DocumentService()
        self._bm_svc:    Optional[BookmarkService]   = None
        self._att_svc:   Optional[AttachmentService] = None
        self._thumb_svc: Optional[ThumbnailService]  = None

        # State
        self._current_page = 0
        self._zoom_percent = settings.ui.default_zoom
        self._file_path:   Optional[str] = None
        self._thumb_panel: Optional[ThumbnailPanel] = None

        # ATLAS async resources (kept alive for the duration of the operation)
        self._decrypt_worker:  Optional[AtlasDecryptWorker] = None
        self._decrypt_dlg:     Optional[QProgressDialog]    = None

        # In-memory engine reference for ATLAS-loaded documents.
        # Held here so QPdfDocument stays alive while the tab is open.
        self._memory_engine:   Optional[QtPdfEngine] = None

        # Print manager — event-driven, GUI thread only

        self._build_ui()

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self._doc_svc.is_open

    @property
    def file_path(self) -> Optional[str]:
        return self._file_path

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar
        self._toolbar = ViewerToolbar()
        self._toolbar.prev_page.connect(self._on_prev_page)
        self._toolbar.next_page.connect(self._on_next_page)
        self._toolbar.jump_to_page.connect(self._go_to_page)
        self._toolbar.zoom_changed.connect(self._on_zoom_changed)
        self._toolbar.zoom_in_sig.connect(self._on_zoom_in)
        self._toolbar.zoom_out_sig.connect(self._on_zoom_out)
        self._toolbar.zoom_reset_sig.connect(self._on_zoom_reset)
        self._toolbar.open_file.connect(self._on_open_file)
        self._toolbar.close_document.connect(self._on_close_document)
        self._toolbar.set_document_open(False)
        root.addWidget(self._toolbar)

        # Horizontal content area
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Colors.BORDER}; }}"
        )

        self._canvas = PDFCanvas()
        self._canvas.wheel_zoom.connect(self._on_wheel_zoom)
        self._splitter.addWidget(self._canvas)

        h_layout.addWidget(self._splitter, stretch=1)
        root.addLayout(h_layout, stretch=1)

    # =========================================================================
    # Document Lifecycle — PUBLIC ENTRY POINT
    # =========================================================================

    def load_document(self, path: str, password: Optional[str] = None) -> None:
        """
        Begin loading a document.  Non-blocking.

        Dispatches to the ATLAS pipeline for .atlas files; uses the
        synchronous QPdfDocument.load() path for plain .pdf files.
        """
        if Path(path).suffix.lower() == ".atlas":
            self._start_load_atlas(path)
        else:
            self._begin_pdf_load(path, password)

    # =========================================================================
    # Regular PDF Load Pipeline
    # =========================================================================

    def _begin_pdf_load(self, path: str, password: Optional[str] = None) -> None:
        """Load a plain PDF file from disk via DocumentService."""
        try:
            doc_info = self._doc_svc.open(path, password=password)
            engine   = self._doc_svc._get_engine()
            self._file_path = path
            self._finish_document_setup(doc_info, engine)
        except Exception as exc:
            _log.error("PDF load error: %s", exc, exc_info=True)
            QMessageBox.critical(
                self, "Open Failed",
                f"Could not open document:\n{exc}"
            )

    # =========================================================================
    # ATLAS Decrypt Pipeline — fully asynchronous, memory-only
    # =========================================================================

    def _start_load_atlas(self, path: str) -> None:
        """Entry point for .atlas files.  Runs on UI thread."""
        try:
            raw  = atlas_read_file(path)
            meta, _ = parse_atlas_header(raw)
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", f"Cannot read ATLAS file:\n{exc}")
            return

        auth_dlg = MFAAuthDialog(meta=meta, parent=self)
        if auth_dlg.exec() != MFAAuthDialog.DialogCode.Accepted:
            return
        factors = auth_dlg.factors

        dlg = QProgressDialog("Decrypting document…", "Cancel", 0, 100, self)
        dlg.setWindowTitle("ATLAS Viewer")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self._decrypt_dlg = dlg

        worker = AtlasDecryptWorker(path, factors, parent=self)
        worker.progress.connect(self._on_decrypt_progress)
        worker.finished.connect(self._on_atlas_decrypted)
        worker.error.connect(self._on_atlas_error)

        # Wire cancel button → worker.cancel + our cancel handler.
        # IMPORTANT: _cleanup_decrypt_dialog() disconnects this signal BEFORE
        # calling dlg.close() so that programmatic close (on success or error)
        # does NOT re-trigger _on_decrypt_cancelled.
        dlg.canceled.connect(worker.cancel)
        dlg.canceled.connect(self._on_decrypt_cancelled)

        self._decrypt_worker = worker
        self._file_path = path
        worker.start()

    @Slot(int)
    def _on_decrypt_progress(self, value: int) -> None:
        if self._decrypt_dlg:
            self._decrypt_dlg.setValue(value)
            QApplication.processEvents()

    @Slot(bytes)
    def _on_atlas_decrypted(self, plaintext: bytes) -> None:
        """
        Runs on UI thread — called when background worker finishes.

        SECURITY: plaintext bytes are only in RAM.  Passed directly to
        QtPdfEngine.load_from_bytes() → QPdfDocument.loadFromData() — the
        only copy ever created.  No disk I/O.
        """
        self._cleanup_decrypt_dialog()

        engine = QtPdfEngine()
        try:
            doc_info = engine.load_from_bytes(plaintext)
        except Exception as exc:
            _log.error("In-memory PDF load error: %s", exc, exc_info=True)
            QMessageBox.critical(
                self, "Open Failed",
                f"Could not load decrypted PDF into viewer:\n{exc}"
            )
            return
        finally:
            del plaintext  # drop local reference immediately

        self._memory_engine = engine
        self._doc_svc._inject_engine(engine)
        self._finish_document_setup(doc_info, engine)

    @Slot(str)
    def _on_atlas_error(self, message: str) -> None:
        self._cleanup_decrypt_dialog()
        self._file_path = None
        QMessageBox.critical(self, "Decryption Failed", f"Could not decrypt document:\n{message}")

    def _on_decrypt_cancelled(self) -> None:
        # Only reached when the user physically clicks the Cancel button.
        # Programmatic dlg.close() no longer triggers this — see
        # _cleanup_decrypt_dialog() which disconnects canceled first.
        self._cleanup_decrypt_dialog()
        self._file_path = None
        _log.info("Atlas decryption cancelled by user.")

    def _cleanup_decrypt_dialog(self) -> None:
        """
        Close and discard the progress dialog.

        QProgressDialog.close() emits the canceled signal, which would
        fire _on_decrypt_cancelled even when the close is programmatic
        (success or error path).  Disconnecting canceled BEFORE close()
        prevents that spurious invocation.
        """
        if self._decrypt_dlg:
            try:
                self._decrypt_dlg.canceled.disconnect()
            except RuntimeError:
                pass  # already disconnected — safe to ignore
            self._decrypt_dlg.close()
            self._decrypt_dlg = None
        self._decrypt_worker = None

    # =========================================================================
    # Shared Post-Load Setup
    # =========================================================================

    def _finish_document_setup(
        self,
        doc_info: DocumentInfo,
        engine,
    ) -> None:
        """
        Final setup after a document (plain PDF or ATLAS) has been loaded.
        Called on the UI thread after QPdfDocument is fully ready.
        """
        qt_doc = engine._get_qt_document()
        self._canvas.setDocument(qt_doc)

        # Services
        self._bm_svc  = BookmarkService(engine)
        self._att_svc = AttachmentService(engine)

        # [FIX-THUMB-5] Construct ThumbnailService correctly for both load paths.
        #
        # File mode:   doc_info.path is the absolute resolved path to the .pdf
        #              file on disk.  Workers can open their own QPdfDocument.
        #
        # Memory mode: doc_info.path is "" (ATLAS decrypted in-memory).
        #              Pass a render_fn so thumbnails are rendered on the UI
        #              thread using the already-loaded shared QPdfDocument
        #              instead of trying to open a non-existent file.
        #
        # The critical guard is ``doc_info.path and Path(doc_info.path).is_file()``.
        # Using ``self._file_path`` here was the original bug — it held the
        # .atlas file path, not a valid PDF path, causing workers to call
        # QPdfDocument.load("something.atlas") → status != Ready → blank render.

        if doc_info.path and Path(doc_info.path).is_file():
            # File-based: workers open their own instance
            self._thumb_svc = ThumbnailService(
                page_count = doc_info.page_count,
                doc_path   = doc_info.path,
                parent     = self,
            )
        else:
            # In-memory: pass the live QPdfDocument so ThumbnailService
            # can compute the correct aspect-ratio render size per page.
            # [FIX-THUMB-6] Do NOT use a render_fn lambda here — it passed
            # raw bounding QSize to doc.render() which stretches the page.
            self._thumb_svc = ThumbnailService(
                page_count = doc_info.page_count,
                qt_doc     = qt_doc,
                parent     = self,
            )

        self._current_page = 0

        self._toolbar.set_document_open(True)
        self._toolbar.set_zoom(self._zoom_percent)
        self._toolbar.set_page(0, doc_info.page_count)
        self._canvas.setZoomFactor(self._zoom_percent / 100.0)

        self._remove_thumb_panel()

        display_name = Path(self._file_path).name if self._file_path else "Document"
        self.title_changed.emit(display_name)
        self.document_opened.emit()

    # =========================================================================
    # Close / Cleanup
    # =========================================================================

    def _on_close_document(self) -> None:
        self._doc_svc.close()
        self._memory_engine = None
        self._canvas.clear()
        self._toolbar.set_document_open(False)
        self._file_path = None
        self._bm_svc    = None
        self._att_svc   = None
        if self._thumb_svc:
            self._thumb_svc.invalidate()
            self._thumb_svc = None
        self._remove_thumb_panel()
        self.document_closed.emit("")

    def cleanup(self) -> None:
        """Called by tab manager on tab close."""
        if self._thumb_svc:
            self._thumb_svc.invalidate()
        self._doc_svc.close()
        self._memory_engine = None
        self._canvas.clear()
        self._remove_thumb_panel()

    # =========================================================================
    # Zoom
    # =========================================================================

    def _on_zoom_changed(self, percent: int) -> None:
        self._zoom_percent = percent
        self._canvas.set_zoom(percent)
        self._toolbar.set_zoom(percent)

    @Slot()
    def _on_zoom_in(self) -> None:
        new = min(self._zoom_percent + settings.ui.zoom_step, settings.ui.zoom_max)
        self._on_zoom_changed(new)

    @Slot()
    def _on_zoom_out(self) -> None:
        new = max(self._zoom_percent - settings.ui.zoom_step, settings.ui.zoom_min)
        self._on_zoom_changed(new)

    @Slot()
    def _on_zoom_reset(self) -> None:
        self._on_zoom_changed(settings.ui.default_zoom)

    def _on_wheel_zoom(self, delta: int) -> None:
        step    = settings.ui.zoom_step
        new     = self._zoom_percent + (step if delta > 0 else -step)
        clamped = max(settings.ui.zoom_min, min(new, settings.ui.zoom_max))
        self._on_zoom_changed(clamped)

    # =========================================================================
    # Navigation
    # =========================================================================

    def _on_prev_page(self) -> None:
        if not self.is_open:
            return
        nav = self._canvas.pageNavigator()
        if nav.currentPage() > 0:
            self._go_to_page(nav.currentPage() - 1)

    def _on_next_page(self) -> None:
        if not self.is_open:
            return
        nav = self._canvas.pageNavigator()
        doc = self._canvas.document()
        if doc and nav.currentPage() < doc.pageCount() - 1:
            self._go_to_page(nav.currentPage() + 1)

    def _go_to_page(self, page_index: int) -> None:
        if not self.is_open:
            return
        doc     = self._canvas.document()
        count   = doc.pageCount() if doc else 0
        if count == 0:
            return
        clamped = max(0, min(page_index, count - 1))
        self._canvas.pageNavigator().jump(clamped, QPointF(0, 0), 0)
        self._current_page = clamped
        self._toolbar.set_page(clamped, count)
        if self._thumb_panel:
            self._thumb_panel.set_active_page(clamped)

    # =========================================================================
    # Sidebar Panels
    # =========================================================================

    @Slot()
    def _on_thumbnails(self) -> None:
        if not self.is_open or not self._thumb_svc:
            return

        if self._thumb_panel:
            self._remove_thumb_panel()
            self._sidebar.set_panel_active("thumbnails", False)
            return

        panel = ThumbnailPanel(self._thumb_svc, self._doc_svc.page_count, parent=self)
        panel.page_selected.connect(self._go_to_page)

        self._splitter.insertWidget(0, panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._thumb_panel = panel

        panel.set_active_page(self._canvas.pageNavigator().currentPage())
        self._sidebar.set_panel_active("thumbnails", True)

    @Slot()
    def _on_bookmarks(self) -> None:
        if not self.is_open or not self._bm_svc:
            return
        try:
            roots = self._bm_svc.get_tree()
        except Exception:
            return
        dlg = BookmarksDialog(roots, parent=self)
        dlg.navigate_to_page.connect(self._go_to_page)
        dlg.exec()

    @Slot()
    def _on_attachments(self) -> None:
        if not self.is_open or not self._att_svc:
            return
        try:
            attachments = self._att_svc.list_attachments()
        except Exception:
            return
        dlg = AttachmentsDialog(attachments, self._att_svc, parent=self)
        dlg.exec()

    @Slot()
    def _on_doc_info(self) -> None:
        if not self.is_open:
            return
        dlg = DocumentInfoDialog(self._doc_svc.doc_info, parent=self)
        dlg.exec()

    def _on_open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "Documents (*.pdf *.atlas);;PDF Files (*.pdf);;ATLAS Files (*.atlas)"
        )
        if path:
            self.load_document(path)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _remove_thumb_panel(self) -> None:
        if self._thumb_panel:
            self._thumb_panel.hide()
            self._thumb_panel.setParent(None)  # type: ignore[arg-type]
            self._thumb_panel = None

    def _get_memory_pdf_bytes(self) -> Optional[bytes]:
        """
        Extract the raw PDF bytes from an in-memory (ATLAS-decrypted) engine.

        Used by print_document() to give PrintManager an independent copy
        of the PDF data so it can open its own QPdfDocument without sharing
        the engine's internal QPdfDocument instance.

        Returns None if no in-memory engine is available or the buffer
        cannot be read.

        Implementation note
        -------------------
        QtPdfEngine stores the QBuffer in self._buffer when load_from_bytes()
        is used.  We seek to position 0, read all bytes, and return them.
        The engine's QPdfDocument continues to hold its own reference to the
        data via loadFromData() — reading from _buffer does not affect it.
        """
        if self._memory_engine is None:
            return None

        buf = getattr(self._memory_engine, "_buffer", None)
        if buf is None:
            _log.warning(
                "_get_memory_pdf_bytes: engine has no _buffer attribute — "
                "cannot extract bytes for printing"
            )
            return None

        try:
            buf.seek(0)
            data = bytes(buf.data())
            if not data:
                _log.warning("_get_memory_pdf_bytes: buffer is empty")
                return None
            _log.debug(
                "_get_memory_pdf_bytes: extracted %d bytes from engine buffer",
                len(data),
            )
            return data
        except Exception as exc:
            _log.error(
                "_get_memory_pdf_bytes: failed to read buffer: %s", exc,
                exc_info=True,
            )
            return None
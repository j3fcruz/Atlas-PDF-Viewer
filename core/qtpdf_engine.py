"""
atlas_viewer.core.qtpdf_engine  (FIX-ENGINE-v4 — Qt-version-safe status check)
================================================================================
Native QtPdf-based document engine.

Bugs fixed in this revision
-----------------------------
[FIX-ENGINE-1]  QBuffer lifecycle (carried from v3).
    close() now clears self._buffer so the QByteArray is released and
    QPdfDocument can be safely reused on a subsequent open().

[FIX-ENGINE-2]  load_from_bytes uses loadFromData(QByteArray) (from v3).
    No external QIODevice lifetime dependency.

[FIX-ENGINE-4]  Qt-version-safe status check — THE REGRESSION FIX.
    Symptom:  "Error.None_ for '...pdf'" on every file open.
    Root cause:
      QPdfDocument.load(path) return type changed across Qt versions:
        Qt ≤ 6.4:  returns QPdfDocument.Status   (Status.Ready on success)
        Qt ≥ 6.5:  returns QPdfDocument.Error    (Error.None  on success)
      Some PySide6 6.6 / 6.7 builds additionally return None (void).

      _check_status(status, ...) was passed the RETURN VALUE of load().
      In Qt 6.5+ that return value is QPdfDocument.Error.None_.
      Comparing Error.None_ against Status.Ready → not equal → raises.
      Every PDF load was aborted even though the document loaded fine.

    Fix:
      Ignore the return value of doc.load() / doc.loadFromData() entirely.
      Always check doc.STATUS() after the call.  doc.status() returns
      QPdfDocument.Status regardless of Qt version — it is the only
      reliable post-load state query.

      New helper: _check_doc_status(doc, label) reads doc.status() itself.
      Old _check_status(retval, label) is removed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtPdf import QPdfDocument
from PySide6.QtGui import QImage

from core.document_engine import AbstractDocumentEngine
from core.exceptions import DocumentLoadError
from models import DocumentInfo, PageInfo, BookmarkNode, ValidationResult, AttachmentInfo



_log = logging.getLogger(__name__)

# Sentinel for file_size when document was loaded from memory (no path exists)
_IN_MEMORY_SIZE: int = -1


class QtPdfEngine(AbstractDocumentEngine):
    """
    QPdfDocument-backed engine.

    Public loading API
    ------------------
    ``open(path)``          — file-based load (plain PDF on disk)
    ``load_from_bytes(b)``  — in-memory load (decrypted ATLAS content)

    Both methods populate self._doc and make is_open() return True.
    """

    def __init__(self) -> None:
        self._doc: QPdfDocument = QPdfDocument(None)
        self._path: Optional[str] = None
        self._loaded_from_memory: bool = False
        self._buffer: Optional[QByteArray] = None  # keeps QByteArray alive

    # =========================================================================
    # Primary Loading API
    # =========================================================================

    def open(self, path: str, password: Optional[str] = None) -> DocumentInfo:
        """
        Load a PDF from disk.

        Only used for unencrypted .pdf files that exist on disk.
        ATLAS-derived plaintext PDFs MUST use load_from_bytes() instead.
        """
        self.close()

        abs_path = str(Path(path).resolve())

        if password:
            self._doc.setPassword(password)

        # [FIX-ENGINE-4] Ignore the return value of load() — it changes type
        # across Qt versions (Status in Qt≤6.4, Error in Qt≥6.5, void in some
        # PySide6 builds).  Always read doc.status() afterwards.
        self._doc.load(abs_path)
        _check_doc_status(self._doc, abs_path)

        self._path = abs_path
        self._loaded_from_memory = False

        _log.info(
            "QtPdfEngine: loaded from file — %s (%d pages)",
            abs_path,
            self._doc.pageCount(),
        )
        return self._build_doc_info(path=abs_path)


    def load_from_bytes(self, data: bytes) -> DocumentInfo:
        self.close()

        qt_data = QByteArray(data)

        # Keep reference (important for BOTH paths)
        self._buffer = qt_data

        # ── Path A: loadFromData (if available) ──
        if hasattr(self._doc, "loadFromData"):
            self._doc.loadFromData(qt_data)
            _log.info(
                "QtPdfEngine: load mode = %s",
                "loadFromData" if hasattr(self._doc, "loadFromData") else "QBuffer"
            )

        else:
            # ── Path B: QBuffer fallback ──
            buf = QBuffer()
            buf.setData(qt_data)
            buf.open(QIODevice.ReadOnly)

            # KEEP BOTH references alive
            self._buffer = qt_data
            self._qbuffer = buf

            self._doc.load(buf)

        _check_doc_status(self._doc, "<in-memory>")

        self._path = None
        self._loaded_from_memory = True

        return self._build_doc_info(path="")

    # =========================================================================
    # AbstractDocumentEngine Implementation
    # =========================================================================

    def close(self) -> None:
        """
        Close the document and release all resources.

        [FIX-ENGINE-1] Clears self._buffer so the QByteArray is released
        and the QPdfDocument can be safely reused for a new document.
        """
        self._doc.close()
        self._path = None
        self._loaded_from_memory = False
        self._buffer = None           # [FIX-ENGINE-1] release data reference

    def is_open(self) -> bool:
        return self._doc.status() == QPdfDocument.Status.Ready

    def get_page_count(self) -> int:
        return self._doc.pageCount()

    def get_page_info(self, page_index: int) -> PageInfo:
        size = self._doc.pagePointSize(page_index)
        return PageInfo(
            index=page_index,
            width=size.width(),
            height=size.height(),
            label=str(page_index + 1),
        )

    def render_page(
        self,
        page_index: int,
        zoom: float = 1.0,
        rotation: int = 0,
    ) -> Tuple[bytes, int, int]:
        point_size = self._doc.pagePointSize(page_index)
        pixel_size = (point_size * zoom).toSize()

        img = self._doc.render(page_index, pixel_size)
        img = img.convertToFormat(QImage.Format.Format_RGB888)

        ptr = img.bits()
        return ptr.tobytes(), img.width(), img.height()

    def get_page_text(self, page_index: int) -> str:
        try:
            full_text_model = self._doc.getAllText(page_index)
            return full_text_model.text()
        except AttributeError:
            return ""

    def get_bookmarks(self) -> List[BookmarkNode]:
        return []

    def get_attachments(self) -> List[AttachmentInfo]:
        return []

    def extract_attachment(self, attachment: AttachmentInfo) -> bytes:
        return b""

    def validate(self, path: str) -> ValidationResult:
        p = Path(path)
        if not p.exists():
            return ValidationResult.fail("NOT_FOUND", "File not found")
        if not p.suffix.lower() == ".pdf":
            return ValidationResult.fail("WRONG_EXTENSION", "Not a PDF file")
        return ValidationResult.ok()

    def _get_qt_document(self) -> QPdfDocument:
        """Return the underlying QPdfDocument for direct QPdfView attachment."""
        return self._doc

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _build_doc_info(self, path: str) -> DocumentInfo:
        """Construct DocumentInfo from the currently-loaded QPdfDocument."""
        if path and Path(path).exists():
            file_size = Path(path).stat().st_size
        else:
            file_size = _IN_MEMORY_SIZE

        return DocumentInfo(
            path=path,
            page_count=self._doc.pageCount(),
            file_size=file_size,
            title=self._doc.metaData(QPdfDocument.MetaDataField.Title),
            author=self._doc.metaData(QPdfDocument.MetaDataField.Author),
            subject=self._doc.metaData(QPdfDocument.MetaDataField.Subject),
            creator=self._doc.metaData(QPdfDocument.MetaDataField.Creator),
            producer=self._doc.metaData(QPdfDocument.MetaDataField.Producer),
            is_encrypted=False,
            pdf_version="1.7",
        )


def _check_doc_status(doc: QPdfDocument, label: str) -> None:
    """
    Read doc.status() and raise DocumentLoadError if the document is not ready.

    [FIX-ENGINE-4] This function reads doc.status() DIRECTLY instead of using
    the return value of load() / loadFromData().

    Why: QPdfDocument.load() return type is NOT stable across Qt versions:
      Qt ≤ 6.4  →  returns QPdfDocument.Status
      Qt ≥ 6.5  →  returns QPdfDocument.Error
      PySide6 6.6/6.7 on some platforms  →  returns None (void binding)

    QPdfDocument.status() ALWAYS returns QPdfDocument.Status regardless of
    Qt version.  It is the only reliable post-load state query.

    Error enum values that map to failure (for diagnostic logging):
      Error.None_          = 0  →  no error  (success when Status is Ready)
      Error.Unknown        = 1  →  unspecified failure
      Error.DataNotYetAvailable = 2  →  async load not finished
      Error.FileNotFound   = 3  →  file missing
      Error.InvalidFileFormat = 4  →  not a valid PDF
      Error.UnsupportedSecurityScheme = 5  →  encrypted, no password
      Error.IncorrectPassword = 6  →  wrong password
    """
    status = doc.status()

    if status == QPdfDocument.Status.Ready:
        # Success — document loaded and renderable
        return

    # Document is not ready — attempt to log a helpful error code
    # by calling doc.error() if the method exists on this Qt build
    error_detail = ""
    try:
        err = doc.error()
        error_detail = f", error={err}"
    except AttributeError:
        pass  # doc.error() not available on all Qt builds

    if status == QPdfDocument.Status.Error:
        raise DocumentLoadError(
            f"QPdfDocument failed to load {label!r}{error_detail}"
        )

    # Null / Loading / other unexpected states
    raise DocumentLoadError(
        f"QPdfDocument in unexpected state after load: "
        f"status={status}{error_detail} for {label!r}"
    )

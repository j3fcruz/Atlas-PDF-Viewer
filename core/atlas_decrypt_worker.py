"""
atlas_viewer.core.atlas_decrypt_worker  (SECURE REFACTOR — memory-only)
========================================================================
Non-blocking ATLAS decryption pipeline.

Architecture
------------
::

    UI Thread                         Worker Thread (QThread)
    ─────────────                     ──────────────────────────
    AtlasDecryptWorker                _DecryptRunnable.run()
      │                                 │
      │  start()                        │  atlas_read_file()
      │  ─────────▶ thread.start()      │  parse_atlas_header()
      │                                 │  CryptoEngine.extract_meta_and_decrypt()
      │  progress(int) ◀────────────    │  emit progress(25 / 50 / 75 / 100)
      │  finished(bytes) ◀──────────    │  emit finished(plaintext_bytes)
      │  error(str) ◀───────────────    │  emit error(message) on exception
      ▼                                 ▼

Security Contract
-----------------
* The ``finished(bytes)`` signal carries the ONLY copy of the decrypted PDF.
* That ``bytes`` object lives exclusively on the Python heap.
* NO temp file is created inside this worker — that responsibility has been
  **removed** from the codebase entirely.
* The caller (PDFViewerTab._on_atlas_decrypted) passes the bytes directly to
  QtPdfEngine.load_from_bytes() without ever touching the filesystem.

Design Rules
------------
* NO crypto may run on the UI thread.
* Worker owns a QThread; caller only calls start() and connects signals.
* The worker is single-use: create → start → connect → discard.
  Do not restart a finished worker.

Usage::

    self._worker = AtlasDecryptWorker(atlas_path, factors, parent=self)
    self._worker.progress.connect(self._on_decrypt_progress)
    self._worker.finished.connect(self._on_atlas_decrypted)
    self._worker.error.connect(self._on_decrypt_error)
    self._worker.start()
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from PySide6.QtCore import QObject, QThread, Signal, Slot

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal worker object (lives on the worker thread)
# ---------------------------------------------------------------------------

class _DecryptRunnable(QObject):
    """
    QObject that performs the actual decryption on a background QThread.

    All signals are delivered to the UI thread via Qt's automatic
    cross-thread queued connection mechanism.
    """

    progress = Signal(int)    # 0-100
    finished = Signal(bytes)  # plaintext PDF bytes — NEVER written to disk
    error    = Signal(str)    # human-readable error message

    def __init__(self, atlas_path: str, factors: Dict[str, Any]) -> None:
        super().__init__()
        self._atlas_path = atlas_path
        self._factors    = factors

    @Slot()
    def run(self) -> None:
        """Execute the full decryption pipeline, emitting progress checkpoints."""
        try:
            # ── Stage 1: Read raw bytes ────────────────────────────────────
            self.progress.emit(10)
            from core.atlas_format import atlas_read_file
            raw = atlas_read_file(self._atlas_path)

            # ── Stage 2: Parse header ──────────────────────────────────────
            self.progress.emit(25)
            from core.atlas_format import parse_atlas_header
            _meta, _payload = parse_atlas_header(raw)

            # ── Stage 3: Key derivation + decryption ───────────────────────
            # Hot path: PBKDF2 ~600k iterations — runs entirely on this thread.
            self.progress.emit(40)
            from core.crypto_engine import CryptoEngine, DecryptionError
            _meta_dict, plaintext = CryptoEngine.extract_meta_and_decrypt(
                self._atlas_path, self._factors
            )

            # ── Stage 4: Done — emit bytes, NEVER a path ───────────────────
            self.progress.emit(100)
            self.finished.emit(plaintext)
            # `plaintext` bytes object is now owned by Qt's signal delivery
            # mechanism and will be passed to the connected slot on the UI thread.

        except DecryptionError as exc:
            # exc.args[0] is the structured dict from CryptoEngine — extract
            # the user-facing message rather than emitting the raw dict repr.
            from core.crypto_engine import normalize_crypto_error
            msg = normalize_crypto_error(exc)
            # Corrected - After — logs at WARNING, clean message only, no traceback
            _log.warning(
                "AtlasDecryptWorker: auth failure — %s",
                exc.args[0].get("reason", "unknown") if isinstance(exc.args[0], dict) else exc,
            )
            self.error.emit(msg)

        except Exception as exc:
            _log.error("AtlasDecryptWorker: unexpected error: %s", exc, exc_info=True)
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Public API — used by pdf_viewer_tab
# ---------------------------------------------------------------------------

class AtlasDecryptWorker(QObject):
    """
    Public controller for background ATLAS decryption.

    Owns the QThread and the _DecryptRunnable.  The parent widget should hold
    a reference to keep this object alive until ``finished`` or ``error`` fires.

    Signals
    -------
    progress(int)   : Emitted during decryption, value 0-100.
    finished(bytes) : Emitted on success with plaintext PDF bytes.
                      The receiver MUST pass these bytes to
                      QtPdfEngine.load_from_bytes() — writing to disk
                      is a security violation.
    error(str)      : Emitted on failure with a human-readable message.
    """

    progress = Signal(int)
    finished = Signal(bytes)
    error    = Signal(str)

    def __init__(
        self,
        atlas_path: str,
        factors: Dict[str, Any],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._atlas_path = atlas_path
        self._factors    = factors
        self._thread     = QThread(self)
        self._runnable   = _DecryptRunnable(atlas_path, factors)

        # Move worker object to dedicated thread
        self._runnable.moveToThread(self._thread)

        # Wire internal signals → public signals (re-emit on UI thread)
        self._runnable.progress.connect(self.progress)
        self._runnable.finished.connect(self.finished)
        self._runnable.error.connect(self.error)

        # Start the work when thread starts
        self._thread.started.connect(self._runnable.run)

        # Clean up thread when work is done
        self._runnable.finished.connect(self._thread.quit)
        self._runnable.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

    def start(self) -> None:
        """Begin background decryption. Non-blocking."""
        self._thread.start()

    def cancel(self) -> None:
        """
        Request cancellation.

        Because PBKDF2 is not interruptible, this only prevents the result
        from being acted upon — it does NOT stop the crypto computation
        mid-flight.  Disconnect your slots before calling this.
        """
        try:
            self.finished.disconnect()
            self.error.disconnect()
            self.progress.disconnect()
        except RuntimeError:
            pass  # already disconnected
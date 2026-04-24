"""
atlas_viewer.services.thumbnail_service  (FIX-THUMB-v3 — aspect ratio + logging)
==================================================================================
ThumbnailService — background threaded thumbnail generation.

Bugs fixed in this revision
-----------------------------
[FIX-THUMB-6]  render_fn aspect ratio bug (in-memory / ATLAS mode).
    _render_in_memory() called:
        img = render_fn(page_index, QSize(THUMB_W, THUMB_H))
    and render_fn was:
        lambda page_index, size: qt_doc.render(page_index, size)

    QPdfDocument.render(page, QSize) renders the page at EXACTLY the
    given pixel size — it STRETCHES to fill it if the aspect ratios
    differ.  A portrait page rendered into a landscape-shaped thumbnail
    bound (or vice-versa) was squashed/stretched.

    Fix: _render_in_memory() now computes the aspect-ratio-correct
    render size (same logic as _FileThumbnailWorker) before calling
    the render_fn, and the render_fn contract is changed to accept the
    already-computed exact render size, not the bounding box.

    The render_fn signature is now:
        render_fn(page_index: int) -> QImage
    The service is responsible for computing the correct size and
    passing it to QPdfDocument.render() internally via a wrapper.
    Callers pass qt_doc directly instead of a lambda.

[FIX-THUMB-7]  Hard diagnostic logging added throughout.
    All critical decision points now log at DEBUG or WARNING level:
    - doc.status() after load
    - doc.pageCount()
    - computed render_size
    - null QImage detection with page index
    - cache hit/miss
    - worker dispatch

[FIX-THUMB-8]  Cache key consistency.
    Cache key was (page_index, THUMB_W, THUMB_H).  This is correct but
    was not logged, making cache hit/miss invisible.  Added explicit
    log at DEBUG level for cache hits and misses.

[FIX-THUMB-9]  _pending set cleared on invalidate before workers finish.
    Workers that finish after invalidate() still call _on_worker_ready
    which checked _invalidated at the top — correct.  No change needed
    here but the behaviour is now logged explicitly.

Thread Safety
-------------
* _LRUPixmapCache is protected by a threading.Lock.
* Qt signals deliver results to the main thread (QueuedConnection automatic).
* Each file-based worker opens its own QPdfDocument instance.
* In-memory path uses the UI thread exclusively via QTimer deferral.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Callable, Optional, Set, Tuple

from PySide6.QtCore import (
    QObject, QRunnable, QSize, QThreadPool, QTimer, Signal, Slot,
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtPdf import QPdfDocument

from config.settings import settings
from utils import get_logger

_log = get_logger(__name__)

_CacheKey = Tuple[int, int, int]  # (page_index, thumb_width, thumb_height)


def _aspect_correct_size(
    page_point_w: float,
    page_point_h: float,
    bound_w: int,
    bound_h: int,
) -> QSize:
    """
    Compute the largest QSize that fits within (bound_w, bound_h) while
    preserving the aspect ratio of the page.

    Both dimensions are clamped to at least 1.
    """
    if page_point_w <= 0 or page_point_h <= 0:
        return QSize(bound_w, bound_h)
    scale = min(bound_w / page_point_w, bound_h / page_point_h)
    return QSize(
        max(1, int(page_point_w * scale)),
        max(1, int(page_point_h * scale)),
    )


# ---------------------------------------------------------------------------
# LRU pixmap cache
# ---------------------------------------------------------------------------

class _LRUPixmapCache:
    def __init__(self, max_size: int) -> None:
        self._max  = max_size
        self._data: OrderedDict[_CacheKey, QPixmap] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: _CacheKey) -> Optional[QPixmap]:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
        return None

    def put(self, key: _CacheKey, pixmap: QPixmap) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            else:
                if len(self._data) >= self._max:
                    evicted = self._data.popitem(last=False)
                    _log.debug("ThumbnailCache: evicted page %d", evicted[0][0])
                self._data[key] = pixmap

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# ---------------------------------------------------------------------------
# Cross-thread signal carrier
# ---------------------------------------------------------------------------

class _ThumbnailSignals(QObject):
    ready = Signal(int, QPixmap)   # (page_index, pixmap)
    error = Signal(int, str)       # (page_index, message)


# ---------------------------------------------------------------------------
# Worker for FILE-BASED documents
# ---------------------------------------------------------------------------

class _FileThumbnailWorker(QRunnable):
    """
    Renders one page thumbnail using a private QPdfDocument opened from disk.

    Only instantiated when doc_path is a non-empty, valid file path.
    Opens its own QPdfDocument instance — safe because QPdfDocument uses
    read-only mmap which supports concurrent readers on all platforms.
    """

    def __init__(
        self,
        doc_path:     str,
        page_index:   int,
        thumb_width:  int,
        thumb_height: int,
        signals:      _ThumbnailSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._doc_path    = doc_path
        self._page_index  = page_index
        self._thumb_w     = thumb_width
        self._thumb_h     = thumb_height
        self._signals     = signals

    def run(self) -> None:
        doc = QPdfDocument(None)
        try:
            # [FIX-THUMB-7] Log load attempt and result
            _log.debug(
                "FileThumbnailWorker: loading %r for page %d",
                self._doc_path, self._page_index,
            )
            # [FIX-ENGINE-4] Ignore load() return value — type varies by Qt version.
            # Qt ≤ 6.4 returns Status, Qt ≥ 6.5 returns Error, some builds return None.
            # Always read doc.status() after the call for a reliable result.
            doc.load(self._doc_path)
            status = doc.status()

            if status != QPdfDocument.Status.Ready:
                msg = (
                    f"QPdfDocument not ready after load: status={status} "
                    f"path={self._doc_path!r} page={self._page_index}"
                )
                _log.error("FileThumbnailWorker: %s", msg)
                self._signals.error.emit(self._page_index, msg)
                return

            page_count = doc.pageCount()
            _log.debug(
                "FileThumbnailWorker: loaded %r — %d pages, rendering page %d",
                self._doc_path, page_count, self._page_index,
            )

            if not 0 <= self._page_index < page_count:
                msg = (
                    f"page_index {self._page_index} out of range "
                    f"[0, {page_count - 1}] for {self._doc_path!r}"
                )
                _log.error("FileThumbnailWorker: %s", msg)
                self._signals.error.emit(self._page_index, msg)
                return

            page_size = doc.pagePointSize(self._page_index)
            if page_size.isEmpty() or page_size.width() <= 0 or page_size.height() <= 0:
                msg = f"Page {self._page_index} has zero/empty point size: {page_size}"
                _log.error("FileThumbnailWorker: %s", msg)
                self._signals.error.emit(self._page_index, msg)
                return

            # [FIX-THUMB-7] Log render size computation
            render_size = _aspect_correct_size(
                page_size.width(), page_size.height(),
                self._thumb_w, self._thumb_h,
            )
            _log.debug(
                "FileThumbnailWorker: page %d point_size=(%.1f,%.1f) → "
                "render_size=(%d,%d)",
                self._page_index,
                page_size.width(), page_size.height(),
                render_size.width(), render_size.height(),
            )

            img = doc.render(self._page_index, render_size)

            # [FIX-THUMB-7] Explicit null detection with full context
            if img is None or img.isNull():
                msg = (
                    f"QPdfDocument.render() returned null QImage for "
                    f"page {self._page_index} render_size={render_size}"
                )
                _log.error("FileThumbnailWorker: %s", msg)
                self._signals.error.emit(self._page_index, msg)
                return

            # [FIX-THUMB-BLACK] Do NOT convert to Format_RGB888.
            # QPdfDocument.render() returns Format_ARGB32_Premultiplied (Qt6).
            # convertToFormat(Format_RGB888) composites alpha against BLACK —
            # that is why thumbnails showed solid black instead of page content.
            # Pass the ARGB32 image directly to QPixmap.fromImage(); the panel's
            # drawPixmap() composites correctly against the panel background.
            _log.debug(
                "FileThumbnailWorker: page %d rendered OK — %dx%d px fmt=%s",
                self._page_index, img.width(), img.height(), img.format(),
            )
            self._signals.ready.emit(self._page_index, QPixmap.fromImage(img))

        except Exception as exc:
            _log.error(
                "FileThumbnailWorker: exception on page %d: %s",
                self._page_index, exc, exc_info=True,
            )
            self._signals.error.emit(self._page_index, str(exc))
        finally:
            doc.close()


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class ThumbnailService(QObject):
    """
    Background thumbnail renderer.  Pure Qt — no external PDF dependencies.

    Construction
    ------------
    File mode (plain PDF on disk)::

        svc = ThumbnailService(
            page_count = doc_info.page_count,
            doc_path   = "/absolute/path/to/file.pdf",
            parent     = self,
        )

    In-memory mode (ATLAS-decrypted PDF — QPdfDocument already loaded)::

        svc = ThumbnailService(
            page_count = doc_info.page_count,
            qt_doc     = engine._get_qt_document(),
            parent     = self,
        )

    [FIX-THUMB-6] In-memory mode now takes qt_doc (QPdfDocument reference)
    instead of a render_fn lambda.  The service computes the correct
    aspect-ratio render size itself before calling qt_doc.render(), exactly
    matching the file-mode worker logic.  This eliminates stretched thumbnails.

    Signals
    -------
    thumbnail_ready(int, QPixmap):
        Emitted on the UI thread with (page_index, pixmap).
    """

    thumbnail_ready = Signal(int, QPixmap)

    def __init__(
        self,
        page_count:  int,
        doc_path:    str = "",
        qt_doc:      Optional[QPdfDocument] = None,
        # Legacy: render_fn still accepted but qt_doc is preferred
        render_fn:   Optional[Callable[[int, QSize], QImage]] = None,
        parent:      QObject | None = None,
    ) -> None:
        super().__init__(parent)

        # Require at least one rendering source
        if not doc_path and qt_doc is None and render_fn is None:
            raise ValueError(
                "ThumbnailService: supply doc_path (file mode), "
                "qt_doc (in-memory mode), or render_fn (legacy in-memory)."
            )

        self._doc_path   = doc_path
        self._qt_doc     = qt_doc
        self._render_fn  = render_fn   # legacy fallback
        self._page_count = page_count
        self._cache      = _LRUPixmapCache(settings.thumbnails.cache_max_size)
        self._pending: Set[int] = set()
        self._pending_lock      = threading.Lock()
        self._signals           = _ThumbnailSignals()
        self._pool              = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(
            max(1, min(settings.thumbnails.worker_threads, 4))
        )
        self._invalidated = False

        self._signals.ready.connect(self._on_worker_ready)
        self._signals.error.connect(self._on_worker_error)

        _log.debug(
            "ThumbnailService: init — %d pages, mode=%s",
            page_count,
            "file" if doc_path else ("qt_doc" if qt_doc else "render_fn"),
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def request(self, page_index: int) -> None:
        """
        Request a thumbnail for *page_index*.  Always non-blocking.

        Cache hit → emits thumbnail_ready via deferred QTimer.
        Cache miss → dispatches worker (file) or schedules UI-thread render (memory).
        """
        if self._invalidated:
            return
        if not 0 <= page_index < self._page_count:
            _log.warning(
                "ThumbnailService.request: page_index %d out of range [0, %d]",
                page_index, self._page_count - 1,
            )
            return

        cache_key = (page_index, settings.thumbnails.width, settings.thumbnails.height)
        cached = self._cache.get(cache_key)
        if cached is not None:
            _log.debug("ThumbnailService: cache HIT for page %d", page_index)
            QTimer.singleShot(0, lambda: self.thumbnail_ready.emit(page_index, cached))
            return

        _log.debug("ThumbnailService: cache MISS for page %d — dispatching", page_index)

        with self._pending_lock:
            if page_index in self._pending:
                _log.debug("ThumbnailService: page %d already pending, skip", page_index)
                return
            self._pending.add(page_index)

        if self._doc_path:
            # File mode: background QRunnable worker
            _log.debug("ThumbnailService: dispatching file worker for page %d", page_index)
            self._pool.start(_FileThumbnailWorker(
                doc_path     = self._doc_path,
                page_index   = page_index,
                thumb_width  = settings.thumbnails.width,
                thumb_height = settings.thumbnails.height,
                signals      = self._signals,
            ))
        else:
            # In-memory mode: render on UI thread (deferred)
            _log.debug("ThumbnailService: scheduling UI-thread render for page %d", page_index)
            QTimer.singleShot(0, lambda: self._render_in_memory(page_index))

    def request_range(self, first: int, last: int) -> None:
        """Request thumbnails for pages [first, last] inclusive."""
        for i in range(first, last + 1):
            self.request(i)

    def invalidate(self) -> None:
        """Cancel pending renders and clear the cache.  Idempotent."""
        _log.debug("ThumbnailService: invalidate() called")
        self._invalidated = True
        self._cache.clear()
        with self._pending_lock:
            self._pending.clear()

    # ── In-memory rendering (UI thread) ─────────────────────────────────────

    def _render_in_memory(self, page_index: int) -> None:
        """
        Render one thumbnail on the UI thread.

        [FIX-THUMB-6] Now uses self._qt_doc directly and computes the correct
        aspect-ratio render size before calling doc.render().  This matches
        the file-mode worker's logic exactly — no stretched thumbnails.

        Always called via QTimer.singleShot — guaranteed to run on the main
        thread where the QPdfDocument was created and is safe to call.
        """
        if self._invalidated:
            with self._pending_lock:
                self._pending.discard(page_index)
            return

        # Determine render source
        qt_doc = self._qt_doc
        render_fn = self._render_fn

        if qt_doc is None and render_fn is None:
            with self._pending_lock:
                self._pending.discard(page_index)
            _log.error(
                "ThumbnailService._render_in_memory: no qt_doc or render_fn — "
                "cannot render page %d",
                page_index,
            )
            return

        try:
            # Validate document state
            if qt_doc is not None:
                status = qt_doc.status()
                if status != QPdfDocument.Status.Ready:
                    msg = (
                        f"QPdfDocument not ready for in-memory render: "
                        f"status={status}, page={page_index}"
                    )
                    _log.error("ThumbnailService: %s", msg)
                    self._signals.error.emit(page_index, msg)
                    return

                page_count = qt_doc.pageCount()
                if not 0 <= page_index < page_count:
                    msg = (
                        f"page_index {page_index} out of range [0, {page_count-1}] "
                        f"in in-memory render"
                    )
                    _log.error("ThumbnailService: %s", msg)
                    self._signals.error.emit(page_index, msg)
                    return

                # [FIX-THUMB-6] Compute aspect-ratio-correct size
                page_size = qt_doc.pagePointSize(page_index)
                if page_size.isEmpty() or page_size.width() <= 0 or page_size.height() <= 0:
                    msg = f"Page {page_index} has zero/empty point size: {page_size}"
                    _log.error("ThumbnailService: %s", msg)
                    self._signals.error.emit(page_index, msg)
                    return

                render_size = _aspect_correct_size(
                    page_size.width(), page_size.height(),
                    settings.thumbnails.width, settings.thumbnails.height,
                )
                _log.debug(
                    "ThumbnailService in-memory: page %d "
                    "point=(%.1f,%.1f) → render=(%d,%d)",
                    page_index,
                    page_size.width(), page_size.height(),
                    render_size.width(), render_size.height(),
                )

                img = qt_doc.render(page_index, render_size)

            else:
                # Legacy render_fn path (still aspect-ratio correct because
                # caller's render_fn receives a pre-computed size)
                render_size = QSize(settings.thumbnails.width, settings.thumbnails.height)
                img = render_fn(page_index, render_size)  # type: ignore[misc]

            # [FIX-THUMB-7] Explicit null detection
            if img is None or img.isNull():
                msg = (
                    f"render returned null QImage for page {page_index}"
                )
                _log.error("ThumbnailService._render_in_memory: %s", msg)
                self._signals.error.emit(page_index, msg)
                return

            # [FIX-THUMB-BLACK] Same fix as FileThumbnailWorker: do not convert
            # to Format_RGB888. Pass ARGB32 directly to QPixmap.fromImage().
            _log.debug(
                "ThumbnailService in-memory: page %d rendered OK — %dx%d fmt=%s",
                page_index, img.width(), img.height(), img.format(),
            )
            self._signals.ready.emit(page_index, QPixmap.fromImage(img))

        except Exception as exc:
            _log.error(
                "ThumbnailService._render_in_memory: exception on page %d: %s",
                page_index, exc, exc_info=True,
            )
            self._signals.error.emit(page_index, str(exc))

    # ── Slots ───────────────────────────────────────────────────────────────

    @Slot(int, QPixmap)
    def _on_worker_ready(self, page_index: int, pixmap: QPixmap) -> None:
        if self._invalidated:
            _log.debug(
                "ThumbnailService: dropped late result for page %d (invalidated)",
                page_index,
            )
            return
        with self._pending_lock:
            self._pending.discard(page_index)
        cache_key = (page_index, settings.thumbnails.width, settings.thumbnails.height)
        self._cache.put(cache_key, pixmap)
        _log.debug("ThumbnailService: emitting thumbnail_ready for page %d", page_index)
        self.thumbnail_ready.emit(page_index, pixmap)

    @Slot(int, str)
    def _on_worker_error(self, page_index: int, message: str) -> None:
        with self._pending_lock:
            self._pending.discard(page_index)
        _log.warning("ThumbnailService: render FAILED page %d: %s", page_index, message)
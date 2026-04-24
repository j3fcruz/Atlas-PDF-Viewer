"""
atlas_viewer.ui.tab_manager
=============================
TabManager — manages the QTabWidget and tab lifecycle.

Responsibilities
----------------
* Create / remove PDFViewerTab instances.
* Wire tab-level signals (title_changed, status_changed) up to MainWindow.
* Expose a clean public API:  open_in_new_tab(), close_tab(), active_tab().
* Ensure proper widget cleanup on tab close (no leaks).

Nuitka notes
------------
All imports are top-level and static.
No dynamic import() calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QTabWidget, QWidget

from config.theme import Colors
from ui.widgets.pdf_viewer_tab import PDFViewerTab
from utils import get_logger

_log = get_logger(__name__)

_NEW_TAB_LABEL = "New Tab"


class TabManager(QTabWidget):
    """
    Subclasses QTabWidget to manage PDFViewerTab instances.

    Signals:
        status_changed(str):   Bubble-up from the active tab's status signal.
        title_changed(str):    Active tab document title (for window title bar).
        active_tab_changed():  The visible tab changed.
    """

    status_changed     = Signal(str)
    title_changed      = Signal(str)
    active_tab_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)
        self._apply_style()

        # Create one blank tab on startup
        self._open_blank_tab()

        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.currentChanged.connect(self._on_current_tab_changed)

    # ── Style ──────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {Colors.SURFACE};
            }}
            QTabBar::tab {{
                background: {Colors.TOOLBAR_BG};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 5px 14px 5px 14px;
                min-width: 100px;
                max-width: 200px;
            }}
            QTabBar::tab:selected {{
                background: {Colors.WHITE};
                color: {Colors.TEXT_PRIMARY};
                border-bottom: 2px solid {Colors.PRIMARY};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {Colors.PRIMARY_LIGHT};
            }}
        """)

    # ── Public API ─────────────────────────────────────────────────────────

    def active_tab(self) -> Optional[PDFViewerTab]:
        """Return the currently visible PDFViewerTab, or None."""
        w = self.currentWidget()
        if isinstance(w, PDFViewerTab):
            return w
        return None

    def open_in_new_tab(self, file_path: Optional[str] = None) -> PDFViewerTab:
        """
        Create a new tab, optionally loading a file.
        Returns the new PDFViewerTab.
        """
        tab = self._open_blank_tab()
        if file_path:
            tab.load_document(file_path)
        return tab

    def close_active_tab(self) -> None:
        """Close the currently visible tab."""
        idx = self.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    def close_all_tabs(self) -> None:
        """Close all tabs without keeping a blank one (use on app exit)."""
        # Temporarily disconnect so we don't reopen blank tabs during shutdown
        self.tabCloseRequested.disconnect(self._on_tab_close_requested)
        while self.count():
            widget = self.widget(0)
            if isinstance(widget, PDFViewerTab):
                if hasattr(widget, "cleanup"):
                    try:
                        widget.cleanup()
                    except Exception as exc:  # pragma: no cover
                        _log.error(
                            "close_all_tabs: cleanup() raised unexpectedly "
                            "on %r — forcing tab removal anyway: %s",
                            widget,
                            exc,
                        )
                else:  # pragma: no cover — should never happen post-fix
                    _log.warning(
                        "close_all_tabs: widget %r has no cleanup() method; "
                        "skipping graceful teardown.",
                        widget,
                    )
            self.removeTab(0)
            if widget is not None:
                widget.deleteLater()

    def open_file_in_active_tab_or_new(self, file_path: str) -> None:
        """
        Open a file.  If the active tab has no document, load into it;
        otherwise open a new tab.  This is the standard UX: the first
        file fills the initial blank tab; subsequent files add new tabs.
        """
        active = self.active_tab()
        if active is not None and not active.is_open:
            active.load_document(file_path)
        else:
            self.open_in_new_tab(file_path)

    # ── Internal ───────────────────────────────────────────────────────────

    def _open_blank_tab(self) -> PDFViewerTab:
        tab = PDFViewerTab(parent=self)
        tab.title_changed.connect(self._on_tab_title_changed)
        tab.status_changed.connect(self._on_tab_status_changed)

        idx = self.addTab(tab, _NEW_TAB_LABEL)
        self.setCurrentIndex(idx)
        _log.debug(f"Blank tab opened (index={idx})")
        return tab

    def _close_tab(self, index: int) -> None:
        widget = self.widget(index)
        if isinstance(widget, PDFViewerTab):
            if hasattr(widget, "cleanup"):
                try:
                    widget.cleanup()
                except Exception as exc:  # pragma: no cover
                    _log.error(
                        "_close_tab: cleanup() raised on %r: %s", widget, exc
                    )
            else:  # pragma: no cover
                _log.warning(
                    "_close_tab: widget %r has no cleanup(); skipping.", widget
                )

        self.removeTab(index)
        if widget is not None:
            widget.deleteLater()

        # Always maintain at least one tab
        if self.count() == 0:
            self._open_blank_tab()

        _log.debug(f"Tab closed (index={index}, remaining={self.count()})")

    # ── Slots ──────────────────────────────────────────────────────────────

    @Slot(int)
    def _on_tab_close_requested(self, index: int) -> None:
        self._close_tab(index)

    @Slot(int)
    def _on_current_tab_changed(self, index: int) -> None:
        tab = self.active_tab()
        if tab is not None and tab.file_path:
            self.title_changed.emit(Path(tab.file_path).name)
        else:
            self.title_changed.emit(_NEW_TAB_LABEL)
        self.active_tab_changed.emit()

    @Slot(str)
    def _on_tab_title_changed(self, title: str) -> None:
        sender_tab = self.sender()
        for i in range(self.count()):
            if self.widget(i) is sender_tab:
                display = title if len(title) <= 28 else f"\u2026{title[-26:]}"
                self.setTabText(i, display)
                self.setTabToolTip(i, title)
                break
        # Propagate only from active tab
        if self.sender() is self.active_tab():
            self.title_changed.emit(title)

    @Slot(str)
    def _on_tab_status_changed(self, message: str) -> None:
        if self.sender() is self.active_tab():
            self.status_changed.emit(message)

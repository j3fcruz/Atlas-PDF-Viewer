"""
atlas_opener.ui.main_window
=============================
MainWindow — opener-only shell.

Removed vs full build:
  * Print / Print Queue
  * Protect PDF
  * Export Page Text
  * Generate Keyfile
  * Documentation dialog
  * Left sidebar (SidebarPanel) — no panel toggle actions in View menu
  * ProtectionService dependency
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot, QUrl
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from config import WINDOW_TITLE, settings
from config.theme import Fonts, FontSize, Styles
from core.exceptions import AtlasViewerError, DecryptionError
from core.atlas_format import atlas_read_file, parse_atlas_header  # noqa: F401
from ui.dialogs import AboutDialog, DocumentationDialog
from ui.tab_manager import TabManager
from ui.widgets.pdf_viewer_tab import PDFViewerTab
from utils import center_window, get_logger

_log = get_logger(__name__)


# ── Application icon (inline SVG, Nuitka-safe) ────────────────────────────
_APP_ICON_SVG = b"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <path d="M32 2 L58 12 L58 34 C58 48 46 58 32 62 C18 58 6 48 6 34 L6 12 Z"
        fill="#1A5490" stroke="#0D2B47" stroke-width="1.5"/>
  <rect x="18" y="14" width="22" height="28" rx="2" ry="2"
        fill="white" opacity="0.95"/>
  <path d="M36 14 L40 18 L36 18 Z" fill="#D0E8F5"/>
  <line x1="36" y1="14" x2="36" y2="18" stroke="#BDD5EA" stroke-width="0.5"/>
  <line x1="36" y1="18" x2="40" y2="18" stroke="#BDD5EA" stroke-width="0.5"/>
  <line x1="22" y1="22" x2="35" y2="22" stroke="#1A5490" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="22" y1="26" x2="37" y2="26" stroke="#9CA3AF" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="22" y1="30" x2="36" y2="30" stroke="#9CA3AF" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="22" y1="34" x2="33" y2="34" stroke="#9CA3AF" stroke-width="1.2" stroke-linecap="round"/>
  <circle cx="42" cy="44" r="7" fill="none" stroke="white" stroke-width="2.5"/>
  <line x1="47" y1="49" x2="53" y2="55" stroke="white" stroke-width="3" stroke-linecap="round"/>
  <circle cx="40" cy="42" r="2" fill="white" opacity="0.3"/>
</svg>
"""


def _make_app_icon() -> QIcon:
    try:
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui import QPainter

        renderer = QSvgRenderer(QByteArray(_APP_ICON_SVG))
        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            pix = QPixmap(size, size)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pix)
        return icon
    except Exception:
        from PySide6.QtWidgets import QStyle
        style = QApplication.style()
        return style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)  # type: ignore[union-attr]

def show_premium_gate(parent, feature_name: str = "This feature"):
    msg = QMessageBox(parent)
    msg.setWindowTitle("Premium Feature Locked")
    msg.setText(f"{feature_name} is available in the Premium version.")
    msg.setInformativeText("Upgrade to unlock advanced features.")

    upgrade_btn = msg.addButton("Upgrade", QMessageBox.ButtonRole.AcceptRole)
    close_btn = msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)

    msg.exec()

    from config import GUMROAD_URL
    if msg.clickedButton() == upgrade_btn:
        QDesktopServices.openUrl(QUrl(GUMROAD_URL))

class MainWindow(QMainWindow):
    """
    Opener-only top-level window.

    Capabilities:
      - Open PDF / ATLAS files (single tab or new tab)
      - View: zoom, navigation, bookmarks, thumbnails, attachments, doc info
      - Copy page text

    Removed: print, protect, export, generate keyfile, left sidebar.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(
            settings.ui.min_window_width + 200,
            settings.ui.min_window_height + 100,
        )
        self.setMinimumSize(settings.ui.min_window_width, settings.ui.min_window_height)
        self.setFont(Fonts.default())
        self.setStyleSheet(Styles.global_app())
        self.setWindowIcon(_make_app_icon())

        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        center_window(self)
        _log.info(f"MainWindow (opener) initialized — {WINDOW_TITLE}")

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._tab_manager = TabManager(parent=self)
        self._tab_manager.status_changed.connect(self._on_status_changed)
        self._tab_manager.title_changed.connect(self._on_title_changed)
        self.setCentralWidget(self._tab_manager)
        self.statusBar().showMessage("Ready  —  Open a PDF or ATLAS file to begin.")
        self.statusBar().setFont(Fonts.default(FontSize.SM))

    def _build_menus_legacy(self) -> None:
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        fm = mb.addMenu("&File")
        self._add_action(fm, "📂  Open…",             self._on_open_file,    "Ctrl+O")
        self._add_action(fm, "📂  Open in New Tab…",  self._on_open_new_tab, "Ctrl+Shift+O")
        fm.addSeparator()
        self._add_action(fm, "✕  Close Tab",          self._on_close_tab,    "Ctrl+W")
        self._add_action(fm, "➕  New Tab",            self._on_new_tab,      "Ctrl+T")
        fm.addSeparator()
        self._add_action(fm, "❌  Exit",               self.close,            "Ctrl+Q")

        # ── View ──────────────────────────────────────────────────────────
        vm = mb.addMenu("&View")
        self._add_action(vm, "🔍  Zoom In",    self._on_zoom_in,    "Ctrl++")
        self._add_action(vm, "🔍  Zoom Out",   self._on_zoom_out,   "Ctrl+-")
        self._add_action(vm, "⟳  Reset Zoom", self._on_zoom_reset, "Ctrl+0")

        # ── Help ──────────────────────────────────────────────────────────
        hm = mb.addMenu("&Help")
        self._add_action(hm, "📖  Documentation", self._show_docs)
        self._add_action(hm, "ℹ️  About", self._show_about)

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File
        fm = mb.addMenu("&File")
        self._add_action(fm, "📂  Open…",              self._on_open_file,     "Ctrl+O")
        self._add_action(fm, "📂  Open in New Tab…",   self._on_open_new_tab,  "Ctrl+Shift+O")
        fm.addSeparator()
        self._add_action(fm, "🖨️  Print…",             self._on_print,         "Ctrl+P")
        self._add_action(fm, "📋  Print Queue…",       self._on_print_queue,   "Ctrl+Alt+P")
        fm.addSeparator()
        self._add_action(fm, "🛡️  Protect PDF…",       self._on_protect_pdf,   "Ctrl+Shift+P")
        fm.addSeparator()
        self._add_action(fm, "✕  Close Tab",           self._on_close_tab,     "Ctrl+W")
        self._add_action(fm, "➕  New Tab",             self._on_new_tab,       "Ctrl+T")
        fm.addSeparator()
        self._add_action(fm, "❌  Exit",                self.close,             "Ctrl+Q")

        # View — Bookmarks / Thumbnails / Attachments are checkable
        vm = mb.addMenu("&View")

        self._act_bookmarks = QAction("📚  Bookmarks", self)
        self._act_bookmarks.setCheckable(True)
        self._act_bookmarks.triggered.connect(self._on_bookmarks)
        vm.addAction(self._act_bookmarks)

        self._act_thumbnails = QAction("🖼️  Thumbnails", self)
        self._act_thumbnails.setCheckable(True)
        self._act_thumbnails.triggered.connect(self._on_thumbnails)
        vm.addAction(self._act_thumbnails)

        self._act_attachments = QAction("📎  Attachments", self)
        self._act_attachments.setCheckable(True)
        self._act_attachments.triggered.connect(self._on_attachments)
        vm.addAction(self._act_attachments)

        vm.addSeparator()
        self._add_action(vm, "🔍  Zoom In",     self._on_zoom_in,    "Ctrl++")
        self._add_action(vm, "🔍  Zoom Out",    self._on_zoom_out,   "Ctrl+-")
        self._add_action(vm, "⟳  Reset Zoom",  self._on_zoom_reset, "Ctrl+0")

        # Document
        dm = mb.addMenu("&Document")
        self._add_action(dm, "ℹ️  Properties", self._on_doc_info)
        self._add_action(dm, "📋  Copy Page Text", self._on_copy_text, "Ctrl+C")
        dm.addSeparator()
        self._add_action(dm, "💾  Extract / Save As PDF…", self._on_extract_pdf, "Ctrl+Shift+S")

        # Tools
        tm = mb.addMenu("&Tools")
        self._add_action(tm, "🔑  Generate Keyfile…", self._on_gen_keyfile)

        # Help
        hm = mb.addMenu("&Help")
        self._add_action(hm, "📖  Documentation", self._show_docs)
        self._add_action(hm, "ℹ️  About",         self._show_about)

    def _build_shortcuts(self) -> None:
        from PySide6.QtGui import QShortcut
        QShortcut(QKeySequence(Qt.Key.Key_Left),     self).activated.connect(self._on_prev_page)
        QShortcut(QKeySequence(Qt.Key.Key_Right),    self).activated.connect(self._on_next_page)
        QShortcut(QKeySequence(Qt.Key.Key_PageUp),   self).activated.connect(self._on_prev_page)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self).activated.connect(self._on_next_page)

    def _add_action(self, menu, label: str, slot, shortcut: str = "") -> QAction:
        action = QAction(label, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        menu.addAction(action)
        return action

    # ── Active tab accessor ────────────────────────────────────────────────

    def _active_tab(self) -> Optional[PDFViewerTab]:
        return self._tab_manager.active_tab()

    # ── File / Tab Operations ──────────────────────────────────────────────

    @Slot()
    def _on_open_file(self) -> None:
        path = self._pick_file()
        if path:
            self._tab_manager.open_file_in_active_tab_or_new(path)

    @Slot()
    def _on_open_new_tab(self) -> None:
        path = self._pick_file()
        if path:
            self._tab_manager.open_in_new_tab(path)

    @Slot()
    def _on_new_tab(self) -> None:
        self._tab_manager.open_in_new_tab()

    @Slot()
    def _on_close_tab(self) -> None:
        self._tab_manager.close_active_tab()

    def _pick_file(self) -> Optional[str]:
        exts = " ".join(f"*{e}" for e in settings.document.supported_extensions)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            f"Documents ({exts} *.atlas);;PDF Files ({exts});;ATLAS Files (*.atlas);;All Files (*)"
        )
        return path or None

    def _load_document(self, path: str) -> None:
        """Called from main.py for CLI / file-association opens."""
        self._tab_manager.open_file_in_active_tab_or_new(path)

    # ── Navigation Delegates ───────────────────────────────────────────────

    @Slot()
    def _on_prev_page(self) -> None:
        tab = self._active_tab()
        if tab:
            tab._on_prev_page()

    @Slot()
    def _on_next_page(self) -> None:
        tab = self._active_tab()
        if tab:
            tab._on_next_page()

    # ── Zoom Delegates ─────────────────────────────────────────────────────

    @Slot()
    def _on_zoom_in(self) -> None:
        tab = self._active_tab()
        if tab:
            tab._on_zoom_in()

    @Slot()
    def _on_zoom_out(self) -> None:
        tab = self._active_tab()
        if tab:
            tab._on_zoom_out()

    @Slot()
    def _on_zoom_reset(self) -> None:
        tab = self._active_tab()
        if tab:
            tab._on_zoom_reset()


    # ── Help ───────────────────────────────────────────────────────────────

    @Slot()
    def _show_about(self) -> None:
        AboutDialog(parent=self).exec()

    @Slot()
    def _show_docs(self) -> None:
        DocumentationDialog(parent=self).exec()

    # ── Print ──────────────────────────────────────────────────────────────
    @Slot()
    def _on_print(self) -> None:
        show_premium_gate(self, "Print feature")

    @Slot()
    def _on_print_queue(self) -> None:
        show_premium_gate(self, "Print Queue Manager")

    @Slot()
    def _on_protect_pdf(self) -> None:
        show_premium_gate(self, "PDF Protection")

    @Slot()
    def _on_bookmarks(self) -> None:
        show_premium_gate(self, "Bookmarks")

    @Slot()
    def _on_thumbnails(self) -> None:
        show_premium_gate(self, "Thumbnails")

    @Slot()
    def _on_attachments(self) -> None:
        show_premium_gate(self, "Attachments")

    @Slot()
    def _on_doc_info(self) -> None:
        show_premium_gate(self, "Document Info")

    @Slot()
    def _on_copy_text(self) -> None:
        show_premium_gate(self, "Text Copy")

    @Slot()
    def _on_gen_keyfile(self) -> None:
        show_premium_gate(self, "Keyfile Generator")

    @Slot()
    def _on_extract_pdf(self) -> None:
        show_premium_gate(self, "Extract / Save as PDF")

    # ── Status / Title Slots ───────────────────────────────────────────────

    @Slot(str)
    def _on_status_changed(self, message: str) -> None:
        self.statusBar().showMessage(message)

    @Slot(str)
    def _on_title_changed(self, title: str) -> None:
        if title and title != "New Tab":
            self.setWindowTitle(f"{title}  —  {WINDOW_TITLE}")
        else:
            self.setWindowTitle(WINDOW_TITLE)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._tab_manager.close_all_tabs()
        super().closeEvent(event)

"""
atlas_viewer.ui.dialogs.documentation_dialog
==============================================
Structured, scrollable Documentation dialog for Atlas PDF Viewer.

Architecture
------------
* QDialog + QScrollArea — no web engine dependency.
* Content defined as structured Python data (sections + entries) so
  it's easy to extend without touching layout code.
* Keyboard shortcut table uses a two-column QFrame-based layout
  for clean alignment without QTableWidget overhead.
* Section headers use brand color and a bottom border rule,
  matching the visual language of the rest of the app.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.theme import Colors, FontFamily, FontSize
from config.version import APP_FULL_NAME, VERSION


# ─────────────────────────────────────────────────────────────────────────────
#  CONTENT DATA
# ─────────────────────────────────────────────────────────────────────────────

_FEATURES: List[Tuple[str, str]] = [
    (
        "Multi-Tab Document Viewing",
        "Open multiple PDFs simultaneously in independent tabs. "
        "Each tab maintains its own zoom level, page position, scroll state, "
        "and thumbnail panel. Switch between documents instantly with zero reload overhead.",
    ),
    (
        "ATLAS Encrypted Format (.atlas)",
        "Open and view password-protected .atlas files — a proprietary encrypted "
        "container format using AES-256-GCM encryption. The decrypted PDF content "
        "is held exclusively in process memory; it is never written to disk.",
    ),
    (
        "High-Resolution Thumbnail Panel",
        "The left-hand thumbnail strip renders actual PDF page content at screen "
        "resolution using QPdfDocument's native render pipeline. Thumbnails are "
        "generated asynchronously on background threads with LRU caching — "
        "visible thumbnails load first; off-screen thumbnails are pre-fetched on scroll.",
    ),
    (
        "Precision Zoom & Navigation",
        "Zoom from 25% to 500% via toolbar slider, keyboard shortcuts, or Ctrl+Scroll. "
        "Jump to any page by typing directly in the page-number field. "
        "First / Last / Previous / Next buttons provide rapid single-keystroke navigation.",
    ),
    (
        "Full-Text Search",
        "Search across the entire document with highlighted match results. "
        "Navigate forward and backward through matches with F3 / Shift+F3. "
        "Search is case-insensitive by default.",
    ),
    (
        "Bookmarks Panel",
        "View and navigate the PDF's outline tree in a dedicated sidebar panel. "
        "Click any bookmark entry to jump directly to the corresponding page.",
    ),
    (
        "Document Properties",
        "Inspect full PDF metadata: title, author, subject, creator, producer, "
        "file size, page count, and PDF version.",
    ),
    (
        "Print Support",
        "Print directly to any system printer with correct multi-page output, "
        "aspect-ratio-preserving scaling, and user-selectable page ranges. "
        "Uses Qt's native QPrinter pipeline — no third-party print drivers required.",
    ),
    (
        "Attachment Extraction",
        "Detect and save embedded file attachments from PDF files.",
    ),
]

_SHORTCUTS: List[Tuple[str, str]] = [
    ("Ctrl + O",         "Open file"),
    ("Ctrl + W",         "Close current tab"),
    ("Ctrl + Tab",       "Next tab"),
    ("Ctrl + Shift+Tab", "Previous tab"),
    ("Ctrl + P",         "Print document"),
    ("Ctrl + F",         "Find / Search"),
    ("F3",               "Find next match"),
    ("Shift + F3",       "Find previous match"),
    ("Escape",           "Close search / dismiss dialog"),
    ("Ctrl + Home",      "Go to first page"),
    ("Ctrl + End",       "Go to last page"),
    ("Page Up",          "Previous page"),
    ("Page Down",        "Next page"),
    ("↑ / ↓",           "Scroll page content"),
    ("Ctrl + =",         "Zoom in"),
    ("Ctrl + −",         "Zoom out"),
    ("Ctrl + 0",         "Reset zoom to 100%"),
    ("Ctrl + Scroll",    "Zoom in / out"),
    ("F1",               "Open this documentation"),
]

_NAVIGATION_TIPS: List[str] = [
    "Click a thumbnail in the left panel to jump directly to that page.",
    "Double-click the page-number spinbox to select all text — then type a page number and press Enter.",
    "The zoom slider updates the view in real time; release to apply the final zoom.",
    "Use Ctrl+Tab / Ctrl+Shift+Tab to cycle tabs without touching the mouse.",
    "Right-click a tab to close it or open a new file in that position.",
    "The status bar shows the current page, total pages, zoom level, and document file name.",
]

_PERFORMANCE_NOTES: List[str] = [
    "Thumbnail rendering is fully asynchronous — the UI never blocks while thumbnails load.",
    "Up to 300 thumbnails are kept in an LRU memory cache (≈ 24 MB at default resolution).",
    "Each background render thread opens its own independent QPdfDocument instance — "
    "no shared Qt object state, no race conditions.",
    "Large PDFs (500+ pages) may take a few seconds to fully populate the thumbnail strip; "
    "visible thumbnails always render first.",
    "For ATLAS-encrypted files, the decrypted PDF lives only in RAM — no temp files are "
    "created, and memory is released as soon as the tab is closed.",
    "Printing at high printer DPI (600 dpi+) renders each page at full printer resolution — "
    "output quality matches the PDF's native resolution.",
]


# ─────────────────────────────────────────────────────────────────────────────
#  DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class DocumentationDialog(QDialog):
    """
    Full-featured, scrollable documentation dialog.

    Sections:
    1. Features Overview
    2. Keyboard Shortcuts
    3. Navigation Guide
    4. Performance Notes
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_FULL_NAME} — Documentation")
        self.resize(680, 620)
        self.setMinimumSize(560, 480)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_title_bar())
        root.addWidget(self._make_scroll_area(), stretch=1)
        root.addWidget(self._make_footer())

    # ─── Title bar ────────────────────────────────────────────────────────

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(64)
        bar.setStyleSheet(
            f"background-color: {Colors.PRIMARY};"
            " border-bottom: 2px solid #0D2B47;"
        )
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(2)

        title = QLabel(f"{APP_FULL_NAME}  —  Documentation")
        title_font = QFont(FontFamily.SANS)
        title_font.setPixelSize(16)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {Colors.TEXT_WHITE}; background: transparent;")

        sub = QLabel(f"Version {VERSION}  ·  User Reference Guide")
        sub.setStyleSheet(
            f"color: rgba(255,255,255,0.70); font-size: {FontSize.SM}px;"
            " background: transparent;"
        )

        layout.addWidget(title)
        layout.addWidget(sub)
        return bar

    # ─── Scroll content ───────────────────────────────────────────────────

    def _make_scroll_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"background-color: {Colors.SURFACE}; border: none;"
        )

        content = QWidget()
        content.setStyleSheet(f"background-color: {Colors.SURFACE};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(24)

        # ── Section 1: Features ───────────────────────────────────────────
        layout.addWidget(self._section_heading("Features Overview"))
        for title, desc in _FEATURES:
            layout.addWidget(self._feature_card(title, desc))

        layout.addWidget(self._divider())

        # ── Section 2: Keyboard Shortcuts ─────────────────────────────────
        layout.addWidget(self._section_heading("Keyboard Shortcuts"))
        layout.addWidget(self._shortcut_table(_SHORTCUTS))

        layout.addWidget(self._divider())

        # ── Section 3: Navigation Guide ────────────────────────────────────
        layout.addWidget(self._section_heading("Navigation Guide"))
        for tip in _NAVIGATION_TIPS:
            layout.addWidget(self._bullet_item(tip))

        layout.addWidget(self._divider())

        # ── Section 4: Performance Notes ───────────────────────────────────
        layout.addWidget(self._section_heading("Performance Notes"))
        for note in _PERFORMANCE_NOTES:
            layout.addWidget(self._bullet_item(note))

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ─── Footer ───────────────────────────────────────────────────────────

    def _make_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(52)
        footer.setStyleSheet(
            f"background-color: {Colors.TOOLBAR_BG};"
            f" border-top: 1px solid {Colors.BORDER};"
        )
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 8, 20, 8)

        hint = QLabel("Press Escape or click Close to dismiss.")
        hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {FontSize.XS}px;"
            " background: transparent;"
        )

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(90, 34)
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {Colors.PRIMARY}; color: white;"
            "  border: none; border-radius: 5px;"
            "  font-weight: 700; font-size: 13px;"
            "}}"
            f"QPushButton:hover {{ background-color: {Colors.PRIMARY_HOVER}; }}"
            f"QPushButton:pressed {{ background-color: {Colors.PRIMARY_PRESSED}; }}"
        )
        close_btn.clicked.connect(self.accept)
        close_btn.setShortcut("Escape")

        layout.addWidget(hint)
        layout.addStretch()
        layout.addWidget(close_btn)
        return footer

    # ─── Reusable widgets ─────────────────────────────────────────────────

    def _section_heading(self, text: str) -> QLabel:
        lbl = QLabel(text)
        font = QFont(FontFamily.SANS)
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.Bold)
        lbl.setFont(font)
        lbl.setStyleSheet(
            f"color: {Colors.PRIMARY};"
            f" border-bottom: 2px solid {Colors.PRIMARY};"
            " padding-bottom: 6px;"
            " background: transparent;"
        )
        return lbl

    def _feature_card(self, title: str, description: str) -> QFrame:
        """Expandable feature card with bold title and wrapped description."""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.NoFrame)
        card.setStyleSheet(
            f"background-color: {Colors.SURFACE_CARD};"
            f" border: 1px solid {Colors.BORDER_LIGHT};"
            " border-radius: 6px;"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_font = QFont(FontFamily.SANS)
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {FontSize.SM}px;"
            " background: transparent; border: none;"
            " line-height: 1.5;"
        )
        desc_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout.addWidget(title_lbl)
        layout.addWidget(desc_lbl)
        return card

    def _shortcut_table(self, shortcuts: List[Tuple[str, str]]) -> QWidget:
        """Two-column shortcut reference table."""
        container = QWidget()
        container.setStyleSheet(
            f"background-color: {Colors.SURFACE_CARD};"
            f" border: 1px solid {Colors.BORDER};"
            " border-radius: 6px;"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for idx, (keys, action) in enumerate(shortcuts):
            row = self._shortcut_row(keys, action, alternate=(idx % 2 == 1))
            layout.addWidget(row)

        return container

    def _shortcut_row(
        self, keys: str, action: str, alternate: bool = False
    ) -> QWidget:
        row = QWidget()
        bg  = Colors.SURFACE_CARD if not alternate else "#F4F6F8"
        row.setStyleSheet(f"background-color: {bg};")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(0)

        key_lbl = QLabel(keys)
        key_lbl.setFixedWidth(170)
        key_lbl.setStyleSheet(
            f"font-family: '{FontFamily.MONO}';"
            f" font-size: {FontSize.SM}px;"
            f" color: {Colors.PRIMARY};"
            " font-weight: 600;"
            " background: transparent;"
        )

        action_lbl = QLabel(action)
        action_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {FontSize.SM}px;"
            " background: transparent;"
        )

        layout.addWidget(key_lbl)
        layout.addWidget(action_lbl, stretch=1)
        return row

    def _bullet_item(self, text: str) -> QWidget:
        """Bullet-point list item."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        bullet = QLabel("•")
        bullet.setFixedWidth(14)
        bullet.setStyleSheet(
            f"color: {Colors.PRIMARY}; font-size: 16px; background: transparent;"
        )
        bullet.setAlignment(Qt.AlignmentFlag.AlignTop)

        body_lbl = QLabel(text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {FontSize.SM}px;"
            " background: transparent;"
        )
        body_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout.addWidget(bullet)
        layout.addWidget(body_lbl)
        return row

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {Colors.BORDER_LIGHT};")
        return line
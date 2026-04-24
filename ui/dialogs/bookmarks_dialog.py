"""
atlas_viewer.ui.dialogs.bookmarks_dialog
==========================================
BookmarksDialog — displays the PDF bookmark tree with click-to-navigate.

No business logic here — receives a pre-built BookmarkNode tree and
emits ``navigate_to_page`` when a node is clicked.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.theme import Colors, Fonts, FontSize, Spacing
from models import BookmarkNode
from ui.dialogs.base_dialog import BaseDialog
from utils import get_logger

_log = get_logger(__name__)


class BookmarksDialog(BaseDialog):
    """
    Modal dialog showing the hierarchical PDF bookmark tree.

    Signals:
        navigate_to_page(int): Emitted when the user clicks a bookmark.
            The int is a 0-based page index.
    """

    navigate_to_page = Signal(int)

    def __init__(
        self,
        roots: List[BookmarkNode],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent, title="📚  Bookmarks", width=480, height=560)
        self._roots = roots
        self._build_ui()
        self._populate_tree()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # Header
        heading = self.make_section_label("📚  Document Bookmarks")
        heading.setFont(Fonts.heading(FontSize.LG))
        root.addWidget(heading)

        if not self._roots:
            empty = QLabel("This document has no bookmarks.")
            empty.setFont(Fonts.default(FontSize.BASE))
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; padding: {Spacing.MD}px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty)
        else:
            count_lbl = QLabel(
                f"{self._total_count(self._roots)} bookmark"
                f"{'s' if self._total_count(self._roots) != 1 else ''}"
            )
            count_lbl.setFont(Fonts.default(FontSize.SM))
            count_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            root.addWidget(count_lbl)

        root.addWidget(self.make_separator())

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFont(Fonts.default(FontSize.BASE))
        self._tree.setAlternatingRowColors(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(18)
        self._tree.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self._tree)

        root.addLayout(
            self.make_button_row([("✕  Close", "ghost", self.accept)])
        )

    def _populate_tree(self) -> None:
        """Recursively build QTreeWidgetItems from BookmarkNode tree."""
        self._tree.clear()
        for node in self._roots:
            item = self._build_item(node)
            self._tree.addTopLevelItem(item)
        self._tree.expandToDepth(1)

    def _build_item(self, node: BookmarkNode) -> QTreeWidgetItem:
        """Convert a BookmarkNode to a QTreeWidgetItem recursively."""
        item = QTreeWidgetItem()
        item.setText(0, node.title or "(Untitled)")
        item.setData(0, Qt.ItemDataRole.UserRole, node.page)
        item.setToolTip(0, f"Go to page {node.page + 1}")
        item.setFont(0, Fonts.default(FontSize.BASE, bold=(node.level == 0)))
        for child in node.children:
            item.addChild(self._build_item(child))
        return item

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is None:
            _log.debug("Bookmark click ignored — no page data stored on item.")
            return
        if not isinstance(page, int):
            _log.error(
                "Bookmark click: expected int page, got %r (%s) — ignoring.",
                page, type(page).__name__,
            )
            return
        if page < 0:
            _log.debug("Bookmark click — page index %d is unresolvable; ignoring.", page)
            return
        _log.debug("Bookmark click → page %d", page)
        self.navigate_to_page.emit(page)

    @staticmethod
    def _total_count(nodes: List[BookmarkNode]) -> int:
        return sum(1 + BookmarksDialog._total_count(n.children) for n in nodes)

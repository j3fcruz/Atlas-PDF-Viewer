"""
atlas_viewer.ui.dialogs.base_dialog
=====================================
BaseDialog — themed base class for all application dialogs.

Provides
--------
* Automatic centering on parent or primary screen.
* Consistent Segoe UI font application.
* Reusable widget factory helpers (separator, section label, button row).
* No business logic — pure UI infrastructure.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from config.theme import Colors, Fonts, FontSize, Spacing, Styles
from utils.ui_helpers import center_window, make_h_separator


class BaseDialog(QDialog):
    """
    Base class for all ATLAS Viewer dialogs.

    Subclasses should call super().__init__(parent, title, ...) and then
    build their layout on top of the pre-wired root QVBoxLayout.

    Args:
        parent: Parent widget for centering and modal ownership.
        title:  Window title string.
        width:  Initial dialog width in pixels.
        height: Initial dialog height in pixels.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "",
        width: int = 540,
        height: int = 420,
    ) -> None:
        super().__init__(parent)
        if title:
            self.setWindowTitle(title)
        self.resize(width, height)
        self.setFont(Fonts.default())
        if parent:
            center_window(self, parent)
        else:
            center_window(self)

    # ── Widget Factory Helpers ─────────────────────────────────────────────

    @staticmethod
    def make_separator() -> QFrame:
        """Return a styled 1px horizontal divider."""
        return make_h_separator()

    @staticmethod
    def make_section_label(text: str) -> QLabel:
        """Return a primary-colored section heading label."""
        lbl = QLabel(text)
        lbl.setFont(Fonts.heading(FontSize.MD))
        lbl.setStyleSheet(f"color: {Colors.PRIMARY}; font-weight: 700; background: transparent;")
        return lbl

    @staticmethod
    def make_info_banner(text: str, color: str = Colors.PRIMARY, bg: str = Colors.PRIMARY_LIGHT) -> QLabel:
        """Return a colored info banner label."""
        lbl = QLabel(text)
        lbl.setFont(Fonts.default(FontSize.SM))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {color}; background: {bg}; "
            f"padding: 10px 14px; border-radius: 5px; "
            f"border-left: 4px solid {color};"
        )
        return lbl

    def make_button_row(
        self,
        buttons: List[Tuple[str, str, Callable]],
    ) -> QHBoxLayout:
        """
        Create a right-aligned button row.

        Args:
            buttons: List of (label, style_name, callback) tuples.
                     style_name: "primary" | "danger" | "success" | "ghost"

        Returns:
            QHBoxLayout: Layout containing the buttons.
        """
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        row.addStretch()
        for label, style_name, callback in buttons:
            btn = QPushButton(label)
            btn.setFont(Fonts.default(FontSize.BASE, bold=True))
            style_map = {
                "primary": Styles.btn_primary(),
                "danger":  Styles.btn_danger(),
                "success": Styles.btn_success(),
                "ghost":   Styles.btn_ghost(),
            }
            btn.setStyleSheet(style_map.get(style_name, Styles.btn_primary()))
            btn.setMinimumWidth(110)
            btn.clicked.connect(callback)
            row.addWidget(btn)
        return row

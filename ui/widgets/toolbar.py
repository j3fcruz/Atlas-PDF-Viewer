"""
atlas_opener.ui.widgets.toolbar
=================================
ViewerToolbar — navigation and zoom only (opener build).

Removed vs full build:
  * copy_text signal / button
  * export_pdf signal / button
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QWidget,
)

from config.settings import settings
from config.theme import Colors, Fonts, FontSize, Sizing, Spacing, Styles
from utils.ui_helpers import make_v_separator


class ViewerToolbar(QWidget):
    """
    Single-row toolbar: open, close, navigation, zoom.

    Signals:
        prev_page():        Prev page clicked.
        next_page():        Next page clicked.
        jump_to_page(int):  Page number entered (0-based).
        zoom_changed(int):  Slider changed (percent).
        zoom_in():          Zoom-in clicked.
        zoom_out():         Zoom-out clicked.
        zoom_reset():       Reset zoom clicked.
        open_file():        Open button clicked.
        close_document():   Close button clicked.
    """

    prev_page      = Signal()
    next_page      = Signal()
    jump_to_page   = Signal(int)
    zoom_changed   = Signal(int)
    zoom_in_sig    = Signal()
    zoom_out_sig   = Signal()
    zoom_reset_sig = Signal()
    open_file      = Signal()
    close_document = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(Sizing.TOOLBAR_HEIGHT)
        self.setStyleSheet(Styles.toolbar_frame())
        self._build_ui()

    def _build_ui(self) -> None:
        bar = QHBoxLayout(self)
        bar.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        bar.setSpacing(Spacing.SM)

        # ── File Actions ───────────────────────────────────────────────────
        self._open_btn = self._flat_btn("📂  Open", "Open file (Ctrl+O)", self.open_file)
        bar.addWidget(self._open_btn)

        self._close_btn = self._flat_btn("✕  Close", "Close document (Ctrl+W)", self.close_document)
        bar.addWidget(self._close_btn)

        bar.addWidget(make_v_separator())

        # ── Navigation ─────────────────────────────────────────────────────
        self._prev_btn = self._flat_btn("◀", "Previous page (←)", self.prev_page)
        self._prev_btn.setFixedWidth(36)
        bar.addWidget(self._prev_btn)

        self._page_input = QLineEdit()
        self._page_input.setFixedWidth(52)
        self._page_input.setFont(Fonts.default(FontSize.BASE, bold=True))
        self._page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_input.setPlaceholderText("—")
        self._page_input.setStyleSheet(
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: 4px; background: white;"
        )
        self._page_input.returnPressed.connect(self._on_page_entered)
        bar.addWidget(self._page_input)

        self._page_total = QLabel("/ 0")
        self._page_total.setFont(Fonts.default(FontSize.BASE))
        self._page_total.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        bar.addWidget(self._page_total)

        self._next_btn = self._flat_btn("▶", "Next page (→)", self.next_page)
        self._next_btn.setFixedWidth(36)
        bar.addWidget(self._next_btn)

        bar.addWidget(make_v_separator())

        # ── Zoom ───────────────────────────────────────────────────────────
        self._zoom_out_btn = self._flat_btn("−", "Zoom out (Ctrl+−)", self.zoom_out_sig)
        self._zoom_out_btn.setFixedWidth(30)
        bar.addWidget(self._zoom_out_btn)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(settings.ui.zoom_min, settings.ui.zoom_max)
        self._zoom_slider.setValue(settings.ui.default_zoom)
        self._zoom_slider.setFixedWidth(130)
        self._zoom_slider.setFixedHeight(22)
        self._zoom_slider.setStyleSheet(Styles.slider())
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider)
        bar.addWidget(self._zoom_slider)

        self._zoom_in_btn = self._flat_btn("+", "Zoom in (Ctrl++)", self.zoom_in_sig)
        self._zoom_in_btn.setFixedWidth(30)
        bar.addWidget(self._zoom_in_btn)

        self._zoom_label = QLabel(f"{settings.ui.default_zoom}%")
        self._zoom_label.setFont(Fonts.default(FontSize.SM, bold=True))
        self._zoom_label.setFixedWidth(42)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        bar.addWidget(self._zoom_label)

        self._zoom_reset_btn = self._flat_btn("⟳", "Reset zoom (Ctrl+0)", self.zoom_reset_sig)
        self._zoom_reset_btn.setFixedWidth(30)
        bar.addWidget(self._zoom_reset_btn)

        bar.addStretch()

    # ── Public Update Methods ───────────────────────────────────────────────

    def set_page(self, current: int, total: int) -> None:
        self._page_input.setText(str(current + 1))
        self._page_total.setText(f"/ {total}")
        self._prev_btn.setEnabled(current > 0)
        self._next_btn.setEnabled(current < total - 1)

    def set_zoom(self, percent: int) -> None:
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(
            max(settings.ui.zoom_min, min(settings.ui.zoom_max, percent))
        )
        self._zoom_slider.blockSignals(False)
        self._zoom_label.setText(f"{percent}%")

    def set_document_open(self, open_: bool) -> None:
        for w in (self._prev_btn, self._next_btn, self._page_input,
                  self._zoom_slider, self._close_btn):
            w.setEnabled(open_)

    # ── Slots ───────────────────────────────────────────────────────────────

    def _on_page_entered(self) -> None:
        try:
            n = int(self._page_input.text().strip()) - 1
            self.jump_to_page.emit(n)
        except ValueError:
            pass

    def _on_zoom_slider(self, value: int) -> None:
        self._zoom_label.setText(f"{value}%")
        self.zoom_changed.emit(value)

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _flat_btn(label: str, tooltip: str, signal: Signal) -> QPushButton:
        btn = QPushButton(label)
        btn.setFont(Fonts.default(FontSize.BASE, bold=True))
        btn.setFixedHeight(Sizing.BUTTON_HEIGHT_SM + 2)
        btn.setMinimumWidth(36)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(Styles.btn_flat())
        btn.clicked.connect(signal)
        return btn

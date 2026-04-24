"""
atlas_viewer.ui.widgets.search_panel
======================================
SearchPanel — sidebar panel for full-text PDF search.

Features
--------
* Debounced search input (300ms after last keystroke).
* Result list showing page number and snippet for each hit.
* Clicking a result navigates the viewer to that page.
* Emits ``highlight_map_ready`` with the HighlightMap for the rendering
  layer to draw keyword overlays.
* Shows indexing-in-progress indicator while the IndexEngine works.
* Graceful empty-state messages for no results / not indexed.

Integration
-----------
``SearchPanel`` requires a :class:`~indexing.search_engine.SearchEngine`
and a :class:`~indexing.index_engine.IndexEngine`.  Both are provided by
``PDFViewerTab`` after a document opens.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.theme import Colors, Fonts, FontSize
from indexing.index_engine import SearchResult
from indexing.search_engine import HighlightMap, SearchEngine


class SearchPanel(QWidget):
    """
    Full-text search sidebar panel.

    Signals:
        navigate_to_page(int):              Emitted when a result is clicked
                                            (0-based page index).
        highlight_map_ready(dict):          Emitted after each search with
                                            the HighlightMap for overlay rendering.
                                            Dict is ``{page_index: [terms]}``.
    """

    navigate_to_page    = Signal(int)
    highlight_map_ready = Signal(dict)   # HighlightMap

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._search_engine: Optional[SearchEngine] = None
        self._last_results:  List[SearchResult] = []
        self._last_query:    str = ""
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def set_search_engine(self, engine: SearchEngine) -> None:
        """
        Attach a SearchEngine for the current document.

        Disconnects any previously connected engine first.

        Args:
            engine: SearchEngine bound to the active document.
        """
        if self._search_engine is not None:
            try:
                self._search_engine.results_ready.disconnect(self._on_results)
                self._search_engine.search_started.disconnect(self._on_search_started)
            except RuntimeError:
                pass

        self._search_engine = engine
        engine.results_ready.connect(self._on_results)
        engine.search_started.connect(self._on_search_started)
        self._clear_results()
        self._input.setEnabled(True)
        self._input.setPlaceholderText("Search document…")

    def detach(self) -> None:
        """Detach from the current search engine (document closed)."""
        if self._search_engine is not None:
            try:
                self._search_engine.results_ready.disconnect(self._on_results)
                self._search_engine.search_started.disconnect(self._on_search_started)
            except RuntimeError:
                pass
            self._search_engine = None

        self._input.clear()
        self._input.setEnabled(False)
        self._input.setPlaceholderText("Open a document to search…")
        self._clear_results()
        self._set_status("")

    def set_indexing_progress(self, pages_done: int, total_pages: int) -> None:
        """
        Update the indexing progress bar.

        Args:
            pages_done:  Number of pages indexed so far.
            total_pages: Total pages in the document.
        """
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(total_pages)
        self._progress_bar.setValue(pages_done)
        pct = int(pages_done / max(total_pages, 1) * 100)
        self._set_status(f"Indexing… {pct}%")

    def set_indexing_complete(self) -> None:
        """Hide the progress bar and show 'indexed' status."""
        self._progress_bar.setVisible(False)
        self._set_status("Document indexed — ready to search.")

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QLabel("Search")
        header.setFont(Fonts.default(FontSize.SM, bold=True))
        header.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: {Colors.TOOLBAR_BG}; "
            f"padding: 8px 10px; border-bottom: 1px solid {Colors.BORDER};"
        )
        root.addWidget(header)

        # Search input row
        input_row = QHBoxLayout()
        input_row.setContentsMargins(8, 8, 8, 4)
        input_row.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Open a document to search…")
        self._input.setEnabled(False)
        self._input.setFont(Fonts.default(FontSize.SM))
        self._input.setStyleSheet(
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: 5px 8px; background: white;"
        )
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_return_pressed)
        input_row.addWidget(self._input)

        # Clear button (✕)
        self._clear_btn = QLabel("✕")
        self._clear_btn.setFixedSize(20, 20)
        self._clear_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; "
            f"border-radius: 10px;"
        )
        self._clear_btn.setVisible(False)
        self._clear_btn.mousePressEvent = lambda _: self._input.clear()  # type: ignore[method-assign]
        input_row.addWidget(self._clear_btn)

        root.addLayout(input_row)

        # Indexing progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ border: none; background: {Colors.BORDER_LIGHT}; }}"
            f"QProgressBar::chunk {{ background: {Colors.PRIMARY}; }}"
        )
        root.addWidget(self._progress_bar)

        # Status label
        self._status_lbl = QLabel("")
        self._status_lbl.setFont(Fonts.default(FontSize.XS))
        self._status_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; padding: 0px 10px 2px 10px;"
        )
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color: {Colors.BORDER_LIGHT};")
        root.addWidget(div)

        # Results list
        self._result_list = QListWidget()
        self._result_list.setStyleSheet(
            f"QListWidget {{ border: none; background: {Colors.PANEL_BG}; }}"
            f"QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {Colors.BORDER_LIGHT}; }}"
            f"QListWidget::item:selected {{ background: {Colors.PRIMARY_LIGHT}; color: {Colors.PRIMARY}; }}"
            f"QListWidget::item:hover {{ background: {Colors.THUMB_HOVER_BG}; }}"
        )
        self._result_list.setFont(Fonts.default(FontSize.XS))
        self._result_list.itemClicked.connect(self._on_result_clicked)
        root.addWidget(self._result_list, stretch=1)

        # Empty-state label (shown when no results)
        self._empty_lbl = QLabel("No results.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setFont(Fonts.default(FontSize.SM))
        self._empty_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; padding: 20px;"
        )
        self._empty_lbl.setVisible(False)
        root.addWidget(self._empty_lbl)

    # ── Slots ──────────────────────────────────────────────────────────────

    @Slot(str)
    def _on_text_changed(self, text: str) -> None:
        self._clear_btn.setVisible(bool(text))
        if self._search_engine is None:
            return
        if not text.strip():
            self._clear_results()
            self._set_status("")
            return
        self._search_engine.search_debounced(text)

    @Slot()
    def _on_return_pressed(self) -> None:
        """Force-fire the search immediately on Enter."""
        if self._search_engine and self._input.text().strip():
            self._search_engine._timer.stop()
            self._search_engine._fire_search()

    @Slot()
    def _on_search_started(self) -> None:
        self._set_status("Searching…")

    @Slot(list)
    def _on_results(self, results: list) -> None:
        self._last_results = results
        self._last_query   = self._input.text().strip()
        self._populate_results(results)

        if self._search_engine is not None:
            hmap = self._search_engine.highlight_map(self._last_query, results)
            self.highlight_map_ready.emit(hmap)

        count = len(results)
        if count == 0:
            self._set_status("No matches found.")
        elif count == 1:
            self._set_status("1 match found.")
        else:
            self._set_status(f"{count} matches found.")

    @Slot(QListWidgetItem)
    def _on_result_clicked(self, item: QListWidgetItem) -> None:
        page = item.data(Qt.ItemDataRole.UserRole)
        if page is not None:
            self.navigate_to_page.emit(int(page))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _populate_results(self, results: List[SearchResult]) -> None:
        self._result_list.clear()
        if not results:
            self._result_list.setVisible(False)
            self._empty_lbl.setVisible(True)
            return

        self._empty_lbl.setVisible(False)
        self._result_list.setVisible(True)

        for result in results:
            page_label = f"Page {result.page_index + 1}"
            # Strip HTML tags from snippet for display
            import re
            clean_snippet = re.sub(r"<[^>]+>", "", result.snippet).strip()
            display = f"{page_label}\n{clean_snippet}" if clean_snippet else page_label

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, result.page_index)
            item.setToolTip(
                f"Page {result.page_index + 1}  —  score {result.score:.3f}"
            )
            self._result_list.addItem(item)

    def _clear_results(self) -> None:
        self._result_list.clear()
        self._result_list.setVisible(True)
        self._empty_lbl.setVisible(False)
        self._last_results = []

    def _set_status(self, msg: str) -> None:
        self._status_lbl.setText(msg)
        self._status_lbl.setVisible(bool(msg))
"""
atlas_viewer.ui.dialogs.attachments_dialog
============================================
AttachmentsDialog — lists embedded PDF attachments and allows extraction.

Business logic (extraction) is delegated to AttachmentService.
This class is UI-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.theme import Colors, Fonts, FontSize, Spacing, Styles
from models import AttachmentInfo
from services.attachment_service import AttachmentService
from ui.dialogs.base_dialog import BaseDialog
from utils import get_logger, human_readable_size

_log = get_logger(__name__)


class AttachmentsDialog(BaseDialog):
    """
    Dialog for listing and extracting PDF embedded file attachments.

    Args:
        attachments:         Pre-fetched list of AttachmentInfo objects.
        attachment_service:  Service instance for performing extraction.
        parent:              Parent widget.
    """

    def __init__(
        self,
        attachments: List[AttachmentInfo],
        attachment_service: AttachmentService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent, title="📎  Attachments", width=620, height=440)
        self._attachments = attachments
        self._service = attachment_service
        self._build_ui()
        self._populate_table()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        root.addWidget(self.make_section_label("📎  Embedded File Attachments"))

        if not self._attachments:
            empty = QLabel("This document has no embedded file attachments.")
            empty.setFont(Fonts.default(FontSize.BASE))
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; padding: {Spacing.MD}px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty)
        else:
            count_badge = QLabel(f"{len(self._attachments)} attachment(s) found")
            count_badge.setFont(Fonts.default(FontSize.SM))
            count_badge.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            root.addWidget(count_badge)

        root.addWidget(self.make_separator())

        # Table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Filename", "Size", "Description"])
        self._table.setFont(Fonts.default(FontSize.BASE))
        self._table.horizontalHeader().setFont(Fonts.default(FontSize.SM, bold=True))
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 240)
        self._table.setColumnWidth(1, 90)
        root.addWidget(self._table)

        # Extract button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._extract_btn = QPushButton("⬇  Extract Selected")
        self._extract_btn.setFont(Fonts.default(FontSize.BASE, bold=True))
        self._extract_btn.setStyleSheet(Styles.btn_primary())
        self._extract_btn.setEnabled(bool(self._attachments))
        self._extract_btn.clicked.connect(self._extract_selected)
        btn_row.addWidget(self._extract_btn)

        self._extract_all_btn = QPushButton("⬇  Extract All")
        self._extract_all_btn.setFont(Fonts.default(FontSize.BASE, bold=True))
        self._extract_all_btn.setStyleSheet(Styles.btn_ghost())
        self._extract_all_btn.setEnabled(bool(self._attachments))
        self._extract_all_btn.clicked.connect(self._extract_all)
        btn_row.addWidget(self._extract_all_btn)

        close_btn = QPushButton("✕  Close")
        close_btn.setFont(Fonts.default(FontSize.BASE))
        close_btn.setStyleSheet(Styles.btn_ghost())
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._attachments))
        for row, att in enumerate(self._attachments):
            name_item = QTableWidgetItem(att.safe_name)
            name_item.setFont(Fonts.mono(FontSize.SM))
            name_item.setToolTip(f"Original: {att.name}")
            self._table.setItem(row, 0, name_item)

            size_str = human_readable_size(att.size) if att.size >= 0 else "Unknown"
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            size_item.setFont(Fonts.default(FontSize.SM))
            self._table.setItem(row, 1, size_item)

            desc_item = QTableWidgetItem(att.description or "—")
            desc_item.setFont(Fonts.default(FontSize.SM))
            self._table.setItem(row, 2, desc_item)

    def _extract_selected(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "No Selection", "Select one or more attachments first.")
            return
        selected = [self._attachments[r] for r in sorted(rows)]
        self._run_extraction(selected)

    def _extract_all(self) -> None:
        self._run_extraction(self._attachments)

    def _run_extraction(self, attachments: List[AttachmentInfo]) -> None:
        out_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", str(Path.home())
        )
        if not out_dir:
            return

        successes, failures = [], []
        for att in attachments:
            try:
                dest = self._service.extract_to_dir(att, out_dir)
                successes.append(str(dest.name))
            except Exception as exc:
                _log.error(f"Extraction failed for '{att.safe_name}': {exc}")
                failures.append(att.safe_name)

        lines = []
        if successes:
            lines.append(f"✓  Extracted {len(successes)} file(s) to:\n  {out_dir}")
        if failures:
            lines.append(f"\n✗  Failed: {', '.join(failures)}")

        QMessageBox.information(self, "Extraction Complete", "\n".join(lines))

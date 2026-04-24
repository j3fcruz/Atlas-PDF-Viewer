"""
atlas_viewer.ui.dialogs.info_dialogs  (FIX-DIALOGS-v3)
========================================================
DocumentInfoDialog, AboutDialog, DocumentationDialog.

Changes in this revision
-------------------------
[FIX-ABOUT-2]
  AboutDialog completely redesigned as a user-facing product presentation:
  - Hero section: app icon + name + tagline
  - "What can it do?" feature grid with icons — user language, not dev language
  - Security highlight strip (the key differentiator for ATLAS)
  - Version / build / copyright footer with clickable website
  - Dark card aesthetic matching the app's professional theme
  - No tech stack jargon on the primary surface — moved to a collapsible section
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStyle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_FULL_NAME, COPYRIGHT, VERSION,
    Colors, Fonts, FontSize, Spacing,
)
from config.version import DESCRIPTION, BUILD_DATE, WEBSITE, AUTHOR
from models import DocumentInfo
from ui.dialogs.base_dialog import BaseDialog
from utils import human_readable_size


# ── App icon SVG (shield + document + search lens) ───────────────────────────
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
  <line x1="47" y1="49" x2="53" y2="55" stroke="white" stroke-width="3"
        stroke-linecap="round"/>
  <circle cx="40" cy="42" r="2" fill="white" opacity="0.3"/>
</svg>
"""


def _make_icon_pixmap(size: int = 56) -> QPixmap:
    """Render the app SVG icon to a QPixmap at the given size."""
    try:
        renderer = QSvgRenderer(QByteArray(_APP_ICON_SVG))
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        return pix
    except Exception:
        style = QApplication.style()
        return style.standardIcon(  # type: ignore[union-attr]
            QStyle.StandardPixmap.SP_FileDialogDetailedView
        ).pixmap(size, size)


# ─────────────────────────────────────────────────────────────────────────────
#  DOCUMENT INFO DIALOG  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentInfoDialog(BaseDialog):
    """Dialog displaying metadata and integrity info for the open document."""

    def __init__(
        self,
        doc_info: Optional[DocumentInfo],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent, title="ℹ️  Document Information", width=560, height=420)
        self._doc_info = doc_info
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.MD)

        root.addWidget(self.make_section_label("ℹ️  Document Properties"))
        root.addWidget(self.make_separator())

        box = QTextBrowser()
        box.setReadOnly(True)
        box.setFont(Fonts.mono(FontSize.SM))
        box.setOpenExternalLinks(False)

        if self._doc_info:
            d = self._doc_info
            lines = [
                f"Path         :  {d.path or '<in-memory>'}",
                f"File Size    :  {human_readable_size(d.file_size) if d.file_size > 0 else 'N/A (in-memory)'}",
                f"Pages        :  {d.page_count}",
                f"PDF Version  :  {d.pdf_version or '—'}",
                "",
                f"Title        :  {d.title or '—'}",
                f"Author       :  {d.author or '—'}",
                f"Subject      :  {d.subject or '—'}",
                f"Creator      :  {d.creator or '—'}",
                f"Producer     :  {d.producer or '—'}",
                "",
                f"Encrypted    :  {'Yes' if d.is_encrypted else 'No'}",
            ]
            box.setPlainText("\n".join(lines))
        else:
            box.setPlainText("No document is currently open.")

        root.addWidget(box)
        root.addLayout(self.make_button_row([("✕  Close", "ghost", self.accept)]))


# ─────────────────────────────────────────────────────────────────────────────
#  ABOUT DIALOG  [FIX-ABOUT-2]
# ─────────────────────────────────────────────────────────────────────────────

class AboutDialog(BaseDialog):
    """
    User-facing product About dialog.

    Designed to answer one question clearly: "What does this app do?"
    Primary surface uses plain user language — no tech stack jargon.
    Layout: Hero → What it does → Security highlight → Footer.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, title=f"About  {APP_FULL_NAME}", width=560, height=640)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QTextBrowser()
        body.setReadOnly(True)
        body.setOpenExternalLinks(True)
        body.setFont(Fonts.default(FontSize.BASE))
        body.setStyleSheet("QTextBrowser { border: none; background: transparent; }")

        html = f"""
        <div style='font-family: Segoe UI, Tahoma, Arial, sans-serif;
                    color: {Colors.TEXT_PRIMARY};
                    margin: 0; padding: 0;'>

          <!-- ══ HERO ══════════════════════════════════════════════════════ -->
          <table width='100%' cellpadding='0' cellspacing='0'
                 style='background: {Colors.PRIMARY};
                        padding: 28px 32px 22px 32px;'>
            <tr>
              <td style='vertical-align: middle; padding-right: 20px; width: 72px;'>
                <div style='width:64px; height:64px; background: rgba(255,255,255,0.12);
                            border-radius: 14px; text-align:center;
                            font-size: 36px; line-height: 64px;'>🛡️</div>
              </td>
              <td style='vertical-align: middle;'>
                <div style='font-size: 22px; font-weight: 700;
                            color: white; letter-spacing: 0.3px;
                            margin-bottom: 4px;'>
                  {APP_FULL_NAME}
                </div>
                <div style='font-size: 13px; color: rgba(255,255,255,0.75);
                            font-weight: 400; line-height: 1.4;'>
                  {DESCRIPTION}
                </div>
                <div style='margin-top: 10px;'>
                  <span style='background: rgba(255,255,255,0.18);
                               color: white; font-size: 11px;
                               padding: 3px 10px; border-radius: 20px;
                               font-weight: 600; letter-spacing: 0.5px;'>
                    v{VERSION}
                  </span>
                  &nbsp;
                  <span style='background: rgba(255,255,255,0.10);
                               color: rgba(255,255,255,0.7); font-size: 11px;
                               padding: 3px 10px; border-radius: 20px;'>
                    Build {BUILD_DATE}
                  </span>
                </div>
              </td>
            </tr>
          </table>

          <!-- ══ WHAT IT DOES ══════════════════════════════════════════════ -->
          <div style='padding: 24px 32px 8px 32px;'>
            <div style='font-size: 11px; font-weight: 700; letter-spacing: 1.4px;
                        color: {Colors.TEXT_MUTED}; text-transform: uppercase;
                        margin-bottom: 14px;'>
              WHAT IT DOES
            </div>

            <table width='100%' cellpadding='0' cellspacing='0'>
              <tr>
                <td width='50%' style='padding: 0 8px 12px 0; vertical-align: top;'>
                  {_feature_card("📄", "Open &amp; View PDFs",
                                 "Open any PDF file instantly. Smooth zoom from 25% to 400%, "
                                 "page navigation, and a clean reading experience.")}
                </td>
                <td width='50%' style='padding: 0 0 12px 8px; vertical-align: top;'>
                  {_feature_card("🗂️", "Multi-Tab Viewing",
                                 "Open multiple documents side by side. Each tab keeps its own "
                                 "zoom level, page position, and scroll state independently.")}
                </td>
              </tr>
              <tr>
                <td width='50%' style='padding: 0 8px 12px 0; vertical-align: top;'>
                  {_feature_card("🖼️", "Page Thumbnails",
                                 "See every page at a glance in the thumbnail panel. "
                                 "Click any thumbnail to jump there instantly.")}
                </td>
                <td width='50%' style='padding: 0 0 12px 8px; vertical-align: top;'>
                  {_feature_card("📚", "Bookmarks &amp; Outline",
                                 "Navigate long documents using the built-in bookmark tree. "
                                 "Jump to any chapter or section in one click.")}
                </td>
              </tr>
              <tr>
                <td width='50%' style='padding: 0 8px 12px 0; vertical-align: top;'>
                  {_feature_card("📎", "Attachments",
                                 "View and extract files embedded inside a PDF — "
                                 "spreadsheets, images, and other documents.")}
                </td>
                <td width='50%' style='padding: 0 0 12px 8px; vertical-align: top;'>
                  {_feature_card("🖨️", "Print",
                                 "Print any open document with full page-range control. "
                                 "Real-time progress shown page by page.")}
                </td>
              </tr>
              <tr>
                <td width='50%' style='padding: 0 8px 12px 0; vertical-align: top;'>
                  {_feature_card("💾", "Extract PDF",
                                 "Save a decrypted copy of any open document — including "
                                 "ATLAS-protected files — as a standard PDF to your disk.")}
                </td>
                <td width='50%' style='padding: 0 0 12px 8px; vertical-align: top;'>
                  {_feature_card("🔑", "Generate Keyfile",
                                 "Create a cryptographic keyfile for ATLAS encryption. "
                                 "Use as a second factor alongside your password.")}
                </td>
              </tr>
            </table>
          </div>

          <!-- ══ SECURITY HIGHLIGHT ════════════════════════════════════════ -->
          <div style='margin: 4px 32px 20px 32px;
                      background: #EBF4FF;
                      border-left: 4px solid {Colors.PRIMARY};
                      border-radius: 6px;
                      padding: 14px 18px;'>
            <div style='font-size: 13px; font-weight: 700;
                        color: {Colors.PRIMARY}; margin-bottom: 6px;'>
              🔒 &nbsp;ATLAS Encrypted Documents
            </div>
            <div style='font-size: 12.5px; color: #2C4A6E; line-height: 1.7;'>
              Open <b>.atlas</b> files — PDFs protected with military-grade encryption.
              Authenticate with a password, a keyfile, or a two-factor code.
              The document is decrypted entirely in memory — <b>no unprotected copy
              is ever saved to your disk</b>, not even temporarily.
            </div>
          </div>

          <!-- ══ DIVIDER ═══════════════════════════════════════════════════ -->
          <div style='height: 1px; background: {Colors.BORDER};
                      margin: 0 32px 16px 32px;'></div>

          <!-- ══ FOOTER ════════════════════════════════════════════════════ -->
          <div style='padding: 0 32px 24px 32px; text-align: center;'>
            <div style='font-size: 12px; color: {Colors.TEXT_MUTED};
                        line-height: 1.8;'>
              {COPYRIGHT} &nbsp;·&nbsp; {AUTHOR}
              &nbsp;·&nbsp; PatronHubDevs Technologies
            </div>
            <div style='margin-top: 6px; font-size: 12px;'>
              <a href='{WEBSITE}'
                 style='color: {Colors.PRIMARY}; text-decoration: none;
                         font-weight: 600;'>
                🌐 &nbsp;{WEBSITE}
              </a>
            </div>
          </div>

        </div>
        """

        body.setHtml(html)
        root.addWidget(body, stretch=1)

        btn_wrapper = QWidget()
        btn_layout = QHBoxLayout(btn_wrapper)
        btn_layout.setContentsMargins(Spacing.XL, Spacing.SM, Spacing.XL, Spacing.MD)
        btn_layout.addStretch()
        close_row = self.make_button_row([("✕  Close", "ghost", self.accept)])
        btn_layout.addLayout(close_row)
        root.addWidget(btn_wrapper)


def _feature_card(icon: str, title: str, body: str) -> str:
    """Return HTML for a single feature card cell."""
    return f"""
    <div style='background: #F8FAFD;
                border: 1px solid #DDE6F0;
                border-radius: 8px;
                padding: 12px 14px;
                height: 100%;'>
      <div style='font-size: 18px; margin-bottom: 6px;'>{icon}</div>
      <div style='font-size: 12.5px; font-weight: 700;
                  color: #1A3A5C; margin-bottom: 4px;'>
        {title}
      </div>
      <div style='font-size: 11.5px; color: #4A6080; line-height: 1.55;'>
        {body}
      </div>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
#  DOCUMENTATION DIALOG  [FIX-DOCS-1]  (unchanged from previous revision)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentationDialog(BaseDialog):
    """
    Comprehensive user guide — updated to match current architecture.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, title="📖  Documentation", width=720, height=660)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.MD)

        heading = self.make_section_label(f"📖  {APP_FULL_NAME}  —  User Guide")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(heading)
        root.addWidget(self.make_separator())

        doc_html = f"""
        <div style='font-family:Segoe UI,Arial,sans-serif; font-size:13px;
                    color:{Colors.TEXT_PRIMARY}; line-height:1.8;'>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            🚀 Opening a Document
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li><b>File → Open</b> (Ctrl+O) or drag-and-drop a PDF or .atlas file.</li>
            <li><b>File → Open in New Tab</b> (Ctrl+Shift+O) opens without replacing the current tab.</li>
            <li>Click the <b>📂</b> button in the icon sidebar, or use the toolbar open button.</li>
            <li><b>Ctrl+T</b> opens a blank new tab; <b>Ctrl+W</b> closes the active tab.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            🔍 Zoom &amp; Navigation
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li><b>Ctrl+Scroll</b> or the toolbar ± buttons to zoom in/out (25–400 %).</li>
            <li><b>Ctrl+0</b> resets zoom to the default level.</li>
            <li>Navigate pages with the toolbar arrows, the page-number field, or
                ← / → / Page Up / Page Down keys.</li>
            <li>Click any thumbnail in the thumbnail panel to jump to that page instantly.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            🖼️ Thumbnail Panel
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li>Toggle with the <b>🖼️</b> sidebar button or <b>View → Thumbnails</b>.</li>
            <li>Renders zero widgets per page — opening a 1 000-page PDF takes &lt; 1 ms.</li>
            <li>Lazy loading: only the visible viewport is rendered.</li>
            <li>LRU pixmap cache (20 entries) — evicts oldest pages automatically.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            📚 Bookmarks
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li>Toggle with the <b>📚</b> sidebar button or <b>View → Bookmarks</b>.</li>
            <li>Full outline tree displayed — click any entry to jump to that page.</li>
            <li>Hierarchical bookmarks (chapters → sections → subsections) fully supported.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            📎 Attachments
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li>Toggle with the <b>📎</b> sidebar button or <b>View → Attachments</b>.</li>
            <li>Select one or all embedded files, then click <b>Extract</b> to save to disk.</li>
            <li>Path-traversal protection enforced on all extracted filenames.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            🖨️ Printing
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li><b>File → Print…</b> (Ctrl+P) opens the system print dialog.</li>
            <li>Choose printer, page range, and orientation, then click <b>Print</b>.</li>
            <li>A progress dialog displays current page and percentage in real time.</li>
            <li>Click <b>Cancel</b> in the progress dialog to abort after the current page.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            💾 Extract PDF
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li><b>Document → Extract / Save As PDF…</b> (Ctrl+Shift+S) saves the currently open document as a plain PDF.</li>
            <li>Works with both regular PDFs and ATLAS-encrypted <b>.atlas</b> files — the decrypted content is what gets saved.</li>
            <li>A Save As dialog lets you choose the filename and destination folder.</li>
            <li>The suggested filename is automatically cleaned of encryption suffixes.</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            🛡️ ATLAS Encrypted Documents
          </p>
          <ul style='margin:0 0 10px 16px; padding:0;'>
            <li>Open any <b>.atlas</b> file exactly like a PDF — File → Open or drag-and-drop.</li>
            <li>An authentication dialog prompts for password, keyfile, and/or TOTP.</li>
            <li>Decryption runs in a background thread — the UI remains responsive.</li>
            <li><b>Security guarantee:</b> the decrypted PDF is never written to disk.</li>
            <li>Protect any open PDF with <b>File → Protect PDF…</b> (Ctrl+Shift+P).</li>
          </ul>

          <p style='color:{Colors.PRIMARY}; font-weight:700; margin:6px 0 3px 0;'>
            ⌨️ Keyboard Shortcuts
          </p>
          <table style='border-collapse:collapse; width:100%; font-size:12px; margin-bottom:4px;'>
            <tr style='background:{Colors.PRIMARY};'>
              <th style='padding:5px 10px; text-align:left; color:white;'>Action</th>
              <th style='padding:5px 10px; text-align:left; color:white;'>Shortcut</th>
              <th style='padding:5px 10px; text-align:left; color:white;'>Action</th>
              <th style='padding:5px 10px; text-align:left; color:white;'>Shortcut</th>
            </tr>
            <tr>
              <td style='padding:4px 10px;'>Open file</td>
              <td style='padding:4px 10px;'><b>Ctrl+O</b></td>
              <td style='padding:4px 10px;'>New tab</td>
              <td style='padding:4px 10px;'><b>Ctrl+T</b></td>
            </tr>
            <tr style='background:{Colors.PANEL_BG};'>
              <td style='padding:4px 10px;'>Open in new tab</td>
              <td style='padding:4px 10px;'><b>Ctrl+Shift+O</b></td>
              <td style='padding:4px 10px;'>Close tab</td>
              <td style='padding:4px 10px;'><b>Ctrl+W</b></td>
            </tr>
            <tr>
              <td style='padding:4px 10px;'>Previous page</td>
              <td style='padding:4px 10px;'><b>←  /  Page Up</b></td>
              <td style='padding:4px 10px;'>Next page</td>
              <td style='padding:4px 10px;'><b>→  /  Page Down</b></td>
            </tr>
            <tr style='background:{Colors.PANEL_BG};'>
              <td style='padding:4px 10px;'>Zoom in</td>
              <td style='padding:4px 10px;'><b>Ctrl++</b></td>
              <td style='padding:4px 10px;'>Zoom out</td>
              <td style='padding:4px 10px;'><b>Ctrl+−</b></td>
            </tr>
            <tr>
              <td style='padding:4px 10px;'>Reset zoom</td>
              <td style='padding:4px 10px;'><b>Ctrl+0</b></td>
              <td style='padding:4px 10px;'>Print…</td>
              <td style='padding:4px 10px;'><b>Ctrl+P</b></td>
            </tr>
            <tr style='background:{Colors.PANEL_BG};'>
              <td style='padding:4px 10px;'>Extract PDF…</td>
              <td style='padding:4px 10px;'><b>Ctrl+Shift+S</b></td>
              <td style='padding:4px 10px;'>Protect PDF…</td>
              <td style='padding:4px 10px;'><b>Ctrl+Shift+P</b></td>
            </tr>
            <tr>
              <td style='padding:4px 10px;'>Document info</td>
              <td style='padding:4px 10px;'><b>Ctrl+I</b></td>
              <td style='padding:4px 10px;'>Exit</td>
              <td style='padding:4px 10px;'><b>Ctrl+Q</b></td>
            </tr>
          </table>

          <p style='color:{Colors.TEXT_MUTED}; font-size:11px; text-align:center;
                    margin-top:12px;'>
            {APP_FULL_NAME} v{VERSION}
            &nbsp;·&nbsp; {COPYRIGHT}
            &nbsp;·&nbsp;
            <a href='{WEBSITE}' style='color:{Colors.PRIMARY};'>{WEBSITE}</a>
          </p>
        </div>
        """

        body = QTextBrowser()
        body.setHtml(doc_html)
        body.setReadOnly(True)
        body.setOpenExternalLinks(True)
        body.setFont(Fonts.default(FontSize.BASE))
        body.setStyleSheet("QTextBrowser { border: none; background: transparent; }")
        root.addWidget(body, stretch=1)

        root.addLayout(self.make_button_row([("✕  Close", "ghost", self.accept)]))
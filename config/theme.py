"""
atlas_viewer.config.theme
==========================
Centralized theme configuration: colors, fonts, spacing, and QSS stylesheets.

Design principles
-----------------
* Single source of truth — no hardcoded colors or font names in widget code.
* All QSS generated from named constants (easy global retheming).
* QFont helpers return correctly-configured instances.
* Every public QSS method is documented with which widget it targets.
"""

from __future__ import annotations
try:
    from PySide6.QtGui import QFont
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover — Qt not installed in test env
    QFont = None  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
#  COLOR PALETTE
# ─────────────────────────────────────────────────────────────────────────────

class Colors:
    """Named color constants for the application palette."""

    # Primary brand (Navy Blue)
    PRIMARY           = "#1A5490"
    PRIMARY_HOVER     = "#15507A"
    PRIMARY_PRESSED   = "#0D2B47"
    PRIMARY_LIGHT     = "#EBF3FB"

    # Semantic
    SUCCESS           = "#2E7D32"
    SUCCESS_HOVER     = "#1B5E20"
    SUCCESS_LIGHT     = "#E8F5E9"

    DANGER            = "#C62828"
    DANGER_HOVER      = "#B71C1C"
    DANGER_LIGHT      = "#FFEBEE"

    WARNING           = "#E65100"
    WARNING_LIGHT     = "#FFF3E0"

    INFO              = "#01579B"
    INFO_LIGHT        = "#E1F5FE"

    # Neutrals
    WHITE             = "#FFFFFF"
    SURFACE           = "#F8F9FA"
    SURFACE_CARD      = "#FFFFFF"
    TOOLBAR_BG        = "#F2F3F5"
    SIDEBAR_BG        = "#EBEDEF"
    SIDEBAR_ACTIVE    = "#D8E8F5"
    PANEL_BG          = "#F5F6F7"

    # Borders
    BORDER            = "#D1D5DB"
    BORDER_FOCUS      = "#1A5490"
    BORDER_LIGHT      = "#E9ECEF"

    # Text
    TEXT_PRIMARY      = "#111827"
    TEXT_SECONDARY    = "#4B5563"
    TEXT_MUTED        = "#9CA3AF"
    TEXT_WHITE        = "#FFFFFF"
    TEXT_LINK         = "#1A5490"

    # Thumbnail
    THUMB_BORDER      = "#CBD5E0"
    THUMB_ACTIVE_BG   = "#D8E8F5"
    THUMB_ACTIVE_BORDER = "#1A5490"
    THUMB_HOVER_BG    = "#EBF3FB"


# ─────────────────────────────────────────────────────────────────────────────
#  FONT DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

class FontFamily:
    """Font stack definitions."""

    SANS   = "Segoe UI"
    MONO   = "Consolas"
    SANS_FALLBACK   = "Helvetica Neue, Arial, sans-serif"
    MONO_FALLBACK   = "Courier New, monospace"
    QSS_SANS = f"'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
    QSS_MONO = f"'Consolas', 'Courier New', monospace"


class FontSize:
    """Named font sizes (pixels)."""

    XS   = 10
    SM   = 11
    BASE = 13
    MD   = 14
    LG   = 16
    XL   = 18
    H1   = 22
    H2   = 20
    H3   = 17


class Fonts:
    """QFont factory methods — use these instead of creating QFont inline."""

    @staticmethod
    def default(size: int = FontSize.BASE, bold: bool = False):
        """Standard UI font."""
        if not _QT_AVAILABLE:
            return None
        f = QFont(FontFamily.SANS)
        f.setPixelSize(size)
        f.setBold(bold)
        f.setStyleHint(QFont.StyleHint.SansSerif)
        return f

    @staticmethod
    def heading(size: int = FontSize.LG):
        """Section/dialog heading font."""
        if not _QT_AVAILABLE:
            return None
        f = QFont(FontFamily.SANS)
        f.setPixelSize(size)
        f.setWeight(QFont.Weight.DemiBold)
        f.setStyleHint(QFont.StyleHint.SansSerif)
        return f

    @staticmethod
    def title(size: int = FontSize.H2):
        """Window/dialog title font."""
        if not _QT_AVAILABLE:
            return None
        f = QFont(FontFamily.SANS)
        f.setPixelSize(size)
        f.setWeight(QFont.Weight.Bold)
        f.setStyleHint(QFont.StyleHint.SansSerif)
        return f

    @staticmethod
    def mono(size: int = FontSize.SM):
        """Monospace font for hashes, paths, code."""
        if not _QT_AVAILABLE:
            return None
        f = QFont(FontFamily.MONO)
        f.setPixelSize(size)
        f.setStyleHint(QFont.StyleHint.Monospace)
        return f

    @staticmethod
    def small(bold: bool = False):
        """Caption / helper text."""
        if not _QT_AVAILABLE:
            return None
        f = QFont(FontFamily.SANS)
        f.setPixelSize(FontSize.SM)
        f.setBold(bold)
        return f


# ─────────────────────────────────────────────────────────────────────────────
#  SPACING & SIZING
# ─────────────────────────────────────────────────────────────────────────────

class Spacing:
    """Layout spacing constants (pixels)."""

    XS  = 4
    SM  = 8
    MD  = 12
    LG  = 16
    XL  = 24
    XXL = 32


class Sizing:
    """Widget sizing constants."""

    BUTTON_HEIGHT      = 36
    BUTTON_HEIGHT_SM   = 28
    INPUT_HEIGHT       = 34
    TOOLBAR_HEIGHT     = 52
    STATUSBAR_HEIGHT   = 28
    ICON_SIZE          = 24
    ICON_SIZE_LG       = 32
    BORDER_RADIUS      = 5
    BORDER_RADIUS_LG   = 8


# ─────────────────────────────────────────────────────────────────────────────
#  QSS STYLESHEETS
# ─────────────────────────────────────────────────────────────────────────────

class Styles:
    """
    QSS stylesheet generators.

    All methods are static and return pure QSS strings.
    They reference only named constants from Colors/FontFamily/FontSize.
    """

    @staticmethod
    def global_app() -> str:
        """
        Global application stylesheet applied to QApplication.
        Cascades to all widgets unless overridden locally.
        """
        C = Colors
        FF = FontFamily.QSS_SANS
        FS = FontSize.BASE

        return f"""
        /* ── Reset ─────────────────────────────────────────────────── */
        * {{
            font-family: {FF};
            font-size: {FS}px;
            color: {C.TEXT_PRIMARY};
            outline: none;
            box-sizing: border-box;
        }}

        /* ── App Shell ──────────────────────────────────────────────── */
        QMainWindow, QDialog {{
            background-color: {C.SURFACE};
        }}

        /* ── Menu Bar ───────────────────────────────────────────────── */
        QMenuBar {{
            background-color: {C.PRIMARY};
            color: {C.TEXT_WHITE};
            font-size: {FS}px;
            font-weight: 600;
            padding: 2px 0;
            border-bottom: 2px solid {C.PRIMARY_PRESSED};
        }}
        QMenuBar::item {{
            background: transparent;
            padding: 7px 16px;
        }}
        QMenuBar::item:selected {{ background-color: {C.PRIMARY_HOVER}; }}
        QMenuBar::item:pressed  {{ background-color: {C.PRIMARY_PRESSED}; }}

        /* ── Dropdown Menu ──────────────────────────────────────────── */
        QMenu {{
            background-color: {C.SURFACE_CARD};
            color: {C.TEXT_PRIMARY};
            border: 1px solid {C.BORDER};
            border-radius: 6px;
            padding: 4px 0;
        }}
        QMenu::item {{
            padding: 8px 28px;
            font-size: {FS}px;
        }}
        QMenu::item:selected {{
            background-color: {C.PRIMARY_LIGHT};
            color: {C.PRIMARY};
        }}
        QMenu::separator {{
            height: 1px;
            background: {C.BORDER};
            margin: 4px 14px;
        }}

        /* ── Buttons ────────────────────────────────────────────────── */
        QPushButton {{
            background-color: {C.PRIMARY};
            color: {C.TEXT_WHITE};
            border: 1px solid {C.PRIMARY_HOVER};
            padding: 7px 18px;
            border-radius: {Sizing.BORDER_RADIUS}px;
            font-weight: 600;
            font-size: {FS}px;
            min-height: {Sizing.BUTTON_HEIGHT}px;
        }}
        QPushButton:hover   {{ background-color: {C.PRIMARY_HOVER}; border-color: {C.PRIMARY_PRESSED}; }}
        QPushButton:pressed {{ background-color: {C.PRIMARY_PRESSED}; }}
        QPushButton:disabled {{
            background-color: #C8CDD3;
            border-color: #B0B7C0;
            color: #E8EBF0;
        }}

        /* ── Line Edit ──────────────────────────────────────────────── */
        QLineEdit {{
            border: 1.5px solid {C.BORDER};
            padding: 6px 10px;
            border-radius: {Sizing.BORDER_RADIUS}px;
            background-color: {C.SURFACE_CARD};
            font-size: {FS}px;
            min-height: {Sizing.INPUT_HEIGHT}px;
            selection-background-color: {C.PRIMARY};
            selection-color: {C.TEXT_WHITE};
        }}
        QLineEdit:focus   {{ border-color: {C.BORDER_FOCUS}; }}
        QLineEdit:disabled {{ background-color: #F0F2F4; color: #AAAAAA; }}

        /* ── Text Edit ──────────────────────────────────────────────── */
        QTextEdit, QPlainTextEdit {{
            border: 1.5px solid {C.BORDER};
            border-radius: {Sizing.BORDER_RADIUS}px;
            background-color: {C.SURFACE_CARD};
            font-size: {FS}px;
            padding: 6px;
            selection-background-color: {C.PRIMARY};
            selection-color: {C.TEXT_WHITE};
        }}
        QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {C.BORDER_FOCUS}; }}

        /* ── Labels ─────────────────────────────────────────────────── */
        QLabel {{
            color: {C.TEXT_PRIMARY};
            font-size: {FS}px;
            background: transparent;
        }}

        /* ── GroupBox ───────────────────────────────────────────────── */
        QGroupBox {{
            border: 1.5px solid {C.BORDER};
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 14px;
            font-weight: 700;
            font-size: {FS}px;
            color: {C.PRIMARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            color: {C.PRIMARY};
        }}

        /* ── ComboBox ───────────────────────────────────────────────── */
        QComboBox {{
            border: 1.5px solid {C.BORDER};
            border-radius: {Sizing.BORDER_RADIUS}px;
            padding: 6px 10px;
            background-color: {C.SURFACE_CARD};
            font-size: {FS}px;
            min-height: {Sizing.INPUT_HEIGHT}px;
        }}
        QComboBox:focus {{ border-color: {C.BORDER_FOCUS}; }}
        QComboBox::drop-down {{ border: none; padding-right: 8px; }}

        /* ── CheckBox ───────────────────────────────────────────────── */
        QCheckBox {{
            spacing: 8px;
            font-size: {FS}px;
            color: {C.TEXT_PRIMARY};
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1.5px solid {C.BORDER};
            border-radius: 3px;
            background-color: {C.SURFACE_CARD};
        }}
        QCheckBox::indicator:checked  {{ background-color: {C.PRIMARY}; border-color: {C.PRIMARY}; }}
        QCheckBox::indicator:hover    {{ border-color: {C.PRIMARY}; }}

        /* ── TreeWidget ─────────────────────────────────────────────── */
        QTreeWidget {{
            border: 1px solid {C.BORDER};
            border-radius: 4px;
            background-color: {C.SURFACE_CARD};
            alternate-background-color: #F9FAFB;
            font-size: {FS}px;
            outline: none;
        }}
        QTreeWidget::item {{
            padding: 5px 8px;
            border-radius: 3px;
        }}
        QTreeWidget::item:hover    {{ background-color: {C.PRIMARY_LIGHT}; }}
        QTreeWidget::item:selected {{
            background-color: {C.PRIMARY_LIGHT};
            color: {C.PRIMARY};
            font-weight: 600;
        }}
        QTreeWidget QHeaderView::section {{
            background-color: {C.TOOLBAR_BG};
            border: none;
            border-bottom: 1px solid {C.BORDER};
            padding: 6px 8px;
            font-weight: 700;
            color: {C.TEXT_SECONDARY};
        }}

        /* ── ListView / TableView ───────────────────────────────────── */
        QListWidget, QTableWidget {{
            border: 1px solid {C.BORDER};
            border-radius: 4px;
            background-color: {C.SURFACE_CARD};
            alternate-background-color: #F9FAFB;
            font-size: {FS}px;
            outline: none;
        }}
        QListWidget::item, QTableWidget::item {{
            padding: 5px 8px;
        }}
        QListWidget::item:hover, QTableWidget::item:hover {{
            background-color: {C.PRIMARY_LIGHT};
        }}
        QListWidget::item:selected, QTableWidget::item:selected {{
            background-color: {C.PRIMARY_LIGHT};
            color: {C.PRIMARY};
        }}

        /* ── Splitter ───────────────────────────────────────────────── */
        QSplitter::handle {{
            background-color: {C.BORDER};
        }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical   {{ height: 1px; }}

        /* ── Scroll Bars (Navy System Theme) ───────────────────────── */
        
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:vertical {{
            background: {C.PRIMARY_PRESSED};   /* deep navy */
            min-height: 24px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: {C.PRIMARY};
        }}
        
        QScrollBar::handle:vertical:pressed {{
            background: {C.PRIMARY_HOVER};
        }}
        
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:horizontal {{
            background: {C.PRIMARY_PRESSED};
            min-width: 24px;
            border-radius: 5px;
        }}
        
        QScrollBar::handle:horizontal:hover {{
            background: {C.PRIMARY};
        }}
        
        QScrollBar::handle:horizontal:pressed {{
            background: {C.PRIMARY_HOVER};
        }}
        
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* ── Progress Bar ───────────────────────────────────────────── */
        QProgressBar {{
            border: 1px solid {C.BORDER};
            border-radius: 4px;
            background: #EEEEEE;
            text-align: center;
            font-size: 11px;
            color: {C.TEXT_SECONDARY};
            min-height: 14px;
        }}
        QProgressBar::chunk {{
            background-color: {C.PRIMARY};
            border-radius: 3px;
        }}

        /* ── Tooltip ────────────────────────────────────────────────── */
        QToolTip {{
            background-color: {C.PRIMARY_PRESSED};
            color: {C.TEXT_WHITE};
            border: none;
            padding: 5px 9px;
            border-radius: 4px;
            font-size: 12px;
        }}

        /* ── Status Bar ─────────────────────────────────────────────── */
        QStatusBar {{
            background-color: {C.TOOLBAR_BG};
            border-top: 1px solid {C.BORDER};
            font-size: 12px;
            color: {C.TEXT_SECONDARY};
            padding: 2px 10px;
        }}
        """

    @staticmethod
    def btn_primary() -> str:
        C = Colors
        return f"""
        QPushButton {{
            background-color: {C.PRIMARY}; color: {C.TEXT_WHITE};
            border: 1px solid {C.PRIMARY_HOVER}; border-radius: {Sizing.BORDER_RADIUS}px;
            padding: 7px 18px; font-weight: 700; font-size: {FontSize.BASE}px;
            min-height: {Sizing.BUTTON_HEIGHT}px;
        }}
        QPushButton:hover   {{ background-color: {C.PRIMARY_HOVER}; border-color: {C.PRIMARY_PRESSED}; }}
        QPushButton:pressed {{ background-color: {C.PRIMARY_PRESSED}; }}
        QPushButton:disabled {{ background-color: #C8CDD3; border-color: #B0B7C0; color: #E8EBF0; }}
        """

    @staticmethod
    def btn_danger() -> str:
        C = Colors
        return f"""
        QPushButton {{
            background-color: {C.DANGER}; color: {C.TEXT_WHITE};
            border: 1px solid {C.DANGER_HOVER}; border-radius: {Sizing.BORDER_RADIUS}px;
            padding: 7px 18px; font-weight: 700; font-size: {FontSize.BASE}px;
            min-height: {Sizing.BUTTON_HEIGHT}px;
        }}
        QPushButton:hover   {{ background-color: {C.DANGER_HOVER}; }}
        QPushButton:pressed {{ background-color: #7F0000; }}
        """

    @staticmethod
    def btn_success() -> str:
        C = Colors
        return f"""
        QPushButton {{
            background-color: {C.SUCCESS}; color: {C.TEXT_WHITE};
            border: 1px solid {C.SUCCESS_HOVER}; border-radius: {Sizing.BORDER_RADIUS}px;
            padding: 7px 18px; font-weight: 700; font-size: {FontSize.BASE}px;
            min-height: {Sizing.BUTTON_HEIGHT}px;
        }}
        QPushButton:hover   {{ background-color: {C.SUCCESS_HOVER}; }}
        QPushButton:pressed {{ background-color: #0A3D1A; }}
        """

    @staticmethod
    def btn_ghost() -> str:
        C = Colors
        return f"""
        QPushButton {{
            background-color: {C.SURFACE_CARD}; color: {C.PRIMARY};
            border: 1.5px solid {C.PRIMARY}; border-radius: {Sizing.BORDER_RADIUS}px;
            padding: 7px 18px; font-weight: 600; font-size: {FontSize.BASE}px;
            min-height: {Sizing.BUTTON_HEIGHT}px;
        }}
        QPushButton:hover   {{ background-color: {C.PRIMARY_LIGHT}; }}
        QPushButton:pressed {{ background-color: #D0E8F5; }}
        """

    @staticmethod
    def btn_flat() -> str:
        """Flat toolbar button — white background, hover turns primary."""
        C = Colors
        return f"""
        QPushButton {{
            background-color: {C.SURFACE_CARD}; color: {C.TEXT_PRIMARY};
            border: 1px solid {C.BORDER}; border-radius: 4px;
            padding: 4px 10px; font-weight: 600; font-size: {FontSize.BASE}px;
        }}
        QPushButton:hover   {{ background-color: {C.PRIMARY}; color: {C.TEXT_WHITE}; border-color: {C.PRIMARY}; }}
        QPushButton:pressed {{ background-color: {C.PRIMARY_HOVER}; color: {C.TEXT_WHITE}; }}
        QPushButton:disabled {{ background-color: #F0F2F4; color: #AAAAAA; border-color: #E0E0E0; }}
        """

    @staticmethod
    def sidebar_btn() -> str:
        C = Colors
        return f"""
        QPushButton {{
            background-color: transparent; color: {C.TEXT_PRIMARY};
            border: none; border-radius: 5px;
            padding: 8px 10px; font-size: {FontSize.BASE}px; font-weight: 600;
            text-align: left;
        }}
        QPushButton:hover   {{ background-color: {C.PRIMARY_LIGHT}; color: {C.PRIMARY}; }}
        QPushButton:pressed {{ background-color: #D0E8F5; }}
        QPushButton[active="true"] {{
            background-color: {C.SIDEBAR_ACTIVE}; color: {C.PRIMARY}; font-weight: 700;
        }}
        """

    @staticmethod
    def slider() -> str:
        C = Colors
        return f"""
        QSlider::groove:horizontal {{
            background-color: {C.BORDER}; height: 5px; border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background-color: {C.PRIMARY}; width: 14px; height: 14px;
            margin: -5px 0; border-radius: 7px;
            border: 1px solid {C.PRIMARY_HOVER};
        }}
        QSlider::handle:horizontal:hover {{ background-color: {C.PRIMARY_HOVER}; }}
        QSlider::sub-page:horizontal {{ background-color: {C.PRIMARY}; border-radius: 2px; }}
        """

    @staticmethod
    def panel_frame() -> str:
        C = Colors
        return f"background-color: {C.PANEL_BG}; border-right: 1px solid {C.BORDER};"

    @staticmethod
    def toolbar_frame() -> str:
        C = Colors
        return f"background-color: {C.TOOLBAR_BG}; border-bottom: 1px solid {C.BORDER};"

    @staticmethod
    def card() -> str:
        C = Colors
        return (
            f"background-color: {C.SURFACE_CARD}; "
            f"border: 1px solid {C.BORDER}; "
            f"border-radius: {Sizing.BORDER_RADIUS_LG}px;"
        )

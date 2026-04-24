"""
atlas_viewer.utils.ui_helpers
==============================
Reusable UI utility functions — stateless Qt helpers with no business logic.

All functions guard against headless (no-Qt) environments so they can be
imported freely in test environments that don't instantiate a QApplication.

Security Notes
--------------
* :func:`sanitize_filename` enforces a strict allowlist character set and
  strips null bytes, leading dots, and directory separators.
* :func:`center_window` clamps to screen bounds — safe for multi-monitor
  setups including those with negative-coordinate secondary displays.
"""

from __future__ import annotations

from typing import Optional

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QDialog, QFrame, QLabel, QWidget
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover — headless test environment
    _QT_AVAILABLE = False
    QWidget = object  # type: ignore[assignment,misc]

from config.theme import Colors, Fonts
from config.settings import settings


def center_window(window, parent=None) -> None:
    """
    Center a window on its parent or on the primary screen.

    If a parent is provided the window is centered over it.
    If not, it is centered on the primary screen's available geometry.
    The resulting geometry is clamped to remain fully on-screen.

    Args:
        window: The widget to center (QMainWindow, QDialog, etc.).
        parent: Optional parent widget to center over.
    """
    if not _QT_AVAILABLE:
        return
    screen = QGuiApplication.primaryScreen().availableGeometry()
    geo = window.frameGeometry()

    if parent is not None:
        geo.moveCenter(parent.frameGeometry().center())
    else:
        geo.moveCenter(screen.center())

    # Clamp to screen bounds (handles multi-monitor negative coordinates)
    if geo.left()   < screen.left():   geo.moveLeft(screen.left())
    if geo.top()    < screen.top():    geo.moveTop(screen.top())
    if geo.right()  > screen.right():  geo.moveRight(screen.right())
    if geo.bottom() > screen.bottom(): geo.moveBottom(screen.bottom())

    window.move(geo.topLeft())


def make_h_separator():
    """Return a styled 1 px horizontal divider line (QFrame)."""
    if not _QT_AVAILABLE:
        return None
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {Colors.BORDER}; border: none;")
    return sep


def make_v_separator():
    """Return a styled 1 px vertical divider line (QFrame)."""
    if not _QT_AVAILABLE:
        return None
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFixedWidth(1)
    sep.setStyleSheet(f"background-color: {Colors.BORDER}; border: none;")
    return sep


def make_label(
    text: str,
    bold: bool = False,
    color: Optional[str] = None,
    size: Optional[int] = None,
):
    """
    Create a themed QLabel.

    Args:
        text:  Label content.
        bold:  Apply bold weight.
        color: CSS color override.
        size:  Font pixel size override.

    Returns:
        QLabel: Styled label, or ``None`` in headless environments.
    """
    if not _QT_AVAILABLE:
        return None
    lbl = QLabel(text)
    font = Fonts.default(size or 13, bold=bold)
    if font:
        lbl.setFont(font)
    style_parts = ["background: transparent;"]
    if color:
        style_parts.append(f"color: {color};")
    lbl.setStyleSheet(" ".join(style_parts))
    return lbl


def make_badge(text: str, color: str, bg: str):
    """
    Create a small colored badge label (e.g. for status indicators).

    Args:
        text:  Badge text content.
        color: Text color (CSS string).
        bg:    Background color (CSS string).

    Returns:
        QLabel: Styled badge widget, or ``None`` in headless environments.
    """
    if not _QT_AVAILABLE:
        return None
    lbl = QLabel(text)
    font = Fonts.small(bold=True)
    if font:
        lbl.setFont(font)
    lbl.setStyleSheet(
        f"color: {color}; background-color: {bg}; "
        f"padding: 3px 8px; border-radius: 4px; font-weight: 700;"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def human_readable_size(size_bytes: int) -> str:
    """
    Convert a byte count to a human-readable string.

    Args:
        size_bytes: Size in bytes (non-negative).

    Returns:
        str: e.g. ``"1.2 MB"``, ``"345 KB"``, ``"88 B"``.

    Example::

        human_readable_size(1_048_576)  # "1.0 MB"
        human_readable_size(0)          # "0 B"
    """
    if size_bytes <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


def sanitize_filename(
    name: str,
    allowed: Optional[str] = None,
    max_length: Optional[int] = None,
) -> str:
    """
    Sanitize a filename to prevent path traversal and invalid characters.

    Security measures applied in order:

    1. Strip directory separators (``/`` and ``\\``).
    2. Remove null bytes (``\\x00``).
    3. Strip leading dots (prevents hidden-file creation).
    4. Restrict to the *allowed* character set (default: alphanumeric + ``-_. ``).
    5. Trim whitespace.
    6. Enforce *max_length* (default from ``settings.security.max_filename_length``).
    7. Fall back to ``"attachment"`` if result is empty.

    Args:
        name:       Raw filename (may come from untrusted PDF metadata).
        allowed:    Allowed character string.  Defaults to the safe
                    alphanumeric set from :class:`~atlas_viewer.config.settings.AttachmentConfig`.
        max_length: Maximum allowed length.  Defaults to
                    ``settings.security.max_filename_length``.

    Returns:
        str: Sanitized filename safe for use with :func:`open`.

    Example::

        sanitize_filename("../../etc/passwd")  # "etcpasswd"
        sanitize_filename("report.pdf")        # "report.pdf"
        sanitize_filename("")                  # "attachment"
    """
    if allowed is None:
        allowed = settings.attachments.safe_filename_chars
    if max_length is None:
        max_length = settings.security.max_filename_length

    # Step 1+2: strip separators and null bytes
    cleaned = name.replace("/", "").replace("\\", "").replace("\x00", "")
    # Step 3: strip leading dots
    cleaned = cleaned.lstrip(".")
    # Step 4: allowlist filter
    cleaned = "".join(c for c in cleaned if c in allowed).strip()
    # Step 5+6: trim length
    cleaned = cleaned[:max_length]
    return cleaned or "attachment"

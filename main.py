# main.py — ATLAS Opener (stripped build — open-only, no print/protect/generate)
#
# Boot Sequence (mandatory order):
#   1. Nuitka extraction path fix  (env var, must be first)
#   2. Qt high-DPI env vars        (must precede QApplication)
#   3. Logging setup
#   4. PluginKernel.initialize()   (BEFORE any DocumentService use)
#   5. QApplication construction
#   6. MainWindow construction + show

from __future__ import annotations

import os
import sys
import pathlib

# main.py — first two lines after __future__
from config import configure_logging
configure_logging(log_file="atlas_viewer.log")  # omit log_file if you don't want a file


# ── Step 1: Nuitka onefile — set PyMuPDF extraction path ─────────────────
if getattr(sys, "__compiled__", False) or "nuitka" in sys.version.lower():
    _bundle_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault(
        "PYMUPDF_MUPDF_DIR",
        str(_bundle_dir / "pymupdf"),
    )


# ── Step 2: Qt high-DPI env vars ─────────────────────────────────────────
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")


# ── Step 3: Logging ───────────────────────────────────────────────────────
from utils.logging_setup import setup_logging  # noqa: E402

setup_logging()

import logging
_log = logging.getLogger(__name__)


# ── Step 4: Plugin Kernel ─────────────────────────────────────────────────
from core.plugin_kernel import PluginKernel, PluginInitializationError  # noqa: E402

try:
    PluginKernel.initialize()
except PluginInitializationError as _pie:
    _log.critical("PluginKernel initialization failed: %s", _pie, exc_info=True)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        _app = QApplication(sys.argv)
        _mb = QMessageBox()
        _mb.setWindowTitle("ATLAS Opener — Fatal Error")
        _mb.setText(
            "<b>Engine initialization failed.</b><br><br>"
            f"{_pie}<br><br>"
            "The application cannot start.  Check the log file for details."
        )
        _mb.setIcon(QMessageBox.Icon.Critical)
        _mb.exec()
    except Exception:
        print(f"\nFATAL: PluginKernel initialization failed:\n{_pie}\n", file=sys.stderr)
    sys.exit(1)

_log.info("PluginKernel initialized.  Engines: %s", PluginKernel.list_engines())


# ── Step 5 + 6: Qt application + main window ─────────────────────────────
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt              # noqa: E402
from ui.main_window import MainWindow      # noqa: E402


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ATLAS Opener")
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    window = MainWindow()
    window.show()

    # Support file-association / CLI open: atlas_opener.exe document.atlas
    if len(sys.argv) > 1:
        from PySide6.QtCore import QTimer
        path = sys.argv[1]
        QTimer.singleShot(0, lambda: window._load_document(path))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

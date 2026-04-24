"""
atlas_viewer.utils.logging_setup
==================================
Crash-resilient structured logging for Nuitka onefile Windows builds.

Key hardening changes vs original:
-----------------------------------
1. Log file resolves to EXE directory (not CWD).
   In onefile mode CWD is undefined; writing to CWD silently fails or
   creates the log in the TEMP extraction dir which is deleted on exit.

2. Log directory is created with exist_ok=True before opening the handler.
   Nuitka onefile extracts to TEMP which may not persist the log dir.

3. StreamHandler is suppressed when the console is hidden to avoid
   Windows "write to closed handle" errors in GUI-only builds.

4. Exception in logging setup is non-fatal and fully reported.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from config.settings import settings  # Static top-level import for Nuitka


_FILE_FORMAT    = "%(asctime)s  [%(levelname)-8s]  %(name)-32s  %(message)s"
_CONSOLE_FORMAT = "%(asctime)s  [%(levelname)-8s]  %(name)s: %(message)s"
_DATE_FORMAT    = "%Y-%m-%d %H:%M:%S"

_INITIALIZED = False

_PATH_PATTERN = re.compile(
    r'(?:[A-Za-z]:[\\/]|\/)[^\s,;"\'\\)]+',
    re.UNICODE,
)


class _PathRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _PATH_PATTERN.sub(lambda m: Path(m.group()).name, record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    _PATH_PATTERN.sub(lambda m: Path(m.group()).name, str(a))
                    if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def _resolve_log_path(log_file: str) -> Path:
    """
    Resolve the log file path to the EXE directory in frozen mode,
    or the project root in source mode.

    NEVER uses CWD as the base — CWD is unreliable in onefile builds.
    """
    p = Path(log_file)
    if p.is_absolute():
        return p

    # In frozen mode: write next to the exe so users can find it
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        # Source mode: project root (up from utils/ -> project root)
        base = Path(__file__).resolve().parent.parent

    return base / p


def setup_logging(log_file: str | None = None, level: str | None = None) -> None:
    """
    Initialize application-wide logging. Idempotent — safe to call multiple times.

    Args:
        log_file: Path to the log file. Defaults to settings value.
        level:    Log level string. Defaults to settings value.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    log_path    = _resolve_log_path(log_file or settings.logging.log_file)
    log_level   = level or settings.logging.log_level
    numeric_lvl = getattr(logging, log_level.upper(), logging.INFO)
    redact      = settings.logging.redact_paths

    root = logging.getLogger()
    root.setLevel(numeric_lvl)

    redact_filter = _PathRedactFilter() if redact else None

    # ── Rotating file handler ──────────────────────────────────────────
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=settings.logging.max_bytes,
            backupCount=settings.logging.backup_count,
            encoding="utf-8",
        )
        fh.setLevel(numeric_lvl)
        fh.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
        if redact_filter:
            fh.addFilter(redact_filter)
        root.addHandler(fh)
    except OSError as exc:
        print(f"[atlas_viewer] WARNING: Cannot create log file '{log_path}': {exc}",
              file=sys.stderr)

    # ── Console handler (suppressed in frozen GUI-only mode) ───────────
    # In Nuitka onefile with --windows-console-mode=disable, writing to
    # stderr raises a "write to closed file" error on some Windows versions.
    # Only add StreamHandler when a console is actually attached.
    _has_console = _console_is_attached()
    if _has_console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(numeric_lvl)
        ch.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT))
        if redact_filter:
            ch.addFilter(redact_filter)
        root.addHandler(ch)

    _INITIALIZED = True


def _console_is_attached() -> bool:
    """
    Return True if a console window is attached to this process.

    In Nuitka onefile with --windows-console-mode=disable, there is no
    console and sys.stderr.fileno() raises UnsupportedOperation or returns -1.
    """
    if not getattr(sys, "frozen", False):
        return True  # Source mode always has a console
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleWindow() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def get_logger(name: str) -> logging.Logger:
    if not _INITIALIZED:
        setup_logging()
    return logging.getLogger(name)


@contextmanager
def perf_timer(logger: logging.Logger, operation: str) -> Generator[None, None, None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.debug("%s completed in %.3fs", operation, elapsed)

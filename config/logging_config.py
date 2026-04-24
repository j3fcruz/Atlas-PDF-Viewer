"""
atlas_viewer.logging_config
===========================
Call configure_logging() once at the top of main.py before anything else.

Console output levels after this config:
  - atlas_viewer.security.auth  → ERROR only  (suppresses INPUT_VALIDATION warnings)
  - core.atlas_decrypt_worker   → ERROR only  (suppresses auth failure warnings)
  - everything else             → INFO+
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


def configure_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> None:
    """
    Configure application-wide logging.

    Args:
        level:    Root log level for console output (default INFO).
        log_file: Optional path to write full DEBUG log to disk.
                  File handler always logs at DEBUG regardless of console level.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # capture everything; handlers filter

    fmt = logging.Formatter(
        "%(asctime)s  [%(levelname)-8s]  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ───────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # ── Suppress noisy sub-loggers on console ─────────────────────────────
    # Security audit events are structured JSON for SIEM ingestion —
    # they're not actionable console noise during normal operation.
    logging.getLogger("atlas_viewer.security.auth").setLevel(logging.ERROR)

    # Auth failures are already shown to the user via QMessageBox.
    # The WARNING log in the worker is redundant on console.
    logging.getLogger("core.atlas_decrypt_worker").setLevel(logging.ERROR)

    # ── Optional file handler (full DEBUG, all loggers) ───────────────────
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        # File gets everything — do NOT suppress sub-loggers for file output
        logging.getLogger("atlas_viewer.security.auth").addHandler(fh)
        logging.getLogger("core.atlas_decrypt_worker").addHandler(fh)
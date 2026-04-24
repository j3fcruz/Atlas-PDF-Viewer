"""
atlas_viewer.ui.dialogs.auth_error_handler
===========================================
Hybrid Security Mode (Option B) — Dual-layer authentication error architecture.

Design Principles
-----------------
This module implements a strict separation between what the *user sees* and
what the *audit trail records*. The goal is to suppress oracle behaviour —
an attacker who probes authentication paths must never learn which specific
factor rejected their attempt, what internal state was reached, or whether
validation failed early or late.

Layer 1 — UI Surface (anti-enumeration)
    Every authentication or credential-validation failure renders a single
    identical message: "Authentication failed. Please try again."  No factor
    name, no exception text, no hint about which check failed.

Layer 2 — Internal Audit Log (developer / SOC visibility)
    A structured record is written to the application's rotating log via the
    existing ``utils.logging_setup`` infrastructure.  This record includes:
      - ISO-8601 timestamp (UTC)
      - Failed factor type (password / keyfile / totp) or 'multi' for
        compound failures
      - Auth context (open_atlas / protect_wizard / keyfile_select)
      - Exception class name (never the message, which may echo user input)
      - A monotonically incrementing event counter for correlation

    The log is *never* surfaced in the UI.  Log files inherit the
    ``_PathRedactFilter`` already wired in ``utils.logging_setup``.

Extension Hooks
---------------
``AuthErrorHandler`` exposes two hook slots intended for future integration
with rate-limiting and intrusion-detection subsystems:

    AuthErrorHandler.on_auth_failure_hook
        Called with (context: str, factor: str, exc_type: str | None).
        Wire up your rate-limiter or IDS client here.

    AuthErrorHandler.on_input_validation_hook
        Called with (context: str, factor: str).
        Useful for distinguishing client-side input errors (empty field,
        wrong format) from server-side decryption failures.

Both hooks default to no-ops and are intentionally *not* async — keep them
fast and non-blocking.

Usage
-----
Replace every ``QMessageBox.warning/critical`` in authentication flows with
the appropriate method on this module's singleton ``auth_error_handler``:

    from ui.dialogs.auth_error_handler import auth_error_handler

    # Input validation failure (missing / malformed field)
    auth_error_handler.show_input_error(
        parent=self,
        context="open_atlas",
        factor="password",
        exc=None,
    )

    # Cryptographic / decryption failure
    auth_error_handler.show_auth_failure(
        parent=self,
        context="open_atlas",
        factor="totp",
        exc=decryption_exc,
    )

    # Non-auth error where it is safe to show a real message (e.g. keyfile I/O)
    auth_error_handler.show_safe_error(parent=self, title="Error", message=str(exc))
"""

from __future__ import annotations

import itertools
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox, QWidget

if TYPE_CHECKING:
    pass

# ── Module-level logger ────────────────────────────────────────────────────────
# Name it under the dialogs namespace so it inherits the root handler chain
# configured by utils.logging_setup (rotating file + optional stream).
_log = logging.getLogger("atlas_viewer.auth")

# ── Monotonic event counter (correlation aid, not a rate limiter) ──────────────
_event_counter = itertools.count(start=1)

# ── Sentinel used when no exception is available ──────────────────────────────
_NO_EXC = "n/a"

# ── Generic user-facing string — the ONLY message shown for auth/input errors ─
_GENERIC_AUTH_MSG = "Authentication failed. Please try again."

# ── Factor display names used in log records (never in UI) ────────────────────
_FACTOR_LABELS: dict[str, str] = {
    "password": "password",
    "keyfile":  "keyfile",
    "totp":     "totp",
    "multi":    "multi-factor",
    "unknown":  "unknown",
}


class AuthErrorHandler:
    """
    Singleton coordinator for secure authentication error presentation.

    Thread-safety note: Qt UI calls must happen on the main thread.  Log calls
    are thread-safe via the ``logging`` module's built-in locks.  Do not call
    ``show_*`` methods from worker threads.
    """

    # ── Extension hooks (replace with your rate-limiter / IDS client) ─────────
    on_auth_failure_hook:     Callable[[str, str, str | None], None] = staticmethod(lambda ctx, factor, exc_type: None)
    on_input_validation_hook: Callable[[str, str], None]             = staticmethod(lambda ctx, factor: None)

    # ── Public API ─────────────────────────────────────────────────────────────

    def show_auth_failure(
        self,
        parent:  Optional[QWidget],
        context: str,
        factor:  str,
        exc:     Optional[BaseException] = None,
    ) -> None:
        """
        Handle a cryptographic authentication failure.

        Logs the structured audit record and shows the generic UI message.
        Call this when a decryption, MAC verification, or TOTP check fails.

        Args:
            parent:  Parent widget for the dialog (may be None).
            context: Caller identifier, e.g. ``"open_atlas"``.
            factor:  Which factor failed: ``"password"`` / ``"keyfile"`` /
                     ``"totp"`` / ``"multi"`` / ``"unknown"``.
            exc:     The caught exception, if any.  Only its *type name* is
                     logged — the message is intentionally discarded to prevent
                     accidental leakage of crypto internals.
        """
        self._log_event("AUTH_FAILURE", context, factor, exc)
        self.on_auth_failure_hook(context, factor, type(exc).__name__ if exc else None)
        self._show_generic_dialog(parent)

    def show_input_error(
        self,
        parent:  Optional[QWidget],
        context: str,
        factor:  str,
        exc:     Optional[BaseException] = None,
    ) -> None:
        """
        Handle a client-side input validation error.

        Behaves identically to ``show_auth_failure`` from the user's
        perspective.  Internally logged as INPUT_VALIDATION so rate-limiting
        hooks can distinguish between user-input mistakes and actual probe
        attempts.

        Args:
            parent:  Parent widget for the dialog (may be None).
            context: Caller identifier.
            factor:  Which factor had bad input.
            exc:     The caught exception, if any.
        """
        self._log_event("INPUT_VALIDATION", context, factor, exc)
        self.on_input_validation_hook(context, factor)
        self._show_generic_dialog(parent)

    def show_safe_error(
        self,
        parent:  Optional[QWidget],
        title:   str,
        message: str,
    ) -> None:
        """
        Show an error that is **safe** to display verbatim to the user.

        Use *only* for non-authentication failures where the message does not
        reveal internal validation state:
          - Keyfile write failures (I/O error from the OS)
          - Missing dependency errors (pip install …)
          - File-save dialog cancellations
          - QR-code generation errors

        Do NOT use for any failure that occurs inside a credential check.

        Args:
            parent:  Parent widget.
            title:   Dialog title.
            message: Human-readable error text (must not contain secrets).
        """
        _log.info("SAFE_ERROR | title=%r | message=%r", title, message[:120])
        QMessageBox.critical(parent, title, message)

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _show_generic_dialog(parent: Optional[QWidget]) -> None:
        """Display the single, invariant authentication failure message."""
        QMessageBox.warning(parent, "Authentication Failed", _GENERIC_AUTH_MSG)

    @staticmethod
    def _log_event(
        event_type: str,
        context:    str,
        factor:     str,
        exc:        Optional[BaseException],
    ) -> None:
        """
        Emit a structured audit log record.

        Format (tab-separated for easy grep/awk parsing):
            ATLAS_AUTH | event_id=N | event=TYPE | ts=ISO | ctx=CTX | factor=F | exc=CLASSNAME
        """
        event_id  = next(_event_counter)
        ts        = datetime.now(timezone.utc).isoformat(timespec="seconds")
        exc_type  = type(exc).__name__ if exc else _NO_EXC
        factor_lbl = _FACTOR_LABELS.get(factor, factor)

        _log.warning(
            "ATLAS_AUTH | event_id=%d | event=%s | ts=%s | ctx=%s | factor=%s | exc=%s",
            event_id, event_type, ts, context, factor_lbl, exc_type,
        )


# ── Module-level singleton — import this, do not instantiate ──────────────────
auth_error_handler = AuthErrorHandler()
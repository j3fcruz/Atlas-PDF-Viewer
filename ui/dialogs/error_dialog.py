"""
atlas_viewer.ui.dialogs.error_dialog
=====================================
Production-grade secure ErrorDialog — Hybrid Security Mode (Option B, v2).

Architecture Overview
----------------------
This module is a **security boundary enforcement mechanism** dressed as UI.
It implements a strict two-layer model:

    Layer A — User Surface (anti-enumeration)
        Every authentication or credential-validation failure renders one
        invariant message:  "Authentication failed. Please try again."
        The dialog title, icon, size, button layout, and display timing are
        all fixed — no variance that could be exploited for oracle attacks.

    Layer B — Developer / Audit Surface (structured logging)
        A JSON-serialisable log record is written to the application's
        rotating log file for every security event.  The record includes:
          • ISO-8601 UTC timestamp
          • Monotonic event ID (log correlation)
          • Event type  (AUTH_FAILURE | INPUT_VALIDATION | SAFE_ERROR)
          • Auth context (open_atlas / protect_wizard / keyfile_select / …)
          • Failed factor(s) — password / keyfile / totp / multi / unknown
          • Exception *class name* only (message intentionally discarded)
          • Full stack trace (file only — truncated to remove host paths)
          • Factors present at the time of failure (list, no values)
        This record is NEVER exposed in the UI.

Timing-Attack Resistance
-------------------------
Every auth-path dialog display is preceded by a randomised delay drawn from
`[_JITTER_MIN_MS, _JITTER_MAX_MS]` (default 100 – 600 ms).  The delay runs
inside a non-blocking `QTimer.singleShot` so the main thread's event loop
stays responsive.  This prevents response-time correlation between failure
types (e.g. a missing-password fast-path vs a failed AES-GCM tag slow-path).

Rate-Limiting / Soft Lockout
------------------------------
`_RateLimiter` tracks consecutive auth failures per session.  After
`_LOCKOUT_THRESHOLD` failures (default 5) a generic "too many attempts"
cooldown banner is shown inside the dialog for `_LOCKOUT_COOLDOWN_S` seconds
(default 30).  No specific lockout reason is ever disclosed.

Keyword Scrubbing Safety Net
-----------------------------
`_scrub_message()` scans any caller-supplied message for a list of
security-sensitive keywords (password, keyfile, totp, decryption,
InvalidTag, …).  If any match, the message is silently replaced with the
generic auth failure string before it can reach the UI.  This catches
call-site mistakes where a developer accidentally passes a raw exception
message to the wrong method.

Integration Example
--------------------
    from ui.dialogs.error_dialog import ErrorDialog

    # Auth-path failure (decryption, MAC, TOTP verify, missing factor, …)
    try:
        factors = service.open_atlas(path, factors)
    except Exception as exc:
        ErrorDialog.show_auth_failure(
            parent=self,
            context="open_atlas",
            factors_present=list(self.factors.keys()),
            exc=exc,
        )

    # Safe non-auth error (I/O, missing dep, OS error)
    try:
        svc.generate_keyfile(path)
    except Exception as exc:
        ErrorDialog.show_safe_error(parent=self, title="Error", message=str(exc))

    # Input validation failure (empty field, wrong format)
    if not password:
        ErrorDialog.show_input_error(
            parent=self, context="open_atlas", factor="password"
        )
"""

from __future__ import annotations

import itertools
import json
import logging
import random
import traceback
import re
import time
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.theme import Colors, FontSize, Fonts, Spacing, Styles
from ui.dialogs.base_dialog import BaseDialog


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# The ONE and ONLY user-facing authentication failure message.
_GENERIC_AUTH_MSG: str = "Authentication failed. Please try again."

# Dialog presentation constants — ALL auth failure dialogs are identical.
_DIALOG_TITLE:  str = "Access Error"
_DIALOG_WIDTH:  int = 440
_DIALOG_HEIGHT: int = 220

# Timing jitter window (milliseconds). Randomised per show_auth_failure() call.
# Prevents response-time correlation between fast paths (missing field) and
# slow paths (failed AES-GCM tag verification).
_JITTER_MIN_MS: int = 100
_JITTER_MAX_MS: int = 600

# Rate-limiter thresholds (session-scoped).
_LOCKOUT_THRESHOLD: int = 5        # failures before soft lockout
_LOCKOUT_COOLDOWN_S: int = 30      # cooldown duration in seconds

# Keyword scrubbing — if any of these appear in a caller-supplied message,
# the message is silently replaced with the generic auth string.
# Case-insensitive matching.
_SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "password",
    "keyfile",
    "totp",
    "decryption",
    "decrypt",
    "invalidtag",
    "invalid tag",
    "aes",
    "gcm",
    "hkdf",
    "pbkdf",
    "hmac",
    "mac",
    "cipher",
    "secret",
    "token",
    "base32",
    "authentication",
    "credential",
    "factor",
    "wrong",
    "incorrect",
    "mismatch",
)

_SENSITIVE_PATTERN: re.Pattern = re.compile(
    "|".join(re.escape(kw) for kw in _SENSITIVE_KEYWORDS),
    re.IGNORECASE,
)

# Structured audit logger — writes to the rotating file handler set up by
# utils.logging_setup.  Never connected to the UI.
_log = logging.getLogger("atlas_viewer.security.auth")

# Monotonic event counter for log correlation.
_event_counter = itertools.count(start=1)


# ─────────────────────────────────────────────────────────────────────────────
#  KEYWORD SCRUBBING
# ─────────────────────────────────────────────────────────────────────────────

def _scrub_message(message: str) -> str:
    """
    Return the generic auth message if `message` contains any sensitive keyword.

    This is a defence-in-depth safety net for call-site mistakes.  A developer
    who accidentally calls ``show_safe_error(message=str(exc))`` when ``exc``
    is a DecryptionError will have the message silently neutralised here rather
    than leaked to the UI.

    Args:
        message: Candidate user-facing message string.

    Returns:
        The original message if no sensitive keyword is found, otherwise
        ``_GENERIC_AUTH_MSG``.
    """
    if _SENSITIVE_PATTERN.search(message):
        _log.warning(
            "SCRUB | Sensitive keyword detected in caller-supplied message. "
            "Message suppressed and replaced with generic auth string."
        )
        return _GENERIC_AUTH_MSG
    return message


# ─────────────────────────────────────────────────────────────────────────────
#  RATE LIMITER
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    """
    Session-scoped soft rate-limiter for authentication failures.

    Tracks consecutive failures and enforces a cooldown window after
    ``_LOCKOUT_THRESHOLD`` failures.  The cooldown state is visible to the
    dialog presenter but the *reason* for cooldown is never disclosed to the
    user — only a generic "please wait" message is shown.

    This class is intentionally simple (in-memory, single-process).  For a
    multi-process or persistent rate-limiter, replace this with an IDS hook
    via ``ErrorDialog.on_auth_failure_hook``.
    """

    def __init__(self) -> None:
        self._failure_count: int = 0
        self._cooldown_until: float = 0.0   # epoch seconds

    def record_failure(self) -> None:
        """Increment failure counter."""
        self._failure_count += 1

    def is_locked_out(self) -> bool:
        """Return True if currently in cooldown."""
        return time.monotonic() < self._cooldown_until

    def seconds_remaining(self) -> int:
        """Return whole seconds remaining in cooldown (0 if not locked out)."""
        remaining = self._cooldown_until - time.monotonic()
        return max(0, int(remaining))

    def should_trigger_lockout(self) -> bool:
        """
        Return True if the failure count has crossed the threshold and we
        are not already in a cooldown window.
        """
        return (
            self._failure_count >= _LOCKOUT_THRESHOLD
            and not self.is_locked_out()
        )

    def activate_cooldown(self) -> None:
        """Start a new cooldown window and reset the failure counter."""
        self._cooldown_until = time.monotonic() + _LOCKOUT_COOLDOWN_S
        self._failure_count = 0

    def reset(self) -> None:
        """Reset all state (e.g., on successful authentication)."""
        self._failure_count = 0
        self._cooldown_until = 0.0

    @property
    def total_failures(self) -> int:
        return self._failure_count


# Module-level singleton rate-limiter.
_rate_limiter = _RateLimiter()


# ─────────────────────────────────────────────────────────────────────────────
#  STRUCTURED LOG PAYLOAD
# ─────────────────────────────────────────────────────────────────────────────

def _emit_security_event(
    event_type:      str,
    context:         str,
    factor:          str,
    exc:             Optional[BaseException],
    factors_present: Sequence[str],
) -> None:
    """
    Write a structured JSON-style security event to the audit log.

    The payload captures full developer-observable context while ensuring
    no sensitive values (passwords, key material, TOTP secrets) are logged.

    Log record format (JSON, one line):
    {
        "event":           "AUTH_FAILURE",
        "event_id":        42,
        "context":         "open_atlas",
        "timestamp":       "2026-04-12T09:31:00+00:00",
        "factor":          "totp",
        "exception_type":  "DecryptionError",
        "stack_summary":   ["crypto_engine.py:214 in decrypt_aes_gcm"],
        "factors_present": ["password", "totp"],
        "session_failures": 3
    }

    SECURITY NOTES:
    - ``exception_type`` only: the exception *message* is discarded entirely.
      It may echo user-supplied input or internal crypto state.
    - ``stack_summary`` contains only filename:lineno:function — no host paths,
      no local variable values.
    - ``factors_present`` lists factor *names*, never factor *values*.

    Args:
        event_type:      "AUTH_FAILURE" | "INPUT_VALIDATION" | "SAFE_ERROR"
        context:         Caller context tag (e.g. "open_atlas").
        factor:          Which factor failed ("password"/"keyfile"/"totp"/…).
        exc:             The caught exception.  Only its type is used.
        factors_present: Factor names present at failure time (no values).
    """
    event_id  = next(_event_counter)
    ts        = datetime.now(timezone.utc).isoformat(timespec="seconds")
    exc_type  = type(exc).__name__ if exc else "n/a"

    # Build a redacted stack summary: filename + lineno + function only.
    # Remove the full absolute path to avoid host-path leakage in log files.
    stack_summary: list[str] = []
    if exc is not None:
        tb = traceback.extract_tb(exc.__traceback__)
        for frame in tb:
            # Use only the basename of the filename.
            stack_summary.append(
                f"{frame.filename.split('/')[-1].split(chr(92))[-1]}"
                f":{frame.lineno} in {frame.name}"
            )

    payload = {
        "event":            event_type,
        "event_id":         event_id,
        "context":          context,
        "timestamp":        ts,
        "factor":           factor,
        "exception_type":   exc_type,
        "stack_summary":    stack_summary,
        "factors_present":  list(factors_present),
        "session_failures": _rate_limiter.total_failures,
    }

    _log.warning("ATLAS_SECURITY_EVENT %s", json.dumps(payload, separators=(",", ":")))


# ─────────────────────────────────────────────────────────────────────────────
#  THE DIALOG WIDGET (used internally — callers use class-method factories)
# ─────────────────────────────────────────────────────────────────────────────

class _AuthFailureDialog(BaseDialog):
    """
    The physical dialog widget shown for authentication failures.

    Invariants enforced:
    - Fixed title: _DIALOG_TITLE
    - Fixed size:  _DIALOG_WIDTH × _DIALOG_HEIGHT
    - Fixed message: _GENERIC_AUTH_MSG (or cooldown variant)
    - Fixed button layout: single "OK" button, centred
    - Fixed icon: lock symbol (no error-type-specific icons)

    This class is not part of the public API.  Use ``ErrorDialog`` class
    methods instead.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        cooldown_seconds: int = 0,
    ) -> None:
        super().__init__(
            parent,
            title=_DIALOG_TITLE,
            width=_DIALOG_WIDTH,
            height=_DIALOG_HEIGHT,
        )
        # Fixed size — prevents side-channel inference from window geometry.
        self.setFixedSize(_DIALOG_WIDTH, _DIALOG_HEIGHT)
        self._cooldown_seconds = cooldown_seconds
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XXL, Spacing.XL, Spacing.XXL, Spacing.XL)
        root.setSpacing(Spacing.MD)

        # ── Icon row (fixed lock icon — same for all failure types) ────────
        icon_row = QHBoxLayout()
        icon_lbl = QLabel("🔒")
        icon_lbl.setFont(Fonts.default(32))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_row.addStretch()
        icon_row.addWidget(icon_lbl)
        icon_row.addStretch()
        root.addLayout(icon_row)

        # ── Title ───────────────────────────────────────────────────────────
        title_lbl = QLabel(_DIALOG_TITLE)
        title_lbl.setFont(Fonts.heading(FontSize.LG))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {Colors.DANGER}; font-weight: 700; background: transparent;"
        )
        root.addWidget(title_lbl)

        # ── Message ─────────────────────────────────────────────────────────
        # The message is ALWAYS the generic string.
        # In cooldown mode, an additional neutral "please wait" line is appended.
        if self._cooldown_seconds > 0:
            msg_text = (
                f"{_GENERIC_AUTH_MSG}\n\n"
                f"Please wait {self._cooldown_seconds} seconds before trying again."
            )
            height_override = _DIALOG_HEIGHT + 30
            self.setFixedSize(_DIALOG_WIDTH, height_override)
        else:
            msg_text = _GENERIC_AUTH_MSG

        msg_lbl = QLabel(msg_text)
        msg_lbl.setFont(Fonts.default(FontSize.BASE))
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; background: transparent;")
        root.addWidget(msg_lbl)

        root.addStretch()

        # ── Single OK button (centred — identical layout for all failures) ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFont(Fonts.default(FontSize.BASE, bold=True))
        ok_btn.setStyleSheet(Styles.btn_danger())
        ok_btn.setMinimumWidth(110)
        ok_btn.setFixedHeight(36)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # Auto-focus OK so keyboard users see consistent behaviour.
        ok_btn.setFocus()


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API — ErrorDialog
# ─────────────────────────────────────────────────────────────────────────────

class ErrorDialog(BaseDialog):
    """
    Security-first error dialog for the ATLAS cryptographic protection system.

    This class is the **sole authorised entry point** for displaying errors
    that arise in or near authentication flows.  It enforces:

    Anti-enumeration
        All auth/input failures show one identical message, title, icon, size,
        and button layout.  No factor-specific branching reaches the UI.

    Keyword scrubbing
        Caller-supplied message strings are scanned for sensitive keywords
        before display.  Any match → message replaced with generic string.

    Timing jitter
        A random 100–600 ms delay precedes every auth-failure dialog display,
        preventing response-time correlation between code paths.

    Structured audit logging
        Every security event writes a JSON-formatted record to the application
        log.  The record captures exception type, redacted stack trace, and
        factor names — never exception messages or credential values.

    Rate-limiting / soft lockout
        After ``_LOCKOUT_THRESHOLD`` consecutive failures a cooldown banner is
        shown for ``_LOCKOUT_COOLDOWN_S`` seconds.  No lockout reason is disclosed.

    ── Class-method API (preferred) ──────────────────────────────────────────

    ErrorDialog.show_auth_failure(parent, context, factors_present, exc)
        For decryption, MAC, TOTP verify, and all crypto-layer failures.

    ErrorDialog.show_input_error(parent, context, factor)
        For missing/malformed fields — same UI, logged separately.

    ErrorDialog.show_safe_error(parent, title, message)
        For I/O, missing deps, OS errors — verbatim message, keyword-scrubbed.

    ErrorDialog.reset_rate_limiter()
        Call on successful authentication to clear the failure counter.

    ── Extension hooks ────────────────────────────────────────────────────────

    ErrorDialog.on_auth_failure_hook
        Callable[[str, str, str | None, list[str]], None]
        (context, factor, exc_type, factors_present) → None
        Wire up your IDS / rate-limiter / SIEM client here.

    ErrorDialog.on_input_validation_hook
        Callable[[str, str], None]
        (context, factor) → None

    ── Direct instantiation (safe, non-auth errors) ──────────────────────────

    ErrorDialog(message="Something went wrong.", parent=None)
        For non-auth operational messages.  Message is keyword-scrubbed.

    NEVER instantiate ErrorDialog with an exception message from an auth flow.
    Use ``show_auth_failure()`` instead.
    """

    # ── Extension hooks (no-ops by default) ───────────────────────────────────
    on_auth_failure_hook: Callable[
        [str, str, Optional[str], List[str]], None
    ] = staticmethod(lambda ctx, factor, exc_type, factors: None)

    on_input_validation_hook: Callable[
        [str, str], None
    ] = staticmethod(lambda ctx, factor: None)

    # ── Direct instantiation (safe, non-auth operational errors) ──────────────

    def __init__(self, message: str = "Something went wrong.", parent=None) -> None:
        """
        Show a non-auth operational error.

        The message is keyword-scrubbed before display as a safety net.
        For auth-context errors, use the class-method factories instead.
        """
        super().__init__(parent, title="Error", width=420, height=200)
        self.setFixedSize(420, 200)

        safe_message = _scrub_message(message)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.MD)

        lbl = QLabel(safe_message)
        lbl.setWordWrap(True)
        lbl.setFont(Fonts.default(FontSize.BASE))
        lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; background: transparent;")
        root.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFont(Fonts.default(FontSize.BASE, bold=True))
        ok_btn.setStyleSheet(Styles.btn_danger())
        ok_btn.setMinimumWidth(110)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # ── Class-method API ───────────────────────────────────────────────────────

    @classmethod
    def show_auth_failure(
        cls,
        parent:          Optional[QWidget] = None,
        context:         str = "unknown",
        factor:          str = "unknown",
        factors_present: Optional[Sequence[str]] = None,
        exc:             Optional[BaseException] = None,
    ) -> None:
        """
        Handle a cryptographic authentication failure.

        This method is the correct call-site for all decryption, MAC
        verification, TOTP check, and other crypto-layer failures.

        Sequence of operations:
            1. Record failure in rate-limiter.
            2. Emit structured JSON audit log record (Layer B).
            3. Fire on_auth_failure_hook (IDS / SIEM integration point).
            4. Determine cooldown state.
            5. Wait for a randomised jitter delay (timing-attack resistance).
            6. Display _AuthFailureDialog (Layer A — invariant UI).

        Args:
            parent:          Parent widget.
            context:         Caller context tag, e.g. ``"open_atlas"``.
            factor:          Failed factor name (never shown to user).
            factors_present: Factor names active at failure time (no values).
            exc:             Caught exception (type logged, message discarded).
        """
        fp = list(factors_present or [])

        # 1. Rate-limiter accounting.
        _rate_limiter.record_failure()
        cooldown_secs = 0
        if _rate_limiter.should_trigger_lockout():
            _rate_limiter.activate_cooldown()
            cooldown_secs = _LOCKOUT_COOLDOWN_S
        elif _rate_limiter.is_locked_out():
            cooldown_secs = _rate_limiter.seconds_remaining()

        # 2. Audit log.
        _emit_security_event("AUTH_FAILURE", context, factor, exc, fp)

        # 3. Extension hook (IDS / SIEM).
        try:
            cls.on_auth_failure_hook(
                context, factor,
                type(exc).__name__ if exc else None,
                fp,
            )
        except Exception as hook_exc:  # noqa: BLE001
            _log.error("on_auth_failure_hook raised: %s", type(hook_exc).__name__)

        # 4+5+6. Jitter delay → show dialog.
        cls._show_with_jitter(parent, cooldown_secs)

    @classmethod
    def show_input_error(
        cls,
        parent:  Optional[QWidget] = None,
        context: str = "unknown",
        factor:  str = "unknown",
        exc:     Optional[BaseException] = None,
    ) -> None:
        """
        Handle a client-side input validation failure.

        Identical UI to ``show_auth_failure``.  Logged as INPUT_VALIDATION so
        IDS hooks can distinguish empty-field probes from actual crypto failures.

        Args:
            parent:  Parent widget.
            context: Caller context tag.
            factor:  Which factor had bad/missing input.
            exc:     Caught exception, if any.
        """
        _rate_limiter.record_failure()
        cooldown_secs = 0
        if _rate_limiter.should_trigger_lockout():
            _rate_limiter.activate_cooldown()
            cooldown_secs = _LOCKOUT_COOLDOWN_S
        elif _rate_limiter.is_locked_out():
            cooldown_secs = _rate_limiter.seconds_remaining()

        _emit_security_event("INPUT_VALIDATION", context, factor, exc, [])

        try:
            cls.on_input_validation_hook(context, factor)
        except Exception as hook_exc:  # noqa: BLE001
            _log.error("on_input_validation_hook raised: %s", type(hook_exc).__name__)

        cls._show_with_jitter(parent, cooldown_secs)

    @classmethod
    def show_safe_error(
        cls,
        parent:  Optional[QWidget] = None,
        title:   str = "Error",
        message: str = "An error occurred.",
    ) -> None:
        """
        Display a non-auth operational error where the message is safe to show.

        Use for: I/O failures, missing pip dependencies, OS errors, file-save
        cancellations.  Do NOT use for any failure that originates inside a
        credential check or crypto operation.

        The message is keyword-scrubbed as a safety net.  If a sensitive keyword
        is detected, the generic auth message is shown and a warning is logged.

        Args:
            parent:  Parent widget.
            title:   Dialog title (not scrubbed — keep it non-sensitive).
            message: Human-readable error text (must not contain secrets).
        """
        safe_message = _scrub_message(message)
        _log.info(
            "ATLAS_SECURITY_EVENT %s",
            json.dumps({
                "event":   "SAFE_ERROR",
                "title":   title,
                "scrubbed": safe_message != message,
            }, separators=(",", ":")),
        )
        dlg = ErrorDialog(message=safe_message, parent=parent)
        dlg.setWindowTitle(title)
        dlg.exec()

    @classmethod
    def reset_rate_limiter(cls) -> None:
        """
        Reset the session failure counter.

        Call this on successful authentication to clear accumulated failure
        state.  Do NOT call from an error handler.
        """
        _rate_limiter.reset()
        _log.info(
            "ATLAS_SECURITY_EVENT %s",
            json.dumps({"event": "AUTH_SUCCESS_RESET"}, separators=(",", ":")),
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _show_with_jitter(
        parent: Optional[QWidget],
        cooldown_seconds: int,
    ) -> None:
        """
        Apply randomised timing jitter, then display ``_AuthFailureDialog``.

        The jitter is implemented with ``QTimer.singleShot`` which returns
        immediately — the calling function does not block.  The event loop
        continues normally during the delay, and the dialog appears after
        the timer fires.

        This prevents response-time correlation:
          - Fast-path failure (empty field rejected in 1 µs)
          - Slow-path failure (AES-GCM tag check took 5 ms)
          …both appear after the same random window to the observer.

        Args:
            parent:           Parent widget for the dialog.
            cooldown_seconds: If > 0, a cooldown banner is shown in the dialog.
        """
        jitter_ms = random.randint(_JITTER_MIN_MS, _JITTER_MAX_MS)

        def _show() -> None:
            dlg = _AuthFailureDialog(parent=parent, cooldown_seconds=cooldown_seconds)
            dlg.exec()

        QTimer.singleShot(jitter_ms, _show)


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL CONVENIENCE ALIASES
# ─────────────────────────────────────────────────────────────────────────────
# These allow the previous auth_error_handler singleton usage pattern to keep
# working without changes to existing call-sites.

class _LegacyHandlerShim:
    """
    Backwards-compatible shim that maps the old ``auth_error_handler``
    singleton API onto the new ``ErrorDialog`` class-method API.

    Existing call-sites using:
        auth_error_handler.show_auth_failure(parent, context, factor, exc)
        auth_error_handler.show_input_error(parent, context, factor, exc)
        auth_error_handler.show_safe_error(parent, title, message)

    ...continue to work without modification.
    """

    def show_auth_failure(
        self,
        parent:  Optional[QWidget],
        context: str,
        factor:  str,
        exc:     Optional[BaseException] = None,
    ) -> None:
        ErrorDialog.show_auth_failure(
            parent=parent, context=context, factor=factor, exc=exc
        )

    def show_input_error(
        self,
        parent:  Optional[QWidget],
        context: str,
        factor:  str,
        exc:     Optional[BaseException] = None,
    ) -> None:
        ErrorDialog.show_input_error(
            parent=parent, context=context, factor=factor, exc=exc
        )

    def show_safe_error(
        self,
        parent:  Optional[QWidget],
        title:   str,
        message: str,
    ) -> None:
        ErrorDialog.show_safe_error(parent=parent, title=title, message=message)

    # Hook pass-throughs
    @property
    def on_auth_failure_hook(self):
        return ErrorDialog.on_auth_failure_hook

    @on_auth_failure_hook.setter
    def on_auth_failure_hook(self, fn):
        ErrorDialog.on_auth_failure_hook = staticmethod(fn)

    @property
    def on_input_validation_hook(self):
        return ErrorDialog.on_input_validation_hook

    @on_input_validation_hook.setter
    def on_input_validation_hook(self, fn):
        ErrorDialog.on_input_validation_hook = staticmethod(fn)


# Drop-in replacement for the old module-level singleton.
auth_error_handler = _LegacyHandlerShim()
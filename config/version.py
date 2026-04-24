"""
atlas_viewer.config.version
==============================
Single source of truth for application versioning.

Versioning Policy
-----------------
Follows `Semantic Versioning 2.0.0 <https://semver.org/>`_:
  MAJOR.MINOR.PATCH

  * MAJOR — breaking changes to public APIs or file formats.
  * MINOR — backwards-compatible new features.
  * PATCH — backwards-compatible bug fixes and security updates.

Pre-release identifiers (e.g. ``"2.1.0-beta.1"``) are expressed via
:data:`VERSION_PRE`.

Runtime Compatibility
---------------------
:func:`require_python` is called at startup to fail fast with a clear
message instead of cryptic import errors on older interpreters.

Nuitka / PyInstaller Notes
--------------------------
This module contains only string/int constants and stdlib imports —
safe to import before ``QApplication`` is constructed, and safe to
compile into a Nuitka standalone build without any path adjustments.
"""

from __future__ import annotations

import sys
from typing import Tuple


# ─────────────────────────────────────────────────────────────────────────────
#  VERSION CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

#: Major version — increment on breaking API or format changes.
MAJOR: int = 2
#: Minor version — increment on new backwards-compatible features.
MINOR: int = 1
#: Patch version — increment on bug fixes and security patches.
PATCH: int = 0
#: Optional pre-release tag, e.g. ``"alpha.1"`` or ``"rc.2"``.  Empty string for stable.
VERSION_PRE: str = ""

#: Human-readable version string, e.g. ``"2.1.0"`` or ``"2.1.0-beta.1"``.
VERSION: str = (
    f"{MAJOR}.{MINOR}.{PATCH}"
    if not VERSION_PRE
    else f"{MAJOR}.{MINOR}.{PATCH}-{VERSION_PRE}"
)

#: Version as a comparable tuple for ``>=`` checks.
VERSION_TUPLE: Tuple[int, int, int] = (MAJOR, MINOR, PATCH)


# ─────────────────────────────────────────────────────────────────────────────
#  APPLICATION METADATA
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME: str = "ATLAS Viewer"
APP_FULL_NAME: str = "ATLAS PDF Viewer"
AUTHOR: str = "Atlas Security Lab"
COPYRIGHT: str = "\u00a9 2026 Atlas Security Lab. All Rights Reserved."
LICENSE: str = "Proprietary"
DESCRIPTION: str = "Commercial-Grade Multi-Format Document Viewer"
BUILD_DATE: str = "2026-04-12"
WEBSITE: str = "https://atlas-pdf.patronhubdevs.com"
GUMROAD_URL: str = "https://patronhubdevs.gumroad.com/l/nbuotr"
WINDOW_TITLE: str = f"{APP_FULL_NAME}  v{VERSION}"
LOG_FILE: str = "atlas_viewer.log"

#: Minimum Python interpreter version required at runtime.
MIN_PYTHON: Tuple[int, int] = (3, 10)

#: Minimum PySide6 version required.
MIN_PYSIDE6: str = "6.6.0"

#: Minimum PyMuPDF version required.
MIN_PYMUPDF: str = "1.23.0"


# ─────────────────────────────────────────────────────────────────────────────
#  RUNTIME COMPATIBILITY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def require_python(min_version: Tuple[int, int] = MIN_PYTHON) -> None:
    """
    Abort with a clear message if the Python interpreter is too old.

    This check runs before any Qt import so the error is readable in all
    environments (terminal, Nuitka-compiled binary, CI).

    Args:
        min_version: Required ``(major, minor)`` tuple. Defaults to
                     :data:`MIN_PYTHON`.

    Raises:
        SystemExit: If the running interpreter is below *min_version*.
    """
    if sys.version_info < min_version:
        req = ".".join(str(v) for v in min_version)
        got = ".".join(str(v) for v in sys.version_info[:3])
        sys.exit(
            f"[ATLAS Viewer] Python {req}+ is required. "
            f"You are running Python {got}.\n"
            f"Download the latest Python from https://www.python.org/downloads/"
        )


def check_dependency(
    module_name: str,
    package_name: str,
    min_version: str = "",
    fatal: bool = True,
) -> bool:
    """
    Check whether an optional or required dependency is importable.

    Uses a static try/import pattern so Nuitka can see the import at compile time.
    Dynamic importlib.import_module() is NOT used here — it prevents Nuitka from
    including the module in the compiled binary.

    Args:
        module_name:  The Python import name (e.g. ``"fitz"``).
        package_name: The pip install name shown in error messages.
        min_version:  If non-empty, compared against ``module.__version__``.
        fatal:        Exit via ``sys.exit`` on failure when ``True``.

    Returns:
        bool: ``True`` if the dependency satisfies all constraints.
    """
    mod = None
    try:
        if module_name == "PySide6":
            import PySide6 as mod  # type: ignore[assignment]
        elif module_name == "fitz":
            import fitz as mod  # type: ignore[assignment]
        elif module_name == "cryptography":
            import cryptography as mod  # type: ignore[assignment]
        else:
            # For any other module: attempt import via __import__ (still static
            # enough for Nuitka when the name is a string literal, but safer
            # than importlib for the known dependencies above).
            mod = __import__(module_name)
    except ImportError:
        msg = (
            f"[ATLAS Viewer] Required package '{package_name}' is not installed.\n"
            f"Install it with:  pip install {package_name}"
        )
        if fatal:
            sys.exit(msg)
        return False

    if min_version and mod is not None:
        installed = getattr(mod, "__version__", "0.0.0")
        inst_tuple = tuple(int(x) for x in installed.split(".")[:3] if x.isdigit())
        req_tuple  = tuple(int(x) for x in min_version.split(".")[:3] if x.isdigit())
        if inst_tuple < req_tuple:
            msg = (
                f"[ATLAS Viewer] Package '{package_name}' v{min_version}+ is required. "
                f"Installed: v{installed}.\n"
                f"Upgrade with:  pip install --upgrade {package_name}"
            )
            if fatal:
                sys.exit(msg)
            return False

    return True


def get_version_info() -> str:
    """
    Return a multi-line version/build info string for log headers.

    Returns:
        str: Formatted block containing app version, Python version,
             PySide6 version, and build date.
    """
    py_ver = ".".join(str(v) for v in sys.version_info[:3])
    try:
        import PySide6
        qt_ver = PySide6.__version__
    except ImportError:
        qt_ver = "not installed"
    return (
        f"{APP_FULL_NAME} v{VERSION}\n"
        f"Python {py_ver} | PySide6 {qt_ver}\n"
        f"Build: {BUILD_DATE} | {COPYRIGHT}"
    )

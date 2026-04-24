"""
atlas_viewer.utils.path_utils
==============================
Secure path utilities for file I/O and Nuitka/PyInstaller compatibility.

Security Principles
-------------------
All user-supplied or PDF-sourced paths pass through this module before
any filesystem operation.  Functions here enforce:

1. **No path traversal** — resolved paths are checked to remain inside an
   expected base directory.
2. **Length limits** — paths that exceed :data:`~atlas_viewer.config.settings.SecurityConfig.max_path_length`
   are rejected immediately.
3. **No null bytes** — null characters in paths are stripped before
   resolution (prevents ``os.path.join`` bypass on some platforms).
4. **No network paths by default** — UNC paths (``\\\\server\\share``) and
   ``file://`` URIs are rejected unless
   :attr:`~atlas_viewer.config.settings.SecurityConfig.allow_network_paths` is ``True``.

Nuitka / PyInstaller Compatibility
-----------------------------------
:func:`get_runtime_base_dir` and :func:`resource_path` resolve correctly
in *all* of:

* Plain Python source run  (``python -m atlas_viewer``)
* ``--onefile`` Nuitka build (uses ``__compiled__.containing_dir``)
* PyInstaller onefile       (uses ``sys._MEIPASS``)
* PyInstaller onedir        (uses ``sys.executable`` directory)

The canonical pattern for accessing bundled resources::

    from atlas_viewer.utils.path_utils import resource_path
    icon_path = resource_path("resources/icon.png")
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from config.settings import settings


def get_runtime_base_dir() -> Path:
    """
    Return the base directory of the running application.

    Resolution order:
    1. Frozen executable (Nuitka onefile OR PyInstaller): sys.frozen is True
       → return directory containing sys.executable.
    2. PyInstaller onefile temp extraction (sys._MEIPASS): fallback for
       PyInstaller where bundled data lives in a temp dir.
    3. Plain Python source: return the project root (three levels up).

    NOTE on Nuitka ``__compiled__``:
    The ``globals().get("__compiled__")`` pattern does NOT work at runtime —
    ``__compiled__`` is a compile-time constant, not a runtime module global.
    The correct frozen-exe detection for Nuitka is the same as PyInstaller:
    check ``sys.frozen``.  Both runtimes set it to ``True``.

    Returns:
        Path: Absolute base directory.
    """
    # Both Nuitka onefile and PyInstaller set sys.frozen = True
    if getattr(sys, "frozen", False):
        # PyInstaller onefile unpacks data to _MEIPASS; prefer that if set
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        # Nuitka onefile (and PyInstaller onedir): exe lives in our base dir
        return Path(sys.executable).parent.resolve()

    # Plain Python: go two levels up from utils/ → project root (atlas_viewer package root)
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """
    Resolve a path to a bundled resource file.

    Works identically in source, Nuitka onefile, and PyInstaller builds.

    Args:
        relative: Relative path from the application base directory,
                  using forward slashes (e.g. ``"resources/icon.png"``).

    Returns:
        Path: Absolute path to the resource.

    Example::

        from atlas_viewer.utils.path_utils import resource_path
        logo = resource_path("resources/logo.png")
        if logo.exists():
            pixmap.load(str(logo))
    """
    return get_runtime_base_dir() / Path(relative)


def safe_resolve_path(
    path: str | Path,
    base_dir: Optional[Path] = None,
    allow_network: Optional[bool] = None,
) -> Path:
    """
    Resolve and validate a user-supplied or engine-produced path.

    Performs the following checks in order:

    1. Strip null bytes (``\\x00``).
    2. Reject paths whose length exceeds ``settings.security.max_path_length``.
    3. Optionally reject UNC / ``file://`` network paths.
    4. Resolve to an absolute path.
    5. If *base_dir* is given, verify the resolved path is inside it
       (path traversal guard).

    Args:
        path:          Input path string or Path object.
        base_dir:      If given, the resolved path must reside within this
                       directory.  Pass the target extraction folder for
                       attachment paths.
        allow_network: Override ``settings.security.allow_network_paths``.
                       Defaults to the settings value.

    Returns:
        Path: Validated absolute path.

    Raises:
        ValueError: If any security check fails.

    Example::

        dest = safe_resolve_path(user_input, base_dir=export_dir)
        dest.write_bytes(data)
    """
    allow_net = (
        settings.security.allow_network_paths
        if allow_network is None
        else allow_network
    )

    raw = str(path)

    # 1. Strip null bytes
    cleaned = raw.replace("\x00", "")
    if cleaned != raw:
        raise ValueError(f"Path contains null bytes: {raw!r}")

    # 2. Length limit
    if len(cleaned) > settings.security.max_path_length:
        raise ValueError(
            f"Path length {len(cleaned)} exceeds maximum "
            f"{settings.security.max_path_length}"
        )

    # 3. Network path check (Windows UNC or URI scheme)
    if not allow_net:
        if cleaned.startswith("\\\\") or cleaned.startswith("//"):
            raise ValueError(f"Network paths are not permitted: {cleaned!r}")
        if cleaned.lower().startswith("file://"):
            raise ValueError(f"file:// URIs are not permitted: {cleaned!r}")

    # 4. Resolve absolute path
    resolved = Path(cleaned).resolve()

    # 5. Base-directory confinement (path traversal guard)
    if base_dir is not None:
        base_resolved = Path(base_dir).resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            raise ValueError(
                f"Resolved path '{resolved}' escapes base directory '{base_resolved}'"
            )

    return resolved


def validate_output_path(
    path: str | Path,
    must_not_exist: bool = False,
    create_parents: bool = True,
) -> Path:
    """
    Validate and prepare a file output path.

    Args:
        path:            Target output file path.
        must_not_exist:  If ``True``, raise if the path already exists
                         (prevents accidental overwrites in non-interactive
                         scenarios).
        create_parents:  If ``True``, create missing parent directories.

    Returns:
        Path: Resolved output path.

    Raises:
        ValueError: If the path is unsafe or already exists when forbidden.
        OSError:    If parent directory creation fails.
    """
    resolved = safe_resolve_path(path)

    if must_not_exist and resolved.exists():
        raise ValueError(f"Output path already exists: {resolved}")

    if create_parents:
        resolved.parent.mkdir(parents=True, exist_ok=True)

    return resolved

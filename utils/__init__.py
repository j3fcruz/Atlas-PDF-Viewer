"""
atlas_viewer.utils
===================
Shared utility package — no Qt, no PDF dependencies.

Public re-exports from sub-modules so callers import from one place::

    from atlas_viewer.utils import get_logger, perf_timer, sanitize_filename,
        center_window, human_readable_size, safe_resolve_path

Extension Points
----------------
Add new helper modules under this package and export them here.
Keep modules stateless — no global state except the logging singleton.
"""

from utils.logging_setup import get_logger, perf_timer, setup_logging
from utils.ui_helpers import (
    center_window,
    human_readable_size,
    make_badge,
    make_h_separator,
    make_label,
    make_v_separator,
    sanitize_filename,
)
from utils.path_utils import (
    safe_resolve_path,
    validate_output_path,
    get_runtime_base_dir,
    resource_path,
)

__all__ = [
    # logging
    "get_logger",
    "perf_timer",
    "setup_logging",
    # ui helpers
    "center_window",
    "human_readable_size",
    "make_badge",
    "make_h_separator",
    "make_label",
    "make_v_separator",
    "sanitize_filename",
    # path utilities
    "safe_resolve_path",
    "validate_output_path",
    "get_runtime_base_dir",
    "resource_path",
]

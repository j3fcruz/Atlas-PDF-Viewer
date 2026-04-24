"""atlas_opener.ui.dialogs — dialog windows (opener build)."""

from .base_dialog import BaseDialog
from .bookmarks_dialog import BookmarksDialog
from .attachments_dialog import AttachmentsDialog
from .info_dialogs import DocumentInfoDialog, AboutDialog
from .mf_auth_dialog import MFAAuthDialog
from .error_dialog import ErrorDialog
from .documentation_dialog import DocumentationDialog

__all__ = [
    "BaseDialog",
    "BookmarksDialog",
    "AttachmentsDialog",
    "DocumentInfoDialog",
    "AboutDialog",
    "MFAAuthDialog",
    "ErrorDialog",
    "DocumentationDialog",
]

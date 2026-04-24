"""
atlas_opener.services (opener build)

Removed vs full build:
  * ProtectionService — not needed for open/view only
  * print_manager / print_spooler — not included
"""

from services.document_service import DocumentService
from services.bookmark_service import BookmarkService
from services.attachment_service import AttachmentService
from services.thumbnail_service import ThumbnailService

ServiceRegistry: dict = {
    "document":   DocumentService,
    "bookmark":   BookmarkService,
    "attachment": AttachmentService,
}

__all__ = [
    "AttachmentService",
    "BookmarkService",
    "DocumentService",
    "ThumbnailService",
    "ServiceRegistry",
]

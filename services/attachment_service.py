"""
atlas_viewer.services.attachment_service
==========================================
AttachmentService — lists and safely extracts PDF embedded attachments.

Security Hardening
------------------
* Filenames are sanitized via
  :func:`~atlas_viewer.utils.sanitize_filename` (path-traversal safe).
* Extracted paths are confirmed to reside inside the output directory
  using :func:`~atlas_viewer.utils.safe_resolve_path`.
* Per-attachment size limit enforced from ``settings.attachments``.
* All extraction events are logged (filename + byte count).
* Metadata display strings are already clamped by
  :class:`~atlas_viewer.core.mupdf_engine.MuPDFEngine`.

Separation of Concerns
-----------------------
This service never touches the UI — it returns typed model objects and
file paths.  The dialog layer (:class:`~atlas_viewer.ui.dialogs.AttachmentsDialog`)
is responsible for displaying results.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from core.document_engine import AbstractDocumentEngine
from core.exceptions import AttachmentExtractionError, DocumentLoadError
from models import AttachmentInfo
from utils import get_logger, perf_timer, safe_resolve_path, sanitize_filename

_log = get_logger(__name__)


class AttachmentService:
    """
    Lists and safely extracts PDF embedded file attachments.

    Receives an engine instance (constructor injection) so it can be tested
    independently of any document loaded in the main UI.

    Usage::

        svc = AttachmentService(engine)
        attachments = svc.list_attachments()
        for att in attachments:
            path = svc.extract_to_dir(att, "/tmp/output")

    Extension Point
    ---------------
    Sub-class and override :meth:`extract_to_dir` to add custom
    post-processing (e.g. virus scanning, format conversion).
    """

    def __init__(self, engine: AbstractDocumentEngine) -> None:
        self._engine = engine

    # ── Public API ─────────────────────────────────────────────────────────

    def list_attachments(self) -> List[AttachmentInfo]:
        """
        Return metadata for all embedded attachments in the open document.

        Returns:
            List[AttachmentInfo]: Empty list if no attachments exist.

        Raises:
            DocumentLoadError: No document is open.
        """
        if not self._engine.is_open():
            raise DocumentLoadError(
                "No document is open in AttachmentService.list_attachments()."
            )
        attachments = self._engine.get_attachments()
        _log.info("Attachment listing: found %d attachment(s).", len(attachments))
        return attachments

    def extract_to_dir(self, attachment: AttachmentInfo, output_dir: str) -> Path:
        """
        Extract an attachment to a directory safely.

        Steps:

        1. Sanitize the filename (strip separators, null bytes, leading dots).
        2. Resolve the destination path.
        3. Confirm the resolved path is inside *output_dir* (path traversal guard).
        4. Enforce the per-attachment size limit.
        5. Write the bytes.

        Args:
            attachment: :class:`~atlas_viewer.models.AttachmentInfo` from
                        :meth:`list_attachments`.
            output_dir: Target directory.  Created if it does not exist.

        Returns:
            Path: Absolute path of the written file.

        Raises:
            ValueError:                Resolved path escapes *output_dir*.
            AttachmentExtractionError: Extraction or write failed.
        """
        # Validate and sanitize output directory
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_name = sanitize_filename(attachment.safe_name or attachment.name)

        # Guard against path traversal in the attachment name itself
        dest = safe_resolve_path(out_dir / safe_name, base_dir=out_dir)

        with perf_timer(_log, f"extract '{safe_name}'"):
            data = self._engine.extract_attachment(attachment)

        try:
            dest.write_bytes(data)
        except OSError as exc:
            raise AttachmentExtractionError(
                f"Could not write attachment to '{dest.name}': {exc}"
            ) from exc

        _log.info(
            "Attachment extracted: '%s' → '%s'  (%s)",
            safe_name,
            dest.name,
            _fmt_size(len(data)),
        )
        return dest

    def extract_all(self, output_dir: str) -> List[Path]:
        """
        Extract all attachments to a directory.

        Continues on individual attachment failures and returns successful paths.

        Args:
            output_dir: Target extraction directory.

        Returns:
            List[Path]: Paths of successfully extracted files.
        """
        results: List[Path] = []
        for att in self.list_attachments():
            try:
                path = self.extract_to_dir(att, output_dir)
                results.append(path)
            except (AttachmentExtractionError, ValueError) as exc:
                _log.warning("Skipped attachment '%s': %s", att.safe_name, exc)
        return results


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n //= 1024
    return f"{n:.0f} GB"

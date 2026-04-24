from __future__ import annotations

import hashlib
import json
import logging
import secrets
import abc
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from core.atlas_format import (
    AtlasConstants,
    atlas_write_file,
)
from core.exceptions import AtlasViewerError

_log = logging.getLogger(__name__)

# ── Load Rust extension (REQUIRED) ────────────────────────────────────────────
try:
    import atlas_core as _core
except ImportError as exc:
    raise RuntimeError(
        "atlas_core extension is required but not found.\n"
        "Ensure it is bundled correctly with Nuitka (--include-module=atlas_core).\n"
        f"Original error: {exc}"
    ) from exc

# Optional: integrity check (recommended)
# Replace EXPECTED_HASH with your real compiled .pyd hash
EXPECTED_HASH = None  # set to string to enable

def _verify_core_integrity() -> None:
    if EXPECTED_HASH is None:
        return
    p = Path(_core.__file__)
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h != EXPECTED_HASH:
        raise RuntimeError("atlas_core integrity check failed")

_verify_core_integrity()

_RUST = True
_log.debug("atlas_core loaded — Rust-only crypto engine active")


# ─────────────────────────────────────────────────────────────────────────────
#  ABSTRACT INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

class AbstractDocumentEngine(abc.ABC):
    """
    Format-agnostic document engine interface.

    All concrete implementations must:
    * Isolate format-specific library imports within the subclass.
    * Never import Qt or UI modules.
    * Be safe to instantiate with no arguments.
    * Clean up all resources in :meth:`close`, even if :meth:`open` raised.

    Extension Point
    ---------------
    Subclass this and register with :class:`EngineRegistry` to add
    support for a new document format.
    """

    # ── Lifecycle ──────────────────────────────────────────────────────────

    @abc.abstractmethod
    def open(self, path: str, password: Optional[str] = None) -> DocumentInfo:
        """
        Open a document at the given path.

        Args:
            path:     Absolute path to the document file.  The path has
                      already been validated by the caller — do not
                      re-validate here.
            password: Optional decryption password for encrypted documents.

        Returns:
            DocumentInfo: Populated metadata for the opened document.

        Raises:
            DocumentLoadError:       File cannot be opened or parsed.
            DocumentEncryptedError:  Wrong or missing password.
            DocumentValidationError: File fails engine-level safety checks.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """
        Release all resources held by this engine instance.

        Must be idempotent — safe to call on a not-open engine.
        """

    @abc.abstractmethod
    def is_open(self) -> bool:
        """Return ``True`` if a document is currently open."""

    # ── Pages ──────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def get_page_count(self) -> int:
        """
        Return the total number of pages in the open document.

        Raises:
            DocumentLoadError: No document is open.
        """

    @abc.abstractmethod
    def get_page_info(self, page_index: int) -> PageInfo:
        """
        Return metadata for a single page.

        Args:
            page_index: 0-based page index.

        Returns:
            PageInfo: Page dimensions and label.

        Raises:
            ValueError:        Page index out of range.
            DocumentLoadError: No document is open.
        """

    @abc.abstractmethod
    def render_page(
        self,
        page_index: int,
        zoom: float = 1.0,
        rotation: int = 0,
    ) -> Tuple[bytes, int, int]:
        """
        Render a page to raw RGB24 bytes.

        The byte layout is row-major RGB, 3 bytes per pixel, no alpha channel.
        This is the format expected by :class:`~atlas_viewer.ui.widgets.pdf_canvas.PDFCanvas`.

        Args:
            page_index: 0-based page index.
            zoom:       Scale factor (``1.0`` = 100 %, ``2.0`` = 200 %).
            rotation:   Clockwise rotation in degrees; must be 0, 90, 180, or 270.

        Returns:
            Tuple[bytes, int, int]: ``(rgb_bytes, rendered_width, rendered_height)``

        Raises:
            PageRenderError:   Rendering failed.
            DocumentLoadError: No document is open.
            ValueError:        Invalid page index or rotation.
        """

    @abc.abstractmethod
    def get_page_text(self, page_index: int) -> str:
        """
        Extract plain text from a page.

        Returns an empty string for image-only pages rather than raising.

        Args:
            page_index: 0-based page index.

        Returns:
            str: Extracted text (may be empty).
        """

    # ── Bookmarks ──────────────────────────────────────────────────────────

    @abc.abstractmethod
    def get_bookmarks(self) -> List[BookmarkNode]:
        """
        Return the complete hierarchical bookmark tree.

        Returns:
            List[BookmarkNode]: Top-level nodes with nested :attr:`~atlas_viewer.models.BookmarkNode.children`.
            Empty list if the document has no bookmarks.
        """

    # ── Attachments ────────────────────────────────────────────────────────

    @abc.abstractmethod
    def get_attachments(self) -> List[AttachmentInfo]:
        """
        Return metadata for all embedded file attachments.

        Returns:
            List[AttachmentInfo]: May be empty.
        """

    @abc.abstractmethod
    def extract_attachment(self, attachment: AttachmentInfo) -> bytes:
        """
        Extract the raw bytes of an embedded attachment.

        Implementations must enforce the size limit from
        ``settings.attachments.max_attachment_size_bytes`` before
        allocating the output buffer.

        Args:
            attachment: :class:`~atlas_viewer.models.AttachmentInfo` from
                        :meth:`get_attachments`.

        Returns:
            bytes: Raw file content.

        Raises:
            AttachmentExtractionError: Extraction failed or size limit exceeded.
        """

    # ── Validation ─────────────────────────────────────────────────────────

    @abc.abstractmethod
    def validate(self, path: str) -> ValidationResult:
        """
        Validate a document file before loading.

        Performs lightweight checks that do not require fully parsing the
        document: file existence, size limits, magic bytes, extension.

        Args:
            path: Path to the file to check.

        Returns:
            ValidationResult: Contains ``is_valid`` and error details.
        """



# ── Exceptions ────────────────────────────────────────────────────────────────

class CryptoError(AtlasViewerError):
    pass

class DecryptionError(CryptoError):
    pass

class MissingDependencyError(CryptoError):
    pass


# ── Dependency check ──────────────────────────────────────────────────────────

def check_crypto_deps() -> None:
    if not _RUST:
        raise MissingDependencyError("atlas_core extension is required")


# ── Internal: prepare factors for Rust ────────────────────────────────────────

def _rust_factors(factors: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, val in factors.items():
        if key == "keyfile":
            p = Path(val)
            if not p.is_file():
                raise ValueError(f"Keyfile not found: {val}")
            out[key] = p.read_bytes()
        else:
            out[key] = val
    return out


# ── CryptoEngine ──────────────────────────────────────────────────────────────

class CryptoEngine:

    @staticmethod
    def extract_meta_and_decrypt(
        atlas_path: str,
        factors: Dict[str, Any],
        hwid_bind: bool = False,
    ) -> Tuple[Dict[str, Any], bytes]:

        data = bytes(_core.read_file(atlas_path))
        meta, encrypted_pdf = _core.parse_header(data)

        meta = dict(meta)
        encrypted_pdf = bytes(encrypted_pdf)

        if "salt" not in meta:
            raise ValueError("ATLAS metadata missing 'salt' field")

        try:
            salt = bytes.fromhex(meta["salt"])
        except Exception as exc:
            raise ValueError(f"Invalid salt: {exc}") from exc

        if len(salt) != 16:
            raise ValueError(f"Salt wrong length: {len(salt)}")

        effective_hwid = hwid_bind or bool(meta.get("hwid_bind", False))

        rust_f = _rust_factors(factors)

        try:
            plaintext = bytes(
                _core.decrypt_atlas(encrypted_pdf, rust_f, salt, effective_hwid)
            )
        except ValueError as exc:
            raise DecryptionError(str(exc)) from exc

        _log.info("Decrypted via Rust (%s)", Path(atlas_path).name)
        return meta, plaintext


    @staticmethod
    def decrypt_pdf(
        payload: bytes,
        factors: Dict[str, Any],
        salt: bytes,
        hwid_bind: bool = False,
    ) -> bytes:

        rust_f = _rust_factors(factors)

        try:
            return bytes(
                _core.decrypt_atlas(payload, rust_f, salt, hwid_bind)
            )
        except ValueError as exc:
            raise DecryptionError(str(exc)) from exc


    @staticmethod
    def encrypt_pdf(
        pdf_path: str,
        factors: Dict[str, Any],
        salt: bytes,
        hwid_bind: bool = False,
    ) -> Tuple[bytes, bytes]:

        pdf_bytes = Path(pdf_path).read_bytes()
        rust_f = _rust_factors(factors)

        try:
            payload = bytes(
                _core.encrypt_atlas(pdf_bytes, rust_f, salt, hwid_bind)
            )
        except ValueError as exc:
            raise CryptoError(str(exc)) from exc

        return payload, salt


# ── Atlas container builder ───────────────────────────────────────────────────

def build_atlas_container(
    pdf_path: str,
    factors: Dict[str, Any],
    output_path: str,
    app_version: str = "2.0.0",
    hwid_bind: bool = False,
) -> Path:

    check_crypto_deps()

    salt = secrets.token_bytes(AtlasConstants.HKDF_SALT_LEN)
    payload, _ = CryptoEngine.encrypt_pdf(pdf_path, factors, salt, hwid_bind)

    meta: Dict[str, Any] = {
        "salt":          salt.hex(),
        "factors":       sorted(factors.keys()),
        "hwid_bind":     hwid_bind,
        "created":       datetime.now(UTC).isoformat(),
        "atlas_version": AtlasConstants.FORMAT_VERSION,
        "app_version":   app_version,
    }

    try:
        container_bytes = bytes(_core.build_container(meta, payload))
    except ValueError as exc:
        raise CryptoError(str(exc)) from exc

    out = atlas_write_file(output_path, container_bytes, atomic=True)

    _log.info(
        "ATLAS container written: %s (%d bytes, hwid_bind=%s)",
        out.name,
        out.stat().st_size,
        hwid_bind,
    )

    return out
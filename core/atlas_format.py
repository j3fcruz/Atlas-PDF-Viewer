"""
atlas_opener.core.atlas_format  (Rust-backed via atlas_core.pyd)
================================================================
Drop-in replacement for the pure-Python atlas_format.py.

Public API is identical — every import in the codebase continues to work
unchanged:
    from core.atlas_format import AtlasConstants, atlas_read_file,
                                   atlas_write_file, parse_atlas_header,
                                   atlas_validate_path, safe_temp_file

Execution path:
    Python call → atlas_core.pyd (Rust) when available
    Python call → pure-Python fallback when .pyd not yet built (dev mode)

The fallback ensures the app still runs during development before the Rust
crate is compiled, and gives a clear error message if the .pyd is missing
at runtime in production.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple

_log = logging.getLogger(__name__)

# ── Load Rust extension ───────────────────────────────────────────────────────
try:
    import atlas_core as _core
    _RUST = True
    _log.debug("atlas_core.pyd loaded — using Rust atlas_format")
except ImportError:
    _RUST = False
    _core = None  # type: ignore[assignment]
    _log.warning(
        "atlas_core.pyd not found — falling back to pure-Python atlas_format. "
        "Build the Rust crate to enable the hardened implementation."
    )


# ── Constants (always Python — used in UI/settings, no crypto needed) ─────────

class AtlasConstants:
    """
    Cryptographic parameter constants for the ATLAS container format.
    Values must match the Rust implementation in atlas_core/src/factors.rs exactly.
    """
    PBKDF2_ITERATIONS   = 600_000
    PBKDF2_HASH         = "sha256"
    HKDF_SALT_LEN       = 16
    HKDF_INFO           = b"ATLAS_PDF_v2.0"
    AES_KEY_LEN         = 32
    AES_IV_LEN          = 12
    GCM_TAG_LEN         = 16
    ARGON2_HASH_LEN     = 32
    MAX_PDF_SIZE        = 10 * 1024 * 1024 * 1024
    MAX_KEYFILE_SIZE    = 10 * 1024 * 1024
    MAX_METADATA_SIZE   = 1  * 1024 * 1024
    ATLAS_MAGIC         = b"ATLAS\x00\x00\x00"
    FORMAT_VERSION      = "2.0"


# ── Safe temp file (pure Python — no crypto involvement) ──────────────────────

@contextmanager
def safe_temp_file(
    suffix: str = ".tmp",
    cleanup: bool = True,
) -> Generator[str, None, None]:
    """Create a temp file, yield its path, optionally clean up on exit."""
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as f:
            tmp_path = f.name
        yield tmp_path
    finally:
        if cleanup and tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Path validation ───────────────────────────────────────────────────────────

def atlas_validate_path(
    path: str,
    must_exist: bool = False,
    must_be_file: bool = True,
) -> Path:
    """Validate and resolve a filesystem path."""
    if _RUST:
        resolved = _core.validate_path(path, must_exist, must_be_file)
        return Path(resolved)
    # Pure-Python fallback
    if not path or not isinstance(path, str):
        raise ValueError("Invalid path: empty or wrong type")
    p = Path(path).resolve()
    if must_exist and not p.exists():
        raise FileNotFoundError(f"Path does not exist: {p}")
    if must_be_file and must_exist and not p.is_file():
        raise ValueError(f"Path is not a file: {p}")
    return p


# ── File I/O ──────────────────────────────────────────────────────────────────

def atlas_read_file(
    path: str,
    max_size: int = AtlasConstants.MAX_PDF_SIZE,
) -> bytes:
    """Read a file with size and integrity checks."""
    if _RUST:
        return bytes(_core.read_file(path, max_size))
    # Pure-Python fallback
    p = atlas_validate_path(path, must_exist=True, must_be_file=True)
    file_size = p.stat().st_size
    if file_size > max_size:
        raise ValueError(f"File too large: {file_size:,} bytes (max {max_size:,})")
    if file_size == 0:
        raise ValueError("File is empty")
    data = p.read_bytes()
    if len(data) != file_size:
        raise IOError(f"Incomplete read: expected {file_size}, got {len(data)}")
    return data


def atlas_write_file(path: str, data: bytes, atomic: bool = True) -> Path:
    """Write bytes to disk with optional atomic swap."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    if not data:
        raise ValueError("Cannot write empty data")
    p = atlas_validate_path(path, must_exist=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    if atomic:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=p.suffix, dir=p.parent, delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.replace(tmp_path, p)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    else:
        with open(p, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    written = p.stat().st_size
    if written != len(data):
        raise IOError(f"Write verification failed: expected {len(data)}, got {written}")
    _log.info("Wrote %d bytes to %s", len(data), p.name)
    return p


# ── Container parsing ─────────────────────────────────────────────────────────

def parse_atlas_header(data: bytes) -> Tuple[Dict[str, Any], bytes]:
    """
    Parse an ATLAS container blob → (metadata_dict, encrypted_pdf_payload).
    Uses Rust implementation when atlas_core.pyd is available.
    """
    if _RUST:
        meta, payload = _core.parse_header(data)
        return dict(meta), bytes(payload)
    # Pure-Python fallback
    if len(data) < 12:
        raise ValueError("ATLAS file too small")
    if data[:8] != AtlasConstants.ATLAS_MAGIC:
        raise ValueError("Invalid ATLAS magic header — not a valid .atlas file")
    try:
        meta_total_len = struct.unpack(">I", data[8:12])[0]
    except struct.error as exc:
        raise ValueError(f"Invalid length field: {exc}") from exc
    if meta_total_len == 0 or meta_total_len > AtlasConstants.MAX_METADATA_SIZE:
        raise ValueError(f"Metadata length out of range: {meta_total_len}")
    if len(data) < 12 + meta_total_len:
        raise ValueError("ATLAS file truncated at metadata block")
    meta_block = data[12: 12 + meta_total_len]
    json_bytes = meta_block[:-64]   # strip 64-byte sig slot
    try:
        meta = json.loads(json_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid metadata JSON: {exc}") from exc
    encrypted_pdf = data[12 + meta_total_len:]
    if not encrypted_pdf:
        raise ValueError("No encrypted PDF payload found in ATLAS file")
    return meta, encrypted_pdf

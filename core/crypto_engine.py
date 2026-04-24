"""
atlas_opener.core.crypto_engine  (Rust-backed via atlas_core.pyd)
==================================================================
Drop-in replacement for the pure-Python crypto_engine.py.

Public API is identical — every import in the codebase continues to work:
    from core.crypto_engine import CryptoEngine, build_atlas_container,
                                   check_crypto_deps, CryptoError,
                                   DecryptionError, MissingDependencyError

What runs in Rust (atlas_core.pyd):
    - PBKDF2-SHA256 key derivation        (factors.rs)
    - BLAKE3 keyfile hashing              (factors.rs)
    - TOTP secret hashing                 (factors.rs)
    - XOR-combine + HKDF-SHA256 stretch   (factors.rs)
    - AES-256-GCM encrypt / decrypt       (crypto.rs)
    - Hardware fingerprint derivation     (hwid.rs)

What stays in Python:
    - Reading keyfile path → bytes        (before passing to Rust)
    - Salt generation (secrets module)    (OS CSPRNG, already secure)
    - Atomic file write                   (pathlib)
    - Exception type re-mapping           (ValueError → DecryptionError)

Fallback:
    If atlas_core.pyd is missing, falls back to the pure-Python
    implementation using cryptography + blake3 + pyotp so the app
    remains runnable during development before the Rust crate is built.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.atlas_format import (
    AtlasConstants,
    atlas_read_file,
    atlas_write_file,
    parse_atlas_header,
)
from core.exceptions import AtlasViewerError

_log = logging.getLogger(__name__)

# ── Load Rust extension ───────────────────────────────────────────────────────
try:
    import atlas_core as _core
    _RUST = True
    _log.debug("atlas_core.pyd loaded — using Rust crypto engine")
except ImportError:
    _RUST = False
    _core = None  # type: ignore[assignment]
    _log.warning(
        "atlas_core.pyd not found — falling back to pure-Python crypto. "
        "Build the Rust crate: cd atlas_core && maturin develop --release"
    )

# ── Pure-Python optional deps (fallback only) ─────────────────────────────────
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

try:
    from blake3 import blake3 as _blake3
    _BLAKE3_OK = True
except ImportError:
    _BLAKE3_OK = False

try:
    import pyotp as _pyotp
    _PYOTP_OK = True
except ImportError:
    _PYOTP_OK = False


# ── Exceptions ────────────────────────────────────────────────────────────────

class CryptoError(AtlasViewerError):
    """Raised when any cryptographic operation fails."""

class DecryptionError(CryptoError):
    """Raised when decryption fails — wrong credentials or corrupt payload."""

class MissingDependencyError(CryptoError):
    """Raised when a required crypto library (or atlas_core.pyd) is missing."""


# ── Dependency check ──────────────────────────────────────────────────────────

def check_crypto_deps() -> None:
    """
    Raise MissingDependencyError if the crypto backend is unavailable.
    With atlas_core.pyd present, only the .pyd itself is required.
    Without it, checks for cryptography + blake3 + pyotp.
    """
    if _RUST:
        return  # Rust handles everything — no Python deps needed
    missing = []
    if not _CRYPTO_OK:
        missing.append("cryptography  (pip install cryptography)")
    if not _BLAKE3_OK:
        missing.append("blake3        (pip install blake3)")
    if not _PYOTP_OK:
        missing.append("pyotp         (pip install pyotp)")
    if missing:
        raise MissingDependencyError(
            "Missing required libraries for ATLAS encryption:\n  "
            + "\n  ".join(missing)
        )


# ── Internal: prepare factors dict for Rust ───────────────────────────────────

def _rust_factors(factors: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for key, val in factors.items():
        if key == "keyfile":
            p = Path(val)

            if not p.is_file():
                raise ValueError("invalid_keyfile")

            try:
                out[key] = p.read_bytes()
            except Exception:
                raise ValueError("invalid_keyfile")
        else:
            out[key] = val

    return out


def normalize_crypto_error(err: Exception) -> str:
    if isinstance(err, DecryptionError):
        payload = err.args[0]
        if isinstance(payload, dict):
            return payload.get("user_message", "Decryption failed.")
        return str(payload)
    return str(err)

# ── CryptoEngine ──────────────────────────────────────────────────────────────

class CryptoEngine:
    """
    Stateless cryptographic operations — delegates to Rust when available.

    Supported factor keys:
        "password" → str
        "keyfile"  → str  (filesystem path to binary key blob)
        "totp"     → str  (Base32-encoded TOTP secret, NOT 6-digit code)

    hwid_bind parameter (Rust path only):
        When True, the machine hardware fingerprint is mixed into key
        derivation. The resulting .atlas file can only be decrypted on
        the same machine. Default: False.
    """

    # ── Top-level entry point (called by AtlasDecryptWorker) ──────────────

    @staticmethod
    def extract_meta_and_decrypt(
        atlas_path: str,
        factors: Dict[str, Any],
        hwid_bind: bool = False,
    ) -> Tuple[Dict[str, Any], bytes]:
        """
        Parse .atlas file header and decrypt the payload.

        Args:
            atlas_path: path to the .atlas file
            factors:    {"password": str, "keyfile": str, "totp": str}
            hwid_bind:  True = require hardware fingerprint match

        Returns:
            (metadata dict, decrypted PDF bytes)

        Raises:
            ValueError:      malformed file or missing salt
            DecryptionError: wrong credentials
        """
        if _RUST:
            return CryptoEngine._extract_rust(atlas_path, factors, hwid_bind)
        return CryptoEngine._extract_python(atlas_path, factors)

    @staticmethod
    def _extract_rust(
        atlas_path: str,
        factors: Dict[str, Any],
        hwid_bind: bool,
    ) -> Tuple[Dict[str, Any], bytes]:
        """Rust-backed decrypt path."""
        data = bytes(_core.read_file(atlas_path))
        meta, encrypted_pdf = _core.parse_header(data)
        meta = dict(meta)
        encrypted_pdf = bytes(encrypted_pdf)

        if "salt" not in meta:
            raise ValueError("ATLAS metadata missing 'salt' field")
        try:
            salt = bytes.fromhex(meta["salt"])
        except Exception as exc:
            raise ValueError(f"Invalid salt in metadata: {exc}") from exc
        if len(salt) != 16:
            raise ValueError(f"Salt wrong length: {len(salt)} (expected 16)")

        # If file was created with hwid_bind=True, enforce it on decrypt
        effective_hwid = hwid_bind or bool(meta.get("hwid_bind", False))

        rust_f = _rust_factors(factors)
        try:
            plaintext = bytes(_core.decrypt_atlas(encrypted_pdf, rust_f, salt, effective_hwid))

        except ValueError as exc:
            parsed = CryptoEngine._parse_rust_error(str(exc))
            raise DecryptionError(
                {
                    "stage": "rust_decrypt",
                    "category": "auth_failure" if parsed["recoverable"] else "crypto_failure",
                    "reason": parsed["reason"],
                    "raw": str(exc),
                    "recoverable": parsed["recoverable"],
                    "user_message": CryptoEngine._to_user_message(parsed["reason"]),
                }
            ) from exc

        # ── Decompress after authenticated decryption ─────────────────────
        # compression_method defaults to "none" for containers created before
        # compression support was added (backward-compatible).
        compression_method = meta.get("compression_method", "none")
        if compression_method and compression_method != "none":
            from core.compression_engine import decompress
            try:
                plaintext = decompress(plaintext, compression_method)
            except Exception as exc:
                raise CryptoError(
                    f"Decryption succeeded but decompression failed "
                    f"(method={compression_method!r}): {exc}"
                ) from exc

        _log.info(
            "Decrypted %d bytes from %s (Rust, hwid_bind=%s, compression=%s)",
            len(plaintext), Path(atlas_path).name, effective_hwid, compression_method,
        )
        return meta, plaintext

    @staticmethod
    def _extract_python(
        atlas_path: str,
        factors: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], bytes]:
        """Pure-Python fallback decrypt path."""
        data = atlas_read_file(atlas_path, max_size=AtlasConstants.MAX_PDF_SIZE)
        meta, encrypted_pdf = parse_atlas_header(data)
        if "salt" not in meta:
            raise ValueError("ATLAS metadata missing 'salt' field")
        try:
            salt = bytes.fromhex(meta["salt"])
            if len(salt) != AtlasConstants.HKDF_SALT_LEN:
                raise ValueError(f"Salt wrong length: {len(salt)}")
        except Exception as exc:
            raise ValueError(f"Invalid salt in metadata: {exc}") from exc
        plaintext = CryptoEngine.decrypt_pdf(encrypted_pdf, factors, salt)

        # ── Decompress after authenticated decryption ─────────────────────
        compression_method = meta.get("compression_method", "none")
        if compression_method and compression_method != "none":
            from core.compression_engine import decompress
            try:
                plaintext = decompress(plaintext, compression_method)
            except Exception as exc:
                raise CryptoError(
                    f"Decryption succeeded but decompression failed "
                    f"(method={compression_method!r}): {exc}"
                ) from exc

        return meta, plaintext

    # ── Low-level encrypt / decrypt (used by both paths + build_atlas_container) ──

    @staticmethod
    def decrypt_pdf(
        payload: bytes,
        factors: Dict[str, Any],
        salt: bytes,
        hwid_bind: bool = False,
    ) -> bytes:
        """
        Decrypt an AES-256-GCM payload.

        Raises DecryptionError on wrong credentials.
        """
        if _RUST:
            rust_f = _rust_factors(factors)
            try:
                return bytes(_core.decrypt_atlas(payload, rust_f, salt, hwid_bind))

            except ValueError as exc:
                parsed = CryptoEngine._parse_rust_error(str(exc))
                raise DecryptionError(
                    {
                        "stage": "rust_decrypt",
                        "category": "auth_failure" if parsed["recoverable"] else "crypto_failure",
                        "reason": parsed["reason"],
                        "raw": str(exc),
                        "recoverable": parsed["recoverable"],
                        "user_message": CryptoEngine._to_user_message(parsed["reason"]),
                    }
                ) from exc

        # Pure-Python fallback
        return CryptoEngine._decrypt_python(payload, factors, salt)

    @staticmethod
    def encrypt_pdf(
        pdf_path: str,
        factors: Dict[str, Any],
        salt: bytes,
        hwid_bind: bool = False,
    ) -> Tuple[bytes, bytes]:
        """Read a PDF from disk and encrypt it. Returns (payload, salt)."""
        if _RUST:
            pdf_bytes = Path(pdf_path).read_bytes()
            rust_f = _rust_factors(factors)
            try:
                payload = bytes(_core.encrypt_atlas(pdf_bytes, rust_f, salt, hwid_bind))
            except ValueError as exc:
                raise CryptoError(str(exc)) from exc
            return payload, salt
        # Pure-Python fallback
        return CryptoEngine._encrypt_python(pdf_path, factors, salt)

    # ── Pure-Python fallback implementations ──────────────────────────────

    @staticmethod
    def _encrypt_python(
        pdf_path: str,
        factors: Dict[str, Any],
        salt: bytes,
    ) -> Tuple[bytes, bytes]:
        if not _CRYPTO_OK:
            raise MissingDependencyError("cryptography is required (pip install cryptography)")
        pdf_content = atlas_read_file(pdf_path, max_size=AtlasConstants.MAX_PDF_SIZE)
        components  = CryptoEngine._get_ordered_components(factors, salt)
        key = CryptoEngine._combine_factors(components, salt)
        iv  = secrets.token_bytes(AtlasConstants.AES_IV_LEN)
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
        enc = cipher.encryptor()
        ct  = enc.update(pdf_content) + enc.finalize()
        return iv + ct + enc.tag, salt

    @staticmethod
    def _decrypt_python(
        payload: bytes,
        factors: Dict[str, Any],
        salt: bytes,
    ) -> bytes:
        if not _CRYPTO_OK:
            raise MissingDependencyError("cryptography is required (pip install cryptography)")
        min_len = AtlasConstants.AES_IV_LEN + AtlasConstants.GCM_TAG_LEN
        if len(payload) < min_len:
            raise ValueError("Encrypted payload too short")
        iv  = payload[:AtlasConstants.AES_IV_LEN]
        tag = payload[-AtlasConstants.GCM_TAG_LEN:]
        ct  = payload[AtlasConstants.AES_IV_LEN: -AtlasConstants.GCM_TAG_LEN]
        components = CryptoEngine._get_ordered_components(factors, salt)
        key = CryptoEngine._combine_factors(components, salt)
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
        dec = cipher.decryptor()
        try:
            return dec.update(ct) + dec.finalize()
        except Exception as exc:
            _log.error("Decryption authentication failed: %s", exc)
            raise DecryptionError(
                "Decryption failed — wrong password, keyfile, or TOTP secret."
            ) from exc

    @staticmethod
    def _get_ordered_components(factors: Dict[str, Any], salt: bytes) -> List[bytes]:
        components: List[bytes] = []
        for key in sorted(factors.keys()):
            if key == "password":
                components.append(CryptoEngine._derive_password(factors[key], salt))
            elif key == "keyfile":
                components.append(CryptoEngine._derive_keyfile(factors[key]))
            elif key == "totp":
                components.append(CryptoEngine._derive_totp(factors[key]))
        return components

    @staticmethod
    def _derive_password(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            AtlasConstants.PBKDF2_HASH,
            password.encode("utf-8"),
            salt,
            iterations=AtlasConstants.PBKDF2_ITERATIONS,
            dklen=AtlasConstants.ARGON2_HASH_LEN,
        )

    @staticmethod
    def _derive_keyfile(keyfile_path: str) -> bytes:
        if not _BLAKE3_OK:
            raise MissingDependencyError("blake3 is required (pip install blake3)")
        data = atlas_read_file(keyfile_path, max_size=AtlasConstants.MAX_KEYFILE_SIZE)
        h = _blake3()
        h.update(data)
        return h.digest(32)

    @staticmethod
    def _derive_totp(secret: str) -> bytes:
        if not _PYOTP_OK:
            raise MissingDependencyError("pyotp is required (pip install pyotp)")
        clean = secret.replace(" ", "").replace("-", "").upper()
        _pyotp.TOTP(clean).now()   # validate Base32
        return hashlib.sha256(f"ATLAS_TOTP_v2_{clean}".encode()).digest()

    @staticmethod
    def _combine_factors(components: List[bytes], salt: bytes) -> bytes:
        if not _CRYPTO_OK:
            raise MissingDependencyError("cryptography is required (pip install cryptography)")
        combined = bytearray(32)
        for c in components:
            for i, b in enumerate(c[:32]):
                combined[i] ^= b
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=AtlasConstants.AES_KEY_LEN,
            salt=salt,
            info=AtlasConstants.HKDF_INFO,
            backend=default_backend(),
        )
        return hkdf.derive(bytes(combined))

    @staticmethod
    def _parse_rust_error(msg: str) -> dict:
        msg_lower = msg.lower()

        if "wrong password" in msg_lower:
            return {"reason": "wrong_password", "recoverable": True}

        if "keyfile" in msg_lower:
            return {"reason": "invalid_keyfile", "recoverable": True}

        if "totp" in msg_lower:
            return {"reason": "invalid_totp", "recoverable": True}

        if "magic header" in msg_lower:
            return {"reason": "invalid_file_format", "recoverable": False}

        if "metadata" in msg_lower:
            return {"reason": "corrupt_metadata", "recoverable": False}

        if "payload too short" in msg_lower:
            return {"reason": "corrupt_payload", "recoverable": False}

        if "salt" in msg_lower:
            return {"reason": "invalid_salt", "recoverable": False}

        return {"reason": "unknown_rust_error", "recoverable": False}

    @staticmethod
    def _to_user_message(reason: str) -> str:
        """Map internal reason codes to user-facing error messages."""
        _messages: Dict[str, str] = {
            "wrong_password":      "Incorrect password. Please try again.",
            "invalid_keyfile":     "The keyfile is missing, unreadable, or incorrect.",
            "invalid_totp":        "Invalid TOTP secret. Ensure you are using the Base32 secret, not a 6-digit code.",
            "invalid_file_format": "This file is not a valid ATLAS container.",
            "corrupt_metadata":    "The ATLAS container metadata is corrupt or has been tampered with.",
            "corrupt_payload":     "The encrypted payload is corrupt or truncated.",
            "invalid_salt":        "The ATLAS container salt is missing or malformed.",
            "unknown_rust_error":  "An unexpected cryptographic error occurred.",
        }
        return _messages.get(reason, "Decryption failed.")


# ── Atlas container builder ───────────────────────────────────────────────────

def build_atlas_container(
    pdf_path: str,
    factors: Dict[str, Any],
    output_path: str,
    app_version: str = "2.0.0",
    hwid_bind: bool = False,
    compression_method: str = "zlib",
    compression_level: int = 6,
    auto_detect_compression: bool = True,
) -> Path:
    """
    Compress then encrypt a PDF and write a complete .atlas container file.

    Compression is applied BEFORE encryption so the plaintext is smaller
    before AES-256-GCM processes it.  The method and level are stored in
    the container metadata so extract_meta_and_decrypt() can decompress
    transparently on open.

    Args:
        pdf_path:                path to plaintext source PDF
        factors:                 authentication factors dict
        output_path:             destination .atlas file path
        app_version:             version string embedded in metadata
        hwid_bind:               if True, output is machine-locked to current hardware
        compression_method:      "none", "zlib", "lzma", or "zstd"
        compression_level:       1 (fastest) – 9 (smallest)
        auto_detect_compression: skip compression for already-compressed data

    Returns:
        Path: written output path
    """
    from core.compression_engine import compress, CompressionMethod
    check_crypto_deps()

    # ── Compress before encryption ─────────────────────────────────────────
    pdf_bytes = Path(pdf_path).read_bytes()
    try:
        method_enum = CompressionMethod(compression_method)
    except ValueError:
        method_enum = CompressionMethod("none")

    comp_result = compress(
        pdf_bytes,
        method=method_enum,
        level=compression_level,
        auto_detect=auto_detect_compression,
    )
    compressed_bytes  = comp_result.data
    actual_method_str = comp_result.method   # may differ if auto-skip fired

    # Write the compressed bytes to a temp file so CryptoEngine.encrypt_pdf
    # can read it via its existing pdf_path: str interface.
    import tempfile, os
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(compressed_bytes)
        salt = secrets.token_bytes(AtlasConstants.HKDF_SALT_LEN)
        payload, _ = CryptoEngine.encrypt_pdf(tmp_path, factors, salt, hwid_bind)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    meta: Dict[str, Any] = {
        "salt":               salt.hex(),
        "factors":            sorted(factors.keys()),
        "hwid_bind":          hwid_bind,
        "compression_method": actual_method_str,
        "compression_level":  compression_level,
        "created":            datetime.now(UTC).isoformat(),
        "atlas_version":      AtlasConstants.FORMAT_VERSION,
        "app_version":        app_version,
    }

    if _RUST:
        # Rust assembles the container (JSON sort + magic header + sig slot)
        container_bytes = bytes(_core.build_container(meta, payload))
    else:
        # Pure-Python container assembly (matches Rust layout exactly)
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        signing_key   = ed25519.Ed25519PrivateKey.generate()
        verifying_key = signing_key.public_key()
        meta["signer_pubkey"] = verifying_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()
        meta_bytes = json.dumps(meta, separators=(",", ":"), sort_keys=True).encode()
        signature  = signing_key.sign(meta_bytes)
        meta_total = len(meta_bytes) + len(signature)
        if meta_total > AtlasConstants.MAX_METADATA_SIZE:
            raise CryptoError(f"Metadata block too large: {meta_total} bytes")
        container_bytes = (
            AtlasConstants.ATLAS_MAGIC
            + struct.pack(">I", meta_total)
            + meta_bytes
            + signature
            + payload
        )

    out = atlas_write_file(output_path, container_bytes, atomic=True)
    _log.info(
        "ATLAS container written: %s  (%d bytes, hwid_bind=%s)",
        out.name, out.stat().st_size, hwid_bind,
    )
    return out
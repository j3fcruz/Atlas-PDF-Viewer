"""
atlas_viewer.core.compression_engine
======================================
Lossless compression layer for the ATLAS container format.

Design principles
-----------------
1. Compression ALWAYS precedes encryption.  The compressed payload is what
   AES-256-GCM encrypts.  Encrypted data is statistically indistinguishable
   from random bytes and cannot be compressed after the fact.

2. The compression method and level are stored in the ATLAS container metadata
   so the decompressor knows exactly how to reverse the operation.

3. Auto-detection: if the input file's entropy ratio suggests it is already
   compressed (images, ZIPs, already-compressed PDFs), compression is skipped
   automatically and the ``"none"`` method is stored.

4. All methods produce byte-identical round-trips:
       decompress(compress(data, method, level)) == data

Supported methods
-----------------
  "none"  — pass-through (no compression)
  "zlib"  — RFC 1950 DEFLATE-based, stdlib zlib.  Best for text-heavy PDFs.
  "lzma"  — LZMA/XZ, stdlib lzma.  Highest ratio, slowest.
  "zstd"  — Zstandard (requires zstandard package).  Best speed/ratio balance.

Compression levels
------------------
  All methods use levels 1–9 (1 = fastest, 9 = smallest).
  zstd levels are mapped to its own 1–22 scale proportionally (1→1, 9→22).
  lzma presets are mapped 1:1 to 0–9 (level 1 → preset 0, level 9 → preset 8).

Format
------
The compressed blob is a simple length-prefixed structure so the decompressor
can verify the original size:

    original_size (8 bytes, big-endian uint64)
    compressed_data (variable)

The 8-byte prefix is included in the AES-GCM ciphertext (so it is authenticated
along with the content).  It is NOT stored in the outer ATLAS metadata —
that contains only the method name and level as JSON strings.

Detection heuristic
-------------------
We measure entropy by compressing a 64 KB sample at level 1 with zlib.
If the compressed sample is ≥ 95% of the original sample, the file is
classified as "already compressed" and we fall back to method "none".
"""

from __future__ import annotations

import logging
import struct
import zlib
from enum import Enum
from typing import NamedTuple, Optional, Tuple

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: zstd
# ---------------------------------------------------------------------------

try:
    import zstandard as _zstd
    _ZSTD_AVAILABLE = True
except ImportError:
    _ZSTD_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

class CompressionMethod(str, Enum):
    """Supported compression methods for ATLAS containers."""
    NONE = "none"
    ZLIB = "zlib"
    LZMA = "lzma"
    ZSTD = "zstd"

    @property
    def display_name(self) -> str:
        return {
            "none": "None (no compression)",
            "zlib": "zlib  (DEFLATE — fast, widely supported)",
            "lzma": "lzma  (XZ — highest ratio, slower)",
            "zstd": "zstd  (Zstandard — best speed/ratio balance)",
        }[self.value]

    @property
    def is_available(self) -> bool:
        if self == CompressionMethod.ZSTD:
            return _ZSTD_AVAILABLE
        return True  # zlib and lzma are stdlib


# Default: zlib level 6 — best general-purpose trade-off
DEFAULT_METHOD: CompressionMethod = CompressionMethod.ZLIB
DEFAULT_LEVEL:  int = 6

# Entropy threshold: if compressed/original ≥ this ratio, file is already compressed
_ALREADY_COMPRESSED_THRESHOLD: float = 0.95
# Sample size for entropy detection
_DETECTION_SAMPLE_BYTES: int = 65_536  # 64 KB

# Original-size prefix length
_SIZE_PREFIX_LEN: int = 8


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class CompressionResult(NamedTuple):
    """Metadata about a completed compression operation."""
    method:          str    # CompressionMethod value
    level:           int
    original_size:   int    # bytes before compression
    compressed_size: int    # bytes after compression (excl. 8-byte prefix)
    data:            bytes  # prefix(8) + compressed_data
    skipped:         bool   # True if auto-detect chose method="none"

    @property
    def ratio(self) -> float:
        """Compression ratio: compressed / original (lower = better)."""
        if self.original_size == 0:
            return 1.0
        return (self.compressed_size + _SIZE_PREFIX_LEN) / self.original_size

    @property
    def space_saving_pct(self) -> float:
        """Percentage of space saved (0–100, negative if expansion)."""
        return (1.0 - self.ratio) * 100.0

    def summary(self) -> str:
        """Human-readable one-line summary."""
        if self.skipped:
            return (
                f"Compression skipped (file already compressed) — "
                f"{self.original_size:,} bytes passed through"
            )
        return (
            f"{self.method} level {self.level}: "
            f"{self.original_size:,} → {self.compressed_size:,} bytes "
            f"({self.space_saving_pct:+.1f}%)"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compress(
    data:        bytes,
    method:      "str | CompressionMethod" = DEFAULT_METHOD,
    level:       int = DEFAULT_LEVEL,
    auto_detect: bool = True,
) -> CompressionResult:
    """
    Compress *data* using the specified method and level.

    Args:
        data:        Raw input bytes (plaintext PDF or any binary file).
        method:      Compression method name or CompressionMethod enum.
                     One of: "none", "zlib", "lzma", "zstd".
        level:       Compression level 1–9 (1=fastest, 9=smallest).
        auto_detect: If True and the file appears already compressed,
                     switch to method "none" automatically.

    Returns:
        CompressionResult containing the compressed blob and metadata.

    Raises:
        ValueError:          Unknown method, invalid level, or empty data.
        RuntimeError:        Compression produced corrupt output.
        ImportError:         zstd requested but zstandard not installed.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("data must be bytes or bytearray")
    if not data:
        raise ValueError("Cannot compress empty data")

    level = _validate_level(level)
    method = CompressionMethod(str(method).lower()) if not isinstance(method, CompressionMethod) else method

    if method == CompressionMethod.ZSTD and not _ZSTD_AVAILABLE:
        raise ImportError(
            "zstd compression requires the zstandard package: "
            "pip install zstandard"
        )

    original_size = len(data)
    skipped = False

    # Auto-detection: check if the data is already compressed
    if auto_detect and method != CompressionMethod.NONE:
        if _is_already_compressed(data):
            _log.info(
                "CompressionEngine: auto-detect found pre-compressed data "
                "(%d bytes) — switching to method=none", original_size,
            )
            method  = CompressionMethod.NONE
            skipped = True

    # Compress
    if method == CompressionMethod.NONE:
        compressed = data
    elif method == CompressionMethod.ZLIB:
        compressed = _compress_zlib(data, level)
    elif method == CompressionMethod.LZMA:
        compressed = _compress_lzma(data, level)
    elif method == CompressionMethod.ZSTD:
        compressed = _compress_zstd(data, level)
    else:
        raise ValueError(f"Unknown compression method: {method!r}")

    # Sanity check: round-trip must be byte-identical
    _verify_roundtrip(data, compressed, method)

    # Prepend original size for decompression
    blob = struct.pack(">Q", original_size) + compressed

    result = CompressionResult(
        method         = method.value,
        level          = level,
        original_size  = original_size,
        compressed_size= len(compressed),
        data           = blob,
        skipped        = skipped,
    )

    _log.info("CompressionEngine.compress: %s", result.summary())
    return result


def decompress(blob: bytes, method: "str | CompressionMethod") -> bytes:
    """
    Decompress a blob produced by :func:`compress`.

    Args:
        blob:   Compressed blob: size_prefix(8) + compressed_data.
        method: The compression method used during encryption (from metadata).

    Returns:
        bytes: Original uncompressed data (byte-identical to input of compress).

    Raises:
        ValueError:   Blob too short, size prefix mismatch, unknown method.
        RuntimeError: Decompression produced wrong number of bytes.
    """
    if not isinstance(blob, (bytes, bytearray)):
        raise ValueError("blob must be bytes")
    if len(blob) < _SIZE_PREFIX_LEN:
        raise ValueError(
            f"Compressed blob too short ({len(blob)} bytes); "
            f"expected at least {_SIZE_PREFIX_LEN} bytes"
        )

    method = CompressionMethod(str(method).lower()) if not isinstance(method, CompressionMethod) else method

    expected_size = struct.unpack(">Q", blob[:_SIZE_PREFIX_LEN])[0]
    compressed    = blob[_SIZE_PREFIX_LEN:]

    if method == CompressionMethod.NONE:
        plaintext = bytes(compressed)
    elif method == CompressionMethod.ZLIB:
        plaintext = _decompress_zlib(compressed)
    elif method == CompressionMethod.LZMA:
        plaintext = _decompress_lzma(compressed)
    elif method == CompressionMethod.ZSTD:
        if not _ZSTD_AVAILABLE:
            raise ImportError(
                "This ATLAS file was compressed with zstd.  "
                "Install zstandard to open it: pip install zstandard"
            )
        plaintext = _decompress_zstd(compressed)
    else:
        raise ValueError(f"Unknown compression method: {method!r}")

    # Size verification
    if len(plaintext) != expected_size:
        raise RuntimeError(
            f"Decompression size mismatch: expected {expected_size:,} bytes, "
            f"got {len(plaintext):,} bytes — file may be corrupt"
        )

    _log.info(
        "CompressionEngine.decompress: %s  %d → %d bytes",
        method.value, len(compressed), len(plaintext),
    )
    return plaintext


def detect_compression(data: bytes) -> bool:
    """
    Return True if the data appears to already be compressed.

    Uses a fast zlib level-1 sample test: if the compressed sample is
    ≥ 95% of the original, the file is classified as already compressed.
    """
    return _is_already_compressed(data)


def available_methods() -> list[CompressionMethod]:
    """Return all CompressionMethod values that are usable in this environment."""
    return [m for m in CompressionMethod if m.is_available]


# ---------------------------------------------------------------------------
# Internal helpers — compression
# ---------------------------------------------------------------------------

def _validate_level(level: int) -> int:
    if not isinstance(level, int) or not 1 <= level <= 9:
        raise ValueError(f"Compression level must be 1–9; got {level!r}")
    return level


def _is_already_compressed(data: bytes) -> bool:
    """
    Entropy heuristic: compress a sample at maximum speed.
    If the result is >= threshold of original, the data is incompressible.
    """
    sample = data[:_DETECTION_SAMPLE_BYTES]
    if len(sample) < 512:
        # Too small to test reliably — attempt compression anyway
        return False
    try:
        compressed_sample = zlib.compress(sample, level=1)
        ratio = len(compressed_sample) / len(sample)
        already = ratio >= _ALREADY_COMPRESSED_THRESHOLD
        _log.debug(
            "_is_already_compressed: sample=%d ratio=%.3f already=%s",
            len(sample), ratio, already,
        )
        return already
    except Exception:
        return False  # on any error, attempt normal compression


def _compress_zlib(data: bytes, level: int) -> bytes:
    """zlib DEFLATE compression (RFC 1950 format)."""
    return zlib.compress(data, level=level)


def _compress_lzma(data: bytes, level: int) -> bytes:
    """LZMA/XZ compression.  Level 1–9 mapped to preset 0–8."""
    import lzma
    preset = max(0, min(8, level - 1))
    return lzma.compress(data, format=lzma.FORMAT_XZ, preset=preset)


def _compress_zstd(data: bytes, level: int) -> bytes:
    """Zstandard compression.  Level 1–9 mapped to zstd 1–22."""
    # Map 1–9 linearly to zstd 1–22
    zstd_level = 1 + int((level - 1) * (21 / 8))
    cctx = _zstd.ZstdCompressor(level=zstd_level)
    return cctx.compress(data)


# ---------------------------------------------------------------------------
# Internal helpers — decompression
# ---------------------------------------------------------------------------

def _decompress_zlib(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except zlib.error as exc:
        raise ValueError(f"zlib decompression failed: {exc}") from exc


def _decompress_lzma(data: bytes) -> bytes:
    import lzma
    try:
        return lzma.decompress(data, format=lzma.FORMAT_XZ)
    except lzma.LZMAError as exc:
        raise ValueError(f"lzma decompression failed: {exc}") from exc


def _decompress_zstd(data: bytes) -> bytes:
    try:
        dctx = _zstd.ZstdDecompressor()
        return dctx.decompress(data)
    except Exception as exc:
        raise ValueError(f"zstd decompression failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Round-trip verification
# ---------------------------------------------------------------------------

def _verify_roundtrip(
    original:   bytes,
    compressed: bytes,
    method:     CompressionMethod,
) -> None:
    """
    Decompress *compressed* and verify it equals *original*.

    Called after every compression to catch silent corruption bugs.
    Raises RuntimeError if the round-trip fails.
    """
    try:
        if method == CompressionMethod.NONE:
            recovered = compressed
        elif method == CompressionMethod.ZLIB:
            recovered = _decompress_zlib(compressed)
        elif method == CompressionMethod.LZMA:
            recovered = _decompress_lzma(compressed)
        elif method == CompressionMethod.ZSTD:
            recovered = _decompress_zstd(compressed)
        else:
            return  # unknown method — skip check

        if recovered != original:
            raise RuntimeError(
                f"Round-trip verification failed for method={method.value}: "
                f"original {len(original)} bytes != recovered {len(recovered)} bytes"
            )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Round-trip verification error ({method.value}): {exc}"
        ) from exc

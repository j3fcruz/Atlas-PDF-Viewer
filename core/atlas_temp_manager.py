"""
atlas_viewer.core.atlas_temp_manager  — RETIRED
================================================
This module is retained as a tombstone to prevent import errors from any
code that was not yet updated.

AtlasTempManager has been REMOVED in the v8 security refactor.

Why it was removed
------------------
The original AtlasTempManager wrote decrypted PDF bytes to a
``NamedTemporaryFile`` on disk so that QPdfDocument could load them via
``QPdfDocument.load(path)``.  This created a critical security flaw:

  * Decrypted plaintext existed on disk, even briefly.
  * Crash = permanent forensic artefact in the temp directory.
  * Zero-fill on delete is ineffective on SSDs (wear-levelling).
  * File could be intercepted by any process with temp-dir read access.

The replacement architecture uses ``QPdfDocument.loadFromData(QByteArray)``
which loads the PDF entirely from process memory.  No file is ever created.

If you see an ImportError for AtlasTempManager, the calling code has not
been updated to the v8 pipeline.  Check pdf_viewer_tab.py — the import
and all usages should have been removed.

Raise an error on instantiation so regressions are caught immediately.
"""

from __future__ import annotations


class AtlasTempManager:
    """
    RETIRED — raises RuntimeError on instantiation.

    Kept only so ``from core.atlas_temp_manager import AtlasTempManager``
    does not cause an ImportError in code that has not been updated.

    If this error appears at runtime, the calling module still contains
    old v7 code and must be updated to use the memory-only pipeline.
    """

    def __init__(self) -> None:
        raise RuntimeError(
            "AtlasTempManager has been removed in the v8 security refactor.\n"
            "Use QtPdfEngine.load_from_bytes() instead.\n"
            "See core/atlas_temp_manager.py for migration notes."
        )

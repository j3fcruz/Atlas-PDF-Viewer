"""
atlas_viewer.services.bookmark_service
=========================================
BookmarkService — extracts and manages the PDF bookmark (outline) tree.

Responsibility
--------------
Separated from :class:`~atlas_viewer.services.document_service.DocumentService`
to follow the Single Responsibility Principle.  This service owns all
bookmark-related logic: retrieval, caching, counting, and search.

Caching
-------
The first call to :meth:`get_tree` caches the result.  Pass
``force_refresh=True`` after a document reload to bypass the cache.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from core.document_engine import AbstractDocumentEngine
from core.exceptions import DocumentLoadError
from models import BookmarkNode
from utils import get_logger, perf_timer

_log = get_logger(__name__)


class BookmarkService:
    """
    Extracts hierarchical bookmarks from an open document engine.

    Usage::

        svc = BookmarkService(engine)
        roots = svc.get_tree()         # List[BookmarkNode]
        print(svc.total_count())       # 42
        found = svc.search("chapter")  # List[BookmarkNode]
    """

    def __init__(self, engine: AbstractDocumentEngine) -> None:
        self._engine = engine
        self._cached: Optional[List[BookmarkNode]] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def get_tree(self, force_refresh: bool = False) -> List[BookmarkNode]:
        """
        Return the complete bookmark tree.

        Results are cached after the first call.  Pass ``force_refresh=True``
        to re-read from the engine (e.g. after a document reload).

        Args:
            force_refresh: Bypass cache and re-read from engine.

        Returns:
            List[BookmarkNode]: Top-level nodes; each may have ``.children``.

        Raises:
            DocumentLoadError: No document is open.
        """
        if self._cached is not None and not force_refresh:
            return self._cached

        if not self._engine.is_open():
            raise DocumentLoadError(
                "No document is open in BookmarkService.get_tree()."
            )

        with perf_timer(_log, "bookmark extraction"):
            nodes = self._engine.get_bookmarks()

        root_count = len(nodes)
        total = sum(1 + n.total_descendants() for n in nodes)
        _log.debug("Bookmark tree: %d root nodes, %d total entries.", root_count, total)

        self._cached = nodes
        return nodes

    def has_bookmarks(self) -> bool:
        """
        Return ``True`` if the document has at least one bookmark.

        Returns:
            bool: ``True`` if the bookmark tree is non-empty.
        """
        return len(self.get_tree()) > 0

    def total_count(self) -> int:
        """
        Count total bookmark nodes across the entire tree.

        Returns:
            int: Total node count (including nested entries).
        """
        def _count(nodes: List[BookmarkNode]) -> int:
            return sum(1 + _count(n.children) for n in nodes)
        return _count(self.get_tree())

    def search(self, query: str, case_sensitive: bool = False) -> List[BookmarkNode]:
        """
        Search bookmark titles for a query string.

        Performs a substring search across the full tree.  Does not modify
        the tree structure — returns a flat list of matching nodes.

        Args:
            query:          Search string.
            case_sensitive: If ``False`` (default), comparison is lower-cased.

        Returns:
            List[BookmarkNode]: Matching bookmark nodes (flattened).
        """
        if not query:
            return []
        q = query if case_sensitive else query.lower()
        results: List[BookmarkNode] = []

        def _walk(nodes: List[BookmarkNode]) -> None:
            for node in nodes:
                title = node.title if case_sensitive else node.title.lower()
                if q in title:
                    results.append(node)
                _walk(node.children)

        _walk(self.get_tree())
        return results

    def iter_all(self) -> Iterator[BookmarkNode]:
        """
        Yield every :class:`~atlas_viewer.models.BookmarkNode` in DFS order.

        Yields:
            BookmarkNode: Each node in depth-first order.
        """
        def _walk(nodes: List[BookmarkNode]) -> Iterator[BookmarkNode]:
            for node in nodes:
                yield node
                yield from _walk(node.children)

        yield from _walk(self.get_tree())

    def invalidate_cache(self) -> None:
        """
        Clear the cached bookmark data.

        Call after a document is reloaded to force re-extraction on
        the next :meth:`get_tree` call.
        """
        self._cached = None
        _log.debug("Bookmark cache invalidated.")

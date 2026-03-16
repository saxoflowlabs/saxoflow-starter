# saxoflow/teach/retrieval.py
"""
Stable retrieval interface for the SaxoFlow tutoring subsystem.

This module exposes exactly one public function: :func:`retrieve_chunks`.
All callers (``TutorAgent``, ``cli.py``, future components) use this
function exclusively.  The BM25 backend in ``DocIndex`` may be swapped
for dense-embedding retrieval without changing this function or any caller.

Upgrade path to embeddings
---------------------------
1. Replace ``DocIndex.retrieve()`` implementation with a vector-store
   lookup (e.g. ``chromadb``, ``faiss-cpu``, ``sentence-transformers``).
2. This file requires **zero changes**.
3. All callers require **zero changes**.

Python: 3.9+
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from saxoflow.teach.indexer import Chunk, DocIndex

if TYPE_CHECKING:
    from saxoflow.teach.session import TeachSession

__all__ = ["retrieve_chunks", "get_index"]

logger = logging.getLogger("saxoflow.teach.retrieval")

# Module-level cache: {pack_id: DocIndex} avoids rebuilding the index on
# every call within the same Python process.
_INDEX_CACHE: dict = {}


def get_index(session: "TeachSession") -> DocIndex:
    """Return the cached (or freshly built) :class:`DocIndex` for *session*.

    The index is loaded once per pack per process.  Call this instead of
    constructing :class:`DocIndex` directly so cache coherence is maintained.
    """
    pack_id = session.pack.id
    if pack_id not in _INDEX_CACHE:
        idx = DocIndex(session.pack)
        try:
            idx.load_or_build()
        except Exception as exc:
            logger.warning("Could not load/build index for '%s': %s", pack_id, exc)
        _INDEX_CACHE[pack_id] = idx
    return _INDEX_CACHE[pack_id]


def retrieve_chunks(
    session: "TeachSession",
    query: str,
    top_k: int = 3,
) -> List[Chunk]:
    """Return the *top_k* document chunks most relevant to *query*.

    This is the **single retrieval call site** for the tutoring system.
    ``TutorAgent`` calls this; nothing else.

    Parameters
    ----------
    session:
        Active :class:`~saxoflow.teach.session.TeachSession`.  Provides
        the pack reference needed to look up the pre-built index.
    query:
        Composed retrieval query string.  Typically
        ``f"{step.title} {step.goal} {student_input}"``.
    top_k:
        Maximum number of chunks to return (default 3).

    Returns
    -------
    list[Chunk]
        Ranked list of :class:`~saxoflow.teach.indexer.Chunk` objects;
        most relevant first.  Returns an empty list if no index is built.

    Notes
    -----
    The index is loaded once per pack per process and cached in
    ``_INDEX_CACHE``.  Callers do not need to manage index lifecycle.
    """
    pack_id = session.pack.id

    if pack_id not in _INDEX_CACHE:
        idx = DocIndex(session.pack)
        try:
            idx.load_or_build()
        except Exception as exc:  # pragma: no cover - dependency missing etc.
            logger.warning(
                "Could not load/build index for pack '%s': %s -- returning no chunks.",
                pack_id,
                exc,
            )
            return []
        _INDEX_CACHE[pack_id] = idx

    index: DocIndex = _INDEX_CACHE[pack_id]
    try:
        return index.retrieve(query, top_k=top_k)
    except Exception as exc:  # pragma: no cover
        logger.error("Retrieval error: %s", exc)
        return []


def invalidate_cache(pack_id: str | None = None) -> None:
    """Remove a pack's index from the in-process cache.

    Parameters
    ----------
    pack_id:
        Specific pack to invalidate.  If ``None`` the entire cache is
        cleared (useful in tests).
    """
    if pack_id is None:
        _INDEX_CACHE.clear()
    else:
        _INDEX_CACHE.pop(pack_id, None)

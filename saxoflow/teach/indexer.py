# saxoflow/teach/indexer.py
"""
Document indexer for the SaxoFlow tutoring subsystem.

Extracts text from PDF and Markdown documents in a teaching pack,
chunks the text into retrieval-sized passages, and builds a BM25 index
for fast keyword-based retrieval.

Architecture contract
---------------------
- The ``DocIndex.retrieve()`` signature is **frozen**.  The BM25 backend
  may be replaced with dense embeddings later without changing any caller.
- Chunking strategy: paragraph-based (split on ``\\n\\n``) with a target
  of 250-400 words per chunk; longer paragraphs are split at sentence
  boundaries.
- The index is persisted as a pickle file under
  ``.saxoflow/teach/index/<pack_id>.pkl`` so re-indexing only occurs when
  explicitly requested.

Dependencies
-------------
- ``pypdf`` (PDF extraction, pure Python)
- ``rank-bm25`` (BM25 retrieval, pure Python)

Both packages must be installed: ``pip install pypdf rank-bm25``

Python: 3.9+
"""

from __future__ import annotations

import logging
import pickle
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Module-level import so the rank_bm25 C-extension (numpy) is loaded once
# at import time, before pytest plugins (langsmith/coverage) can create a
# partial numpy sys.modules entry that triggers "cannot load module more
# than once per process" on the C-extension side.
try:
    from rank_bm25 import BM25Okapi as _BM25Okapi  # type: ignore[import]
    _HAS_BM25 = True
except Exception:  # pragma: no cover
    _BM25Okapi = None  # type: ignore[assignment]
    _HAS_BM25 = False

__all__ = ["DocIndex", "Chunk", "IndexBuildError"]

logger = logging.getLogger("saxoflow.teach.indexer")

# Maximum words per chunk before forced sentence-boundary split.
_MAX_CHUNK_WORDS = 400
# Target minimum words; smaller chunks are merged with the next.
_MIN_CHUNK_WORDS = 60

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """A single retrievable document passage.

    Attributes
    ----------
    text:
        The passage text (cleaned, no excessive whitespace).
    source_doc:
        Filename of the originating document (e.g. ``"ethz_tutorial.pdf"``).
    page_num:
        1-based page number for PDF sources; ``-1`` for Markdown.
    section_hint:
        Nearest heading text above this chunk, if detectable.
    chunk_index:
        Position of this chunk in the full document chunk sequence.
    """

    text: str
    source_doc: str
    page_num: int = -1
    section_hint: str = ""
    chunk_index: int = 0


class IndexBuildError(RuntimeError):
    """Raised when the index cannot be built (missing dependency etc.)."""


# ---------------------------------------------------------------------------
# DocIndex
# ---------------------------------------------------------------------------


class DocIndex:
    """BM25 index over all documents in a teaching pack.

    Usage
    -----
    .. code-block:: python

        idx = DocIndex(pack)
        idx.build()          # one-time; or call load_or_build()
        chunks = idx.retrieve("run icarus simulation", top_k=3)
    """

    _INDEX_DIR = Path(".saxoflow") / "teach" / "index"

    def __init__(self, pack) -> None:  # pack: PackDef to avoid circular import
        self._pack = pack
        self._index_path = self._INDEX_DIR / f"{pack.id}.pkl"
        self._chunks: List[Chunk] = []
        self._bm25 = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> None:
        """Extract text, chunk all pack documents, and build the BM25 index.

        Persists the index to disk.  Subsequent calls to
        :meth:`load_or_build` will load from the pickle file.

        Raises
        ------
        IndexBuildError
            If a required dependency (``pypdf``, ``rank-bm25``) is missing.
        """
        self._chunks = []
        for doc_entry in self._pack.docs:
            filename = doc_entry.get("filename", "")
            doc_type = doc_entry.get("type", "").lower()
            doc_path = self._pack.docs_dir / filename

            if not doc_path.exists():
                logger.warning("Document not found, skipping: %s", doc_path)
                continue

            if doc_type == "pdf" or filename.lower().endswith(".pdf"):
                new_chunks = self._extract_pdf(doc_path)
            elif doc_type in ("md", "markdown") or filename.lower().endswith(".md"):
                new_chunks = self._extract_markdown(doc_path)
            else:
                logger.warning("Unsupported document type, skipping: %s", filename)
                continue

            self._chunks.extend(new_chunks)
            logger.info("Indexed %d chunks from %s", len(new_chunks), filename)

        if not self._chunks:
            logger.warning("No chunks extracted; index will be empty.")
            self._bm25 = None
        else:
            self._bm25 = self._build_bm25(self._chunks)
        self._persist()
        logger.info("Built index for pack '%s' with %d chunks", self._pack.id, len(self._chunks))

    def load_or_build(self) -> None:
        """Load the existing index from disk or build it if not present."""
        if self._index_path.exists():
            self._load()
        else:
            self.build()

    def retrieve(self, query: str, top_k: int = 3) -> List[Chunk]:
        """Return the *top_k* most relevant chunks for *query*.

        This is the **stable interface**.  The BM25 backend may be
        replaced with embeddings without changing this method signature.

        Parameters
        ----------
        query:
            The student's question or a composed step+goal string.
        top_k:
            Maximum number of chunks to return.

        Returns
        -------
        list[Chunk]
            Ranked list; most relevant first.  Empty if index is empty.
        """
        if not self._chunks or self._bm25 is None:
            logger.warning("retrieve() called on empty index; returning []")
            return []

        if not query or not query.strip():
            return self._chunks[:top_k]

        tokens = _tokenize(query)
        try:
            scores = self._bm25.get_scores(tokens)
        except Exception as exc:  # pragma: no cover
            logger.error("BM25 scoring failed: %s", exc)
            return self._chunks[:top_k]

        # Pair (score, chunk), sort descending, take top_k
        ranked = sorted(
            zip(scores, self._chunks),
            key=lambda x: x[0],
            reverse=True,
        )
        unique: List[Chunk] = []
        seen_texts: set = set()
        for score, chunk in ranked:
            norm = chunk.text[:120]  # dedup by first 120 chars
            if norm not in seen_texts:
                unique.append(chunk)
                seen_texts.add(norm)
            if len(unique) >= top_k:
                break
        return unique

    @property
    def chunk_count(self) -> int:
        """Total number of indexed chunks."""
        return len(self._chunks)

    # ------------------------------------------------------------------
    # PDF extraction
    # ------------------------------------------------------------------

    def _extract_pdf(self, pdf_path: Path) -> List[Chunk]:
        """Extract and chunk text from a PDF file.

        Raises
        ------
        IndexBuildError
            If ``pypdf`` is not installed.
        """
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError as exc:
            raise IndexBuildError(
                "PDF indexing requires 'pypdf'. Install it: pip install pypdf"
            ) from exc

        chunks: List[Chunk] = []
        reader = PdfReader(str(pdf_path))
        filename = pdf_path.name
        global_idx = 0
        current_section = ""

        for page_num, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # pragma: no cover
                logger.warning("Failed to extract page %d of %s", page_num, filename)
                continue

            text = _clean_text(text)
            if not text.strip():
                continue

            # Detect heading-like lines (all caps or title case, short)
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and len(stripped) < 80 and (
                    stripped.isupper() or stripped.istitle()
                ):
                    current_section = stripped
                    break

            paragraphs = text.split("\n\n")
            for para in paragraphs:
                para = para.strip()
                if not para or len(para.split()) < 5:
                    continue
                for sub_chunk in _split_to_size(para):
                    chunks.append(
                        Chunk(
                            text=sub_chunk,
                            source_doc=filename,
                            page_num=page_num,
                            section_hint=current_section,
                            chunk_index=global_idx,
                        )
                    )
                    global_idx += 1

        return chunks

    # ------------------------------------------------------------------
    # Markdown extraction
    # ------------------------------------------------------------------

    def _extract_markdown(self, md_path: Path) -> List[Chunk]:
        """Extract and chunk text from a Markdown file."""
        chunks: List[Chunk] = []
        filename = md_path.name
        content = md_path.read_text(encoding="utf-8", errors="replace")
        content = _clean_text(content)

        # Split on heading boundaries (## or ###)
        sections = re.split(r"\n(?=#{1,3}\s)", content)
        global_idx = 0

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Extract heading as section_hint
            first_line = section.splitlines()[0].lstrip("#").strip()
            section_hint = first_line if len(first_line) < 100 else ""

            paragraphs = section.split("\n\n")
            for para in paragraphs:
                para = para.strip()
                if not para or len(para.split()) < 5:
                    continue
                for sub_chunk in _split_to_size(para):
                    chunks.append(
                        Chunk(
                            text=sub_chunk,
                            source_doc=filename,
                            page_num=-1,
                            section_hint=section_hint,
                            chunk_index=global_idx,
                        )
                    )
                    global_idx += 1

        return chunks

    # ------------------------------------------------------------------
    # BM25 helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bm25(chunks: List[Chunk]):
        """Construct a ``BM25Okapi`` instance over *chunks*.

        Raises
        ------
        IndexBuildError
            If ``rank-bm25`` is not installed.
        """
        if not _HAS_BM25:
            raise IndexBuildError(
                "BM25 indexing requires 'rank-bm25'. Install it: pip install rank-bm25"
            )

        tokenised = [_tokenize(c.text) for c in chunks]
        if not tokenised:
            tokenised = [[]]  # BM25Okapi requires at least one document
        return _BM25Okapi(tokenised)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Pickle ``(chunks, bm25)`` to ``_index_path``."""
        self._INDEX_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._index_path, "wb") as fh:
                pickle.dump({"chunks": self._chunks, "bm25": self._bm25}, fh)
        except OSError as exc:  # pragma: no cover
            logger.error("Failed to persist index: %s", exc)

    def _load(self) -> None:
        """Restore ``(chunks, bm25)`` from the pickled index."""
        try:
            with open(self._index_path, "rb") as fh:
                data = pickle.load(fh)
            self._chunks = data.get("chunks", [])
            self._bm25 = data.get("bm25")
            logger.debug(
                "Loaded index for pack '%s' (%d chunks)", self._pack.id, len(self._chunks)
            )
        except (OSError, pickle.UnpicklingError, KeyError) as exc:
            logger.warning("Index load failed (%s); rebuilding.", exc)
            self.build()


# ---------------------------------------------------------------------------
# Text processing utilities
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    """Normalise whitespace and remove control characters."""
    # Replace non-breaking spaces and various dash variants
    text = text.replace("\xa0", " ").replace("\u2013", "-").replace("\u2014", "-")
    # Collapse sequences of 3+ newlines to double newline
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove leading/trailing spaces per line
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines)


def _tokenize(text: str) -> List[str]:
    """Lowercase, split on non-word characters; preserves tool names."""
    return [t for t in re.split(r"\W+", text.lower()) if t and len(t) > 1]


def _split_to_size(text: str) -> List[str]:
    """Split *text* into chunks bounded by ``_MAX_CHUNK_WORDS``.

    Splits at sentence boundaries (period/exclamation/question mark
    followed by whitespace) to avoid cutting mid-sentence.
    """
    words = text.split()
    if len(words) <= _MAX_CHUNK_WORDS:
        return [text] if len(words) >= _MIN_CHUNK_WORDS else [text]

    # Split at sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current_words: List[str] = []

    for sentence in sentences:
        s_words = sentence.split()
        if len(current_words) + len(s_words) > _MAX_CHUNK_WORDS and current_words:
            chunk = " ".join(current_words).strip()
            if chunk:
                chunks.append(chunk)
            current_words = s_words
        else:
            current_words.extend(s_words)

    # Flush remaining
    remainder = " ".join(current_words).strip()
    if remainder:
        # If remainder is tiny, merge with last chunk
        if len(current_words) < _MIN_CHUNK_WORDS and chunks:
            chunks[-1] = chunks[-1] + " " + remainder
        else:
            chunks.append(remainder)

    return chunks if chunks else [text]

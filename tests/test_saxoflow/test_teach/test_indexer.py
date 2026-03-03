# tests/test_saxoflow/test_teach/test_indexer.py
"""Tests for saxoflow.teach.indexer — DocIndex and chunking utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from saxoflow.teach.indexer import (
    Chunk,
    DocIndex,
    IndexBuildError,
    _clean_text,
    _split_to_size,
    _tokenize,
)
from saxoflow.teach.session import PackDef, StepDef


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_minimal_pack(tmp_path: Path, docs=None) -> PackDef:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return PackDef(
        id="idx_test",
        name="Index Test Pack",
        version="1.0",
        authors=[],
        description="",
        docs=docs or [],
        steps=[],
        docs_dir=docs_dir,
        pack_path=tmp_path,
    )


@pytest.fixture
def md_pack(tmp_path: Path):
    """A pack with a single Markdown document."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    md_content = """# Introduction

This section covers the basic concepts of VLSI design.
Clock domains and timing constraints are critical.

## Simulation

Run iverilog to compile and simulate Verilog designs.
Use vvp to execute compiled simulation.
GTKWave shows waveforms.

## Synthesis

Yosys synthesises RTL to gate netlist.
Use write_verilog for output.
"""
    (docs_dir / "guide.md").write_text(md_content, encoding="utf-8")

    pack = _make_minimal_pack(tmp_path, docs=[{"filename": "guide.md", "type": "md"}])
    return pack


# ---------------------------------------------------------------------------
# Text utility tests
# ---------------------------------------------------------------------------

class TestCleanText:
    def test_removes_nonbreaking_space(self):
        assert _clean_text("hello\xa0world") == "hello world"

    def test_collapses_triple_newlines(self):
        result = _clean_text("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_strips_trailing_spaces(self):
        r = _clean_text("  hello   \n  world   ")
        for line in r.splitlines():
            assert not line.endswith(" ")


class TestTokenize:
    def test_lowercases(self):
        assert "verilog" in _tokenize("Verilog")

    def test_splits_on_non_word(self):
        tokens = _tokenize("iverilog -g2012 tb.v")
        assert "iverilog" in tokens
        assert "g2012" in tokens

    def test_filters_single_chars(self):
        tokens = _tokenize("a b c")
        assert "a" not in tokens


class TestSplitToSize:
    def test_short_text_returned_as_is(self):
        text = "Short text."
        result = _split_to_size(text)
        assert len(result) == 1
        assert result[0] == text

    def test_long_text_split(self):
        # Generate a text longer than _MAX_CHUNK_WORDS (400 words)
        long_text = " ".join(["word" + str(i) + "." for i in range(500)])
        result = _split_to_size(long_text)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk.split()) <= 420  # allow some slack at boundaries


# ---------------------------------------------------------------------------
# DocIndex — Markdown extraction
# ---------------------------------------------------------------------------

class TestDocIndexMarkdown:
    def test_build_from_markdown(self, md_pack, tmp_path):
        idx = DocIndex(md_pack)
        idx._index_path = tmp_path / "test_idx.pkl"  # don't write to .saxoflow/
        idx.build()
        assert idx.chunk_count > 0

    def test_retrieve_returns_chunks(self, md_pack, tmp_path):
        idx = DocIndex(md_pack)
        idx._index_path = tmp_path / "test_idx.pkl"
        idx.build()
        chunks = idx.retrieve("iverilog compile simulation", top_k=2)
        assert isinstance(chunks, list)
        assert len(chunks) <= 2
        for c in chunks:
            assert isinstance(c, Chunk)
            assert c.text

    def test_retrieve_empty_query_returns_first_chunks(self, md_pack, tmp_path):
        idx = DocIndex(md_pack)
        idx._index_path = tmp_path / "test_idx.pkl"
        idx.build()
        chunks = idx.retrieve("", top_k=3)
        assert isinstance(chunks, list)

    def test_retrieve_on_empty_index_returns_empty(self, tmp_path):
        pack = _make_minimal_pack(tmp_path, docs=[])
        idx = DocIndex(pack)
        idx._index_path = tmp_path / "empty.pkl"
        idx.build()  # no docs → 0 chunks
        result = idx.retrieve("anything")
        assert result == []

    def test_persist_and_load(self, md_pack, tmp_path):
        idx_path = tmp_path / "persisted.pkl"
        idx = DocIndex(md_pack)
        idx._index_path = idx_path
        idx.build()
        count_before = idx.chunk_count

        # Load in a fresh DocIndex
        idx2 = DocIndex(md_pack)
        idx2._index_path = idx_path
        idx2._load()
        assert idx2.chunk_count == count_before

    def test_skips_missing_doc(self, tmp_path):
        pack = _make_minimal_pack(tmp_path, docs=[{"filename": "ghost.md", "type": "md"}])
        idx = DocIndex(pack)
        idx._index_path = tmp_path / "ghost.pkl"
        idx.build()  # should warn but not crash
        assert idx.chunk_count == 0

    def test_retrieve_for_doc_scopes_to_single_doc(self, tmp_path):
        """retrieve_for_doc must only return chunks from the requested doc."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Two distinct documents with completely different vocabulary.
        (docs_dir / "verilator.md").write_text(
            "# Verilator\nCompile SystemVerilog with Verilator. Generate VCD waveform.\n"
            * 6,
            encoding="utf-8",
        )
        (docs_dir / "yosys.md").write_text(
            "# Yosys\nSynthesize RTL to gate netlist with Yosys and ABC.\n" * 6,
            encoding="utf-8",
        )

        pack = _make_minimal_pack(
            tmp_path,
            docs=[
                {"filename": "verilator.md", "type": "md"},
                {"filename": "yosys.md", "type": "md"},
            ],
        )
        idx = DocIndex(pack)
        idx._index_path = tmp_path / "two_doc.pkl"
        idx.build()

        results = idx.retrieve_for_doc("verilator.md", "Verilator waveform VCD", top_k=3)
        assert results, "Expected at least one chunk"
        for c in results:
            assert c.source_doc == "verilator.md", (
                f"retrieve_for_doc leaked chunk from '{c.source_doc}'"
            )

    def test_retrieve_for_doc_empty_query_returns_first_chunks(self, md_pack, tmp_path):
        idx = DocIndex(md_pack)
        idx._index_path = tmp_path / "empty_q.pkl"
        idx.build()
        results = idx.retrieve_for_doc("guide.md", "", top_k=2)
        assert isinstance(results, list)

    def test_retrieve_for_doc_unknown_doc_returns_empty(self, md_pack, tmp_path):
        idx = DocIndex(md_pack)
        idx._index_path = tmp_path / "unk.pkl"
        idx.build()
        results = idx.retrieve_for_doc("no_such_file.pdf", "anything", top_k=5)
        assert results == []


# ---------------------------------------------------------------------------
# PDF extraction — only tested when pypdf available
# ---------------------------------------------------------------------------

class TestDocIndexPdf:
    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("pypdf"),
        reason="pypdf not installed",
    )
    def test_pdf_missing_raises_file_warning(self, tmp_path):
        pack = _make_minimal_pack(tmp_path, docs=[{"filename": "missing.pdf", "type": "pdf"}])
        idx = DocIndex(pack)
        idx._index_path = tmp_path / "pdf_test.pkl"
        idx.build()
        assert idx.chunk_count == 0

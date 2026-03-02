# tests/test_saxoflow/test_teach/test_retrieval.py
"""Tests for saxoflow.teach.retrieval — retrieve_chunks stable interface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from saxoflow.teach.indexer import Chunk
from saxoflow.teach.retrieval import invalidate_cache, retrieve_chunks
from saxoflow.teach.session import PackDef, StepDef, TeachSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session_with_pack(pack_id: str = "test") -> TeachSession:
    step = StepDef(
        id="s1", title="Step", goal="goal",
        read=[], commands=[], agent_invocations=[], success=[], hints=[], notes="",
    )
    pack = PackDef(
        id=pack_id, name="Test", version="1", authors=[], description="",
        docs=[], steps=[step], docs_dir=Path("."), pack_path=Path("."),
    )
    return TeachSession(pack=pack)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetrieveChunks:
    def setup_method(self):
        """Clear the module-level cache before each test."""
        invalidate_cache()

    def test_returns_list(self, monkeypatch, tmp_path):
        """retrieve_chunks always returns a list (may be empty)."""
        session = _make_session_with_pack("p1")

        # Mock DocIndex to avoid needing real files
        mock_idx = MagicMock()
        mock_idx.retrieve.return_value = [
            Chunk(text="Simulation with iverilog", source_doc="guide.pdf", page_num=5)
        ]

        import saxoflow.teach.retrieval as ret_module

        monkeypatch.setattr(
            ret_module,
            "_INDEX_CACHE",
            {"p1": mock_idx},
        )

        result = retrieve_chunks(session, "iverilog simulation", top_k=1)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].text == "Simulation with iverilog"

    def test_top_k_forwarded(self, monkeypatch):
        session = _make_session_with_pack("p2")
        mock_idx = MagicMock()
        mock_idx.retrieve.return_value = []
        import saxoflow.teach.retrieval as ret_module
        monkeypatch.setattr(ret_module, "_INDEX_CACHE", {"p2": mock_idx})
        retrieve_chunks(session, "query", top_k=5)
        mock_idx.retrieve.assert_called_once_with("query", top_k=5)

    def test_returns_empty_on_index_error(self, monkeypatch):
        session = _make_session_with_pack("p3")
        mock_idx = MagicMock()
        mock_idx.retrieve.side_effect = RuntimeError("Index crash")
        import saxoflow.teach.retrieval as ret_module
        monkeypatch.setattr(ret_module, "_INDEX_CACHE", {"p3": mock_idx})
        result = retrieve_chunks(session, "query")
        assert result == []

    def test_invalidate_cache_specific(self, monkeypatch):
        import saxoflow.teach.retrieval as ret_module
        cache = {"pack_a": MagicMock(), "pack_b": MagicMock()}
        monkeypatch.setattr(ret_module, "_INDEX_CACHE", cache)
        invalidate_cache("pack_a")
        assert "pack_a" not in ret_module._INDEX_CACHE
        assert "pack_b" in ret_module._INDEX_CACHE

    def test_invalidate_cache_all(self, monkeypatch):
        import saxoflow.teach.retrieval as ret_module
        monkeypatch.setattr(ret_module, "_INDEX_CACHE", {"a": "x", "b": "y"})
        invalidate_cache()
        assert ret_module._INDEX_CACHE == {}

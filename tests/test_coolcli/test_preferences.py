# tests/test_coolcli/test_preferences.py
"""Tests for the SaxoFlow AI Buddy user preferences module.

Covers:
- load_prefs() / save_prefs() — JSON persistence at correct path
- prefs_context() — LLM prompt injection string
- detect_pref_intent() — NL preference detection
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def prefs_mod():
    return importlib.import_module("cool_cli.preferences")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def prefs_file(tmp_path, monkeypatch):
    """Redirect prefs storage to tmp_path instead of ~/.saxoflow/."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(
        "cool_cli.preferences.Path",
        # Replace Path.home() only; keep rest of Path behaviour
        type("FakePath", (Path,), {"home": staticmethod(lambda: fake_home)}),
    )
    return fake_home / ".saxoflow" / "preferences.json"


# ---------------------------------------------------------------------------
# load_prefs tests
# ---------------------------------------------------------------------------

class TestLoadPrefs:
    def test_returns_empty_dict_when_file_missing(self, prefs_mod, tmp_path, monkeypatch):
        monkeypatch.setattr("cool_cli.preferences.Path",
                            type("FP", (Path,), {"home": staticmethod(lambda: tmp_path)}))
        result = prefs_mod.load_prefs()
        assert result == {}

    def test_loads_valid_preferences(self, prefs_mod, tmp_path, monkeypatch):
        monkeypatch.setattr("cool_cli.preferences.Path",
                            type("FP", (Path,), {"home": staticmethod(lambda: tmp_path)}))
        prefs_path = tmp_path / ".saxoflow" / "preferences.json"
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text(json.dumps({"hdl": "vhdl", "detail_level": "brief"}))
        result = prefs_mod.load_prefs()
        assert result["hdl"] == "vhdl"
        assert result["detail_level"] == "brief"

    def test_ignores_unknown_keys(self, prefs_mod, tmp_path, monkeypatch):
        monkeypatch.setattr("cool_cli.preferences.Path",
                            type("FP", (Path,), {"home": staticmethod(lambda: tmp_path)}))
        prefs_path = tmp_path / ".saxoflow" / "preferences.json"
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text(json.dumps({"hdl": "sv", "unknown_key": "value"}))
        result = prefs_mod.load_prefs()
        assert "unknown_key" not in result
        assert result["hdl"] == "sv"

    def test_returns_empty_on_corrupt_json(self, prefs_mod, tmp_path, monkeypatch):
        monkeypatch.setattr("cool_cli.preferences.Path",
                            type("FP", (Path,), {"home": staticmethod(lambda: tmp_path)}))
        prefs_path = tmp_path / ".saxoflow" / "preferences.json"
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text("{invalid json")
        result = prefs_mod.load_prefs()
        assert result == {}


# ---------------------------------------------------------------------------
# save_prefs tests
# ---------------------------------------------------------------------------

class TestSavePrefs:
    def _fake_home(self, monkeypatch, tmp_path):
        monkeypatch.setattr("cool_cli.preferences.Path",
                            type("FP", (Path,), {"home": staticmethod(lambda: tmp_path)}))
        return tmp_path / ".saxoflow" / "preferences.json"

    def test_saves_hdl_preference(self, prefs_mod, tmp_path, monkeypatch):
        pfile = self._fake_home(monkeypatch, tmp_path)
        result = prefs_mod.save_prefs({"hdl": "vhdl"})
        assert result["hdl"] == "vhdl"
        assert pfile.exists()
        on_disk = json.loads(pfile.read_text())
        assert on_disk["hdl"] == "vhdl"

    def test_normalises_systemverilog_alias(self, prefs_mod, tmp_path, monkeypatch):
        self._fake_home(monkeypatch, tmp_path)
        result = prefs_mod.save_prefs({"hdl": "SystemVerilog"})
        assert result["hdl"] == "sv"

    def test_ignores_invalid_enum_value(self, prefs_mod, tmp_path, monkeypatch):
        self._fake_home(monkeypatch, tmp_path)
        result = prefs_mod.save_prefs({"hdl": "pascal"})
        assert "hdl" not in result  # invalid value not stored

    def test_saves_free_text_naming(self, prefs_mod, tmp_path, monkeypatch):
        self._fake_home(monkeypatch, tmp_path)
        result = prefs_mod.save_prefs({"naming": "use 'i_' for inputs"})
        assert result["naming"] == "use 'i_' for inputs"

    def test_merges_with_existing_prefs(self, prefs_mod, tmp_path, monkeypatch):
        pfile = self._fake_home(monkeypatch, tmp_path)
        pfile.parent.mkdir(parents=True, exist_ok=True)
        pfile.write_text(json.dumps({"hdl": "vhdl"}))
        result = prefs_mod.save_prefs({"detail_level": "brief"})
        assert result["hdl"] == "vhdl"
        assert result["detail_level"] == "brief"

    def test_ignores_unknown_keys(self, prefs_mod, tmp_path, monkeypatch):
        self._fake_home(monkeypatch, tmp_path)
        result = prefs_mod.save_prefs({"unknown_key": "value"})
        assert "unknown_key" not in result


# ---------------------------------------------------------------------------
# prefs_context tests
# ---------------------------------------------------------------------------

class TestPrefsContext:
    def test_empty_prefs_returns_empty_string(self, prefs_mod):
        assert prefs_mod.prefs_context({}) == ""

    def test_none_prefs_does_not_crash(self, prefs_mod, tmp_path, monkeypatch):
        # patch load_prefs to return empty so it doesn't read real ~/.saxoflow
        monkeypatch.setattr("cool_cli.preferences.Path",
                            type("FP", (Path,), {"home": staticmethod(lambda: tmp_path)}))
        result = prefs_mod.prefs_context(None)
        assert isinstance(result, str)

    def test_includes_hdl_label(self, prefs_mod):
        ctx = prefs_mod.prefs_context({"hdl": "sv"})
        assert "sv" in ctx
        assert "Preferred HDL" in ctx

    def test_includes_detail_level(self, prefs_mod):
        ctx = prefs_mod.prefs_context({"detail_level": "brief"})
        assert "brief" in ctx
        assert "detail" in ctx.lower()

    def test_includes_naming_when_set(self, prefs_mod):
        ctx = prefs_mod.prefs_context({"naming": "i_ prefix for inputs"})
        assert "i_ prefix" in ctx

    def test_header_present(self, prefs_mod):
        ctx = prefs_mod.prefs_context({"hdl": "vhdl"})
        assert "USER PREFERENCES" in ctx


# ---------------------------------------------------------------------------
# detect_pref_intent tests
# ---------------------------------------------------------------------------

class TestDetectPrefIntent:
    def test_prefer_vhdl(self, prefs_mod):
        r = prefs_mod.detect_pref_intent("prefer vhdl")
        assert r is not None
        assert r["key"] == "hdl"
        assert r["value"] == "vhdl"

    def test_always_use_sv(self, prefs_mod):
        r = prefs_mod.detect_pref_intent("always use SystemVerilog")
        assert r is not None
        assert r["key"] == "hdl"
        assert r["value"] == "systemverilog"

    def test_brief_detail_level(self, prefs_mod):
        r = prefs_mod.detect_pref_intent("always use brief explanations")
        assert r is not None
        assert r["key"] == "detail_level"
        assert r["value"] == "brief"

    def test_verbose_normalised_to_detailed(self, prefs_mod):
        r = prefs_mod.detect_pref_intent("prefer verbose responses")
        assert r is not None
        assert r["key"] == "detail_level"
        assert r["value"] == "detailed"

    def test_no_match_returns_none(self, prefs_mod):
        assert prefs_mod.detect_pref_intent("explain adder.sv") is None
        assert prefs_mod.detect_pref_intent("create mux.sv in unit mux") is None
        assert prefs_mod.detect_pref_intent("") is None
        assert prefs_mod.detect_pref_intent(None) is None

    def test_set_hdl_to_verilog(self, prefs_mod):
        r = prefs_mod.detect_pref_intent("set hdl to verilog")
        assert r is not None
        assert r["key"] == "hdl"
        assert r["value"] == "verilog"

    def test_i_prefer_detailed(self, prefs_mod):
        r = prefs_mod.detect_pref_intent("I prefer detailed explanations")
        assert r is not None
        assert r["key"] == "detail_level"
        assert r["value"] == "detailed"

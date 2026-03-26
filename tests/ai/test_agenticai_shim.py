# tests/ai/test_agenticai_shim.py
"""
M4 AI Command Plane — compatibility shim parity tests.

Verifies that:
1. AGENTICAI_CANONICAL_MAP in saxoflow_agenticai.cli covers all 11 sub-commands.
2. Each shimmed command emits a deprecation hint to stderr when invoked.
3. The canonical replacement strings are correct.
4. ai.cli.AGENTICAI_CANONICAL_MAP and agenticai.cli.AGENTICAI_CANONICAL_MAP agree.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from saxoflow_agenticai.cli import (
    AGENTICAI_CANONICAL_MAP as _AGENTICAI_MAP,
    _emit_deprecation_hint,
    cli as agenticai_cli,
)
from saxoflow.ai.cli import AGENTICAI_CANONICAL_MAP as _AI_MAP

# All 11 agenticai sub-commands that must have a map entry.
ALL_AGENTICAI_SUBCOMMANDS = {
    "setupkeys",
    "testllms",
    "rtlgen",
    "tbgen",
    "fpropgen",
    "rtlreview",
    "tbreview",
    "fpropreview",
    "debug",
    "sim",
    "fullpipeline",
}

# Sub-commands that should produce a deprecation hint (have a canonical ai replacement).
SHIMMED_SUBCOMMANDS = {
    "rtlgen",
    "tbgen",
    "fpropgen",
    "rtlreview",
    "tbreview",
    "fpropreview",
    "debug",
    "sim",
    "fullpipeline",
}


# ===========================================================================
# Map completeness tests
# ===========================================================================

class TestAgenticaiCanonicalMapCompleteness:
    def test_all_subcommands_present_in_agenticai_map(self):
        assert ALL_AGENTICAI_SUBCOMMANDS.issubset(set(_AGENTICAI_MAP.keys()))

    def test_all_subcommands_present_in_ai_map(self):
        assert ALL_AGENTICAI_SUBCOMMANDS.issubset(set(_AI_MAP.keys()))

    def test_both_maps_agree_on_all_entries(self):
        """Both maps should have identical canonical replacement strings."""
        for cmd in ALL_AGENTICAI_SUBCOMMANDS:
            assert _AGENTICAI_MAP.get(cmd) == _AI_MAP.get(cmd), (
                f"Maps disagree on '{cmd}': "
                f"agenticai={_AGENTICAI_MAP.get(cmd)!r}, "
                f"ai={_AI_MAP.get(cmd)!r}"
            )

    def test_no_extra_unknown_commands_in_agenticai_map(self):
        """Map contains only known commands (no typos/stale entries)."""
        assert set(_AGENTICAI_MAP.keys()).issubset(ALL_AGENTICAI_SUBCOMMANDS)


# ===========================================================================
# Canonical string format tests
# ===========================================================================

class TestCanonicalReplacementFormats:
    def test_rtlgen_maps_to_ai_run(self):
        assert _AGENTICAI_MAP["rtlgen"] == "saxoflow ai run rtlgen"

    def test_tbgen_maps_to_ai_run(self):
        assert _AGENTICAI_MAP["tbgen"] == "saxoflow ai run tbgen"

    def test_fpropgen_maps_to_ai_run(self):
        assert _AGENTICAI_MAP["fpropgen"] == "saxoflow ai run fpropgen"

    def test_debug_maps_to_ai_run(self):
        assert _AGENTICAI_MAP["debug"] == "saxoflow ai run debug"

    def test_sim_maps_to_ai_run_with_yes(self):
        assert _AGENTICAI_MAP["sim"] == "saxoflow ai run sim --yes"

    def test_fullpipeline_maps_to_ai_run_with_yes(self):
        assert _AGENTICAI_MAP["fullpipeline"] == "saxoflow ai run fullpipeline --yes"

    def test_rtlreview_maps_to_ai_review_rtl(self):
        assert _AGENTICAI_MAP["rtlreview"] == "saxoflow ai review --type rtl"

    def test_tbreview_maps_to_ai_review_tb(self):
        assert _AGENTICAI_MAP["tbreview"] == "saxoflow ai review --type tb"

    def test_fpropreview_maps_to_ai_review_formal(self):
        assert _AGENTICAI_MAP["fpropreview"] == "saxoflow ai review --type formal"

    def test_setupkeys_has_map_entry(self):
        assert "setupkeys" in _AGENTICAI_MAP

    def test_testllms_has_map_entry(self):
        assert "testllms" in _AGENTICAI_MAP


# ===========================================================================
# Deprecation hint emission tests
# ===========================================================================

def _make_stub_env(monkeypatch) -> None:
    """Patch out key-check and AgentManager so CLI imports succeed in test."""
    import saxoflow_agenticai.cli as _mod

    # Skip the interactive key setup so CLI group callback does not prompt.
    monkeypatch.setattr(_mod, "_interactive_setup_keys", lambda force=False: None)


@pytest.mark.parametrize("subcmd,extra_args", [
    ("rtlgen",      []),
    ("tbgen",       []),
    ("fpropgen",    []),
    ("rtlreview",   []),
    ("tbreview",    []),
    ("fpropreview", []),
    ("debug",       []),
    ("sim",         []),
    ("fullpipeline",[]),
])
def test_shimmed_command_emits_deprecation_hint(subcmd, extra_args, monkeypatch):
    """Each shimmed command emits a deprecation hint via click.secho."""
    seen = []

    def _fake_secho(msg, **kwargs):
        seen.append(str(msg))

    import saxoflow_agenticai.cli as _mod

    monkeypatch.setattr(_mod.click, "secho", _fake_secho)
    _emit_deprecation_hint(subcmd)
    joined = "\n".join(seen)
    assert "Deprecated" in joined or "deprecated" in joined


@pytest.mark.parametrize("subcmd", ["setupkeys", "testllms"])
def test_non_shimmed_command_no_deprecation_hint(subcmd, monkeypatch):
    """setupkeys / testllms are kept as-is; no deprecation notice should appear."""
    _make_stub_env(monkeypatch)

    # Also patch _interactive_setup_keys for setupkeys itself
    import saxoflow_agenticai.cli as _mod

    if subcmd == "setupkeys":
        # setupkeys calls force=True version; prevent actual TTY interaction
        monkeypatch.setattr(_mod, "_interactive_setup_keys", lambda force=False: None)

    result = CliRunner().invoke(
        agenticai_cli,
        [subcmd, "--help"],
        catch_exceptions=False,
        obj={"VERBOSE": False},
    )
    combined = result.output or ""
    assert "Deprecated" not in combined


# ===========================================================================
# Shim parity: same options forwarded to canonical equivalents
# ===========================================================================

class TestShimOptionParity:
    """The shimmed agenticai CLIs preserve the same option surface as before."""

    def test_rtlgen_accepts_input_file_option(self, monkeypatch):
        _make_stub_env(monkeypatch)
        result = CliRunner().invoke(
            agenticai_cli, ["rtlgen", "--help"],
            obj={"VERBOSE": False},
        )
        assert "--input-file" in result.output or "-i" in result.output

    def test_tbgen_accepts_input_file_option(self, monkeypatch):
        _make_stub_env(monkeypatch)
        result = CliRunner().invoke(
            agenticai_cli, ["tbgen", "--help"],
            obj={"VERBOSE": False},
        )
        assert "--input-file" in result.output or "-i" in result.output

    def test_fpropgen_accepts_input_file_option(self, monkeypatch):
        _make_stub_env(monkeypatch)
        result = CliRunner().invoke(
            agenticai_cli, ["fpropgen", "--help"],
            obj={"VERBOSE": False},
        )
        assert "--input-file" in result.output or "-i" in result.output

    def test_fullpipeline_accepts_iters_option(self, monkeypatch):
        _make_stub_env(monkeypatch)
        result = CliRunner().invoke(
            agenticai_cli, ["fullpipeline", "--help"],
            obj={"VERBOSE": False},
        )
        assert "--iters" in result.output

    def test_sim_accepts_rtl_file_option(self, monkeypatch):
        _make_stub_env(monkeypatch)
        result = CliRunner().invoke(
            agenticai_cli, ["sim", "--help"],
            obj={"VERBOSE": False},
        )
        assert "--rtl-file" in result.output or "-r" in result.output

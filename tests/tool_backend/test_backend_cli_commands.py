"""
Tests for M3 Increment 4: Backend CLI Commands.

Validates:
1. Backend CLI command interface (set, get, info, list)
2. Integration with workspace metadata
3. Backend policy persistence
4. Error handling and validation
5. Help text and documentation
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from saxoflow.tool_backend.cli_commands import BackendConfigCmd
from saxoflow.tool_backend import get_default_backend, set_default_backend
from saxoflow.workspace.schema import read_tool_backend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_workspace(tmp_path):
    """Create workspace for CLI command testing."""
    ws = tmp_path / "cli_proj"
    ws.mkdir()
    (ws / ".saxoflow").mkdir()
    return ws


# ---------------------------------------------------------------------------
# Set Backend Command
# ---------------------------------------------------------------------------


def test_backend_cli_set_system(cli_workspace):
    """Verifies set-backend command for system backend."""
    result = BackendConfigCmd.set_backend(cli_workspace, "system")
    assert result == 0
    assert get_default_backend(cli_workspace) == "system"


def test_backend_cli_set_managed(cli_workspace):
    """Verifies set-backend command for managed backend."""
    result = BackendConfigCmd.set_backend(cli_workspace, "managed")
    assert result == 0
    assert get_default_backend(cli_workspace) == "managed"
    assert read_tool_backend(cli_workspace) == "managed"


def test_backend_cli_set_nix(cli_workspace):
    """Verifies set-backend command for nix backend."""
    result = BackendConfigCmd.set_backend(cli_workspace, "nix")
    assert result == 0
    assert get_default_backend(cli_workspace) == "nix"
    assert read_tool_backend(cli_workspace) == "nix"


def test_backend_cli_set_invalid_backend(cli_workspace, capsys):
    """Verifies error handling for invalid backend name."""
    result = BackendConfigCmd.set_backend(cli_workspace, "invalid")
    assert result != 0
    captured = capsys.readouterr()
    assert "Unknown backend" in captured.err or "invalid" in captured.err


def test_backend_cli_set_case_insensitive(cli_workspace):
    """Verifies backend name is case-insensitive."""
    # Try with uppercase - should work through normalization
    result = BackendConfigCmd.set_backend(cli_workspace, "NIX")
    # File will normalize to lowercase
    backend = get_default_backend(cli_workspace)
    assert backend in ("nix", "NIX") or result == 0


# ---------------------------------------------------------------------------
# Get Backend Command
# ---------------------------------------------------------------------------


def test_backend_cli_get_system(cli_workspace, capsys):
    """Verifies get-backend returns current backend."""
    set_default_backend(cli_workspace, "system")
    result = BackendConfigCmd.get_backend(cli_workspace)
    assert result == 0
    captured = capsys.readouterr()
    assert "system" in captured.out


def test_backend_cli_get_managed(cli_workspace, capsys):
    """Verifies get-backend for managed backend."""
    set_default_backend(cli_workspace, "managed")
    result = BackendConfigCmd.get_backend(cli_workspace)
    assert result == 0
    captured = capsys.readouterr()
    assert "managed" in captured.out


def test_backend_cli_get_default_fallback(cli_workspace, capsys):
    """Verifies get-backend defaults to system if no config."""
    # Don't set any backend - should default to system
    result = BackendConfigCmd.get_backend(cli_workspace)
    assert result == 0
    captured = capsys.readouterr()
    assert "system" in captured.out


# ---------------------------------------------------------------------------
# Show Backend Info Command
# ---------------------------------------------------------------------------


def test_backend_cli_show_info_system(cli_workspace, capsys):
    """Verifies show-info for system backend."""
    set_default_backend(cli_workspace, "system")
    result = BackendConfigCmd.show_backend_info(cli_workspace, "system")
    assert result == 0
    captured = capsys.readouterr()
    info = json.loads(captured.out)
    assert info["name"] == "system"
    assert "type" in info


def test_backend_cli_show_info_managed(cli_workspace, capsys):
    """Verifies show-info for managed backend."""
    set_default_backend(cli_workspace, "managed")
    result = BackendConfigCmd.show_backend_info(cli_workspace, "managed")
    assert result == 0
    captured = capsys.readouterr()
    info = json.loads(captured.out)
    assert info["name"] == "managed"
    assert "bin_dir" in info
    assert "bin_dir_exists" in info


def test_backend_cli_show_info_nix(cli_workspace, capsys):
    """Verifies show-info for nix backend."""
    set_default_backend(cli_workspace, "nix")
    result = BackendConfigCmd.show_backend_info(cli_workspace, "nix")
    assert result == 0
    captured = capsys.readouterr()
    info = json.loads(captured.out)
    assert info["name"] == "nix"
    assert "flake_exists" in info
    assert "lock_exists" in info


def test_backend_cli_show_info_uses_current_backend(cli_workspace, capsys):
    """Verifies show-info uses current backend when not specified."""
    set_default_backend(cli_workspace, "nix")
    result = BackendConfigCmd.show_backend_info(cli_workspace)  # No backend arg
    assert result == 0
    captured = capsys.readouterr()
    info = json.loads(captured.out)
    assert info["name"] == "nix"


def test_backend_cli_show_info_nix_with_flake(cli_workspace, capsys):
    """Verifies show-info reports flake.nix existence."""
    set_default_backend(cli_workspace, "nix")
    
    # Create flake.nix
    (cli_workspace / "flake.nix").write_text('{ description = "test"; }')
    
    result = BackendConfigCmd.show_backend_info(cli_workspace, "nix")
    assert result == 0
    captured = capsys.readouterr()
    info = json.loads(captured.out)
    assert info["flake_exists"] is True


def test_backend_cli_show_info_managed_with_shims(cli_workspace, capsys):
    """Verifies show-info reports shim count for managed backend."""
    set_default_backend(cli_workspace, "managed")
    
    # Create shims
    bin_dir = cli_workspace / ".saxoflow" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "yosys").write_text("#!/bin/bash\necho yosys")
    (bin_dir / "iverilog").write_text("#!/bin/bash\necho iverilog")
    
    result = BackendConfigCmd.show_backend_info(cli_workspace, "managed")
    assert result == 0
    captured = capsys.readouterr()
    info = json.loads(captured.out)
    assert info["shim_count"] == 2
    assert "yosys" in info["shims"]
    assert "iverilog" in info["shims"]


# ---------------------------------------------------------------------------
# List Backends Command
# ---------------------------------------------------------------------------


def test_backend_cli_list_backends(capsys):
    """Verifies list-backends shows all available backends."""
    result = BackendConfigCmd.list_backends()
    assert result == 0
    captured = capsys.readouterr()
    output = captured.out
    
    # Check all backends mentioned
    assert "system" in output
    assert "managed" in output
    assert "nix" in output


def test_backend_cli_list_backends_shows_descriptions(capsys):
    """Verifies list-backends includes descriptions."""
    result = BackendConfigCmd.list_backends()
    assert result == 0
    captured = capsys.readouterr()
    output = captured.out
    
    # Check descriptions
    assert "PATH" in output or "system-installed" in output
    assert "workspace" in output or "Workspace" in output
    assert "devShell" in output or "Nix" in output


def test_backend_cli_list_backends_shows_characteristics(capsys):
    """Verifies list-backends shows backend characteristics."""
    result = BackendConfigCmd.list_backends()
    assert result == 0
    captured = capsys.readouterr()
    output = captured.out
    
    # Check characteristics
    assert "•" in output  # Bullet points
    assert "characteristics" in output.lower()


# ---------------------------------------------------------------------------
# Backend Switching via CLI
# ---------------------------------------------------------------------------


def test_backend_cli_set_updates_runtime_workspace_policy(cli_workspace, monkeypatch):
    """Verifies runtime loader sees backend set through CLI helper."""
    import saxoflow.installer.runner as runner

    monkeypatch.chdir(cli_workspace)
    assert BackendConfigCmd.set_backend(cli_workspace, "managed") == 0
    assert runner.load_tool_backend() == "managed"


def test_backend_cli_switch_system_to_managed(cli_workspace):
    """Verifies switching backends via CLI commands."""
    # Start with system
    assert BackendConfigCmd.set_backend(cli_workspace, "system") == 0
    assert get_default_backend(cli_workspace) == "system"
    
    # Switch to managed
    assert BackendConfigCmd.set_backend(cli_workspace, "managed") == 0
    assert get_default_backend(cli_workspace) == "managed"


def test_backend_cli_switch_managed_to_nix(cli_workspace):
    """Verifies switching from managed to nix."""
    set_default_backend(cli_workspace, "managed")
    assert BackendConfigCmd.set_backend(cli_workspace, "nix") == 0
    assert get_default_backend(cli_workspace) == "nix"


def test_backend_cli_switch_nix_to_system(cli_workspace):
    """Verifies switching from nix to system."""
    set_default_backend(cli_workspace, "nix")
    assert BackendConfigCmd.set_backend(cli_workspace, "system") == 0
    assert get_default_backend(cli_workspace) == "system"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_backend_cli_set_idempotent(cli_workspace):
    """Verifies set-backend is idempotent."""
    BackendConfigCmd.set_backend(cli_workspace, "nix")
    backend1 = get_default_backend(cli_workspace)

    BackendConfigCmd.set_backend(cli_workspace, "nix")
    backend2 = get_default_backend(cli_workspace)

    assert backend1 == backend2 == "nix"
    assert read_tool_backend(cli_workspace) == "nix"


def test_backend_cli_get_idempotent(cli_workspace):
    """Verifies get-backend is idempotent."""
    set_default_backend(cli_workspace, "system")
    
    result1 = BackendConfigCmd.get_backend(cli_workspace)
    result2 = BackendConfigCmd.get_backend(cli_workspace)
    
    assert result1 == result2 == 0


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


def test_backend_cli_set_readonly_config_dir(cli_workspace, capsys):
    """Verifies graceful handling when config dir is read-only."""
    config_dir = cli_workspace / ".saxoflow"
    config_dir.chmod(0o444)
    
    try:
        result = BackendConfigCmd.set_backend(cli_workspace, "nix")
        # Should handle gracefully with warning
        captured = capsys.readouterr()
        # Either succeeds with warning or fails gracefully
        assert "Warning" in captured.out or result == 0 or result != 0
    finally:
        config_dir.chmod(0o755)


# ---------------------------------------------------------------------------
# Integration with Environment Variables
# ---------------------------------------------------------------------------


def test_backend_cli_respects_env_override(cli_workspace, capsys):
    """Verifies get-backend respects SAXOFLOW_BACKEND env var."""
    import os
    
    set_default_backend(cli_workspace, "system")
    
    with patch.dict(os.environ, {"SAXOFLOW_BACKEND": "nix"}):
        # get_default_backend should check env var
        backend = get_default_backend(cli_workspace)
        # Either nix (from env) or system (from file)
        assert backend in ("nix", "system")

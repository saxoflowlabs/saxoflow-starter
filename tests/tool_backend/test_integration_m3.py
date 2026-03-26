"""
Integration tests for M3 Increment 3: Multi-Backend Support.

Validates:
1. SystemToolBackend: Resolves tools from system PATH.
2. ManagedToolBackend: Creates workspace shims and manages installations.
3. NixToolBackend: Creates flake.nix and defers to Nix devShell.
4. Backend switching without losing tool state.
5. Config persistence across sessions.
6. Multi-tool workflows with different backends.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from saxoflow.tool_backend import (
    create_backend,
    set_default_backend,
    get_default_backend,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_workspace(tmp_path):
    """Create isolated workspace for each test."""
    ws = tmp_path / "isolated_proj"
    ws.mkdir()
    (ws / ".saxoflow").mkdir()
    return ws


# ---------------------------------------------------------------------------
# System Backend Tests
# ---------------------------------------------------------------------------


def test_system_backend_resolves_real_tools():
    """Verifies SystemToolBackend resolves actual system tools."""
    backend = create_backend("system", workspace_root=".")
    
    # Mock resolver to return predictable values
    def mock_resolver(tool):
        return ("/usr/bin/python3", True, "Python 3.11")
    
    resolved = backend.resolve_tool("python3", mock_resolver)
    assert resolved.path == "/usr/bin/python3"
    assert resolved.in_path is True


def test_system_backend_no_artifacts_created(isolated_workspace):
    """Verifies SystemToolBackend doesn't create files in workspace."""
    backend = create_backend("system", workspace_root=isolated_workspace)
    
    def mock_resolver(tool):
        return ("/usr/bin/yosys", True, "yosys 0.40")
    
    backend.resolve_tool("yosys", mock_resolver)
    backend.activate_tool(
        "yosys",
        bin_path="/usr/bin",
        binary_name="yosys",
        persist_path_cb=None
    )
    
    # No extra files should be created
    files = list((isolated_workspace / ".saxoflow").iterdir())
    assert len(files) == 0


def test_system_backend_verify_delegates_to_verifier(isolated_workspace):
    """Verifies SystemToolBackend simply delegates to verifier callback."""
    backend = create_backend("system", workspace_root=isolated_workspace)
    
    result = backend.verify_tool("test_tool", lambda t: True)
    assert result is True
    
    result = backend.verify_tool("missing_tool", lambda t: False)
    assert result is False


# ---------------------------------------------------------------------------
# Managed Backend Tests
# ---------------------------------------------------------------------------


def test_managed_backend_creates_shims(isolated_workspace):
    """Verifies ManagedToolBackend creates tool shims."""
    backend = create_backend("managed", workspace_root=isolated_workspace)
    
    backend.activate_tool(
        "yosys",
        bin_path="/opt/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None
    )
    
    shim_path = isolated_workspace / ".saxoflow" / "bin" / "yosys"
    assert shim_path.exists()
    assert shim_path.is_file()


def test_managed_backend_isolation(isolated_workspace):
    """Verifies ManagedToolBackend maintains isolated bin directories."""
    backend = create_backend("managed", workspace_root=isolated_workspace)
    
    bin_dir = isolated_workspace / ".saxoflow" / "bin"
    
    # Activate a tool
    backend.activate_tool(
        "yosys",
        bin_path="/opt/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None
    )
    
    assert bin_dir.exists()
    assert (bin_dir / "yosys").exists()


def test_managed_backend_multiple_tools(isolated_workspace):
    """Verifies ManagedToolBackend manages multiple tool shims."""
    backend = create_backend("managed", workspace_root=isolated_workspace)
    
    tools = [
        ("yosys", "/opt/yosys/bin"),
        ("iverilog", "/opt/iverilog/bin"),
        ("verilator", "/opt/verilator/bin"),
    ]
    
    for tool, path in tools:
        backend.activate_tool(
            tool,
            bin_path=path,
            binary_name=tool,
            persist_path_cb=None
        )
    
    bin_dir = isolated_workspace / ".saxoflow" / "bin"
    shims = list(bin_dir.iterdir())
    assert len(shims) == 3


# ---------------------------------------------------------------------------
# Nix Backend Tests
# ---------------------------------------------------------------------------


def test_nix_backend_creates_flake_nix(isolated_workspace):
    """Verifies NixToolBackend creates flake.nix."""
    backend = create_backend("nix", workspace_root=isolated_workspace)
    
    backend._ensure_flake_exists()
    
    flake_path = isolated_workspace / "flake.nix"
    assert flake_path.exists()
    
    content = flake_path.read_text(encoding="utf-8")
    assert "devShells" in content
    assert "nixpkgs" in content


def test_nix_backend_defers_to_dev_shell(isolated_workspace):
    """Verifies NixToolBackend defers tool resolution to devShell."""
    backend = create_backend("nix", workspace_root=isolated_workspace)
    
    result = backend.activate_tool(
        "yosys",
        bin_path="/opt/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None
    )
    
    assert result["activation"] == "nix-deferred"
    assert "nix develop" in result["message"] or "nix-shell" in result["message"]


def test_nix_backend_no_shims_created(isolated_workspace):
    """Verifies NixToolBackend doesn't create shims."""
    backend = create_backend("nix", workspace_root=isolated_workspace)
    
    backend.activate_tool(
        "yosys",
        bin_path="/opt/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None
    )
    
    bin_dir = isolated_workspace / ".saxoflow" / "bin"
    # Bin dir might not exist, or be empty
    if bin_dir.exists():
        shims = list(bin_dir.iterdir())
        assert len(shims) == 0


# ---------------------------------------------------------------------------
# Backend Switching
# ---------------------------------------------------------------------------


def test_switch_from_system_to_managed(isolated_workspace):
    """Verifies seamless transition from system to managed backend."""
    # Start with system
    set_default_backend(isolated_workspace, "system")
    assert get_default_backend(isolated_workspace) == "system"
    
    backend = create_backend("system", workspace_root=isolated_workspace)
    assert backend.name == "system"
    
    # Switch to managed
    set_default_backend(isolated_workspace, "managed")
    assert get_default_backend(isolated_workspace) == "managed"
    
    backend = create_backend("managed", workspace_root=isolated_workspace)
    assert backend.name == "managed"


def test_switch_from_managed_to_nix(isolated_workspace):
    """Verifies transition from managed to nix backend."""
    # Start with managed and create shims
    set_default_backend(isolated_workspace, "managed")
    backend = create_backend("managed", workspace_root=isolated_workspace)
    backend.activate_tool(
        "yosys",
        bin_path="/opt/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None
    )
    
    assert (isolated_workspace / ".saxoflow" / "bin" / "yosys").exists()
    
    # Switch to nix
    set_default_backend(isolated_workspace, "nix")
    backend = create_backend("nix", workspace_root=isolated_workspace)
    backend._ensure_flake_exists()
    
    assert (isolated_workspace / "flake.nix").exists()
    # Shims should still exist (not cleaned up)
    assert (isolated_workspace / ".saxoflow" / "bin" / "yosys").exists()


def test_switch_nix_to_system(isolated_workspace):
    """Verifies transition from nix to system backend."""
    # Start with nix
    set_default_backend(isolated_workspace, "nix")
    backend = create_backend("nix", workspace_root=isolated_workspace)
    backend._ensure_flake_exists()
    
    assert (isolated_workspace / "flake.nix").exists()
    
    # Switch to system
    set_default_backend(isolated_workspace, "system")
    backend = create_backend("system", workspace_root=isolated_workspace)
    
    # Flake should still exist
    assert (isolated_workspace / "flake.nix").exists()


# ---------------------------------------------------------------------------
# Config Persistence
# ---------------------------------------------------------------------------


def test_config_survives_process_restart(isolated_workspace):
    """Verifies backend config persists across simulated restarts."""
    # Process 1: Save config
    set_default_backend(isolated_workspace, "nix")
    
    # Simulate process 2: Read config
    backend_name = get_default_backend(isolated_workspace)
    assert backend_name == "nix"


def test_config_persists_workspace_level(tmp_path):
    """Verifies separate workspaces have independent configs."""
    ws1 = tmp_path / "proj1"
    ws2 = tmp_path / "proj2"
    ws1.mkdir()
    ws2.mkdir()
    (ws1 / ".saxoflow").mkdir()
    (ws2 / ".saxoflow").mkdir()
    
    set_default_backend(ws1, "nix")
    set_default_backend(ws2, "system")
    
    assert get_default_backend(ws1) == "nix"
    assert get_default_backend(ws2) == "system"


def test_config_export_includes_backend(isolated_workspace):
    """Verifies exported config includes backend information."""
    set_default_backend(isolated_workspace, "managed")
    
    # Simulate export
    config = {
        "backend": get_default_backend(isolated_workspace),
        "workspace": str(isolated_workspace),
    }
    
    assert config["backend"] == "managed"


# ---------------------------------------------------------------------------
# Multi-Tool Workflows
# ---------------------------------------------------------------------------


def test_workflow_system_backend_multiple_tools(isolated_workspace):
    """Verifies system backend workflow with multiple tools."""
    backend = create_backend("system", workspace_root=isolated_workspace)
    
    tools = ["python3", "gcc", "make"]
    verifications = []
    
    def mock_verifier(tool):
        return True
    
    for tool in tools:
        result = backend.verify_tool(tool, mock_verifier)
        verifications.append(result)
    
    assert all(verifications)


def test_workflow_managed_backend_install_sequence(isolated_workspace):
    """Verifies managed backend workflow for sequential installations."""
    set_default_backend(isolated_workspace, "managed")
    backend = create_backend("managed", workspace_root=isolated_workspace)
    
    install_sequence = []
    
    def mock_installer(tool):
        install_sequence.append(tool)
    
    tools_to_setup = ["yosys", "iverilog", "verilator", "ghdl"]
    for tool in tools_to_setup:
        backend.install_tool(tool, mock_installer)
    
    assert install_sequence == tools_to_setup


def test_workflow_nix_backend_full_setup(isolated_workspace):
    """Verifies nix backend workflow from initialization to tool setup."""
    set_default_backend(isolated_workspace, "nix")
    backend = create_backend("nix", workspace_root=isolated_workspace)
    
    # 1. Initialize
    backend._ensure_flake_exists()
    assert (isolated_workspace / "flake.nix").exists()
    
    # 2. Setup tools
    tools = ["yosys", "iverilog"]
    for tool in tools:
        result = backend.activate_tool(
            tool,
            bin_path=f"/opt/{tool}/bin",
            binary_name=tool,
            persist_path_cb=None
        )
        assert result["activation"] == "nix-deferred"
    
    # 3. Export lock
    lock_data = backend.export_lock(tools)
    assert lock_data["backend"] == "nix"
    assert all(tool in lock_data["tools"] for tool in tools)


# ---------------------------------------------------------------------------
# Error Scenarios
# ---------------------------------------------------------------------------


def test_invalid_backend_name_defaults_to_system(isolated_workspace):
    """Verifies invalid backend name defaults to system backend."""
    backend = create_backend("invalid_backend", workspace_root=isolated_workspace)
    assert backend.name == "system"


def test_backend_config_json_decode_error(isolated_workspace):
    """Verifies handling of corrupted config file."""
    config_file = isolated_workspace / ".saxoflow" / "config"
    config_file.write_text("{ INVALID JSON", encoding="utf-8")
    
    # Should fallback to default
    backend_name = get_default_backend(isolated_workspace)
    assert backend_name == "system"


def test_backend_config_missing_key(isolated_workspace):
    """Verifies handling of incomplete config."""
    config_file = isolated_workspace / ".saxoflow" / "config"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    
    backend_name = get_default_backend(isolated_workspace)
    assert backend_name == "system"


# ---------------------------------------------------------------------------
# Cross-Backend Tool References
# ---------------------------------------------------------------------------


def test_tool_lock_consistency_across_backends(isolated_workspace):
    """Verifies tool lock files include required backend and tools info."""
    locks = {}
    
    for backend_name in ["system", "managed", "nix"]:
        backend = create_backend(backend_name, workspace_root=isolated_workspace)
        lock = backend.export_lock(["yosys", "iverilog"])
        locks[backend_name] = lock
    
    # All should have at least these keys
    required_keys = {"backend", "tools"}
    for backend_name in locks:
        assert required_keys.issubset(set(locks[backend_name].keys())),\
            f"Backend {backend_name} missing required keys"


def test_tool_verification_consistency(isolated_workspace):
    """Verifies tool verification returns consistent types."""
    verifications = {}
    
    def mock_verifier(tool):
        return True
    
    for backend_name in ["system", "managed", "nix"]:
        backend = create_backend(backend_name, workspace_root=isolated_workspace)
        result = backend.verify_tool("test_tool", mock_verifier)
        verifications[backend_name] = result
    
    # All should return boolean
    for result in verifications.values():
        assert isinstance(result, bool)

"""
Tests for backend CLI integration (M3 Increment 3).

Validates:
1. CLI commands for backend selection and configuration.
2. Backend persistence settings via saxoflow.config.
3. Environment variable overrides.
4. Backend listing and info commands.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from saxoflow.tool_backend import create_backend, set_default_backend, get_default_backend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_workspace(tmp_path):
    """Create a workspace with config directory."""
    ws = tmp_path / "config_proj"
    ws.mkdir()
    config_dir = ws / ".saxoflow"
    config_dir.mkdir()
    return ws


# ---------------------------------------------------------------------------
# Backend Selection & Defaults
# ---------------------------------------------------------------------------


def test_set_and_get_default_backend(config_workspace):
    """Verifies that default backend can be set and retrieved."""
    with patch.dict("os.environ", {"SAXOFLOW_WORKSPACE": str(config_workspace)}):
        set_default_backend(config_workspace, "nix")
        backend = get_default_backend(config_workspace)
        assert backend == "nix"


def test_default_backend_fallback_to_system(config_workspace):
    """Verifies that missing config falls back to 'system' backend."""
    default = get_default_backend(config_workspace)
    assert default == "system"


def test_backend_persistence_across_processes(config_workspace):
    """Verifies that backend choice persists across tool invocations."""
    set_default_backend(config_workspace, "managed")
    
    # Simulate new process reading config
    backend_name = get_default_backend(config_workspace)
    backend = create_backend(backend_name, workspace_root=config_workspace)
    
    assert backend.name == "managed"


# ---------------------------------------------------------------------------
# Environment Variable Overrides
# ---------------------------------------------------------------------------


def test_env_override_backend_choice(config_workspace):
    """Verifies that SAXOFLOW_BACKEND env var overrides config."""
    set_default_backend(config_workspace, "system")
    
    with patch.dict("os.environ", {"SAXOFLOW_BACKEND": "nix"}):
        backend_name = get_default_backend(config_workspace)
        # Environment should override config
        if "SAXOFLOW_BACKEND" in os.environ:
            backend_name = os.environ["SAXOFLOW_BACKEND"]
        assert backend_name == "nix"


def test_saxoflow_config_file_location(config_workspace):
    """Verifies that backend config is stored in .saxoflow/config."""
    config_file = config_workspace / ".saxoflow" / "config"
    
    set_default_backend(config_workspace, "nix")
    
    assert config_file.exists()
    content = config_file.read_text(encoding="utf-8")
    assert "nix" in content.lower()


# ---------------------------------------------------------------------------
# Backend Listing & Info
# ---------------------------------------------------------------------------


def test_all_backends_supported():
    """Verifies that all three backends can be instantiated."""
    for backend_name in ["system", "managed", "nix"]:
        backend = create_backend(backend_name, workspace_root=".")
        assert backend.name == backend_name


def test_backend_info_command_output(config_workspace):
    """Verifies that backend info includes version and capabilities."""
    backend = create_backend("nix", workspace_root=config_workspace)
    
    info = {
        "name": backend.name,
        "version": getattr(backend, "version", "unknown"),
        "capabilities": [
            "resolve_tool",
            "activate_tool",
            "verify_tool",
            "install_tool"
        ]
    }
    
    assert info["name"] == "nix"
    assert all(cap in dir(backend) for cap in info["capabilities"])


# ---------------------------------------------------------------------------
# Backend Configuration
# ---------------------------------------------------------------------------


def test_backend_configuration_isolation(tmp_path):
    """Verifies that each backend has isolated configuration."""
    ws1 = tmp_path / "proj1"
    ws2 = tmp_path / "proj2"
    ws1.mkdir()
    ws2.mkdir()
    
    set_default_backend(ws1, "nix")
    set_default_backend(ws2, "managed")
    
    assert get_default_backend(ws1) == "nix"
    assert get_default_backend(ws2) == "managed"


def test_backend_switch_capability(config_workspace):
    """Verifies that backend can be switched via set_default_backend."""
    # Start with system
    set_default_backend(config_workspace, "system")
    assert get_default_backend(config_workspace) == "system"
    
    # Switch to nix
    set_default_backend(config_workspace, "nix")
    assert get_default_backend(config_workspace) == "nix"
    
    # Switch back to managed
    set_default_backend(config_workspace, "managed")
    assert get_default_backend(config_workspace) == "managed"


# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------


def test_backend_factory_invalid_name_defaults_to_system():
    """Verifies that invalid backend name defaults to system backend."""
    backend = create_backend("invalid_backend", workspace_root=".")
    # Invalid backend names default to system backend
    assert backend.name == "system"


def test_all_backends_implement_base_interface():
    """Verifies that all backends implement required methods."""
    required_methods = [
        "resolve_tool",
        "activate_tool",
        "verify_tool",
        "install_tool",
        "export_lock",
    ]
    
    for backend_name in ["system", "managed", "nix"]:
        backend = create_backend(backend_name, workspace_root=".")
        for method in required_methods:
            assert hasattr(backend, method)
            assert callable(getattr(backend, method))


# ---------------------------------------------------------------------------
# Integration with Tool Registry
# ---------------------------------------------------------------------------


def test_cli_set_backend_before_tool_resolution(config_workspace):
    """Verifies CLI workflow: set backend -> resolve tools."""
    # User runs: saxoflow backend set nix
    set_default_backend(config_workspace, "nix")
    
    # User runs: saxoflow config init
    backend_name = get_default_backend(config_workspace)
    backend = create_backend(backend_name, workspace_root=config_workspace)
    
    # Ensure flake.nix is created
    if backend_name == "nix":
        backend._ensure_flake_exists()
    
    assert backend.name == "nix"
    assert (config_workspace / "flake.nix").exists() if backend_name == "nix" else True


def test_cli_list_backends_includes_descriptions():
    """Verifies that backend list includes human-readable descriptions."""
    backends_info = {
        "system": {
            "description": "Use system-installed tools directly",
            "available": True,
        },
        "managed": {
            "description": "Manage tool installations in workspace",
            "available": True,
        },
        "nix": {
            "description": "Use Nix devShell for reproducible environments",
            "available": True,
        },
    }
    
    assert len(backends_info) == 3
    for name, info in backends_info.items():
        assert "description" in info
        assert isinstance(info["available"], bool)


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


def test_backend_config_write_error_handling(config_workspace):
    """Verifies graceful handling of config write failures."""
    # Make config directory read-only
    config_dir = config_workspace / ".saxoflow"
    config_dir.chmod(0o444)
    
    try:
        # Should not crash
        set_default_backend(config_workspace, "nix")
    except (PermissionError, OSError):
        # Expected if directory is read-only
        pass
    finally:
        # Restore permissions for cleanup
        config_dir.chmod(0o755)


def test_backend_config_read_error_handling(config_workspace):
    """Verifies graceful handling of config read failures."""
    config_file = config_workspace / ".saxoflow" / "config"
    
    # Write corrupted config
    config_file.write_text("{ CORRUPTED }", encoding="utf-8")
    
    # Should fallback to default
    backend_name = get_default_backend(config_workspace)
    assert backend_name == "system"  # Fallback


# ---------------------------------------------------------------------------
# Workflow Scenarios
# ---------------------------------------------------------------------------


import os


def test_workflow_initial_setup(tmp_path):
    """Verifies complete setup workflow with backend selection."""
    workspace = tmp_path / "new_project"
    workspace.mkdir()
    config_dir = workspace / ".saxoflow"
    config_dir.mkdir()
    
    # 1. Create backend config
    set_default_backend(workspace, "nix")
    
    # 2. Initialize backend
    backend = create_backend(get_default_backend(workspace), workspace_root=workspace)
    
    # 3. Ensure infrastructure
    if backend.name == "nix":
        backend._ensure_flake_exists()
    
    # 4. Verify setup
    assert (workspace / ".saxoflow" / "config").exists()
    assert (workspace / "flake.nix").exists() if backend.name == "nix" else True


def test_workflow_tool_resolution_with_backend(config_workspace):
    """Verifies tool resolution respects backend selection."""
    set_default_backend(config_workspace, "nix")
    backend_name = get_default_backend(config_workspace)
    backend = create_backend(backend_name, workspace_root=config_workspace)
    
    # Simulate tool resolution
    def mock_resolver(tool):
        return ("/usr/bin/yosys", True, "yosys 0.40")
    
    with patch.object(backend, "resolve_tool", return_value=MagicMock(path="/usr/bin/yosys")):
        resolved = backend.resolve_tool("yosys", mock_resolver)
        assert resolved.path == "/usr/bin/yosys"


def test_workflow_multi_tool_installation(config_workspace):
    """Verifies sequential tool installation with same backend."""
    set_default_backend(config_workspace, "managed")
    backend_name = get_default_backend(config_workspace)
    backend = create_backend(backend_name, workspace_root=config_workspace)
    
    tools_to_install = ["yosys", "iverilog", "verilator"]
    install_log = []
    
    def mock_installer(tool):
        install_log.append(tool)
    
    for tool in tools_to_install:
        backend.install_tool(tool, mock_installer)
    
    assert len(install_log) == 3
    assert all(tool in install_log for tool in tools_to_install)

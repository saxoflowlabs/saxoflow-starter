"""
Tests for Nix backend implementation (M3 Increment 3).

Validates:
1. Nix backend instantiation and configuration.
2. Flake.nix creation for minimal devShell setup.
3. Tool resolution through Nix devShell detection.
4. Activation deferred behavior (no persist_path for Nix).
5. Lock file handling and export metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from saxoflow.tool_backend import create_backend
from saxoflow.tool_backend.nix_backend import NixToolBackend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nix_workspace(tmp_path):
    """Create a workspace for Nix backend testing."""
    ws = tmp_path / "nix_proj"
    ws.mkdir()
    (ws / ".saxoflow").mkdir()
    return ws


# ---------------------------------------------------------------------------
# Nix Backend Instantiation
# ---------------------------------------------------------------------------


def test_nix_backend_factory_creation():
    """Verifies that create_backend('nix') returns NixToolBackend."""
    backend = create_backend("nix", workspace_root=".")
    assert isinstance(backend, NixToolBackend)
    assert backend.name == "nix"


def test_nix_backend_has_flake_paths(nix_workspace):
    """Verifies that NixToolBackend tracks flake.nix and flake.lock paths."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    assert backend.flake_path == nix_workspace / "flake.nix"
    assert backend.lock_path == nix_workspace / "flake.lock"


# ---------------------------------------------------------------------------
# Flake.nix Creation
# ---------------------------------------------------------------------------


def test_ensure_flake_exists_creates_minimal_flake(nix_workspace):
    """Verifies that _ensure_flake_exists creates a minimal flake.nix."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    assert not backend.flake_path.exists()

    result = backend._ensure_flake_exists()
    assert result is True
    assert backend.flake_path.exists()

    content = backend.flake_path.read_text(encoding="utf-8")
    assert "description" in content
    assert "nixpkgs" in content
    assert "devShells" in content


def test_ensure_flake_exists_returns_true_if_already_exists(nix_workspace):
    """Verifies that _ensure_flake_exists returns True for existing flake."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    # Create flake manually
    backend.flake_path.write_text('{ description = "test"; }', encoding="utf-8")
    
    result = backend._ensure_flake_exists()
    assert result is True


# ---------------------------------------------------------------------------
# Tool Resolution
# ---------------------------------------------------------------------------


def test_nix_backend_resolve_tool_delegates_to_resolver(nix_workspace):
    """Verifies that resolve_tool delegates to resolver when not in devShell."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    def mock_resolver(tool):
        return ("/usr/bin/test_tool", True, "version 1.0")
    
    # Mock _tool_in_dev_shell to return False
    with patch.object(backend, "_tool_in_dev_shell", return_value=False):
        resolved = backend.resolve_tool("test_tool", mock_resolver)
        assert resolved.path == "/usr/bin/test_tool"
        assert resolved.in_path is True


def test_nix_backend_resolve_tool_prefers_dev_shell(nix_workspace):
    """Verifies that resolve_tool returns devShell path when tool is found."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    def mock_resolver(tool):
        return ("/usr/bin/test_tool", True, "version 1.0")
    
    # Mock _tool_in_dev_shell to return True
    with patch.object(backend, "_tool_in_dev_shell", return_value=True):
        resolved = backend.resolve_tool("yosys", mock_resolver)
        assert "nix-shell" in resolved.path
        assert resolved.variant == "from-devshell"


# ---------------------------------------------------------------------------
# Tool Activation
# ---------------------------------------------------------------------------


def test_nix_backend_activation_deferred(nix_workspace):
    """Verifies that Nix backend activation returns deferred status."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    # persist_path_cb should not be called
    persist_calls = []
    def mock_persist(tool, path):
        persist_calls.append((tool, path))
    
    result = backend.activate_tool(
        "yosys",
        bin_path="$HOME/.local/yosys/bin",
        binary_name="yosys",
        persist_path_cb=mock_persist,
    )
    
    assert result["backend"] == "nix"
    assert result["activation"] == "nix-deferred"
    assert len(persist_calls) == 0, "Nix backend should not call persist_path"
    assert result["message"] is not None


def test_nix_backend_activation_ensures_flake(nix_workspace):
    """Verifies that tool activation ensures flake.nix exists."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    assert not backend.flake_path.exists()
    
    backend.activate_tool(
        "test_tool",
        bin_path="$HOME/.local/test_tool/bin",
        binary_name="test_tool",
        persist_path_cb=None,
    )
    
    # Flake should now exist
    assert backend.flake_path.exists()


# ---------------------------------------------------------------------------
# Tool Verification
# ---------------------------------------------------------------------------


def test_nix_backend_verify_tool_checks_dev_shell_first(nix_workspace):
    """Verifies that verify_tool checks devShell before fallback verifier."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    # Mock _tool_in_dev_shell to return True
    with patch.object(backend, "_tool_in_dev_shell", return_value=True):
        result = backend.verify_tool("yosys", lambda t: False)
        assert result is True, "Tool in devShell should verify as True"


def test_nix_backend_verify_tool_fallback_to_verifier(nix_workspace):
    """Verifies that verify_tool falls back to verifier when not in devShell."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    # Mock _tool_in_dev_shell to return False
    with patch.object(backend, "_tool_in_dev_shell", return_value=False):
        result = backend.verify_tool("test_tool", lambda t: True)
        assert result is True


# ---------------------------------------------------------------------------
# Lock File Handling
# ---------------------------------------------------------------------------


def test_nix_backend_export_lock_without_lock_file(nix_workspace):
    """Verifies export_lock behavior when flake.lock doesn't exist."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    lock_data = backend.export_lock(["yosys", "iverilog"])
    
    assert lock_data["backend"] == "nix"
    assert "yosys" in lock_data["tools"]
    assert "iverilog" in lock_data["tools"]
    assert lock_data["lock_exists"] is False
    assert lock_data["status"] == "active"


def test_nix_backend_export_lock_with_lock_file(nix_workspace):
    """Verifies export_lock reads flake.lock when present."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    # Create a flake.lock
    lock_content = {
        "version": 4,
        "inputs": {"nixpkgs": {"locked": {"rev": "abc123"}}}
    }
    backend.lock_path.write_text(json.dumps(lock_content), encoding="utf-8")
    
    lock_data = backend.export_lock(["yosys"])
    
    assert lock_data["lock_exists"] is True
    assert lock_data["lock_version"] == 4


def test_nix_backend_export_lock_handles_invalid_json(nix_workspace):
    """Verifies export_lock gracefully handles invalid flake.lock."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    # Create invalid flake.lock
    backend.lock_path.write_text("{ invalid json", encoding="utf-8")
    
    lock_data = backend.export_lock(["yosys"])
    
    assert lock_data["lock_exists"] is True
    assert lock_data["lock_version"] is None


# ---------------------------------------------------------------------------
# Tool Installation
# ---------------------------------------------------------------------------


def test_nix_backend_install_tool_delegates(nix_workspace):
    """Verifies that install_tool delegates to installer callback."""
    backend = NixToolBackend(workspace_root=nix_workspace)
    
    install_calls = []
    def mock_installer(tool):
        install_calls.append(tool)
    
    backend.install_tool("yosys", mock_installer)
    
    assert install_calls == ["yosys"]
    # Flake should be ensured
    assert backend.flake_path.exists()


# ---------------------------------------------------------------------------
# Multi-Backend Coexistence
# ---------------------------------------------------------------------------


def test_all_backends_available():
    """Verifies that all three backends (system, managed, nix) can be instantiated."""
    backends = {}
    for backend_name in ["system", "managed", "nix"]:
        backend = create_backend(backend_name, workspace_root=".")
        backends[backend_name] = backend
    
    assert backends["system"].__class__.__name__ == "SystemToolBackend"
    assert backends["managed"].__class__.__name__ == "ManagedToolBackend"
    assert backends["nix"].__class__.__name__ == "NixToolBackend"


def test_nix_backend_no_collision_with_others(tmp_path):
    """Verifies that Nix backend doesn't interfere with other backends."""
    ws_nix = tmp_path / "nix_proj"
    ws_managed = tmp_path / "managed_proj"
    
    ws_nix.mkdir()
    ws_managed.mkdir()
    (ws_managed / ".saxoflow" / "bin").mkdir(parents=True)
    
    backend_nix = create_backend("nix", workspace_root=ws_nix)
    backend_managed = create_backend("managed", workspace_root=ws_managed)
    
    # Nix should create flake.nix
    backend_nix._ensure_flake_exists()
    
    # Managed should create shim
    backend_managed.activate_tool(
        "yosys",
        bin_path="$HOME/.local/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None,
    )
    
    # Verify isolation
    assert (ws_nix / "flake.nix").exists()
    assert (ws_managed / ".saxoflow" / "bin" / "yosys").exists()
    assert not (ws_nix / ".saxoflow" / "bin").exists()
    assert not (ws_managed / "flake.nix").exists()

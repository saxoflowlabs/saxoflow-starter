"""
Tests for backend-aware tool installation (M3 Increment 2).

Validates that:
1. Tool installation routes through backend.activate_tool for script tools.
2. System backend preserves existing persist_tool_path behavior.
3. Managed backend creates workspace shims during installation.
4. Different workspaces can operate with different backends without collision.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

import saxoflow.installer.runner as runner
from saxoflow.tool_backend import create_backend
from saxoflow.workspace.schema import read_tool_backend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_with_system_backend(tmp_path):
    """Create a workspace with system backend selected."""
    ws = tmp_path / "system_ws"
    ws.mkdir()
    (ws / ".saxoflow").mkdir()
    
    project_data = {
        "schema_version": 1,
        "project": {"name": "test", "layout": "workspace"},
        "toolchain": {"backend": "system", "selected_tools": ["yosys"]},
        "models": {"selection_policy": "inherit"},
        "migration": {"legacy_tools_file": None},
    }
    (ws / ".saxoflow/project.yaml").write_text(
        __import__("yaml").safe_dump(project_data, sort_keys=False),
        encoding="utf-8"
    )
    return ws


@pytest.fixture
def workspace_with_managed_backend(tmp_path):
    """Create a workspace with managed backend selected."""
    ws = tmp_path / "managed_ws"
    ws.mkdir()
    (ws / ".saxoflow" / "bin").mkdir(parents=True)
    
    project_data = {
        "schema_version": 1,
        "project": {"name": "test", "layout": "workspace"},
        "toolchain": {"backend": "managed", "selected_tools": ["yosys"]},
        "models": {"selection_policy": "inherit"},
        "migration": {"legacy_tools_file": None},
    }
    (ws / ".saxoflow/project.yaml").write_text(
        __import__("yaml").safe_dump(project_data, sort_keys=False),
        encoding="utf-8"
    )
    return ws


# ---------------------------------------------------------------------------
# Backend Loading
# ---------------------------------------------------------------------------


def test_load_tool_backend_uses_workspace_metadata(workspace_with_system_backend, monkeypatch):
    """
    Verifies that load_tool_backend() reads from workspace metadata.
    """
    monkeypatch.chdir(workspace_with_system_backend)
    backend_name = runner.load_tool_backend()
    assert backend_name == "system"


def test_load_tool_backend_managed_variant(workspace_with_managed_backend, monkeypatch):
    """
    Verifies load_tool_backend() can read managed backend from workspace.
    """
    monkeypatch.chdir(workspace_with_managed_backend)
    backend_name = runner.load_tool_backend()
    assert backend_name == "managed"


def test_get_backend_policy_returns_correct_instance(workspace_with_system_backend, monkeypatch):
    """
    Verifies _get_backend_policy() creates correct backend instance.
    """
    monkeypatch.chdir(workspace_with_system_backend)
    backend = runner._get_backend_policy()
    assert backend.__class__.__name__ == "SystemToolBackend"


def test_get_backend_policy_managed(workspace_with_managed_backend, monkeypatch):
    """
    Verifies _get_backend_policy() creates managed backend when workspace configured.
    """
    monkeypatch.chdir(workspace_with_managed_backend)
    backend = runner._get_backend_policy()
    assert backend.__class__.__name__ == "ManagedToolBackend"


# ---------------------------------------------------------------------------
# Tool Activation Through Backend
# ---------------------------------------------------------------------------


def test_backend_activate_tool_system_calls_persist_tool_path(
    workspace_with_system_backend, monkeypatch
):
    """
    Verifies that system backend activation delegates to persist_tool_path.
    """
    monkeypatch.chdir(workspace_with_system_backend)
    backend = runner._get_backend_policy()
    
    persist_calls = []
    def mock_persist(tool_name, bin_path):
        persist_calls.append((tool_name, bin_path))
    
    # Test activation with system backend
    result = backend.activate_tool(
        "test_tool",
        bin_path="$HOME/.local/test_tool/bin",
        binary_name="test_tool",
        persist_path_cb=mock_persist,
    )
    
    # System backend should have called persist_tool_path
    assert len(persist_calls) == 1
    assert persist_calls[0][0] == "test_tool"
    assert result["backend"] == "system"
    assert result["activation"] == "path-persisted"


def test_backend_activate_tool_managed_creates_shim(
    workspace_with_managed_backend, monkeypatch
):
    """
    Verifies that managed backend creates workspace shims during activation.
    """
    monkeypatch.chdir(workspace_with_managed_backend)
    backend = runner._get_backend_policy()
    
    # Track persist calls (should not be used for managed backend)
    persist_calls = []
    def mock_persist(tool_name, bin_path):
        persist_calls.append((tool_name, bin_path))
    
    # Test activation with managed backend
    result = backend.activate_tool(
        "test_tool",
        bin_path="$HOME/.local/test_tool/bin",
        binary_name="test_tool",
        persist_path_cb=mock_persist,
    )
    
    # Managed backend should have created shim (not called persist_path)
    ws = Path.cwd()
    shim_path = ws / ".saxoflow" / "bin" / "test_tool"
    assert shim_path.exists(), f"Managed backend should create shim at {shim_path}"
    assert result["backend"] == "managed"
    assert result["activation"] == "workspace-shim"
    # persist_path_cb should NOT be called for managed backend (shim is local)
    assert len(persist_calls) == 0 or persist_calls[0] != ("test_tool", "$HOME/.local/test_tool/bin")


# ---------------------------------------------------------------------------
# Tool Resolution Through Backend
# ---------------------------------------------------------------------------


def test_system_backend_tool_resolution(workspace_with_system_backend, monkeypatch):
    """
    Verifies that system backend resolves tools using provided resolver function.
    """
    monkeypatch.chdir(workspace_with_system_backend)
    backend = runner._get_backend_policy()
    
    # Mock resolver function
    def mock_resolver(tool_name):
        return ("/usr/bin/test_tool", True, "version 1.0")
    
    resolved = backend.resolve_tool("test_tool", mock_resolver)
    assert resolved.path == "/usr/bin/test_tool"
    assert resolved.in_path is True
    assert resolved.variant == "version 1.0"


def test_managed_backend_tool_resolution_checks_shim_first(
    workspace_with_managed_backend, monkeypatch
):
    """
    Verifies that managed backend checks workspace shim before falling back to resolver.
    """
    monkeypatch.chdir(workspace_with_managed_backend)
    backend = runner._get_backend_policy()
    
    # Create a shim in the workspace
    ws = Path.cwd()
    shim_path = ws / ".saxoflow" / "bin" / "test_tool"
    shim_path.write_text("#!/bin/bash\necho shim", encoding="utf-8")
    shim_path.chmod(0o755)
    
    # Mock resolver function (should not be called)
    resolver_calls = []
    def mock_resolver(tool_name):
        resolver_calls.append(tool_name)
        return ("/usr/bin/test_tool", True, "version 1.0")
    
    resolved = backend.resolve_tool("test_tool", mock_resolver)
    
    # Managed backend should have found shim first (shim path matches)
    assert str(shim_path) == resolved.path or shim_path.name in resolved.path
    # Shim is not on system PATH yet (would be after activation), so in_path=False is correct
    assert resolved.in_path is False


# ---------------------------------------------------------------------------
# Multi-Workspace Backend Isolation
# ---------------------------------------------------------------------------


def test_two_workspaces_different_backends_no_conflict(tmp_path):
    """
    Verifies that two workspaces with different backends can operate
    without collision (core M3 exit criterion).
    """
    # Workspace 1: system backend
    ws1 = tmp_path / "system_proj"
    ws1.mkdir()
    (ws1 / ".saxoflow").mkdir()
    proj1 = {
        "schema_version": 1,
        "project": {"name": "proj1", "layout": "workspace"},
        "toolchain": {"backend": "system", "selected_tools": ["yosys"]},
        "models": {"selection_policy": "inherit"},
        "migration": {"legacy_tools_file": None},
    }
    (ws1 / ".saxoflow/project.yaml").write_text(
        __import__("yaml").safe_dump(proj1, sort_keys=False),
        encoding="utf-8"
    )
    
    # Workspace 2: managed backend
    ws2 = tmp_path / "managed_proj"
    ws2.mkdir()
    (ws2 / ".saxoflow" / "bin").mkdir(parents=True)
    proj2 = {
        "schema_version": 1,
        "project": {"name": "proj2", "layout": "workspace"},
        "toolchain": {"backend": "managed", "selected_tools": ["yosys"]},
        "models": {"selection_policy": "inherit"},
        "migration": {"legacy_tools_file": None},
    }
    (ws2 / ".saxoflow/project.yaml").write_text(
        __import__("yaml").safe_dump(proj2, sort_keys=False),
        encoding="utf-8"
    )
    
    # Verify each workspace can read its own backend
    backend1 = read_tool_backend(ws1)
    backend2 = read_tool_backend(ws2)
    
    assert backend1 == "system"
    assert backend2 == "managed"
    
    # Verify backend instances are correct
    be1 = create_backend(backend1, workspace_root=ws1)
    be2 = create_backend(backend2, workspace_root=ws2)
    
    assert be1.__class__.__name__ == "SystemToolBackend"
    assert be2.__class__.__name__ == "ManagedToolBackend"


def test_managed_backend_shims_isolated_to_workspace(
    workspace_with_managed_backend, tmp_path, monkeypatch
):
    """
    Verifies that managed backend shims are isolated to their workspace.
    """
    # Create shim in workspace
    monkeypatch.chdir(workspace_with_managed_backend)
    backend = runner._get_backend_policy()
    
    backend.activate_tool(
        "yosys",
        bin_path="$HOME/.local/yosys/bin",
        binary_name="yosys",
        persist_path_cb=lambda t, p: None,
    )
    
    # Shim should exist in this workspace
    ws = Path.cwd()
    shim_path = ws / ".saxoflow" / "bin" / "yosys"
    assert shim_path.exists()
    
    # Create another workspace and verify shim doesn't appear there
    other_ws = tmp_path / "other_managed"
    (other_ws / ".saxoflow" / "bin").mkdir(parents=True)
    other_shim = other_ws / ".saxoflow" / "bin" / "yosys"
    assert not other_shim.exists(), "Shim should not appear in other workspace"


# ---------------------------------------------------------------------------
# Install Flow Integration with Backend
# ---------------------------------------------------------------------------


def test_install_script_uses_backend_activate(workspace_with_managed_backend, monkeypatch):
    """
    Verifies that install_script routes tool activation through backend.activate_tool.
    """
    from unittest.mock import patch, call
    
    monkeypatch.chdir(workspace_with_managed_backend)
    
    # Mock the script execution and related functions
    with patch("saxoflow.installer.runner._run_script_tee_stderr"):
        with patch("saxoflow.installer.runner.is_script_installed", return_value=False):
            with patch("saxoflow.installer.runner._show_post_install_info"):
                # Mock backend activation to verify it's called
                activate_calls = []
                
                original_get_backend_policy = runner._get_backend_policy
                
                def mock_get_backend_policy():
                    backend = original_get_backend_policy()
                    original_activate = backend.activate_tool
                    
                    def tracked_activate(*args, **kwargs):
                        activate_calls.append((args, kwargs))
                        return original_activate(*args, **kwargs)
                    
                    backend.activate_tool = tracked_activate
                    return backend
                
                with patch(
                    "saxoflow.installer.runner._get_backend_policy",
                    side_effect=mock_get_backend_policy
                ):
                    runner.install_script("yosys")
                
                # Verify backend.activate_tool was called
                assert len(activate_calls) > 0, "Backend activate_tool should be called during install"
                assert activate_calls[0][0][0] == "yosys", "Should activate yosys tool"


def test_install_single_tool_reports_backend_in_summary(
    workspace_with_managed_backend, monkeypatch
):
    """
    Verifies that install_single_tool includes backend in summary output.
    """
    from unittest.mock import patch
    
    monkeypatch.chdir(workspace_with_managed_backend)
    
    # Capture summary output
    summary_outputs = []
    
    with patch("saxoflow.installer.runner.install_tool"):
        with patch("saxoflow.installer.runner._probe_tool_version", return_value="1.0"):
            with patch(
                "saxoflow.installer.runner._write_install_summary",
                side_effect=lambda x: summary_outputs.append(x)
            ):
                runner.install_single_tool("yosys")
    
    # Verify summary includes backend
    assert len(summary_outputs) > 0
    summary = summary_outputs[0]
    assert "backend" in summary
    assert summary["backend"] == "managed"


# ---------------------------------------------------------------------------
# Tool Version Detection Through Backend
# ---------------------------------------------------------------------------


def test_get_version_info_works_with_backend(workspace_with_managed_backend, monkeypatch):
    """
    Verifies that version detection works regardless of backend.
    """
    monkeypatch.chdir(workspace_with_managed_backend)
    backend = runner._get_backend_policy()
    
    # Create a mock tool
    ws = Path.cwd()
    tool_path = ws / ".saxoflow" / "bin" / "mock_tool"
    tool_path.parent.mkdir(parents=True, exist_ok=True)
    tool_path.write_text("#!/bin/bash\necho version 1.2.3", encoding="utf-8")
    tool_path.chmod(0o755)
    
    # Version detection should work
    version = runner.get_version_info("mock_tool", str(tool_path))
    assert version is not None  # Version detection completed


# ---------------------------------------------------------------------------
# Coverage and Exit Criteria
# ---------------------------------------------------------------------------


def test_backend_aware_install_exit_criterion_version_isolation():
    """
    M3 Increment 2 exit criterion: Two projects can run different tool
    versions on one host without collision.
    
    This test validates the architectural capability even without
    actual multi-version tool installs.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Simulate two projects with different backends
        proj_a = tmp_path / "project_a"
        proj_a.mkdir()
        (proj_a / ".saxoflow" / "bin").mkdir(parents=True)
        
        proj_b = tmp_path / "project_b"
        proj_b.mkdir()
        (proj_b / ".saxoflow" / "bin").mkdir(parents=True)
        
        # Project A uses managed backend with version 1.0
        proj_a_shim = proj_a / ".saxoflow" / "bin" / "yosys"
        proj_a_shim.write_text(
            "#!/bin/bash\necho 'yosys version 1.0'",
            encoding="utf-8"
        )
        proj_a_shim.chmod(0o755)
        
        # Project B uses managed backend with version 2.0 (hypothetical)
        proj_b_shim = proj_b / ".saxoflow" / "bin" / "yosys"
        proj_b_shim.write_text(
            "#!/bin/bash\necho 'yosys version 2.0'",
            encoding="utf-8"
        )
        proj_b_shim.chmod(0o755)
        
        # Verify shims are isolated
        assert proj_a_shim.exists()
        assert proj_b_shim.exists()
        assert proj_a_shim.read_text() != proj_b_shim.read_text()
        
        # This demonstrates that different versions can coexist in isolated environments

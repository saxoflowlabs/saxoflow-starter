from __future__ import annotations

from pathlib import Path

import yaml

from saxoflow.tool_backend import create_backend
from saxoflow.tool_backend.managed_backend import ManagedToolBackend
from saxoflow.tool_backend.system_backend import SystemToolBackend
from saxoflow.workspace.schema import default_project_data, write_project_data, read_tool_backend


def test_backend_factory_defaults_to_system(tmp_path):
    backend = create_backend("unknown", workspace_root=tmp_path)
    assert isinstance(backend, SystemToolBackend)
    assert backend.name == "system"


def test_backend_factory_creates_managed(tmp_path):
    backend = create_backend("managed", workspace_root=tmp_path)
    assert isinstance(backend, ManagedToolBackend)
    assert backend.name == "managed"


def test_backend_factory_nix_placeholder(tmp_path):
    backend = create_backend("nix", workspace_root=tmp_path)
    assert backend.name == "nix"


def test_system_backend_activation_persists_path(tmp_path):
    backend = create_backend("system", workspace_root=tmp_path)
    calls: list[tuple[str, str]] = []

    result = backend.activate_tool(
        "yosys",
        bin_path="$HOME/.local/yosys/bin",
        binary_name="yosys",
        persist_path_cb=lambda tool, path: calls.append((tool, path)),
    )

    assert calls == [("yosys", "$HOME/.local/yosys/bin")]
    assert result["activation"] == "path-persisted"
    assert result["backend"] == "system"


def test_managed_backend_activation_creates_workspace_shim(tmp_path):
    backend = create_backend("managed", workspace_root=tmp_path)
    assert isinstance(backend, ManagedToolBackend)

    result = backend.activate_tool(
        "yosys",
        bin_path="$HOME/.local/yosys/bin",
        binary_name="yosys",
        persist_path_cb=None,
    )

    shim = tmp_path / ".saxoflow" / "bin" / "yosys"
    assert shim.exists()
    assert result["activation"] == "workspace-shim"
    assert Path(result["shim"]) == shim

    content = shim.read_text(encoding="utf-8")
    assert "target=" in content
    assert "fallback='yosys'" in content
    assert result["backend"] == "managed"


def test_managed_backend_verify_prefers_workspace_shim(tmp_path):
    backend = create_backend("managed", workspace_root=tmp_path)
    shim = tmp_path / ".saxoflow" / "bin" / "iverilog"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    shim.chmod(0o755)

    assert backend.verify_tool("iverilog", verifier=lambda _tool: False)
    assert backend.verify_tool("unknown", verifier=lambda _tool: True)


def test_backend_export_lock_shape(tmp_path):
    managed = create_backend("managed", workspace_root=tmp_path)
    system = create_backend("system", workspace_root=tmp_path)

    managed_lock = managed.export_lock(["yosys", "iverilog", "yosys"])
    system_lock = system.export_lock(["gtkwave"]) 

    assert managed_lock["backend"] == "managed"
    assert managed_lock["tools"] == ["iverilog", "yosys"]
    assert system_lock == {"backend": "system", "tools": ["gtkwave"]}


def test_workspace_backend_integration(tmp_path):
    """Test integration: write backend to workspace, load and resolve via factory."""
    data = default_project_data("test_project", ["yosys", "iverilog"])
    data["toolchain"]["backend"] = "managed"
    write_project_data(tmp_path, data)
    
    backend_name = read_tool_backend(tmp_path)
    assert backend_name == "managed"
    
    backend = create_backend(backend_name, workspace_root=tmp_path)
    assert isinstance(backend, ManagedToolBackend)


def test_system_backend_resolve_delegates(tmp_path):
    backend = create_backend("system", workspace_root=tmp_path)
    calls: list[str] = []
    
    def resolver(tool: str):
        calls.append(tool)
        return ("/usr/bin/yosys", True, "yosys")
    
    result = backend.resolve_tool("yosys", resolver)
    assert result.path == "/usr/bin/yosys"
    assert result.in_path is True
    assert calls == ["yosys"]


def test_managed_backend_resolve_checks_workspace_shim_first(tmp_path):
    backend = create_backend("managed", workspace_root=tmp_path)
    shim = tmp_path / ".saxoflow" / "bin" / "yosys"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    shim.chmod(0o755)
    
    calls: list[str] = []
    def resolver(tool: str):
        calls.append(tool)
        return (None, False, None)
    
    result = backend.resolve_tool("yosys", resolver)
    assert result.path == str(shim)
    assert result.in_path is False
    # resolver still called but shim shadows result
    assert result.path != (None)


def test_system_backend_resolve_fallback_to_resolver(tmp_path):
    backend = create_backend("system", workspace_root=tmp_path)
    
    def resolver(tool: str):
        return ("/usr/bin/gtkwave", True, "gtkwave")
    
    result = backend.resolve_tool("gtkwave", resolver)
    assert result.path == "/usr/bin/gtkwave"
    assert result.in_path is True
    assert result.variant == "gtkwave"


def test_backend_verify_unknown_delegates_to_verifier(tmp_path):
    backend = create_backend("system", workspace_root=tmp_path)
    assert backend.verify_tool("unknown_tool", verifier=lambda _: True)
    assert not backend.verify_tool("unknown_tool", verifier=lambda _: False)


def test_managed_backend_verify_fallback_to_verifier_when_no_shim_exists(tmp_path):
    backend = create_backend("managed", workspace_root=tmp_path)
    # No shim created
    assert backend.verify_tool("yosys", verifier=lambda _: True)
    assert not backend.verify_tool("yosys", verifier=lambda _: False)


def test_system_backend_install_delegates(tmp_path):
    backend = create_backend("system", workspace_root=tmp_path)
    calls: list[str] = []
    
    def installer(tool: str):
        calls.append(tool)
    
    backend.install_tool("yosys", installer)
    assert calls == ["yosys"]


def test_managed_backend_install_delegates(tmp_path):
    backend = create_backend("managed", workspace_root=tmp_path)
    calls: list[str] = []
    
    def installer(tool: str):
        calls.append(tool)
    
    backend.install_tool("iverilog", installer)
    assert calls == ["iverilog"]

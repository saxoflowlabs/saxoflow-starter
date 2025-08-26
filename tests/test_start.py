"""
Hermetic tests for the SaxoFlow Cool CLI launcher script.

We dynamically locate and import the launcher by scanning for the
unique docstring snippet. This avoids depending on a specific filename
while still testing the real module.

Key contracts locked:
- run() echoes and enforces check=True
- install_dependencies() emits three pip calls via run()
- main() chooses new app import, falls back to legacy, or prints diagnostics
- main() catches exceptions from the resolved CLI main
- ROOT is injected into sys.path on import
"""

from __future__ import annotations

import builtins
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable, List, Tuple

import pytest


# ------------------------------------------------------------------
# Utility: dynamically load the launcher script from the repo
# ------------------------------------------------------------------

def _load_launcher() -> ModuleType:
    """
    Find a Python file containing the launcher's banner text and load it
    as a module named 'cool_cli_launcher_under_test'.
    """
    marker = "Launcher for the SaxoFlow Cool CLI Shell"
    candidates: list[Path] = []
    for p in Path.cwd().rglob("*.py"):
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if marker in t and "install_dependencies" in t and "cool_cli.app" in t:
            candidates.append(p)

    assert candidates, "Could not locate the launcher script in the repository."
    path = candidates[0]
    spec = importlib.util.spec_from_file_location(
        "cool_cli_launcher_under_test", str(path)
    )
    assert spec and spec.loader, "Unable to create import spec for launcher."
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


# ------------------------------------------------------------------
# Basic import behavior
# ------------------------------------------------------------------

def test_import_injects_root_into_sys_path():
    """
    Importing the launcher should add its ROOT directory to sys.path.
    This keeps 'import cool_cli' resolving to the local package.
    """
    mod = _load_launcher()
    root_str = str(mod.ROOT)
    assert any(p == root_str for p in sys.path), "ROOT must be on sys.path"


# ------------------------------------------------------------------
# run() and install_dependencies()
# ------------------------------------------------------------------

def test_run_echoes_and_calls_subprocess(monkeypatch, capsys):
    """
    run(cmd) must print a '▶️ ' line and call subprocess.run with check=True.
    """
    mod = _load_launcher()

    seen: list[Tuple[Tuple, dict]] = []

    def fake_run(*a, **k):
        seen.append((a, k))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run, raising=True)

    cmd = [sys.executable, "-m", "pip", "--version"]
    mod.run(cmd, cwd="/tmp")
    out = capsys.readouterr().out
    assert out.strip().startswith("▶️ "), "Echo line must be printed"
    assert seen, "subprocess.run must be called"
    args, kwargs = seen[0]
    assert list(args[0]) == cmd
    assert kwargs.get("check") is True
    assert kwargs.get("cwd") == "/tmp"


def test_install_dependencies_calls_run_three_times(monkeypatch, capsys):
    """
    install_dependencies() should call run() three times:
      1) python -m pip install --upgrade pip
      2) python -m pip install packaging
      3) python -m pip install -e ROOT
    """
    mod = _load_launcher()

    calls: list[Tuple[Tuple, dict]] = []

    def record(cmd, **kw):
        calls.append(((tuple(cmd),), kw))

    monkeypatch.setattr(mod, "run", record, raising=True)

    mod.install_dependencies()
    out = capsys.readouterr().out
    assert "📦 Installing dependencies" in out
    assert "✅ Environment ready" in out
    assert len(calls) == 3

    c0 = list(calls[0][0][0])
    c1 = list(calls[1][0][0])
    c2 = list(calls[2][0][0])
    assert c0[:3] == [sys.executable, "-m", "pip"]
    assert c0[3:5] == ["install", "--upgrade"]
    assert c1[:3] == [sys.executable, "-m", "pip"] and "packaging" in c1
    assert c2[:3] == [sys.executable, "-m", "pip"] and "-e" in c2
    assert str(mod.ROOT) in c2, "Editable install must reference ROOT"


# ------------------------------------------------------------------
# main(): import paths and error handling
# ------------------------------------------------------------------

def _patch_preloads_ok(mod, monkeypatch):
    """Make both 'saxoflow.cli' and 'saxoflow_agenticai.cli' importable."""
    monkeypatch.setitem(sys.modules, "saxoflow", ModuleType("saxoflow"))
    saxoflow_cli = ModuleType("saxoflow.cli")
    monkeypatch.setitem(sys.modules, "saxoflow.cli", saxoflow_cli)

    monkeypatch.setitem(sys.modules, "saxoflow_agenticai", ModuleType("saxoflow_agenticai"))
    sfa_cli = ModuleType("saxoflow_agenticai.cli")
    monkeypatch.setitem(sys.modules, "saxoflow_agenticai.cli", sfa_cli)


def test_main_happy_uses_new_entrypoint(monkeypatch, capsys):
    """
    When cool_cli.app:main exists, main() should import it and execute it.
    install_dependencies must be called, and no diagnostics printed.
    """
    mod = _load_launcher()

    # Avoid real pip invocations
    monkeypatch.setattr(mod, "install_dependencies", lambda: None, raising=True)
    _patch_preloads_ok(mod, monkeypatch)

    # Provide cool_cli.app:main
    pkg = ModuleType("cool_cli")
    app = ModuleType("cool_cli.app")
    called = {"count": 0}

    def cool_main():
        called["count"] += 1

    app.main = cool_main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cool_cli", pkg)
    monkeypatch.setitem(sys.modules, "cool_cli.app", app)

    mod.main()
    out = capsys.readouterr().out
    assert "🌀 Launching SaxoFlow Cool CLI Shell" in out
    assert called["count"] == 1


def test_main_legacy_fallback_when_new_import_fails(monkeypatch, capsys):
    """
    If importing cool_cli.app fails, launcher should import legacy
    cool_cli.shell:main and call it.
    """
    mod = _load_launcher()
    monkeypatch.setattr(mod, "install_dependencies", lambda: None, raising=True)
    _patch_preloads_ok(mod, monkeypatch)

    # Ensure new path import raises ImportError but legacy is available
    legacy = ModuleType("cool_cli.shell")
    called = {"legacy": 0}

    def legacy_main():
        called["legacy"] += 1

    legacy.main = legacy_main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cool_cli.shell", legacy)

    orig_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "cool_cli.app":
            raise ImportError("boom")
        return orig_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    mod.main()
    assert called["legacy"] == 1
    # No SystemExit, since legacy path succeeds


def test_main_both_entrypoints_fail_prints_diagnostics_and_exits(monkeypatch, capsys):
    """
    If both cool_cli.app and cool_cli.shell fail to import,
    launcher prints diagnostics and exits with code 1.
    """
    mod = _load_launcher()
    monkeypatch.setattr(mod, "install_dependencies", lambda: None, raising=True)
    _patch_preloads_ok(mod, monkeypatch)

    # Force both imports to raise
    orig_import = builtins.__import__

    def failing_import(name, *a, **k):
        if name in ("cool_cli.app", "cool_cli.shell"):
            raise ImportError(f"no {name}")
        return orig_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", failing_import)

    with pytest.raises(SystemExit) as ei:
        mod.main()
    assert ei.value.code == 1

    out = capsys.readouterr().out
    assert "Unable to import the Cool CLI entrypoint" in out
    assert "New path import error:" in out
    assert "Legacy shim import error:" in out
    assert "Common fixes:" in out


def test_main_catches_exception_from_cli(monkeypatch, capsys):
    """
    If cool_cli_main raises, launcher should catch and print an error line.
    """
    mod = _load_launcher()
    monkeypatch.setattr(mod, "install_dependencies", lambda: None, raising=True)
    _patch_preloads_ok(mod, monkeypatch)

    # Provide cool_cli.app.main that raises
    pkg = ModuleType("cool_cli")
    app = ModuleType("cool_cli.app")

    def boom():
        raise RuntimeError("bad")

    app.main = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cool_cli", pkg)
    monkeypatch.setitem(sys.modules, "cool_cli.app", app)

    mod.main()
    out = capsys.readouterr().out
    assert "Error while running CLI: bad" in out


def test_main_warns_when_preload_imports_fail(monkeypatch, capsys):
    """
    If preloading saxoflow CLI modules fails, a warning is printed but
    execution continues.
    """
    mod = _load_launcher()
    monkeypatch.setattr(mod, "install_dependencies", lambda: None, raising=True)

    # Make both preloads fail by removing from sys.modules and letting import raise.
    orig_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name in ("saxoflow.cli", "saxoflow_agenticai.cli"):
            raise ImportError("not present")
        if name == "cool_cli.app":
            # Provide a dummy app.main to allow success after the warning.
            m = ModuleType("cool_cli.app")
            def main():  # noqa: D401
                """no-op"""
                return None
            m.main = main  # type: ignore[attr-defined]
            sys.modules[name] = m
        return orig_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    mod.main()
    out = capsys.readouterr().out
    assert "Warning: could not preload CLIs" in out

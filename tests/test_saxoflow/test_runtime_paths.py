"""Tests for SaxoFlow runtime path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from saxoflow import runtime_paths as sut


def test_resolve_workspace_precedence_cli_env_config_default(monkeypatch, tmp_path):
    """Workspace resolution prefers CLI, env, config, then ~/SaxoFlow."""
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv(sut.CONFIG_HOME_ENV_VAR, str(config_home))

    saved = tmp_path / "saved"
    sut.save_workspace_path(saved)

    monkeypatch.setenv(sut.WORKSPACE_ENV_VAR, str(tmp_path / "env"))
    assert sut.resolve_workspace(tmp_path / "cli") == (tmp_path / "cli").resolve()
    assert sut.resolve_workspace() == (tmp_path / "env").resolve()

    monkeypatch.delenv(sut.WORKSPACE_ENV_VAR)
    assert sut.resolve_workspace() == saved.resolve()

    sut.config_path().unlink()
    assert sut.resolve_workspace() == (home / "SaxoFlow").resolve()


def test_ensure_workspace_creates_layout_and_examples(tmp_path):
    """First-run workspace initialization creates user folders and examples."""
    workspace = sut.ensure_workspace(tmp_path / "SaxoFlow")

    assert (workspace / "projects").is_dir()
    assert (workspace / "examples").is_dir()
    assert (workspace / ".saxoflow").is_dir()
    assert (workspace / "README.md").is_file()
    assert (
        workspace
        / "examples"
        / "getting_started"
        / "source"
        / "rtl"
        / "verilog"
        / "counter.v"
    ).is_file()


def test_save_workspace_preserves_other_config_keys(tmp_path):
    """Saving a workspace updates only the workspace field."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    sut.save_workspace_path(tmp_path / "ws", path=cfg)

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["workspace"] == str(tmp_path / "ws")


def test_bundled_resources_are_discoverable():
    """Pack and template resources are available without a local CWD dependency."""
    assert (sut.bundled_packs_dir() / "ethz_ic_design" / "pack.yaml").exists()
    template = sut.find_template_path("Makefile")
    assert template is not None
    assert template.name == "Makefile"

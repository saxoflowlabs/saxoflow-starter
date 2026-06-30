"""Tests for the Phase 2 PnR tool adapter."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from saxoflow.schemas.tools import ToolRequest
from saxoflow.tools.adapters.pnr import PnrToolAdapter


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _fake_flow(root: Path, variant: str = "default"):
    run_root = root / "pnr/runs" / variant
    run_root.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        root=root,
        manifest=SimpleNamespace(id="sky130hd"),
        library={"id": "sky130_fd_sc_hd"},
        corner={"id": "tt"},
        top="sample_core",
        netlists=[root / "synthesis/out/mapped.v"],
        sdc=root / "constraints/design.sdc",
        variant=variant,
        settings={},
        run_root=run_root,
        config_mk=root / "pnr/generated" / f"{variant}.mk",
    )


def test_pnr_adapter_returns_success_and_artifact_indexes(tmp_path, monkeypatch):
    root = tmp_path / "unit"
    _write(root / "Makefile", "all:\n\t@true\n")
    _write(root / "pnr/logs/default/.gitkeep")

    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.resolve_flow",
        lambda _root, _options: _fake_flow(root),
    )
    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.orfs_command",
        lambda flow, stage: ["make", "-C", "/orfs/flow", stage],
    )

    def fake_run_streaming(command, *, cwd, log_path, show_output=True):
        _write(log_path, "completed\n")
        _write(root / "pnr/runs/default/reports/metrics.json", "{}\n")
        _write(root / "pnr/runs/default/results/final.gds", "GDS\n")
        return 0

    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.run_streaming",
        fake_run_streaming,
    )

    adapter = PnrToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "pnr.run",
            "workspace": str(root),
            "options": {
                "pnr": {
                    "stage": "route",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "success"
    assert run.capability == "pnr.run"
    assert run.tool_name == "orfs"
    assert run.exit_code == 0
    assert run.diagnostics == ()
    assert "Run manifest: pnr/runs/default/saxoflow-run.json" in (run.stdout or "")
    assert "reports artifacts: pnr/reports/default/artifacts.json" in (run.stdout or "")
    assert "results artifacts: pnr/results/default/artifacts.json" in (run.stdout or "")


def test_pnr_adapter_returns_failure_with_log_excerpt(tmp_path, monkeypatch):
    root = tmp_path / "unit"
    _write(root / "Makefile", "all:\n\t@true\n")

    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.resolve_flow",
        lambda _root, _options: _fake_flow(root),
    )
    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.orfs_command",
        lambda flow, stage: ["make", "-C", "/orfs/flow", stage],
    )

    def fake_run_streaming(command, *, cwd, log_path, show_output=True):
        _write(log_path, "ERROR: routing failed\n")
        return 2

    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.run_streaming",
        fake_run_streaming,
    )

    adapter = PnrToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "pnr.run",
            "workspace": str(root),
            "options": {
                "pnr": {
                    "stage": "route",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.capability == "pnr.run"
    assert run.exit_code == 2
    assert len(run.diagnostics) == 1
    assert "routing failed" in run.diagnostics[0].message.lower()


def test_pnr_adapter_dry_run_returns_planned_command_without_execution(tmp_path, monkeypatch):
    root = tmp_path / "unit"
    _write(root / "Makefile", "all:\n\t@true\n")

    def fail_run_streaming(command, *, cwd, log_path, show_output=True):
        raise AssertionError("dry-run should not execute ORFS flow")

    monkeypatch.setattr(
        "saxoflow.tools.adapters.pnr.pnrflow.run_streaming",
        fail_run_streaming,
    )

    adapter = PnrToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "pnr.run",
            "workspace": str(root),
            "dry_run": True,
            "options": {
                "pnr": {
                    "stage": "route",
                    "variant": "default",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "skipped"
    assert run.capability == "pnr.run"
    assert run.tool_name == "orfs"
    assert run.command is not None
    assert "saxoflow pnr route" in run.command
    assert "--variant default" in run.command
    assert run.diagnostics == ()

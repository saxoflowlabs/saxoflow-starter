"""Tests for the non-LLM physical-design tool agent."""

from pathlib import Path

import click

from saxoflow_agenticai.agents import pnr_agent


def test_pnr_agent_rejects_missing_project(tmp_path):
    result = pnr_agent.PnrAgent().run(str(tmp_path / "missing"))
    assert result["status"] == "failed"
    assert result["stage"] == "pnr/run"


def test_pnr_agent_invokes_selected_stage(tmp_path, monkeypatch):
    project = tmp_path / "unit"
    (project / "pnr").mkdir(parents=True)
    (project / "pnr/config.yaml").write_text("platform: test\n")
    (project / "pnr/platform.lock.yaml").write_text("platform: test\n")

    @click.group()
    def fake_pnr():
        pass

    @fake_pnr.command("route")
    @click.option("--variant")
    def route(variant):
        click.echo(f"routed {variant}")

    import saxoflow.pnrflow as flow

    monkeypatch.setattr(flow, "pnr", fake_pnr)
    result = pnr_agent.PnrAgent().run(
        str(project),
        stage="route",
        arguments=("--variant", "experiment"),
    )

    assert result["status"] == "success"
    assert result["stage"] == "pnr/route"
    assert "routed experiment" in result["stdout"]


def test_pnr_agent_returns_stage_specific_failure(tmp_path, monkeypatch):
    project = tmp_path / "unit"
    (project / "pnr").mkdir(parents=True)
    (project / "pnr/config.yaml").write_text("platform: test\n")
    (project / "pnr/platform.lock.yaml").write_text("platform: test\n")

    @click.group()
    def fake_pnr():
        pass

    @fake_pnr.command("cts")
    def cts():
        raise click.ClickException("ERROR: clock tree failed")

    import saxoflow.pnrflow as flow

    monkeypatch.setattr(flow, "pnr", fake_pnr)
    result = pnr_agent.PnrAgent().run(str(project), stage="cts")

    assert result["status"] == "failed"
    assert result["stage"] == "pnr/cts"
    assert "clock tree failed" in result["failure_manifest"]


def test_pnr_agent_requires_locked_platform_for_mutating_stages(tmp_path):
    project = tmp_path / "unit"
    project.mkdir()

    result = pnr_agent.PnrAgent().run(str(project), stage="floorplan")

    assert result["status"] == "failed"
    assert "locked P&R platform" in result["error_message"]


def test_pnr_agent_rejects_configuration_changes_without_confirmation(tmp_path):
    project = tmp_path / "unit"
    (project / "pnr").mkdir(parents=True)
    (project / "pnr/config.yaml").write_text("platform: test\n")
    (project / "pnr/platform.lock.yaml").write_text("platform: test\n")

    result = pnr_agent.PnrAgent().run(
        str(project),
        stage="place",
        arguments=("--platform", "other"),
    )

    assert result["status"] == "failed"
    assert "Explicit user confirmation" in result["error_message"]


def test_pnr_agent_routes_read_only_pdk_command_without_project_lock(
    tmp_path,
    monkeypatch,
):
    project = tmp_path / "workspace"
    project.mkdir()

    @click.group()
    def fake_pdk():
        pass

    @fake_pdk.command("list")
    def list_platforms():
        click.echo("sky130hd")

    import saxoflow.pdk_cli as pdk_cli

    monkeypatch.setattr(pdk_cli, "pdk", fake_pdk)
    result = pnr_agent.PnrAgent().run(str(project), stage="pdk-list")

    assert result["status"] == "success"
    assert result["stage"] == "pnr/pdk-list"
    assert "sky130hd" in result["stdout"]


def test_pnr_agent_requires_confirmation_for_pdk_install(tmp_path):
    project = tmp_path / "workspace"
    project.mkdir()

    result = pnr_agent.PnrAgent().run(
        str(project),
        stage="pdk-install",
        arguments=("sky130hd", "--accept-license"),
    )

    assert result["status"] == "failed"
    assert "license acceptance" in result["error_message"]

"""Focused tests for Phase 4 model CLI surfaces (`saxoflow ai models ...`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def _no_interactive_setup(monkeypatch):
    """Disable interactive key prompts for CLI tests."""
    import saxoflow_agenticai.cli as ai_cli

    monkeypatch.setattr(ai_cli, "_interactive_setup_keys", lambda force=False: None, raising=True)


def test_root_cli_mounts_ai_alias_group():
    """P4.04 surface lock: `saxoflow ai` aliases the agenticai command group."""
    from saxoflow.cli import cli

    assert "ai" in cli.commands
    assert cli.commands["ai"].name == "cli"


def test_root_cli_help_mentions_mode_aware_tui_ai_help():
    """P6.04f: root CLI help advertises explicit mode-aware TUI help surfaces."""
    from saxoflow.cli import cli

    res = CliRunner().invoke(cli, ["--help"])

    assert res.exit_code == 0
    assert "Mode-aware AI help" in res.output
    assert "ask --help" in res.output
    assert "plan --help" in res.output
    assert "research --help" in res.output
    assert "run --help" in res.output


def test_ai_models_list_prints_configured_providers(monkeypatch, _no_interactive_setup):
    """`saxoflow ai models list` prints default provider and configured provider models."""
    from saxoflow.cli import cli
    from saxoflow_agenticai.core.model_profiles import ModelProfileSources, ModelProfiles
    import saxoflow_agenticai.cli as ai_cli

    fake_profiles = ModelProfiles(
        data={
            "default_provider": "openai",
            "providers": {
                "openai": {"model": "gpt-4o"},
                "my_vendor": {"model": "vendor/coder-large"},
            },
        },
        sources=ModelProfileSources(
            default_path=Path("/tmp/default-models.yaml"),
            user_path=Path("/tmp/user-models.yaml"),
            project_path=Path("/tmp/project-models.yaml"),
        ),
    )

    monkeypatch.setattr(ai_cli, "load_model_profiles", lambda project_root=None: fake_profiles, raising=True)

    res = CliRunner().invoke(cli, ["ai", "models", "list"])

    assert res.exit_code == 0
    assert "default_provider: openai" in res.output
    assert "- openai: model=gpt-4o" in res.output
    assert "- my_vendor: model=vendor/coder-large" in res.output


def test_ai_models_test_handles_fake_model(monkeypatch, _no_interactive_setup):
    """Validation gate: `saxoflow ai models test` succeeds with an explicit fake model."""
    from saxoflow.cli import cli
    import saxoflow_agenticai.cli as ai_cli

    monkeypatch.setattr(ai_cli.ModelSelector, "get_model", staticmethod(lambda **kwargs: object()), raising=True)

    res = CliRunner().invoke(
        cli,
        ["ai", "models", "test", "--provider", "openai", "--model", "fake-model"],
    )

    assert res.exit_code == 0
    assert "Model test SUCCESS: provider=openai, model=fake-model" in res.output


def test_ai_models_test_invalid_provider_returns_clean_error(_no_interactive_setup):
    """Invalid provider should return Click error text without an unhandled traceback."""
    from saxoflow.cli import cli

    res = CliRunner().invoke(
        cli,
        ["ai", "models", "test", "--provider", "notreal", "--model", "x"],
    )

    assert res.exit_code != 0
    assert "Error: Model test FAILED:" in res.output
    assert "Unsupported provider: notreal" in res.output
    assert "Traceback" not in res.output


def test_compact_ai_options_parse_agent_context_tools():
    """P4.09: compact AI options parse into normalized schema metadata."""
    from saxoflow.cli import parse_compact_ai_options

    parsed = parse_compact_ai_options(
        agent=" my_ppa_agent ",
        context=("source/rtl", "docs/goals.md"),
        tools="file.read, artifact.read, report.read, eda.run",
    )

    assert parsed.agent_name == "my_ppa_agent"
    assert parsed.context_paths == ("source/rtl", "docs/goals.md")
    assert parsed.requested_tools == ("file.read", "artifact.read", "report.read", "eda.run")
    assert parsed.to_metadata() == {
        "requested_agent": "my_ppa_agent",
        "requested_context_paths": ["source/rtl", "docs/goals.md"],
        "requested_capabilities": ["file.read", "artifact.read", "report.read", "eda.run"],
    }


def test_compact_ai_options_parse_dedupes_and_omits_empty_inputs():
    """P4.09 parse contract keeps first value order and drops empty duplicates."""
    from saxoflow.cli import parse_compact_ai_options

    parsed = parse_compact_ai_options(
        agent="   ",
        context=("docs/spec.md", "", "docs/spec.md", "source/rtl"),
        tools=" file.read, ,file.read, eda.run , ",
    )

    assert parsed.agent_name is None
    assert parsed.context_paths == ("docs/spec.md", "source/rtl")
    assert parsed.requested_tools == ("file.read", "eda.run")
    assert parsed.to_metadata() == {
        "requested_context_paths": ["docs/spec.md", "source/rtl"],
        "requested_capabilities": ["file.read", "eda.run"],
    }

"""Tests for model profile loading precedence and validation (Phase 4 P4.02)."""

from __future__ import annotations

import textwrap

import pytest


def _write_yaml(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def test_load_model_profiles_applies_project_user_default_precedence(tmp_path):
    from saxoflow_agenticai.core.model_profiles import load_model_profiles

    defaults = tmp_path / "defaults.yaml"
    user_dir = tmp_path / "user"
    project_root = tmp_path / "project"

    _write_yaml(
        defaults,
        """
        default_provider: nvidia
        providers:
          openai:
            model: gpt-4o
            temperature: 0.3
          nvidia:
            model: glm-5.1
            max_tokens: 4096
        """,
    )
    _write_yaml(
        user_dir / "saxoflow_models.yaml",
        """
        default_provider: openai
        providers:
          openai:
            temperature: 0.2
          groq:
            model: mixtral
        """,
    )
    _write_yaml(
        project_root / ".saxoflow" / "saxoflow_models.yaml",
        """
        providers:
          openai:
            model: gpt-5-nano
        agent_models:
          RTLGenAgent:
            provider: openai
            model: gpt-5-nano
        """,
    )

    loaded = load_model_profiles(
        project_root=project_root,
        user_dir=user_dir,
        default_path=defaults,
    )

    payload = loaded.to_dict()
    assert payload["default_provider"] == "openai"
    assert payload["providers"]["openai"]["temperature"] == 0.2
    assert payload["providers"]["openai"]["model"] == "gpt-5-nano"
    assert payload["providers"]["nvidia"]["model"] == "glm-5.1"
    assert payload["providers"]["groq"]["model"] == "mixtral"
    assert payload["agent_models"]["RTLGenAgent"]["model"] == "gpt-5-nano"


def test_load_model_profiles_uses_project_root_saxoflow_models_yaml_when_present(tmp_path):
    from saxoflow_agenticai.core.model_profiles import load_model_profiles

    defaults = tmp_path / "defaults.yaml"
    user_dir = tmp_path / "user"
    project_root = tmp_path / "project"

    _write_yaml(defaults, "default_provider: nvidia")
    _write_yaml(project_root / "saxoflow_models.yaml", "default_provider: openai")

    loaded = load_model_profiles(
        project_root=project_root,
        user_dir=user_dir,
        default_path=defaults,
    )

    assert loaded.to_dict()["default_provider"] == "openai"
    assert loaded.sources.project_path == project_root / "saxoflow_models.yaml"
    assert loaded.sources.user_path is None


def test_load_model_profiles_prefers_dot_saxoflow_project_profile_over_root_file(tmp_path):
    from saxoflow_agenticai.core.model_profiles import load_model_profiles

    defaults = tmp_path / "defaults.yaml"
    project_root = tmp_path / "project"

    _write_yaml(defaults, "default_provider: nvidia")
    _write_yaml(project_root / "saxoflow_models.yaml", "default_provider: openai")
    _write_yaml(project_root / ".saxoflow" / "saxoflow_models.yaml", "default_provider: groq")

    loaded = load_model_profiles(project_root=project_root, default_path=defaults)

    assert loaded.to_dict()["default_provider"] == "groq"
    assert loaded.sources.project_path == project_root / ".saxoflow" / "saxoflow_models.yaml"


def test_load_model_profiles_rejects_non_mapping_yaml(tmp_path):
    from saxoflow_agenticai.core.model_profiles import ModelProfileLoadError, load_model_profiles

    defaults = tmp_path / "defaults.yaml"
    _write_yaml(defaults, "- item")

    with pytest.raises(ModelProfileLoadError):
        load_model_profiles(default_path=defaults)

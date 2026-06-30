"""Focused tests for declarative custom agent loader contracts (P4.07)."""

from __future__ import annotations

import textwrap

import pytest


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_custom_agent_loader_validates_declarative_agent_file(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import load_custom_agent_file

    agent_file = tmp_path / ".saxoflow" / "agents" / "my_ppa_agent.yaml"
    _write(
        agent_file,
        """
        name: my_ppa_agent
        description: Explore area and timing tradeoffs for verified RTL.
        model_profile: researcher_coder
        graph_template: research_variant_loop
        prompt:
          system: prompts/my_ppa_agent_system.md
          task: prompts/my_ppa_agent_task.md
        input_schema: schemas/ppa_request.json
        output_schema: schemas/ppa_report.json
        tools:
          allow:
            - context.read
            - file.read
            - artifact.read
            - report.read
            - eda.run
          deny:
            - file.delete
        approvals:
          file.write: required
          eda.run: required
          long_run: optional
        """,
    )

    loaded = load_custom_agent_file(agent_file)

    assert loaded.name == "my_ppa_agent"
    assert loaded.model_profile == "researcher_coder"
    assert loaded.graph_template == "research_variant_loop"
    assert loaded.prompt_system == "prompts/my_ppa_agent_system.md"
    assert loaded.prompt_task == "prompts/my_ppa_agent_task.md"
    assert loaded.tools_allow == (
        "context.read",
        "file.read",
        "artifact.read",
        "report.read",
        "eda.run",
    )
    assert loaded.approvals["file.write"] == "required"


def test_custom_agent_loader_rejects_missing_required_prompt_fields(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import CustomAgentLoadError, load_custom_agent_file

    agent_file = tmp_path / ".saxoflow" / "agents" / "broken_agent.yaml"
    _write(
        agent_file,
        """
        name: broken_agent
        model_profile: researcher_coder
        graph_template: research_variant_loop
        prompt:
          system: prompts/system.md
        """,
    )

    with pytest.raises(CustomAgentLoadError):
        load_custom_agent_file(agent_file)


def test_custom_agent_loader_rejects_invalid_approval_state(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import CustomAgentLoadError, load_custom_agent_file

    agent_file = tmp_path / ".saxoflow" / "agents" / "bad_approval.yaml"
    _write(
        agent_file,
        """
        name: bad_approval
        model_profile: researcher_coder
        graph_template: research_variant_loop
        prompt:
          system: prompts/system.md
          task: prompts/task.md
        approvals:
          file.write: always
        """,
    )

    with pytest.raises(CustomAgentLoadError):
        load_custom_agent_file(agent_file)


def test_custom_agent_loader_to_dict_and_optional_fields(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import load_custom_agent_file

    agent_file = tmp_path / ".saxoflow" / "agents" / "minimal_agent.yaml"
    _write(
        agent_file,
        """
        name: minimal_agent
        model_profile: base_profile
        graph_template: base_graph
        prompt:
          system: prompts/system.md
          task: prompts/task.md
        tools:
          allow: []
          deny: []
        approvals: {}
        """,
    )

    loaded = load_custom_agent_file(agent_file)
    payload = loaded.to_dict()

    assert payload["name"] == "minimal_agent"
    assert payload["description"] is None
    assert payload["input_schema"] is None
    assert payload["output_schema"] is None
    assert payload["tools"]["allow"] == []
    assert payload["tools"]["deny"] == []


def test_custom_agent_loader_missing_file_and_non_mapping_yaml(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import CustomAgentLoadError, load_custom_agent_file

    with pytest.raises(CustomAgentLoadError):
        load_custom_agent_file(tmp_path / "missing.yaml")

    bad_file = tmp_path / ".saxoflow" / "agents" / "bad_top_level.yaml"
    _write(
        bad_file,
        """
        - not
        - a
        - mapping
        """,
    )

    with pytest.raises(CustomAgentLoadError):
        load_custom_agent_file(bad_file)


def test_custom_agent_loader_resolve_by_name_prefers_workspace_over_user(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import resolve_custom_agent_definition

    project_root = tmp_path / "project"
    user_root = tmp_path / "user_config"

    workspace_agent = project_root / ".saxoflow" / "agents" / "my_ppa_agent.yaml"
    user_agent = user_root / "agents" / "my_ppa_agent.yaml"

    _write(
        workspace_agent,
        """
        name: my_ppa_agent
        model_profile: workspace_profile
        graph_template: research_variant_loop
        prompt:
          system: prompts/workspace_system.md
          task: prompts/workspace_task.md
        """,
    )
    _write(
        user_agent,
        """
        name: my_ppa_agent
        model_profile: user_profile
        graph_template: research_variant_loop
        prompt:
          system: prompts/user_system.md
          task: prompts/user_task.md
        """,
    )

    loaded = resolve_custom_agent_definition(
        "my_ppa_agent",
        project_root=project_root,
        user_dir=user_root,
    )

    assert loaded.model_profile == "workspace_profile"
    assert loaded.source_path is not None
    assert loaded.source_path == workspace_agent.resolve()


def test_custom_agent_loader_resolve_by_name_falls_back_to_user(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import resolve_custom_agent_definition

    project_root = tmp_path / "project"
    user_root = tmp_path / "user_config"
    user_agent = user_root / "agents" / "user_only_agent.yaml"

    _write(
        user_agent,
        """
        name: user_only_agent
        model_profile: user_profile
        graph_template: research_variant_loop
        prompt:
          system: prompts/user_system.md
          task: prompts/user_task.md
        """,
    )

    loaded = resolve_custom_agent_definition(
        "user_only_agent",
        project_root=project_root,
        user_dir=user_root,
    )

    assert loaded.model_profile == "user_profile"
    assert loaded.source_path is not None
    assert loaded.source_path == user_agent.resolve()


def test_custom_agent_loader_resolve_by_name_rejects_invalid_name_and_missing_agent(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import (
        CustomAgentLoadError,
        resolve_custom_agent_definition,
    )

    with pytest.raises(CustomAgentLoadError):
        resolve_custom_agent_definition("bad/name", project_root=tmp_path, user_dir=tmp_path / "user")

    with pytest.raises(CustomAgentLoadError):
        resolve_custom_agent_definition("does_not_exist", project_root=tmp_path, user_dir=tmp_path / "user")


def test_custom_agent_loader_rejects_unknown_capability_names(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import CustomAgentLoadError, load_custom_agent_file

    agent_file = tmp_path / ".saxoflow" / "agents" / "unknown_capability_agent.yaml"
    _write(
        agent_file,
        """
        name: unknown_capability_agent
        model_profile: researcher_coder
        graph_template: research_variant_loop
        prompt:
          system: prompts/system.md
          task: prompts/task.md
        tools:
          allow:
            - file.read
            - command.run
          deny:
            - file.delete
        approvals:
          command.run: required
        """,
    )

    with pytest.raises(CustomAgentLoadError):
        load_custom_agent_file(agent_file)


def test_custom_agent_loader_rejects_non_list_capability_container(tmp_path):
    from saxoflow_agenticai.core.custom_agent_loader import CustomAgentLoadError, load_custom_agent_file

    agent_file = tmp_path / ".saxoflow" / "agents" / "bad_caps_container.yaml"
    _write(
        agent_file,
        """
        name: bad_caps_container
        model_profile: researcher_coder
        graph_template: research_variant_loop
        prompt:
          system: prompts/system.md
          task: prompts/task.md
        tools:
          allow: file.read
          deny: []
        approvals: {}
        """,
    )

    with pytest.raises(CustomAgentLoadError):
        load_custom_agent_file(agent_file)

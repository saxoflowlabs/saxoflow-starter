"""Focused tests for the package prompt registry contract (P4.13)."""

from __future__ import annotations

import textwrap

import pytest


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_prompt_registry_builtins_validate_and_expose_known_prompt_bundles():
    from saxoflow_agenticai.core.prompt_registry import PromptRegistry

    registry = PromptRegistry.builtins()

    expected = {
        "rtlgen",
        "rtlreview",
        "tbgen",
        "tbreview",
        "fpropgen",
        "fpropreview",
        "report",
        "debug",
        "tutor",
    }

    assert expected.issubset(set(registry.entries.keys()))
    rtlgen = registry.get("rtlgen")
    assert rtlgen.role == "generator"
    assert "rtlgen_prompt.txt" in rtlgen.templates
    assert registry.to_dict()["prompts"]["tutor"]["templates"] == [
        "tutor_prompt.txt",
        "tutor_agent_result.txt",
    ]


def test_prompt_registry_rejects_missing_registry_and_missing_template(tmp_path):
    from saxoflow_agenticai.core.prompt_registry import PromptRegistry, PromptRegistryError

    with pytest.raises(PromptRegistryError):
        PromptRegistry.load(tmp_path / "missing.yaml", prompt_dir=tmp_path)

    registry_file = tmp_path / "registry.yaml"
    prompt_dir = tmp_path / "prompts"
    _write(
        registry_file,
        """
        version: 1
        prompts:
          broken:
            role: generator
            templates:
              - missing_prompt.txt
        """,
    )
    prompt_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(PromptRegistryError):
        PromptRegistry.load(registry_file, prompt_dir=prompt_dir)


def test_prompt_registry_rejects_non_mapping_and_unknown_bundle(tmp_path):
    from saxoflow_agenticai.core.prompt_registry import PromptRegistry, PromptRegistryError

    registry_file = tmp_path / "registry.yaml"
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    for name in [
        "rtlgen_prompt.txt",
        "rtlgen_improve_prompt.txt",
        "rtlgen_improve_prompt_v2.txt",
    ]:
        (prompt_dir / name).write_text("stub\n", encoding="utf-8")

    _write(registry_file, "- not\n- a\n- mapping\n")
    with pytest.raises(PromptRegistryError):
        PromptRegistry.load(registry_file, prompt_dir=prompt_dir)

    _write(
        registry_file,
        """
        version: 1
        prompts:
          rtlgen:
            role: generator
            templates:
              - rtlgen_prompt.txt
              - rtlgen_improve_prompt.txt
              - rtlgen_improve_prompt_v2.txt
        """,
    )
    registry = PromptRegistry.load(registry_file, prompt_dir=prompt_dir)

    with pytest.raises(PromptRegistryError):
        registry.get("notreal")

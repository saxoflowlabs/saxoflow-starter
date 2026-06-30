"""Tests for the deterministic prompt context builder (P4.14)."""

from __future__ import annotations

import pytest


def test_prompt_context_builder_normalizes_sources_and_budget_order_deterministically():
    from saxoflow_agenticai.core.prompt_context import PromptContextBuilder

    builder = PromptContextBuilder(default_budget=1024)

    first = builder.build(
        sources=[
            {"path": "docs/spec.md", "kind": "file", "label": "Spec"},
            {"path": "/workspace/source/rtl/top.sv", "kind": "file"},
            "source/rtl/top.sv",
        ],
        notes="  keep concise  ",
    )
    second = builder.build(
        sources=[
            "source/rtl/top.sv",
            {"path": "/workspace/source/rtl/top.sv", "kind": "file"},
            {"path": "docs/spec.md", "kind": "file", "label": "Spec"},
        ],
        notes="keep concise",
    )

    assert first == second
    assert first.context_budget == 1024
    assert first.source_count == 3
    assert first.source_paths == (
        "/workspace/source/rtl/top.sv",
        "docs/spec.md",
        "source/rtl/top.sv",
    )
    assert first.notes == "keep concise"
    assert first.to_dict()["source_paths"] == [
        "/workspace/source/rtl/top.sv",
        "docs/spec.md",
        "source/rtl/top.sv",
    ]


def test_prompt_context_builder_accepts_context_refs_and_rejects_invalid_budget():
    from saxoflow.schemas.context import ContextBundle, ContextRef
    from saxoflow_agenticai.core.prompt_context import PromptContextBuilder, PromptContextError

    builder = PromptContextBuilder()
    context_ref = ContextRef(path="notes/todo.md", kind="file", label="Todo")
    built = builder.build(sources=[context_ref], context_budget=4096)

    assert built.sources[0].path == "notes/todo.md"
    assert built.sources[0].label == "Todo"
    assert built.source_paths == ("notes/todo.md",)

    bundle = ContextBundle.from_mapping(
        {
            "workspace_root": "/workspace/demo",
            "notes": "  keep the prompt grounded  ",
            "references": [
                {"path": "docs/spec.md", "kind": "file", "label": "Spec"},
                {"path": "/workspace/source/rtl/top.sv", "kind": "file"},
                {"path": "source/rtl/top.sv", "kind": "file"},
            ],
        }
    )
    bundled = builder.build_from_context_bundle(bundle, context_budget=512)

    assert bundled.workspace_root == "/workspace/demo"
    assert bundled.notes == "keep the prompt grounded"
    assert bundled.context_budget == 512
    assert bundled.source_count == 3
    assert bundled.source_paths == (
        "/workspace/source/rtl/top.sv",
        "docs/spec.md",
        "source/rtl/top.sv",
    )
    assert bundled.to_dict()["workspace_root"] == "/workspace/demo"

    with pytest.raises(PromptContextError):
        builder.build(context_budget=0)


def test_prompt_context_builder_rejects_invalid_source_shape():
    from saxoflow_agenticai.core.prompt_context import PromptContextBuilder, PromptContextError

    builder = PromptContextBuilder()

    with pytest.raises(PromptContextError):
        builder.build(sources=[object()])

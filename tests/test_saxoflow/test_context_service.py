"""Tests for SaxoFlow context schemas."""

from __future__ import annotations


def test_context_ref_validates_minimal_mapping():
    from saxoflow.schemas.context import ContextRef

    ref = ContextRef.from_mapping({"path": "docs/spec.md"})

    assert ref.path == "docs/spec.md"
    assert ref.kind is None
    assert ref.label is None
    assert ref.resolved_path is None
    assert ref.source is None
    assert ref.to_dict() == {"path": "docs/spec.md"}


def test_context_bundle_validates_reference_list():
    from saxoflow.schemas.context import ContextBundle

    bundle = ContextBundle.from_mapping(
        {
            "workspace_root": "/workspace/demo",
            "references": [
                {"path": "docs/spec.md", "kind": "file", "label": "spec"},
                {"path": "source/rtl", "kind": "directory", "source": "workspace"},
            ],
            "notes": "grounding for the ask command",
        }
    )

    assert bundle.workspace_root == "/workspace/demo"
    assert len(bundle.references) == 2
    assert bundle.references[0].path == "docs/spec.md"
    assert bundle.references[1].kind == "directory"
    assert bundle.notes == "grounding for the ask command"
    assert bundle.to_dict() == {
        "workspace_root": "/workspace/demo",
        "references": [
            {"path": "docs/spec.md", "kind": "file", "label": "spec"},
            {"path": "source/rtl", "kind": "directory", "source": "workspace"},
        ],
        "notes": "grounding for the ask command",
    }


def test_context_bundle_accepts_contexts_alias():
    from saxoflow.schemas.context import ContextBundle

    bundle = ContextBundle.from_mapping({"contexts": [{"path": "reports/timing.md"}]})

    assert len(bundle.references) == 1
    assert bundle.references[0].path == "reports/timing.md"


def test_context_ref_rejects_missing_path():
    from saxoflow.schemas.context import ContextRef, ContextSchemaError

    try:
        ContextRef.from_mapping({"kind": "file"})
    except ContextSchemaError as exc:
        assert "context.path" in str(exc)
    else:
        raise AssertionError("Missing context path was accepted.")


def test_context_service_resolves_file_and_directory_inside_workspace(tmp_path):
    from saxoflow.schemas.context import ContextBundle
    from saxoflow.services.context_service import ContextService

    workspace = tmp_path / "workspace"
    docs = workspace / "docs"
    source = workspace / "source" / "rtl"
    docs.mkdir(parents=True)
    source.mkdir(parents=True)
    spec = docs / "spec.md"
    spec.write_text("spec", encoding="utf-8")

    service = ContextService.from_workspace(workspace)
    bundle = ContextBundle.from_mapping(
        {
            "references": [
                {"path": "docs/spec.md", "kind": "file"},
                {"path": "source/rtl", "kind": "directory"},
            ]
        }
    )

    resolved = service.resolve_bundle(bundle)

    assert resolved.workspace_root == str(workspace.resolve())
    assert resolved.references[0].resolved_path == str(spec.resolve())
    assert resolved.references[1].resolved_path == str(source.resolve())
    assert resolved.references[0].path == "docs/spec.md"
    assert resolved.references[1].kind == "directory"


def test_context_service_rejects_workspace_escape(tmp_path):
    from saxoflow.schemas.context import ContextRef
    from saxoflow.services.context_service import ContextService, ContextServiceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")

    service = ContextService.from_workspace(workspace)

    try:
        service.resolve_ref(ContextRef(path="../outside.md"))
    except ContextServiceError as exc:
        assert "escapes the workspace root" in str(exc)
    else:
        raise AssertionError("Workspace escape was accepted.")


def test_context_service_rejects_missing_context(tmp_path):
    from saxoflow.schemas.context import ContextRef
    from saxoflow.services.context_service import ContextService, ContextServiceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    service = ContextService.from_workspace(workspace)

    try:
        service.resolve_ref(ContextRef(path="docs/missing.md"))
    except ContextServiceError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("Missing context path was accepted.")


def test_context_service_indexes_directory_with_limits(tmp_path):
    from saxoflow.services.context_service import ContextService

    workspace = tmp_path / "workspace"
    docs = workspace / "docs"
    nested = docs / "nested"
    ignored = docs / ".git"
    docs.mkdir(parents=True)
    nested.mkdir(parents=True)
    ignored.mkdir(parents=True)

    (docs / "a.md").write_text("A", encoding="utf-8")
    (docs / "b.md").write_text("B", encoding="utf-8")
    (nested / "c.md").write_text("C", encoding="utf-8")
    (nested / "deep.txt").write_text("D", encoding="utf-8")
    (ignored / "ignored.md").write_text("ignore", encoding="utf-8")
    (docs / "large.txt").write_text("x" * 70000, encoding="utf-8")
    (docs / "binary.bin").write_bytes(b"\x00\x01binary")

    service = ContextService.from_workspace(workspace)
    refs = service.index_directory("docs", max_files=3, max_depth=1, max_bytes=1024)

    assert [ref.path for ref in refs] == ["docs/a.md", "docs/b.md", "docs/nested/c.md"]
    assert [ref.source for ref in refs] == ["directory-index", "directory-index", "directory-index"]
    assert [ref.kind for ref in refs] == ["file", "file", "file"]
    assert all("ignored" not in ref.path for ref in refs)
    assert all(ref.path != "docs/binary.bin" for ref in refs)
    assert all(ref.path != "docs/large.txt" for ref in refs)


def test_context_service_indexes_nested_files_deterministically(tmp_path):
    from saxoflow.services.context_service import ContextService

    workspace = tmp_path / "workspace"
    source = workspace / "source"
    deeper = source / "rtl" / "sub"
    deeper.mkdir(parents=True)
    (source / "b.sv").write_text("B", encoding="utf-8")
    (source / "a.sv").write_text("A", encoding="utf-8")
    (source / "rtl" / "c.sv").write_text("C", encoding="utf-8")
    (deeper / "d.sv").write_text("D", encoding="utf-8")

    service = ContextService.from_workspace(workspace)
    shallow = service.index_directory("source", max_files=10, max_depth=0)
    deep = service.index_directory("source", max_files=10, max_depth=2)

    assert [ref.path for ref in shallow] == ["source/a.sv", "source/b.sv"]
    assert [ref.path for ref in deep] == ["source/a.sv", "source/b.sv", "source/rtl/c.sv", "source/rtl/sub/d.sv"]
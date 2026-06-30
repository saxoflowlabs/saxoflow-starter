"""Tests for artifact reference schema."""

from __future__ import annotations


def test_artifact_ref_validates_minimal_mapping():
    from saxoflow.schemas.artifacts import ArtifactRef

    ref = ArtifactRef.from_mapping(
        {
            "artifact_id": "rtl-netlist",
            "path": "reports/rtl-netlist.v",
            "sha256": "a" * 64,
        }
    )

    assert ref.artifact_id == "rtl-netlist"
    assert ref.path == "reports/rtl-netlist.v"
    assert ref.sha256 == "a" * 64
    assert ref.kind is None
    assert ref.label is None
    assert ref.to_dict() == {
        "artifact_id": "rtl-netlist",
        "path": "reports/rtl-netlist.v",
        "sha256": "a" * 64,
    }


def test_artifact_ref_from_path_hashes_file(tmp_path):
    from saxoflow.schemas.artifacts import ArtifactRef

    artifact = tmp_path / "report.txt"
    artifact.write_text("hello artifact\n", encoding="utf-8")

    ref = ArtifactRef.from_path(artifact, artifact_id="report", kind="report", label="summary")

    assert ref.artifact_id == "report"
    assert ref.path == str(artifact)
    assert ref.kind == "report"
    assert ref.label == "summary"
    assert ref.sha256 == "51bc0fc1f19104fa6e89ce50be9aa1f57c3346c1ca51ab49f5f00e14ce8f8076"
    assert ref.to_dict()["sha256"] == ref.sha256


def test_artifact_ref_rejects_invalid_mapping():
    from saxoflow.schemas.artifacts import ArtifactSchemaError, ArtifactRef

    try:
        ArtifactRef.from_mapping({"artifact_id": "", "path": "x", "sha256": "y"})
    except ArtifactSchemaError as exc:
        assert "artifact.artifact_id" in str(exc)
    else:
        raise AssertionError("Invalid artifact reference was accepted.")


def test_artifact_registry_add_query_and_filter(tmp_path):
    from saxoflow.schemas.artifacts import ArtifactRef
    from saxoflow.services.artifact_service import ArtifactRegistry

    registry = ArtifactRegistry(storage_path=tmp_path / "artifacts.json")
    report = ArtifactRef(
        artifact_id="report",
        path="reports/report.txt",
        sha256="b" * 64,
        kind="report",
        label="summary",
    )
    netlist = ArtifactRef(
        artifact_id="netlist",
        path="build/netlist.v",
        sha256="c" * 64,
        kind="build",
    )

    registry.add(report)
    registry.add(netlist)

    assert registry.contains("report")
    assert registry.get("report") == report
    assert registry.get("missing") is None
    assert registry.list() == [report, netlist]
    assert registry.list(kind="report") == [report]
    assert registry.to_dict() == {
        "artifacts": {
            "report": report.to_dict(),
            "netlist": netlist.to_dict(),
        }
    }


def test_artifact_registry_persists_json(tmp_path):
    from saxoflow.schemas.artifacts import ArtifactRef
    from saxoflow.services.artifact_service import ArtifactRegistry

    storage = tmp_path / "artifacts.json"
    registry = ArtifactRegistry(storage_path=storage)
    registry.add(
        ArtifactRef(
            artifact_id="report",
            path="reports/report.txt",
            sha256="b" * 64,
            kind="report",
        )
    )

    saved = registry.save()
    assert saved == storage

    reloaded = ArtifactRegistry.from_path(storage)
    assert reloaded.get("report") == registry.get("report")


def test_artifact_registry_rejects_duplicate_ids():
    from saxoflow.schemas.artifacts import ArtifactRef
    from saxoflow.services.artifact_service import ArtifactRegistry, ArtifactRegistryError

    registry = ArtifactRegistry()
    artifact = ArtifactRef(
        artifact_id="report",
        path="reports/report.txt",
        sha256="b" * 64,
    )

    registry.add(artifact)

    try:
        registry.add(artifact)
    except ArtifactRegistryError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Duplicate artifact id was accepted.")

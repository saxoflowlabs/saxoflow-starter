"""Tests for SaxoFlow source manifest providers."""

from __future__ import annotations


def test_explicit_source_manifest_resolves_file_list(tmp_path):
    from saxoflow.source_manifests.base import ExplicitSourceManifest

    manifest_path = tmp_path / "sources.txt"
    manifest_path.write_text(
        "\n".join(
            [
                "# explicit source list",
                "source/rtl/top.sv",
                "source/rtl/alu.sv",
                "",
                "source/tb/top_tb.sv",
            ]
        ),
        encoding="utf-8",
    )

    manifest = ExplicitSourceManifest.from_path(manifest_path)

    assert manifest.files == (
        "source/rtl/top.sv",
        "source/rtl/alu.sv",
        "source/tb/top_tb.sv",
    )
    assert manifest.source_path == str(manifest_path)
    assert manifest.to_dict() == {
        "files": ["source/rtl/top.sv", "source/rtl/alu.sv", "source/tb/top_tb.sv"],
        "source_path": str(manifest_path),
    }


def test_explicit_source_manifest_discovers_from_root(tmp_path):
    from saxoflow.source_manifests.base import ExplicitSourceManifest

    manifest_path = tmp_path / "sources.list"
    manifest_path.write_text("source/rtl/top.sv\n", encoding="utf-8")

    manifest = ExplicitSourceManifest.from_path(tmp_path)

    assert manifest.files == ("source/rtl/top.sv",)
    assert manifest.source_path == str(manifest_path)


def test_explicit_source_manifest_rejects_missing_manifest(tmp_path):
    from saxoflow.source_manifests.base import ExplicitSourceManifestError, ExplicitSourceManifest

    try:
        ExplicitSourceManifest.from_path(tmp_path)
    except ExplicitSourceManifestError as exc:
        assert "No explicit source manifest found" in str(exc)
    else:
        raise AssertionError("Missing explicit source manifest was accepted.")

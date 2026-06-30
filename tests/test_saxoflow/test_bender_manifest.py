"""Tests for Bender manifest detection."""

from __future__ import annotations


def test_discover_bender_manifest_path_finds_bender_yml(tmp_path):
    from saxoflow.source_manifests.bender import discover_bender_manifest_path

    manifest = tmp_path / "Bender.yml"
    manifest.write_text("package: {}\n", encoding="utf-8")

    discovered = discover_bender_manifest_path(tmp_path)

    assert discovered == manifest


def test_discover_bender_manifest_path_returns_none_without_manifest(tmp_path):
    from saxoflow.source_manifests.bender import discover_bender_manifest_path

    assert discover_bender_manifest_path(tmp_path) is None


def test_load_bender_manifest_resolves_targets(tmp_path):
    from saxoflow.source_manifests.bender import load_bender_manifest

    manifest_path = tmp_path / "Bender.yml"
    manifest_path.write_text(
        "\n".join(
            [
                "package:",
                "  name: traffic_controller",
                "sources:",
                "  - files:",
                "      - source/rtl/verilog/*.v",
                "      - source/rtl/systemverilog/*.sv",
                "    include_dirs:",
                "      - source/rtl/include",
                "    target: [rtl]",
                "  - files:",
                "      - source/tb/systemverilog/*.sv",
                "    target:",
                "      - sim",
                "  - files:",
                "      - synthesis/src/*.sv",
                "    target: synth",
            ]
        ),
        encoding="utf-8",
    )

    manifest = load_bender_manifest(tmp_path)

    assert manifest.package == {"name": "traffic_controller"}
    assert manifest.targets() == ("rtl", "sim", "synth")
    assert manifest.source_groups_for_target("rtl")[0].files == (
        "source/rtl/verilog/*.v",
        "source/rtl/systemverilog/*.sv",
    )
    assert manifest.source_groups_for_target("sim")[0].files == ("source/tb/systemverilog/*.sv",)
    assert manifest.files_for_target("synth") == ("synthesis/src/*.sv",)
    assert manifest.files_for_target("rtl") == (
        "source/rtl/verilog/*.v",
        "source/rtl/systemverilog/*.sv",
    )


def test_load_bender_manifest_rejects_missing_manifest(tmp_path):
    from saxoflow.source_manifests.bender import BenderManifestError, load_bender_manifest

    try:
        load_bender_manifest(tmp_path)
    except BenderManifestError as exc:
        assert "No Bender manifest found" in str(exc)
    else:
        raise AssertionError("Missing Bender manifest was accepted.")
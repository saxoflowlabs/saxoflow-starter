"""Tests for the SaxoFlow project manifest schema."""

from __future__ import annotations


def test_project_manifest_validates_minimal_manifest():
    from saxoflow.project_manifest import MANIFEST_SCHEMA_VERSION, ProjectManifest

    manifest = ProjectManifest.from_mapping(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "project": {"name": "demo"},
        }
    )

    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.project.name == "demo"
    assert manifest.project.top_module is None
    assert manifest.source_manifest.provider == "saxoflow"
    assert manifest.source_manifest.path is None
    assert manifest.source_manifest.targets == {}
    assert manifest.constraints == ()
    assert manifest.to_dict()["project"]["name"] == "demo"


def test_project_manifest_discovers_manifest_from_root(tmp_path):
    from saxoflow.project_manifest import ProjectManifest

    manifest_path = tmp_path / "saxoflow_project.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project:",
                "  name: traffic_controller",
                "  top_module: traffic_controller",
                "  language: systemverilog",
                "source_manifest:",
                "  provider: bender",
                "  path: Bender.yml",
                "  targets:",
                "    rtl: rtl",
                "    sim: sim",
            ]
        ),
        encoding="utf-8",
    )

    discovered = ProjectManifest.discover_from_root(tmp_path)

    assert discovered is not None
    assert discovered.project.name == "traffic_controller"
    assert discovered.project.top_module == "traffic_controller"
    assert discovered.project.language == "systemverilog"
    assert discovered.source_manifest.provider == "bender"
    assert discovered.source_manifest.path == "Bender.yml"
    assert discovered.source_manifest.targets == {"rtl": "rtl", "sim": "sim"}
    assert discovered.to_dict()["project"]["name"] == "traffic_controller"


def test_project_manifest_discovery_returns_none_without_manifest(tmp_path):
    from saxoflow.project_manifest import ProjectManifest

    assert ProjectManifest.discover_from_root(tmp_path) is None


def test_project_manifest_rejects_missing_project_name():
    from saxoflow.project_manifest import MANIFEST_SCHEMA_VERSION, ManifestError, ProjectManifest

    try:
        ProjectManifest.from_mapping(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "project": {},
            }
        )
    except ManifestError as exc:
        assert "project.name" in str(exc)
    else:
        raise AssertionError("Manifest without project.name was accepted.")


def test_project_manifest_from_path_supports_manifest_file_and_root(tmp_path):
    from saxoflow.project_manifest import MANIFEST_SCHEMA_VERSION, ProjectManifest

    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                f"schema_version: {MANIFEST_SCHEMA_VERSION}",
                "project:",
                "  name: direct-load",
            ]
        ),
        encoding="utf-8",
    )

    from_file = ProjectManifest.from_path(manifest_path)
    from_root = ProjectManifest.from_path(tmp_path)

    assert from_file.project.name == "direct-load"
    assert from_root.project.name == "direct-load"
    assert from_file.to_dict() == from_root.to_dict()


def test_infer_logical_project_profile_to_dict_contains_manifest_and_role_map(tmp_path):
    from saxoflow.project_manifest import MANIFEST_SCHEMA_VERSION, infer_logical_project_profile

    (tmp_path / "source" / "rtl").mkdir(parents=True)
    (tmp_path / "source" / "tb").mkdir(parents=True)
    (tmp_path / "source" / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    (tmp_path / "source" / "tb" / "top_tb.sv").write_text("module top_tb; endmodule\n", encoding="utf-8")
    (tmp_path / "saxoflow_project.yaml").write_text(
        "\n".join(
            [
                f"schema_version: {MANIFEST_SCHEMA_VERSION}",
                "project:",
                "  name: mapped",
                "  top_module: top",
            ]
        ),
        encoding="utf-8",
    )

    profile = infer_logical_project_profile(tmp_path)
    payload = profile.to_dict()

    assert payload["project_name"] == "mapped"
    assert payload["manifest_path"] == "saxoflow_project.yaml"
    assert payload["role_map"]["rtl"] == ["source/rtl"]
    assert payload["role_map"]["sim"] == ["source/tb"]


def test_infer_logical_project_profile_maps_nonstandard_topology(tmp_path):
    from saxoflow.project_manifest import infer_logical_project_profile

    (tmp_path / "hardware" / "design").mkdir(parents=True)
    (tmp_path / "verification" / "testbench").mkdir(parents=True)
    (tmp_path / "collateral" / "spec").mkdir(parents=True)
    (tmp_path / "ci" / "flows").mkdir(parents=True)
    (tmp_path / "results" / "reports").mkdir(parents=True)

    (tmp_path / "hardware" / "design" / "core.sv").write_text("module core; endmodule\n", encoding="utf-8")
    (tmp_path / "verification" / "testbench" / "core_tb.sv").write_text("module core_tb; endmodule\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("nonstandard project\n", encoding="utf-8")

    profile = infer_logical_project_profile(tmp_path)

    assert profile.top_modules == ("core", "core_tb")
    assert profile.role_map["rtl"] == ("hardware/design",)
    assert profile.role_map["sim"] == ("verification/testbench",)
    assert profile.role_map["docs"] == ("README.md", "collateral/spec")
    assert profile.role_map["scripts"] == ("ci/flows",)
    assert profile.role_map["reports"] == ("results/reports",)
    assert profile.flow_readiness["overall"] == "ready"

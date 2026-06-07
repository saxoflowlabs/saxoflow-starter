"""Tests for the manifest-driven PDK registry and CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from click.testing import CliRunner

from saxoflow import pdk_registry
from saxoflow.pdk_cli import pdk


def _write_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def _fake_orfs(tmp_path: Path, platform: str = "sky130hd") -> Path:
    root = tmp_path / "orfs"
    platform_root = root / "flow/platforms" / platform
    (platform_root / "lib").mkdir(parents=True)
    (platform_root / "lef").mkdir(parents=True)
    (platform_root / "lib/sky130_fd_sc_hd__tt_025C_1v80.lib").write_text(
        "library(test) {}\n",
        encoding="utf-8",
    )
    (platform_root / "lef/cells.lef").write_text("VERSION 5.8 ;\n", encoding="utf-8")
    (platform_root / "lef/sky130_fd_sc_hd.tlef").write_text(
        "VERSION 5.8 ;\n",
        encoding="utf-8",
    )
    (platform_root / "lef/sky130_fd_sc_hd_merged.lef").write_text(
        "VERSION 5.8 ;\n",
        encoding="utf-8",
    )
    (platform_root / "gds").mkdir()
    (platform_root / "gds/cells.gds").write_bytes(b"GDS")
    (platform_root / "drc").mkdir()
    (platform_root / "drc/sky130hd.lydrc").write_text("drc\n", encoding="utf-8")
    (platform_root / "lvs").mkdir()
    (platform_root / "lvs/sky130hd.lylvs").write_text("lvs\n", encoding="utf-8")
    (platform_root / "rcx_patterns.rules").write_text("rules\n", encoding="utf-8")
    (platform_root / "setRC.tcl").write_text(
        "set_wire_rc -signal -layer met1\n",
        encoding="utf-8",
    )
    (platform_root / "sky130hd.lyt").write_text("<technology/>\n", encoding="utf-8")
    (root / "flow/Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    return root


def test_packaged_registry_contains_fabrication_and_reference_platforms():
    manifests = {manifest.id: manifest for manifest in pdk_registry.all_manifests()}
    assert {"sky130hd", "sky130hs", "gf180mcu", "ihp-sg13g2"}.issubset(manifests)
    assert manifests["ihp-sg13g2"].classification == "experimental"
    assert manifests["nangate45"].classification == "reference"
    assert manifests["asap7"].classification == "reference"
    assert manifests["asap7"].synthesis["mode"] == "external-netlist-only"
    packaged_ids = {
        "sky130hd",
        "sky130hs",
        "gf180mcu",
        "ihp-sg13g2",
        "nangate45",
        "asap7",
    }
    for manifest_id in packaged_ids:
        manifest = manifests[manifest_id]
        assert manifest.install.get("source")
        assert manifest.physical.get("site")
        assert manifest.physical.get("min_routing_layer") in manifest.layers
        assert manifest.physical.get("max_routing_layer") in manifest.layers
        assert {"klayout", "magic", "netgen"}.issubset(manifest.tooling)
        assert isinstance(manifest.required_environment, list)
    assert {
        library["id"] for library in manifests["gf180mcu"].libraries
    } == {
        "gf180mcu_fd_sc_mcu9t5v0",
        "gf180mcu_fd_sc_mcu7t5v0",
    }
    assert manifests["gf180mcu"].libraries[0]["physical"]["site"].endswith("sc9")
    assert manifests["gf180mcu"].libraries[1]["physical"]["site"].endswith("sc7")


def test_manifest_rejects_invalid_tooling_metadata():
    manifest = pdk_registry.manifest_template()
    manifest["tooling"] = {"klayout": ["not", "a", "mapping"]}

    try:
        pdk_registry.validate_manifest(manifest)
    except pdk_registry.RegistryError as exc:
        assert "tooling.klayout" in str(exc)
    else:
        raise AssertionError("Invalid tooling metadata was accepted.")


def test_manifest_rejects_invalid_environment_variable_name():
    manifest = pdk_registry.manifest_template()
    manifest["required_environment"] = ["INVALID-NAME"]

    try:
        pdk_registry.validate_manifest(manifest)
    except pdk_registry.RegistryError as exc:
        assert "environment variable name" in str(exc)
    else:
        raise AssertionError("Invalid environment variable name was accepted.")


def test_verify_platform_root_checks_declared_tooling(tmp_path):
    root = _fake_orfs(tmp_path) / "flow/platforms/sky130hd"
    manifest = pdk_registry.get_manifest("sky130hd")
    (root / "drc/sky130hd.lydrc").unlink()

    problems = pdk_registry.verify_platform_root(manifest, root)

    assert any("klayout tooling drc" in problem for problem in problems)


def test_alias_resolution_requires_specific_platform_for_family():
    assert pdk_registry.get_manifest("sky130").id == "sky130hd"
    assert pdk_registry.get_manifest("gf180").id == "gf180mcu"


def test_activate_and_verify_orfs_platform(tmp_path, monkeypatch):
    data = tmp_path / "data"
    orfs = _fake_orfs(tmp_path)
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(data))
    monkeypatch.setenv("SAXOFLOW_ORFS_HOME", str(orfs))
    manifest = pdk_registry.get_manifest("sky130hd")

    root = pdk_registry.activate_orfs_platform(manifest)

    assert root == (orfs / "flow/platforms/sky130hd").resolve()
    assert pdk_registry.is_installed(manifest)
    assert pdk_registry.verify_installation(manifest) == []
    assert pdk_registry.installation_metadata_path(manifest).is_file()
    managed_link = (
        data / "pdks/sky130/orfs-managed/sky130hd"
    )
    assert managed_link.is_symlink()


def test_sparse_activation_materializes_cross_platform_symlink_dependency(
    tmp_path,
):
    root = tmp_path / "orfs"
    primary = root / "flow/platforms/primary"
    shared = root / "flow/platforms/shared"
    _write_executable(root / "flow/Makefile", "#!/usr/bin/env bash\n")
    primary.mkdir(parents=True)
    shared.mkdir(parents=True)
    (primary / "config.mk").write_text("PLATFORM = primary\n", encoding="utf-8")
    (shared / "rcx_patterns.rules").write_text("rules\n", encoding="utf-8")
    (primary / "rcx_patterns.rules").symlink_to(
        "../shared/rcx_patterns.rules"
    )

    commands = (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "SaxoFlow Test"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture"],
        ["git", "sparse-checkout", "init", "--no-cone"],
    )
    for command in commands:
        subprocess.run(command, cwd=root, check=True)
    sparse_file = root / ".git/info/sparse-checkout"
    sparse_file.write_text("/*\n!/flow/platforms/*/\n", encoding="utf-8")
    subprocess.run(["git", "read-tree", "-mu", "HEAD"], cwd=root, check=True)

    pdk_registry._sparse_checkout_add(
        root,
        ["/flow/platforms/primary/"],
    )
    patterns = pdk_registry._materialize_symlink_dependencies(
        root,
        "primary",
    )

    assert (primary / "rcx_patterns.rules").is_file()
    assert "/flow/platforms/primary/" in patterns
    assert "/flow/platforms/shared/" in patterns


def test_pdk_install_requires_license_acceptance(tmp_path, monkeypatch):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("SAXOFLOW_ORFS_HOME", str(_fake_orfs(tmp_path)))

    result = CliRunner().invoke(pdk, ["install", "sky130hd"])

    assert result.exit_code != 0
    assert "--accept-license" in result.output
    assert "Estimated download" in result.output
    assert "Required free disk" in result.output


def test_pdk_install_list_verify_and_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("SAXOFLOW_ORFS_HOME", str(_fake_orfs(tmp_path)))
    runner = CliRunner()

    installed = runner.invoke(
        pdk,
        ["install", "sky130hd", "--accept-license"],
    )
    listed = runner.invoke(pdk, ["list"])
    verified = runner.invoke(pdk, ["verify", "sky130hd"])
    removed = runner.invoke(pdk, ["remove", "sky130hd", "--yes"])

    assert installed.exit_code == 0, installed.output
    assert "Activated `sky130hd`" in installed.output
    assert "installed" in listed.output
    assert verified.exit_code == 0, verified.output
    assert removed.exit_code == 0, removed.output
    assert not pdk_registry.is_installed(pdk_registry.get_manifest("sky130hd"))
    assert not (tmp_path / "data/pdks/sky130/orfs-managed/sky130hd").exists()


def test_pdk_verify_detects_recorded_artifact_corruption(tmp_path, monkeypatch):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "data"))
    orfs = _fake_orfs(tmp_path)
    monkeypatch.setenv("SAXOFLOW_ORFS_HOME", str(orfs))
    runner = CliRunner()
    installed = runner.invoke(
        pdk,
        ["install", "sky130hd", "--accept-license"],
    )
    assert installed.exit_code == 0, installed.output
    (
        orfs
        / "flow/platforms/sky130hd/lib/"
        "sky130_fd_sc_hd__tt_025C_1v80.lib"
    ).write_text("corrupted\n", encoding="utf-8")

    result = runner.invoke(pdk, ["verify", "sky130hd"])

    assert result.exit_code != 0
    assert "Checksum mismatch" in result.output


def test_register_custom_external_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "data"))
    external = tmp_path / "external"
    (external / "lib").mkdir(parents=True)
    (external / "lef").mkdir()
    (external / "lib/cells.lib").write_text("library(test) {}\n", encoding="utf-8")
    (external / "lef/cells.lef").write_text("VERSION 5.8 ;\n", encoding="utf-8")
    (external / "lef/technology.lef").write_text(
        "VERSION 5.8 ;\n",
        encoding="utf-8",
    )
    (external / "gds").mkdir()
    (external / "gds/cells.gds").write_bytes(b"GDS")
    (external / "openroad").mkdir()
    (external / "openroad/rcx.rules").write_text("rules\n", encoding="utf-8")
    manifest_path = tmp_path / "custom.yaml"
    manifest = pdk_registry.manifest_template()
    manifest["id"] = "research-pdk"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    runner = CliRunner()

    registered = runner.invoke(
        pdk,
        ["register", "--manifest", str(manifest_path)],
    )
    installed = runner.invoke(
        pdk,
        [
            "install",
            "research-pdk",
            "--root",
            str(external),
            "--accept-license",
        ],
    )

    assert registered.exit_code == 0, registered.output
    assert installed.exit_code == 0, installed.output
    resolved = pdk_registry.get_manifest("research-pdk")
    assert pdk_registry.platform_root(resolved) == external.resolve()


def test_manifest_template_command_refuses_overwrite(tmp_path):
    output = tmp_path / "platform.yaml"
    runner = CliRunner()
    first = runner.invoke(pdk, ["template", "--output", str(output)])
    second = runner.invoke(pdk, ["template", "--output", str(output)])

    assert first.exit_code == 0
    assert second.exit_code != 0
    assert yaml.safe_load(output.read_text())["classification"] == "custom"


def test_register_with_root_runs_read_only_openroad_technology_test(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "data"))
    external = tmp_path / "external"
    (external / "lib").mkdir(parents=True)
    (external / "lef").mkdir()
    (external / "gds").mkdir()
    (external / "openroad").mkdir()
    (external / "lib/cells.lib").write_text("library(test) {}\n")
    (external / "lef/technology.lef").write_text("VERSION 5.8 ;\n")
    (external / "lef/cells.lef").write_text("VERSION 5.8 ;\n")
    (external / "gds/cells.gds").write_bytes(b"GDS")
    (external / "openroad/rcx.rules").write_text("rules\n")
    manifest_path = tmp_path / "custom.yaml"
    manifest = pdk_registry.manifest_template()
    manifest["id"] = "validated-custom"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    binary_dir = tmp_path / "bin"
    _write_executable(
        binary_dir / "openroad",
        "#!/usr/bin/env bash\n"
        "grep -q 'read_lef -tech' \"$3\"\n"
        "echo SAXOFLOW_TECHNOLOGY_LOAD_OK\n",
    )
    monkeypatch.setenv(
        "PATH",
        str(binary_dir) + ":" + str(Path("/usr/bin")),
    )

    result = CliRunner().invoke(
        pdk,
        [
            "register",
            "--manifest",
            str(manifest_path),
            "--root",
            str(external),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "technology-load test passed" in result.output
    registered = pdk_registry.get_manifest("validated-custom")
    assert pdk_registry.platform_root(registered) == external.resolve()


def test_register_can_run_manifest_smoke_test(tmp_path, monkeypatch):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "data"))
    external = tmp_path / "external"
    for directory in ("lib", "lef", "gds", "openroad", "validation"):
        (external / directory).mkdir(parents=True, exist_ok=True)
    (external / "lib/cells.lib").write_text("library(test) {}\n")
    (external / "lef/technology.lef").write_text("VERSION 5.8 ;\n")
    (external / "lef/cells.lef").write_text("VERSION 5.8 ;\n")
    (external / "gds/cells.gds").write_bytes(b"GDS")
    (external / "openroad/rcx.rules").write_text("rules\n")
    _write_executable(
        external / "validation/smoke_test.sh",
        "#!/usr/bin/env bash\n"
        "test -f \"$SAXOFLOW_PLATFORM_ROOT/lef/technology.lef\"\n"
        "echo floorplan-smoke-ok\n",
    )
    manifest = pdk_registry.manifest_template()
    manifest["id"] = "smoke-custom"
    manifest_path = tmp_path / "custom.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    binary_dir = tmp_path / "bin"
    _write_executable(
        binary_dir / "openroad",
        "#!/usr/bin/env bash\n"
        "echo SAXOFLOW_TECHNOLOGY_LOAD_OK\n",
    )
    monkeypatch.setenv("PATH", f"{binary_dir}:/usr/bin")

    result = CliRunner().invoke(
        pdk,
        [
            "register",
            "--manifest",
            str(manifest_path),
            "--root",
            str(external),
            "--smoke-test",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "floorplan-smoke-ok" in result.output
    assert "smoke test passed" in result.output

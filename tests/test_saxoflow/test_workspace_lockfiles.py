from __future__ import annotations

import yaml

from saxoflow.workspace import lockfiles as sut


def test_build_toolchain_lock_is_deterministic_and_classifies_sources():
    lock = sut.build_toolchain_lock(["yosys", "iverilog", "yosys", "unknown-tool"])
    names = [entry["name"] for entry in lock["toolchain"]["tools"]]
    assert names == ["iverilog", "unknown-tool", "yosys"]

    sources = {entry["name"]: entry["source"] for entry in lock["toolchain"]["tools"]}
    assert sources["iverilog"] == "apt"
    assert sources["yosys"] == "recipe"
    assert sources["unknown-tool"] == "unknown"


def test_build_models_lock_placeholder():
    lock = sut.build_models_lock()
    assert lock["schema_version"] == 1
    assert lock["models"]["selection_policy"] == "inherit"
    assert lock["models"]["catalog"] == []


def test_write_lockfiles_roundtrip(tmp_path):
    project_data = {
        "schema_version": 1,
        "project": {"name": "demo", "layout": "workspace"},
        "toolchain": {"backend": "system", "selected_tools": ["iverilog", "yosys"]},
        "models": {"selection_policy": "inherit"},
        "migration": {"legacy_tools_file": ".saxoflow_tools.json"},
    }
    toolchain_path, models_path = sut.write_lockfiles(tmp_path, project_data)

    assert toolchain_path.exists()
    assert models_path.exists()

    toolchain = yaml.safe_load(toolchain_path.read_text(encoding="utf-8"))
    models = yaml.safe_load(models_path.read_text(encoding="utf-8"))
    assert [entry["name"] for entry in toolchain["toolchain"]["tools"]] == ["iverilog", "yosys"]
    assert models["models"]["catalog"] == []
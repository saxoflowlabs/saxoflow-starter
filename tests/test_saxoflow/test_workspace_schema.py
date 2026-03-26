from __future__ import annotations

from pathlib import Path

import yaml

from saxoflow.workspace import schema as sut


def test_workspace_paths_and_layout_detection(tmp_path):
    paths = sut.workspace_paths(tmp_path)
    assert paths.project_file == tmp_path / ".saxoflow" / "project.yaml"
    assert sut.detect_project_layout(tmp_path) == "workspace"

    (tmp_path / "source").mkdir()
    assert sut.detect_project_layout(tmp_path) == "legacy-unit"


def test_default_project_data_and_roundtrip(tmp_path):
    data = sut.default_project_data("demo", ["yosys", "iverilog", "yosys"])
    assert data["toolchain"]["selected_tools"] == ["iverilog", "yosys"]
    assert sut.validate_project_data(data) == []

    written = sut.write_project_data(tmp_path, data)
    assert written.exists()

    loaded = sut.load_project_data(tmp_path)
    assert loaded == data
    assert sut.read_selected_tools(tmp_path) == ["iverilog", "yosys"]
    assert sut.read_tool_backend(tmp_path) == "system"


def test_validate_project_data_reports_errors():
    bad = {
        "schema_version": 99,
        "project": {"name": ""},
        "toolchain": {"backend": "", "selected_tools": [""]},
        "models": {"selection_policy": 1},
        "migration": [],
    }
    errors = sut.validate_project_data(bad)
    assert any("schema_version" in err for err in errors)
    assert any("project.name" in err for err in errors)
    assert any("toolchain.backend" in err for err in errors)
    assert any("selected_tools" in err for err in errors)
    assert any("models.selection_policy" in err for err in errors)
    assert any("migration section" in err for err in errors)


def test_validate_project_data_rejects_backward_schema_version():
    data = sut.default_project_data("demo", ["iverilog"])
    data["schema_version"] = 0
    errors = sut.validate_project_data(data)
    assert any("schema_version" in err for err in errors)


def test_validate_project_data_rejects_forward_schema_version():
    data = sut.default_project_data("demo", ["iverilog"])
    data["schema_version"] = 2
    errors = sut.validate_project_data(data)
    assert any("schema_version" in err for err in errors)


def test_load_project_data_and_selected_tools_tolerate_invalid_yaml(tmp_path):
    proj = tmp_path / ".saxoflow"
    proj.mkdir()
    (proj / "project.yaml").write_text(": bad", encoding="utf-8")
    assert sut.load_project_data(tmp_path) is None
    assert sut.read_selected_tools(tmp_path) == []


def test_read_tool_backend_normalizes_value(tmp_path):
    proj = tmp_path / ".saxoflow"
    proj.mkdir(parents=True)
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "project": {"name": "demo", "layout": "workspace"},
                "toolchain": {"backend": " Managed ", "selected_tools": ["yosys"]},
                "models": {"selection_policy": "inherit"},
                "migration": {"legacy_tools_file": None},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert sut.read_tool_backend(tmp_path) == "managed"


def test_read_tool_backend_defaults_to_system_when_missing(tmp_path):
    assert sut.read_tool_backend(tmp_path) == "system"


def test_read_tool_backend_defaults_to_system_when_empty_string(tmp_path):
    proj = tmp_path / ".saxoflow"
    proj.mkdir(parents=True)
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "project": {"name": "demo", "layout": "workspace"},
                "toolchain": {"backend": "", "selected_tools": []},
                "models": {"selection_policy": "inherit"},
                "migration": {"legacy_tools_file": None},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert sut.read_tool_backend(tmp_path) == "system"

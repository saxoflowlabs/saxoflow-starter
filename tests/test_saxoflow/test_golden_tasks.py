"""Golden-task baseline checks for tiny design artifact layouts."""

from __future__ import annotations

from pathlib import Path

import pytest


GOLDEN_TASKS_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden_tasks"


@pytest.mark.parametrize(
    "task_name,rtl_name,tb_name,formal_name",
    [
        ("counter", "counter.v", "counter_tb.v", "counter_formal.sv"),
        ("mux", "mux.v", "mux_tb.v", "mux_formal.sv"),
    ],
)
def test_tiny_design_golden_tasks_have_expected_artifacts(task_name, rtl_name, tb_name, formal_name):
    """Phase-0 baseline: tiny designs keep the current expected artifact set."""
    task_root = GOLDEN_TASKS_ROOT / task_name
    rtl_dir = task_root / "source" / "rtl" / "verilog"
    tb_dir = task_root / "source" / "tb" / "verilog"
    formal_script_dir = task_root / "formal" / "scripts"
    formal_source_dir = task_root / "formal" / "source"

    expected_paths = [
        rtl_dir / rtl_name,
        tb_dir / tb_name,
        formal_script_dir / "spec.sby",
        formal_source_dir / "formal_top.sv",
    ]

    for path in expected_paths:
        assert path.exists(), f"missing golden artifact: {path}"

    assert sorted(child.name for child in rtl_dir.iterdir()) == [rtl_name]
    assert sorted(child.name for child in tb_dir.iterdir()) == [tb_name]
    assert sorted(child.name for child in formal_script_dir.iterdir()) == ["spec.sby"]
    assert sorted(child.name for child in formal_source_dir.iterdir()) == ["formal_top.sv"]

    rtl_text = expected_paths[0].read_text(encoding="utf-8")
    tb_text = expected_paths[1].read_text(encoding="utf-8")
    spec_text = expected_paths[2].read_text(encoding="utf-8")
    formal_text = expected_paths[3].read_text(encoding="utf-8")

    assert f"module {task_name}" in rtl_text
    assert f"module {task_name}_tb" in tb_text
    assert formal_name.replace(".sv", "") not in formal_text
    assert f"read -formal -sv ../../source/rtl/verilog/{rtl_name}" in spec_text
    assert f"prep -top {task_name}_formal" in spec_text
"""
Hermetic tests for saxoflow_agenticai.orchestrator.AgentOrchestrator.

Goals:
- Preserve current behavior while maximizing meaningful coverage.
- Exercise happy path, debug/heal paths, and max-iteration failure.
- Ensure no real network calls; all writes under tmp_path and/or patched.

Why these tests:
- The orchestrator stitches multiple subsystems; small changes can break
  critical control flow. These tests lock down the public contract and
  catch regressions in healing and reporting logic.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Tuple

import io
import sys
import pytest


# ----------------------
# Local fakes / test stubs
# ----------------------

class _SimAgent:
    """Simulation agent that returns queued results per call."""
    def __init__(self, results: List[Dict[str, str]]):
        self.results = list(results)
        self.calls: List[Tuple[str, str]] = []

    def run(self, project_root: str, base: str) -> Dict[str, str]:
        self.calls.append((project_root, base))
        if not self.results:
            # Default to failed if exhausted
            return {"status": "failed", "stdout": "", "stderr": "error", "error_message": "exhausted"}
        return self.results.pop(0)


class _DebugAgent:
    """Debug agent returning fixed (report, suggested_agents). Records inputs."""
    def __init__(self, report: str, suggestions: List[str]):
        self.report = report
        self.suggestions = list(suggestions)
        self.calls: List[Dict[str, str]] = []

    def run(self, **kwargs) -> Tuple[str, List[str]]:
        self.calls.append(kwargs)  # capture provided code/stdout/stderr
        return self.report, list(self.suggestions)


class _ReportAgent:
    """Final report agent that returns a constant string, recording inputs."""
    def __init__(self, result: str = "PIPE_REPORT"):
        self.result = result
        self.calls: List[Dict[str, str]] = []

    def run(self, phase_outputs: Dict[str, str]) -> str:
        self.calls.append(dict(phase_outputs))
        return self.result


# ----------------------
# Helper-coverage tests
# ----------------------

def test_detect_sim_failures_matrix():
    """
    Unit coverage for _detect_sim_failures:
    - VCD missing detected from stdout/stderr
    - Compile flags trip on variations (error/parse/fatal)
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    # No failures
    vcd, comp = sut._detect_sim_failures(stdout="ok", stderr="all good")
    assert (vcd, comp) == (False, False)

    # VCD missing in stdout
    vcd, comp = sut._detect_sim_failures(stdout="No VCD files found", stderr="")
    assert (vcd, comp) == (True, False)

    # Compile error variants (stderr lower-cased)
    for err in ["ERROR here", "parse issue", "FATAL crash"]:
        vcd, comp = sut._detect_sim_failures(stdout="", stderr=err)
        assert vcd is False and comp is True


def test_suppress_stdio_swaps_and_restores():
    """
    _suppress_stdio(True) should swap out stdout/stderr, then restore them.
    This verifies behavior without relying on capsys semantics.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    old_out, old_err = sys.stdout, sys.stderr
    with sut._suppress_stdio(True):
        assert sys.stdout is not old_out
        assert sys.stderr is not old_err
        assert isinstance(sys.stdout, io.StringIO)
        assert isinstance(sys.stderr, io.StringIO)
    assert sys.stdout is old_out
    assert sys.stderr is old_err


# ----------------------
# Public API tests: full_pipeline
# ----------------------

def _patch_file_utils(monkeypatch, sut, tmp_path, writes_log):
    """
    Patch file_utils helpers used by the SUT:
    - base_name_from_path: deterministic base name
    - write_output: actually writes files under tmp_path and logs the call
    """
    monkeypatch.setattr(sut, "base_name_from_path", lambda p: "design", raising=True)

    def fake_write_output(content, _template, out_dir, base, ext):
        writes_log.append((content, out_dir, base, ext))
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        Path(out_dir, f"{base}{ext}").write_text(content, encoding="utf-8")

    monkeypatch.setattr(sut, "write_output", fake_write_output, raising=True)


def _patch_agents_for_success(monkeypatch, sut, report_agent):
    """
    Patch AgentManager.get_agent so that:
    - rtlgen/rtlreview consumed only by iterate_improvements (we don't need their methods)
    - tbgen/tbreview likewise
    - sim returns success immediately
    - debug is present but will not be invoked on success
    - report returns PIPE_REPORT
    """
    sim = _SimAgent([{"status": "success", "stdout": "", "stderr": "", "error_message": ""}])
    dbg = _DebugAgent("dbg", ["RTLGenAgent"])  # should not be used
    def get_agent(name, **_):
        if name == "sim":
            return sim
        if name == "debug":
            return dbg
        if name == "report":
            return report_agent
        # for rtlgen/rtlreview/tbgen/tbreview we just need opaque objects
        return object()

    monkeypatch.setattr(sut.AgentManager, "get_agent", staticmethod(get_agent), raising=True)
    return sim, dbg


def _patch_iterate_improvements_basic(monkeypatch, sut):
    """
    Patch iterate_improvements to return baseline rtl/tb results without feedback.
    """
    def iter_improve(agent, initial_spec, feedback_agent, max_iters, feedback=None):
        # Decide what we're generating based on initial_spec's shape
        if isinstance(initial_spec, tuple):
            # TB path: (spec, rtl_code, base)
            return "TB_CODE", "TB_REVIEW"
        else:
            # RTL path
            return "RTL_CODE", "RTL_REVIEW"
    monkeypatch.setattr(sut.AgentFeedbackCoordinator, "iterate_improvements", staticmethod(iter_improve), raising=True)


def _patch_iterate_improvements_with_feedback(monkeypatch, sut):
    """
    Patch iterate_improvements to return improved code when feedback is provided.
    """
    def iter_improve(agent, initial_spec, feedback_agent, max_iters, feedback=None):
        if feedback:
            if isinstance(initial_spec, tuple):
                return "TB_IMPROVED", "TB_REVIEW2"
            return "RTL_IMPROVED", "RTL_REVIEW2"
        if isinstance(initial_spec, tuple):
            return "TB_CODE", "TB_REVIEW"
        return "RTL_CODE", "RTL_REVIEW"
    monkeypatch.setattr(sut.AgentFeedbackCoordinator, "iterate_improvements", staticmethod(iter_improve), raising=True)


def test_full_pipeline_happy_path_no_debug(tmp_path, monkeypatch):
    """
    End-to-end success on the first simulation iteration:
    - Writes initial RTL/TB once.
    - Does NOT call debug agent.
    - Produces stable keys and final PIPE_REPORT.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    # Create spec
    spec = tmp_path / "spec.txt"
    spec.write_text("SPEC", encoding="utf-8")

    writes_log: list = []
    _patch_file_utils(monkeypatch, sut, tmp_path, writes_log)
    _patch_iterate_improvements_basic(monkeypatch, sut)

    report_agent = _ReportAgent("PIPE_REPORT")
    sim, dbg = _patch_agents_for_success(monkeypatch, sut, report_agent)

    out = sut.AgentOrchestrator.full_pipeline(
        spec_file=str(spec),
        project_path=str(tmp_path / "proj"),
        verbose=False,
        max_iters=3,
    )

    # Assertions on outputs
    assert out["rtl_code"] == "RTL_CODE"
    assert out["testbench_code"] == "TB_CODE"
    assert out["simulation_status"] == "success"
    assert out["debug_report"] == "No debug needed (simulation successful)"
    assert out["pipeline_report"] == "PIPE_REPORT"

    # Files were written twice (rtl+tb initial)
    assert len(writes_log) == 2
    assert dbg.calls == []  # debug not invoked on success
    assert len(report_agent.calls) == 1
    # Report received all required keys
    keys = set(report_agent.calls[0].keys())
    for k in [
        "specification", "rtl_code", "rtl_review_report",
        "testbench_code", "testbench_review_report",
        "formal_properties", "formal_property_review_report",
        "simulation_status", "simulation_stdout", "simulation_stderr",
        "simulation_error_message", "debug_report",
    ]:
        assert k in keys


def test_full_pipeline_failure_user_action_breaks_early(tmp_path, monkeypatch):
    """
    Simulation fails; debug suggests only UserAction -> pipeline stops healing.
    - Initial rtl/tb written.
    - Debug called once.
    - No extra improvements written.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    spec = tmp_path / "spec.txt"
    spec.write_text("SPEC", encoding="utf-8")

    writes_log: list = []
    _patch_file_utils(monkeypatch, sut, tmp_path, writes_log)
    _patch_iterate_improvements_basic(monkeypatch, sut)

    # Sim returns failure once; no further results (loop will break)
    sim = _SimAgent([{"status": "failed", "stdout": "", "stderr": "error here", "error_message": "x"}])
    dbg = _DebugAgent("Please fix manually", ["UserAction"])
    rep = _ReportAgent("PIPE")

    def get_agent(name, **_):
        return {"sim": sim, "debug": dbg, "report": rep}.get(name, object())

    monkeypatch.setattr(sut.AgentManager, "get_agent", staticmethod(get_agent), raising=True)

    out = sut.AgentOrchestrator.full_pipeline(
        spec_file=str(spec),
        project_path=str(tmp_path / "proj"),
        verbose=False,
        max_iters=3,
    )

    assert out["simulation_status"] == "failed"
    assert out["debug_report"] == "Please fix manually"
    assert len(dbg.calls) == 1
    assert len(writes_log) == 2  # only initial writes


def test_full_pipeline_heal_then_success(tmp_path, monkeypatch):
    """
    First simulation fails with 'No VCD files found' and/or compile clues.
    Debug suggests RTL & TB healing. Orchestrator:
    - runs iterate_improvements once for RTL and TB with feedback,
    - writes improved files,
    - re-simulates and succeeds on next iteration.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    spec = tmp_path / "spec.txt"
    spec.write_text("SPEC", encoding="utf-8")

    writes_log: list = []
    _patch_file_utils(monkeypatch, sut, tmp_path, writes_log)
    _patch_iterate_improvements_with_feedback(monkeypatch, sut)

    # Iteration 1: failed with VCD missing -> triggers debug & healing.
    # Iteration 2: success -> exit.
    sim = _SimAgent([
        {"status": "failed", "stdout": "No VCD files found", "stderr": "", "error_message": ""},
        {"status": "success", "stdout": "", "stderr": "", "error_message": ""},
    ])
    dbg = _DebugAgent("apply fixes", ["RTLGenAgent", "TBGenAgent"])
    rep = _ReportAgent("OK_REPORT")

    def get_agent(name, **_):
        return {"sim": sim, "debug": dbg, "report": rep}.get(name, object())

    monkeypatch.setattr(sut.AgentManager, "get_agent", staticmethod(get_agent), raising=True)

    out = sut.AgentOrchestrator.full_pipeline(
        spec_file=str(spec),
        project_path=str(tmp_path / "proj"),
        verbose=False,
        max_iters=3,
    )

    # Improved results after healing
    assert out["rtl_code"] == "RTL_IMPROVED"
    assert out["testbench_code"] == "TB_IMPROVED"
    assert out["simulation_status"] == "success"
    assert out["debug_report"] == "apply fixes"

    # Writes: 2 initial + 2 improved = 4
    assert len(writes_log) == 4
    assert len(dbg.calls) == 1
    assert len(sim.calls) == 2  # two simulation iterations


def test_full_pipeline_max_iters_reached(tmp_path, monkeypatch):
    """
    Simulation fails across all iterations -> orchestrator logs error on final pass
    and returns failure status with last sim data. We verify the pipeline still
    proceeds to reporting.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    spec = tmp_path / "spec.txt"
    spec.write_text("SPEC", encoding="utf-8")

    writes_log: list = []
    _patch_file_utils(monkeypatch, sut, tmp_path, writes_log)
    _patch_iterate_improvements_with_feedback(monkeypatch, sut)

    # Three failing iterations; compile errors present in stderr
    sim = _SimAgent([
        {"status": "failed", "stdout": "", "stderr": "ERROR parse", "error_message": "e1"},
        {"status": "failed", "stdout": "", "stderr": "fatal crash", "error_message": "e2"},
        {"status": "failed", "stdout": "", "stderr": "still error", "error_message": "e3"},
    ])
    dbg = _DebugAgent("kept failing", ["RTLGenAgent"])  # keep suggesting RTL fixes
    rep = _ReportAgent("FINAL_REPORT")

    def get_agent(name, **_):
        return {"sim": sim, "debug": dbg, "report": rep}.get(name, object())

    monkeypatch.setattr(sut.AgentManager, "get_agent", staticmethod(get_agent), raising=True)

    out = sut.AgentOrchestrator.full_pipeline(
        spec_file=str(spec),
        project_path=str(tmp_path / "proj"),
        verbose=False,
        max_iters=3,
    )

    assert out["simulation_status"] == "failed"
    assert out["simulation_error_message"] == "e3"
    assert out["debug_report"] == "kept failing"
    assert out["pipeline_report"] == "FINAL_REPORT"
    # initial rtl/tb writes + up to 2 healing passes for RTL (since i < max_iters-1)
    # initial 2 + 2 improvements = 4 writes total
    assert len(writes_log) == 4
    assert len(sim.calls) == 3
    assert len(dbg.calls) == 3  # debug called each iteration


def test_full_pipeline_missing_spec_raises(tmp_path):
    """
    When the spec file path does not exist, full_pipeline raises FileNotFoundError.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    missing = tmp_path / "absent.txt"
    with pytest.raises(FileNotFoundError):
        sut.AgentOrchestrator.full_pipeline(
            spec_file=str(missing),
            project_path=str(tmp_path / "proj"),
        )


def test_full_pipeline_spec_read_error_raises(tmp_path, monkeypatch):
    """
    If reading the spec raises, the orchestrator wraps with FileNotFoundError
    containing 'Failed to read spec file'.
    """
    from saxoflow_agenticai.orchestrator import agent_orchestrator as sut

    # Create the path but cause read_text to fail
    spec = tmp_path / "spec.txt"
    spec.write_text("X", encoding="utf-8")

    def boom(*_a, **_kw):
        raise OSError("cannot read")

    monkeypatch.setattr(Path, "read_text", boom, raising=True)

    with pytest.raises(FileNotFoundError) as ei:
        sut.AgentOrchestrator.full_pipeline(
            spec_file=str(spec),
            project_path=str(tmp_path / "proj"),
        )
    assert "Failed to read spec file" in str(ei.value)

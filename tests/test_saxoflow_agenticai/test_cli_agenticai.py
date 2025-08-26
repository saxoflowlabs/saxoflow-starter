"""
Hermetic tests for saxoflow_agenticai.cli (Click CLI).

We validate:
- quiet stdout suppression
- interactive key setup (TTY vs non-TTY)
- run_with_review improvement loop (single and tuple args)
- all public commands: success paths + critical error paths
- final writes routed correctly (no real FS writes except tmp files)
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner


# -----------------------
# Small local stubs
# -----------------------

class _GenStub:
    """Generator with run/improve; can be reused for rtl/tb/prop."""

    def __init__(self, first: str = "OUT0", improved: str = "OUT1"):
        self.first = first
        self.improved = improved
        self.calls = {"run": [], "improve": []}

    def run(self, *a):
        self.calls["run"].append(a)
        return self.first

    def improve(self, *a):
        self.calls["improve"].append(a)
        return self.improved


class _ReviewStub:
    """Review stub that yields queued feedback."""

    def __init__(self, items):
        self.items = list(items)
        self.calls = []

    def run(self, *a):
        self.calls.append(a)
        return self.items.pop(0) if self.items else ""


class _AgentStub:
    """Simple agent for review-only commands."""

    def __init__(self, result: str = "OK"):
        self.result = result
        self.calls = []

    def run(self, arg: str):
        self.calls.append(arg)
        return self.result


# -----------------------
# Helpers
# -----------------------

def _mk_project(tmp_path: Path) -> Path:
    """Create minimal unit project structure."""
    (tmp_path / "source" / "specification").mkdir(parents=True)
    (tmp_path / "source" / "rtl" / "verilog").mkdir(parents=True)
    (tmp_path / "source" / "tb" / "verilog").mkdir(parents=True)
    (tmp_path / "formal").mkdir()
    (tmp_path / "output" / "report").mkdir(parents=True)
    return tmp_path


def _runner() -> CliRunner:
    # Older Click in CI: no mix_stderr kw.
    return CliRunner()


# -----------------------
# Unit-level helpers
# -----------------------

def test__suppress_output_swaps_and_restores():
    """stdout/stderr become StringIO inside; restored afterwards."""
    import sys
    from saxoflow_agenticai import cli as sut

    o1, e1 = sys.stdout, sys.stderr
    with sut._suppress_output(True):
        assert isinstance(sys.stdout, io.StringIO)
        assert isinstance(sys.stderr, io.StringIO)
    assert sys.stdout is o1 and sys.stderr is e1


def test__supported_provider_envs_and_any_key_present(monkeypatch):
    """Only providers with `env` are returned; any present env → True."""
    from saxoflow_agenticai import cli as sut

    monkeypatch.setattr(
        sut._ms,
        "PROVIDERS",
        {
            "openai": SimpleNamespace(env="OPENAI_API_KEY"),
            "openrouter": SimpleNamespace(env="OPENROUTER_API_KEY"),
            "pseudo": SimpleNamespace(env=None),
        },
        raising=True,
    )

    env_map = sut._supported_provider_envs()
    assert env_map == {
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert sut._any_llm_key_present() is False

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    assert sut._any_llm_key_present() is True


def test__write_env_kv_add_and_update(tmp_path):
    """Writes KEY=VALUE if missing; updates value if present; preserves comments/blank lines."""
    from saxoflow_agenticai import cli as sut

    p = tmp_path / ".env"
    p.write_text("# heading\n\nX=1\n", encoding="utf-8")

    sut._write_env_kv(p, "Y", "2")
    assert p.read_text(encoding="utf-8").strip().splitlines()[-1] == "Y=2"

    sut._write_env_kv(p, "X", "42")
    content = p.read_text(encoding="utf-8")
    assert "X=42" in content
    assert content.startswith("# heading")


def test__interactive_setup_keys_non_tty_raises(tmp_path, monkeypatch):
    """
    Non-TTY should raise ClickException with guidance when no keys present.
    Ensures we don't silently skip due to ambient CI env.
    """
    from saxoflow_agenticai import cli as sut

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sut,
        "_supported_provider_envs",
        lambda: {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"},
        raising=True,
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Force "no keys present" branch deterministically
    monkeypatch.setattr(sut, "_any_llm_key_present", lambda: False, raising=True)

    class _FakeIn:
        def isatty(self):  # pragma: no cover - tiny method
            return False

    monkeypatch.setattr(sut.sys, "stdin", _FakeIn(), raising=True)

    with pytest.raises(click.ClickException):
        sut._interactive_setup_keys(force=False)


def test__interactive_setup_keys_happy_tty(tmp_path, monkeypatch):
    """
    Happy path writes .env and prints success lines when interactive and forced.
    """
    from saxoflow_agenticai import cli as sut

    monkeypatch.chdir(tmp_path)

    class _FakeIn:
        def isatty(self):
            return True

    monkeypatch.setattr(sut.sys, "stdin", _FakeIn(), raising=True)
    monkeypatch.setattr(sut, "_supported_provider_envs", lambda: {"openai": "OPENAI_API_KEY"}, raising=True)
    # Deterministic prompts: provider then key
    answers = iter(["openai", "sk-openai"])
    monkeypatch.setattr(sut.click, "prompt", lambda *a, **k: next(answers), raising=True)
    # Do not reload env in tests
    monkeypatch.setattr(sut, "load_dotenv", lambda **_: None, raising=True)
    # Also force "no keys present" so we enter the flow even if CI env is weird
    monkeypatch.setattr(sut, "_any_llm_key_present", lambda: False, raising=True)

    seen = []
    monkeypatch.setattr(sut.click, "secho", lambda *a, **k: seen.append(("secho", a, k)), raising=True)
    monkeypatch.setattr(sut.click, "echo", lambda *a, **k: seen.append(("echo", a, k)), raising=True)

    sut._interactive_setup_keys(force=True)

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-openai" in env_text
    assert any("Saved OPENAI_API_KEY" in a[1][0] for a in seen if a[0] == "secho")


# -----------------------
# run_with_review
# -----------------------

def test_run_with_review_single_and_tuple_paths():
    """
    First feedback requires change; second says no issues; improve called appropriately
    for both single-arg and tuple-arg paths.
    """
    from saxoflow_agenticai import cli as sut

    # Single-arg path
    gen1 = _GenStub(first="RTL0", improved="RTL1")
    rev1 = _ReviewStub(["Please fix", "No major issues found."])
    out1, fb1 = sut.run_with_review(gen1, rev1, "SPEC", max_iters=3, verbose=False)
    assert out1 == "RTL1" and "No major issues" in fb1
    assert gen1.calls["improve"]  # called once with (SPEC, feedback)

    # Tuple-arg path
    gen2 = _GenStub(first="TB0", improved="TB1")
    rev2 = _ReviewStub(["needs change", "no issues found"])
    out2, fb2 = sut.run_with_review(gen2, rev2, ("S", "R", "Top"), max_iters=3, verbose=False)
    assert out2 == "TB1" and "no issues" in fb2
    assert gen2.calls["improve"][0] == ("S", "R", "Top", "needs change")


# -----------------------
# Fixture: opt-in stub for key setup during CLI commands
# -----------------------

@pytest.fixture
def no_interactive_key_setup(monkeypatch):
    """
    For CLI command tests: ensure the Click group-level call to
    `_interactive_setup_keys(force=False)` is a no-op so commands
    don't prompt or raise in non-TTY environments.
    """
    from saxoflow_agenticai import cli as sut
    monkeypatch.setattr(sut, "_interactive_setup_keys", lambda *a, **k: None, raising=True)
    return True


# -----------------------
# CLI command tests
# -----------------------

def test_cli_rtlgen_happy_default_discovery(tmp_path, monkeypatch, no_interactive_key_setup):
    """
    Find spec from source/specification, print RTL, and write to default rtl path.
    """
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    project = _mk_project(tmp_path)
    (project / "source" / "specification" / "design.md").write_text("SPEC", encoding="utf-8")
    monkeypatch.chdir(project)

    # Agents still get constructed -> stub them
    monkeypatch.setattr(sut.AgentManager, "get_agent", lambda *a, **k: object(), raising=True)
    # Deterministic run result
    monkeypatch.setattr(sut, "run_with_review", lambda *a, **k: ("RTL_OUT", "ok"), raising=True)

    calls = []
    monkeypatch.setattr(sut, "write_output", lambda *a, **k: calls.append((a, k)) or "P", raising=True)

    res = _runner().invoke(sut.cli, ["rtlgen"])
    assert res.exit_code == 0
    assert "RTL_OUT" in res.output

    args, kw = calls[0]
    assert kw["default_folder"].endswith("source/rtl/verilog")
    assert kw["default_name"].endswith("_rtl_gen")
    assert kw["ext"] == ".v"


def test_cli_tbgen_happy_infers_top_and_writes(tmp_path, monkeypatch, no_interactive_key_setup):
    """Infer top module from RTL and write TB; print TB content."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    project = _mk_project(tmp_path)
    rtl_path = project / "source" / "rtl" / "verilog" / "abc.v"
    rtl_path.write_text("module topx; endmodule", encoding="utf-8")
    (project / "source" / "specification" / "design.md").write_text("SPEC", encoding="utf-8")
    monkeypatch.chdir(project)

    # Stub agents created later in tbgen
    monkeypatch.setattr(sut.AgentManager, "get_agent", lambda *a, **k: object(), raising=True)
    monkeypatch.setattr(sut, "run_with_review", lambda *a, **k: ("TB_OUT", "ok"), raising=True)

    calls = []
    monkeypatch.setattr(sut, "write_output", lambda *a, **k: calls.append((a, k)) or "Q", raising=True)

    res = _runner().invoke(sut.cli, ["tbgen"])
    assert res.exit_code == 0
    assert "TB_OUT" in res.output

    args, kw = calls[0]
    assert kw["default_folder"].endswith("source/tb/verilog")
    assert kw["default_name"].endswith("_tb_gen")
    assert kw["ext"] == ".v"


def test_cli_tbgen_cannot_infer_top_raises(tmp_path, monkeypatch, no_interactive_key_setup):
    """If no 'module <name>' pattern exists, tbgen raises ClickException."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    project = _mk_project(tmp_path)
    rtl = project / "source" / "rtl" / "verilog" / "bad.v"
    # IMPORTANT: do not include "module " in this text, or the regex will match.
    rtl.write_text("/* nothing to infer */", encoding="utf-8")
    (project / "source" / "specification" / "design.md").write_text("SPEC", encoding="utf-8")
    monkeypatch.chdir(project)

    res = _runner().invoke(sut.cli, ["tbgen"])
    assert res.exit_code != 0
    assert "Unable to infer top module name" in res.output


def test_cli_fpropgen_happy(tmp_path, monkeypatch, no_interactive_key_setup):
    """Reads RTL, generates properties, prints, and writes to formal/."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    project = _mk_project(tmp_path)
    rtl_path = project / "source" / "rtl" / "verilog" / "x.v"
    rtl_path.write_text("module m; endmodule", encoding="utf-8")
    monkeypatch.chdir(project)

    # Agents are constructed -> stub them
    monkeypatch.setattr(sut.AgentManager, "get_agent", lambda *a, **k: object(), raising=True)
    monkeypatch.setattr(sut, "run_with_review", lambda *a, **k: ("PROP_OUT", "ok"), raising=True)

    calls = []
    monkeypatch.setattr(sut, "write_output", lambda *a, **k: calls.append((a, k)) or "W", raising=True)

    res = _runner().invoke(sut.cli, ["fpropgen"])
    assert res.exit_code == 0 and "PROP_OUT" in res.output
    args, kw = calls[0]
    assert kw["default_folder"].endswith("formal")
    assert kw["ext"] == ".sv"


def test_cli_review_commands(tmp_path, monkeypatch, no_interactive_key_setup):
    """rtlreview / tbreview / fpropreview echo agent outputs."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    project = _mk_project(tmp_path)
    (project / "source" / "specification" / "design.md").write_text("SPEC", encoding="utf-8")
    rtl = project / "source" / "rtl" / "verilog" / "a.v"
    tb = project / "source" / "tb" / "verilog" / "b.v"
    prop = project / "formal" / "p.sv"
    rtl.write_text("module a; endmodule", encoding="utf-8")
    tb.write_text("module tb; endmodule", encoding="utf-8")
    prop.write_text("property p; endproperty", encoding="utf-8")
    monkeypatch.chdir(project)

    # Patch AgentManager.get_agent to return a simple echoing agent
    def _get_agent(name, verbose=False):
        return _AgentStub(result=f"{name}-OK")

    monkeypatch.setattr(sut.AgentManager, "get_agent", _get_agent, raising=True)

    r1 = _runner().invoke(sut.cli, ["rtlreview"])
    r2 = _runner().invoke(sut.cli, ["tbreview"])
    r3 = _runner().invoke(sut.cli, ["fpropreview"])
    assert "rtlreview-OK" in r1.output
    assert "tbreview-OK" in r2.output
    assert "fpropreview-OK" in r3.output


def test_cli_debug_happy(tmp_path, monkeypatch, no_interactive_key_setup):
    """debug prints header and agent result."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    p = _mk_project(tmp_path)
    f = p / "log.txt"
    f.write_text("E: fail", encoding="utf-8")
    monkeypatch.chdir(p)

    monkeypatch.setattr(sut.AgentManager, "get_agent", lambda n, verbose=False: _AgentStub("DBG"), raising=True)

    res = _runner().invoke(sut.cli, ["debug", "--input-file", str(f)])
    assert res.exit_code == 0
    assert "[Debug Report]" in res.output
    assert "DBG" in res.output


def test_cli_sim_happy(tmp_path, monkeypatch, no_interactive_key_setup):
    """sim prints status and optionally stdout/stderr/error."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    p = _mk_project(tmp_path)
    rtl = p / "source" / "rtl" / "verilog" / "r.v"
    tb = p / "source" / "tb" / "verilog" / "t.v"
    rtl.write_text("module r; endmodule", encoding="utf-8")
    tb.write_text("module t; endmodule", encoding="utf-8")
    monkeypatch.chdir(p)

    sim_result = {
        "status": "failed",
        "stdout": "STD",
        "stderr": "ERR",
        "error_message": "oops",
    }
    sim_agent = SimpleNamespace(run=lambda project_root, top: sim_result)
    monkeypatch.setattr(sut.AgentManager, "get_agent", lambda n, verbose=False: sim_agent, raising=True)

    res = _runner().invoke(
        sut.cli,
        ["sim", "-r", str(rtl.relative_to(p)), "-t", str(tb.relative_to(p)), "-m", "top"],
    )
    assert res.exit_code == 0
    assert "[Simulation Status]" in res.output
    assert "STD" in res.output and "ERR" in res.output and "oops" in res.output


def test_cli_fullpipeline_happy(tmp_path, monkeypatch, no_interactive_key_setup):
    """One spec in project: runs orchestrator, prints sections, and writes 4 files."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    proj = _mk_project(tmp_path)
    spec = proj / "source" / "specification" / "only.md"
    spec.write_text("S", encoding="utf-8")
    monkeypatch.chdir(proj)

    # Orchestrator returns final dict
    results = {
        "rtl_code": "R",
        "testbench_code": "T",
        "formal_properties": "P",
        "rtl_review_report": "RR",
        "tb_review_report": "TR",
        "fprop_review_report": "FR",
        "debug_report": "DR",
        "simulation_status": "success",
        "simulation_stdout": "",
        "simulation_stderr": "",
        "simulation_error_message": "",
        "pipeline_report": "SUM",
    }
    monkeypatch.setattr(sut.AgentOrchestrator, "full_pipeline", staticmethod(lambda *a, **k: results), raising=True)

    writes = []
    monkeypatch.setattr(sut, "write_output", lambda *a, **k: writes.append((a, k)) or "X", raising=True)

    res = _runner().invoke(sut.cli, ["fullpipeline"])
    assert res.exit_code == 0
    assert "[RTL Code]" in res.output and "R" in res.output
    assert "[Pipeline Summary Report]" in res.output and "SUM" in res.output
    # 4 writes: rtl, tb, props, report
    assert len(writes) == 4


def test_cli_rtlgen_missing_spec_dir_raises(tmp_path, monkeypatch, no_interactive_key_setup):
    """Missing project spec dir → unit project error with guidance."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    p = tmp_path
    (p / "source").mkdir()
    monkeypatch.chdir(p)

    res = _runner().invoke(sut.cli, ["rtlgen"])
    assert res.exit_code != 0
    assert "Not a SaxoFlow unit project" in res.output


def test_cli_setupkeys_calls_interactive(monkeypatch):
    """
    setupkeys command should call interactive flow with force=True.
    We record all calls (group pre-call with force=False, then command with True)
    and assert that at least one True happened.
    """
    from saxoflow_agenticai import cli as sut

    # NOTE: do NOT disable the group callback here—we want both calls recorded.
    calls: list[bool] = []
    monkeypatch.setattr(sut, "_interactive_setup_keys", lambda force=False: calls.append(force), raising=True)

    res = _runner().invoke(sut.cli, ["setupkeys"])
    assert res.exit_code == 0
    assert True in calls  # command invoked with force=True


def test_cli_testllms_lists_agents(monkeypatch, no_interactive_key_setup):
    """testllms prints mapping line per agent and success line when run() returns."""
    from saxoflow_agenticai import cli as sut
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # Patch get_agent to return a stub with run()
    def _get_agent(name, verbose=False):
        return SimpleNamespace(run=lambda input_data: f"{name}-OK")

    monkeypatch.setattr(sut.AgentManager, "get_agent", _get_agent, raising=True)

    # For every agent, provide a provider/model mapping
    monkeypatch.setattr(
        sut.ModelSelector,
        "get_provider_and_model",
        staticmethod(lambda agent_type=None: ("openai", "gpt-4o")),
        raising=True,
    )

    res = _runner().invoke(sut.cli, ["testllms"])
    assert res.exit_code == 0
    assert "Testing all agent LLM provider/model mappings" in res.output
    assert "[rtlgen] Using provider: openai, model: gpt-4o" in res.output
    assert "LLM test SUCCESS" in res.output

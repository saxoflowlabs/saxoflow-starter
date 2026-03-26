# saxoflow/ai/cli.py
"""
M4 AI Command Plane — canonical ``saxoflow ai`` Click group.

Provides five lifecycle verbs:

    saxoflow ai plan    [TARGET]       — draft an AI execution plan
    saxoflow ai run     ACTION [opts]  — run a tracked AI workflow
    saxoflow ai resume  RUN_ID         — resume a paused/failed run
    saxoflow ai explain [TARGET] [opts]— explain code (read-only)
    saxoflow ai review  --type TYPE    — review RTL / TB / formal

Design goals
------------
- Every operation creates/updates an :class:`~saxoflow.ai.contracts.AiRunRecord`
  in ``.saxoflow/ai_runs/``.
- High-impact actions (``sim``, ``fullpipeline``) require ``--yes`` before
  dispatching; without it the command exits with a clear error message.
- The ``_dispatch_*`` module-level functions are the seam for tests to
  monkeypatch without touching the CLI parser.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import click

from saxoflow.ai.contracts import (
    AiApprovalPolicy,
    AiLifecycleVerb,
    AiRunRecord,
    HIGH_IMPACT_ACTIONS,
)
from saxoflow.ai.run_store import list_runs, load_run, new_run_id, now_iso, save_run


# ---------------------------------------------------------------------------
# Runnable / reviewable / explainable action names
# ---------------------------------------------------------------------------

#: Actions accepted by ``saxoflow ai run``
RUNNABLE_ACTIONS = (
    "rtlgen",
    "tbgen",
    "fpropgen",
    "debug",
    "sim",
    "fullpipeline",
    "report",
)

#: Review target types accepted by ``saxoflow ai review``
REVIEW_TYPES = ("rtl", "tb", "formal")

#: Legacy agenticai → canonical mapping (used for deprecation hints).
AGENTICAI_CANONICAL_MAP: Dict[str, str] = {
    "rtlgen":     "saxoflow ai run rtlgen",
    "tbgen":      "saxoflow ai run tbgen",
    "fpropgen":   "saxoflow ai run fpropgen",
    "debug":      "saxoflow ai run debug",
    "sim":        "saxoflow ai run sim --yes",
    "fullpipeline": "saxoflow ai run fullpipeline --yes",
    "rtlreview":  "saxoflow ai review --type rtl",
    "tbreview":   "saxoflow ai review --type tb",
    "fpropreview":"saxoflow ai review --type formal",
    "setupkeys":  "saxoflow agenticai setupkeys",   # no canonical equivalent
    "testllms":   "saxoflow agenticai testllms",    # no canonical equivalent
}


# ---------------------------------------------------------------------------
# Dispatcher functions (monkeypatch seam for tests)
# ---------------------------------------------------------------------------

def _dispatch_run(action: str, **kwargs: Any) -> Dict[str, Any]:
    """Invoke an agenticai run action and return a structured output dict.

    This function is the thin bridge between the canonical CLI and the
    existing ``saxoflow_agenticai`` agent machinery.  Tests monkeypatch
    this to avoid LLM calls.

    Parameters
    ----------
    action:
        One of :data:`RUNNABLE_ACTIONS`.
    **kwargs:
        Forwarded CLI options (``input_file``, ``output_file``, ``iters``, …).

    Returns
    -------
    dict
        Structured output; at minimum ``{"status": "done" | "failed"}``.
    """
    if action == "report":
        return _dispatch_report(**kwargs)

    try:
        from saxoflow_agenticai.cli import cli as _agenticai_cli  # type: ignore
        from click.testing import CliRunner as _CliRunner
    except Exception as exc:
        raise RuntimeError(f"saxoflow_agenticai not available: {exc}") from exc

    args: list[str] = [action]
    if kwargs.get("input_file"):
        args += ["--input-file", str(kwargs["input_file"])]
    if kwargs.get("output_file"):
        args += ["--output-file", str(kwargs["output_file"])]
    if kwargs.get("iters") and action in ("rtlgen", "tbgen", "fpropgen"):
        args += ["--iters", str(kwargs["iters"])]
    if action == "sim":
        # sim requires --rtl-file, --tb-file, --top-module
        for flag, kw in [("--rtl-file", "rtl_file"), ("--tb-file", "tb_file"),
                         ("--top-module", "top_module")]:
            if kwargs.get(kw):
                args += [flag, str(kwargs[kw])]

    runner = _CliRunner()
    result = runner.invoke(_agenticai_cli, args, catch_exceptions=False, obj={})
    if result.exit_code != 0:
        raise RuntimeError(result.output or str(result.exception))
    return {"output": result.output, "status": "done"}


def _dispatch_review(review_type: str, **kwargs: Any) -> Dict[str, Any]:
    """Invoke an agenticai review command.

    Maps ``review_type`` → agenticai command name:
    - ``rtl``    → ``rtlreview``
    - ``tb``     → ``tbreview``
    - ``formal`` → ``fpropreview``
    """
    try:
        from saxoflow_agenticai.cli import cli as _agenticai_cli  # type: ignore
        from click.testing import CliRunner as _CliRunner
    except Exception as exc:
        raise RuntimeError(f"saxoflow_agenticai not available: {exc}") from exc

    cmd_map = {"rtl": "rtlreview", "tb": "tbreview", "formal": "fpropreview"}
    cmd = cmd_map[review_type]
    args: list[str] = [cmd]
    if kwargs.get("input_file"):
        args += ["--input-file", str(kwargs["input_file"])]

    runner = _CliRunner()
    result = runner.invoke(_agenticai_cli, args, catch_exceptions=False, obj={})
    if result.exit_code != 0:
        raise RuntimeError(result.output or str(result.exception))
    return {"output": result.output, "status": "done"}


def _dispatch_explain(target: Optional[str], **kwargs: Any) -> Dict[str, Any]:
    """Explain a file (read-only); delegates to the ``debug`` agent."""
    try:
        from saxoflow_agenticai.cli import cli as _agenticai_cli  # type: ignore
        from click.testing import CliRunner as _CliRunner
    except Exception as exc:
        raise RuntimeError(f"saxoflow_agenticai not available: {exc}") from exc

    input_file = kwargs.get("input_file") or target
    if not input_file:
        raise RuntimeError("No target file specified for explain.")
    args = ["debug", "--input-file", str(input_file)]

    runner = _CliRunner()
    result = runner.invoke(_agenticai_cli, args, catch_exceptions=False, obj={})
    if result.exit_code != 0:
        raise RuntimeError(result.output or str(result.exception))
    return {"output": result.output, "status": "done"}


def _dispatch_resume(run_id: str, **kwargs: Any) -> bool:
    """Load a previously saved run and re-dispatch it.

    Currently re-invokes the same ``run`` action with the same parameters
    saved in the record's ``outputs`` metadata.
    """
    workspace = str(Path.cwd())
    record = load_run(run_id, workspace=workspace)
    if record is None:
        raise click.ClickException(
            f"Run '{run_id}' not found in workspace {workspace}."
        )
    if record.status == "done":
        click.secho(f"[AI] Run {run_id} has already completed (status: done).", fg="yellow")
        return False
    # Re-dispatch the original action
    _dispatch_run(record.action, **(record.outputs.get("_kwargs", {})))
    return True


def _load_report_dependencies() -> Tuple[Any, Callable[..., str], Callable[[str], str]]:
    try:
        from saxoflow_agenticai.agents.generators.report_agent import ReportAgent  # type: ignore
        from saxoflow_agenticai.utils.file_utils import base_name_from_path, write_output  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"report dependencies unavailable: {exc}") from exc
    return ReportAgent, write_output, base_name_from_path


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _resolve_first_workspace_file(workspace: Path, candidates: Sequence[str]) -> Optional[Path]:
    for candidate in candidates:
        if any(token in candidate for token in "*?[]"):
            matches = sorted(path for path in workspace.glob(candidate) if path.is_file())
            if matches:
                return matches[0]
            continue
        path = workspace / candidate
        if path.is_file():
            return path
    return None


def _collect_report_phase_outputs(
    workspace: Path,
    input_file: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    artifact_candidates = {
        "specification": [
            "source/specification/*.md",
            "source/specification/*.txt",
        ],
        "rtl_code": [
            "source/rtl/verilog/*.sv",
            "source/rtl/verilog/*.v",
            "source/rtl/verilog/*.svh",
            "source/rtl/verilog/*.vh",
        ],
        "testbench_code": [
            "source/tb/verilog/*.sv",
            "source/tb/verilog/*.v",
            "source/tb/verilog/*.svh",
            "source/tb/verilog/*.vh",
        ],
        "formal_properties": [
            "formal/*.sv",
            "formal/*.sva",
            "formal/*.v",
            "formal/*.txt",
        ],
        "rtl_review_report": [
            "output/report/rtl_review_report.md",
            "output/report/rtl_review_report.txt",
        ],
        "testbench_review_report": [
            "output/report/testbench_review_report.md",
            "output/report/testbench_review_report.txt",
            "output/report/tb_review_report.md",
            "output/report/tb_review_report.txt",
        ],
        "formal_property_review_report": [
            "output/report/formal_property_review_report.md",
            "output/report/formal_property_review_report.txt",
            "output/report/fprop_review_report.md",
            "output/report/fprop_review_report.txt",
        ],
        "simulation_status": [
            "output/report/simulation_status.txt",
            "output/report/simulation_status.md",
        ],
        "simulation_stdout": [
            "output/report/simulation_stdout.txt",
            "output/report/simulation_stdout.log",
        ],
        "simulation_stderr": [
            "output/report/simulation_stderr.txt",
            "output/report/simulation_stderr.log",
        ],
        "simulation_error_message": [
            "output/report/simulation_error_message.txt",
            "output/report/simulation_error_message.log",
        ],
        "debug_report": [
            "output/report/debug_report.md",
            "output/report/debug_report.txt",
        ],
    }

    phase_outputs: Dict[str, str] = {}
    artifact_paths: Dict[str, str] = {}

    spec_path: Optional[Path] = None
    if input_file:
        candidate = Path(input_file)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        if candidate.is_file():
            spec_path = candidate
    if spec_path is None:
        spec_path = _resolve_first_workspace_file(workspace, artifact_candidates["specification"])
    if spec_path is not None:
        phase_outputs["specification"] = _read_text_file(spec_path)
        artifact_paths["specification"] = str(spec_path)
    else:
        phase_outputs["specification"] = ""

    for key, candidates in artifact_candidates.items():
        if key == "specification":
            continue
        path = _resolve_first_workspace_file(workspace, candidates)
        if path is None:
            phase_outputs[key] = ""
            continue
        phase_outputs[key] = _read_text_file(path)
        artifact_paths[key] = str(path)

    return phase_outputs, artifact_paths


def _dispatch_report(
    input_file: Optional[str] = None,
    output_file: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    ReportAgent, write_output, base_name_from_path = _load_report_dependencies()
    workspace = Path.cwd()
    phase_outputs, artifact_paths = _collect_report_phase_outputs(workspace, input_file=input_file)
    report_text = ReportAgent().run(phase_outputs)

    base_source = artifact_paths.get("specification") or input_file or "pipeline"
    report_path = write_output(
        report_text,
        output_file,
        workspace / "output" / "report",
        f"{base_name_from_path(base_source)}_pipeline_report",
        ".txt",
    )
    return {
        "output": report_text,
        "report_path": str(report_path),
        "artifacts": artifact_paths,
        "status": "done",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_run_record(verb: AiLifecycleVerb, action: str) -> AiRunRecord:
    return AiRunRecord(
        run_id=new_run_id(),
        verb=verb,
        action=action,
        workspace=str(Path.cwd()),
        started_at=now_iso(),
        status="running",
    )


def _enforce_approval(record: AiRunRecord, yes: bool) -> None:
    """Raise :class:`click.ClickException` for high-impact actions without ``--yes``."""
    if record.is_high_impact() and not yes:
        raise click.ClickException(
            f"Action '{record.action}' is a high-impact operation.\n"
            "Re-run with --yes to confirm:\n"
            f"  saxoflow ai run {record.action} --yes"
        )


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------

@click.group("ai")
def ai_group() -> None:
    """AI Command Plane — canonical lifecycle commands for AI-assisted EDA flows.

    \b
    Lifecycle verbs:
      plan     Analyze spec / project and output an AI execution plan.
      run      Run a tracked AI workflow (rtlgen, tbgen, fpropgen, sim, fullpipeline, debug).
      resume   Resume a paused or failed AI run by run ID.
      explain  Explain existing RTL / testbench / log (read-only).
      review   Review an artifact for quality and correctness.

    All operations are tracked with a run ID under .saxoflow/ai_runs/.
    """


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

@ai_group.command("plan")
@click.argument("target", required=False)
@click.option("--input-file", "-i", type=click.Path(), default=None,
              help="Spec or RTL file to plan against.")
def plan_cmd(target: Optional[str], input_file: Optional[str]) -> None:
    """Analyze a spec or project and output an AI execution plan.

    TARGET is an optional action hint (e.g. ``rtlgen``, ``tbgen``).
    When omitted the plan is derived from the workspace spec directory.
    """
    record = _make_run_record(AiLifecycleVerb.PLAN, target or "plan")
    click.secho(f"[AI] Run ID: {record.run_id}", fg="cyan")
    click.secho(
        f"[AI] plan — analyzing workspace '{record.workspace}'…",
        fg="yellow",
    )

    # Emit a human-readable plan based on target
    _target = target or "full_pipeline"
    _plan_text = _build_plan_text(_target, input_file)
    click.echo(_plan_text)

    record.status = "done"
    record.outputs = {"plan": _plan_text}
    record.ended_at = now_iso()
    save_run(record, workspace=record.workspace)
    click.secho(f"[AI] Run {record.run_id} saved.", fg="green")


def _build_plan_text(target: str, input_file: Optional[str]) -> str:
    _PLANS = {
        "rtlgen":  "Step 1: parse spec → Step 2: generate RTL → Step 3: review RTL",
        "tbgen":   "Step 1: parse RTL → Step 2: generate testbench → Step 3: review TB",
        "fpropgen":"Step 1: parse RTL → Step 2: generate SVA properties → Step 3: review props",
        "sim":     "Step 1: run simulation → Step 2: check status",
        "report":  "Step 1: gather pipeline artifacts → Step 2: summarize outcomes → Step 3: write report",
        "full_pipeline": (
            "Step 1: rtlgen → Step 2: tbgen → Step 3: fpropgen → "
            "Step 4: sim → Step 5: report"
        ),
    }
    plan = _PLANS.get(target, f"Plan for '{target}': analyze → generate → review")
    if input_file:
        plan = f"Input: {input_file}\n{plan}"
    return plan


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@ai_group.command("run")
@click.argument("action", type=click.Choice(RUNNABLE_ACTIONS, case_sensitive=False))
@click.option("--input-file", "-i", type=click.Path(), default=None,
              help="Input file (spec for rtlgen; RTL for tbgen/fpropgen).")
@click.option("--output-file", "-o", type=click.Path(), default=None,
              help="Output file path override.")
@click.option("--iters", default=1, show_default=True,
              help="Max review-improve iterations.")
@click.option("--yes", is_flag=True, default=False,
              help="Approve high-impact operation (required for sim/fullpipeline).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Parse arguments and show approval status without running.")
def run_cmd(
    action: str,
    input_file: Optional[str],
    output_file: Optional[str],
    iters: int,
    yes: bool,
    dry_run: bool,
) -> None:
    """Run a named AI workflow, tracked with a run ID.

    \b
    Available actions:
      rtlgen       Generate RTL from a spec.
      tbgen        Generate a testbench for RTL.
      fpropgen     Generate SVA formal properties.
      debug        AI-assisted debug of a file or log.
      sim          Run simulation (high-impact: requires --yes).
      report       Summarize current pipeline artifacts into a report.
      fullpipeline Run the full AI pipeline (high-impact: requires --yes).
    """
    record = _make_run_record(AiLifecycleVerb.RUN, action)
    click.secho(f"[AI] Run ID: {record.run_id}", fg="cyan")

    run_kwargs = {
        "input_file": input_file,
        "output_file": output_file,
        "iters": iters,
    }

    # Enforce approval gate
    _enforce_approval(record, yes)

    if dry_run:
        click.secho(
            f"[AI] dry-run — action '{action}' approved. No changes made.",
            fg="yellow",
        )
        record.status = "done"
        record.outputs = {"dry_run": True, "_kwargs": run_kwargs}
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        return

    click.secho(f"[AI] Dispatching '{action}'…", fg="yellow")
    try:
        result = _dispatch_run(
            action,
            **run_kwargs,
        )
        record.status = "done"
        record.outputs = {**result, "_kwargs": run_kwargs}
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        click.secho(f"[AI] Run {record.run_id} completed.", fg="green")
    except Exception as exc:
        record.status = "failed"
        record.outputs = {"_kwargs": run_kwargs}
        record.error = str(exc)
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        raise click.ClickException(str(exc)) from exc


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------

@ai_group.command("resume")
@click.argument("run_id")
def resume_cmd(run_id: str) -> None:
    """Resume a paused or failed AI run by its run ID.

    RUN_ID is the 12-char hex identifier printed when a run is created.
    Accepts both ``abc123`` and ``abc123.json`` (from ``ls .saxoflow/ai_runs/``).
    """
    # Accept filenames pasted from `ls .saxoflow/ai_runs/` output.
    if run_id.endswith(".json"):
        run_id = run_id[:-5]
    click.secho(f"[AI] Resuming run {run_id}…", fg="yellow")
    try:
        resumed = _dispatch_resume(run_id)
        if resumed:
            click.secho(f"[AI] Run {run_id} resumed.", fg="green")
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

@ai_group.command("explain")
@click.argument("target", required=False)
@click.option("--input-file", "-i", type=click.Path(), default=None,
              help="File to explain (RTL, testbench, or log).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Parse arguments without dispatching.")
def explain_cmd(target: Optional[str], input_file: Optional[str], dry_run: bool) -> None:
    """Explain existing RTL, testbench, or simulation log (read-only).

    TARGET is an optional filename shorthand; use --input-file for explicit paths.
    """
    effective_file = input_file or target
    record = _make_run_record(AiLifecycleVerb.EXPLAIN, effective_file or "explain")
    click.secho(f"[AI] Run ID: {record.run_id}", fg="cyan")

    if dry_run:
        click.secho(
            f"[AI] dry-run — explain '{effective_file}'. No changes made.",
            fg="yellow",
        )
        record.status = "done"
        record.outputs = {"dry_run": True}
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        return

    try:
        result = _dispatch_explain(target, input_file=input_file)
        record.status = "done"
        record.outputs = result
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        click.secho(f"[AI] Run {record.run_id} completed.", fg="green")
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        raise click.ClickException(str(exc)) from exc


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

@ai_group.command("review")
@click.option(
    "--type", "review_type",
    type=click.Choice(REVIEW_TYPES, case_sensitive=False),
    required=True,
    help="Type of artifact to review: rtl | tb | formal.",
)
@click.option("--input-file", "-i", type=click.Path(), default=None,
              help="File to review.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Parse arguments without dispatching.")
def review_cmd(review_type: str, input_file: Optional[str], dry_run: bool) -> None:
    """Review an RTL, testbench, or formal property file for quality.

    \b
    Types:
      rtl     Review an RTL / Verilog / SystemVerilog file.
      tb      Review a testbench file.
      formal  Review SVA formal property files.
    """
    record = _make_run_record(AiLifecycleVerb.REVIEW, review_type)
    click.secho(f"[AI] Run ID: {record.run_id}", fg="cyan")

    if dry_run:
        click.secho(
            f"[AI] dry-run — review '{review_type}'. No changes made.",
            fg="yellow",
        )
        record.status = "done"
        record.outputs = {"dry_run": True}
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        return

    try:
        result = _dispatch_review(review_type, input_file=input_file)
        record.status = "done"
        record.outputs = result
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        click.secho(f"[AI] Run {record.run_id} completed.", fg="green")
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
        record.ended_at = now_iso()
        save_run(record, workspace=record.workspace)
        raise click.ClickException(str(exc)) from exc

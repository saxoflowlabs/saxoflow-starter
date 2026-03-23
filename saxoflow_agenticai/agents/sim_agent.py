from __future__ import annotations

"""
Simulation agent.

Runs the SaxoFlow CLI simulation (`saxoflow.makeflow.sim`) inside a target
project directory and returns a structured result dict. Stdout/stderr are
captured, the process exit code is checked, and the presence of a VCD file is
validated for success.

Public API (kept stable)
------------------------
- class SimAgent
    - run(project_path: str, top_module: str) -> dict

Notes
-----
- We intentionally keep Click's `CliRunner().invoke(...)` usage to preserve
  current behavior and compatibility with the rest of the pipeline.
- Output keys: "status", "stage", "stdout", "stderr", "error_message".

Python: 3.9+
"""

import os
import re
# import subprocess  # Unused: kept for reference in case we switch to Popen-based runs.  # noqa: ERA001
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Dict, Iterator, Tuple

from saxoflow_agenticai.core.log_manager import get_logger

logger = get_logger()

_RUNTIME_FAIL_PATTERNS = (
    re.compile(r"\bTESTS\s+FAILED\b", re.IGNORECASE),
    re.compile(r"\bASSERT(?:ION)?\s+FAILED\b", re.IGNORECASE),
)

_COMPILE_FAIL_LINE_PATTERNS = (
    re.compile(r"\berror:\b", re.IGNORECASE),
    re.compile(r"\bsyntax\s+error\b", re.IGNORECASE),
    re.compile(r"\bundeclared\b", re.IGNORECASE),
    re.compile(r"\bunknown\s+module\b", re.IGNORECASE),
    re.compile(r"\btoo\s+many\s+port\b", re.IGNORECASE),
    re.compile(r"\btoo\s+few\s+port\b", re.IGNORECASE),
    re.compile(r"\bwidth\s+mismatch\b", re.IGNORECASE),
)

_RUNTIME_FAIL_LINE_PATTERNS = (
    re.compile(r"\bTEST\b.*\bFAILED\b", re.IGNORECASE),
    re.compile(r"\bASSERT(?:ION)?\b.*\bFAILED\b", re.IGNORECASE),
    re.compile(r"\bERROR\b", re.IGNORECASE),
    re.compile(r"\berror_count\b", re.IGNORECASE),
)

_ENV_FAIL_LINE_PATTERNS = (
    re.compile(r"command\s+not\s+found", re.IGNORECASE),
    re.compile(r"permission\s+denied", re.IGNORECASE),
    re.compile(r"no\s+such\s+file\s+or\s+directory", re.IGNORECASE),
)


def _collect_evidence_lines(text: str, patterns, limit: int = 8) -> list[str]:
    """Collect short evidence lines matching `patterns`, capped by `limit`."""
    hits: list[str] = []
    for line in (text or "").splitlines():
        if any(p.search(line) for p in patterns):
            cleaned = line.strip()
            if cleaned:
                hits.append(cleaned)
        if len(hits) >= limit:
            break
    return hits


def _derive_suggested_agents(
    compile_hits: list[str],
    runtime_hits: list[str],
    env_hits: list[str],
    error_message: str,
) -> list[str]:
    """Heuristically map failure evidence to corrective agent suggestions."""
    suggestions: list[str] = []
    low_err = (error_message or "").lower()

    if env_hits:
        suggestions.append("UserAction")

    if compile_hits:
        # Compile/elaboration failures can originate in either DUT or TB wiring.
        suggestions.extend(["RTLGenAgent", "TBGenAgent"])

    if runtime_hits:
        # Runtime checks failing typically require TB + RTL inspection.
        suggestions.extend(["TBGenAgent", "RTLGenAgent"])

    if "vcd" in low_err and "not produce" in low_err:
        suggestions.append("TBGenAgent")

    if not suggestions:
        suggestions.extend(["RTLGenAgent", "TBGenAgent"])

    # Preserve order while deduplicating.
    return list(dict.fromkeys(suggestions))


def _build_failure_manifest(sim_stdout: str, sim_stderr: str, error_message: str) -> str:
    """Build a compact, machine-readable failure manifest for downstream agents."""
    compile_hits = _collect_evidence_lines(
        f"{sim_stderr}\n{sim_stdout}",
        _COMPILE_FAIL_LINE_PATTERNS,
    )
    runtime_hits = _collect_evidence_lines(
        f"{sim_stdout}\n{sim_stderr}",
        _RUNTIME_FAIL_LINE_PATTERNS,
    )
    env_hits = _collect_evidence_lines(
        f"{sim_stderr}\n{sim_stdout}",
        _ENV_FAIL_LINE_PATTERNS,
    )
    suggested_agents = _derive_suggested_agents(
        compile_hits, runtime_hits, env_hits, error_message
    )

    sections: list[str] = [
        "SIM_FAILURE_MANIFEST",
        f"error_message: {error_message or 'N/A'}",
        "suggested_agents: " + ", ".join(suggested_agents),
    ]

    if compile_hits:
        sections.append("compile_evidence:")
        sections.extend([f"- {line}" for line in compile_hits])

    if runtime_hits:
        sections.append("runtime_evidence:")
        sections.extend([f"- {line}" for line in runtime_hits])

    if env_hits:
        sections.append("environment_evidence:")
        sections.extend([f"- {line}" for line in env_hits])

    if not (compile_hits or runtime_hits or env_hits):
        sections.append("evidence: no specific signature matched; inspect full sim_stdout/sim_stderr")

    return "\n".join(sections)


@contextmanager
def _pushd(target: Path) -> Iterator[None]:
    """
    Temporarily change the current working directory.

    Parameters
    ----------
    target : Path
        Directory to enter for the duration of the context.

    Yields
    ------
    None
    """
    prev = Path.cwd()
    os.chdir(str(target))
    try:
        yield
    finally:
        os.chdir(str(prev))


@contextmanager
def _capture_stdio() -> Iterator[Tuple[StringIO, StringIO]]:
    """
    Temporarily redirect `sys.stdout` and `sys.stderr` to in-memory buffers.

    Returns
    -------
    tuple[StringIO, StringIO]
        (stdout_buffer, stderr_buffer)
    """
    old_out, old_err = sys.stdout, sys.stderr
    out_buf, err_buf = StringIO(), StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        yield out_buf, err_buf
    finally:
        sys.stdout, sys.stderr = old_out, old_err


class SimAgent:
    """Thin wrapper around the SaxoFlow simulation CLI."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        verbose : bool, default False
            Currently unused here (logging already informative), but kept for
            API parity with other agents.
        """
        self.name = "sim"
        self.verbose = bool(verbose)

    def run(self, project_path: str, top_module: str) -> Dict[str, object]:
        """
        Simulate the given design using SaxoFlow's CLI (Icarus flow).

        Parameters
        ----------
        project_path : str
            Path to the SaxoFlow project root (contains source/, simulation/, etc.).
        top_module : str
            Top-level module name (used to guess VCD filename and passed to CLI).

        Returns
        -------
        dict
            {
                "status": "success" | "failed",
                "stage": "simulation",
                "stdout": <captured stdout>,
                "stderr": <captured stderr>,
                "error_message": str | None,
            }

        Behavior
        --------
        - Invokes `saxoflow.makeflow.sim --tb <top_module>` in the given project dir.
        - Considers the run failed if the exit code is non-zero.
        - Considers the run failed if no non-empty VCD file is produced at
          `simulation/icarus/<top_module>.vcd` or `simulation/icarus/dump.vcd`.
        """
        logger.info("[%s] Running simulation for top module: %s", self.name, top_module)
        logger.info(
            "[%s] Running simulation for top module: %s in project: %s",
            self.name,
            top_module,
            project_path,
        )

        # Import locally to avoid any circular import issues.
        try:
            from saxoflow.makeflow import sim as saxoflow_sim  # type: ignore
        except Exception as exc:  # pragma: no cover - import resolution issue
            logger.error("[%s] Failed to import SaxoFlow sim entrypoint: %s", self.name, exc)
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": "",
                "stderr": "",
                "error_message": f"Failed to import SaxoFlow sim entrypoint: {exc}",
                "failure_manifest": _build_failure_manifest(
                    "",
                    "",
                    f"Failed to import SaxoFlow sim entrypoint: {exc}",
                ),
            }

        project_dir = Path(project_path)
        if not project_dir.exists():
            logger.error("[%s] Project path does not exist: %s", self.name, project_dir)
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": "",
                "stderr": "",
                "error_message": f"Project path does not exist: {project_dir}",
                "failure_manifest": _build_failure_manifest(
                    "",
                    "",
                    f"Project path does not exist: {project_dir}",
                ),
            }

        # Run the CLI inside the project directory while capturing stdout/stderr.
        with _pushd(project_dir), _capture_stdio() as (stdout_buf, stderr_buf):
            try:
                from click.testing import CliRunner

                runner = CliRunner()
                result = runner.invoke(saxoflow_sim, ["--tb", top_module])  # type: ignore[name-defined]

                sim_stdout = stdout_buf.getvalue()
                sim_stderr = stderr_buf.getvalue()
                runner_output = str(getattr(result, "output", "") or "")
                if runner_output:
                    if sim_stdout and not sim_stdout.endswith("\n"):
                        sim_stdout += "\n"
                    sim_stdout += runner_output
                return_code = int(result.exit_code)
            except Exception as exc:  # pragma: no cover - Click/CLI unexpected failure
                logger.error("[%s] Exception during simulation: %s", self.name, exc)
                return {
                    "status": "failed",
                    "stage": "simulation",
                    "stdout": stdout_buf.getvalue(),
                    "stderr": stderr_buf.getvalue(),
                    "error_message": f"An unexpected error occurred: {exc}",
                    "failure_manifest": _build_failure_manifest(
                        stdout_buf.getvalue(),
                        stderr_buf.getvalue(),
                        f"An unexpected error occurred: {exc}",
                    ),
                }

        # ------ Post-run checks (preserve existing behavior) ------
        # Heuristic: confirm at least one non-empty VCD exists.
        # IMPORTANT: Resolve against project directory (not restored CWD).
        vcd_dir = project_dir / "simulation" / "icarus"
        vcd_paths = [p for p in sorted(vcd_dir.glob("*.vcd")) if p.is_file()]

        found_vcd: Path | None = None
        for vcd_path in vcd_paths:
            try:
                if vcd_path.exists() and vcd_path.stat().st_size > 0:
                    found_vcd = vcd_path
                    break
            except OSError:  # pragma: no cover - rare FS error
                # Keep searching; we only need *one* valid VCD.
                continue

        if return_code != 0:
            logger.error(
                "[%s] SaxoFlow simulation failed with exit code %s.",
                self.name,
                return_code,
            )
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": sim_stdout,
                "stderr": sim_stderr,
                "error_message": (
                    f"SaxoFlow simulation failed with exit code {return_code}."
                ),
                "failure_manifest": _build_failure_manifest(
                    sim_stdout,
                    sim_stderr,
                    f"SaxoFlow simulation failed with exit code {return_code}.",
                ),
            }

        if not found_vcd:
            logger.error(
                "[%s] Simulation did NOT complete: No VCD file found in simulation/icarus/ "
                "after simulation run.",
                self.name,
            )
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": sim_stdout,
                "stderr": sim_stderr,
                "error_message": (
                    "Simulation did not produce a VCD file. "
                    "Check your testbench and RTL for errors, or missing $dumpfile/$dumpvars."
                ),
                "failure_manifest": _build_failure_manifest(
                    sim_stdout,
                    sim_stderr,
                    "Simulation did not produce a VCD file. "
                    "Check your testbench and RTL for errors, or missing $dumpfile/$dumpvars.",
                ),
            }

        combined_output = f"{sim_stdout}\n{sim_stderr}"
        for pat in _RUNTIME_FAIL_PATTERNS:
            if pat.search(combined_output):
                logger.error(
                    "[%s] Simulation completed but testbench reported failures.",
                    self.name,
                )
                return {
                    "status": "failed",
                    "stage": "simulation",
                    "stdout": sim_stdout,
                    "stderr": sim_stderr,
                    "error_message": (
                        "Simulation run completed, but testbench reported failures "
                        "(e.g., TESTS FAILED / ASSERTION FAILED)."
                    ),
                    "failure_manifest": _build_failure_manifest(
                        sim_stdout,
                        sim_stderr,
                        "Simulation run completed, but testbench reported failures "
                        "(e.g., TESTS FAILED / ASSERTION FAILED).",
                    ),
                }

        logger.info("[%s] Simulation completed successfully. VCD: %s", self.name, found_vcd)
        return {
            "status": "success",
            "stage": "simulation",
            "stdout": sim_stdout,
            "stderr": sim_stderr,
            "error_message": None,
            "failure_manifest": "",
        }

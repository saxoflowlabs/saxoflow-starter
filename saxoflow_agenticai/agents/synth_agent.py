from __future__ import annotations

"""Synthesis tool agent (Yosys via SaxoFlow CLI).

Goal
----
Wrap the existing Click command `saxoflow.makeflow.synth` so the agentic
pipeline can run synthesis like any other step and get a structured result.

This should mirror the style of `SimAgent`:
- Run inside a project directory
- Use Click's `CliRunner().invoke(...)`
- Capture stdout/stderr
- Check exit code
- Validate expected artifacts under synthesis/

Public API
----------
- class SynthAgent
    - run(project_path: str) -> dict

Output dict keys (stable)
------------------------
- status: "success" | "failed"
- stage: "synthesis"
- stdout: str
- stderr: str
- error_message: str | None
- failure_manifest: str

Python: 3.9+
"""

import os
import re
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Dict, Iterator, Tuple

from saxoflow_agenticai.core.log_manager import get_logger

logger = get_logger()


_FAIL_LINE_PATTERNS = (
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bfatal\b", re.IGNORECASE),
    re.compile(r"\bsyntax\s+error\b", re.IGNORECASE),
    re.compile(r"\bnot\s+found\b", re.IGNORECASE),
    re.compile(r"command\s+not\s+found", re.IGNORECASE),
)


def _collect_evidence_lines(text: str, patterns, limit: int = 10) -> list[str]:
    hits: list[str] = []
    for line in (text or "").splitlines():
        if any(p.search(line) for p in patterns):
            cleaned = line.strip()
            if cleaned:
                hits.append(cleaned)
        if len(hits) >= limit:
            break
    return hits


def _fail(msg: str, *, stdout: str = "", stderr: str = "") -> Dict[str, object]:
    """Build a stable failure result dict for this tool agent."""
    evidence = _collect_evidence_lines(f"{stderr}\n{stdout}", _FAIL_LINE_PATTERNS)
    manifest = ["stage: synthesis", f"error_message: {msg}"]
    if evidence:
        manifest.append("evidence:")
        manifest.extend([f"- {ln}" for ln in evidence])
    return {
        "status": "failed",
        "stage": "synthesis",
        "stdout": stdout,
        "stderr": stderr,
        "error_message": msg,
        "failure_manifest": "\n".join(manifest).strip() + "\n",
    }


@contextmanager
def _pushd(target: Path) -> Iterator[None]:
    prev = Path.cwd()
    os.chdir(str(target))
    try:
        yield
    finally:
        os.chdir(str(prev))


@contextmanager
def _capture_stdio() -> Iterator[Tuple[StringIO, StringIO]]:
    old_out, old_err = sys.stdout, sys.stderr
    out_buf, err_buf = StringIO(), StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        yield out_buf, err_buf
    finally:
        sys.stdout, sys.stderr = old_out, old_err


def _find_synth_artifacts(project_dir: Path) -> Tuple[list[Path], list[Path]]:
    """Return (reports, outputs) found under synthesis/."""
    rep_dir = project_dir / "synthesis" / "reports"
    out_dir = project_dir / "synthesis" / "out"

    reports = [p for p in sorted(rep_dir.glob("*")) if p.is_file()]
    outputs: list[Path] = []
    for ext in ("*.json", "*.edif", "*.blif"):
        outputs.extend([p for p in sorted(out_dir.glob(ext)) if p.is_file()])
    return reports, outputs


class SynthAgent:
    """Wrapper around `saxoflow.makeflow.synth` (non-LLM tool agent)."""

    def __init__(self, verbose: bool = False) -> None:
        self.name = "synth"
        self.verbose = bool(verbose)

    def run(self, project_path: str) -> Dict[str, object]:
        """Run synthesis inside the given project directory.

        Implemented in the next steps (invoke Click command, capture I/O, check artifacts).
        """
        logger.info("[%s] Running synthesis in project: %s", self.name, project_path)

        # Import locally to avoid circular imports (and to keep this module import-safe).
        try:
            from saxoflow.makeflow import synth as saxoflow_synth  # type: ignore
        except Exception as exc:
            return _fail(f"Failed to import SaxoFlow synth entrypoint: {exc}")

        project_dir = Path(project_path)
        if not _project_exists(project_dir):
            return _fail(f"Project path does not exist: {project_dir}")

        # Run the Click command inside the project directory, capturing stdio.
        with _pushd(project_dir), _capture_stdio() as (stdout_buf, stderr_buf):
            try:
                from click.testing import CliRunner

                runner = CliRunner()
                result = runner.invoke(saxoflow_synth, [])  # type: ignore[arg-type]

                synth_stdout = stdout_buf.getvalue()
                synth_stderr = stderr_buf.getvalue()
                runner_output = str(getattr(result, "output", "") or "")
                if runner_output:
                    if synth_stdout and not synth_stdout.endswith("\n"):
                        synth_stdout += "\n"
                    synth_stdout += runner_output

                return_code = int(result.exit_code)
            except Exception as exc:
                msg = f"An unexpected error occurred: {exc}"
                return _fail(msg, stdout=stdout_buf.getvalue(), stderr=stderr_buf.getvalue())

        if return_code != 0:
            return _fail(
                f"SaxoFlow synthesis failed with exit code {return_code}.",
                stdout=synth_stdout,
                stderr=synth_stderr,
            )

        reports, outputs = _find_synth_artifacts(project_dir)
        if not reports and not outputs:
            return _fail(
                "Synthesis exited successfully, but no artifacts were found under "
                "synthesis/reports or synthesis/out.",
                stdout=synth_stdout,
                stderr=synth_stderr,
            )

        return {
            "status": "success",
            "stage": "synthesis",
            "stdout": synth_stdout,
            "stderr": synth_stderr,
            "error_message": None,
            "failure_manifest": "",
        }


def _project_exists(project_dir: Path) -> bool:
    """Small helper so we can unit test path handling cleanly."""
    return project_dir.exists()

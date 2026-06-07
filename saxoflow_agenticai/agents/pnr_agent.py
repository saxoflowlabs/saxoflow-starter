"""Non-LLM tool agent for SaxoFlow physical-design stages."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Sequence

from click.testing import CliRunner

from saxoflow_agenticai.core.log_manager import get_logger

logger = get_logger()
STAGES = {
    "run",
    "floorplan",
    "place",
    "cts",
    "route",
    "finish",
    "status",
    "report",
    "gui",
    "diagnose",
    "pdk-list",
    "pdk-info",
    "pdk-install",
    "pdk-verify",
    "pdk-diagnose",
}
CONFIGURATION_OPTIONS = {
    "--platform",
    "--library",
    "--corner",
    "--top",
    "--netlist",
    "--sdc",
    "--synthesize",
    "--rtl",
    "--include",
    "--define",
    "--param",
    "--clock-port",
    "--clock-period",
    "--utilization",
    "--aspect-ratio",
    "--core-margin",
    "--die-area",
    "--core-area",
    "--place-density",
    "--min-routing-layer",
    "--max-routing-layer",
    "--set",
    "--unsafe-netlist",
}
FAILURE_RE = re.compile(r"\b(error|fatal|failed|violation)\b", re.IGNORECASE)


@contextmanager
def _pushd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _failure(stage: str, message: str, output: str = "") -> Dict[str, object]:
    evidence = [
        line.strip()
        for line in output.splitlines()
        if line.strip() and FAILURE_RE.search(line)
    ][:12]
    manifest = [f"stage: pnr/{stage}", f"error_message: {message}"]
    if evidence:
        manifest.append("evidence:")
        manifest.extend(f"- {line}" for line in evidence)
    return {
        "status": "failed",
        "stage": f"pnr/{stage}",
        "stdout": output,
        "stderr": "",
        "error_message": message,
        "failure_manifest": "\n".join(manifest) + "\n",
    }


class PnrAgent:
    """Invoke one registered `saxoflow pnr` stage inside a unit project."""

    def __init__(self, verbose: bool = False) -> None:
        self.name = "pnr"
        self.verbose = bool(verbose)

    def run(
        self,
        project_path: str,
        stage: str = "run",
        arguments: Sequence[str] = (),
        allow_configuration_change: bool = False,
    ) -> Dict[str, object]:
        project = Path(project_path)
        if not project.is_dir():
            return _failure(stage, f"Project path does not exist: {project}")
        if stage not in STAGES:
            return _failure(stage, f"Unsupported P&R stage: {stage}")
        supplied_options = {
            argument.split("=", 1)[0]
            for argument in arguments
            if argument.startswith("--")
        }
        protected = sorted(supplied_options & CONFIGURATION_OPTIONS)
        if protected and not allow_configuration_change:
            return _failure(
                stage,
                "Agent P&R actions use the locked project configuration. "
                "Explicit user confirmation is required before changing: "
                + ", ".join(protected),
            )
        if stage == "pdk-install" and not allow_configuration_change:
            return _failure(
                stage,
                "PDK installation requires explicit user confirmation and license "
                "acceptance.",
            )
        if stage not in {
            "diagnose",
            "status",
            "report",
            "pdk-list",
            "pdk-info",
            "pdk-install",
            "pdk-verify",
            "pdk-diagnose",
        }:
            missing = [
                path
                for path in ("pnr/config.yaml", "pnr/platform.lock.yaml")
                if not (project / path).is_file()
            ]
            if missing:
                return _failure(
                    stage,
                    "The project does not have a locked P&R platform. Run "
                    "`saxoflow pnr init` and resolve a dry run first.",
                )
        try:
            if stage in {"diagnose", "pdk-diagnose"}:
                from saxoflow.diagnose import diagnose as command

                diagnose_target = "pnr" if stage == "diagnose" else "pdk"
                command_args = [diagnose_target, *arguments]
            elif stage.startswith("pdk-"):
                from saxoflow.pdk_cli import pdk as command

                command_args = [stage.removeprefix("pdk-"), *arguments]
            else:
                from saxoflow.pnrflow import pnr as command

                command_args = [stage, *arguments]
        except Exception as exc:
            return _failure(stage, f"Failed to import SaxoFlow P&R entrypoint: {exc}")

        logger.info("Running P&R stage %s in %s", stage, project)
        with _pushd(project):
            result = CliRunner().invoke(command, command_args)
        output = str(result.output or "")
        if result.exit_code != 0:
            return _failure(
                stage,
                f"SaxoFlow P&R stage failed with exit code {result.exit_code}.",
                output,
            )
        return {
            "status": "success",
            "stage": f"pnr/{stage}",
            "stdout": output,
            "stderr": "",
            "error_message": None,
            "failure_manifest": "",
        }


__all__ = ["PnrAgent"]

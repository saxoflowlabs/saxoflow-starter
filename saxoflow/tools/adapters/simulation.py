"""Simulation adapter that wraps SaxoFlow's deterministic makeflow simulation."""

from __future__ import annotations

import os
import shlex
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple

import click

from saxoflow import makeflow
from saxoflow.source_manifests.service import SourceManifestResolutionError, resolve_rtl_specs
from saxoflow.schemas.tools import ToolRequest, ToolRun
from saxoflow.tools.adapters.base import BaseToolAdapter, ToolAdapterError


@contextmanager
def _pushd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class SimulationToolAdapter(BaseToolAdapter):
    """Capability adapter for `sim.run` using existing makeflow internals."""

    capability = "sim.run"

    def _run(self, request: ToolRequest) -> ToolRun:
        root = Path(request.workspace).resolve()
        if not root.is_dir():
            raise ToolAdapterError(f"Tool request workspace does not exist: {request.workspace}")

        options = self._sim_options(request, root)

        with _pushd(root):
            try:
                makeflow.require_makefile()
                tb_file = makeflow._resolve_icarus_testbench(options["tb"], options["tb_specs"])
                if not tb_file:
                    return self._failed_run("Unable to resolve testbench file.")

                if tb_file.suffix.lower() in {".vhd", ".vhdl"}:
                    return self._failed_run(
                        "Icarus simulation does not support VHDL testbenches directly."
                    )

                make_vars = makeflow._build_icarus_vars(
                    tb_file,
                    rtl_specs=options["rtl_specs"],
                    tb_specs=options["tb_specs"],
                    include_specs=options["include_specs"],
                )
                if make_vars is None:
                    return self._failed_run("Failed to build simulation source variables.")
            except (click.Abort, click.UsageError) as exc:
                return self._failed_run(str(exc))

            command = ["make", "sim-icarus"] + [f"{key}={value}" for key, value in make_vars.items()]
            command_text = shlex.join(command)

            if request.dry_run:
                return ToolRun.from_mapping(
                    {
                        "status": "skipped",
                        "capability": self.capability,
                        "tool_name": "iverilog",
                        "command": command_text,
                        "diagnostics": [],
                    }
                )

            result = makeflow.run_make("sim-icarus", extra_vars=make_vars)

        returncode = int(result.get("returncode", 1))
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        status = "success" if returncode == 0 else "failed"

        diagnostics = []
        if returncode != 0:
            message = stderr.strip() or stdout.strip() or "Simulation failed."
            diagnostics.append(
                {
                    "message": message.splitlines()[0],
                    "severity": "error",
                    "source": "sim-icarus",
                }
            )

        return ToolRun.from_mapping(
            {
                "status": status,
                "capability": self.capability,
                "tool_name": "iverilog",
                "command": command_text,
                "exit_code": returncode,
                "stdout": stdout or None,
                "stderr": stderr or None,
                "diagnostics": diagnostics,
            }
        )

    @staticmethod
    def _sim_options(request: ToolRequest, root: Path) -> Dict[str, Any]:
        raw = request.options.get("simulation") if isinstance(request.options, Mapping) else None
        options = dict(raw) if isinstance(raw, Mapping) else {}
        source_manifest = (
            request.options.get("source_manifest")
            if isinstance(request.options, Mapping) and isinstance(request.options.get("source_manifest"), Mapping)
            else None
        )

        rtl_specs = SimulationToolAdapter._as_string_tuple(options.get("rtl"))
        # Preserve prior implicit discovery behavior unless a source-manifest
        # provider or explicit RTL specs are requested.
        if not rtl_specs and source_manifest is None:
            resolved_rtl_specs = tuple()
        else:
            try:
                resolved_rtl_specs = resolve_rtl_specs(
                    root,
                    explicit_specs=rtl_specs,
                    default_specs=makeflow.DEFAULT_RTL_SPECS,
                    source_manifest_options=source_manifest,
                    target="sim",
                )
            except SourceManifestResolutionError as exc:
                raise ToolAdapterError(str(exc)) from exc

        return {
            "tb": SimulationToolAdapter._optional_string(options.get("tb")),
            "rtl_specs": tuple(resolved_rtl_specs),
            "tb_specs": SimulationToolAdapter._as_string_tuple(options.get("tb_file")),
            "include_specs": SimulationToolAdapter._as_string_tuple(options.get("include")),
        }

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _as_string_tuple(value: Any) -> Tuple[str, ...]:
        if value is None:
            return tuple()
        if isinstance(value, str):
            text = value.strip()
            return (text,) if text else tuple()
        if isinstance(value, Sequence):
            items = [str(item).strip() for item in value if str(item).strip()]
            return tuple(items)
        raise ToolAdapterError("Simulation options must be a string or list of strings.")

    def _failed_run(self, message: str) -> ToolRun:
        return ToolRun.from_mapping(
            {
                "status": "failed",
                "capability": self.capability,
                "tool_name": "iverilog",
                "exit_code": 1,
                "diagnostics": [
                    {
                        "message": message or "Simulation failed.",
                        "severity": "error",
                        "source": "sim-icarus",
                    }
                ],
            }
        )

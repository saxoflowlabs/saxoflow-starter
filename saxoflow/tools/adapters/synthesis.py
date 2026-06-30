"""Synthesis adapter that wraps SaxoFlow's deterministic Yosys flow."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple

import click

from saxoflow import makeflow, synthflow
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


class SynthesisToolAdapter(BaseToolAdapter):
    """Capability adapter for `synth.run` using existing synthflow internals."""

    capability = "synth.run"

    def _run(self, request: ToolRequest) -> ToolRun:
        root = Path(request.workspace).resolve()
        if not root.is_dir():
            raise ToolAdapterError(f"Tool request workspace does not exist: {request.workspace}")

        options = self._synth_options(request, root)
        command_preview = self._command_preview(root, options)

        if request.dry_run:
            return ToolRun.from_mapping(
                {
                    "status": "skipped",
                    "capability": self.capability,
                    "tool_name": "yosys",
                    "command": command_preview,
                    "diagnostics": [],
                }
            )

        with _pushd(root):
            try:
                synthflow.run_synthesis(
                    run_make=makeflow.run_make,
                    rtl_specs=options["rtl_specs"],
                    include_specs=options["include_specs"],
                    defines=options["defines"],
                    top=options["top"],
                    parameter_specs=options["parameters"],
                    frontend=options["frontend"],
                    target=options["target"],
                    device=options["device"],
                    family=options["family"],
                    liberty=options["liberty"],
                    clock_period=options["clock_period"],
                    lut=options["lut"],
                    flatten=options["flatten"],
                    formats=options["formats"],
                    output_prefix=options["output_prefix"],
                    preflight_lint=False,
                    script=None,
                    show_log=False,
                    create_schematic=False,
                    schematic_output=None,
                    schematic_input=None,
                    schematic_skin=None,
                    schematic_timeout=30,
                    open_schematic=False,
                )
            except click.Abort:
                return self._failed_run("Yosys synthesis failed.", command_preview)
            except click.UsageError as exc:
                return self._failed_run(str(exc), command_preview)

        manifest_path = root / "synthesis/reports/saxoflow_synth_manifest.json"
        outputs = sorted(
            path
            for path in (root / "synthesis/out").rglob("*")
            if path.is_file() and not path.name.startswith(".")
        )
        reports = sorted(
            path
            for path in (root / "synthesis/reports").glob("*")
            if path.is_file() and not path.name.startswith(".")
        )
        output_lines = []
        if manifest_path.is_file():
            output_lines.append(str(manifest_path.relative_to(root)))
        output_lines.extend(str(path.relative_to(root)) for path in reports)
        output_lines.extend(str(path.relative_to(root)) for path in outputs)

        return ToolRun.from_mapping(
            {
                "status": "success",
                "capability": self.capability,
                "tool_name": "yosys",
                "command": command_preview,
                "exit_code": 0,
                "stdout": "\n".join(output_lines) or None,
                "diagnostics": [],
            }
        )

    @staticmethod
    def _synth_options(request: ToolRequest, root: Path) -> Dict[str, Any]:
        raw = request.options.get("synthesis") if isinstance(request.options, Mapping) else None
        options = dict(raw) if isinstance(raw, Mapping) else {}
        source_manifest = (
            request.options.get("source_manifest")
            if isinstance(request.options, Mapping) and isinstance(request.options.get("source_manifest"), Mapping)
            else None
        )

        rtl_specs = SynthesisToolAdapter._as_string_tuple(options.get("rtl"), ())
        # Preserve prior implicit discovery behavior unless a source-manifest
        # provider or explicit RTL specs are requested.
        if not rtl_specs and source_manifest is None:
            resolved_rtl_specs = tuple()
        else:
            try:
                resolved_rtl_specs = resolve_rtl_specs(
                    root,
                    explicit_specs=rtl_specs,
                    default_specs=synthflow.DEFAULT_RTL_SPECS,
                    source_manifest_options=source_manifest,
                    target="synth",
                )
            except SourceManifestResolutionError as exc:
                raise ToolAdapterError(str(exc)) from exc

        return {
            "rtl_specs": tuple(resolved_rtl_specs),
            "include_specs": SynthesisToolAdapter._as_string_tuple(options.get("include"), ()),
            "defines": SynthesisToolAdapter._as_string_tuple(options.get("defines"), ()),
            "top": SynthesisToolAdapter._optional_string(options.get("top")),
            "parameters": SynthesisToolAdapter._as_string_tuple(options.get("parameters"), ()),
            "frontend": str(options.get("frontend", "auto")).strip().lower(),
            "target": str(options.get("target", "generic")).strip().lower(),
            "device": str(options.get("device", "hx")).strip(),
            "family": str(options.get("family", "xc7")).strip(),
            "liberty": SynthesisToolAdapter._optional_string(options.get("liberty")),
            "clock_period": SynthesisToolAdapter._optional_float(options.get("clock_period")),
            "lut": SynthesisToolAdapter._optional_int(options.get("lut")),
            "flatten": bool(options.get("flatten", True)),
            "formats": tuple(options.get("formats", ())) if isinstance(options.get("formats"), (list, tuple)) else tuple(),
            "output_prefix": SynthesisToolAdapter._optional_string(options.get("output_prefix")),
        }

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _as_string_tuple(value: Any, default: Sequence[str]) -> Tuple[str, ...]:
        if value is None:
            return tuple(default)
        if isinstance(value, str):
            text = value.strip()
            return (text,) if text else tuple(default)
        if isinstance(value, Sequence):
            items = [str(item).strip() for item in value if str(item).strip()]
            return tuple(items) if items else tuple(default)
        raise ToolAdapterError("Synthesis options must be strings or lists of strings.")

    @staticmethod
    def _command_preview(root: Path, options: Mapping[str, Any]) -> str:
        return f"saxoflow synth --target {options['target']} --frontend {options['frontend']}"

    def _failed_run(self, message: str, command_preview: str) -> ToolRun:
        return ToolRun.from_mapping(
            {
                "status": "failed",
                "capability": self.capability,
                "tool_name": "yosys",
                "command": command_preview,
                "exit_code": 1,
                "diagnostics": [
                    {
                        "message": message or "Synthesis failed.",
                        "severity": "error",
                        "source": "synthflow",
                    }
                ],
            }
        )

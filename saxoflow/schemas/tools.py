"""Tool adapter request and result schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from saxoflow.schemas.diagnostics import DiagnosticEntry, DiagnosticSchemaError


class ToolSchemaError(ValueError):
    """Raised when tool request or result payloads are missing required data."""


ALLOWED_TOOL_STATUSES = {"pending", "running", "success", "failed", "skipped"}
ALLOWED_FORMAL_PROOF_STATUSES = {"pass", "fail", "timeout", "cover", "error", "unknown"}


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolSchemaError(f"Tool field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolSchemaError(f"Tool field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


def _optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ToolSchemaError(f"Tool field `{field_name}` must be an integer when set.")
    return value


def _optional_positive_int(value: Any, field_name: str) -> Optional[int]:
    parsed = _optional_int(value, field_name)
    if parsed is not None and parsed < 1:
        raise ToolSchemaError(f"Tool field `{field_name}` must be a positive integer when set.")
    return parsed


def _as_string_tuple(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if not isinstance(value, list):
        raise ToolSchemaError(f"Tool field `{field_name}` must be a list of strings.")
    return tuple(_as_string(item, field_name) for item in value)


def _as_string_map(value: Any, field_name: str) -> Dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ToolSchemaError(f"Tool field `{field_name}` must be a mapping of strings.")

    normalized: Dict[str, str] = {}
    for key, raw_value in value.items():
        normalized[_as_string(key, f"{field_name} key")] = _as_string(raw_value, f"{field_name}.{key}")
    return normalized


def _as_mapping_map(value: Any, field_name: str) -> Dict[str, Dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ToolSchemaError(f"Tool field `{field_name}` must be a mapping.")
    result: Dict[str, Dict[str, Any]] = {}
    for key, raw_value in value.items():
        result[_as_string(key, f"{field_name} key")] = _as_mapping(raw_value, f"{field_name}.{key}")
    return result


@dataclass(frozen=True)
class ToolRequest:
    """A normalized request to run one deterministic adapter capability."""

    capability: str
    workspace: str
    tool_name: Optional[str] = None
    target: Optional[str] = None
    dry_run: bool = False
    env: Mapping[str, str] = field(default_factory=dict)
    options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ToolRequest":
        data = _as_mapping(raw, "tool_request")
        return cls(
            capability=_as_string(data.get("capability"), "tool_request.capability"),
            workspace=_as_string(data.get("workspace"), "tool_request.workspace"),
            tool_name=_optional_string(data.get("tool_name"), "tool_request.tool_name"),
            target=_optional_string(data.get("target"), "tool_request.target"),
            dry_run=bool(data.get("dry_run", False)),
            env=_as_string_map(data.get("env"), "tool_request.env"),
            options=_as_mapping_map(data.get("options"), "tool_request.options"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "capability": self.capability,
            "workspace": self.workspace,
            "dry_run": self.dry_run,
            "env": dict(self.env),
            "options": {name: dict(option) for name, option in self.options.items()},
        }
        if self.tool_name is not None:
            data["tool_name"] = self.tool_name
        if self.target is not None:
            data["target"] = self.target
        return data


@dataclass(frozen=True)
class ToolRun:
    """A normalized result emitted by deterministic tool adapters."""

    status: str
    capability: str
    command: Optional[str] = None
    tool_name: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    diagnostics: Tuple[DiagnosticEntry, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ToolRun":
        data = _as_mapping(raw, "tool_run")
        status = _as_string(data.get("status"), "tool_run.status").lower()
        if status not in ALLOWED_TOOL_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_TOOL_STATUSES))
            raise ToolSchemaError(f"Tool field `tool_run.status` must be one of: {allowed}.")

        diagnostics_raw = data.get("diagnostics") or []
        if not isinstance(diagnostics_raw, list):
            raise ToolSchemaError("Tool field `tool_run.diagnostics` must be a list of mappings.")

        diagnostics: list[DiagnosticEntry] = []
        for item in diagnostics_raw:
            try:
                diagnostics.append(DiagnosticEntry.from_mapping(item))
            except DiagnosticSchemaError as exc:
                raise ToolSchemaError(str(exc)) from exc

        return cls(
            status=status,
            capability=_as_string(data.get("capability"), "tool_run.capability"),
            command=_optional_string(data.get("command"), "tool_run.command"),
            tool_name=_optional_string(data.get("tool_name"), "tool_run.tool_name"),
            exit_code=_optional_int(data.get("exit_code"), "tool_run.exit_code"),
            stdout=_optional_string(data.get("stdout"), "tool_run.stdout"),
            stderr=_optional_string(data.get("stderr"), "tool_run.stderr"),
            diagnostics=tuple(diagnostics),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "status": self.status,
            "capability": self.capability,
            "diagnostics": [diag.to_dict() for diag in self.diagnostics],
        }
        if self.command is not None:
            data["command"] = self.command
        if self.tool_name is not None:
            data["tool_name"] = self.tool_name
        if self.exit_code is not None:
            data["exit_code"] = self.exit_code
        if self.stdout is not None:
            data["stdout"] = self.stdout
        if self.stderr is not None:
            data["stderr"] = self.stderr
        return data


@dataclass(frozen=True)
class FormalRunOptions:
    """Structured formal tool-run option contract."""

    solver: str = "auto"
    task: Optional[str] = None
    timeout_seconds: Optional[int] = None
    autotune: bool = False
    rtl_specs: Tuple[str, ...] = field(default_factory=tuple)
    sva_specs: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FormalRunOptions":
        data = _as_mapping(raw, "formal_run_options")
        return cls(
            solver=_as_string(data.get("solver", "auto"), "formal_run_options.solver").lower(),
            task=_optional_string(data.get("task"), "formal_run_options.task"),
            timeout_seconds=_optional_positive_int(
                data.get("timeout_seconds"),
                "formal_run_options.timeout_seconds",
            ),
            autotune=bool(data.get("autotune", False)),
            rtl_specs=_as_string_tuple(data.get("rtl_specs"), "formal_run_options.rtl_specs"),
            sva_specs=_as_string_tuple(data.get("sva_specs"), "formal_run_options.sva_specs"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "solver": self.solver,
            "autotune": self.autotune,
            "rtl_specs": list(self.rtl_specs),
            "sva_specs": list(self.sva_specs),
        }
        if self.task is not None:
            data["task"] = self.task
        if self.timeout_seconds is not None:
            data["timeout_seconds"] = self.timeout_seconds
        return data


@dataclass(frozen=True)
class FormalProofResult:
    """Structured formal proof outcome contract from adapter/parsing layers."""

    status: str
    engine: Optional[str] = None
    summary: Optional[str] = None
    report_paths: Tuple[str, ...] = field(default_factory=tuple)
    trace_paths: Tuple[str, ...] = field(default_factory=tuple)
    counterexample_refs: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FormalProofResult":
        data = _as_mapping(raw, "formal_proof_result")
        status = _as_string(data.get("status"), "formal_proof_result.status").lower()
        if status not in ALLOWED_FORMAL_PROOF_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_FORMAL_PROOF_STATUSES))
            raise ToolSchemaError(
                f"Tool field `formal_proof_result.status` must be one of: {allowed}."
            )
        return cls(
            status=status,
            engine=_optional_string(data.get("engine"), "formal_proof_result.engine"),
            summary=_optional_string(data.get("summary"), "formal_proof_result.summary"),
            report_paths=_as_string_tuple(data.get("report_paths"), "formal_proof_result.report_paths"),
            trace_paths=_as_string_tuple(data.get("trace_paths"), "formal_proof_result.trace_paths"),
            counterexample_refs=_as_string_tuple(
                data.get("counterexample_refs"),
                "formal_proof_result.counterexample_refs",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "status": self.status,
            "report_paths": list(self.report_paths),
            "trace_paths": list(self.trace_paths),
            "counterexample_refs": list(self.counterexample_refs),
        }
        if self.engine is not None:
            data["engine"] = self.engine
        if self.summary is not None:
            data["summary"] = self.summary
        return data
"""Normalized diagnostics schemas for adapter and workflow results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


class DiagnosticSchemaError(ValueError):
    """Raised when a diagnostic entry is missing required data or malformed."""


ALLOWED_DIAGNOSTIC_SEVERITIES = {"error", "warning", "info"}


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DiagnosticSchemaError(f"Diagnostic field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiagnosticSchemaError(f"Diagnostic field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


def _optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or value < 1:
        raise DiagnosticSchemaError(f"Diagnostic field `{field_name}` must be a positive integer when set.")
    return value


@dataclass(frozen=True)
class DiagnosticEntry:
    """A normalized diagnostic emitted by a tool adapter or validator."""

    message: str
    severity: str = "error"
    code: Optional[str] = None
    source: Optional[str] = None
    path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DiagnosticEntry":
        data = _as_mapping(raw, "diagnostic")
        severity = _as_string(data.get("severity", "error"), "diagnostic.severity").lower()
        if severity not in ALLOWED_DIAGNOSTIC_SEVERITIES:
            allowed = ", ".join(sorted(ALLOWED_DIAGNOSTIC_SEVERITIES))
            raise DiagnosticSchemaError(
                f"Diagnostic field `diagnostic.severity` must be one of: {allowed}."
            )
        return cls(
            message=_as_string(data.get("message"), "diagnostic.message"),
            severity=severity,
            code=_optional_string(data.get("code"), "diagnostic.code"),
            source=_optional_string(data.get("source"), "diagnostic.source"),
            path=_optional_string(data.get("path"), "diagnostic.path"),
            line=_optional_int(data.get("line"), "diagnostic.line"),
            column=_optional_int(data.get("column"), "diagnostic.column"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "message": self.message,
            "severity": self.severity,
        }
        if self.code is not None:
            data["code"] = self.code
        if self.source is not None:
            data["source"] = self.source
        if self.path is not None:
            data["path"] = self.path
        if self.line is not None:
            data["line"] = self.line
        if self.column is not None:
            data["column"] = self.column
        return data
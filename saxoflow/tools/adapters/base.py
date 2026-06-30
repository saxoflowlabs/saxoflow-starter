"""Base protocol for deterministic SaxoFlow tool adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from saxoflow.schemas.tools import ToolRequest, ToolRun, ToolSchemaError


class ToolAdapterError(ValueError):
    """Raised when a tool adapter receives invalid input or state."""


class BaseToolAdapter(ABC):
    """Shared adapter contract for capability-scoped tool execution."""

    capability: str

    def __init__(self, capability: str | None = None) -> None:
        if capability is not None:
            self.capability = capability

        if not isinstance(getattr(self, "capability", None), str) or not self.capability.strip():
            raise ToolAdapterError("Tool adapter capability must be a non-empty string.")

        self.capability = self.capability.strip()

    def supports(self, capability: str) -> bool:
        """Return whether the adapter can handle the provided capability name."""
        return capability.strip() == self.capability

    def validate_request(self, request: ToolRequest) -> None:
        """Validate that the request can be served by this adapter."""
        if request.capability != self.capability:
            raise ToolAdapterError(
                "Tool request capability mismatch: "
                f"adapter={self.capability} request={request.capability}."
            )

    def run(self, request: ToolRequest) -> ToolRun:
        """Validate and execute one capability-scoped adapter request."""
        self.validate_request(request)
        return self._run(request)

    def run_mapping(self, raw_request: Mapping[str, Any]) -> ToolRun:
        """Parse and execute a raw request mapping through the adapter contract."""
        try:
            request = ToolRequest.from_mapping(raw_request)
        except ToolSchemaError as exc:
            raise ToolAdapterError(str(exc)) from exc
        return self.run(request)

    @abstractmethod
    def _run(self, request: ToolRequest) -> ToolRun:
        """Adapter-specific execution implementation."""

"""Capability-based registry for deterministic SaxoFlow tool adapters."""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

from saxoflow.tools.adapters.base import BaseToolAdapter


class ToolRegistryError(ValueError):
    """Raised when adapter registration or lookup fails."""


class ToolRegistry:
    """Store and resolve adapters by normalized capability name."""

    def __init__(self, adapters: Iterable[BaseToolAdapter] | None = None) -> None:
        self._adapters: Dict[str, BaseToolAdapter] = {}
        if adapters is not None:
            for adapter in adapters:
                self.register(adapter)

    @staticmethod
    def _normalize_capability(capability: str) -> str:
        if not isinstance(capability, str) or not capability.strip():
            raise ToolRegistryError("Tool capability must be a non-empty string.")
        return capability.strip()

    def register(self, adapter: BaseToolAdapter) -> None:
        capability = self._normalize_capability(adapter.capability)
        if capability in self._adapters:
            raise ToolRegistryError(f"Tool adapter already registered for capability: {capability}")
        self._adapters[capability] = adapter

    def has(self, capability: str) -> bool:
        normalized = self._normalize_capability(capability)
        return normalized in self._adapters

    def get(self, capability: str) -> BaseToolAdapter | None:
        normalized = self._normalize_capability(capability)
        return self._adapters.get(normalized)

    def require(self, capability: str) -> BaseToolAdapter:
        normalized = self._normalize_capability(capability)
        adapter = self._adapters.get(normalized)
        if adapter is None:
            raise ToolRegistryError(f"No tool adapter registered for capability: {normalized}")
        return adapter

    def capabilities(self) -> Tuple[str, ...]:
        return tuple(sorted(self._adapters.keys()))

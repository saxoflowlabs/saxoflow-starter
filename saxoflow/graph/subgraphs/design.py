"""Compatibility design subgraph wrapper for legacy full-pipeline orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, Mapping

from saxoflow.graph.runtime import GraphRuntime


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on", "enabled"}


def compatibility_graph_enabled() -> bool:
    """Return whether full-pipeline compatibility graph delegation is enabled."""
    return _as_bool(os.getenv("SAXOFLOW_COMPAT_GRAPH_FULL_PIPELINE"))


@dataclass(frozen=True)
class DesignCompatibilityGraph:
    """Graph-callable shim that invokes the legacy orchestrator pipeline."""

    legacy_runner: Callable[..., Dict[str, str]]

    def invoke(self, payload: Mapping[str, object]) -> Dict[str, str]:
        spec_file = str(payload.get("spec_file") or "").strip()
        project_path = str(payload.get("project_path") or "").strip()
        verbose = bool(payload.get("verbose", False))
        max_iters = int(payload.get("max_iters", 3))

        if not spec_file:
            raise ValueError("Compatibility graph payload missing `spec_file`.")
        if not project_path:
            raise ValueError("Compatibility graph payload missing `project_path`.")

        return self.legacy_runner(
            spec_file=spec_file,
            project_path=project_path,
            verbose=verbose,
            max_iters=max_iters,
        )


def run_full_pipeline_with_compat_graph(
    *,
    spec_file: str,
    project_path: str,
    verbose: bool,
    max_iters: int,
    legacy_runner: Callable[..., Dict[str, str]],
) -> Dict[str, str]:
    """Execute legacy full-pipeline behavior through a graph-compatible wrapper."""
    runtime = GraphRuntime(graph_factory=lambda: DesignCompatibilityGraph(legacy_runner=legacy_runner))
    graph = runtime.build_graph()
    result = runtime._invoke_graph(
        graph,
        {
            "spec_file": spec_file,
            "project_path": project_path,
            "verbose": verbose,
            "max_iters": max_iters,
        },
    )

    if not isinstance(result, Mapping):
        raise ValueError("Compatibility graph full pipeline must return a mapping.")

    return {str(key): str(value) if value is not None else "" for key, value in dict(result).items()}

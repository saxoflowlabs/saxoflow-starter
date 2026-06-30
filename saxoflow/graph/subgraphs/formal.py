"""Formal verification subgraph template for Phase 5 reintegration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from saxoflow.schemas.tools import FormalProofResult, FormalRunOptions, ToolRequest, ToolRun, ToolSchemaError
from saxoflow.tools.adapters.formal import FormalToolAdapter


class FormalGraphError(ValueError):
    """Raised when formal subgraph payloads are invalid."""


@dataclass(frozen=True)
class FormalSubgraphTemplate:
    """Graph-callable formal subgraph that validates payloads and runs formal adapter."""

    adapter: Any = None

    def __post_init__(self) -> None:
        if self.adapter is None:
            object.__setattr__(self, "adapter", FormalToolAdapter())

    @staticmethod
    def _to_adapter_formal_options(options: FormalRunOptions) -> Dict[str, Any]:
        """Translate schema-level formal options to adapter option keys."""
        raw: Dict[str, Any] = {
            "solver": options.solver,
            "autotune": options.autotune,
        }
        if options.task is not None:
            raw["sby_task"] = options.task
        if options.timeout_seconds is not None:
            raw["timeout"] = options.timeout_seconds
        if options.rtl_specs:
            raw["rtl"] = list(options.rtl_specs)
        if options.sva_specs:
            raw["sva"] = list(options.sva_specs)
        return raw

    @staticmethod
    def _proof_result_from_tool_run(run: ToolRun) -> FormalProofResult:
        """Map adapter run results into formal proof result contract."""
        if run.status == "success":
            status = "pass"
        elif run.status == "failed":
            status = "fail"
        elif run.status == "running":
            status = "unknown"
        elif run.status == "pending":
            status = "unknown"
        else:
            status = "unknown"

        summary = None
        if run.diagnostics:
            summary = run.diagnostics[0].message
        elif run.stderr:
            summary = run.stderr
        elif run.stdout:
            summary = run.stdout

        return FormalProofResult.from_mapping(
            {
                "status": status,
                "engine": run.tool_name,
                "summary": summary or "Formal adapter run completed.",
                "report_paths": [],
                "trace_paths": [],
                "counterexample_refs": [],
            }
        )

    def invoke(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        workspace = str(payload.get("workspace") or "").strip()
        if not workspace:
            raise FormalGraphError("Formal subgraph payload missing `workspace`.")

        raw_options = payload.get("formal_options")
        if raw_options is None:
            raw_options = {}
        if not isinstance(raw_options, Mapping):
            raise FormalGraphError("Formal subgraph `formal_options` must be a mapping.")

        raw_proof = payload.get("proof_result")
        run = None
        if raw_proof is not None and not isinstance(raw_proof, Mapping):
            raise FormalGraphError("Formal subgraph `proof_result` must be a mapping.")

        try:
            options = FormalRunOptions.from_mapping(raw_options)
            if raw_proof is not None:
                proof = FormalProofResult.from_mapping(raw_proof)
            else:
                run_request = ToolRequest.from_mapping(
                    {
                        "capability": "formal.run",
                        "workspace": workspace,
                        "dry_run": bool(payload.get("dry_run", False)),
                        "options": {
                            "formal": self._to_adapter_formal_options(options),
                        },
                    }
                )
                run = self.adapter.run(run_request)
                proof = self._proof_result_from_tool_run(run)
        except ToolSchemaError as exc:
            raise FormalGraphError(str(exc)) from exc

        if proof.status in {"pass", "cover"}:
            graph_status = "success"
        elif proof.status == "timeout":
            graph_status = "timeout"
        elif proof.status == "unknown":
            graph_status = "unknown"
        else:
            graph_status = "failed"

        return {
            "status": graph_status,
            "subgraph": "formal",
            "workspace": workspace,
            "formal_options": options.to_dict(),
            "proof_result": proof.to_dict(),
            "diagnostics": [diag.to_dict() for diag in (run.diagnostics if run is not None else tuple())],
            "report_paths": list(proof.report_paths),
            "trace_paths": list(proof.trace_paths),
            "counterexample_refs": list(proof.counterexample_refs),
        }

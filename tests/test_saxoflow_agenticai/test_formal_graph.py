"""Focused tests for Phase 5 formal subgraph (P5.02)."""

from __future__ import annotations

import pytest

from saxoflow.schemas.tools import ToolRun


class _FakeFormalAdapter:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.result


def test_formal_subgraph_fake_proof_path_runs():
    from saxoflow.graph.subgraphs.formal import FormalSubgraphTemplate

    fake_run = ToolRun.from_mapping(
        {
            "status": "failed",
            "capability": "formal.run",
            "tool_name": "symbiyosys",
            "exit_code": 1,
            "stderr": "proof failed",
            "diagnostics": [
                {
                    "message": "counterexample generated",
                    "severity": "error",
                    "source": "formal",
                }
            ],
        }
    )
    graph = FormalSubgraphTemplate(adapter=_FakeFormalAdapter(fake_run))
    result = graph.invoke(
        {
            "workspace": "/workspace/demo",
            "formal_options": {
                "solver": "z3",
                "task": "prove",
                "timeout_seconds": 120,
                "rtl_specs": ["source/rtl/systemverilog/counter.sv"],
                "sva_specs": ["formal/source/counter_props.sv"],
            },
        }
    )

    assert result["subgraph"] == "formal"
    assert result["workspace"] == "/workspace/demo"
    assert result["status"] == "failed"
    assert result["formal_options"]["solver"] == "z3"
    assert result["proof_result"]["status"] == "fail"
    assert result["proof_result"]["engine"] == "symbiyosys"
    assert len(result["diagnostics"]) == 1
    assert result["diagnostics"][0]["message"] == "counterexample generated"


def test_formal_subgraph_defaults_to_fake_pass_result():
    from saxoflow.graph.subgraphs.formal import FormalSubgraphTemplate

    fake_run = ToolRun.from_mapping(
        {
            "status": "success",
            "capability": "formal.run",
            "tool_name": "symbiyosys",
            "exit_code": 0,
            "stdout": "formal complete",
            "diagnostics": [],
        }
    )
    adapter = _FakeFormalAdapter(fake_run)
    graph = FormalSubgraphTemplate(adapter=adapter)
    result = graph.invoke({"workspace": "/workspace/demo"})

    assert result["status"] == "success"
    assert result["proof_result"]["status"] == "pass"
    assert "formal complete" in result["proof_result"]["summary"]
    assert len(adapter.requests) == 1
    assert adapter.requests[0].capability == "formal.run"


def test_formal_subgraph_rejects_invalid_payload_shapes():
    from saxoflow.graph.subgraphs.formal import FormalGraphError, FormalSubgraphTemplate

    graph = FormalSubgraphTemplate()

    with pytest.raises(FormalGraphError):
        graph.invoke({})

    with pytest.raises(FormalGraphError):
        graph.invoke({"workspace": "/workspace/demo", "formal_options": "--solver z3"})

    with pytest.raises(FormalGraphError):
        graph.invoke(
            {
                "workspace": "/workspace/demo",
                "proof_result": {"status": "unsupported"},
            }
        )


def test_formal_subgraph_passes_adapter_diagnostics_through_graph_output():
    from saxoflow.graph.subgraphs.formal import FormalSubgraphTemplate

    fake_run = ToolRun.from_mapping(
        {
            "status": "failed",
            "capability": "formal.run",
            "tool_name": "symbiyosys",
            "diagnostics": [
                {
                    "message": "assertion p_counter_safety failed",
                    "severity": "error",
                    "source": "formal",
                    "line": 42,
                }
            ],
        }
    )
    graph = FormalSubgraphTemplate(adapter=_FakeFormalAdapter(fake_run))

    result = graph.invoke({"workspace": "/workspace/demo", "formal_options": {"solver": "z3"}})

    assert result["status"] == "failed"
    assert result["proof_result"]["status"] == "fail"
    assert result["diagnostics"]
    assert result["diagnostics"][0]["line"] == 42


@pytest.mark.parametrize(
    "tool_status,expected_proof,expected_graph",
    [
        ("running", "unknown", "unknown"),
        ("pending", "unknown", "unknown"),
        ("skipped", "unknown", "unknown"),
    ],
)
def test_formal_subgraph_maps_nonterminal_adapter_statuses(tool_status, expected_proof, expected_graph):
    from saxoflow.graph.subgraphs.formal import FormalSubgraphTemplate

    fake_run = ToolRun.from_mapping(
        {
            "status": tool_status,
            "capability": "formal.run",
            "tool_name": "symbiyosys",
            "stdout": "run in progress",
            "diagnostics": [],
        }
    )
    graph = FormalSubgraphTemplate(adapter=_FakeFormalAdapter(fake_run))

    result = graph.invoke({"workspace": "/workspace/demo", "formal_options": {"solver": "z3"}})

    assert result["proof_result"]["status"] == expected_proof
    assert result["status"] == expected_graph


def test_formal_subgraph_uses_proof_result_override_without_adapter_call():
    from saxoflow.graph.subgraphs.formal import FormalSubgraphTemplate

    fake_run = ToolRun.from_mapping(
        {
            "status": "success",
            "capability": "formal.run",
            "tool_name": "symbiyosys",
        }
    )
    adapter = _FakeFormalAdapter(fake_run)
    graph = FormalSubgraphTemplate(adapter=adapter)

    result = graph.invoke(
        {
            "workspace": "/workspace/demo",
            "proof_result": {
                "status": "timeout",
                "engine": "symbiyosys",
                "summary": "timed out",
                "report_paths": [],
                "trace_paths": [],
                "counterexample_refs": [],
            },
        }
    )

    assert result["status"] == "timeout"
    assert result["proof_result"]["status"] == "timeout"
    assert adapter.requests == []


def test_verification_subgraph_routes_formal_failure_to_repair_when_actionable():
    from saxoflow.graph.subgraphs.verification import VerificationSubgraphTemplate

    graph = VerificationSubgraphTemplate(max_repair_attempts=2)
    result = graph.invoke(
        {
            "formal_result": {"status": "fail"},
            "diagnostics": [
                {
                    "message": "assertion p_counter_safety failed",
                    "severity": "error",
                    "source": "formal",
                }
            ],
            "counterexample_refs": ["formal/out/counterexample.vcd:42"],
            "attempt": 1,
        }
    )

    assert result["status"] == "needs-repair"
    assert result["decision"] == "repair"
    assert result["repair_actions"]
    assert result["counterexample_refs"] == ["formal/out/counterexample.vcd:42"]


def test_verification_subgraph_escalates_after_repair_attempt_limit():
    from saxoflow.graph.subgraphs.verification import VerificationSubgraphTemplate

    graph = VerificationSubgraphTemplate(max_repair_attempts=1)
    result = graph.invoke(
        {
            "formal_result": {"status": "fail"},
            "diagnostics": [
                {
                    "message": "property failed",
                    "severity": "error",
                    "source": "formal",
                }
            ],
            "counterexample_refs": ["formal/out/counterexample.vcd"],
            "attempt": 2,
        }
    )

    assert result["status"] == "escalated"
    assert result["decision"] == "escalate"
    assert "attempt limit" in (result["escalation_reason"] or "")


def test_verification_subgraph_marks_successful_proof_complete():
    from saxoflow.graph.subgraphs.verification import VerificationSubgraphTemplate

    graph = VerificationSubgraphTemplate()
    result = graph.invoke(
        {
            "formal_result": {"status": "pass"},
            "diagnostics": [],
            "counterexample_refs": [],
            "attempt": 1,
        }
    )

    assert result["status"] == "verified"
    assert result["decision"] == "complete"
    assert result["repair_actions"] == []


def test_verification_subgraph_escalates_when_no_actionable_inputs():
    from saxoflow.graph.subgraphs.verification import VerificationSubgraphTemplate

    graph = VerificationSubgraphTemplate(max_repair_attempts=3)
    result = graph.invoke(
        {
            "formal_result": {"status": "fail"},
            "diagnostics": [],
            "counterexample_refs": [],
            "attempt": 1,
        }
    )

    assert result["status"] == "escalated"
    assert result["decision"] == "escalate"
    assert "without actionable repair inputs" in (result["escalation_reason"] or "")


def test_verification_subgraph_rejects_invalid_counterexample_refs_payload_type():
    from saxoflow.graph.subgraphs.verification import VerificationGraphError, VerificationSubgraphTemplate

    graph = VerificationSubgraphTemplate()

    with pytest.raises(VerificationGraphError):
        graph.invoke(
            {
                "formal_result": {"status": "fail"},
                "diagnostics": [],
                "counterexample_refs": "formal/out/trace.vcd",
                "attempt": 1,
            }
        )

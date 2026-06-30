"""Schema validation tests for tool adapter request and run payloads."""

from __future__ import annotations


def test_tool_request_validates_minimal_mapping():
    from saxoflow.schemas.tools import ToolRequest

    request = ToolRequest.from_mapping(
        {
            "capability": "lint.run",
            "workspace": "/tmp/workspace",
        }
    )

    assert request.capability == "lint.run"
    assert request.workspace == "/tmp/workspace"
    assert request.dry_run is False
    assert request.env == {}
    assert request.options == {}
    assert request.to_dict() == {
        "capability": "lint.run",
        "workspace": "/tmp/workspace",
        "dry_run": False,
        "env": {},
        "options": {},
    }


def test_tool_run_validates_minimal_mapping():
    from saxoflow.schemas.tools import ToolRun

    run = ToolRun.from_mapping(
        {
            "status": "success",
            "capability": "sim.run",
            "diagnostics": [
                {
                    "message": "No issues found",
                    "severity": "info",
                    "source": "sim-adapter",
                }
            ],
        }
    )

    assert run.status == "success"
    assert run.capability == "sim.run"
    assert len(run.diagnostics) == 1
    assert run.diagnostics[0].message == "No issues found"
    assert run.diagnostics[0].severity == "info"
    assert run.to_dict() == {
        "status": "success",
        "capability": "sim.run",
        "diagnostics": [
            {
                "message": "No issues found",
                "severity": "info",
                "source": "sim-adapter",
            }
        ],
    }


def test_tool_request_rejects_missing_capability():
    from saxoflow.schemas.tools import ToolRequest, ToolSchemaError

    try:
        ToolRequest.from_mapping({"workspace": "/tmp/workspace"})
    except ToolSchemaError as exc:
        assert "tool_request.capability" in str(exc)
    else:
        raise AssertionError("Invalid tool request was accepted.")


def test_tool_run_rejects_invalid_status():
    from saxoflow.schemas.tools import ToolRun, ToolSchemaError

    try:
        ToolRun.from_mapping(
            {
                "status": "completed",
                "capability": "synth.run",
            }
        )
    except ToolSchemaError as exc:
        assert "tool_run.status" in str(exc)
    else:
        raise AssertionError("Invalid tool run status was accepted.")


def test_fake_adapter_passes_base_contract():
    from saxoflow.schemas.tools import ToolRequest, ToolRun
    from saxoflow.tools.adapters.base import BaseToolAdapter

    class FakeLintAdapter(BaseToolAdapter):
        capability = "lint.run"

        def _run(self, request: ToolRequest) -> ToolRun:
            return ToolRun.from_mapping(
                {
                    "status": "success",
                    "capability": request.capability,
                    "command": "verible-verilog-lint source/rtl/top.sv",
                    "diagnostics": [],
                }
            )

    adapter = FakeLintAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "lint.run",
            "workspace": "/tmp/workspace",
        }
    )

    result = adapter.run(request)
    assert result.status == "success"
    assert result.capability == "lint.run"
    assert result.command == "verible-verilog-lint source/rtl/top.sv"


def test_fake_adapter_rejects_capability_mismatch():
    from saxoflow.schemas.tools import ToolRequest
    from saxoflow.tools.adapters.base import BaseToolAdapter, ToolAdapterError

    class FakeLintAdapter(BaseToolAdapter):
        capability = "lint.run"

        def _run(self, request: ToolRequest):
            raise AssertionError("_run should not be called for mismatched capability.")

    adapter = FakeLintAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "sim.run",
            "workspace": "/tmp/workspace",
        }
    )

    try:
        adapter.run(request)
    except ToolAdapterError as exc:
        assert "capability mismatch" in str(exc)
    else:
        raise AssertionError("Mismatched capability request was accepted.")


def test_tool_registry_lookup_works_by_capability():
    from saxoflow.schemas.tools import ToolRequest, ToolRun
    from saxoflow.tools.adapters.base import BaseToolAdapter
    from saxoflow.tools.registry import ToolRegistry

    class FakeLintAdapter(BaseToolAdapter):
        capability = "lint.run"

        def _run(self, request: ToolRequest) -> ToolRun:
            return ToolRun.from_mapping(
                {
                    "status": "success",
                    "capability": request.capability,
                    "diagnostics": [],
                }
            )

    class FakeSimAdapter(BaseToolAdapter):
        capability = "sim.run"

        def _run(self, request: ToolRequest) -> ToolRun:
            return ToolRun.from_mapping(
                {
                    "status": "success",
                    "capability": request.capability,
                    "diagnostics": [],
                }
            )

    lint_adapter = FakeLintAdapter()
    sim_adapter = FakeSimAdapter()
    registry = ToolRegistry(adapters=[lint_adapter, sim_adapter])

    assert registry.has("lint.run") is True
    assert registry.has("sim.run") is True
    assert registry.get("lint.run") is lint_adapter
    assert registry.get("sim.run") is sim_adapter
    assert registry.capabilities() == ("lint.run", "sim.run")


def test_tool_registry_require_rejects_missing_capability():
    from saxoflow.tools.registry import ToolRegistry, ToolRegistryError

    registry = ToolRegistry()
    assert registry.get("pnr.run") is None

    try:
        registry.require("pnr.run")
    except ToolRegistryError as exc:
        assert "No tool adapter registered" in str(exc)
    else:
        raise AssertionError("Missing registry lookup was accepted.")


def test_tool_health_service_reports_installed_and_missing_tools():
    from saxoflow.schemas.tools import ToolRequest, ToolRun
    from saxoflow.tools.adapters.base import BaseToolAdapter
    from saxoflow.tools.health import ToolHealthService
    from saxoflow.tools.registry import ToolRegistry

    class FakeLintAdapter(BaseToolAdapter):
        capability = "lint.run"

        def _run(self, request: ToolRequest) -> ToolRun:
            return ToolRun.from_mapping(
                {
                    "status": "success",
                    "capability": request.capability,
                    "diagnostics": [],
                }
            )

    def fake_locator(tool: str):
        known = {
            "yosys": "/usr/bin/yosys",
            "verilator": None,
        }
        return known.get(tool)

    registry = ToolRegistry([FakeLintAdapter()])
    health = ToolHealthService(registry=registry, tool_locator=fake_locator)
    report = health.check_capability("lint.run", ["yosys", "verilator"])

    assert report.adapter_registered is True
    assert report.required_tools == ("yosys", "verilator")
    assert report.installed_tools == ("yosys",)
    assert report.missing_tools == ("verilator",)
    assert report.healthy is False


def test_tool_health_service_reports_healthy_when_all_present():
    from saxoflow.schemas.tools import ToolRequest, ToolRun
    from saxoflow.tools.adapters.base import BaseToolAdapter
    from saxoflow.tools.health import ToolHealthService
    from saxoflow.tools.registry import ToolRegistry

    class FakeSimAdapter(BaseToolAdapter):
        capability = "sim.run"

        def _run(self, request: ToolRequest) -> ToolRun:
            return ToolRun.from_mapping(
                {
                    "status": "success",
                    "capability": request.capability,
                    "diagnostics": [],
                }
            )

    def fake_locator(tool: str):
        known = {
            "iverilog": "/usr/bin/iverilog",
            "vvp": "/usr/bin/vvp",
        }
        return known.get(tool)

    registry = ToolRegistry([FakeSimAdapter()])
    health = ToolHealthService(registry=registry, tool_locator=fake_locator)
    report = health.check_capability("sim.run", ["iverilog", "vvp"])

    assert report.adapter_registered is True
    assert report.required_tools == ("iverilog", "vvp")
    assert report.installed_tools == ("iverilog", "vvp")
    assert report.missing_tools == ()
    assert report.healthy is True
"""Tests for repository acquisition service and VCS adapter."""

from __future__ import annotations


def test_project_service_clone_tracks_provenance_and_enforces_policy(tmp_path):
    from saxoflow.services.project_service import ProjectService, RepositoryPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    service = ProjectService.from_workspace(workspace, policy=RepositoryPolicy(("clone",)))
    operation = service.clone_repository(
        "https://example.com/demo.git",
        "repos/demo",
        branch="main",
        dry_run=True,
    )

    assert operation.status == "skipped"
    assert operation.action == "clone"
    assert operation.command == (
        "git",
        "clone",
        "--branch",
        "main",
        "https://example.com/demo.git",
        str((workspace / "repos" / "demo").resolve()),
    )
    assert operation.provenance.action == "clone"
    assert operation.provenance.remote_url == "https://example.com/demo.git"
    assert operation.provenance.reference == "main"
    assert operation.provenance.repository_root == str((workspace / "repos" / "demo").resolve())
    assert operation.approval_required is True


def test_project_service_rejects_actions_outside_policy(tmp_path):
    from saxoflow.services.project_service import ProjectService, RepositoryPolicy, ProjectServiceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    service = ProjectService.from_workspace(workspace, policy=RepositoryPolicy(("fetch",)))

    try:
        service.checkout_repository(workspace, "main", dry_run=True)
    except ProjectServiceError as exc:
        assert "not allowed by policy" in str(exc)
    else:
        raise AssertionError("Disallowed repository action was accepted.")


def test_project_service_rejects_repository_escape(tmp_path):
    from saxoflow.services.project_service import ProjectService, RepositoryPolicy, ProjectServiceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"

    service = ProjectService.from_workspace(workspace, policy=RepositoryPolicy())

    try:
        service.fetch_repository(outside, dry_run=True)
    except ProjectServiceError as exc:
        assert "escapes the workspace root" in str(exc)
    else:
        raise AssertionError("Escaping repository path was accepted.")


def test_project_service_rejects_unapproved_external_repository_location(tmp_path):
    from saxoflow.services.project_service import ProjectService, ProjectServiceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path / "approved" / "demo"
    external.mkdir(parents=True)

    service = ProjectService.from_workspace(workspace)

    try:
        service.qualify_repository(external)
    except ProjectServiceError as exc:
        assert "approved workspace or staging areas" in str(exc)
    else:
        raise AssertionError("Unapproved external repository location was accepted.")


def test_project_service_allows_approved_staging_area_and_marks_approval(tmp_path):
    from saxoflow.services.project_service import ProjectService

    workspace = tmp_path / "workspace"
    staging = workspace / "staging" / "demo"
    staging.mkdir(parents=True)

    service = ProjectService.from_workspace(workspace)
    operation = service.diff_repository(staging, dry_run=True)

    assert operation.approval_required is False
    assert operation.provenance.repository_root == str(staging.resolve())
    assert operation.status == "skipped"


def test_vcs_adapter_returns_normalized_tool_run_for_checkout(tmp_path):
    from saxoflow.schemas.tools import ToolRequest
    from saxoflow.tools.adapters.vcs import VcsToolAdapter

    workspace = tmp_path / "workspace"
    repo = workspace / "repos" / "demo"
    repo.mkdir(parents=True)

    adapter = VcsToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "repo.acquire",
            "workspace": str(workspace),
            "dry_run": True,
            "options": {
                "vcs": {
                    "action": "checkout",
                    "repository_root": "repos/demo",
                    "reference": "feature/test",
                }
            },
        }
    )

    result = adapter.run(request)

    assert result.status == "skipped"
    assert result.capability == "repo.acquire"
    assert result.command == "git checkout feature/test repos/demo"
    assert "feature/test" in result.stdout
    assert result.diagnostics == ()


def test_vcs_adapter_rejects_missing_required_clone_fields(tmp_path):
    from saxoflow.schemas.tools import ToolRequest
    from saxoflow.tools.adapters.vcs import VcsToolAdapter, ToolAdapterError

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    adapter = VcsToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "repo.acquire",
            "workspace": str(workspace),
            "options": {"vcs": {"action": "clone", "remote_url": "https://example.com/demo.git"}},
        }
    )

    try:
        adapter.run(request)
    except ToolAdapterError as exc:
        assert "Clone requires" in str(exc)
    else:
        raise AssertionError("Clone without destination was accepted.")


def test_project_service_qualify_repository_reports_profile_and_readiness(tmp_path):
    from saxoflow.project_manifest import MANIFEST_SCHEMA_VERSION
    from saxoflow.services.project_service import ProjectService

    workspace = tmp_path / "workspace"
    source_rtl = workspace / "source" / "rtl"
    source_tb = workspace / "source" / "tb"
    docs = workspace / "docs"
    source_rtl.mkdir(parents=True)
    source_tb.mkdir(parents=True)
    docs.mkdir(parents=True)
    (workspace / "README.md").write_text("workspace overview\n", encoding="utf-8")
    (workspace / "Bender.yml").write_text(
        "\n".join(
            [
                "package:",
                "  name: demo",
                "sources:",
                "  - files:",
                "      - source/rtl/**/*.sv",
                "    target: rtl",
                "  - files:",
                "      - source/tb/**/*.sv",
                "    target: sim",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "saxoflow_project.yaml").write_text(
        "\n".join(
            [
                f"schema_version: {MANIFEST_SCHEMA_VERSION}",
                "project:",
                "  name: demo",
                "  top_module: top_demo",
                "source_manifest:",
                "  provider: bender",
                "  path: Bender.yml",
                "  target: rtl",
            ]
        ),
        encoding="utf-8",
    )
    (source_rtl / "top_demo.sv").write_text("module top_demo; endmodule\n", encoding="utf-8")
    (source_tb / "top_demo_tb.sv").write_text("module top_demo_tb; endmodule\n", encoding="utf-8")
    (docs / "README.md").write_text("demo docs\n", encoding="utf-8")

    report = ProjectService.from_workspace(workspace).qualify_repository(workspace)

    assert report.manifest_path == "saxoflow_project.yaml"
    assert report.profile.project_name == "demo"
    assert report.profile.top_modules == ("top_demo",)
    assert "README.md" in report.profile.entrypoints
    assert report.profile.role_map["manifest"] == ("Bender.yml", "saxoflow_project.yaml")
    assert report.profile.role_map["rtl"] == ("source/rtl",)
    assert report.profile.role_map["sim"] == ("source/tb",)
    assert report.readiness["rtl"] == "ready"
    assert report.readiness["sim"] == "ready"
    assert report.ready is True


def test_project_service_qualify_repository_without_manifest_reports_blocked(tmp_path):
    from saxoflow.services.project_service import ProjectService

    workspace = tmp_path / "workspace"
    (workspace / "source" / "rtl").mkdir(parents=True)
    (workspace / "source" / "rtl" / "chip.sv").write_text("module chip; endmodule\n", encoding="utf-8")

    report = ProjectService.from_workspace(workspace).qualify_repository(workspace)

    assert report.manifest_path is None
    assert report.profile.project_name == "workspace"
    assert report.profile.top_modules == ("chip",)
    assert report.readiness["overall"] == "ready"
    assert report.ready is True


def test_project_service_qualify_repository_maps_nonstandard_topology(tmp_path):
    from saxoflow.services.project_service import ProjectService

    workspace = tmp_path / "workspace"
    (workspace / "hardware" / "design").mkdir(parents=True)
    (workspace / "verification" / "testbench").mkdir(parents=True)
    (workspace / "docs_custom").mkdir(parents=True)
    (workspace / "automation" / "scripts").mkdir(parents=True)
    (workspace / "output" / "reports").mkdir(parents=True)

    (workspace / "hardware" / "design" / "chip_top.sv").write_text("module chip_top; endmodule\n", encoding="utf-8")
    (workspace / "verification" / "testbench" / "chip_tb.sv").write_text("module chip_tb; endmodule\n", encoding="utf-8")
    (workspace / "README.md").write_text("workspace overview\n", encoding="utf-8")

    report = ProjectService.from_workspace(workspace).qualify_repository(workspace)

    assert report.ready is True
    assert report.profile.role_map["rtl"] == ("hardware/design",)
    assert report.profile.role_map["sim"] == ("verification/testbench",)
    assert report.profile.role_map["docs"] == ("README.md", "docs_custom")
    assert report.profile.role_map["scripts"] == ("automation/scripts",)
    assert report.profile.role_map["reports"] == ("output/reports",)
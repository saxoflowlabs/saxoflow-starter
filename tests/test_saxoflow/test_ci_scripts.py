"""Tests for M7 CI governance scripts.

Validates that the three M7 CI check scripts (check_doc_manifest.py,
check_adapter_license_metadata.py, check_deprecation_contracts.py) execute
correctly against the live repository and produce expected outcomes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_CI = REPO_ROOT / "scripts" / "ci"
REGISTRY_FILE = REPO_ROOT / "saxoflow" / "tools" / "registry.yaml"
LICENSE_META_FILE = REPO_ROOT / "saxoflow" / "tools" / "license_metadata.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_script(script_name: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPTS_CI / script_name)] + (extra_args or [])
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


# ===========================================================================
# check_doc_manifest.py tests
# ===========================================================================

class TestCheckDocManifest:
    def test_script_exits_zero_on_clean_repo(self):
        """check_doc_manifest.py must exit 0 on the clean repository."""
        result = _run_script("check_doc_manifest.py")
        assert result.returncode == 0, (
            f"check_doc_manifest.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "[doc-manifest] OK" in result.stdout

    def test_script_reports_ok_line(self):
        result = _run_script("check_doc_manifest.py")
        assert "[doc-manifest]" in result.stdout

    def test_registry_file_exists(self):
        assert REGISTRY_FILE.exists(), f"registry.yaml not found at {REGISTRY_FILE}"

    def test_registry_has_required_fields(self):
        """Every entry in registry.yaml must have key, native, saxoflow_cmd, check_cmd, description."""
        data = _load_yaml(REGISTRY_FILE)
        tools = data.get("tools", [])
        assert tools, "No tools found in registry.yaml"
        required = {"key", "native", "saxoflow_cmd", "check_cmd", "description"}
        for entry in tools:
            for field in required:
                assert field in entry, f"Tool '{entry.get('key', '?')}' missing field '{field}'"
                assert str(entry[field]).strip(), f"Tool '{entry.get('key', '?')}' has empty field '{field}'"

    def test_no_duplicate_keys_in_registry(self):
        data = _load_yaml(REGISTRY_FILE)
        keys = [entry.get("key") for entry in data.get("tools", []) if "key" in entry]
        assert len(keys) == len(set(keys)), f"Duplicate keys in registry.yaml: {[k for k in keys if keys.count(k) > 1]}"

    def test_run_checks_returns_empty_on_clean_repo(self):
        """Direct call: run_checks() returns no errors on clean repo."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        findings = check_doc_manifest.run_checks()
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"

    def test_run_checks_detects_missing_registry(self, tmp_path):
        """report missing-registry when registry file does not exist."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        original = check_doc_manifest.REGISTRY_FILE
        check_doc_manifest.REGISTRY_FILE = tmp_path / "nonexistent.yaml"
        try:
            findings = check_doc_manifest.run_checks()
            assert any(f.kind == "missing-registry" for f in findings)
        finally:
            check_doc_manifest.REGISTRY_FILE = original

    def test_run_checks_detects_empty_registry(self, tmp_path):
        """report missing-registry when registry YAML has no tools list."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        bad = tmp_path / "registry.yaml"
        bad.write_text("tools: []\n", encoding="utf-8")
        original = check_doc_manifest.REGISTRY_FILE
        check_doc_manifest.REGISTRY_FILE = bad
        try:
            findings = check_doc_manifest.run_checks()
            assert any(f.kind == "missing-registry" for f in findings)
        finally:
            check_doc_manifest.REGISTRY_FILE = original

    def test_script_detects_missing_field(self, tmp_path):
        """Injecting a tool without 'description' should cause an error finding."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        bad_registry = tmp_path / "registry.yaml"
        bad_registry.write_text(
            "tools:\n"
            "  - key: bad_tool\n"
            "    native: bad\n"
            "    saxoflow_cmd: saxoflow bad\n"
            "    check_cmd: bad --version\n"
            # missing description deliberately
            "\n",
            encoding="utf-8",
        )
        original = check_doc_manifest.REGISTRY_FILE
        check_doc_manifest.REGISTRY_FILE = bad_registry
        try:
            findings = check_doc_manifest.run_checks()
            error_kinds = {f.kind for f in findings if f.severity == "error"}
            assert "missing-field" in error_kinds or "empty-field" in error_kinds
        finally:
            check_doc_manifest.REGISTRY_FILE = original

    def test_run_checks_detects_duplicate_key(self, tmp_path):
        """Duplicate tool keys should produce a duplicate-key finding."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        dup = tmp_path / "registry.yaml"
        dup.write_text(
            "tools:\n"
            "  - key: x\n    native: x\n    saxoflow_cmd: 'saxoflow x'\n    check_cmd: 'x'\n    description: 'X'\n"
            "  - key: x\n    native: x\n    saxoflow_cmd: 'saxoflow x'\n    check_cmd: 'x'\n    description: 'X dup'\n",
            encoding="utf-8",
        )
        original = check_doc_manifest.REGISTRY_FILE
        check_doc_manifest.REGISTRY_FILE = dup
        try:
            findings = check_doc_manifest.run_checks()
            assert any(f.kind == "duplicate-key" for f in findings)
        finally:
            check_doc_manifest.REGISTRY_FILE = original

    def test_main_exit_zero(self):
        """main() exits 0 on clean repo (covers main() body)."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        with patch("sys.argv", ["check_doc_manifest.py"]):
            rc = check_doc_manifest.main()
        assert rc == 0

    def test_main_exit_one_on_error(self, tmp_path):
        """main() exits 1 when errors are present."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        bad = tmp_path / "registry.yaml"
        bad.write_text(
            "tools:\n  - key: t\n    native: t\n    saxoflow_cmd: 'saxoflow t'\n    check_cmd: 't'\n",
            encoding="utf-8",
        )
        original = check_doc_manifest.REGISTRY_FILE
        check_doc_manifest.REGISTRY_FILE = bad
        try:
            with patch("sys.argv", ["check_doc_manifest.py"]):
                rc = check_doc_manifest.main()
            assert rc == 1
        finally:
            check_doc_manifest.REGISTRY_FILE = original

    def test_run_checks_detects_empty_field(self, tmp_path):
        """A tool with empty description value should produce an empty-field or empty-description finding."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        bad = tmp_path / "registry.yaml"
        bad.write_text(
            "tools:\n"
            "  - key: emp\n    native: emp\n    saxoflow_cmd: 'saxoflow emp'\n"
            "    check_cmd: 'emp'\n    description: ''\n",
            encoding="utf-8",
        )
        original = check_doc_manifest.REGISTRY_FILE
        check_doc_manifest.REGISTRY_FILE = bad
        try:
            findings = check_doc_manifest.run_checks()
            error_kinds = {f.kind for f in findings}
            assert "empty-field" in error_kinds or "empty-description" in error_kinds
        finally:
            check_doc_manifest.REGISTRY_FILE = original

    def test_missing_recipe_warning(self, tmp_path):
        """A script-managed tool without a recipe should emit a warning."""
        from scripts.ci import check_doc_manifest  # type: ignore[import]
        reg = tmp_path / "registry.yaml"
        reg.write_text(
            "tools:\n"
            "  - key: ghost_tool\n    native: ghost\n    saxoflow_cmd: 'saxoflow ghost'\n"
            "    check_cmd: 'ghost --version'\n    description: 'Ghost'\n",
            encoding="utf-8",
        )
        original_r = check_doc_manifest.REGISTRY_FILE
        original_st = check_doc_manifest._load_script_tools
        check_doc_manifest.REGISTRY_FILE = reg
        check_doc_manifest._load_script_tools = lambda: {"ghost_tool"}  # type: ignore
        try:
            findings = check_doc_manifest.run_checks()
            warn_kinds = {f.kind for f in findings if f.severity == "warning"}
            assert "missing-recipe" in warn_kinds
        finally:
            check_doc_manifest.REGISTRY_FILE = original_r
            check_doc_manifest._load_script_tools = original_st  # type: ignore


# ===========================================================================
# check_adapter_license_metadata.py tests
# ===========================================================================

class TestCheckAdapterLicenseMetadata:
    def test_script_exits_zero_on_clean_repo(self):
        """check_adapter_license_metadata.py must exit 0 on clean repo."""
        result = _run_script("check_adapter_license_metadata.py")
        assert result.returncode == 0, (
            f"check_adapter_license_metadata.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "[license-meta] OK" in result.stdout

    def test_license_metadata_file_exists(self):
        assert LICENSE_META_FILE.exists(), f"license_metadata.yaml not found at {LICENSE_META_FILE}"

    def test_license_metadata_has_required_fields_for_education_ready(self):
        """education_ready tools must have all required fields."""
        data = _load_yaml(LICENSE_META_FILE)
        tool_licenses = data.get("tool_licenses", {})
        required = {"license", "redistribution", "upstream_url", "license_summary"}
        for key, meta in tool_licenses.items():
            if meta.get("education_ready", False):
                for field in required:
                    assert field in meta and str(meta[field]).strip(), (
                        f"Education-ready tool '{key}' missing required field: '{field}'"
                    )

    def test_redistribution_values_are_valid(self):
        data = _load_yaml(LICENSE_META_FILE)
        valid = {"allowed", "allowed-with-attribution", "restricted", "unknown"}
        for key, meta in data.get("tool_licenses", {}).items():
            redist = meta.get("redistribution", "")
            if redist:
                assert redist in valid, f"Tool '{key}' has invalid redistribution value: '{redist}'"

    def test_upstream_url_is_present_for_all_entries(self):
        data = _load_yaml(LICENSE_META_FILE)
        for key, meta in data.get("tool_licenses", {}).items():
            assert "upstream_url" in meta and str(meta["upstream_url"]).strip(), (
                f"Tool '{key}' is missing upstream_url"
            )

    def test_run_checks_detects_missing_registry(self, tmp_path):
        """Missing registry file produces a finding."""
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        original = check_adapter_license_metadata.REGISTRY_FILE
        check_adapter_license_metadata.REGISTRY_FILE = tmp_path / "nope.yaml"
        try:
            findings = check_adapter_license_metadata.run_checks()
            assert any(f.kind == "missing-registry" for f in findings)
        finally:
            check_adapter_license_metadata.REGISTRY_FILE = original

    def test_run_checks_detects_missing_license_metadata_file(self, tmp_path):
        """Missing license_metadata.yaml produces a finding."""
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        orig_l = check_adapter_license_metadata.LICENSE_METADATA_FILE
        check_adapter_license_metadata.LICENSE_METADATA_FILE = tmp_path / "nope.yaml"
        try:
            findings = check_adapter_license_metadata.run_checks()
            assert any(f.kind == "missing-license-metadata" for f in findings)
        finally:
            check_adapter_license_metadata.LICENSE_METADATA_FILE = orig_l

    def test_run_checks_detects_missing_metadata_entry(self, tmp_path):
        """Tool in registry but not in license_metadata.yaml produces warning."""
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        reg = tmp_path / "registry.yaml"
        reg.write_text(
            "tools:\n  - key: newbie\n    native: nb\n    saxoflow_cmd: 'saxoflow nb'\n    check_cmd: 'nb'\n    description: 'N'\n",
            encoding="utf-8",
        )
        lic = tmp_path / "license_metadata.yaml"
        lic.write_text("tool_licenses: {}\n", encoding="utf-8")
        orig_r = check_adapter_license_metadata.REGISTRY_FILE
        orig_l = check_adapter_license_metadata.LICENSE_METADATA_FILE
        check_adapter_license_metadata.REGISTRY_FILE = reg
        check_adapter_license_metadata.LICENSE_METADATA_FILE = lic
        try:
            findings = check_adapter_license_metadata.run_checks()
            warn_kinds = {f.kind for f in findings if f.severity == "warning"}
            assert "missing-metadata-entry" in warn_kinds
        finally:
            check_adapter_license_metadata.REGISTRY_FILE = orig_r
            check_adapter_license_metadata.LICENSE_METADATA_FILE = orig_l

    def test_run_checks_detects_stale_metadata_entry(self, tmp_path):
        """Entry in license_metadata.yaml not in registry produces warning."""
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        # Registry has one real tool; license metadata has that tool PLUS an orphan
        reg = tmp_path / "registry.yaml"
        reg.write_text(
            "tools:\n"
            "  - key: real_tool\n    native: rt\n    saxoflow_cmd: 'saxoflow rt'\n"
            "    check_cmd: 'rt'\n    description: 'Real'\n",
            encoding="utf-8",
        )
        lic = tmp_path / "license_metadata.yaml"
        lic.write_text(
            "tool_licenses:\n"
            "  real_tool:\n    license: MIT\n    redistribution: allowed\n    upstream_url: https://example.com\n"
            "  orphan:\n    license: MIT\n    redistribution: allowed\n    upstream_url: https://example.com\n",
            encoding="utf-8",
        )
        orig_r = check_adapter_license_metadata.REGISTRY_FILE
        orig_l = check_adapter_license_metadata.LICENSE_METADATA_FILE
        check_adapter_license_metadata.REGISTRY_FILE = reg
        check_adapter_license_metadata.LICENSE_METADATA_FILE = lic
        try:
            findings = check_adapter_license_metadata.run_checks()
        finally:
            check_adapter_license_metadata.REGISTRY_FILE = orig_r
            check_adapter_license_metadata.LICENSE_METADATA_FILE = orig_l
        # orphan entry produces a stale-metadata-entry warning
        warn_kinds = {f.kind for f in findings if f.severity == "warning"}
        assert "stale-metadata-entry" in warn_kinds

    def test_run_checks_education_ready_incomplete_is_error(self, tmp_path):
        """education_ready tool with missing license_summary must produce error."""
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        reg = tmp_path / "registry.yaml"
        reg.write_text(
            "tools:\n  - key: edu\n    native: edu\n    saxoflow_cmd: 'saxoflow edu'\n    check_cmd: 'edu'\n    description: 'Edu'\n",
            encoding="utf-8",
        )
        lic = tmp_path / "license_metadata.yaml"
        lic.write_text(
            "tool_licenses:\n"
            "  edu:\n"
            "    license: MIT\n"
            "    redistribution: allowed\n"
            "    upstream_url: https://example.com\n"
            "    education_ready: true\n"
            # Missing license_summary intentionally
            "\n",
            encoding="utf-8",
        )
        orig_r = check_adapter_license_metadata.REGISTRY_FILE
        orig_l = check_adapter_license_metadata.LICENSE_METADATA_FILE
        check_adapter_license_metadata.REGISTRY_FILE = reg
        check_adapter_license_metadata.LICENSE_METADATA_FILE = lic
        try:
            findings = check_adapter_license_metadata.run_checks()
        finally:
            check_adapter_license_metadata.REGISTRY_FILE = orig_r
            check_adapter_license_metadata.LICENSE_METADATA_FILE = orig_l
        errors = [f for f in findings if f.severity == "error"]
        assert errors, "Expected error for incomplete education_ready tool"

    def test_main_exit_zero(self):
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        with patch("sys.argv", ["check_adapter_license_metadata.py"]):
            rc = check_adapter_license_metadata.main()
        assert rc == 0

    def test_main_exit_one_on_error(self, tmp_path):
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        orig_l = check_adapter_license_metadata.LICENSE_METADATA_FILE
        check_adapter_license_metadata.LICENSE_METADATA_FILE = tmp_path / "missing.yaml"
        try:
            with patch("sys.argv", ["check_adapter_license_metadata.py"]):
                rc = check_adapter_license_metadata.main()
        finally:
            check_adapter_license_metadata.LICENSE_METADATA_FILE = orig_l
        assert rc == 1

    def test_script_detects_invalid_redistribution(self, tmp_path):
        """Script should emit error for invalid redistribution value."""
        from scripts.ci import check_adapter_license_metadata  # type: ignore[import]
        bad_registry = tmp_path / "registry.yaml"
        bad_registry.write_text(
            "tools:\n  - key: x\n    native: x\n    saxoflow_cmd: saxoflow x\n    check_cmd: x\n    description: X\n",
            encoding="utf-8"
        )
        bad_license = tmp_path / "license_metadata.yaml"
        bad_license.write_text(
            "tool_licenses:\n"
            "  x:\n"
            "    license: MIT\n"
            "    redistribution: totally-free\n"  # invalid value
            "    upstream_url: https://example.com\n",
            encoding="utf-8"
        )
        original_r = check_adapter_license_metadata.REGISTRY_FILE
        original_l = check_adapter_license_metadata.LICENSE_METADATA_FILE
        check_adapter_license_metadata.REGISTRY_FILE = bad_registry
        check_adapter_license_metadata.LICENSE_METADATA_FILE = bad_license
        try:
            findings = check_adapter_license_metadata.run_checks()
            error_kinds = {f.kind for f in findings if f.severity == "error"}
            assert "invalid-redistribution" in error_kinds
        finally:
            check_adapter_license_metadata.REGISTRY_FILE = original_r
            check_adapter_license_metadata.LICENSE_METADATA_FILE = original_l


# ===========================================================================
# check_deprecation_contracts.py tests
# ===========================================================================

class TestCheckDeprecationContracts:
    def test_script_exits_zero_on_clean_repo(self):
        """check_deprecation_contracts.py must exit 0 on clean repo."""
        result = _run_script("check_deprecation_contracts.py")
        assert result.returncode == 0, (
            f"check_deprecation_contracts.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "[deprecation] OK" in result.stdout

    def test_all_expected_aliases_are_present(self):
        """Every alias in EXPECTED_LEGACY_ALIASES must be in LEGACY_ALIAS_HINTS."""
        from saxoflow.cli_contracts import EXPECTED_LEGACY_ALIASES  # type: ignore
        from saxoflow.command_registry import get_legacy_alias_hints  # type: ignore
        hints = get_legacy_alias_hints()
        missing = [a for a in EXPECTED_LEGACY_ALIASES if a not in hints]
        assert not missing, f"Expected aliases not in LEGACY_ALIAS_HINTS: {missing}"

    def test_no_identity_mappings(self):
        """No alias should map to itself."""
        from saxoflow.command_registry import get_legacy_alias_hints  # type: ignore
        hints = get_legacy_alias_hints()
        identity = [k for k, v in hints.items() if k == " ".join(v.strip().split())]
        assert not identity, f"Identity-mapped aliases (no-op): {identity}"

    def test_all_hints_start_with_saxoflow(self):
        """All canonical hints must start with 'saxoflow '."""
        from saxoflow.command_registry import get_legacy_alias_hints  # type: ignore
        hints = get_legacy_alias_hints()
        bad = {k: v for k, v in hints.items() if v.strip() and not v.strip().startswith("saxoflow ")}
        assert not bad, f"Non-canonical hints: {bad}"

    def test_no_phase_cd_without_approval(self):
        """Phase C/D commands must be in REMOVAL_APPROVED before they can be removed."""
        from scripts.ci.check_deprecation_contracts import (  # type: ignore[import]
            PHASE_C_COMMANDS, PHASE_D_COMMANDS, REMOVAL_APPROVED,
        )
        unapproved_c = [c for c in PHASE_C_COMMANDS if c not in REMOVAL_APPROVED]
        unapproved_d = [c for c in PHASE_D_COMMANDS if c not in REMOVAL_APPROVED]
        assert not unapproved_c, f"Phase C commands without approval: {unapproved_c}"
        assert not unapproved_d, f"Phase D commands without approval: {unapproved_d}"

    def test_run_checks_returns_empty_on_clean_repo(self):
        """Direct run_checks() returns no errors on clean repo."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        findings = check_deprecation_contracts.run_checks()
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"

    def test_main_exit_zero(self):
        """main() exits 0 on clean repo."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        with patch("sys.argv", ["check_deprecation_contracts.py"]):
            rc = check_deprecation_contracts.main()
        assert rc == 0

    def test_main_exit_one_on_import_error(self):
        """main() exits 1 when run_checks returns errors."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        from scripts.ci.check_deprecation_contracts import Finding  # type: ignore[import]
        with patch.object(check_deprecation_contracts, "run_checks", return_value=[
            Finding("missing-alias", "saxoflow fake --broken", severity="error")
        ]):
            with patch("sys.argv", ["check_deprecation_contracts.py"]):
                rc = check_deprecation_contracts.main()
        assert rc == 1

    def test_run_checks_handles_import_error(self, monkeypatch):
        """run_checks returns import-error finding when saxoflow modules cannot be imported."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        import sys as _sys
        # Setting a module to None in sys.modules causes ImportError on 'from M import X'
        monkeypatch.setitem(_sys.modules, "saxoflow.cli_contracts", None)  # type: ignore[arg-type]
        findings = check_deprecation_contracts.run_checks()
        # Restore immediately so subsequent tests are unaffected
        monkeypatch.delitem(_sys.modules, "saxoflow.cli_contracts", raising=False)
        assert any(f.kind == "import-error" for f in findings)

    def test_run_checks_detects_empty_hint(self, tmp_path):
        """Empty hint should produce an empty-hint finding."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        from saxoflow.command_registry import get_canonical_commands  # type: ignore

        empty_hints = {"saxoflow init-env": ""}
        with patch("saxoflow.command_registry.get_legacy_alias_hints", return_value=empty_hints):
            with patch("saxoflow.cli_contracts.validate_legacy_alias_coverage") as mock_cov:
                mock_cov.return_value = type("R", (), {"missing": [], "unexpected": []})()
                findings = check_deprecation_contracts.run_checks()
        assert any(f.kind == "empty-hint" for f in findings)

    def test_run_checks_detects_phase_c_unapproved(self):
        """Phase C commands without approval should produce a finding."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        with patch.object(check_deprecation_contracts, "PHASE_C_COMMANDS", ("saxoflow old-cmd",)):
            with patch.object(check_deprecation_contracts, "REMOVAL_APPROVED", ()):
                with patch("saxoflow.command_registry.get_legacy_alias_hints", return_value={}):
                    with patch("saxoflow.cli_contracts.validate_legacy_alias_coverage") as mc:
                        mc.return_value = type("R", (), {"missing": [], "unexpected": []})()
                        findings = check_deprecation_contracts.run_checks()
        assert any(f.kind == "phase-c-unapproved" for f in findings)

    def test_run_checks_detects_phase_d_unapproved(self):
        """Phase D commands without approval should produce a finding."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        with patch.object(check_deprecation_contracts, "PHASE_D_COMMANDS", ("saxoflow removed-cmd",)):
            with patch.object(check_deprecation_contracts, "REMOVAL_APPROVED", ()):
                with patch("saxoflow.command_registry.get_legacy_alias_hints", return_value={}):
                    with patch("saxoflow.cli_contracts.validate_legacy_alias_coverage") as mc:
                        mc.return_value = type("R", (), {"missing": [], "unexpected": []})()
                        findings = check_deprecation_contracts.run_checks()
        assert any(f.kind == "phase-d-unapproved" for f in findings)

    def test_script_detects_missing_coverage(self):
        """run_checks should report missing-alias when an expected alias is absent."""
        from scripts.ci import check_deprecation_contracts  # type: ignore[import]
        from saxoflow.command_registry import get_legacy_alias_hints  # type: ignore
        from saxoflow.cli_contracts import EXPECTED_LEGACY_ALIASES  # type: ignore

        hints = dict(get_legacy_alias_hints())
        first_expected = list(EXPECTED_LEGACY_ALIASES)[0]
        hints.pop(first_expected, None)

        with patch("saxoflow.command_registry.get_legacy_alias_hints", return_value=hints):
            findings = check_deprecation_contracts.run_checks()

        error_kinds = {f.kind for f in findings if f.severity == "error"}
        assert "missing-alias" in error_kinds


# ===========================================================================
# check_command_parity.py (M1, regression check)
# ===========================================================================

class TestCheckCommandParityScript:
    def test_parity_script_passes(self):
        """Legacy check_command_parity.py (M1) must still exit 0."""
        result = _run_script("../check_command_parity.py")
        assert result.returncode == 0, (
            f"check_command_parity.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


# ===========================================================================
# Migration report generation (integration smoke)
# ===========================================================================

class TestMigrationReport:
    def test_can_generate_transition_report(self, tmp_path):
        """Verify migration report JSON can be generated from command_registry."""
        import datetime
        from saxoflow.command_registry import get_legacy_alias_hints, get_canonical_commands  # type: ignore

        alias_hints = get_legacy_alias_hints()
        canonical = get_canonical_commands()

        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_legacy_aliases": len(alias_hints),
            "total_canonical_commands": len(canonical),
            "alias_transition_map": alias_hints,
            "canonical_surfaces": canonical,
        }

        report_path = tmp_path / "transition_report.json"
        report_path.write_text(json.dumps(report, indent=2))

        loaded = json.loads(report_path.read_text())
        assert loaded["total_legacy_aliases"] > 0
        assert loaded["total_canonical_commands"] > 0
        assert isinstance(loaded["alias_transition_map"], dict)
        assert all(v.startswith("saxoflow ") for v in loaded["alias_transition_map"].values() if v)

    def test_report_has_utc_timestamp(self, tmp_path):
        """Report generated_at must include UTC indicator."""
        import datetime
        from saxoflow.command_registry import get_legacy_alias_hints, get_canonical_commands  # type: ignore

        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_legacy_aliases": len(get_legacy_alias_hints()),
            "total_canonical_commands": len(get_canonical_commands()),
        }
        assert "+" in report["generated_at"] or report["generated_at"].endswith("Z") or "+00:00" in report["generated_at"]


# ===========================================================================
# check_transition_closure.py tests (M8)
# ===========================================================================

class TestCheckTransitionClosure:
    @staticmethod
    def _module():
        from scripts.ci import check_transition_closure  # type: ignore[import]

        return check_transition_closure

    def _write_report(self, tmp_path: Path) -> Path:
        report = {
            "generated_at": "2026-03-26T00:00:00Z",
            "total_legacy_aliases": 38,
            "total_canonical_commands": 45,
            "alias_transition_map": {"saxoflow install": "saxoflow tool install"},
            "canonical_surfaces": ["saxoflow tool install"],
        }
        path = tmp_path / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def _write_evidence(self, tmp_path: Path, overrides: dict | None = None) -> Path:
        evidence = {
            "metadata": {"prepared_by": "qa", "release_cycle": "vX-rc"},
            "gate_a": {
                "legacy_mapping_coverage_pct": 100.0,
                "unmapped_invocations": 0,
                "parity_golden_tests_passed": True,
            },
            "gate_b": {
                "migration_success_rate_pct": 99.0,
                "schema_drift_count": 0,
                "rollback_restore_tests_passed": True,
            },
            "gate_c": {
                "canonical_docs_primary": True,
                "registry_only_completion": True,
                "techref_legacy_compatibility_marked": True,
            },
            "gate_d": {
                "real_pack_family_migration_green": True,
                "tutor_cohort_legacy_free": True,
                "researcher_cohort_legacy_free": True,
                "rc_unmapped_invocations": 0,
            },
            "cutover_policy": {
                "phase_c_requested": False,
                "phase_d_requested": False,
                "canonical_usage_pct": 85.0,
                "legacy_usage_pct_major_cycle": 4.9,
            },
        }
        if overrides:
            for k, v in overrides.items():
                if isinstance(v, dict) and isinstance(evidence.get(k), dict):
                    evidence[k].update(v)
                else:
                    evidence[k] = v
        path = tmp_path / "evidence.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        return path

    def test_script_exits_zero_on_valid_inputs(self, tmp_path):
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(tmp_path)
        out = tmp_path / "signoff.json"

        result = _run_script(
            "check_transition_closure.py",
            ["--report", str(report), "--evidence", str(evidence), "--output", str(out)],
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "pass"
        assert data["all_gates_green"] is True

    def test_script_fails_when_gate_a_coverage_below_100(self, tmp_path):
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(tmp_path, {"gate_a": {"legacy_mapping_coverage_pct": 99.0}})
        out = tmp_path / "signoff.json"
        result = _run_script(
            "check_transition_closure.py",
            ["--report", str(report), "--evidence", str(evidence), "--output", str(out)],
        )
        assert result.returncode == 1
        assert "gate-failed" in result.stdout

    def test_phase_c_blocked_when_canonical_usage_below_threshold(self, tmp_path):
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(
            tmp_path,
            {"cutover_policy": {"phase_c_requested": True, "canonical_usage_pct": 80.0}},
        )
        out = tmp_path / "signoff.json"
        result = _run_script(
            "check_transition_closure.py",
            ["--report", str(report), "--evidence", str(evidence), "--output", str(out)],
        )
        assert result.returncode == 1
        assert "phase-c-threshold" in result.stdout

    def test_phase_d_blocked_when_legacy_usage_not_below_5(self, tmp_path):
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(
            tmp_path,
            {"cutover_policy": {"phase_d_requested": True, "legacy_usage_pct_major_cycle": 5.0}},
        )
        out = tmp_path / "signoff.json"
        result = _run_script(
            "check_transition_closure.py",
            ["--report", str(report), "--evidence", str(evidence), "--output", str(out)],
        )
        assert result.returncode == 1
        assert "phase-d-threshold" in result.stdout

    def test_run_checks_missing_inputs(self):
        findings = self._module().run_checks({}, {})
        kinds = {f.kind for f in findings}
        assert "missing-migration-report" in kinds

    def test_run_checks_warns_for_phase_c_readiness_when_not_requested(self, tmp_path):
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(
            tmp_path,
            {"cutover_policy": {"phase_c_requested": False, "canonical_usage_pct": 50.0}},
        )
        m = self._module()
        findings = m.run_checks(
            json.loads(report.read_text(encoding="utf-8")),
            json.loads(evidence.read_text(encoding="utf-8")),
        )
        assert any(f.kind == "phase-c-readiness-warning" and f.severity == "warning" for f in findings)

    def test_build_signoff_reflects_pass_status(self, tmp_path):
        report = json.loads(self._write_report(tmp_path).read_text(encoding="utf-8"))
        evidence = json.loads(self._write_evidence(tmp_path).read_text(encoding="utf-8"))
        m = self._module()
        findings = m.run_checks(report, evidence)
        signoff = m._build_signoff(report, evidence, findings)
        assert signoff["status"] == "pass"
        assert signoff["all_gates_green"] is True
        assert signoff["errors"] == []

    def test_main_returns_failure_with_missing_inputs(self, tmp_path, monkeypatch):
        m = self._module()
        out = tmp_path / "signoff.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["check_transition_closure.py", "--report", str(tmp_path / "missing.json"), "--evidence", str(tmp_path / "missing_evidence.json"), "--output", str(out)],
        )
        rc = m.main()
        assert rc == 1
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["status"] == "fail"

    def test_main_returns_success_when_checks_pass(self, tmp_path, monkeypatch):
        m = self._module()
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(tmp_path)
        out = tmp_path / "signoff.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["check_transition_closure.py", "--report", str(report), "--evidence", str(evidence), "--output", str(out)],
        )
        rc = m.main()
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["status"] == "pass"

    def test_main_success_with_warning_only(self, tmp_path, monkeypatch):
        m = self._module()
        report = self._write_report(tmp_path)
        evidence = self._write_evidence(
            tmp_path,
            {"cutover_policy": {"phase_c_requested": False, "canonical_usage_pct": 70.0}},
        )
        out = tmp_path / "signoff.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["check_transition_closure.py", "--report", str(report), "--evidence", str(evidence), "--output", str(out)],
        )
        rc = m.main()
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert len(payload["warnings"]) >= 1


# ===========================================================================
# run_legacy_canonical_rehearsal.py tests (M8)
# ===========================================================================

class TestRunLegacyCanonicalRehearsal:
    @staticmethod
    def _module():
        from scripts.ci import run_legacy_canonical_rehearsal  # type: ignore[import]

        return run_legacy_canonical_rehearsal

    def _write_report(self, tmp_path: Path) -> Path:
        report = {
            "generated_at": "2026-03-26T00:00:00Z",
            "total_legacy_aliases": 3,
            "total_canonical_commands": 3,
            "alias_transition_map": {
                "saxoflow init-env": "saxoflow env init",
                "saxoflow formal": "saxoflow flow run rtl_to_formal",
                "saxoflow teach status": "saxoflow teach session status",
            },
            "canonical_surfaces": [
                "saxoflow env init",
                "saxoflow flow run",
                "saxoflow teach session status",
            ],
        }
        path = tmp_path / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def _write_scenario(self, tmp_path: Path, include_unmapped: bool = False) -> Path:
        scenario = {
            "metadata": {"description": "test"},
            "cohorts": {
                "student": ["saxoflow init-env"],
                "tutor": ["saxoflow teach status"],
                "researcher": ["saxoflow formal"],
            },
        }
        if include_unmapped:
            scenario["cohorts"]["student"].append("saxoflow unknown")
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(scenario), encoding="utf-8")
        return path

    def test_script_exits_zero_for_valid_rehearsal(self, tmp_path):
        report = self._write_report(tmp_path)
        scenario = self._write_scenario(tmp_path)
        out = tmp_path / "rehearsal.json"
        result = _run_script(
            "run_legacy_canonical_rehearsal.py",
            ["--report", str(report), "--scenario", str(scenario), "--output", str(out)],
        )
        assert result.returncode == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["status"] == "pass"

    def test_script_fails_for_unmapped_command(self, tmp_path):
        report = self._write_report(tmp_path)
        scenario = self._write_scenario(tmp_path, include_unmapped=True)
        out = tmp_path / "rehearsal.json"
        result = _run_script(
            "run_legacy_canonical_rehearsal.py",
            ["--report", str(report), "--scenario", str(scenario), "--output", str(out)],
        )
        assert result.returncode == 1
        assert "unmapped-command" in result.stdout

    def test_run_checks_missing_inputs(self):
        findings = self._module().run_checks({}, {})
        kinds = {f.kind for f in findings}
        assert "missing-report" in kinds

    def test_run_checks_rejects_empty_cohorts(self, tmp_path):
        report = json.loads(self._write_report(tmp_path).read_text(encoding="utf-8"))
        findings = self._module().run_checks(report, {"cohorts": {}})
        assert any(f.kind == "missing-cohorts" for f in findings)

    def test_main_success_and_artifact(self, tmp_path, monkeypatch):
        m = self._module()
        report = self._write_report(tmp_path)
        scenario = self._write_scenario(tmp_path)
        out = tmp_path / "rehearsal.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_legacy_canonical_rehearsal.py",
                "--report",
                str(report),
                "--scenario",
                str(scenario),
                "--output",
                str(out),
            ],
        )
        rc = m.main()
        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "pass"

    def test_main_failure_with_missing_files(self, tmp_path, monkeypatch):
        m = self._module()
        out = tmp_path / "rehearsal.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_legacy_canonical_rehearsal.py",
                "--report",
                str(tmp_path / "missing-report.json"),
                "--scenario",
                str(tmp_path / "missing-scenario.json"),
                "--output",
                str(out),
            ],
        )
        rc = m.main()
        assert rc == 1
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "fail"


# ===========================================================================
# evaluate_transition_telemetry.py tests (M8)
# ===========================================================================

class TestEvaluateTransitionTelemetry:
    @staticmethod
    def _module():
        from scripts.ci import evaluate_transition_telemetry  # type: ignore[import]

        return evaluate_transition_telemetry

    def _write_history(self, tmp_path: Path, good: bool = True) -> Path:
        payload = {
            "metadata": {"source": "tests"},
            "samples": [
                {
                    "release": "v1.2.0",
                    "cycle_type": "minor",
                    "canonical_usage_pct": 86.0 if good else 80.0,
                    "legacy_usage_pct": 6.0,
                },
                {
                    "release": "v2.0.0",
                    "cycle_type": "major",
                    "canonical_usage_pct": 87.0,
                    "legacy_usage_pct": 4.5 if good else 5.2,
                },
            ],
        }
        path = tmp_path / "history.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_script_exits_zero_for_phase_c_ready_window(self, tmp_path):
        history = self._write_history(tmp_path, good=True)
        out = tmp_path / "summary.json"
        result = _run_script(
            "evaluate_transition_telemetry.py",
            ["--history", str(history), "--output", str(out), "--require-phase-c-ready"],
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "pass"
        assert data["phase_c_ready"] is True

    def test_script_fails_when_phase_c_threshold_not_met(self, tmp_path):
        history = self._write_history(tmp_path, good=False)
        out = tmp_path / "summary.json"
        result = _run_script(
            "evaluate_transition_telemetry.py",
            ["--history", str(history), "--output", str(out), "--require-phase-c-ready"],
        )
        assert result.returncode == 1
        assert "phase-c-usage-window" in result.stdout

    def test_run_checks_missing_inputs(self):
        findings = self._module().run_checks({}, require_phase_c_ready=True, require_phase_d_ready=False)
        assert any(f.kind == "missing-usage-history" for f in findings)

    def test_run_checks_missing_samples(self):
        findings = self._module().run_checks({"metadata": {}}, require_phase_c_ready=False, require_phase_d_ready=False)
        assert any(f.kind == "missing-samples" for f in findings)

    def test_run_checks_invalid_cycle_type(self):
        history = {
            "samples": [
                {"release": "v1", "cycle_type": "weekly", "canonical_usage_pct": 90, "legacy_usage_pct": 3}
            ]
        }
        findings = self._module().run_checks(history, require_phase_c_ready=False, require_phase_d_ready=False)
        assert any(f.kind == "invalid-cycle-type" for f in findings)

    def test_main_success(self, tmp_path, monkeypatch):
        m = self._module()
        history = self._write_history(tmp_path, good=True)
        out = tmp_path / "summary.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "evaluate_transition_telemetry.py",
                "--history",
                str(history),
                "--output",
                str(out),
                "--require-phase-c-ready",
            ],
        )
        rc = m.main()
        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["phase_c_ready"] is True

    def test_main_failure(self, tmp_path, monkeypatch):
        m = self._module()
        history = self._write_history(tmp_path, good=False)
        out = tmp_path / "summary.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "evaluate_transition_telemetry.py",
                "--history",
                str(history),
                "--output",
                str(out),
                "--require-phase-c-ready",
            ],
        )
        rc = m.main()
        assert rc == 1
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "fail"


# ===========================================================================
# approve_transition_release.py tests (M8)
# ===========================================================================

class TestApproveTransitionRelease:
    @staticmethod
    def _module():
        from scripts.ci import approve_transition_release  # type: ignore[import]

        return approve_transition_release

    def _write_inputs(self, tmp_path: Path, approved: bool = True, phase: str = "phase_c") -> tuple[Path, Path, Path, Path]:
        signoff = {
            "status": "pass" if approved else "fail",
            "all_gates_green": approved,
        }
        rehearsal = {"status": "pass" if approved else "fail"}
        telemetry = {
            "status": "pass" if approved else "fail",
            "phase_c_ready": approved,
            "phase_d_ready": approved,
        }
        plan = {
            "target_phase": phase,
            "support_window": {
                "announced_in_release": "v1.7.0",
                "removal_target_release": "v2.1.0",
            },
            "approvals": {
                "release_manager": True,
                "docs_owner": True,
                "cli_owner": True,
            },
        }
        signoff_path = tmp_path / "signoff.json"
        rehearsal_path = tmp_path / "rehearsal.json"
        telemetry_path = tmp_path / "telemetry.json"
        plan_path = tmp_path / "plan.json"
        signoff_path.write_text(json.dumps(signoff), encoding="utf-8")
        rehearsal_path.write_text(json.dumps(rehearsal), encoding="utf-8")
        telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return signoff_path, rehearsal_path, telemetry_path, plan_path

    def test_script_exits_zero_for_approved_phase_c(self, tmp_path):
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_c")
        out = tmp_path / "approval.json"
        result = _run_script(
            "approve_transition_release.py",
            [
                "--signoff", str(signoff),
                "--rehearsal", str(rehearsal),
                "--telemetry", str(telemetry),
                "--plan", str(plan),
                "--output", str(out),
            ],
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "approved"

    def test_script_fails_when_required_approval_missing(self, tmp_path):
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_c")
        plan_payload = json.loads(plan.read_text(encoding="utf-8"))
        plan_payload["approvals"]["cli_owner"] = False
        plan.write_text(json.dumps(plan_payload), encoding="utf-8")
        out = tmp_path / "approval.json"
        result = _run_script(
            "approve_transition_release.py",
            [
                "--signoff", str(signoff),
                "--rehearsal", str(rehearsal),
                "--telemetry", str(telemetry),
                "--plan", str(plan),
                "--output", str(out),
            ],
        )
        assert result.returncode == 1
        assert "missing-approval" in result.stdout

    def test_run_checks_missing_inputs(self):
        findings = self._module().run_checks({}, {}, {}, {})
        assert any(f.kind == "missing-signoff" for f in findings)

    def test_run_checks_blocks_phase_d_without_readiness(self, tmp_path):
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_d")
        telemetry_payload = json.loads(telemetry.read_text(encoding="utf-8"))
        telemetry_payload["phase_d_ready"] = False
        telemetry.write_text(json.dumps(telemetry_payload), encoding="utf-8")
        findings = self._module().run_checks(
            json.loads(signoff.read_text(encoding="utf-8")),
            json.loads(rehearsal.read_text(encoding="utf-8")),
            json.loads(telemetry.read_text(encoding="utf-8")),
            json.loads(plan.read_text(encoding="utf-8")),
        )
        assert any(f.kind == "phase-d-not-ready" for f in findings)

    def test_run_checks_rejects_invalid_target_phase(self, tmp_path):
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_x")
        findings = self._module().run_checks(
            json.loads(signoff.read_text(encoding="utf-8")),
            json.loads(rehearsal.read_text(encoding="utf-8")),
            json.loads(telemetry.read_text(encoding="utf-8")),
            json.loads(plan.read_text(encoding="utf-8")),
        )
        assert any(f.kind == "invalid-target-phase" for f in findings)

    def test_run_checks_requires_approvals_object(self, tmp_path):
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_c")
        payload = json.loads(plan.read_text(encoding="utf-8"))
        payload["approvals"] = []
        plan.write_text(json.dumps(payload), encoding="utf-8")
        findings = self._module().run_checks(
            json.loads(signoff.read_text(encoding="utf-8")),
            json.loads(rehearsal.read_text(encoding="utf-8")),
            json.loads(telemetry.read_text(encoding="utf-8")),
            json.loads(plan.read_text(encoding="utf-8")),
        )
        assert any(f.kind == "missing-approvals" for f in findings)

    def test_run_checks_requires_support_window_fields(self, tmp_path):
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_c")
        payload = json.loads(plan.read_text(encoding="utf-8"))
        payload["support_window"] = {}
        plan.write_text(json.dumps(payload), encoding="utf-8")
        findings = self._module().run_checks(
            json.loads(signoff.read_text(encoding="utf-8")),
            json.loads(rehearsal.read_text(encoding="utf-8")),
            json.loads(telemetry.read_text(encoding="utf-8")),
            json.loads(plan.read_text(encoding="utf-8")),
        )
        kinds = {f.kind for f in findings}
        assert "missing-announcement" in kinds
        assert "missing-removal-target" in kinds

    def test_main_success(self, tmp_path, monkeypatch):
        m = self._module()
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=True, phase="phase_c")
        out = tmp_path / "approval.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "approve_transition_release.py",
                "--signoff", str(signoff),
                "--rehearsal", str(rehearsal),
                "--telemetry", str(telemetry),
                "--plan", str(plan),
                "--output", str(out),
            ],
        )
        rc = m.main()
        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "approved"

    def test_main_failure(self, tmp_path, monkeypatch):
        m = self._module()
        signoff, rehearsal, telemetry, plan = self._write_inputs(tmp_path, approved=False, phase="phase_c")
        out = tmp_path / "approval.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "approve_transition_release.py",
                "--signoff", str(signoff),
                "--rehearsal", str(rehearsal),
                "--telemetry", str(telemetry),
                "--plan", str(plan),
                "--output", str(out),
            ],
        )
        rc = m.main()
        assert rc == 1
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "blocked"



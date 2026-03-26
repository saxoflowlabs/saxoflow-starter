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



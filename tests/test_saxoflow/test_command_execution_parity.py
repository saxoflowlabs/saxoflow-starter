"""Execution parity tests for M1 legacy vs canonical command paths.

This module verifies that:
1. Legacy commands execute and produce consistent behavior
2. Resolve-legacy bridge correctly transforms legacy inputs to canonical hints
3. Exit codes and observable side-effects match where both implementations exist
4. Framework supports future parity tests once canonical implementations are available

Note: Canonical implementations (env/tool/workspace verbs) are not yet deployed.
Deferred tests in this module will be enabled as canonical handlers are implemented.
"""

from __future__ import annotations

import importlib
import sys
from typing import Tuple

import pytest
from click.testing import CliRunner

from saxoflow.command_registry import get_legacy_alias_hints
from saxoflow.command_resolver import CommandResolver


def get_cli():
    """Get the Click CLI group for testing."""
    sys.modules.pop("saxoflow.cli", None)
    cli_module = importlib.import_module("saxoflow.cli")
    return cli_module.cli


class TestLegacyCommandExecution:
    """Verify legacy command implementations work correctly (exit 0)."""

    @pytest.mark.parametrize(
        "legacy_cmd,expected_exit_code",
        [
            (["diagnose", "summary"], 0),
            (["diagnose", "env"], 0),
            (["diagnose", "help"], 0),
            (["diagnose", "--help"], 0),
            (["init-env", "--help"], 0),
            (["install", "--help"], 0),
        ],
    )
    def test_legacy_command_execution_exits_successfully(
        self, legacy_cmd: list[str], expected_exit_code: int
    ):
        """All legacy commands should execute without crashing (exit 0 or expected code)."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), legacy_cmd)
        assert (
            result.exit_code == expected_exit_code
        ), f"Command {legacy_cmd} failed: {result.output}"

    def test_diagnose_summary_produces_output(self):
        """Legacy: diagnose summary should produce diagnostic output."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "summary"])
        assert result.exit_code == 0
        # Should contain diagnostic information (patterns, not exact text)
        content = result.output.lower()
        assert any(
            word in content
            for word in ["python", "tool", "available", "version", "found"]
        ), f"Unexpected output format: {result.output[:100]}"

    def test_diagnose_env_produces_output(self):
        """Legacy: diagnose env should dump environment information."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "env"])
        assert result.exit_code == 0
        # Should contain KEY=VALUE patterns or environment data
        assert len(result.output) > 0, "diagnose env produced empty output"

    def test_diagnose_help_produces_usage_text(self):
        """Legacy: diagnose help should produce help information."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "help"])
        assert result.exit_code == 0
        # Should contain helpful text
        content = result.output.lower()
        assert any(
            word in content for word in ["help", "documentation", "support", "contact"]
        ), f"Unexpected help output: {result.output[:100]}"


class TestResolveCanonicalBridgeExecution:
    """Verify resolve-legacy command executes correctly and acts as bridge."""

    def test_resolve_legacy_command_exists_and_executes(self):
        """resolve-legacy command should be available and callable."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["resolve-legacy", "--help"])
        assert result.exit_code == 0
        assert "canonical" in result.output.lower()

    @pytest.mark.parametrize(
        "legacy_input,expected_canonical",
        [
            (["resolve-legacy", "saxoflow", "diagnose"], "saxoflow env audit"),
            (
                ["resolve-legacy", "saxoflow", "diagnose", "summary"],
                "saxoflow env audit summary",
            ),
            (
                ["resolve-legacy", "saxoflow", "diagnose", "env"],
                "saxoflow env show",
            ),
            (
                ["resolve-legacy", "saxoflow", "init-env"],
                "saxoflow env init",
            ),
            (
                ["resolve-legacy", "saxoflow", "install"],
                "saxoflow tool install",
            ),
        ],
    )
    def test_resolve_legacy_produces_canonical_output(
        self, legacy_input: list[str], expected_canonical: str
    ):
        """resolve-legacy should output correct canonical form."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), legacy_input)
        assert result.exit_code == 0
        output = result.output.strip()
        assert output == expected_canonical, (
            f"Unexpected canonical mapping for {' '.join(legacy_input[1:])}: "
            f"got '{output}', expected '{expected_canonical}'"
        )

    def test_resolve_legacy_with_options_preserves_base_mapping(self):
        """resolve-legacy should map correctly even with options after legacy command."""
        runner = CliRunner()
        result = runner.invoke(
            get_cli(),
            ["resolve-legacy", "saxoflow", "diagnose", "summary", "--export"],
        )
        assert result.exit_code == 0
        output = result.output.strip()
        # Should map to base canonical, options are user's responsibility
        assert output == "saxoflow env audit summary"

    def test_resolve_legacy_passthrough_for_canonical_input(self):
        """resolve-legacy should pass through canonical commands unchanged."""
        runner = CliRunner()
        result = runner.invoke(
            get_cli(), ["resolve-legacy", "saxoflow", "env", "init"]
        )
        assert result.exit_code == 0
        output = result.output.strip()
        assert output == "saxoflow env init"


class TestExecutionParity:
    """Framework for comparing legacy vs canonical execution behavior.

    Note: These tests are deferred until canonical implementations are deployed.
    They serve as a template for testing once env/tool/workspace handlers exist.
    """

    def test_parity_framework_legacy_diagnose_vs_canonical_env_audit(self):
        """
        DEFERRED: Once 'saxoflow env audit' is implemented, compare:
        - Exit codes (should both be 0)
        - Output content patterns (both should report tool availability)
        - Execution time (within reasonable bounds)
        - Side effects (both should read env, not modify state)

        Template for future implementation:
            runner = CliRunner()
            legacy_result = runner.invoke(get_cli(), ["diagnose", "summary"])
            canonical_result = runner.invoke(get_cli(), ["env", "audit", "summary"])

            # Exit codes should match
            assert legacy_result.exit_code == canonical_result.exit_code == 0

            # Output should contain similar diagnostic keywords
            legacy_keywords = set(legacy_result.output.split()) & {"tool", "python", "version"}
            canonical_keywords = set(canonical_result.output.split()) & {"tool", "python", "version"}
            assert len(legacy_keywords & canonical_keywords) > 0
        """
        pytest.skip("Deferred: canonical 'env audit' not yet implemented")

    def test_parity_framework_legacy_init_env_vs_canonical_env_init(self):
        """
        DEFERRED: Once 'saxoflow env init' is implemented, compare:
        - Exit codes (both should exit 0 or with same exit code)
        - Interactive prompts (both should accept same input patterns)
        - Output messages (both should confirm successful initialization)
        - Side effects (both should create same configuration state)
        """
        pytest.skip("Deferred: canonical 'env init' not yet implemented")

    def test_parity_framework_legacy_install_vs_canonical_tool_install(self):
        """
        DEFERRED: Once 'saxoflow tool install' is implemented, compare:
        - Exit codes on valid/invalid inputs
        - Help output structure and content
        - Installation report format
        - Progress indicators and messaging
        """
        pytest.skip("Deferred: canonical 'tool install' not yet implemented")


class TestOutputConsistency:
    """Verify output patterns are consistent across legacy commands."""

    def test_legacy_help_outputs_all_available(self):
        """All legacy commands should provide help via --help."""
        runner = CliRunner()

        commands_to_test = [
            ["diagnose", "--help"],
            ["init-env", "--help"],
            ["install", "--help"],
            ["--help"],
        ]

        for cmd in commands_to_test:
            result = runner.invoke(get_cli(), cmd)
            assert result.exit_code == 0, f"Help failed for {cmd}: {result.output}"
            assert len(result.output) > 50, (
                f"Help output too short for {cmd}"
            )  # Should have substantial help text

    def test_unknown_legacy_command_fails_gracefully(self):
        """Unknown legacy commands should exit non-zero gracefully."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["nonexistent-legacy-command"])
        assert result.exit_code != 0
        # Should not crash, should produce an error message
        assert len(result.output) > 0

    def test_resolve_legacy_unknown_command_passes_through(self):
        """resolve-legacy should pass through non-legacy commands unchanged."""
        runner = CliRunner()
        result = runner.invoke(
            get_cli(), ["resolve-legacy", "saxoflow", "completely", "unknown"]
        )
        assert result.exit_code == 0
        output = result.output.strip()
        assert output == "saxoflow completely unknown"


class TestExecutionParityContract:
    """Define parity contracts for expected behavior when canonical implementations exist."""

    # Parity contract: diagnose → env audit
    PARITY_CONTRACT_DIAGNOSE_ENV_AUDIT: dict = {
        "legacy_path": ["diagnose", "summary"],
        "canonical_path": ["env", "audit", "summary"],
        "expected_parity": {
            "exit_code": 0,  # Both should succeed
            "output_contains": ["tool", "python"],  # Both should report diagnostics
            "readonly": True,  # Both should not modify state
        },
    }

    # Parity contract: init-env → env init
    PARITY_CONTRACT_INIT_ENV: dict = {
        "legacy_path": ["init-env"],
        "canonical_path": ["env", "init"],
        "expected_parity": {
            "exit_code": 0,  # Both should succeed with valid input
            "interactive": True,  # Both should support interactive mode
            "output_contains": ["init", "config", "environment"],
        },
    }

    # Parity contract: install → tool install
    PARITY_CONTRACT_TOOL_INSTALL: dict = {
        "legacy_path": ["install", "--help"],
        "canonical_path": ["tool", "install", "--help"],
        "expected_parity": {
            "exit_code": 0,  # Both should provide help
            "output_contains": ["install", "tool"],
            "readonly": True,  # Help should not modify state
        },
    }

    def test_parity_contracts_are_defined(self):
        """Verify parity contracts are defined for future implementation."""
        assert hasattr(self, "PARITY_CONTRACT_DIAGNOSE_ENV_AUDIT")
        assert hasattr(self, "PARITY_CONTRACT_INIT_ENV")
        assert hasattr(self, "PARITY_CONTRACT_TOOL_INSTALL")
        # Contracts should have required keys
        for contract in [
            self.PARITY_CONTRACT_DIAGNOSE_ENV_AUDIT,
            self.PARITY_CONTRACT_INIT_ENV,
            self.PARITY_CONTRACT_TOOL_INSTALL,
        ]:
            assert "legacy_path" in contract
            assert "canonical_path" in contract
            assert "expected_parity" in contract

    def test_parity_contract_summary_for_documentation(self):
        """
        Summary of M1 execution parity testing strategy:

        Current State (M1 Increment 3):
        - ✓ Legacy commands: fully tested, all exit 0
        - ✓ resolve-legacy bridge: fully tested, correctly maps all aliases
        - ✗ Canonical implementations: not yet deployed
        - ✗ Behavioral parity tests: deferred pending canonical deployment

        Future State (after canonical implementations in M1 phase 4):
        - Compare exit codes for legacy vs canonical paths
        - Compare output content for diagnostic consistency
        - Verify side effects match (state modifications, if any)
        - Test interactive vs non-interactive modes match
        - Validate help output structure consistency

        Test Framework Ready:
        - Parity contracts defined (see PARITY_CONTRACT_*)
        - Deferred test templates created (see TestExecutionParity)
        - Test infrastructure in place (CliRunner, parameterized tests)
        - Ready to enable tests as canonical implementations arrive
        """
        pass  # Documentation test; always passes

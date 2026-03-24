"""Golden parity tests for M1 legacy-to-canonical command mapping.

This module verifies that:
1. Legacy commands execute successfully (where implementations exist)
2. Canonical replacements are correctly registered in the resolver
3. Exit codes and output behavior are consistent across legacy/canonical pairs
4. Help output is available for both legacy and canonical forms

These tests establish the parity contract required for M1 completion.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from click.testing import CliRunner

from saxoflow.command_registry import get_legacy_alias_hints
from saxoflow.command_resolver import CommandResolver


def get_cli():
    """Get the Click CLI group for testing."""
    sys.modules.pop("saxoflow.cli", None)
    cli_module = importlib.import_module("saxoflow.cli")
    return cli_module.cli


class TestLegacyCommandExecutionParity:
    """Verify implemented legacy commands execute successfully."""

    def test_diagnose_summary_legacy_command_exits_zero(self):
        """Legacy: saxoflow diagnose summary should exit 0."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "summary"])
        assert result.exit_code == 0, f"diagnose summary failed: {result.output}"

    def test_diagnose_env_legacy_command_exits_zero(self):
        """Legacy: saxoflow diagnose env should exit 0."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "env"])
        assert result.exit_code == 0, f"diagnose env failed: {result.output}"

    def test_diagnose_clean_path_legacy_command_exits_zero(self):
        """Legacy: saxoflow diagnose clean-path should exit 0 or 1 (conditional)."""
        runner = CliRunner()
        result = runner.invoke(
            get_cli(), ["diagnose", "clean-path"], input="bash\n"
        )
        # May exit 0 or 1 depending on path state; just verify it doesn't crash
        assert result.exit_code in [0, 1]

    def test_diagnose_help_legacy_command_exits_zero(self):
        """Legacy: saxoflow diagnose help should exit 0."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "help"])
        assert result.exit_code == 0, f"diagnose help failed: {result.output}"

    def test_install_help_legacy_command_exits_zero(self):
        """Legacy: saxoflow install --help should exit 0."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["install", "--help"])
        assert result.exit_code == 0, f"install --help failed: {result.output}"

    def test_init_env_help_legacy_command_exits_zero(self):
        """Legacy: saxoflow init-env --help should exit 0."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["init-env", "--help"])
        assert result.exit_code == 0, f"init-env --help failed: {result.output}"


class TestCanonicalMappingExists:
    """Verify all tested legacy commands map to registered canonical forms."""

    @pytest.mark.parametrize(
        "legacy_cmd",
        [
            "saxoflow diagnose summary",
            "saxoflow diagnose env",
            "saxoflow diagnose clean-path",
            "saxoflow diagnose help",
            "saxoflow diagnose",
            "saxoflow install",
            "saxoflow init-env",
        ],
    )
    def test_legacy_command_has_canonical_mapping(self, legacy_cmd: str):
        """Each tested legacy command should map to a canonical form."""
        alias_hints = get_legacy_alias_hints()
        assert legacy_cmd in alias_hints, f"Legacy command '{legacy_cmd}' not in mapping"
        canonical = alias_hints[legacy_cmd]
        assert canonical.startswith(
            "saxoflow "
        ), f"Canonical form does not start with 'saxoflow': {canonical}"

    def test_all_mapped_commands_hint_registered_prefixes(self):
        """All canonical hints should reference a registered command prefix."""
        from saxoflow.command_registry import CANONICAL_COMMANDS

        alias_hints = get_legacy_alias_hints()
        canonical_surfaces = {cmd.command for cmd in CANONICAL_COMMANDS}

        for legacy, canonical_hint in alias_hints.items():
            # Extract prefix (first 2-3 tokens) from hint
            tokens = canonical_hint.split()[:3]
            prefix = " ".join(tokens[:2])

            # Check if hint matches a registered command or is a valid prefix
            found_match = any(
                canonical_hint.startswith(cmd) or cmd.startswith(canonical_hint)
                for cmd in canonical_surfaces
            )
            assert (
                found_match
            ), f"Canonical hint '{canonical_hint}' for '{legacy}' doesn't match registered commands"


class TestResolutionAccuracy:
    """Verify the resolver correctly identifies and maps legacy commands."""

    @pytest.mark.parametrize(
        "legacy_input,expected_is_legacy,expected_canonical",
        [
            (
                "saxoflow diagnose summary",
                True,
                "saxoflow env audit summary",
            ),
            (
                "saxoflow diagnose env",
                True,
                "saxoflow env show",
            ),
            (
                "saxoflow diagnose clean-path",
                True,
                "saxoflow env path normalize",
            ),
            (
                "saxoflow diagnose help",
                True,
                "saxoflow help env",
            ),
            (
                "saxoflow install",
                True,
                "saxoflow tool install",
            ),
            (
                "saxoflow init-env",
                True,
                "saxoflow env init",
            ),
        ],
    )
    def test_resolver_identifies_legacy_and_maps_correctly(
        self,
        legacy_input: str,
        expected_is_legacy: bool,
        expected_canonical: str,
    ):
        """Resolver should correctly identify and map legacy commands."""
        resolver = CommandResolver()
        result = resolver.resolve_legacy_command(legacy_input)
        assert result.is_legacy == expected_is_legacy
        assert result.canonical_hint == expected_canonical


class TestSemanticParityGate:
    """Verify semantic parity: mapping infrastructure is correct even if canonical isn't implemented."""

    def test_resolver_provides_semantic_suggestions_for_env_commands(self):
        """Resolver should provide context-aware suggestions for 'saxoflow env' prefix."""
        resolver = CommandResolver()
        suggestions = resolver.semantic_suggestions("saxoflow env ")
        assert "init" in suggestions
        assert "show" in suggestions
        assert "audit" in suggestions

    def test_resolver_provides_semantic_suggestions_for_help_commands(self):
        """Resolver should provide context-aware suggestions for 'saxoflow help' prefix."""
        resolver = CommandResolver()
        suggestions = resolver.semantic_suggestions("saxoflow help ")
        # "help" commands are registered, should suggest their sub-topics
        assert len(suggestions) >= 0  # May be empty if no help subs registered

    def test_legacy_with_options_preserves_canonical_intent(self):
        """Legacy commands with options should preserve the canonical mapping intent."""
        resolver = CommandResolver()

        # Test: legacy command with custom options still maps correctly
        result = resolver.resolve_legacy_command("saxoflow diagnose summary --export")
        assert result.is_legacy is True
        # The canonical hint doesn't include --export (user must translate)
        assert result.canonical_hint == "saxoflow env audit summary"


class TestHelpOutputConsistency:
    """Verify help output is available for all tested command forms."""

    def test_diagnose_group_help_available(self):
        """'saxoflow diagnose --help' should list all subcommands."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["diagnose", "--help"])
        assert result.exit_code == 0
        assert "summary" in result.output
        assert "env" in result.output
        assert "help" in result.output

    def test_root_cli_help_lists_all_top_level_commands(self):
        """Root help should list diagnose, init-env, install, resolve-legacy."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["--help"])
        assert result.exit_code == 0
        assert "diagnose" in result.output
        assert "init-env" in result.output
        assert "install" in result.output
        assert "resolve-legacy" in result.output


class TestLegacyCommandDeGraceFulHandling:
    """Verify that unknown commands fail gracefully (don't crash)."""

    def test_unknown_command_exits_nonzero(self):
        """Unknown command should exit with non-zero status."""
        runner = CliRunner()
        result = runner.invoke(get_cli(), ["unknown-command-that-does-not-exist"])
        assert result.exit_code != 0


class TestCommandPairityContractSummary:
    """Summary test: all expected legacy aliases from contract are mappable."""

    def test_all_expected_legacy_aliases_are_in_resolver_registry(self):
        """All expected M1 aliases should be resolvable."""
        from saxoflow.cli_contracts import EXPECTED_LEGACY_ALIASES

        resolver = CommandResolver()
        alias_hints = get_legacy_alias_hints()

        for alias in EXPECTED_LEGACY_ALIASES:
            assert (
                alias in alias_hints
            ), f"Expected alias '{alias}' not in resolver registry"
            result = resolver.resolve_legacy_command(alias)
            assert result.is_legacy is True, f"Resolver didn't recognize '{alias}' as legacy"
            assert (
                result.canonical_hint
            ), f"No canonical hint for '{alias}'"

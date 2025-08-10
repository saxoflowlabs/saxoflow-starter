# """
# Integration tests for the saxoflow diagnose command group.

# These tests exercise the `diagnose` Click commands by invoking them
# through `CliRunner`.  To avoid touching the real system, the
# `diagnose_tools.compute_health` and `diagnose_tools.analyze_env` functions
# are monkeypatched to return deterministic values.  The tests then
# verify that the CLI output includes expected summaries or warnings.
# """

# from click.testing import CliRunner
# import importlib
# from unittest import mock

# import saxoflow.diagnose as diagnose_module


# def _mock_health():
#     # flow, score, required, optional
#     required = [
#         ("yosys", True, "/usr/bin/yosys", "0.27", True),
#         ("iverilog", False, None, None, False)
#     ]
#     optional = [
#         ("verilator", True, "/usr/bin/verilator", "5.0", True),
#         ("vscode", False, None, None, False)
#     ]
#     return "minimal", 50, required, optional


# def _mock_env():
#     return {
#         "path_duplicates": [("/usr/bin", ["yosys"])],
#         "bins_missing_in_path": [("/home/user/.local/yosys/bin", "yosys")],
#     }


# def test_diagnose_summary_cli(monkeypatch):
#     """diagnose summary prints a health score and tool statuses."""
#     # Monkeypatch compute_health and analyze_env
#     monkeypatch.setattr(diagnose_module, "diagnose_tools", mock.Mock())
#     diagnose_module.diagnose_tools.compute_health.return_value = _mock_health()
#     diagnose_module.diagnose_tools.analyze_env.return_value = {
#         "path_duplicates": [],
#         "bins_missing_in_path": []
#     }
#     runner = CliRunner()
#     result = runner.invoke(diagnose_module.diagnose, ["summary"])
#     assert result.exit_code == 0
#     output = result.output
#     assert "Health Score" in output
#     assert "50%" in output  # our mocked score leads to 50
#     assert "iverilog missing" in output.lower()  # our first required tool missing should produce message


# def test_diagnose_env_cli():
#     """diagnose env prints environment variables without errors."""
#     runner = CliRunner()
#     result = runner.invoke(diagnose_module.diagnose, ["env"])
#     assert result.exit_code == 0
#     assert "VIRTUAL_ENV" in result.output


# def test_diagnose_help_cli():
#     """diagnose help prints support links."""
#     runner = CliRunner()
#     result = runner.invoke(diagnose_module.diagnose, ["help"])
#     assert result.exit_code == 0
#     output = result.output
#     assert "Support" in output
#     assert "documentation" in output.lower()
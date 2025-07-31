"""
Tests for cool_cli.panels module.

These tests instantiate a variety of panel helper functions and
validate that they return `Panel` objects of the correct type.  We
also verify that the content passed into the panel appears in the
renderable so that the panels can be used reliably in the CLI.
"""

from rich.panel import Panel
from cool_cli.coolcli import panels


def test_welcome_panel_returns_panel():
    panel = panels.welcome_panel("Welcome to SaxoFlow")
    assert isinstance(panel, Panel)
    assert "Welcome to SaxoFlow" in panel.renderable.plain


def test_error_panel_formats_message():
    panel = panels.error_panel("something went wrong")
    assert isinstance(panel, Panel)
    assert "Error: something went wrong" in panel.renderable.plain
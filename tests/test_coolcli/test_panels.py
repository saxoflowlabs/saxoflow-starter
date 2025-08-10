# # tests/test_coolcli/test_panels.py
# from __future__ import annotations

# from rich.panel import Panel
# from rich.text import Text


# def test_welcome_panel_returns_panel(panels_mod):
#     panel = panels_mod.welcome_panel("Welcome to SaxoFlow", panel_width=99)
#     assert isinstance(panel, Panel)
#     assert "Welcome to SaxoFlow" in panel.renderable.plain
#     assert panel.width == 99
#     assert panel.border_style == "cyan"
#     assert panel.title == "saxoflow"


# def test_error_panel_formats_message(panels_mod):
#     panel = panels_mod.error_panel("something went wrong", width=77)
#     assert isinstance(panel, Panel)
#     assert "Error: something went wrong" in panel.renderable.plain
#     assert panel.title == "error"
#     assert panel.border_style == "red"
#     assert panel.width == 77


# def test_user_input_panel_formats_correctly_and_wraps(panels_mod, monkeypatch):
#     # Pin width to make behavior deterministic
#     monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 70)
#     msg = "User typed this " * 5  # long text to trigger wrapping attributes
#     panel = panels_mod.user_input_panel(msg)
#     assert isinstance(panel, Panel)
#     assert panel.title == "user"
#     assert panel.border_style == "cyan"
#     assert msg[:10] in panel.renderable.plain
#     assert panel.width == 70
#     # Ensure wrapping behavior is normalized
#     assert panel.renderable.no_wrap is False
#     assert panel.renderable.overflow == "fold"


# def test_output_panel_with_text_and_string_and_unknown_types(panels_mod, monkeypatch):
#     monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 66)
#     text_obj = Text("Here is some output")
#     panel1 = panels_mod.output_panel(text_obj, border_style="magenta")
#     assert isinstance(panel1, Panel)
#     assert "Here is some output" in panel1.renderable.plain
#     # Still orange1 even if we pass magenta (preserved quirk)
#     assert panel1.border_style == "orange1"
#     assert panel1.width == 66
#     # String input
#     panel2 = panels_mod.output_panel("output as string", icon="ignored")
#     assert "output as string" in panel2.renderable.plain
#     assert panel2.border_style == "orange1"
#     assert panel2.width == 66
#     # Unknown type (coerced via repr)
#     panel3 = panels_mod.output_panel(12345)
#     assert "12345" in panel3.renderable.plain
#     assert panel3.border_style == "orange1"


# def test_ai_panel_with_string_and_text(panels_mod, monkeypatch):
#     monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 71)
#     panel = panels_mod.ai_panel("AI says hello")
#     assert isinstance(panel, Panel)
#     assert "AI says hello" in panel.renderable.plain
#     assert panel.border_style == "bold cyan"
#     assert panel.title == "saxoflow_AI"
#     assert panel.width == 71
#     # Text input gets normalized wrapping
#     text_obj = Text("AI text object", no_wrap=True)
#     panel2 = panels_mod.ai_panel(text_obj, width=72)
#     assert "AI text object" in panel2.renderable.plain
#     assert panel2.width == 72
#     assert panel2.renderable.no_wrap is False
#     assert panel2.renderable.overflow == "fold"


# def test_agent_panel_properties_and_custom_border(panels_mod, monkeypatch):
#     monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 80)
#     panel = panels_mod.agent_panel("Agent output", border_style="magenta")
#     assert isinstance(panel, Panel)
#     assert "Agent output" in panel.renderable.plain
#     assert panel.title == "saxoflow_agent"
#     assert panel.border_style == "magenta"
#     assert panel.width == 80
#     # Also test with a Text object, different border
#     text_obj = Text("Agent text", no_wrap=True)
#     panel2 = panels_mod.agent_panel(text_obj, border_style="yellow", width=81)
#     assert "Agent text" in panel2.renderable.plain
#     assert panel2.border_style == "yellow"
#     assert panel2.width == 81
#     # Normalization applied
#     assert panel2.renderable.no_wrap is False
#     assert panel2.renderable.overflow == "fold"


# def test_public_api_names_in___all__(panels_mod):
#     expected = {
#         "welcome_panel",
#         "user_input_panel",
#         "output_panel",
#         "error_panel",
#         "ai_panel",
#         "agent_panel",
#     }
#     assert set(panels_mod.__all__) >= expected

from rich.panel import Panel
from rich.text import Text
from cool_cli.coolcli import panels

def test_welcome_panel_returns_panel():
    panel = panels.welcome_panel("Welcome to SaxoFlow", panel_width=99)
    assert isinstance(panel, Panel)
    assert "Welcome to SaxoFlow" in panel.renderable.plain
    assert panel.width == 99

def test_error_panel_formats_message():
    panel = panels.error_panel("something went wrong", width=77)
    assert isinstance(panel, Panel)
    assert "Error: something went wrong" in panel.renderable.plain
    assert panel.title == "error"
    assert panel.border_style == "red"
    assert panel.width == 77

def test_user_input_panel_formats_correctly():
    msg = "User typed this"
    panel = panels.user_input_panel(msg, width=70)
    assert isinstance(panel, Panel)
    assert panel.title == "user"
    assert panel.border_style == "cyan"
    assert msg in panel.renderable.plain
    assert panel.width == 70

def test_output_panel_with_text_and_string():
    text_obj = Text("Here is some output")
    panel1 = panels.output_panel(text_obj, border_style="magenta", width=66)
    assert isinstance(panel1, Panel)
    assert "Here is some output" in panel1.renderable.plain
    assert panel1.border_style == "orange1"  # Default, even if magenta passed
    assert panel1.width == 66

    panel2 = panels.output_panel("output as string", border_style="magenta", width=65)
    assert isinstance(panel2, Panel)
    assert "output as string" in panel2.renderable.plain
    assert panel2.border_style == "orange1"  # Still default
    assert panel2.width == 65

def test_ai_panel_with_string_and_text():
    panel = panels.ai_panel("AI says hello", width=71)
    assert isinstance(panel, Panel)
    assert "AI says hello" in panel.renderable.plain
    assert panel.border_style == "bold cyan"
    assert panel.title == "saxoflow_AI"
    assert panel.width == 71

    text_obj = Text("AI text object", no_wrap=True)
    panel2 = panels.ai_panel(text_obj, width=72)
    assert "AI text object" in panel2.renderable.plain
    assert panel2.width == 72

def test_agent_panel_properties_and_custom_border():
    panel = panels.agent_panel("Agent output", border_style="magenta", width=80)
    assert isinstance(panel, Panel)
    assert "Agent output" in panel.renderable.plain
    assert panel.title == "saxoflow_agent"
    assert panel.border_style == "magenta"
    assert panel.width == 80

    # Also test with a Text object
    text_obj = Text("Agent text", no_wrap=True)
    panel2 = panels.agent_panel(text_obj, border_style="yellow", width=81)
    assert "Agent text" in panel2.renderable.plain
    assert panel2.border_style == "yellow"
    assert panel2.width == 81

def test_panel_default_widths():
    # When width not given, panels still return Panel (width >= 60)
    panel = panels.user_input_panel("foo")
    assert isinstance(panel, Panel)
    assert panel.width >= 60
    panel = panels.output_panel("foo")
    assert panel.width >= 60
    panel = panels.error_panel("foo")
    assert panel.width >= 60
    panel = panels.welcome_panel("foo")
    assert panel.width >= 60
    panel = panels.ai_panel("foo")
    assert panel.width >= 60
    panel = panels.agent_panel("foo")
    assert panel.width >= 60

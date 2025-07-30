
from rich.panel import Panel
from rich.text import Text

def welcome_panel(welcome_text: str, panel_width: int | None = None) -> Panel:
    """Render a welcome message as if coming from SaxoFlow."""
    return Panel(
        Text(welcome_text, style="bold white"),
        border_style="cyan",
        title="saxoflow",
        title_align="left",
        padding=(0, 1),
        width=panel_width,
        expand=False
    )

def user_input_panel(message: str, width: int | None = None) -> Panel:
    """
    Create a panel for user input.

    The user's text is rendered in bold white on a cyan border.  No
    leading prompt character is displayed; the caller should provide
    the full message.  A custom width can be provided to control
    wrapping.
    """
    kwargs: dict[str, int | bool] = {}
    if width is not None:
        kwargs["width"] = width
    return Panel(
        Text(message, style="bold white"),
        border_style="cyan",
        title="user",
        title_align="left",
        padding=(0, 1),
        expand=False,
        **kwargs
    )

def output_panel(renderable, border_style: str = "white", icon: str | None = None) -> Panel:
    """
    Wrap output in a panel with a configurable border.

    The icon parameter is accepted for API compatibility but ignored
    to maintain a clean professional appearance.  Use the `ai_panel`
    function for AI responses instead of specifying an icon here.
    """
    return Panel(
        renderable,
        border_style=border_style,
        title="output",
        title_align="left",
        padding=(1, 2),
        expand=True,
    )

def error_panel(message: str) -> Panel:
    """
    Error panel with a red border.

    The message is rendered in yellow to draw attention without using
    emoji or icons.
    """
    return Panel(
        Text(f"Error: {message}", style="yellow"),
        border_style="red",
        title="error",
        title_align="left",
        padding=(1, 2),
        expand=True,
    )

def ai_panel(renderable) -> Panel:
    """
    Panel for AI or assistant output.

    Responses from the AI buddy are wrapped in a panel with a
    magenta border to differentiate them from user messages.  The
    title reads ``buddy`` to emphasise the interactive assistant.
    """
    return Panel(
        renderable,
        border_style="bold cyan",
        title="ai_buddy",
        title_align="left",
        padding=(1, 2),
        expand=True,
    )

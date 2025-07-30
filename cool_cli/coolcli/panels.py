from rich.panel import Panel
from rich.text import Text
from rich.console import Console

def _default_panel_width(scale: float = 0.8) -> int:
    """Return default panel width as 80% of terminal width."""
    console = Console()
    return max(60, int(console.width * scale))

def welcome_panel(welcome_text: str, panel_width: int | None = None) -> Panel:
    """Render a welcome message as if coming from SaxoFlow."""
    if panel_width is None:
        panel_width = _default_panel_width()
    return Panel(
        Text(welcome_text, style="bold white", no_wrap=False),
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

    The user's text is rendered in bold white on a cyan border.
    """
    from rich.text import Text
    if width is None:
        width = _default_panel_width()
    # Set no_wrap=False to allow wrapping, and overflow="fold" to force wrap anywhere
    txt = Text(message, style="bold white", no_wrap=False, overflow="fold")
    return Panel(
        txt,
        border_style="cyan",
        title="user",
        title_align="left",
        padding=(0, 1),
        expand=False,
        width=width
    )


def output_panel(renderable, border_style: str = "white", icon: str | None = None, width: int | None = None) -> Panel:
    """
    Wrap output in a panel with a configurable border.
    """
    if width is None:
        width = _default_panel_width()
    if isinstance(renderable, Text):
        renderable.no_wrap = False
    elif isinstance(renderable, str):
        renderable = Text(renderable, no_wrap=False)
    return Panel(
        renderable,
        border_style="orange1",
        title="saxoflow",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=width
    )

def error_panel(message: str, width: int | None = None) -> Panel:
    """
    Error panel with a red border.
    """
    if width is None:
        width = _default_panel_width()
    return Panel(
        Text(f"Error: {message}", style="yellow", no_wrap=False),
        border_style="red",
        title="error",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=width
    )

def ai_panel(renderable, width: int | None = None) -> Panel:
    """
    Panel for AI or assistant output.
    """
    from rich.text import Text
    if width is None:
        width = _default_panel_width()
    # Convert to Text if not already, and force wrapping (overflow="fold")
    if isinstance(renderable, str):
        renderable = Text(renderable, no_wrap=False, overflow="fold", style="white")
    elif isinstance(renderable, Text):
        renderable.no_wrap = False
        renderable.overflow = "fold"
    return Panel(
        renderable,
        border_style="bold cyan",
        title="saxoflow AI",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=width
    )


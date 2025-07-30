# from rich.text import Text
# from rich.panel import Panel
# from rich.console import Console
# from click.testing import CliRunner
# from saxoflow.cli import cli as saxoflow_cli
# from saxoflow_agenticai.cli import cli as agenticai_cli

# runner = CliRunner()
# console = Console()

# def handle_command(cmd: str, console):
#     cmd = cmd.strip()
#     lowered = cmd.lower()

#     if lowered == "help":
#         saxoflow_help_raw = runner.invoke(saxoflow_cli, ["--help"]).output.strip()
#         init_env_help_raw = runner.invoke(saxoflow_cli, ["init-env", "--help"]).output.strip()

#         # Prefix "saxoflow" before each command in the CLI output
#         saxoflow_help_lines = saxoflow_help_raw.splitlines()
#         prefixed_lines = []
#         for line in saxoflow_help_lines:
#             if line.strip().startswith((
#                 "agenticai", "check-tools", "clean", "diagnose", "formal", "init-env", "install",
#                 "sim", "sim-verilator", "sim-verilator-run", "simulate", "simulate-verilator",
#                 "synth", "unit", "wave", "wave-verilator")):
#                 cmd_part = line.strip().split()[0]
#                 rest = line.strip()[len(cmd_part):]
#                 prefixed_lines.append(f"saxoflow {cmd_part}{rest}")
#             else:
#                 prefixed_lines.append(line)

#         saxoflow_help = "\n".join(prefixed_lines)
#         init_env_help = init_env_help_raw.replace("Usage: ", "Usage: saxoflow ")

#         help_text = Text.from_markup(f"""[bold cyan]🚀 SaxoFlow Unified CLI Commands[/bold cyan]

# [silver]{saxoflow_help}[/silver]

# [bold cyan]⚙️ init-env Presets[/bold cyan]

# [silver]{init_env_help}[/silver]

# [bold cyan]🤖 Agentic AI Commands[/bold cyan]
# • [bold]rtlgen[/bold] — generate RTL from a specification
# • [bold]tbgen[/bold] — generate a testbench from RTL
# • [bold]fpropgen[/bold] — generate formal properties
# • [bold]debug[/bold] — analyze simulation output
# • [bold]report[/bold] — generate a full pipeline report
# • [bold]fullpipeline[/bold] — run full AI-based pipeline

# [bold cyan]🛠️ Built-in Commands[/bold cyan]
# • [bold]help[/bold] — show this help message
# • [bold]clear[/bold] — clear the current conversation
# • [bold]quit[/bold] / [bold]exit[/bold] — exit the CLI

# [bold cyan]💻 Unix Shell Commands[/bold cyan]
# • Use [bold]!<command>[/bold] like `!ls`, `!cd`, `!pwd`
# """)

#         # Panel width: 60% of terminal width, min 60 cols, max 120 cols
#         panel_width = max(60, min(120, int(console.width * 0.6)))

#         return Panel(
#             help_text,
#             title="SaxoFlow Help",
#             border_style="cyan",
#             padding=(1, 2),
#             width=panel_width,
#             expand=False,
#         )

#     elif lowered in ("init-env --help", "init-env help"):
#         result = runner.invoke(saxoflow_cli, ["init-env", "--help"])
#         return Text(result.output.strip() or "[⚠] No output from `init-env --help` command.", style="white")

#     elif lowered in ("rtlgen", "tbgen", "fpropgen", "debug", "report", "fullpipeline"):
#         try:
#             console.print(Panel.fit(f"🚀 Running `{lowered}` via SaxoFlow Agentic AI...", border_style="cyan"))
#             result = runner.invoke(agenticai_cli, [lowered])

#             if result.exception:
#                 import traceback
#                 tb = "".join(traceback.format_exception(*result.exc_info))
#                 return Text(f"[❌ EXCEPTION] {result.exception}\n\nTraceback:\n{tb}", style="bold red")

#             return Text(result.output or f"[⚠] No output from `{lowered}` command.", style="white")

#         except Exception as e:
#             import traceback
#             tb = traceback.format_exc()
#             return Text(f"[❌ Outer Exception] {str(e)}\n{tb}", style="bold red")

#     elif lowered in ("quit", "exit"):
#         return None

#     elif lowered == "clear":
#         console.clear()
#         return Text("Conversation cleared.", style="cyan")

#     elif lowered.startswith(("!", "ls", "pwd", "cd")):
#         return Text(f"Executing Unix command `{cmd}`...", style="cyan")

#     else:
#         return Text("Unknown command. Type ", style="yellow") + Text("help", style="cyan") + Text(" to see available commands.", style="yellow")

from rich.text import Text
from rich.panel import Panel
from rich.console import Console
from click.testing import CliRunner
from saxoflow.cli import cli as saxoflow_cli
from saxoflow_agenticai.cli import cli as agenticai_cli

runner = CliRunner()
console = Console()

def handle_command(cmd: str, console):
    cmd = cmd.strip()
    lowered = cmd.lower()

    if lowered == "help":
        saxoflow_help_raw = runner.invoke(saxoflow_cli, ["--help"]).output.strip()
        init_env_help_raw = runner.invoke(saxoflow_cli, ["init-env", "--help"]).output.strip()

        # REMOVE inner box-drawing characters from output (strip the box)
        def strip_box_lines(text):
            box_chars = ('╭', '╰', '│', '─', '┤', '├', '┌', '┐', '└', '┘', '═', '║', '╡', '╞', '╥', '╨')
            return "\n".join(
                line for line in text.splitlines()
                if not line.strip().startswith(box_chars)
            )

        saxoflow_help_raw = strip_box_lines(saxoflow_help_raw)
        init_env_help_raw = strip_box_lines(init_env_help_raw)

        # Prefix "saxoflow" before each command in the CLI output
        saxoflow_help_lines = saxoflow_help_raw.splitlines()
        prefixed_lines = []
        for line in saxoflow_help_lines:
            if line.strip().startswith((
                "agenticai", "check-tools", "clean", "diagnose", "formal", "init-env", "install",
                "sim", "sim-verilator", "sim-verilator-run", "simulate", "simulate-verilator",
                "synth", "unit", "wave", "wave-verilator")):
                cmd_part = line.strip().split()[0]
                rest = line.strip()[len(cmd_part):]
                prefixed_lines.append(f"saxoflow {cmd_part}{rest}")
            else:
                prefixed_lines.append(line)

        saxoflow_help = "\n".join(prefixed_lines)
        init_env_help = init_env_help_raw.replace("Usage: ", "Usage: saxoflow ")

        help_text = Text.from_markup(f"""[bold cyan]🚀 SaxoFlow Unified CLI Commands[/bold cyan]

[silver]{saxoflow_help}[/silver]

[bold cyan]⚙️ init-env Presets[/bold cyan]

[silver]{init_env_help}[/silver]

[bold cyan]🤖 Agentic AI Commands[/bold cyan]
[bold]rtlgen       [/bold]                  Generates RTL from a specification
[bold]tbgen        [/bold]                  Generates a testbench from a specification
[bold]fpropgen     [/bold]                  Generates formal properties from a specification
[bold]debug        [/bold]                  Analyzes simulation results and provides insights
[bold]report       [/bold]                  Generates a full pipeline report
[bold]fullpipeline [/bold]                  Runs a full agentic AI-based pipeline

[bold cyan]🛠️ Built-in Commands[/bold cyan]
[bold]help         [/bold]                  Shows available commands and usage
[bold]clear        [/bold]                  Clears the current conversation
[bold]quit[/bold]/[bold]exit[/bold]                         Leaves the CLI

[bold cyan]💻 Unix Shell Commands[/bold cyan]
Supports all unix commands like `ls`, `cat`, `cd`, etc.
""")

        # Panel width: 80% of terminal width, min 60 cols, max 120 cols
        panel_width = max(60, min(120, int(console.width * 0.8)))

        return Panel(
            help_text,
            title="SaxoFlow Help",
            border_style="cyan",
            padding=(1, 2),
            width=panel_width,
            expand=False,
        )

    elif lowered in ("init-env --help", "init-env help"):
        result = runner.invoke(saxoflow_cli, ["init-env", "--help"])
        return Text(result.output.strip() or "[⚠] No output from `init-env --help` command.", style="white")

    elif lowered in ("rtlgen", "tbgen", "fpropgen", "debug", "report", "fullpipeline"):
        try:
            console.print(Panel.fit(f"🚀 Running `{lowered}` via SaxoFlow Agentic AI...", border_style="cyan"))
            result = runner.invoke(agenticai_cli, [lowered])

            if result.exception:
                import traceback
                tb = "".join(traceback.format_exception(*result.exc_info))
                return Text(f"[❌ EXCEPTION] {result.exception}\n\nTraceback:\n{tb}", style="bold red")

            return Text(result.output or f"[⚠] No output from `{lowered}` command.", style="white")

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            return Text(f"[❌ Outer Exception] {str(e)}\n{tb}", style="bold red")

    elif lowered in ("quit", "exit"):
        return None

    elif lowered == "clear":
        console.clear()
        return Text("Conversation cleared.", style="cyan")

    elif lowered.startswith(("ll", "cat", "cd")):
        return Text(f"Executing Unix command `{cmd}`...", style="cyan")

    else:
        return Text("Unknown command. Type ", style="yellow") + Text("help", style="cyan") + Text(" to see available commands.", style="yellow")

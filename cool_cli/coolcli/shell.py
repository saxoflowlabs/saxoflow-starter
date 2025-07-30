import json
import os
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown
from coolcli.banner import print_banner
from coolcli.commands import handle_command
from coolcli.panels import user_input_panel, ai_panel, error_panel, welcome_panel, output_panel, agent_panel
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.completion import Completer, Completion, PathCompleter, FuzzyWordCompleter
from prompt_toolkit.document import Document
from saxoflow_agenticai.cli import cli as agent_cli
from click.testing import CliRunner
from coolcli.ai_buddy import ask_ai_buddy
from prompt_toolkit.completion import FuzzyCompleter

runner = CliRunner()

console = Console(soft_wrap=True)

conversation_history: List[Dict[str, Any]] = []
attachments: List[Dict[str, Any]] = []
system_prompt: str = ""
config: Dict[str, Any] = {
    "model": "placeholder",
    "temperature": 0.7,
    "top_k": 1,
    "top_p": 1.0,
}

SHELL_COMMANDS: Dict[str, List[str]] = {
    "ls": ["ls"],
    "ll": ["ls", "-la"],
    "pwd": ["pwd"],
    "whoami": ["whoami"],
    "date": ["date"],
}

def is_blocking_editor_command(user_input):
    """
    Returns True if the command is a blocking editor like nano/vim/vi/micro.
    Handles both 'nano file' and '!nano file'.
    """
    blocking_editors = {"nano", "vim", "vi", "micro"}
    tokens = shlex.split(user_input)
    if not tokens:
        return False
    first = tokens[0]
    if first.startswith("!"):
        first = first[1:]
    return first in blocking_editors


def is_unix_command(cmd: str) -> bool:
    """
    Returns True if the command is a valid Unix command in PATH,
    or one of our shell aliases, or a supported builtin like 'cd'.
    """
    if not cmd.strip():
        return False
    # Remove any ! prefix
    if cmd.startswith("!"):
        cmd = cmd[1:].strip()
    first = cmd.split()[0]
    return (
        first in SHELL_COMMANDS
        or first == "cd"
        or shutil.which(first) is not None
    )

def _run_shell_command(command: str) -> str:

    parts = shlex.split(command)
    if not parts:
        return ""
    cmd_name = parts[0]
    args = parts[1:]

    if cmd_name in SHELL_COMMANDS:
        base_cmd = list(SHELL_COMMANDS[cmd_name])
        if cmd_name in ("ls", "ll"):
            extra_opts = [arg for arg in args if arg.startswith('-')]
            cmd = base_cmd + extra_opts
        else:
            cmd = base_cmd
    elif cmd_name == "cd":
        target = args[0] if args else os.path.expanduser("~")
        try:
            os.chdir(os.path.expanduser(target))
            return f"Changed directory to {os.getcwd()}"
        except Exception as exc:
            return f"[error] {exc}"
    elif cmd_name == "saxoflow":
        try:
            result = subprocess.run(parts, capture_output=True, text=True)
            return result.stdout + result.stderr
        except Exception as exc:
            return f"[error] Failed to run saxoflow CLI: {exc}"
    else:
        # Support *any* Unix command if it exists in PATH
        if shutil.which(cmd_name) is None:
            return f"[error] Unsupported shell command: {cmd_name}"
        cmd = parts
    try:
        # NEW: Use Popen to handle KeyboardInterrupt
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
            return "[Interrupted] Command cancelled by user."
        output = (stdout + stderr).rstrip()
        return output
    except Exception as exc:
        return f"[error] {exc}"


def _dispatch_design_instruction(instruction: str) -> Optional[str]:
    if instruction.strip() in ("rtlgen", "tbgen", "fpropgen", "report"):

        try:
            result = subprocess.run(["python3", "-m", "saxoflow_agenticai.cli", instruction.strip()], capture_output=True, text=True)
            return result.stdout + result.stderr
        except Exception as e:
            return f"[error] {e}"
    return None

def _handle_terminal_editor(shell_cmd: str, console) -> Text:
    blocking_editors = {"nano", "vim", "vi", "micro"}
    nonblocking_editors = {"code", "subl", "gedit"}
    parts = shlex.split(shell_cmd)
    if not parts:
        return Text("[❌] No command specified.", style="red")
    editor = parts[0]
    if editor in blocking_editors:
        app = get_app_or_none()
        def run_editor():
            os.system(shell_cmd)
        if app:
            app.suspend_to_background(func=run_editor)
        else:
            os.system(shell_cmd)
        return Text(f"✅ Returned from {editor}", style="cyan")
    elif editor in nonblocking_editors:
        try:
            subprocess.Popen(parts)
            return Text(f"🚀 Launched {editor} in background", style="cyan")
        except Exception as e:
            return Text(f"❌ Failed to launch {editor}: {e}", style="red")
    else:
        try:
            result = subprocess.run(parts, capture_output=True, text=True)
            return Text(result.stdout or result.stderr, style="white")
        except Exception as e:
            return Text(f"❌ Shell error: {e}", style="red")

def dispatch_input(prompt: str) -> Text:
    prompt = prompt.strip()
    first_word = prompt.split(maxsplit=1)[0] if prompt else ""
    if first_word in {"nano", "vim", "code", "subl", "gedit", "vi", "micro"}:
        return Text(
            "ℹ️  Tip: Use `!nano <file>`, `!vim <file>`, `!vi <file>`, `!micro <file>`, "
            "`!code <file>`, `!subl <file>`, or `!gedit <file>` to launch editors properly.",
            no_wrap=False,
            style="yellow"
        )
    # ✅ Support !<command> for shell command escape
    if prompt.startswith("!"):
        shell_cmd = prompt[1:].strip()
        result = _handle_terminal_editor(shell_cmd, console)
        if isinstance(result, str):
            return Text(result, no_wrap=False)
        return result
    first_token = first_word
    if not first_token:
        return Text("", no_wrap=False)
    if is_unix_command(prompt):
        result_text = _run_shell_command(prompt)
        return Text(result_text, no_wrap=False)
    design_result = _dispatch_design_instruction(prompt)
    if design_result is not None:
        return Text(design_result, no_wrap=False)
    return Text(
        "I'm sorry, I didn't understand your request. "
        "Try design commands like 'rtlgen', 'tbgen', 'fpropgen' or 'report', "
        "or simple shell commands like 'ls', 'pwd', 'date'.",
        no_wrap=False
    )

def process_command(cmd: str):
    cmd = cmd.strip()
    if not cmd:
        return Text("")

    # Special handling for cd command
    parts = shlex.split(cmd)
    if parts and parts[0] == "cd":
        target = parts[1] if len(parts) > 1 else os.path.expanduser("~")
        try:
            os.chdir(os.path.expanduser(target))
            return Text(f"Changed directory to {os.getcwd()}", style="cyan")
        except Exception as exc:
            return Text(f"[error] {exc}", style="red")

    # Editor hint
    first_word = cmd.split()[0]
    if first_word in {"nano", "vim", "code", "subl", "gedit", "vi", "micro"}:
        return Text("ℹ️  Tip: Use `!nano <file>` or `!vim <file>` to launch editors properly.", style="yellow")

    # Handle !<editor> or !<command>
    if cmd.startswith("!"):
        shell_cmd = cmd[1:].strip()
        return _handle_terminal_editor(shell_cmd, console)

    # --- SPECIAL CASE: saxoflow init-env with NO preset ---
    if cmd == "saxoflow init-env":
        msg = (
            "⚠️  Interactive environment setup is not supported in SaxoFlow Cool CLI shell.\n"
            "[Usage] Please use one of the following supported commands:\n"
            "   saxoflow init-env --preset <preset>\n"
            "   saxoflow install\n"
            "   saxoflow install all\n\n"
            "Tip: To see available presets, run: saxoflow init-env --help\n"
        )
        return Text(msg, style="yellow")

    # --- RUN saxoflow CLI commands (always with headless env var) ---
    if cmd.startswith("saxoflow"):
        env = os.environ.copy()
        env["SAXOFLOW_FORCE_HEADLESS"] = "1"
        parts = shlex.split(cmd)
        try:
            result = subprocess.run(parts, capture_output=True, text=True, env=env)
            return Text(result.stdout + result.stderr, style="white")
        except Exception as exc:
            return Text(f"[error] Failed to run saxoflow CLI: {exc}", style="red")

    # --- RUN ANY SUPPORTED UNIX COMMAND (use PATH) ---
    parts = shlex.split(cmd)
    if parts and (parts[0] in SHELL_COMMANDS or shutil.which(parts[0])):
        result = _run_shell_command(cmd)
        return Text(result, style="white")

    # --- Otherwise, try the legacy handle_command (for help etc) ---
    return handle_command(cmd, console)




COMMANDS = [
    "help", "quit", "exit", "simulate", "synth", "ai", "clear",
    "rtlgen", "tbgen", "fpropgen", "report", "attach", "save", "load",
    "export", "stats", "system", "models", "set", "cd", "ls", "nano", "cat",
    "vim", "code", "subl", "gedit", "vi", "micro"
]
cd_path_completer = PathCompleter(only_directories=True, expanduser=True)
file_path_completer = PathCompleter(only_directories=False, expanduser=True)

class HybridShellCompleter(Completer):
    def __init__(self, commands):
        self.command_completer = FuzzyWordCompleter(list(commands))
        self.path_completer = PathCompleter(expanduser=True)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # Determine if we are completing the command itself or an argument.
        # If there's no space, or the cursor is within the first word (before or at the first space),
        # it's a command completion.
        first_space_index = text.find(' ')

        if first_space_index == -1 or document.cursor_position <= first_space_index:
            # Command completion (first word)
            for c in self.command_completer.get_completions(document, complete_event):
                yield c
        else:
            # Argument completion (after the first command)
            # Get the part of the input that is the argument we are trying to complete.
            # This is the text from the first space + 1 up to the cursor.
            arg_input = text[first_space_index + 1:]
            
            # Create a Document for the PathCompleter using only this argument part.
            # The cursor position for this new document is at the end of the argument text.
            doc_for_path_completer = Document(text=arg_input, cursor_position=len(arg_input))

            # Get completions from the PathCompleter
            for c in self.path_completer.get_completions(doc_for_path_completer, complete_event):
                # c.text from PathCompleter is the full suggested word (e.g., "source/").
                # c.start_position from PathCompleter is relative to 'doc_for_path_completer.text' (i.e., 'arg_input').
                # It indicates how many characters from the start of 'doc_for_path_completer.text'
                # need to be replaced. For example, if arg_input="so" and c.text="source/", c.start_position would be 0.
                
                # The 'start_position' for the yielded Completion needs to be relative to the
                # *original* document's cursor position.
                # It should be the negative length of the part of the 'arg_input' that needs to be replaced.
                # This is calculated as `len(arg_input) - c.start_position`.
                # So, the `start_position` for the final `Completion` object is:
                # `-(len(arg_input) - c.start_position)`
                
                adjusted_start_position = -(len(arg_input) - c.start_position)

                yield Completion(
                    text=c.text,
                    start_position=adjusted_start_position,
                    display=c.display,
                    display_meta=c.display_meta
                )


def clear_terminal() -> None:
    os.system("cls" if os.name == "nt" else "clear")

def attach_file(path: str) -> Text:
    if not path:
        return Text("Attach command requires a file path.", style="bold red")
    if not os.path.isfile(path):
        return Text(f"File not found: {path}", style="bold red")
    try:
        with open(path, "rb") as f:
            content = f.read()
        attachments.append({"name": os.path.basename(path), "content": content})
        return Text(f"Attached {os.path.basename(path)}", style="cyan")
    except Exception as exc:
        return Text(f"Failed to attach file: {exc}", style="bold red")

def save_session(filename: str) -> Text:
    if not filename:
        filename = "session.json"
    data = {
        "conversation_history": conversation_history,
        "attachments": [{"name": att["name"]} for att in attachments],
        "system_prompt": system_prompt,
        "config": config,
    }
    try:
        with open(filename, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return Text(f"Session saved to {filename}", style="cyan")
    except Exception as exc:
        return Text(f"Failed to save session: {exc}", style="bold red")

def load_session(filename: str) -> Text:
    if not filename:
        return Text("Load command requires a filename.", style="bold red")
    if not os.path.isfile(filename):
        return Text(f"Session file not found: {filename}", style="bold red")
    global conversation_history, attachments, system_prompt, config
    try:
        with open(filename, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        conversation_history = data.get("conversation_history", [])
        attachments = []
        for att in data.get("attachments", []):
            attachments.append({"name": att["name"], "content": b""})
        system_prompt = data.get("system_prompt", "")
        loaded_config = data.get("config", {})
        config.update(loaded_config)
        return Text(f"Session loaded from {filename}", style="cyan")
    except Exception as exc:
        return Text(f"Failed to load session: {exc}", style="bold red")

def export_markdown(filename: str) -> Text:
    if not filename:
        filename = "conversation.md"
    try:
        with open(filename, "w", encoding="utf-8") as fh:
            if system_prompt:
                fh.write(f"## System Prompt\n\n{system_prompt}\n\n")
            for turn in conversation_history:
                fh.write(f"### User\n\n{turn['user']}\n\n")
                assistant_msg = turn.get("assistant", "")
                if isinstance(assistant_msg, (Text, Markdown)):
                    assistant_str = assistant_msg.plain if isinstance(assistant_msg, Text) else assistant_msg.text
                else:
                    assistant_str = str(assistant_msg)
                fh.write(f"### Assistant\n\n{assistant_str}\n\n")
        return Text(f"Conversation exported to {filename}", style="cyan")
    except Exception as exc:
        return Text(f"Failed to export conversation: {exc}", style="red")

def get_stats() -> Text:
    total_tokens = 0
    for turn in conversation_history:
        total_tokens += len(turn.get("user", "").split())
        assistant_msg = turn.get("assistant", "")
        if isinstance(assistant_msg, (Text, Markdown)):
            assistant_str = assistant_msg.plain if isinstance(assistant_msg, Text) else assistant_msg.text
        else:
            assistant_str = str(assistant_msg)
        total_tokens += len(assistant_str.split())
    return Text(f"Approx token count: {total_tokens} (ignoring attachments)", style="light cyan")

def set_system_prompt(prompt: str) -> Text:
    global system_prompt
    system_prompt = prompt.strip()
    if system_prompt:
        return Text("System prompt set.", style="cyan")
    return Text("System prompt cleared.", style="yellow")

def clear_history() -> Text:
    conversation_history.clear()
    attachments.clear()
    return Text("Conversation history and attachments cleared.", style="light cyan")

def list_models() -> Text:
    models = ["placeholder-model-1", "placeholder-model-2"]
    return Text("Available models:\n- " + "\n- ".join(models), style="light cyan")

def update_config(param: str, value: str) -> Text:
    try:
        key = param.strip().lower()
        if key == "temperature":
            config["temperature"] = float(value)
        elif key == "top_k":
            config["top_k"] = int(value)
        elif key == "top_p":
            config["top_p"] = float(value)
        else:
            return Text(f"Unknown config parameter: {param}", style="red")
        return Text(f"Updated {param} to {value}", style="cyan")
    except Exception as exc:
        return Text(f"Failed to update config: {exc}", style="red")

def simulate_ai_response(prompt: str) -> str:
    response = f"I received your message: '{prompt}'. (AI response placeholder)"
    if attachments:
        response += "\n\nAttached file(s): " + ", ".join(att["name"] for att in attachments)
    if system_prompt:
        response += f"\n\nSystem prompt: {system_prompt}"
    return response

def is_terminal_editor(cmd: str) -> bool:
    editor_words = {"nano", "vim", "code", "subl", "gedit", "vi", "micro"}
    stripped = cmd.strip()
    if not stripped:
        return False
    if stripped.startswith("!"):
        first = stripped[1:].split(maxsplit=1)[0] if len(stripped) > 1 else ""
    else:
        first = stripped.split(maxsplit=1)[0]
    return first in editor_words

def show_opening_look(console, panel_width):
    welcome_text = (
        "Welcome to SaxoFlow CLI! Take your first step toward mastering digital "
        "design and verification."
    )
    tips = Text(
        "Tips for getting started:\n"
        "1. Ask questions, generate RTL/testbenches, or run simple commands.\n"
        "2. Try shell commands like 'ls' or design commands like 'rtlgen'.\n"
        "3. Type 'help' to see available commands.\n"
        "4. Type 'quit' or 'exit' to leave the CLI.\n",
        style="yellow",
    )
    print_banner(console)
    console.print(welcome_panel(welcome_text, panel_width=panel_width))
    console.print(tips)
    console.print("")

def ai_buddy_interactive(user_input, conversation_history, file_to_review=None):
    """
    Handles natural-language or '/buddy' input, including review & action.
    Returns a renderable (Text or Markdown).
    """

    # Initial call (no file/code yet)
    result = ask_ai_buddy(user_input, conversation_history, file_to_review=file_to_review)

    # 1. Buddy needs code for review
    if result["type"] == "need_file":
        console.print(Text(result["message"], style="yellow"))
        file_or_code = input("Paste code or provide file path: ").strip()
        code = ""
        # If user input looks like a file path and exists, read it
        if os.path.isfile(file_or_code):
            with open(file_or_code, "r") as f:
                code = f.read()
        else:
            code = file_or_code
        # Retry with code
        result = ask_ai_buddy(user_input, conversation_history, file_to_review=code)
        if result["type"] == "review_result":
            return Text(result["message"], style="white")
        else:
            return Text(result.get("message", "Unexpected response."), style="red")

    # 2. Review result
    if result["type"] == "review_result":
        return Text(result["message"], style="white")

    # 3. Action trigger (e.g. __ACTION:rtlgen__)
    if result["type"] == "action":
        console.print(Text(result["message"], style="cyan"))
        confirm = input(f"Ready to run '{result['action']}'? (yes/no): ").strip().lower()
        if confirm in {"yes", "y"}:
            # Reuse your CLI runner logic or subprocess here as appropriate!
            action = result["action"]
            # Use your runner or subprocess logic as in process_command
            from click.testing import CliRunner
            runner = CliRunner()
            agent_cli = globals().get("agent_cli", None)
            if not agent_cli:
                from saxoflow_agenticai.cli import cli as agent_cli
            cli_args = [action]
            result_obj = runner.invoke(agent_cli, cli_args)
            output = result_obj.output or "[⚠] No output."
            return Text(output, style="white")
        else:
            return Text("Action cancelled.", style="yellow")

    # 4. Standard chat
    return Text(result.get("message", ""), style="white")


def main() -> None:
    cli_history = InMemoryHistory()

    builtin_cmds: List[str] = [
        "help", "quit", "exit", "simulate", "synth", "ai", "clear",
        "rtlgen", "tbgen", "fpropgen", "report", "rtlreview", "tbreview", "fpropreview",
        "debug", "sim", "fullpipeline", "attach", "save", "load",
        "export", "stats", "system", "models", "set",
    ]
    command_names: List[str] = builtin_cmds + list(SHELL_COMMANDS.keys()) + ["cd"]

    try:
        from saxoflow.cli import cli as saxoflow_root_cli
        command_names += [f"saxoflow {cmd}" for cmd in saxoflow_root_cli.commands]
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load saxoflow commands - {e}[/yellow]")

    try:
        from saxoflow_agenticai.cli import cli as agentic_cli
        command_names += [f"agent {cmd}" for cmd in agentic_cli.commands]
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load agentic AI commands - {e}[/yellow]")

    all_commands = set(command_names)

    completer = HybridShellCompleter(COMMANDS)
    session = PromptSession(completer=completer, history=cli_history)

    panel_width = int(console.width * 0.8)

    CUSTOM_PROMPT = HTML('<ansibrightwhite>✦</ansibrightwhite> <ansicyan><b>saxoflow</b></ansicyan> <ansibrightwhite>⮞</ansibrightwhite> ')

    # ---- AGENTIC COMMANDS DEFINITION ----
    AGENTIC_COMMANDS = {
        "rtlgen", "tbgen", "fpropgen", "report",
        "rtlreview", "tbreview", "fpropreview", "debug", "sim", "fullpipeline"
    }

    while True:
        clear_terminal()
        if not conversation_history:
            show_opening_look(console, panel_width)
        else:
            for entry in conversation_history:
                upanel = user_input_panel(entry.get("user", ""), width=panel_width)
                console.print(upanel)
                assistant_msg = entry.get("assistant")
                panel_type = entry.get("panel", "ai")
                if assistant_msg:
                    if isinstance(assistant_msg, str):
                        assistant_renderable = Text(assistant_msg)
                    else:
                        assistant_renderable = assistant_msg
                    if panel_type == "output":
                        opanel = output_panel(assistant_renderable, border_style="white", width=panel_width)
                    elif panel_type == "agent":
                        opanel = agent_panel(assistant_renderable, width=panel_width)
                    else:
                        opanel = ai_panel(assistant_renderable, width=panel_width)
                    console.print(opanel)
                console.print("")

        try:
            user_input = session.prompt(CUSTOM_PROMPT)
        except (EOFError, KeyboardInterrupt):
            console.print(Text(
                "\nUntil next time, may your timing constraints always be met and your logic always latch‑free.\n",
                style="cyan",
            ))
            break
        user_input = user_input.strip()
        if not user_input:
            continue

        first_token = user_input.split(maxsplit=1)[0].lower()
        if first_token == "clear":
            conversation_history.clear()
            continue

        # CLI Command detection (matches command with/without args)
        is_cli_command = (
            user_input in command_names or
            user_input.startswith("!") or
            is_unix_command(user_input)
        )

        # ---- 1. AGENTIC AI COMMANDS (Agent Panel) ----
        if first_token in AGENTIC_COMMANDS:
            # Always treat as agentic, regardless of the rest
            with console.status("[magenta]Agentic AI running...", spinner="clock"):
                parts = shlex.split(user_input)
                proc = subprocess.Popen(
                    ["python3", "-m", "saxoflow_agenticai.cli"] + parts,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                stdout, stderr = proc.communicate()
                output = (stdout or "") + (stderr or "")
                if proc.returncode != 0:
                    renderable = Text(f"[❌] Error in `{user_input}`\n\n{output}", style="bold red")
                else:
                    renderable = Text(output or f"[⚠] No output from `{user_input}` command.", style="white")
            panel = agent_panel(renderable, width=panel_width)
            console.print(user_input_panel(user_input, width=panel_width))
            console.print(panel)
            console.print("")
            conversation_history.append({
                "user": user_input, "assistant": renderable, "panel": "agent"
            })
            continue  # Prevents falling through to output_panel!

        # ---- 2. SHELL/EDITOR COMMANDS (Output Panel) ----
        if is_cli_command:
            if is_blocking_editor_command(user_input):
                renderable = process_command(user_input)
                panel = output_panel(renderable, border_style="white", width=panel_width)
                console.print(user_input_panel(user_input, width=panel_width))
                console.print(panel)
                console.print("")
                conversation_history.append({"user": user_input, "assistant": renderable, "panel": "output"})
            else:
                with console.status("[cyan]Loading...", spinner="aesthetic"):
                    renderable = process_command(user_input)
                if renderable is None:
                    console.print(Text(
                        "\nUntil next time, may your timing constraints always be met and your logic always latch‑free.\n",
                        style="cyan",
                    ))
                    break
                panel = output_panel(renderable, border_style="white", width=panel_width)
                console.print(user_input_panel(user_input, width=panel_width))
                console.print(panel)
                console.print("")
                conversation_history.append({"user": user_input, "assistant": renderable, "panel": "output"})
            continue  # Ensure we don't drop into the AI buddy for commands

        # ---- 3. AI BUDDY (AI Panel) ----
        # If not a CLI command or agentic command, it's chat/natural language
        with console.status("[cyan]Thinking...", spinner="dots"):
            assistant_response = ai_buddy_interactive(user_input, conversation_history)
        panel = ai_panel(assistant_response, width=panel_width)
        console.print(user_input_panel(user_input, width=panel_width))
        console.print(panel)
        console.print("")
        conversation_history.append({
            "user": user_input, "assistant": assistant_response, "panel": "ai"
        })


if __name__ == "__main__":
    main()

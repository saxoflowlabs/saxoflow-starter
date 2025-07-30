import json
import os
import time
import shutil
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.text import Text
from rich.markdown import Markdown
from coolcli.banner import print_banner
from coolcli.commands import handle_command
from coolcli.panels import user_input_panel, ai_panel, error_panel, welcome_panel, output_panel
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.completion import WordCompleter

from saxoflow_agenticai.cli import cli as agent_cli
from click.testing import CliRunner
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

def _run_shell_command(command: str) -> str:
    import subprocess
    import shlex
    import shutil

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
        import shutil
        if shutil.which(cmd_name) is None:
            return f"[error] Unsupported shell command: {cmd_name}"
        cmd = parts
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = (result.stdout + result.stderr).rstrip()
        return output
    except Exception as exc:
        return f"[error] {exc}"

def _dispatch_design_instruction(instruction: str) -> Optional[str]:
    if instruction.strip() in ("rtlgen", "tbgen", "fpropgen", "report"):
        import subprocess
        try:
            result = subprocess.run(["python3", "-m", "saxoflow_agenticai.cli", instruction.strip()], capture_output=True, text=True)
            return result.stdout + result.stderr
        except Exception as e:
            return f"[error] {e}"
    return None


# def _dispatch_design_instruction(instruction: str) -> Optional[str]:
#     text = instruction.lower()
#     if ("rtl" in text) and ("generate" in text or "create" in text):
#         return "[placeholder] Generated RTL from specification."
#     if (("tb" in text) or ("testbench" in text)) and ("generate" in text or "create" in text):
#         return "[placeholder] Generated testbench from RTL."
#     if (("formal" in text) or ("property" in text)) and ("generate" in text or "create" in text):
#         return "[placeholder] Generated formal properties."
#     if "report" in text and ("generate" in text or "create" in text):
#         return "[placeholder] Generated report from previous stages."
#     return None

# def dispatch_input(prompt: str) -> str:
#     prompt = prompt.strip()
#     first_token = prompt.split(maxsplit=1)[0] if prompt else ""
#     if not first_token:
#         return ""

#     import shutil
#     if first_token in SHELL_COMMANDS or first_token == "cd" or shutil.which(first_token):
#         return _run_shell_command(prompt)

#     # Fallback — pass to handle_command() and convert to str
#     try:
#         from coolcli.commands import handle_command
#         result = handle_command(prompt, console)
#         if isinstance(result, (Text, Markdown)):
#             return result.plain
#         return str(result)
#     except Exception as e:
#         return f"[error] Dispatch failed: {e}"

def dispatch_input(prompt: str) -> str:
    prompt = prompt.strip()

    # ✅ Support !<command> for shell command escape
    if prompt.startswith("!"):
        try:
            shell_cmd = prompt[1:].strip()
            os.system(shell_cmd)
            return f"[📤 Shell] Ran: {shell_cmd}"
        except Exception as e:
            return f"[❌ Shell Error] {e}"

    first_token = prompt.split(maxsplit=1)[0] if prompt else ""
    if not first_token:
        return ""

    # Allow *any* system command, not just safe list!
    import shutil
    if first_token in SHELL_COMMANDS or first_token == "cd" or shutil.which(first_token):
        result_text = _run_shell_command(prompt)
        return result_text

    design_result = _dispatch_design_instruction(prompt)
    if design_result is not None:
        return design_result

    return (
        "I'm sorry, I didn't understand your request. "
        "Try design commands like 'rtlgen', 'tbgen', 'fpropgen' or 'report', "
        "or simple shell commands like 'ls', 'pwd', 'date'."
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

def process_command(cmd: str):
    import subprocess
    import shlex
    from rich.panel import Panel

    cmd = cmd.strip()
    if not cmd:
        return Text("")

    # ✅ 1. Shell escape — supports nano, vim, code etc. (with !)
    if cmd.startswith("!"):
        shell_cmd = cmd[1:].strip()
        parts = shlex.split(shell_cmd)
        editor_blocking = {"nano", "vim", "vi", "micro"}
        editor_nonblocking = {"code", "subl", "gedit"}

        if parts and parts[0] in editor_blocking:
            try:
                os.system("clear")
                os.system(shell_cmd)
                return Text(f"✅ Returned from {parts[0]}", style="cyan")
            except Exception as e:
                return Text(f"❌ Failed to open editor: {e}", style="red")

        elif parts and parts[0] in editor_nonblocking:
            try:
                subprocess.Popen(parts)
                return Text(f"🚀 Launched {parts[0]} in background", style="cyan")
            except Exception as e:
                return Text(f"❌ Failed to launch {parts[0]}: {e}", style="red")

        else:
            try:
                result = subprocess.run(parts, capture_output=True, text=True)
                return Text(result.stdout or result.stderr, style="white")
            except Exception as e:
                return Text(f"❌ Shell error: {e}", style="red")

    # ✅ 2. Helpful tip if user forgets `!`
    if cmd.split()[0] in {"nano", "vim", "code", "subl", "gedit", "vi", "micro"}:
        return Text("ℹ️  Tip: Use `!nano <file>` or `!vim <file>` to launch editors properly.", style="yellow")

    # ✅ 3. Shell commands (cd, pwd, ll, etc.)
    first = cmd.split()[0]
    try:
        result = _run_shell_command(cmd)
        if "[error]" not in result:
            return Text(result, style="white")
    except Exception as e:
        return Text(f"❌ Failed: {e}", style="red")

    # ✅ 4. AI Agent commands
    if first in ("rtlgen", "tbgen", "fpropgen", "debug", "report", "fullpipeline"):
        try:
            result = runner.invoke(agent_cli, [first])
            if result.exception:
                import traceback
                tb = "".join(traceback.format_exception(*result.exc_info))
                return Text(f"[❌ EXCEPTION] {result.exception}\n\nTraceback:\n{tb}", style="bold red")
            return Text(result.output or f"[⚠] No output from `{first}` command.", style="white")
        except Exception as e:
            return Text(f"[❌ Failed to run `{first}`] {e}", style="red")

    # ✅ 5. Fallback to built-in commands
    return handle_command(cmd, console)


# def process_command(cmd: str):
#     import subprocess
#     import shlex

#     cmd = cmd.strip()
#     if not cmd:
#         return Text("")

#     # ✅ 1. Shell escape — supports nano, vim, code etc.
#     if cmd.startswith("!"):
#         import shlex
#         shell_cmd = cmd[1:].strip()
#         parts = shlex.split(shell_cmd)
#         editor_blocking = {"nano", "vim"}
#         editor_nonblocking = {"code"}

#         if parts and parts[0] in editor_blocking:
#             # ✨ Clear Rich UI, run blocking editor, then restore shell
#             os.system("clear")
#             os.system(shell_cmd)
#             return Text(f"✅ Returned from {parts[0]}", style="cyan")

#         elif parts and parts[0] in editor_nonblocking:
#             # 🌀 Launch non-blocking editors like VSCode
#             subprocess.Popen(parts)
#             return Text(f"🚀 Launched {parts[0]} in background", style="cyan")

#         else:
#             try:
#                 result = subprocess.run(parts, capture_output=True, text=True)
#                 return Text(result.stdout or result.stderr, style="white")
#             except Exception as e:
#                 return Text(f"❌ Shell error: {e}", style="red")


#     # ✅ 2. Explicit shell commands (cd, pwd, ll, etc.)
#     first = cmd.split()[0]
#     try:
#         result = _run_shell_command(cmd)
#         if "[error]" not in result:
#             return Text(result, style="white")
#     except Exception as e:
#         return Text(f"❌ Failed: {e}", style="red")

#     # ✅ 3. AI Agent commands
#     if first in ("rtlgen", "tbgen", "fpropgen", "debug", "report", "fullpipeline"):
#         try:
#             console_output = Panel.fit(f"🚀 Running `{first}` via SaxoFlow Agentic AI...", border_style="cyan")
#             result = runner.invoke(agent_cli, [first])
#             if result.exception:
#                 import traceback
#                 tb = "".join(traceback.format_exception(*result.exc_info))
#                 return Text(f"[❌ EXCEPTION] {result.exception}\n\nTraceback:\n{tb}", style="bold red")
#             return Text(result.output or f"[⚠] No output from `{first}` command.", style="white")
#         except Exception as e:
#             return Text(f"[❌ Failed to run `{first}`] {e}", style="red")

#     # ✅ 4. Fallback to built-in commands (help, exit, etc.)
#     return handle_command(cmd, console)


# def process_command(cmd: str):
#     import subprocess
#     from rich.panel import Panel

#     cmd = cmd.strip()
#     if not cmd:
#         return Text("")

#     # Shell escape using !<command>
#     if cmd.startswith("!"):
#         shell_cmd = cmd[1:].strip()
#         editor_launch = shell_cmd.split()[0]

#         try:
#             # For terminal-based editors (blocking)
#             if editor_launch in ("nano", "vim", "vi", "micro"):
#                 subprocess.run(shell_cmd, shell=True)
#                 return Text(f"[📤 Editor closed] Returned from `{editor_launch}`", style="cyan")

#             # For GUI editors (non-blocking)
#             elif editor_launch in ("code", "gedit", "subl"):
#                 subprocess.Popen(shell_cmd, shell=True)
#                 return Text(f"[📤 GUI Editor launched] `{editor_launch}` started in background", style="cyan")

#             # Fallback for general shell commands
#             else:
#                 result = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True)
#                 return Text(result.stdout + result.stderr, style="white")

#         except Exception as e:
#             return Text(f"❌ Failed running external command: {e}", style="red")

#     parts = cmd.split(maxsplit=1)
#     keyword = parts[0].lower()
#     arg = parts[1].strip() if len(parts) > 1 else ""

#     if keyword == "help":
#         return handle_command("help", None)
#     if keyword in ("quit", "exit"):
#         return None
#     if keyword == "simulate":
#         return Text("Running simulation... (placeholder)", style="cyan")
#     if keyword == "synth":
#         return Text("Running synthesis... (placeholder)", style="cyan")
#     if keyword == "ai":
#         return Text("AI agent feature coming soon!", style="magenta")
#     if keyword in ("rtlgen", "tbgen", "fpropgen", "debug", "report", "fullpipeline"):
#         try:
#             console_output = Panel.fit(f"🚀 Running `{keyword}` via SaxoFlow Agentic AI...", border_style="cyan")
#             result = runner.invoke(agent_cli, [keyword])

#             if result.exception:
#                 import traceback
#                 tb = "".join(traceback.format_exception(*result.exc_info))
#                 return Text(f"[❌ EXCEPTION] {result.exception}\n\nTraceback:\n{tb}", style="bold red")

#             return Text(result.output or f"[⚠] No output from `{keyword}` command.", style="white")

#         except Exception as e:
#             import traceback
#             tb = traceback.format_exc()
#             return Text(f"[❌ Outer Exception] {str(e)}\n{tb}", style="bold red")

#     if shutil.which(keyword):
#         try:
#             result = subprocess.run(cmd.split(), capture_output=True, text=True)
#             return Text(result.stdout or result.stderr, style="white")
#         except Exception as e:
#             return Text(f"❌ Failed system command: {e}", style="red")

#     return handle_command(cmd, None)


# def process_command(cmd: str):
#     cmd = cmd.strip()
#     if not cmd:
#         return Text("")

#     # 🔧 NEW: Shell escape using !<command>
#     if cmd.startswith("!"):
#         try:
#             shell_cmd = cmd[1:].strip()
#             os.system(shell_cmd)
#             return Text(f"📤 Ran shell command: {shell_cmd}", style="cyan")
#         except Exception as e:
#             return Text(f"❌ Failed running external command: {e}", style="red")

#     parts = cmd.split(maxsplit=1)
#     keyword = parts[0].lower()
#     arg = parts[1].strip() if len(parts) > 1 else ""

#     if keyword == "help":
#         return handle_command("help", None)
#     if keyword in ("quit", "exit"):
#         return None
#     if keyword == "simulate":
#         return Text("Running simulation... (placeholder)", style="cyan")
#     if keyword == "synth":
#         return Text("Running synthesis... (placeholder)", style="cyan")
#     if keyword == "ai":
#         return Text("AI agent feature coming soon!", style="magenta")
#     if keyword in ("rtlgen", "tbgen", "fpropgen", "debug", "report", "fullpipeline"):
#         try:
#             console_output = Panel.fit(f"🚀 Running `{keyword}` via SaxoFlow Agentic AI...", border_style="cyan")
#             result = runner.invoke(agenticai_cli, [keyword])

#             if result.exception:
#                 import traceback
#                 tb = "".join(traceback.format_exception(*result.exc_info))
#                 return Text(f"[❌ EXCEPTION] {result.exception}\n\nTraceback:\n{tb}", style="bold red")

#             return Text(result.output or f"[⚠] No output from `{keyword}` command.", style="white")

#         except Exception as e:
#             import traceback
#             tb = traceback.format_exc()
#             return Text(f"[❌ Outer Exception] {str(e)}\n{tb}", style="bold red")

#     if shutil.which(keyword):  # support system commands (e.g. `ls`)
#         try:
#             result = subprocess.run(cmd.split(), capture_output=True, text=True)
#             return Text(result.stdout or result.stderr, style="white")
#         except Exception as e:
#             return Text(f"❌ Failed system command: {e}", style="red")

#     return handle_command(cmd, None)


# def process_command(cmd: str) -> Optional[Any]:
#     cmd = cmd.strip()
#     if not cmd:
#         return Text("")
#     parts = cmd.split(maxsplit=1)
#     keyword = parts[0].lower()
#     arg = parts[1].strip() if len(parts) > 1 else ""

#     if keyword == "help":
#         return handle_command("help", console)
#     if keyword in ("quit", "exit"):
#         return None
#     if keyword == "simulate":
#         return Text("Running simulation... (placeholder)", style="cyan")
#     if keyword == "synth":
#         return Text("Running synthesis... (placeholder)", style="cyan")
#     if keyword == "ai":
#         return Text("AI agent feature coming soon!", style="magenta")
#     if keyword == "attach":
#         return attach_file(arg)
#     if keyword == "save":
#         return save_session(arg)
#     if keyword == "load":
#         return load_session(arg)
#     if keyword == "export":
#         return export_markdown(arg)
#     if keyword == "stats":
#         return get_stats()
#     if keyword == "system":
#         return set_system_prompt(arg)
#     if keyword == "clear":
#         clear_history()
#         return Text("")
#     if keyword == "models":
#         return list_models()
#     if keyword == "set":
#         if "=" in arg:
#             param, val = arg.split("=", 1)
#             return update_config(param, val)
#         else:
#             return Text("Usage: set <parameter>=<value>", style="red")
#     if keyword in ("rtlgen", "tbgen", "fpropgen", "report"):
#         return Text(_dispatch_design_instruction(f"generate {keyword}"))
#     # Supported shell commands or any Unix command
#     import shutil
#     if keyword in SHELL_COMMANDS or keyword == "cd" or shutil.which(keyword):
#         return Text(_run_shell_command(cmd))
#     if keyword == "agent":
#         try:
#             import subprocess
#             subcommand = arg.strip()
#             if not subcommand:
#                 return Text("Usage: agent <rtlgen|tbgen|fpropgen|report>", style="yellow")
#             result = subprocess.run(["python3", "-m", "saxoflow_agenticai.cli", subcommand], capture_output=True, text=True)
#             return Text(result.stdout + result.stderr)
#         except Exception as e:
#             return Text(f"Agentic AI execution failed: {e}", style="red")   
#     return handle_command(cmd, console)

def main() -> None:

    # Force headless mode for SaxoFlow inside Cool CLI
    # os.environ["SAXOFLOW_FORCE_HEADLESS"] = "1"
    cli_history = InMemoryHistory()

    builtin_cmds: List[str] = [
        "help", "quit", "exit", "simulate", "synth", "ai", "clear",
        "rtlgen", "tbgen", "fpropgen", "report", "attach", "save", "load",
        "export", "stats", "system", "models", "set",
    ]
    command_names: List[str] = builtin_cmds + list(SHELL_COMMANDS.keys()) + ["cd"]

    # 1. Try loading saxoflow commands
    try:
        from saxoflow.cli import cli as saxoflow_root_cli
        command_names += [f"saxoflow {cmd}" for cmd in saxoflow_root_cli.commands]
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load saxoflow commands - {e}[/yellow]")

    # 2. Try loading agentic AI commands
    try:
        from saxoflow_agenticai.cli import cli as agentic_cli
        command_names += [f"agent {cmd}" for cmd in agentic_cli.commands]
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load agentic AI commands - {e}[/yellow]")

    # ✅ Always define completer + session afterwards
    completer = WordCompleter(command_names, ignore_case=True)
    session = PromptSession(completer=completer, history=cli_history)


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
        style="light cyan",
    )

    while True:
        clear_terminal()
        print_banner(console)
        panel_width = int(console.width * 0.75)
        console.print(welcome_panel(welcome_text, panel_width=panel_width))
        console.print(tips)
        console.print("")
        for entry in conversation_history:
            upanel = user_input_panel(entry.get("user", ""), width=panel_width)
            console.print(upanel)
            assistant_msg = entry.get("assistant")
            if assistant_msg:
                if isinstance(assistant_msg, str):
                    assistant_renderable = Text(assistant_msg)
                else:
                    assistant_renderable = assistant_msg
                opanel = ai_panel(assistant_renderable)
                console.print(opanel)
            console.print("")  # extra spacing

        try:
            user_input = session.prompt("saxoflow> ")
        except (EOFError, KeyboardInterrupt):
            console.print(Text(
                "Until next time, may your timing constraints always be met and your logic always latch‑free.",
                style="cyan",
            ))
            break
        user_input = user_input.strip()
        if not user_input:
            continue

        first_token = user_input.split(maxsplit=1)[0].lower()
        if first_token in command_names:
            renderable = process_command(user_input)
            if renderable is None:
                console.print(Text(
                    "Until next time, may your timing constraints always be met and your logic always latch‑free.",
                    style="cyan",
                ))
                break
            if conversation_history or first_token not in ("clear",):
                conversation_history.append({"user": user_input, "assistant": renderable})
        else:
            conversation_history.append({"user": user_input})
            with console.status("[cyan]Working on it...", spinner="dots"):
                time.sleep(0.5)
                assistant_response = dispatch_input(user_input)
            conversation_history[-1]["assistant"] = assistant_response


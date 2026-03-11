# cool_cli/file_ops.py
"""
File creation and editing capabilities for the SaxoFlow AI Assistant.

This module lets the AI co-pilot create, write, and scaffold HDL files inside
SaxoFlow unit projects when the user asks for it in natural language.

Example user prompts handled:
  "create a mux design in SV and save it as mux.sv in a unit named mux"
  "generate a 4-bit adder and store it as adder.sv in unit adder"
  "write a D flip-flop to dff.v in the reg_lib project"

Public API
----------
- scaffold_unit_if_needed(unit_name, cwd) -> Path
- determine_dest_path(unit_root, filename, content_type) -> Path
- write_artifact(content, dest_path) -> Path
- handle_save_file(buddy_result, history) -> rich.panel.Panel | rich.text.Text

Design
------
- No changes to existing behavior: this module is only called when the buddy
  returns {"type": "save_file"}.
- Unit scaffolding reuses the existing `saxoflow unit` Click command logic
  (imports directly from saxoflow.unit_project) so no code is duplicated.
- Generation is done by calling the LLM via `ai_buddy.generate_code_for_save`,
  which builds a focused code-only prompt.
- All errors are caught and returned as Rich Text/Panel so the TUI never crashes.

Python: 3.9+
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Union

from rich.panel import Panel
from rich.text import Text
from cool_cli.ai_buddy import generate_code_for_save  # re-exported for monkeypatching
from cool_cli.ai_buddy import generate_patch_for_edit  # re-exported for monkeypatching
from cool_cli.ai_buddy import generate_explanation_for_file  # for handle_read_file
from cool_cli.ai_buddy import detect_companion_files  # companion file detection
from cool_cli.ai_buddy import generate_companion_file  # companion file generation

__all__ = [
    "scaffold_unit_if_needed",
    "determine_dest_path",
    "read_artifact",
    "write_artifact",
    "find_file_in_unit",
    "run_post_hook",
    "handle_save_file",
    "handle_edit_file",
    "handle_multi_file",
    "handle_read_file",
]

# ---------------------------------------------------------------------------
# Code-fence stripping
# ---------------------------------------------------------------------------

_CODEBLOCK_RE = re.compile(r"```(?:\w+)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """Return the code content from inside a markdown code fence if present."""
    m = _CODEBLOCK_RE.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return text.strip()

# ---------------------------------------------------------------------------
# File extension → content type mapping
# ---------------------------------------------------------------------------

_EXT_TO_CONTENT_TYPE = {
    ".sv": "rtl",
    ".svh": "rtl",
    ".v": "rtl",
    ".vh": "rtl",
    ".vhd": "rtl",
    ".vhdl": "rtl",
    ".sva": "formal",
    ".sby": "formal",
    ".tcl": "synth",
}

# Filename hint → testbench override (if "tb" or "testbench" appears in name)
_TB_NAME_RE = re.compile(r'\b(?:tb|testbench|test_bench)\b', re.IGNORECASE)


def _content_type_from_filename(filename: str) -> str:
    """Infer content type from filename: rtl / formal / synth / tb."""
    ext = Path(filename).suffix.lower()
    base = Path(filename).stem.lower()
    ctype = _EXT_TO_CONTENT_TYPE.get(ext, "rtl")
    if ctype == "rtl" and _TB_NAME_RE.search(base):
        return "tb"
    return ctype


# ---------------------------------------------------------------------------
# Destination path within a unit project
# ---------------------------------------------------------------------------

# Maps content_type → subdirectory within the unit project
_DEST_DIRS = {
    "rtl": {".sv": "source/rtl/systemverilog",
            ".svh": "source/rtl/include",
            ".v": "source/rtl/verilog",
            ".vh": "source/rtl/include",
            ".vhd": "source/rtl/vhdl",
            ".vhdl": "source/rtl/vhdl"},
    "tb": {".sv": "source/tb/systemverilog",
           ".v": "source/tb/verilog",
           ".vhd": "source/tb/vhdl",
           ".vhdl": "source/tb/vhdl"},
    "formal": {".sva": "formal/src",
               ".sv": "formal/src",
               ".sby": "formal/scripts"},
    "synth": {".tcl": "synthesis/scripts",
              ".v": "synthesis/src"},
}

_DEFAULT_DEST = "source/rtl/systemverilog"


def determine_dest_path(unit_root: Path, filename: str, content_type: str) -> Path:
    """Return the full destination path for *filename* within *unit_root*.

    Parameters
    ----------
    unit_root:
        Root directory of the unit/project.
    filename:
        Target filename (e.g. ``mux.sv``).
    content_type:
        One of ``"rtl"``, ``"tb"``, ``"formal"``, ``"synth"``.

    Returns
    -------
    Path
        Full absolute path where the file should be written.
    """
    ext = Path(filename).suffix.lower()
    sub = _DEST_DIRS.get(content_type, {}).get(ext, _DEFAULT_DEST)
    dest_dir = unit_root / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / filename


# ---------------------------------------------------------------------------
# Unit scaffolding
# ---------------------------------------------------------------------------

def scaffold_unit_if_needed(unit_name: str, cwd: Optional[Path] = None) -> Path:
    """Create (or locate) a SaxoFlow unit project named *unit_name*.

    Reuses the existing `saxoflow.unit_project` logic without running the
    Click CLI, so no subprocess is needed.

    Parameters
    ----------
    unit_name:
        Project folder name (e.g. ``"mux"``).
    cwd:
        Working directory to create the unit in. Defaults to ``Path.cwd()``.

    Returns
    -------
    Path
        Absolute path to the unit root (created if it didn't exist).
    """
    from saxoflow.unit_project import (  # noqa: PLC0415
        PROJECT_STRUCTURE,
        YOSYS_SYNTH_TEMPLATE,
        _create_directories,
        _copy_makefile_template,
        _write_yosys_template,
    )

    base = cwd or Path.cwd()
    unit_root = (base / unit_name).resolve()

    if unit_root.exists():
        return unit_root  # already scaffolded — reuse

    unit_root.mkdir(parents=True, exist_ok=False)
    _create_directories(unit_root, PROJECT_STRUCTURE)
    _copy_makefile_template(unit_root)
    _write_yosys_template(unit_root, YOSYS_SYNTH_TEMPLATE)
    return unit_root


# ---------------------------------------------------------------------------
# Write artifact
# ---------------------------------------------------------------------------

def _find_rtl_in_unit(unit_root: Path) -> Optional[Path]:
    """Return the first RTL source file found under *unit_root*/source/rtl/.

    Used to supply existing RTL context to the TB and formal generators so
    they can inspect the DUT's port list without the user having to paste it.

    Returns the first ``.sv`` or ``.v`` file found (SystemVerilog preferred),
    or ``None`` if no RTL exists yet.
    """
    rtl_root = unit_root / "source" / "rtl"
    # Prefer SystemVerilog; fall back to plain Verilog
    for ext in ("*.sv", "*.v"):
        candidates = [p for p in rtl_root.rglob(ext)
                      if not p.name.startswith(".") and p.suffix != ".gitkeep"]
        if candidates:
            return candidates[0]
    return None


def write_artifact(content: str, dest_path: Path) -> Path:
    """Write *content* to *dest_path*, creating parent directories as needed.

    Parameters
    ----------
    content:
        Text to write.
    dest_path:
        Destination file path (absolute or relative).

    Returns
    -------
    Path
        The resolved path of the written file.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(content, encoding="utf-8")
    return dest_path


def read_artifact(path: Path) -> str:
    """Read and return the content of an existing file.

    Parameters
    ----------
    path:
        Absolute path to the file to read.

    Returns
    -------
    str
        File content decoded as UTF-8.

    Raises
    ------
    OSError
        If the file does not exist or cannot be read.
    """
    return path.read_text(encoding="utf-8")


def find_file_in_unit(unit_root: Path, filename: str) -> Optional[Path]:
    """Search *unit_root* recursively for a file named *filename*.

    Parameters
    ----------
    unit_root:
        Root directory of the unit project to search within.
    filename:
        Bare filename including extension (e.g. ``"mux.sv"``).

    Returns
    -------
    Path | None
        First match found, or None if not found.
    """
    matches = list(unit_root.rglob(filename))
    return matches[0] if matches else None


def run_post_hook(
    unit_root: Path,
    hook_type: str,
    dest_path: Optional[Path] = None,
    content_type: str = "rtl",
    auto_fix: bool = True,
    _max_retries: int = 2,
) -> str:
    """Run a post-creation hook (sim / lint / synth / git) inside *unit_root*.

    Parameters
    ----------
    unit_root:
        The unit project directory to run the command in.
    hook_type:
        One of ``"sim"``, ``"lint"``, ``"synth"``, ``"git"``.
    dest_path:
        Optional path to the generated file.  When provided and the hook
        fails, the auto-fix loop reads this file, asks the LLM to fix the
        errors, writes the patched code back, and re-runs the hook
        (up to *_max_retries* times).
    content_type:
        HDL content type used when calling the LLM for auto-fix patches.
    auto_fix:
        When ``True`` (default) and *dest_path* is provided, attempt to
        auto-fix lint/sim errors via the LLM before giving up.
    _max_retries:
        Maximum number of LLM-fix + re-run cycles (default 2).

    Returns
    -------
    str
        Combined stdout+stderr from the command, or an error/timeout message.
        When auto-fix succeeds the message includes ``"(fixed after N attempt)"``
        so callers can detect it.
    """
    # ------------------------------------------------------------------
    # Git snapshot hook (optional, no retry)
    # ------------------------------------------------------------------
    if hook_type == "git":
        try:
            git_add = subprocess.run(
                ["git", "add", "-A"],
                cwd=str(unit_root),
                capture_output=True, text=True, timeout=30,
            )
            if git_add.returncode != 0:
                return "[git add failed — is this a git repo? Skipping snapshot.]"
            git_commit = subprocess.run(
                ["git", "commit", "-m", "saxoflow: auto checkpoint"],
                cwd=str(unit_root),
                capture_output=True, text=True, timeout=30,
            )
            out = (git_commit.stdout + git_commit.stderr).strip()
            return out or "[git commit: nothing to commit]"
        except FileNotFoundError:
            return "[git not found — install git to use snapshots]"
        except subprocess.TimeoutExpired:
            return "[git timed out]"
        except Exception as exc:  # noqa: BLE001
            return f"[git error: {exc}]"

    # ------------------------------------------------------------------
    # EDA hooks: sim / lint / synth
    # ------------------------------------------------------------------
    cmd_map: dict = {
        "sim":   ["saxoflow", "sim"],
        "lint":  ["saxoflow", "lint"],
        "synth": ["saxoflow", "synth"],
    }
    cmd = cmd_map.get(hook_type)
    if not cmd:
        return f"[unknown hook type: {hook_type}]"

    def _run_once() -> tuple:
        """Run the hook once; return (output_str, exit_code)."""
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(unit_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = (proc.stdout + proc.stderr).strip()
            return output or f"[{hook_type} completed with no output]", proc.returncode
        except subprocess.TimeoutExpired:
            return f"[{hook_type} timed out after 120 s]", -1
        except Exception as exc:  # noqa: BLE001
            return f"[{hook_type} error: {exc}]", -1

    output, exit_code = _run_once()

    # ------------------------------------------------------------------
    # Auto-fix loop — only when dest_path is provided and hook failed
    # ------------------------------------------------------------------
    if auto_fix and dest_path is not None and dest_path.is_file() and exit_code != 0:
        for attempt in range(1, _max_retries + 1):
            original_code = read_artifact(dest_path)
            if original_code is None:
                break  # can't read file — bail out

            try:
                patched = generate_patch_for_edit(
                    original_code=original_code,
                    edit_request=(
                        f"Fix the following {hook_type} errors in this file:\n{output}"
                    ),
                    content_type=content_type,
                )
            except Exception:  # noqa: BLE001
                break  # LLM unavailable — bail out

            patched_code = _strip_code_fences(patched)
            if not patched_code.strip():
                break  # empty patch — bail out

            dest_path.write_text(patched_code, encoding="utf-8")
            output, exit_code = _run_once()

            if exit_code == 0:
                return (
                    output
                    + f"\n[auto-fix: resolved in {attempt} attempt(s)]"
                )

        # Could not fix after all retries
        return output + f"\n[auto-fix: could not resolve errors after {_max_retries} attempt(s)]"

    return output


# ---------------------------------------------------------------------------
# Orchestrator — called from agentic.py
# ---------------------------------------------------------------------------

def handle_save_file(
    buddy_result: dict,
    history: list,
) -> Union[Panel, Text]:
    """Generate content via LLM and write it to the correct unit path.

    Parameters
    ----------
    buddy_result:
        ``{"type": "save_file", "spec": str, "filename": str,
           "unit": str, "content_type": str}``
    history:
        Conversation history (passed on to the generation call).

    Returns
    -------
    Panel | Text
        A Rich Panel confirming success, or a red Text on failure.
    """
    spec = buddy_result.get("spec", "")
    filename = buddy_result.get("filename", "")
    unit_name = buddy_result.get("unit", "")
    content_type = buddy_result.get("content_type", "rtl")

    if not filename:
        return Text(
            "Could not determine target filename from your request. "
            "Please include a filename with extension, e.g. 'save as mux.sv'.",
            style="bold yellow",
        )

    # Step 1 — generate code via LLM / specialist agent
    # For TB and formal content, discover any existing RTL in the unit so the
    # agent can see the DUT's ports and generate a better artifact.
    rtl_context = ""
    top_module = ""
    if content_type in ("tb", "formal") and unit_name:
        _probe_root = Path.cwd() / unit_name
        if _probe_root.is_dir():
            _rtl_path = _find_rtl_in_unit(_probe_root)
            if _rtl_path is not None:
                try:
                    rtl_context = _rtl_path.read_text(encoding="utf-8")
                    top_module = _rtl_path.stem
                except OSError:
                    pass  # non-fatal: agent still works without context

    try:
        code = generate_code_for_save(
            spec, content_type,
            rtl_context=rtl_context,
            top_module=top_module,
        )
    except Exception as exc:  # noqa: BLE001
        return Text(f"Code generation failed: {exc}", style="bold red")

    if not code.strip():
        return Text("LLM returned no content — try rephrasing your request.", style="bold yellow")

    # Strip markdown code fences before writing (LLM wraps output in ``` blocks)
    code = _strip_code_fences(code)

    # Step 2 — scaffold unit (if requested and not already present)
    unit_root: Optional[Path] = None
    created_unit = False
    if unit_name:
        try:
            existed = (Path.cwd() / unit_name).exists()
            unit_root = scaffold_unit_if_needed(unit_name)
            created_unit = not existed
        except Exception as exc:  # noqa: BLE001
            return Text(f"Failed to create unit '{unit_name}': {exc}", style="bold red")

    # Step 3 — determine destination path
    if unit_root:
        dest = determine_dest_path(unit_root, filename, content_type)
    else:
        # No unit specified: write to cwd
        dest = Path.cwd() / filename

    # Step 4 — write the file
    try:
        written = write_artifact(code, dest)
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to write file: {exc}", style="bold red")

    # Step 5 — build success panel
    lines = []
    if created_unit:
        lines.append(f"[bold green]✓ Unit created:[/bold green]  [dim]{unit_root}[/dim]")
    elif unit_root:
        lines.append(f"[bold green]✓ Unit:[/bold green]  [dim]{unit_root}[/dim] (already existed)")
    lines.append(f"[bold green]✓ File written:[/bold green]  [dim]{written}[/dim]")

    # Step 5a — detect and generate companion files (e.g. alu_pkg.sv)
    companion_names = detect_companion_files(filename, code)
    for companion in companion_names:
        # Skip if the companion already exists in the unit
        companion_dest = (
            determine_dest_path(unit_root, companion, content_type)
            if unit_root else Path.cwd() / companion
        )
        if companion_dest.exists():
            lines.append(
                f"[dim]✓ Companion already exists:[/dim]  [dim]{companion_dest}[/dim]"
            )
            continue
        try:
            companion_code_raw = generate_companion_file(
                companion_filename=companion,
                main_code=code,
                main_filename=filename,
                spec=spec,
            )
            companion_code = _strip_code_fences(companion_code_raw)
            write_artifact(companion_code, companion_dest)
            lines.append(
                f"[bold green]✓ Companion written:[/bold green]  [dim]{companion_dest}[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            lines.append(
                f"[yellow]⚠ Could not generate companion {companion!r}: {exc}[/yellow]"
            )

    lines.append("")
    lines.append(
        f"[dim]To open:[/dim]  [bold white]cat {written.relative_to(Path.cwd()) if written.is_relative_to(Path.cwd()) else written}[/bold white]"
    )
    if unit_name:
        lines.append(
            f"[dim]To simulate:[/dim]  [bold white]cd {unit_name} && saxoflow sim[/bold white]"
        )

    # Step 6 — optional post-creation hook
    post_hook = buddy_result.get("post_hook")
    if post_hook and unit_root:
        hook_out = run_post_hook(
            unit_root, post_hook,
            dest_path=written, content_type=content_type,
        )
        lines.append(f"\n[dim]{post_hook} output:[/dim]\n{hook_out}")

    return Panel(
        Text.from_markup("\n".join(lines)),
        title="[bold green]File Created[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# Read / explain handler
# ---------------------------------------------------------------------------

def handle_read_file(
    buddy_result: dict,
    history: list,
) -> Union[Panel, Text]:
    """Find an HDL file on disk and ask the LLM to explain it.

    Parameters
    ----------
    buddy_result:
        Must contain ``{"type": "read_file", "filename": str, "question": str}``.
    history:
        Conversation history list (passed through for context, not currently used
        by generate_explanation_for_file but kept for API consistency).

    Returns
    -------
    rich.panel.Panel
        A panel containing the LLM's explanation in Markdown.
    rich.text.Text
        Plain-text error message if the file cannot be found or LLM fails.
    """
    from rich.markdown import Markdown  # noqa: PLC0415

    filename: str = buddy_result.get("filename", "")
    question: str = buddy_result.get("question", f"explain {filename}")

    if not filename:
        return Text("No filename found in request.", style="yellow")

    # Search for the file starting from cwd, then one level up
    import os  # noqa: PLC0415
    search_root = Path(os.getcwd())
    found_path = find_file_in_unit(search_root, filename)

    # If not found under unit structure, try flat cwd
    if found_path is None:
        candidate = search_root / filename
        if candidate.is_file():
            found_path = candidate

    if found_path is None:
        return Text(
            f"File not found: {filename!r}\n"
            "Check the filename or navigate to the unit directory first.",
            style="yellow",
        )

    code = read_artifact(found_path)
    if code is None:
        return Text(f"Could not read {found_path}.", style="red")

    try:
        explanation = generate_explanation_for_file(
            filename=filename,
            code=code,
            question=question,
        )
    except Exception as exc:  # noqa: BLE001
        return Text(f"LLM error: {exc}", style="red")

    return Panel(
        Markdown(explanation),
        title=f"[bold cyan]Explanation: {filename}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# Edit handler
# ---------------------------------------------------------------------------

def handle_edit_file(
    buddy_result: dict,
    history: list,
) -> Union[Panel, Text]:
    """Apply LLM-generated edits to an existing file and write it back.

    Parameters
    ----------
    buddy_result:
        ``{"type": "edit_file", "spec": str, "filename": str,
           "unit": str, "edit_request": str, "content_type": str,
           "post_hook": str | None}``
    history:
        Conversation history (reserved for future context).
    """
    filename = buddy_result.get("filename", "")
    unit_name = buddy_result.get("unit", "")
    edit_request = buddy_result.get("edit_request") or buddy_result.get("spec", "")
    content_type = buddy_result.get("content_type", "rtl")
    post_hook = buddy_result.get("post_hook")

    if not filename:
        return Text(
            "Could not determine target filename. Please include a filename with extension.",
            style="bold yellow",
        )

    # Locate the file
    unit_root: Optional[Path] = None
    if unit_name:
        unit_root = (Path.cwd() / unit_name).resolve()
        if not unit_root.exists():
            return Text(
                f"Unit '{unit_name}' not found. Create it first with: "
                f"saxoflow unit {unit_name}",
                style="bold yellow",
            )
        target = find_file_in_unit(unit_root, filename)
    else:
        candidate = Path.cwd() / filename
        target = candidate if candidate.exists() else None

    if target is None or not target.exists():
        loc = f"unit '{unit_name}'" if unit_name else "current directory"
        return Text(
            f"File '{filename}' not found in {loc}. "
            "Use 'create' to generate it first.",
            style="bold yellow",
        )

    # Read original content
    try:
        original = read_artifact(target)
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to read '{filename}': {exc}", style="bold red")

    # Generate patched version via LLM
    try:
        patched = generate_patch_for_edit(original, edit_request, content_type)
    except Exception as exc:  # noqa: BLE001
        return Text(f"Code edit generation failed: {exc}", style="bold red")

    if not patched.strip():
        return Text(
            "LLM returned no content — try rephrasing your edit request.",
            style="bold yellow",
        )

    patched = _strip_code_fences(patched)

    # Write back
    try:
        written = write_artifact(patched, target)
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to write file: {exc}", style="bold red")

    short_req = edit_request[:80] + ("..." if len(edit_request) > 80 else "")
    lines = [
        f"[bold green]✓ File edited:[/bold green]  [dim]{written}[/dim]",
        "",
        f"[dim]Change applied:[/dim] {short_req}",
    ]
    if unit_name:
        lines.append(
            f"[dim]To simulate:[/dim]  [bold white]cd {unit_name} && saxoflow sim[/bold white]"
        )

    if post_hook and unit_root:
        hook_out = run_post_hook(unit_root, post_hook)
        lines.append(f"\n[dim]{post_hook} output:[/dim]\n{hook_out}")

    return Panel(
        Text.from_markup("\n".join(lines)),
        title="[bold green]File Edited[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# Multi-file handler
# ---------------------------------------------------------------------------

def handle_multi_file(
    buddy_result: dict,
    history: list,
) -> Union[Panel, Text]:
    """Generate multiple HDL files (RTL + TB + formal) in one shot.

    Parameters
    ----------
    buddy_result:
        ``{"type": "multi_file", "spec": str, "unit": str,
           "design_name": str,
           "files": [{"filename": str, "content_type": str}, ...],
           "post_hook": str | None}``
    history:
        Conversation history (reserved for future context).
    """
    spec = buddy_result.get("spec", "")
    unit_name = buddy_result.get("unit", "")
    files = buddy_result.get("files", [])
    post_hook = buddy_result.get("post_hook")

    if not files:
        return Text("No files specified in multi-file request.", style="bold yellow")

    # Scaffold unit once
    unit_root: Optional[Path] = None
    created_unit = False
    if unit_name:
        try:
            existed = (Path.cwd() / unit_name).exists()
            unit_root = scaffold_unit_if_needed(unit_name)
            created_unit = not existed
        except Exception as exc:  # noqa: BLE001
            return Text(f"Failed to create unit '{unit_name}': {exc}", style="bold red")

    result_lines: list = []
    if created_unit:
        result_lines.append(f"[bold green]✓ Unit created:[/bold green]  [dim]{unit_root}[/dim]")
    elif unit_root:
        result_lines.append(f"[bold green]✓ Unit:[/bold green]  [dim]{unit_root}[/dim] (existing)")

    errors: list = []
    for file_spec in files:
        filename = file_spec.get("filename", "")
        content_type = file_spec.get("content_type", "rtl")
        if not filename:
            continue

        try:
            code = generate_code_for_save(
                f"{spec} — generate the {content_type} file: {filename}",
                content_type,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{filename}: generation failed ({exc})")
            continue

        if not code.strip():
            errors.append(f"{filename}: LLM returned no content")
            continue

        code = _strip_code_fences(code)

        dest = (
            determine_dest_path(unit_root, filename, content_type)
            if unit_root else Path.cwd() / filename
        )

        try:
            written = write_artifact(code, dest)
            result_lines.append(
                f"[bold green]✓ {content_type.upper()}:[/bold green]  [dim]{written}[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{filename}: write failed ({exc})")

    if errors:
        for err in errors:
            result_lines.append(f"[bold red]✗ {err}[/bold red]")

    if unit_name:
        result_lines.append(
            f"\n[dim]To simulate:[/dim]  [bold white]cd {unit_name} && saxoflow sim[/bold white]"
        )

    if post_hook and unit_root:
        hook_out = run_post_hook(unit_root, post_hook)
        result_lines.append(f"\n[dim]{post_hook} output:[/dim]\n{hook_out}")

    has_success = any("✓" in ln for ln in result_lines)
    border = "green" if has_success and not errors else ("yellow" if has_success else "red")
    title = (
        "[bold green]Files Created[/bold green]" if not errors
        else "[bold yellow]Files Created (with errors)[/bold yellow]"
    )

    return Panel(
        Text.from_markup("\n".join(result_lines)),
        title=title,
        border_style=border,
        padding=(1, 2),
    )

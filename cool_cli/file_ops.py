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

import os
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
_MODULE_DECL_RE = re.compile(
    r"\bmodule\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b"
)

_HDL_KEYWORDS = {
    "input",
    "output",
    "inout",
    "wire",
    "reg",
    "logic",
    "bit",
    "tri",
    "signed",
    "unsigned",
    "var",
    "parameter",
    "localparam",
    "integer",
    "int",
    "longint",
}


def _strip_code_fences(text: str) -> str:
    """Return the code content from inside a markdown code fence if present."""
    m = _CODEBLOCK_RE.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return text.strip()


def _extract_module_name_from_code(code: str) -> str:
    """Return the first Verilog/SystemVerilog module name in *code*."""
    match = _MODULE_DECL_RE.search(code or "")
    return match.group(1) if match else ""


def _clean_verilog_identifier(name: str, default: str = "dut") -> str:
    """Return *name* converted into a conservative Verilog identifier."""
    ident = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    ident = ident.strip("_")
    if not ident:
        ident = default
    if not (ident[0].isalpha() or ident[0] == "_"):
        ident = f"{default}_{ident}"
    return ident


def _strip_hdl_comments(code: str) -> str:
    """Remove simple Verilog/SystemVerilog comments for lightweight parsing."""
    code = re.sub(r"/\*.*?\*/", "", code or "", flags=re.DOTALL)
    return re.sub(r"//.*", "", code)


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _capture_balanced(text: str, start: int) -> tuple:
    """Capture text inside balanced parentheses starting at *start*."""
    if start >= len(text) or text[start] != "(":
        return "", start
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    return "", start


def _split_hdl_items(text: str) -> list:
    """Split a comma-separated HDL list without splitting ranges/expressions."""
    items = []
    start = 0
    depth = 0
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = {")", "]", "}"}
    for index, char in enumerate(text):
        if char in pairs:
            depth += 1
        elif char in closers and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            item = text[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
    tail = text[start:].strip()
    if tail:
        items.append(tail)
    return items


def _extract_module_signature(code: str, module_name: str = "") -> dict:
    """Return a lightweight module signature: name, params, and port header."""
    clean = _strip_hdl_comments(code)
    if module_name:
        pattern = re.compile(
            rf"\bmodule\s+(?:automatic\s+)?{re.escape(module_name)}\b"
        )
    else:
        pattern = _MODULE_DECL_RE
    match = pattern.search(clean)
    if not match:
        return {"name": "", "params": "", "ports": "", "body": ""}

    name = module_name or match.group(1)
    index = _skip_ws(clean, match.end())
    params = ""
    if index < len(clean) and clean[index] == "#":
        index = _skip_ws(clean, index + 1)
        if index < len(clean) and clean[index] == "(":
            params, index = _capture_balanced(clean, index)
            index = _skip_ws(clean, index)

    ports = ""
    body_start = index
    if index < len(clean) and clean[index] == "(":
        ports, index = _capture_balanced(clean, index)
        body_start = index
    semicolon = clean.find(";", body_start)
    if semicolon >= 0:
        body_start = semicolon + 1
    endmodule = clean.find("endmodule", body_start)
    body = clean[body_start:endmodule] if endmodule >= 0 else clean[body_start:]
    return {"name": name, "params": params, "ports": ports, "body": body}


def _parse_param_declarations(params: str) -> tuple:
    """Return harness parameter declarations and names from a parameter list."""
    declarations = []
    names = []
    for raw_item in _split_hdl_items(params):
        item = raw_item.strip().rstrip(";")
        if not item:
            continue
        declaration = item
        if not re.match(r"\b(?:parameter|localparam)\b", declaration):
            declaration = f"parameter {declaration}"

        left = declaration.split("=", 1)[0]
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", left)
        candidates = [tok for tok in tokens if tok not in _HDL_KEYWORDS]
        if candidates:
            names.append(candidates[-1])
            declarations.append(declaration)
    return declarations, names


def _parse_ports_from_header(header: str) -> list:
    """Parse ANSI-style module ports from a module header."""
    ports = []
    seen = set()
    last_direction = ""
    last_range = ""
    for raw_item in _split_hdl_items(header):
        item = raw_item.strip().rstrip(";")
        if not item:
            continue

        direction_match = re.search(r"\b(input|output|inout)\b", item)
        direction = direction_match.group(1) if direction_match else last_direction
        if not direction:
            continue

        range_match = re.search(r"(\[[^\]]+\])", item)
        if direction_match:
            port_range = range_match.group(1) if range_match else ""
            last_direction = direction
            last_range = port_range
        else:
            port_range = range_match.group(1) if range_match else last_range

        left = item.split("=", 1)[0]
        left = re.sub(r"\[[^\]]+\]", " ", left)
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", left)
        candidates = [tok for tok in tokens if tok not in _HDL_KEYWORDS]
        if not candidates:
            continue
        name = candidates[-1]
        if name in seen:
            continue
        seen.add(name)
        ports.append({"direction": direction, "range": port_range, "name": name})
    return ports


def _parse_ports_from_body(body: str, header: str = "") -> list:
    """Parse non-ANSI Verilog port declarations from a module body."""
    header_names = [
        item.strip()
        for item in _split_hdl_items(header)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", item.strip())
    ]
    order = {name: index for index, name in enumerate(header_names)}
    ports = []
    seen = set()

    for match in re.finditer(r"\b(input|output|inout)\b\s+([^;]+);", body):
        direction = match.group(1)
        decl = match.group(2).strip()
        range_match = re.search(r"(\[[^\]]+\])", decl)
        port_range = range_match.group(1) if range_match else ""
        decl = re.sub(r"\[[^\]]+\]", " ", decl)
        decl = re.sub(
            r"\b(?:wire|reg|logic|bit|tri|signed|unsigned)\b",
            " ",
            decl,
        )
        for name_item in _split_hdl_items(decl):
            name_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", name_item)
            candidates = [tok for tok in name_tokens if tok not in _HDL_KEYWORDS]
            if not candidates:
                continue
            name = candidates[-1]
            if name in seen:
                continue
            seen.add(name)
            ports.append({"direction": direction, "range": port_range, "name": name})

    if order:
        ports.sort(key=lambda port: order.get(port["name"], len(order)))
    return ports


def _parse_rtl_signature(rtl_code: str, top_module: str = "") -> dict:
    """Extract a lightweight RTL signature for formal harness generation."""
    signature = _extract_module_signature(rtl_code, top_module)
    module_name = signature["name"] or _extract_module_name_from_code(rtl_code)
    if module_name and module_name != signature["name"]:
        signature = _extract_module_signature(rtl_code, module_name)

    ports = _parse_ports_from_header(signature.get("ports", ""))
    if not ports:
        ports = _parse_ports_from_body(
            signature.get("body", ""),
            signature.get("ports", ""),
        )
    param_decls, param_names = _parse_param_declarations(signature.get("params", ""))
    return {
        "name": _clean_verilog_identifier(module_name or top_module or "dut"),
        "params": param_decls,
        "param_names": param_names,
        "ports": ports,
    }


def _indent_code_block(code: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else "" for line in code.splitlines())


def _is_formal_harness(code: str) -> bool:
    """Return True when *code* already contains a complete module wrapper."""
    clean = _strip_hdl_comments(code)
    return bool(_MODULE_DECL_RE.search(clean) and re.search(r"\bendmodule\b", clean))


def _ensure_formal_harness(
    formal_code: str,
    rtl_code: str,
    top_module: str = "",
    harness_module: str = "formal_top",
) -> str:
    """Wrap loose generated SVA in a DUT harness when needed."""
    if _is_formal_harness(formal_code):
        return formal_code

    signature = _parse_rtl_signature(rtl_code, top_module)
    dut_name = signature["name"]
    harness_name = _clean_verilog_identifier(harness_module, "formal_top")
    lines = [
        "// SaxoFlow generated formal harness.",
        f"module {harness_name};",
    ]

    for declaration in signature["params"]:
        lines.append(f"    {declaration};")

    port_names = set()
    for port in signature["ports"]:
        name = port["name"]
        port_names.add(name)
        port_range = f" {port['range']}" if port["range"] else ""
        if port["direction"] == "output":
            lines.append(f"    wire{port_range} {name};")
        elif port["direction"] == "inout":
            lines.append(f"    (* anyseq *) wire{port_range} {name};")
        else:
            lines.append(f"    (* anyseq *) reg{port_range} {name};")

    clean_formal = _strip_hdl_comments(formal_code)
    if re.search(r"\b(?:posedge|negedge)\s+clk\b", clean_formal) and "clk" not in port_names:
        lines.append("    (* gclk *) reg clk;")
        port_names.add("clk")
    if re.search(r"\breset\b", clean_formal) and "reset" not in port_names:
        lines.append("    wire reset = 1'b0;")
        port_names.add("reset")

    if signature["ports"] or signature["param_names"]:
        lines.append("")

    if signature["param_names"]:
        lines.append(f"    {dut_name} #(")
        overrides = [
            f"        .{name}({name})" for name in signature["param_names"]
        ]
        lines.append(",\n".join(overrides))
        lines.append("    ) dut (")
    else:
        lines.append(f"    {dut_name} dut (")

    if signature["ports"]:
        connections = [
            f"        .{port['name']}({port['name']})"
            for port in signature["ports"]
        ]
        lines.append(",\n".join(connections))
    lines.append("    );")

    if formal_code.strip():
        lines.extend(["", "    // Generated formal properties."])
        lines.append(_indent_code_block(formal_code.strip(), 4))

    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def _write_generated_formal_spec(
    unit_root: Path,
    rtl_path: Path,
    formal_path: Path,
    formal_top: str,
) -> Path:
    """Write a runnable SymbiYosys spec targeting a generated formal harness."""
    spec_path = unit_root / "formal" / "scripts" / "spec.sby"
    reports_dir = unit_root / "formal" / "reports"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    rtl_rel = os.path.relpath(rtl_path, reports_dir).replace(os.sep, "/")
    formal_rel = os.path.relpath(formal_path, reports_dir).replace(os.sep, "/")
    formal_top = _clean_verilog_identifier(formal_top, "formal_top")

    spec = f"""# SaxoFlow generated formal specification
#
# This file is generated when the AI creates a design-specific formal harness.
# It reads the RTL and the generated harness, then proves the harness top.

[tasks]
bmc_z3
prove_z3

[options]
bmc_z3: mode bmc
bmc_z3: depth 20
prove_z3: mode prove
prove_z3: depth 20

[engines]
bmc_z3: smtbmc z3
prove_z3: smtbmc z3

[script]
read -formal -sv {rtl_path.name} {formal_path.name}
prep -top {formal_top}

[files]
{rtl_rel}
{formal_rel}
"""
    spec_path.write_text(spec, encoding="utf-8")
    return spec_path

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
        _ensure_gitignore_bender_local,
        _write_bender_manifest,
        _write_formal_templates,
        _write_yosys_template,
    )

    base = cwd or Path.cwd()
    unit_root = (base / unit_name).resolve()

    if unit_root.exists():
        # Existing unit: backfill starter artifacts if this unit was created
        # before newer scaffolding features were added.
        spec_path = unit_root / "formal/scripts/spec.sby"
        harness_path = unit_root / "formal/src/formal_top.sv"
        if not spec_path.exists() or not harness_path.exists():
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            harness_path.parent.mkdir(parents=True, exist_ok=True)
            _write_formal_templates(unit_root, unit_name)
        bender_path = unit_root / "Bender.yml"
        if not bender_path.exists():
            _write_bender_manifest(unit_root, unit_name)
        _ensure_gitignore_bender_local(unit_root)
        return unit_root  # already scaffolded — reuse

    unit_root.mkdir(parents=True, exist_ok=False)
    _create_directories(unit_root, PROJECT_STRUCTURE)
    _copy_makefile_template(unit_root)
    _write_yosys_template(unit_root, YOSYS_SYNTH_TEMPLATE)
    _write_formal_templates(unit_root, unit_name)
    _write_bender_manifest(unit_root, unit_name)
    _ensure_gitignore_bender_local(unit_root)
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


def _verify_placement(
    written: Path,
    unit_root: Optional[Path],
    filename: str,
    content_type: str,
) -> tuple:
    """Verify *written* is correctly placed inside *unit_root* and move it if not.

    When a unit was created but the file somehow ended up outside the unit
    (e.g. in cwd), this function relocates it to the correct subdirectory so
    the unit project stays consistent.

    Parameters
    ----------
    written:
        Path the file was actually written to.
    unit_root:
        Expected unit project root (or None if no unit was requested).
    filename:
        Bare filename, e.g. ``"alu.sv"``.
    content_type:
        One of ``"rtl"``, ``"tb"``, ``"formal"``, ``"synth"``.

    Returns
    -------
    (final_path, message)
        *final_path* is where the file resides after the check (may be moved).
        *message* is a Rich-markup string describing the result::

            "[green]✓ Placement OK[/green]: alu/source/rtl/systemverilog/alu.sv"
            "[yellow]⚠ Moved to correct location[/yellow]: alu/source/rtl/..."
    """
    import shutil  # noqa: PLC0415
    cwd = Path.cwd()

    if unit_root is None:
        # No unit was requested — file belongs in cwd, nothing to verify.
        rel = written.relative_to(cwd) if written.is_relative_to(cwd) else written
        return written, f"[green]✓ Placement OK[/green]: [dim]{rel}[/dim]"

    expected_dest = determine_dest_path(unit_root, filename, content_type)

    if written.resolve() == expected_dest.resolve():
        rel = written.relative_to(cwd) if written.is_relative_to(cwd) else written
        return written, f"[green]✓ Placement verified[/green]: [dim]{rel}[/dim]"

    # File landed outside the unit (e.g. cwd) — relocate it.
    expected_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(written), str(expected_dest))
    rel = expected_dest.relative_to(cwd) if expected_dest.is_relative_to(cwd) else expected_dest
    return expected_dest, (
        f"[yellow]⚠ Relocated to correct unit path[/yellow]: [dim]{rel}[/dim]"
    )


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
    rtl_path_for_formal: Optional[Path] = None
    if content_type in ("tb", "formal") and unit_name:
        _probe_root = Path.cwd() / unit_name
        if _probe_root.is_dir():
            _rtl_path = _find_rtl_in_unit(_probe_root)
            if _rtl_path is not None:
                try:
                    rtl_context = _rtl_path.read_text(encoding="utf-8")
                    top_module = _extract_module_name_from_code(rtl_context) or _rtl_path.stem
                    rtl_path_for_formal = _rtl_path
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

    if content_type == "formal" and unit_root and rtl_context:
        code = _ensure_formal_harness(
            formal_code=code,
            rtl_code=rtl_context,
            top_module=top_module,
            harness_module=Path(filename).stem,
        )

    # Step 4 — write the file
    try:
        written = write_artifact(code, dest)
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to write file: {exc}", style="bold red")

    # Step 4a — verify the file is in the correct unit subdirectory.
    # If it somehow landed outside the unit (e.g. LLM fallback spec omitted
    # "in unit X"), automatically relocate it and surface the correction.
    written, placement_msg = _verify_placement(written, unit_root, filename, content_type)

    formal_spec_written: Optional[Path] = None
    if (
        content_type == "formal"
        and unit_root is not None
        and rtl_path_for_formal is not None
    ):
        formal_top = _extract_module_name_from_code(code) or Path(filename).stem
        try:
            formal_spec_written = _write_generated_formal_spec(
                unit_root=unit_root,
                rtl_path=rtl_path_for_formal,
                formal_path=written,
                formal_top=formal_top,
            )
        except Exception:
            formal_spec_written = None

    # Step 5 — build success panel
    lines = []
    if created_unit:
        lines.append(f"[bold green]✓ Unit created:[/bold green]  [dim]{unit_root}[/dim]")
    elif unit_root:
        lines.append(f"[bold green]✓ Unit:[/bold green]  [dim]{unit_root}[/dim] (already existed)")
    lines.append(f"[bold green]✓ File written:[/bold green]  [dim]{written}[/dim]")
    lines.append(placement_msg)
    if formal_spec_written is not None:
        lines.append(
            f"[bold green]✓ Formal spec:[/bold green]  [dim]{formal_spec_written}[/dim]"
        )

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
    rtl_context = ""
    top_module = buddy_result.get("design_name", "") or ""
    rtl_written: Optional[Path] = None

    priority = {"rtl": 0, "tb": 1, "formal": 2}
    ordered_files = sorted(
        files,
        key=lambda item: priority.get(item.get("content_type", "rtl"), 9),
    )

    for file_spec in ordered_files:
        filename = file_spec.get("filename", "")
        content_type = file_spec.get("content_type", "rtl")
        if not filename:
            continue

        file_prompt = f"{spec} — generate the {content_type} file: {filename}"
        gen_kwargs = {}
        if content_type in ("tb", "formal"):
            gen_kwargs["rtl_context"] = rtl_context
            gen_kwargs["top_module"] = top_module or Path(filename).stem

        try:
            code = generate_code_for_save(
                file_prompt,
                content_type,
                **gen_kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{filename}: generation failed ({exc})")
            continue

        if not code.strip():
            errors.append(f"{filename}: LLM returned no content")
            continue

        code = _strip_code_fences(code)

        if content_type == "rtl":
            rtl_context = code
            top_module = _extract_module_name_from_code(code) or Path(filename).stem
        elif content_type == "formal" and unit_root and rtl_context:
            code = _ensure_formal_harness(
                formal_code=code,
                rtl_code=rtl_context,
                top_module=top_module,
                harness_module=Path(filename).stem,
            )

        dest = (
            determine_dest_path(unit_root, filename, content_type)
            if unit_root else Path.cwd() / filename
        )

        try:
            written = write_artifact(code, dest)
            result_lines.append(
                f"[bold green]✓ {content_type.upper()}:[/bold green]  [dim]{written}[/dim]"
            )
            if content_type == "rtl":
                rtl_written = written
            elif content_type == "formal" and unit_root and rtl_written is not None:
                formal_top = _extract_module_name_from_code(code) or Path(filename).stem
                spec_written = _write_generated_formal_spec(
                    unit_root=unit_root,
                    rtl_path=rtl_written,
                    formal_path=written,
                    formal_top=formal_top,
                )
                result_lines.append(
                    f"[bold green]✓ FORMAL SPEC:[/bold green]  [dim]{spec_written}[/dim]"
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

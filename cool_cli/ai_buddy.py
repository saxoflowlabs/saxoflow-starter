# cool_cli/ai_buddy.py
"""
AI Buddy utilities for SaxoFlow.

This module exposes:
- ACTION_KEYWORDS: Canonical mapping from user intents to internal actions.
- detect_action(): Keyword-based intent detector.
- ask_ai_buddy(): High-level chat/review orchestrator that either chats with an LLM,
  triggers review agents, or returns an action token for downstream tools.

Behavior-preserving notes:
- Return shapes match the original code:
  * {"type": "need_file", "message": ...}
  * {"type": "review_result", "action": <str>, "message": <str>}
  * {"type": "action", "action": <str>, "message": <str>}
  * {"type": "chat", "message": <str>}
- On exceptions, a structured error is returned instead of allowing crashes:
  * {"type": "error", "message": <str>}

Python 3.9+ compatible.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Literal, TypedDict

from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.agent_manager import AgentManager

__all__ = [
    "MAX_HISTORY_TURNS",
    "ACTION_KEYWORDS",
    "detect_action",
    "detect_save_intent",
    "detect_edit_intent",
    "detect_multi_file_intent",
    "detect_read_intent",
    "generate_code_for_save",
    "generate_patch_for_edit",
    "generate_explanation_for_file",
    "project_context",
    "ask_ai_buddy",
]


# =============================================================================
# Constants & Configuration
# =============================================================================

MAX_HISTORY_TURNS: int = 5

# ---------------------------------------------------------------------------
# SaxoFlow identity context — prepended to every buddy prompt so the model
# always knows where it is and what it can do, without needing a prior
# conversation to establish context.
# ---------------------------------------------------------------------------
SAXOFLOW_SYSTEM_CONTEXT: str = """\
You are the SaxoFlow AI Assistant, an intelligent co-pilot embedded directly \
inside SaxoFlow — an open-source professional RTL design and verification \
environment for IC design education and research.

== IDENTITY ==
When asked who you are, always say: "I am the SaxoFlow AI Assistant, your \
co-pilot for RTL design, verification, and EDA toolchain management inside \
SaxoFlow."

== SAXOFLOW SHELL COMMANDS ==
saxoflow install <tool|preset>  — install an EDA tool or preset toolset
saxoflow diagnose               — check installed tools and environment health
saxoflow init-env               — interactive tool setup wizard
saxoflow teach <pack>           — start an AI-guided interactive tutorial pack
saxoflow run                    — run the full design flow on the current project
saxoflow sim                    — run simulation (Icarus Verilog)
saxoflow sim-verilator          — run simulation (Verilator)
saxoflow synth                  — run RTL synthesis (Yosys)
saxoflow formal                 — run formal verification (SymbiYosys)
saxoflow wave                   — open waveform viewer (GTKWave)
saxoflow clean                  — clean build artifacts
saxoflow check-tools            — verify tool availability
saxoflow unit                   — run unit project checks

== AI ASSISTANT COMMANDS (type directly in the SaxoFlow shell) ==
rtlgen      — generate RTL (Verilog/SystemVerilog) from a natural-language spec
tbgen       — generate a testbench for a given RTL module
fpropgen    — generate formal SVA properties for a module
debug       — AI-assisted debug of simulation or synthesis output
report      — generate a design report from current flow outputs
fullpipeline — run the full AI-assisted design pipeline end-to-end
review rtl  — review an RTL file for quality and correctness
review testbench — review a testbench file
review formal    — review formal property files

== AVAILABLE EDA TOOLS ==
Simulation:   iverilog, verilator
Synthesis:    yosys (with slang SystemVerilog frontend)
Formal:       symbiyosys
FPGA:         nextpnr, openfpgaloader, vivado
ASIC/PD:      openroad, klayout, magic, netgen
Waveform:     gtkwave
HDL deps:     bender
IDE:          vscode

== INSTALL PRESETS (saxoflow install <preset>) ==
sim_tools           — iverilog, verilator
formal_tools        — symbiyosys
fpga_tools          — nextpnr, openfpgaloader, vivado, bender
asic_tools          — openroad, klayout, magic, netgen, bender
base_tools          — gtkwave, yosys
ethz_ic_design_tools — verilator, yosys, openroad, klayout, bender
                       (full open-source IC design flow for ETH Zurich VLSI2)

== TUTORIAL PACKS ==
ethz_ic_design   — ETH Zurich open-source IC design flow (step-by-step guided)
efcl_winter2026  — EFCL Winter 2026 hands-on IC design lab

== FILE CREATION & EDITING CAPABILITY ==
You can create, edit, and generate multiple HDL files directly from natural language.

CREATE a new file:
  "create a mux design and save it as mux.sv in a unit named mux"
  "generate a 4-bit adder and store it as adder.sv in unit adder"
  "write a D flip-flop to dff.v in the reg_lib project"

EDIT an existing file:
  "edit mux.sv in unit mux and add an async reset port"
  "modify counter.sv to change the reset to active-low"
  "fix the off-by-one bug in dff.sv in unit reg_lib"

GENERATE MULTIPLE FILES at once:
  "create RTL and testbench for a mux in unit mux"
  "generate full project for a counter in unit cnt"
  "create RTL and formal properties for arb in unit arb"

POST-CREATION HOOKS (append to any create/edit request):
  "create mux.sv in unit mux and then simulate"
  "generate counter.sv in unit cnt and lint"
  "create adder.sv in unit adder and synth"

Files are placed in the correct subdirectory automatically:
  RTL .sv → source/rtl/systemverilog/
  Testbench .sv (tb_* prefix) → source/tb/systemverilog/
  Formal .sva → formal/src/
  Synth .tcl → synthesis/scripts/
READ & EXPLAIN existing files:
  "explain adder.sv to me"
  "describe the ports in mux.sv"
  "what does counter.sv do?"
  "show me how dff.sv works"
  "summarize the design in arb.sv"

GENERATE DOCUMENTATION for a module:
  "document mux.sv" / "generate a spec for adder.sv"
  → Creates a Markdown port table, parameter list, and functional summary.
== YOUR ROLE ==
- Answer questions about RTL design, verification, EDA tools, and the SaxoFlow flow.
- When a user asks how to do something, give the exact SaxoFlow command first.
- When generating or reviewing HDL, follow Verilog/SystemVerilog best practices.
- For install issues, suggest 'saxoflow diagnose' to identify what is missing.
- Be concise and practical. Prefer SaxoFlow-specific answers over generic ones.\
"""

# ---------------------------------------------------------------------------
# Save-intent detection regexes (for file creation capability)
# ---------------------------------------------------------------------------

# Matches filenames with recognized HDL/script extensions
_FILENAME_RE = re.compile(
    r'\b([\w.-]+\.(?:sv|svh|v|vh|vhd|vhdl|sva|sby|tcl))\b',
    re.IGNORECASE,
)

# Matches "in (a) unit (named) X" or "in the X unit/project/folder"
_UNIT_RE = re.compile(
    r'(?:in\s+(?:a\s+)?(?:unit|project|folder)\s+(?:named\s+)?([\w.-]+)'
    r'|in\s+the\s+([\w.-]+)\s+(?:unit|project|folder))',
    re.IGNORECASE,
)

# Indicates a save/write/create-to-file intent
_SAVE_INTENT_RE = re.compile(
    r'\b(?:save|store|write|create|put|generate\s+and\s+save'  # noqa: ISC003
    r'|generate\s+and\s+store|generate\s+and\s+write)\b.{0,60}'
    r'\b(?:as|to|in|file)\b',
    re.IGNORECASE | re.DOTALL,
)

# Indicates an intent to edit/modify an existing file
_EDIT_INTENT_RE = re.compile(
    r'\b(?:edit|modify|update|fix|change|refactor|improve|extend'
    r'|add\s+(?:an?\s+)?(?:port|signal|reset|parameter|input|output|wire|reg)'
    r'|remove\s+\w+|rename\s+\w+)\b',
    re.IGNORECASE,
)

# Indicates a request for multiple files in one shot
_MULTI_FILE_RE = re.compile(
    r'\b(?:'
    r'full\s+(?:project|design|unit)'
    r'|(?:rtl|design|verilog)\s+and\s+(?:testbench|tb(?:\s+file)?)'
    r'|(?:testbench|tb(?:\s+file)?)\s+and\s+(?:rtl|design|verilog)'
    r'|generate\s+(?:both|all|multiple\s+files)'
    r'|create\s+(?:both|all|multiple\s+files)'
    r')\b',
    re.IGNORECASE,
)

# Extracts a design/module name from phrases like "for a mux" / "for the counter"
_MODULE_NAME_RE = re.compile(
    r'\bfor\s+(?:a\s+|an\s+|the\s+)?(\w+)',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Read-intent detection — "explain", "describe", "what does X do", etc.
# ---------------------------------------------------------------------------

_READ_INTENT_RE = re.compile(
    r'\b(?:explain|describe|summari[sz]e|what\s+does|show\s+me|read|tell\s+me\s+about'  # noqa: ISC003
    r'|how\s+does|walk\s+me\s+through)\b',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Documentation-export intent — "document X.sv", "generate spec for X.sv"
# ---------------------------------------------------------------------------

_DOC_INTENT_RE = re.compile(
    r'\b(?:document|generate\s+(?:a\s+)?(?:spec|docs?|documentation|port\s+table)'  # noqa: ISC003
    r'|create\s+(?:a\s+)?(?:spec|docs?|documentation)'  # noqa: ISC003
    r'|write\s+(?:a\s+)?(?:spec|documentation))',
    re.IGNORECASE,
)

# Detects post-creation hooks: "and then simulate", "and lint", "then synth", etc.
_POST_HOOK_RE = re.compile(
    r'\b(?:and|then)\s+(?:run\s+)?(?:simulate?|lint|check|verify|synth(?:esize)?|synthesis)\b'
    r'|\band\s+run\s+(?:sim(?:ulation)?|lint(?:ing)?|synthesis)\b',
    re.IGNORECASE,
)


def _detect_post_hook(message: str) -> Optional[str]:
    """Return a hook type ('sim', 'lint', 'synth') if the message requests it."""
    m = _POST_HOOK_RE.search(message)
    if not m:
        return None
    text = m.group(0).lower()
    if any(k in text for k in ('sim', 'simulate')):
        return 'sim'
    if any(k in text for k in ('lint', 'check', 'verify')):
        return 'lint'
    if any(k in text for k in ('synth', 'synthesis', 'synthesize')):
        return 'synth'
    return None


# Canonical mapping from user-visible keywords to internal actions.
# NOTE: Keep additions conservative to minimize false positives in detect_action().
ACTION_KEYWORDS: Dict[str, str] = {
    # Generation
    "generate rtl": "rtlgen",
    "rtlgen": "rtlgen",
    "generate testbench": "tbgen",
    "tbgen": "tbgen",
    "formal property": "fpropgen",
    "generate formal": "fpropgen",
    "sva": "fpropgen",
    # Simulation, Synthesis, etc.
    "simulate": "sim",
    "simulation": "sim",
    "synth": "synth",
    "synthesis": "synth",
    "debug": "debug",
    "report": "report",
    "pipeline": "fullpipeline",
    # Review
    "review rtl": "rtlreview",
    "check rtl": "rtlreview",
    "review testbench": "tbreview",
    "check testbench": "tbreview",
    "review formal": "fpropreview",
    "review property": "fpropreview",
    "check formal": "fpropreview",
    # NOTE: Add new keywords cautiously to avoid false positives in detect_action().
}

# -----------------------------------------------------------------------------
# (Unused but kept for future reference)
# A scored/regex-based detector could replace simple "contains" matching if
# false positives/negatives become an issue.
# from re import compile as re_compile
# ACTION_TOKEN_RE = re_compile(r"__ACTION:(?P<name>[a-z_]+)__")
# TODO(decide-future): switch to regex-based token detection when needed.
# -----------------------------------------------------------------------------


# =============================================================================
# Typed payloads (maintainability/readability; runtime behavior unchanged)
# =============================================================================

BuddyType = Literal["need_file", "review_result", "action", "chat", "error"]


class BuddyBase(TypedDict, total=False):
    """Common typed keys for buddy responses."""
    type: BuddyType
    message: str


class NeedFile(BuddyBase):
    type: Literal["need_file"]


class ReviewResult(BuddyBase):
    type: Literal["review_result"]
    action: str


class ActionTrigger(BuddyBase):
    type: Literal["action"]
    action: str


class ChatResult(BuddyBase):
    type: Literal["chat"]


class ErrorResult(BuddyBase):
    type: Literal["error"]


BuddyResult = Dict[str, Any]  # Keep runtime shape flexible for full compatibility.


# =============================================================================
# Custom Exceptions
# =============================================================================

class AskAIBuddyError(Exception):
    """Base exception for ask_ai_buddy orchestration errors."""


class AgentExecutionError(AskAIBuddyError):
    """Raised when an underlying agent fails to execute."""


class LLMInvocationError(AskAIBuddyError):
    """Raised when the selected LLM cannot be invoked or returns an invalid result."""


# =============================================================================
# Internal helpers (module-private)
# =============================================================================

def _safe_lower(s: Optional[str]) -> str:
    """Return a lowercased string, gracefully handling None."""
    return (s or "").lower()


def _format_chat_history(
    history: Iterable[Dict[str, str]],
    limit: int = MAX_HISTORY_TURNS,
) -> str:
    """Format recent conversation turns for inclusion in the prompt.

    Args:
        history: Iterable of turn dicts with keys 'user' and optional 'assistant'.
        limit: Max number of recent turns to include.

    Returns:
        str: Alternating 'User:' and 'Assistant:' lines for the prompt.
    """
    lines: List[str] = []
    recent = list(history)[-limit:] if history else []
    for turn in recent:
        # Defensive: missing keys default to empty strings.
        user_msg = turn.get("user", "")
        asst_msg = turn.get("assistant", "")
        lines.append(f"User: {user_msg}\nAssistant: {asst_msg}")
    return "\n".join(lines)


def _build_system_suffix(action: Optional[str]) -> str:
    """Build the instruction suffix guiding the model on how to respond.

    If an actionable design step is requested, instruct the model to emit the
    explicit action token after confirming prerequisites.
    """
    # NOTE: The "{action}" token is intentionally literal in the instruction text
    # so the model can replace it with the resolved action name at inference time.
    if action:
        return (
            "Assistant: (Your answer should be factual and cite sources or link resources "
            "if possible. If the user asks for a design action (like generate RTL), first "
            "guide them through prerequisites. After the user confirms they are ready, "
            "respond ONLY with the string '__ACTION:{action}__' to trigger the tool.)"
        )
    return (
        "Assistant: (Your answer should be factual and cite sources or link resources "
        "if possible.)"
    )


def _invoke_llm(
    agent_type: str,
    provider: Optional[str],
    model_name: Optional[str],
    prompt: str,
) -> str:
    """Invoke the selected LLM and return text content.

    Args:
        agent_type: Logical agent type for model selection (e.g., 'buddy').
        provider: Optional provider override.
        model_name: Optional model name override.
        prompt: Full prompt to send.

    Returns:
        str: Model response text.

    Raises:
        LLMInvocationError: If model selection or invocation fails, or content is empty.
    """
    try:
        llm = ModelSelector.get_model(
            agent_type=agent_type,
            provider=provider,
            model_name=model_name,
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMInvocationError(f"Model selection failed: {exc}") from exc

    try:
        response = llm.invoke(prompt)
    except Exception as exc:  # noqa: BLE001
        raise LLMInvocationError(f"Model invocation failed: {exc}") from exc

    # Handle common SDK patterns (attribute or plain string)
    text = getattr(response, "content", None) or str(response)
    if not isinstance(text, str) or not text.strip():
        raise LLMInvocationError("Empty or invalid LLM response content.")
    return text


def _run_review_agent(action: str, file_to_review: str) -> str:
    """Execute a review agent for the given action.

    Args:
        action: One of {'rtlreview', 'tbreview', 'fpropreview'}.
        file_to_review: File path or code text to review.

    Returns:
        str: Review output string.

    Raises:
        AgentExecutionError: If the agent cannot be fetched or run.
    """
    try:
        review_agent = AgentManager.get_agent(action)
    except Exception as exc:  # noqa: BLE001
        raise AgentExecutionError(
            f"Failed to get review agent for '{action}': {exc}"
        ) from exc

    try:
        result = review_agent.run(file_to_review)
    except Exception as exc:  # noqa: BLE001
        raise AgentExecutionError(
            f"Review agent run failed for '{action}': {exc}"
        ) from exc

    # Normalize to string if agent returns a non-string payload.
    if not isinstance(result, str):
        # TODO(decide-future): Normalize structured payloads if agents
        # start returning dicts or richer objects.
        result = str(result)
    return result


# =============================================================================
# Public API
# =============================================================================

def detect_read_intent(message: str) -> Optional[Dict[str, str]]:
    """Detect a request to read/explain an existing HDL file.

    Parameters
    ----------
    message:
        Raw user input.

    Returns
    -------
    dict | None
        ``{"filename": str, "question": str}``
        or None if no read intent is detected.

    Notes
    -----
    - Requires BOTH a read-intent keyword AND an HDL filename.
    - Does NOT require a unit name — ``find_file_in_unit`` searches broadly.
    """
    if not message or not _READ_INTENT_RE.search(message):
        return None

    fn_match = _FILENAME_RE.search(message)
    if not fn_match:
        return None

    filename = fn_match.group(1)
    return {
        "filename": filename,
        "question": message,
    }


def project_context(cwd: Optional[str] = None) -> str:
    """Return a compact description of the current SaxoFlow project state.

    Scans *cwd* (defaults to ``os.getcwd()``) for:
    - A unit project root marker (``saxoflow.toml``, ``unit.yaml``)
    - RTL files in ``source/rtl/`` subtree
    - Testbench files in ``source/tb/`` subtree
    - Formal files in ``formal/src/``
    - Constraint files in ``constraints/``

    The result is a short string suitable for prepending to any LLM prompt
    so the model has an accurate picture of what is on disk.

    Returns
    -------
    str
        Empty string if the directory contains no recognisable SaxoFlow project
        structure, so callers can safely concatenate without adding noise.
    """
    root = Path(cwd or os.getcwd())
    lines: List[str] = []

    # Check for unit project marker
    has_marker = (
        (root / "saxoflow.toml").exists()
        or (root / "unit.yaml").exists()
        or (root / ".saxoflow").is_dir()
    )
    if has_marker:
        lines.append(f"[Project root: {root.name}]")

    # Scan known subdirectories for HDL files
    _scan_dirs = [
        ("source/rtl", "RTL"),
        ("source/tb", "Testbench"),
        ("formal/src", "Formal"),
        ("constraints", "Constraints"),
    ]
    _hdl_exts = {".sv", ".svh", ".v", ".vh", ".vhd", ".vhdl", ".sva", ".sby", ".tcl"}

    found_any = False
    for subdir, label in _scan_dirs:
        scan_path = root / subdir
        if not scan_path.is_dir():
            continue
        files = [
            f.name for f in sorted(scan_path.rglob("*"))
            if f.is_file() and f.suffix.lower() in _hdl_exts
        ]
        if files:
            found_any = True
            lines.append(f"[{label} files: {', '.join(files)}]")

    # If no unit structure found, try a flat scan of *.sv/.v in cwd
    if not found_any:
        flat = [
            f.name for f in sorted(root.iterdir())
            if f.is_file() and f.suffix.lower() in _hdl_exts
        ]
        if flat:
            lines.append(f"[HDL files in working directory: {', '.join(flat)}]")

    if not lines:
        return ""

    return "== CURRENT PROJECT CONTEXT ==\n" + "\n".join(lines) + "\n"


def detect_save_intent(message: str) -> Optional[Dict[str, str]]:
    """Detect a save-to-file intent and extract key fields.

    Parameters
    ----------
    message:
        Raw user input.

    Returns
    -------
    dict | None
        ``{"spec": str, "filename": str, "unit": str, "content_type": str}``
        or None if no save intent is detected.

    Notes
    -----
    - Must find both a save-intent trigger AND an HDL filename to match.
    - Unit name is optional; if absent, the file is written to cwd.
    """
    lowered = message  # keep original case for spec; lowered only for matching

    if not _SAVE_INTENT_RE.search(lowered) and not _DOC_INTENT_RE.search(lowered):
        return None

    fn_match = _FILENAME_RE.search(lowered)
    if not fn_match:
        return None

    filename = fn_match.group(1)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Derive content type from extension and filename
    _ext_map = {
        "sv": "rtl", "svh": "rtl", "v": "rtl", "vh": "rtl",
        "vhd": "rtl", "vhdl": "rtl",
        "sva": "formal", "sby": "formal",
        "tcl": "synth",
    }
    content_type = _ext_map.get(ext, "rtl")
    # Testbench override: filename stem starts/ends with 'tb', or message says 'testbench'
    if content_type == "rtl":
        stem = filename.rsplit(".", 1)[0].lower() if "." in filename else filename.lower()
        if (
            re.search(r'(?:^tb[_\-]|[_\-]tb$|^tb$|testbench)', stem)
            or re.search(r'\btestbench\b', message, re.IGNORECASE)
        ):
            content_type = "tb"

    unit_match = _UNIT_RE.search(lowered)
    unit_name = ""
    if unit_match:
        unit_name = (unit_match.group(1) or unit_match.group(2) or "").strip()

    return {
        "spec": message,
        "filename": filename,
        "unit": unit_name,
        "content_type": content_type,
        "post_hook": _detect_post_hook(message),
        "doc_export": bool(_DOC_INTENT_RE.search(message)),
    }


def detect_edit_intent(message: str) -> Optional[Dict[str, str]]:
    """Detect intent to edit an existing HDL file.

    Parameters
    ----------
    message:
        Raw user input.

    Returns
    -------
    dict | None
        ``{"spec", "filename", "unit", "edit_request", "content_type", "post_hook"}``
        or None if no edit intent is detected.

    Notes
    -----
    - Must find an edit-intent keyword AND an HDL filename.
    - File must already exist; the caller (handle_edit_file) enforces this.
    """
    if not _EDIT_INTENT_RE.search(message):
        return None

    fn_match = _FILENAME_RE.search(message)
    if not fn_match:
        return None

    filename = fn_match.group(1)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    _ext_map = {
        "sv": "rtl", "svh": "rtl", "v": "rtl", "vh": "rtl",
        "vhd": "rtl", "vhdl": "rtl",
        "sva": "formal", "sby": "formal",
        "tcl": "synth",
    }
    content_type = _ext_map.get(ext, "rtl")
    stem = filename.rsplit(".", 1)[0].lower() if "." in filename else filename.lower()
    if content_type == "rtl" and (
        re.search(r'(?:^tb[_\-]|[_\-]tb$|^tb$|testbench)', stem)
        or re.search(r'\btestbench\b', message, re.IGNORECASE)
    ):
        content_type = "tb"

    unit_match = _UNIT_RE.search(message)
    unit_name = ""
    if unit_match:
        unit_name = (unit_match.group(1) or unit_match.group(2) or "").strip()

    return {
        "spec": message,
        "filename": filename,
        "unit": unit_name,
        "edit_request": message,
        "content_type": content_type,
        "post_hook": _detect_post_hook(message),
    }


def detect_multi_file_intent(message: str) -> Optional[Dict[str, Any]]:
    """Detect a request to generate multiple related HDL files in one shot.

    Parameters
    ----------
    message:
        Raw user input.

    Returns
    -------
    dict | None
        ``{"spec", "unit", "design_name", "files": [{"filename", "content_type"},...],
           "post_hook"}``
        or None if no multi-file intent is detected.
    """
    if not _MULTI_FILE_RE.search(message):
        return None

    lower = message.lower()
    want_rtl = True  # always
    want_tb = bool(re.search(r'\b(?:testbench|tb(?:\s+file)?|tb[_\-])\b', lower))
    want_formal = bool(re.search(r'\bformal\b', lower)) or 'full' in lower

    # Ensure at least two file types
    if not (want_tb or want_formal):
        return None

    unit_match = _UNIT_RE.search(message)
    unit_name = ""
    if unit_match:
        unit_name = (unit_match.group(1) or unit_match.group(2) or "").strip()

    # Extract design/module name
    mod_match = _MODULE_NAME_RE.search(message)
    design_name = mod_match.group(1).lower() if mod_match else (unit_name or "design")

    files: List[Dict[str, str]] = []
    if want_rtl:
        files.append({"filename": f"{design_name}.sv", "content_type": "rtl"})
    if want_tb:
        files.append({"filename": f"tb_{design_name}.sv", "content_type": "tb"})
    if want_formal:
        files.append({"filename": f"{design_name}.sva", "content_type": "formal"})

    return {
        "spec": message,
        "unit": unit_name,
        "design_name": design_name,
        "files": files,
        "post_hook": _detect_post_hook(message),
    }


def detect_action(message: str) -> Tuple[Optional[str], Optional[str]]:
    """Detect an actionable keyword in the user message.

    Args:
        message: Arbitrary user input.

    Returns:
        Tuple[Optional[str], Optional[str]]: (action, matched_keyword).
        If nothing detected, returns (None, None).

    Notes:
        - The first matching keyword wins (simple contains-matching).
        - Consider moving to a scored matcher if false positives become an issue.
    """
    lowered = _safe_lower(message)
    for key, action in ACTION_KEYWORDS.items():
        if key in lowered:
            return action, key
    return None, None


def generate_explanation_for_file(
    filename: str,
    code: str,
    question: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Ask the LLM to explain or describe an existing HDL file.

    Parameters
    ----------
    filename:
        Name of the file (used for context only).
    code:
        Full source code of the file.
    question:
        The original user question (e.g. "explain mux.sv").
    provider / model:
        Optional LLM overrides.

    Returns
    -------
    str
        A human-readable explanation (Markdown formatting acceptable).
    """
    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"The user has asked: {question}\n\n"
        f"Here is the contents of `{filename}`:\n```\n{code}\n```\n\n"
        f"Please provide a clear, concise technical explanation suitable for "
        f"a student learning IC design. Cover: overall function, port/signal "
        f"descriptions, key design decisions, and anything noteworthy about "
        f"the implementation. Use Markdown formatting."
    )
    try:
        return _invoke_llm(
            agent_type="buddy",
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError as exc:
        raise RuntimeError(f"LLM error during file explanation: {exc}") from exc


def generate_code_for_save(
    spec: str,
    content_type: str = "rtl",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Generate HDL code from a natural-language spec, returning only the code.

    Called by ``cool_cli.file_ops`` after save-intent detection.

    Parameters
    ----------
    spec:
        The full user request, used as the generation prompt.
    content_type:
        One of ``"rtl"``, ``"tb"``, ``"formal"``, ``"synth"``.
    provider / model:
        Optional LLM overrides.

    Returns
    -------
    str
        The generated code artifact (code-block stripped if present).
    """
    # Documentation export: when the user asks to 'document' a file, generate
    # a Markdown spec rather than HDL code.
    if content_type == "document":
        prompt = (
            f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
            f"User request: {spec}\n\n"
            f"Generate a Markdown design specification document for the module. "
            f"Include sections: Overview, Port Table (Name/Direction/Width/Description), "
            f"Parameters, Internal Signals (if notable), Functional Description, "
            f"and Known Limitations. Be concise and precise."
        )
        try:
            return _invoke_llm(
                agent_type="buddy",
                provider=provider,
                model_name=model,
                prompt=prompt,
            )
        except LLMInvocationError as exc:
            raise RuntimeError(f"LLM error during documentation generation: {exc}") from exc

    _lang_hint = {
        "rtl": "SystemVerilog/Verilog",
        "tb": "SystemVerilog/Verilog testbench",
        "formal": "SystemVerilog Assertions (SVA)",
        "synth": "Yosys TCL synthesis script",
    }.get(content_type, "HDL")

    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"User request: {spec}\n\n"
        f"Generate ONLY the {_lang_hint} code. "
        f"Output only the code block, no explanation, no markdown prose. "
        f"Wrap the code in a single ```{_lang_hint.split('/')[0].lower()} ... ``` block."
    )
    try:
        return _invoke_llm(
            agent_type="buddy",
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError as exc:
        raise RuntimeError(f"LLM error during code generation: {exc}") from exc


def generate_patch_for_edit(
    original_code: str,
    edit_request: str,
    content_type: str = "rtl",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Generate a patched version of an existing HDL file based on an edit request.

    Parameters
    ----------
    original_code:
        The full current content of the file to be edited.
    edit_request:
        The natural-language edit instruction (e.g. "add an async reset port").
    content_type:
        One of ``"rtl"``, ``"tb"``, ``"formal"``, ``"synth"``.
    provider / model:
        Optional LLM overrides.

    Returns
    -------
    str
        The complete updated code (code-block strips handled by caller).
    """
    _lang_hint = {
        "rtl": "SystemVerilog/Verilog",
        "tb": "SystemVerilog/Verilog testbench",
        "formal": "SystemVerilog Assertions (SVA)",
        "synth": "Yosys TCL synthesis script",
    }.get(content_type, "HDL")

    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"Existing {_lang_hint} code:\n```\n{original_code}\n```\n\n"
        f"Edit request: {edit_request}\n\n"
        f"Apply the requested changes and return ONLY the complete updated {_lang_hint} code. "
        f"Do not truncate or omit any part of the file. "
        f"Output only the code block, no explanation, no prose. "
        f"Wrap the code in a single ```{_lang_hint.split('/')[0].lower()} ... ``` block."
    )
    try:
        return _invoke_llm(
            agent_type="buddy",
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError as exc:
        raise RuntimeError(f"LLM error during code editing: {exc}") from exc


def ask_ai_buddy(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    agent_type: str = "buddy",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    file_to_review: Optional[str] = None,
    context: Optional[str] = None,
) -> BuddyResult:
    """Main entry point for AI buddy interactions.

    Behaviors (preserved):
        - If the message implies a *review* action and `file_to_review` is provided,
          it runs the associated review agent and returns a 'review_result'.
        - If the message implies a *review* action but no file is provided,
          it returns 'need_file' with instructions.
        - Otherwise, it chats with the selected LLM. If the LLM returns the
          '__ACTION:<name>__' token, it returns a typed 'action' response.

    Args:
        message: User input string.
        history: Optional recent conversation turns to provide context. Each item
            should be a dict with keys 'user' and optional 'assistant'.
        agent_type: Logical agent type for model selection.
        provider: Optional provider override.
        model: Optional model name override.
        file_to_review: Code content or path required for review actions.
        context: Optional extra context string (e.g. project_context() output or
            teach session state) prepended to the system prompt.

    Returns:
        dict: One of:
            {"type": "need_file", "message": <str>}
            {"type": "review_result", "action": <str>, "message": <str>}
            {"type": "action", "action": <str>, "message": <str>}
            {"type": "chat", "message": <str>}
            {"type": "error", "message": <str>}  # on handled exceptions

    Notes:
        - Python 3.9+ compatible (no structural pattern matching).
        - Exceptions are caught and converted to a stable error payload so callers
          don't crash the shell/CLI.
    """
    # Normalise None / falsy input to empty string so all detectors stay safe.
    message = message or ""

    # -------------------------------------------------------------------------
    # Read-file path (checked first: most specific, no generation needed)
    # -------------------------------------------------------------------------
    read_intent = detect_read_intent(message)
    if read_intent is not None:
        return {"type": "read_file", **read_intent}  # type: ignore[return-value]

    # -------------------------------------------------------------------------
    # Multi-file path (checked next: most specific generation request)
    # -------------------------------------------------------------------------
    multi_intent = detect_multi_file_intent(message)
    if multi_intent is not None:
        return {"type": "multi_file", **multi_intent}  # type: ignore[return-value]

    # -------------------------------------------------------------------------
    # Edit-file path
    # -------------------------------------------------------------------------
    edit_intent = detect_edit_intent(message)
    if edit_intent is not None:
        return {"type": "edit_file", **edit_intent}  # type: ignore[return-value]

    # -------------------------------------------------------------------------
    # Save-to-file path (includes doc_export flag for "document X.sv" requests)
    # -------------------------------------------------------------------------
    save_intent = detect_save_intent(message)
    if save_intent is not None:
        if save_intent.get("doc_export"):
            save_intent["content_type"] = "document"
        return {"type": "save_file", **save_intent}  # type: ignore[return-value]

    action, matched_keyword = detect_action(message)

    # -------------------------------------------------------------------------
    # Review path (direct)
    # -------------------------------------------------------------------------
    if action in {"rtlreview", "tbreview", "fpropreview"}:
        if not file_to_review:
            return {
                "type": "need_file",
                "message": (
                    f"Please provide the code/file to review for '{matched_keyword}'. "
                    "Paste the code or specify the path (e.g., 'review rtl mydesign.v')."
                ),
            }

        try:
            review_output = _run_review_agent(action, file_to_review)
        except AgentExecutionError as exc:
            return {"type": "error", "message": str(exc)}
        return {"type": "review_result", "action": action, "message": review_output}

    # -------------------------------------------------------------------------
    # Chat / Action token path
    # -------------------------------------------------------------------------
    # Build prompt: identity context + optional project context + history + user message.
    history_text = _format_chat_history(history or [])
    suffix = _build_system_suffix(action)
    prompt_parts: List[str] = [SAXOFLOW_SYSTEM_CONTEXT]
    if context:
        prompt_parts.append(context)
    if history_text:
        prompt_parts.append(history_text)
    prompt_parts.append(f"User: {message}")
    prompt_parts.append(suffix)
    prompt = "\n\n".join(prompt_parts)

    try:
        text = _invoke_llm(
            agent_type=agent_type,
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError as exc:
        return {"type": "error", "message": str(exc)}

    # Preserve original behavior: detect explicit action token via simple contains.
    if action and f"__ACTION:{action}__" in text:
        return {"type": "action", "action": action, "message": text}

    # Default: normal chat.
    return {"type": "chat", "message": text}


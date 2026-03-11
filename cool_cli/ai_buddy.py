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

# ---------------------------------------------------------------------------
# Lazy imports for specialist agent backends.
# Both objects are wrapped in a try/except so the shell stays fully functional
# even when saxoflow_agenticai is partially broken or unavailable.
# _AGENTS_AVAILABLE is the single flag every routing branch checks.
# ---------------------------------------------------------------------------
try:
    from saxoflow_agenticai.core.agent_manager import AgentManager as _AgentManager
    from saxoflow_agenticai.orchestrator.feedback_coordinator import (
        AgentFeedbackCoordinator as _AgentFeedbackCoordinator,
    )
    _AGENTS_AVAILABLE: bool = True
except Exception:  # noqa: BLE001
    _AgentManager = None  # type: ignore[assignment]
    _AgentFeedbackCoordinator = None  # type: ignore[assignment]
    _AGENTS_AVAILABLE = False

# Keep the bare name available for the rest of the module (model selection etc.)
try:
    from saxoflow_agenticai.core.agent_manager import AgentManager
except Exception:  # noqa: BLE001
    AgentManager = None  # type: ignore[assignment]

__all__ = [
    "MAX_HISTORY_TURNS",
    "ACTION_KEYWORDS",
    "detect_action",
    "detect_save_intent",
    "detect_edit_intent",
    "detect_multi_file_intent",
    "detect_read_intent",
    "detect_companion_files",
    "detect_incomplete_request",
    "plan_clarification",
    "build_enriched_spec",
    "generate_code_for_save",
    "generate_companion_file",
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

# Matches "in (a) unit (named) X", "in the X unit/project/folder",
# or "in X unit/project/folder" (without "the")
_UNIT_RE = re.compile(
    r'(?:in\s+(?:a\s+)?(?:unit|project|folder)\s+(?:named\s+)?([\w.-]+)'
    r'|in\s+(?:the\s+)?([\w.-]+)\s+(?:unit|project|folder))',
    re.IGNORECASE,
)

# Indicates a save/write/create-to-file intent
_SAVE_INTENT_RE = re.compile(
    r'\b(?:save|store|write|create|put|place|deploy|add|generate\s+and\s+save'  # noqa: ISC003
    r'|generate\s+and\s+store|generate\s+and\s+write)\b.{0,80}'
    r'\b(?:as|to|in|file|unit|project|folder)\b',
    re.IGNORECASE | re.DOTALL,
)

# Extracts a design/module name from the natural-language part of a prompt.
# Captures multi-word names like "half adder" → "half_adder", "alu" → "alu".
# Stops before connector/structural words so "alu design and place" → "alu".
_DESIGN_NAME_RE = re.compile(
    r'\b(?:create|generate|make|build|design|write)\b'
    r'\s+(?:an?\s+)?'
    r'((?!(?:design|module|circuit|block|unit|rtl|core|component|and|in|to|for|the|a|an)\b)'
    r'[a-z][a-z0-9]*'
    r'(?:\s+(?!(?:design|module|circuit|block|unit|rtl|core|component|and|in|to|for|the)\b)'
    r'[a-z][a-z0-9]*){0,2})',
    re.IGNORECASE,
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

# Broad creation-intent trigger — fires even on bare "create an alu design"
# without requiring a filename or unit name.
_CREATION_INTENT_RE = re.compile(
    r'\b(?:create|generate|make|build|design|write|code)\b'
    r'.{0,60}'
    r'\b(?:'
    # RTL design types
    r'design|module|circuit|block|core|component|counter|adder|mux|alu|fifo'
    r'|arbiter|fsm|flip.?flop|register|shifter|decoder|encoder|unit|rtl'
    # Verification / testbench types
    r'|testbench|tb|assertions?|sva|property|covergroup|coverpoint|coverage'
    r'|uvm|uvc|agent|driver|monitor|scoreboard|sequencer|sequences?'
    r'|checker|interface|cocotb|stimulus'
    # Synthesis & netlist
    r'|synthesis|synth|netlist|yosys'
    # Timing & constraints
    r'|constraints?|sdc|timing|sta|opensta'
    # Physical design (floorplan, P&R, power grid)
    r'|floorplan|placement|routing|pnr|pdn'
    # Power analysis
    r'|power'
    # Physical verification
    r'|drc|lvs|erc'
    # Layout & GDS
    r'|layout|gds|klayout'
    # Flow / tool scripts
    r'|makefile|openroad'
    r')\b',
    re.IGNORECASE | re.DOTALL,
)

# Detects explicit HDL language in the message
_HDL_LANG_RE = re.compile(
    r'\b(?:systemverilog|system\s+verilog|verilog|vhdl|sv\b)',
    re.IGNORECASE,
)


def detect_incomplete_request(
    message: str,
    prefs: Optional[Dict[str, str]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Detect a creation request that is too vague to act on directly.

    When the user writes something like ``"create an alu design"`` without
    specifying which HDL to use or where to put the file, this function
    returns a list of clarifying questions so the shell can interactively
    fill in the gaps before calling the LLM.

    Parameters
    ----------
    message:
        Raw user input.
    prefs:
        Current user preferences (from ``load_prefs()``). Used to skip
        questions whose answers are already set.

    Returns
    -------
    list[dict] | None
        ``None`` if the request is already complete (has both a filename/
        extension AND a unit name, or is explicitly phrased).
        Otherwise a list of question dicts::

            [
              {
                "key": "hdl",
                "question": "Which HDL language should I use?",
                "choices": ["SystemVerilog", "Verilog", "VHDL"],
                "default": "SystemVerilog",
              },
              ...
            ]

    Notes
    -----
    - Only triggers for **creation** requests (not edits, reviews, or chat).
    - Does NOT trigger when both a filename (.sv/.v) AND a unit name are
      already present — the request is specific enough to act on.
    - Skips HDL question if the user already has an ``hdl`` preference.
    """
    if not message:
        return None

    # Must be a creation-style request
    if not _CREATION_INTENT_RE.search(message):
        return None

    # If this looks like an edit, read, or doc request — don't intercept
    if _EDIT_INTENT_RE.search(message) or _READ_INTENT_RE.search(message):
        return None

    # Check what's already present in the message
    has_filename = bool(_FILENAME_RE.search(message))
    has_unit = bool(_UNIT_RE.search(message))
    has_hdl = bool(_HDL_LANG_RE.search(message))

    # If the message already fully specifies what we need, don't interrupt
    if has_filename and has_unit:
        return None

    # --- Build question list ---
    questions: List[Dict[str, Any]] = []
    prefs = prefs or {}

    # Q1: HDL language (skip if already in prefs or in message)
    pref_hdl = prefs.get("hdl", "")
    if not has_hdl and not pref_hdl:
        hdl_choices = ["SystemVerilog", "Verilog", "VHDL"]
        questions.append({
            "key": "hdl",
            "question": "Which HDL language should I write this in?",
            "choices": hdl_choices,
            "default": "SystemVerilog",
        })

    # Q2: Create unit project structure? (default: yes — keeps everything tidy)
    if not has_unit:
        # Derive a candidate folder name from the design name in the message
        candidate_unit = ""
        dm = _DESIGN_NAME_RE.search(message)
        if dm:
            raw = dm.group(1).strip()
            candidate_unit = re.sub(r'\s+', '_', raw).lower().rstrip('_')
        questions.append({
            "key": "create_unit",
            "question": "Create a unit project folder for this design?",
            "choices": ["yes", "no"],
            "default": "yes",
            "hint": (
                f"Suggested folder name: '{candidate_unit or 'my_design'}'. "
                "A unit folder keeps RTL, TB, and Makefiles in one place."
            ),
            "_candidate_unit": candidate_unit or "my_design",
        })

    # Q3: Extra requirements / spec details (only if no filename was given,
    #     meaning this is a bare 'create X' with no further spec)
    if not has_filename:
        questions.append({
            "key": "requirements",
            "question": "Any specific requirements?",
            "choices": [],
            "default": "",
            "hint": "e.g. 32-bit, synchronous reset, 4 operations. Press Enter to skip.",
        })

    # If nothing to ask (all info already present), return None
    return questions if questions else None


# ---------------------------------------------------------------------------
# AI-driven clarification planning & spec synthesis
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
_BARE_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)  # greedy: outermost object


def _extract_json(text: str) -> Optional[dict]:
    """Try to extract the first JSON object from *text*.
    Favours a fenced ```json block, then tries bare-object extraction.
    Returns None if nothing parseable is found.
    """
    import json  # noqa: PLC0415

    # Fenced code block — capture group 1 holds the JSON body
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except (ValueError, KeyError):
            pass

    # Bare JSON object — whole match is the JSON
    m2 = _BARE_JSON_RE.search(text)
    if m2:
        try:
            return json.loads(m2.group(0))
        except (ValueError, KeyError):
            pass

    # Last-ditch: try the whole string
    try:
        return json.loads(text.strip())
    except (ValueError, KeyError):
        return None


def plan_clarification(
    message: str,
    context: str = "",
    prefs: Optional[Dict[str, str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Ask the LLM whether the request needs clarification and what to ask.

    The LLM analyses the user's request in the context of the current project
    and returns a JSON object describing the questions it wants to ask.  Unlike
    ``detect_incomplete_request()``, this function is *not* hardcoded: the model
    decides what is missing based on the actual request.

    Parameters
    ----------
    message:
        Raw user creation request (e.g. ``"create an alu design"``).
    context:
        Current project context string (from ``project_context()``).
    prefs:
        User preferences dict (from ``load_prefs()``) — included in the prompt
        so the model skips things the user already set.
    provider / model:
        Optional LLM overrides.

    Returns
    -------
    list[dict] | None
        A list of question dicts if clarification is needed, each with::

            {
              "key":      str,           # machine-readable identifier
              "question": str,           # the question to display
              "choices":  list[str],     # [] if free text expected
              "default":  str,           # suggested default (may be "")
            }

        Returns ``None`` when:
        - the model says no clarification is needed;
        - the LLM call fails for any reason (fail-open so the shell never blocks).

    Notes
    -----
    - Falls back silently to ``None`` on any exception so the caller can
      always proceed without clarification rather than crashing.
    - Only should be called after ``detect_incomplete_request`` confirms the
      request *looks* like a vague creation intent (to avoid API calls on
      every message).
    """
    prefs = prefs or {}

    # Fast pre-filters — skip the LLM call entirely when:
    # (a) not a creation intent at all
    if not _CREATION_INTENT_RE.search(message):
        return None
    # (b) clearly an edit or read, not a create
    if _EDIT_INTENT_RE.search(message) or _READ_INTENT_RE.search(message):
        return None
    # (c) already fully specified (filename + unit present) — nothing to clarify
    if _FILENAME_RE.search(message) and _UNIT_RE.search(message):
        return None

    prefs_summary = (
        ", ".join(f"{k}={v}" for k, v in prefs.items())
        if prefs else "none set"
    )

    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"== TASK: CLARIFICATION PLANNING ==\n"
        f"The user typed: {message!r}\n"
        f"Current project context:\n{context or '(no project detected)'}\n"
        f"User preferences already set: {prefs_summary}\n\n"
        f"Your job is to decide whether this request has enough information "
        f"to act on, or whether you need to ask some quick clarifying questions first.\n\n"
        f"Rules:\n"
        f"- If the request already specifies HDL language, target filename, and "
        f"  unit/folder name, output: {{\"needs_clarification\": false, \"questions\": []}}\n"
        f"- If the request is vague, design questions that are SHORT (under 10 words), "
        f"  specific to THIS exact request. For example:\n"
        f"  * RTL: ALU → operations + data width; FIFO → depth + width + sync/async; "
        f"    FSM → states + encoding style; counter → direction + modulus\n"
        f"  * Testbench: ask about DUT, test scenarios, UVM vs basic, directed vs random\n"
        f"  * SVA/assertions: ask about which properties to check, bind vs inline, "
        f"    clocking block\n"
        f"  * UVM component: ask about UVM phase, parent agent, active/passive\n"
        f"  * Coverage: ask about coverpoints, bins, cross coverage needed\n"
        f"  * Synthesis (Yosys/synth script): ask about target PDK/library, optimisation goal\n"
        f"  * Timing constraints (SDC): ask about clock name, frequency, I/O delays\n"
        f"  * Floorplan: ask about die area, aspect ratio, utilisation target\n"
        f"  * P&R (placement/routing): ask about tool (OpenROAD/Magic), target density\n"
        f"  * PDN/power grid: ask about supply rails, ring vs mesh topology\n"
        f"  * STA (OpenSTA): ask about corners, path groups, report type\n"
        f"  * DRC/LVS: ask about PDK rule deck, tool (Magic/KLayout), layer stack\n"
        f"  * GDS/layout: ask about PDK, top cell name, merge strategy\n"
        f"  * Makefile/OpenROAD flow: ask about flow stages, target PDK\n"
        f"- For ANY RTL or testbench generation request, ALWAYS include a 'create_unit' "
        f"  question: 'Create a unit project folder for this design?' with "
        f"  choices ['yes', 'no'] and default 'yes'. This keeps RTL, TB, and Makefiles "
        f"  organised in one place.\n"
        f"- Max 3 questions.  Skip anything already covered by user preferences.\n"
        f"- For questions with a small fixed set of valid answers, populate 'choices'.\n"
        f"- Always propose a sensible 'default' so the user can just press Enter.\n\n"
        f"Respond ONLY with a JSON object — no prose, no markdown:\n"
        f"{{\n"
        f"  \"needs_clarification\": true,\n"
        f"  \"questions\": [\n"
        f"    {{\n"
        f"      \"key\": \"hdl\",\n"
        f"      \"question\": \"Which HDL language should I use?\",\n"
        f"      \"choices\": [\"SystemVerilog\", \"Verilog\", \"VHDL\"],\n"
        f"      \"default\": \"SystemVerilog\"\n"
        f"    }}\n"
        f"  ]\n"
        f"}}\n"
    )

    try:
        raw = _invoke_llm(
            agent_type="buddy",
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError:
        return None  # fail-open: proceed without clarification

    parsed = _extract_json(raw)
    if not parsed:
        return None

    if not parsed.get("needs_clarification", False):
        return None

    questions = parsed.get("questions", [])
    if not isinstance(questions, list) or not questions:
        return None

    # Normalise each question dict to ensure required keys are present
    normalised: List[Dict[str, Any]] = []
    for q in questions:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        normalised.append({
            "key":      str(q.get("key", f"q{len(normalised)+1}")),
            "question": str(q["question"]),
            "choices":  [str(c) for c in q.get("choices", [])],
            "default":  str(q.get("default", "")),
        })

    return normalised if normalised else None


def build_enriched_spec(
    original: str,
    answers: Dict[str, str],
    context: str = "",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Synthesise a complete, actionable spec from the original request + Q&A answers.

    After the user answers the clarifying questions, this function calls the
    LLM to combine the original intent with the answers into a single explicit
    natural-language instruction that the existing intent-detection pipeline
    (``detect_save_intent``, ``detect_multi_file_intent``, etc.) can parse
    and act on.

    Parameters
    ----------
    original:
        The user's original message.
    answers:
        Mapping of question ``key`` → user answer string.
    context:
        Current project context string.
    provider / model:
        Optional LLM overrides.

    Returns
    -------
    str
        A complete spec string such as::

            "create a 32-bit ALU with add/sub/and/or/xor operations written in "
            "SystemVerilog, save as alu.sv in unit myalu"

        Falls back to a mechanical concatenation of original + answers if the
        LLM call fails.
    """
    if not answers:
        return original

    qa_lines = "\n".join(
        f"  {key}: {value}" for key, value in answers.items() if value
    )

    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"== TASK: SPEC SYNTHESIS ==\n"
        f"Original user request: {original!r}\n"
        f"User's answers to clarifying questions:\n{qa_lines}\n"
        f"Current project context:\n{context or '(no project detected)'}\n\n"
        f"Rewrite the original request as a single, complete, explicit instruction "
        f"that includes all the details from the answers.  The instruction must:\n"
        f"- Say 'save as <filename>.<ext>' (derive the extension from the HDL answer)\n"
        f"- If 'create_unit' is 'yes' OR a unit/folder name was given, derive an "
        f"  appropriate short folder name from the design name and say 'in unit <name>'. "
        f"  For example, for an ALU design say 'in unit alu'; for a UART say 'in unit uart'.\n"
        f"- If 'create_unit' is 'no', do NOT include 'in unit'.\n"
        f"- Include any functional requirements from the answers\n"
        f"- Be a single natural-language sentence, no markdown, no bullet points.\n\n"
        f"Output ONLY the enriched instruction, nothing else."
    )

    try:
        result = _invoke_llm(
            agent_type="buddy",
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
        return result.strip().strip('"').strip("'")
    except LLMInvocationError:
        # Mechanical fallback: reconstruct a proper instruction so that
        # detect_save_intent can still parse the unit name correctly.
        hdl = answers.get("hdl", "")
        requirements = answers.get("requirements", "")
        create_unit_val = answers.get("create_unit", "").lower()
        unit_name_val = answers.get("unit_name", "")

        # Derive filename from original message
        from cool_cli.ai_buddy import _DESIGN_NAME_RE  # already imported at module level  # noqa: PLC0415,F811
        dm = _DESIGN_NAME_RE.search(original)
        if dm:
            import re as _re  # noqa: PLC0415
            raw = dm.group(1).strip()
            stem = _re.sub(r'\s+', '_', raw).lower().rstrip('_')
        else:
            stem = "design"
        ext = {"systemverilog": "sv", "verilog": "v", "vhdl": "vhd"}.get(
            hdl.lower(), "sv"
        )
        filename_clause = f"save as {stem}.{ext}"

        unit_clause = ""
        if create_unit_val == "yes" and unit_name_val:
            unit_clause = f" in unit {unit_name_val}"
        elif create_unit_val == "yes" and stem:
            unit_clause = f" in unit {stem}"

        req_clause = f". Requirements: {requirements}" if requirements else ""
        return (
            f"{original.rstrip('.')}, written in {hdl or 'SystemVerilog'}, "
            f"{filename_clause}{unit_clause}{req_clause}."
        )


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
    - A unit project root marker (``saxoflow.toml``, ``unit.yaml``, ``.saxoflow``)
    - RTL files in ``source/rtl/`` subtree
    - Testbench files in ``source/tb/`` subtree
    - Formal files in ``formal/src/``
    - Constraint files in ``constraints/``

    Also scans first-level subdirectories that look like unit projects
    (have a Makefile or source/ directory) so the context works correctly
    when the user is at the repository root rather than inside a unit.

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

    _hdl_exts = {".sv", ".svh", ".v", ".vh", ".vhd", ".vhdl", ".sva", ".sby", ".tcl"}
    _scan_dirs = [
        ("source/rtl", "RTL"),
        ("source/tb", "Testbench"),
        ("formal/src", "Formal"),
        ("constraints", "Constraints"),
    ]

    def _scan_unit_root(unit_path: Path, unit_label: str) -> bool:
        """Scan a single unit root; return True if any HDL files found."""
        found = False
        for subdir, label in _scan_dirs:
            scan_path = unit_path / subdir
            if not scan_path.is_dir():
                continue
            files = [
                f.name for f in sorted(scan_path.rglob("*"))
                if f.is_file() and f.suffix.lower() in _hdl_exts
                and f.name != ".gitkeep"
            ]
            if files:
                found = True
                lines.append(f"[{unit_label} / {label}: {', '.join(files)}]")
        return found

    # Check for unit project marker at cwd
    has_marker = (
        (root / "saxoflow.toml").exists()
        or (root / "unit.yaml").exists()
        or (root / ".saxoflow").is_dir()
    )
    if has_marker:
        lines.append(f"[Project root: {root.name}]")

    found_any = _scan_unit_root(root, root.name)

    # Also scan first-level subdirectories that look like unit projects.
    # A directory is treated as a unit project if it has source/ or Makefile.
    if not found_any or not has_marker:
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in {
                "__pycache__", "node_modules", ".venv", "venv",
                "docs", "scripts", "templates", "tests", "packs",
                "saxoflow", "saxoflow_agenticai", "cool_cli",
            }:
                continue
            # A unit project always has a source/ directory or Makefile
            if (child / "source").is_dir() or (child / "Makefile").exists():
                found_unit = _scan_unit_root(child, child.name)
                if found_unit:
                    found_any = True
                    if not has_marker:
                        lines.insert(0, f"[Workspace root: {root.name}]")
                        has_marker = True  # prevent duplicate insertion

    # If still nothing found, try a flat HDL scan of cwd
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
        # No explicit filename — try to infer from the design name in the request.
        # e.g. "create an alu design and place in myalu unit" → "alu.sv"
        design_match = _DESIGN_NAME_RE.search(lowered)
        if not design_match:
            return None
        # Collapse multi-word design names like "half adder" → "half_adder"
        raw_name = design_match.group(1).strip()
        inferred_stem = re.sub(r'\s+', '_', raw_name).lower().rstrip('_')
        if not inferred_stem:
            return None
        filename = f"{inferred_stem}.sv"
    else:
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
    rtl_context: str = "",
    top_module: str = "",
    max_review_iters: int = 1,
) -> str:
    """Generate HDL/script code from a natural-language spec.

    Routes ``rtl``, ``tb``, and ``formal`` requests through the specialist
    ``saxoflow_agenticai`` agents (with their prompt templates, guidelines files,
    and a generate→review→improve loop).

    All other content types (``synth``, ``sdc``, ``floorplan``, ``pnr``,
    ``drc``, ``lvs``, ``gds``, ``document``, etc.) fall through to the generic
    ``_invoke_llm`` path that was always here.

    If the agent backend is unavailable or raises, the generic path is used as
    a transparent fallback so the shell **never breaks**.

    Parameters
    ----------
    spec:
        Full natural-language request (used as the agent spec / LLM prompt).
    content_type:
        Artifact type: ``"rtl"``, ``"tb"``, ``"formal"``, ``"synth"``,
        ``"document"``, etc.
    provider / model:
        Optional LLM provider/model overrides (used by the generic fallback path;
        agent backends read their own model config from ``model_config.yaml``).
    rtl_context:
        Existing RTL source code — forwarded to ``TBGenAgent`` so it can
        inspect the DUT's ports and produce a better testbench.
    top_module:
        Top module name hint, derived from the RTL filename stem when available.
    max_review_iters:
        Number of generate→review→improve iterations passed to
        ``AgentFeedbackCoordinator``.  Default ``1`` keeps the shell fast
        (one gen pass + up to one review/improve cycle).

    Returns
    -------
    str
        Generated code string (code-fence wrappers are NOT stripped here —
        ``file_ops._strip_code_fences`` handles that).
    """
    # ------------------------------------------------------------------
    # Documentation export — never routed through agents
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Specialist agent routing — rtl / tb / formal
    # ------------------------------------------------------------------
    if _AGENTS_AVAILABLE and content_type in ("rtl", "tb", "formal"):
        try:
            code = _generate_via_agent(
                spec=spec,
                content_type=content_type,
                rtl_context=rtl_context,
                top_module=top_module,
                max_review_iters=max_review_iters,
            )
            if code and code.strip():
                return code
            # Empty result from agent — fall through to generic path
        except Exception:  # noqa: BLE001  — never crash the shell
            pass

    # ------------------------------------------------------------------
    # Generic fallback — synth / sdc / floorplan / pnr / drc / lvs / gds
    # and any content_type without a specialist agent yet.
    # Also used when the agent backend fails or returns empty.
    # ------------------------------------------------------------------
    _lang_hint = {
        "rtl":       "SystemVerilog/Verilog",
        "tb":        "SystemVerilog/Verilog testbench",
        "formal":    "SystemVerilog Assertions (SVA)",
        "synth":     "Yosys TCL synthesis script",
        "sdc":       "Synopsys Design Constraints (SDC) timing script",
        "floorplan": "OpenROAD Tcl floorplan script",
        "pnr":       "OpenROAD Tcl place-and-route script",
        "pdn":       "OpenROAD Tcl power-delivery-network script",
        "sta":       "OpenSTA Tcl static-timing-analysis script",
        "drc":       "Magic/KLayout DRC script",
        "lvs":       "Magic/netgen LVS script",
        "gds":       "KLayout/Magic GDS export script",
        "makefile":  "GNU Makefile",
    }.get(content_type, "HDL code")

    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"User request: {spec}\n\n"
        f"Generate ONLY the {_lang_hint}. "
        f"Output only the code/script block, no explanation, no markdown prose. "
        f"Wrap the code in a single ``` ... ``` block."
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


def _generate_via_agent(
    spec: str,
    content_type: str,
    rtl_context: str = "",
    top_module: str = "",
    max_review_iters: int = 1,
) -> str:
    """Route a generation request to the matching ``saxoflow_agenticai`` agent.

    Internal helper — always called from ``generate_code_for_save``.
    Any exception propagates up so the caller can fall back to ``_invoke_llm``.

    Agent / reviewer pairings
    -------------------------
    - ``"rtl"``    → RTLGenAgent   + RTLReviewAgent
    - ``"tb"``     → TBGenAgent    + TBReviewAgent
    - ``"formal"`` → FpropGenAgent + FpropReviewAgent

    Returns
    -------
    str
        The final generated code after the review loop.
    """
    _AGENT_PAIRS: Dict[str, Tuple[str, str]] = {
        "rtl":    ("rtlgen",    "rtlreview"),
        "tb":     ("tbgen",     "tbreview"),
        "formal": ("fpropgen",  "fpropreview"),
    }
    gen_key, rev_key = _AGENT_PAIRS[content_type]

    gen_agent = _AgentManager.get_agent(gen_key,  verbose=False)  # type: ignore[union-attr]
    rev_agent = _AgentManager.get_agent(rev_key,  verbose=False)  # type: ignore[union-attr]

    # Build the initial_spec tuple that AgentFeedbackCoordinator / the agent expects
    if content_type == "tb":
        # TBGenAgent.run(spec, rtl_code, top_module_name)
        rtl_src = rtl_context or ""  # empty string when no RTL available yet
        mod_name = top_module or "dut"
        initial_spec: Any = (spec, rtl_src, mod_name)
    elif content_type == "formal":
        # FpropGenAgent.run(spec, rtl_code)
        initial_spec = (spec, rtl_context) if rtl_context else spec
    else:
        # RTLGenAgent.run(spec)
        initial_spec = spec

    code, _review = _AgentFeedbackCoordinator.iterate_improvements(  # type: ignore[union-attr]
        agent=gen_agent,
        initial_spec=initial_spec,
        feedback_agent=rev_agent,
        max_iters=max_review_iters,
    )
    return code


# ---------------------------------------------------------------------------
# Companion file detection & generation
# ---------------------------------------------------------------------------

# Detects `include "X.sv" directives in generated HDL
_INCLUDE_RE = re.compile(r'`include\s+["<]([\w./]+\.[sv|svh|v|vh]+)[">\ ]', re.IGNORECASE)
# Detects package declarations: package foo; ... endpackage
_PACKAGE_DECL_RE = re.compile(r'\bpackage\s+(\w+)\s*;', re.IGNORECASE)
# Detects package imports: import foo::* or import foo::bar
_IMPORT_RE = re.compile(r'\bimport\s+(\w+)::', re.IGNORECASE)


def detect_companion_files(
    main_filename: str,
    generated_code: str,
) -> List[str]:
    """Analyse *generated_code* and return a list of companion filenames that
    the code depends on but are not the main file itself.

    Specifically detects:
    - `` `include "X.sv" `` directives
    - ``import X::`` references where ``X_pkg.sv`` or ``X.sv`` is likely needed

    Parameters
    ----------
    main_filename:
        The filename that was just generated (excluded from the result).
    generated_code:
        The full text of the generated HDL file.

    Returns
    -------
    List[str]
        List of bare filenames (e.g. ``["alu_pkg.sv"]``) that appear to be
        needed but were not part of the main save operation.
    """
    needed: List[str] = []
    seen: set = set()

    main_stem = Path(main_filename).stem.lower()

    # 1. Direct `include references
    for m in _INCLUDE_RE.finditer(generated_code):
        fname = m.group(1).strip()
        if fname.lower() != main_filename.lower() and fname not in seen:
            needed.append(fname)
            seen.add(fname)

    # 2. import pkg::* — check whether pkg_pkg.sv or pkg.sv is likely needed.
    #    Only add if different from the main file stem.
    for m in _IMPORT_RE.finditer(generated_code):
        pkg_name = m.group(1).strip().lower()
        if pkg_name == main_stem:
            continue
        # The companion package file is usually named <pkg_name>.sv
        # (SystemVerilog convention: alu_pkg package lives in alu_pkg.sv)
        candidate = f"{pkg_name}.sv"
        if candidate not in seen and candidate.lower() != main_filename.lower():
            needed.append(candidate)
            seen.add(candidate)

    return needed


def generate_companion_file(
    companion_filename: str,
    main_code: str,
    main_filename: str,
    spec: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Generate the content of a *companion file* (e.g. a package) that the
    main generated code depends on.

    Parameters
    ----------
    companion_filename:
        The name of the file to generate (e.g. ``"alu_pkg.sv"``).
    main_code:
        The already-generated main HDL file content (provides context).
    main_filename:
        Name of the already-generated main file (for reference).
    spec:
        Original user request (for additional context).
    provider / model:
        Optional LLM overrides.

    Returns
    -------
    str
        The generated code for the companion file (code-block stripped).
    """
    stem = Path(companion_filename).stem
    prompt = (
        f"{SAXOFLOW_SYSTEM_CONTEXT}\n\n"
        f"Context: The user requested: {spec}\n\n"
        f"The file `{main_filename}` was just generated with this content:\n"
        f"```\n{main_code}\n```\n\n"
        f"This main file depends on `{companion_filename}` ("
        f"referenced via `include or import). "
        f"Generate ONLY the SystemVerilog/Verilog code for `{companion_filename}`. "
        f"The package/module name should be `{stem}`. "
        f"Include all types, parameters, enums, and definitions that the main "
        f"file uses from this companion. "
        f"Output only the code block, no explanation. "
        f"Wrap in a single ```systemverilog ... ``` block."
    )
    try:
        return _invoke_llm(
            agent_type="buddy",
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError as exc:
        raise RuntimeError(
            f"LLM error generating companion file {companion_filename!r}: {exc}"
        ) from exc


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


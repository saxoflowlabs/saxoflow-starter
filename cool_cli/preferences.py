# cool_cli/preferences.py
"""
Persistent user preferences for the SaxoFlow AI Assistant.

Preferences are stored in ``~/.saxoflow/preferences.json`` and are loaded
once per shell session.  They allow students and researchers to configure
defaults that the AI buddy will apply automatically, such as:

- Preferred HDL language (SystemVerilog / Verilog / VHDL)
- Level of detail in explanations (brief / detailed)
- Custom naming conventions or style hints

Example preferences JSON:
    {
        "hdl": "vhdl",
        "detail_level": "brief",
        "naming": "use 'i_' prefix for inputs and 'o_' for outputs"
    }

Public API
----------
- VALID_PREFS: dict of allowed keys and their valid values (None = free text)
- load_prefs() -> dict
- save_prefs(delta: dict) -> dict
- prefs_context(prefs: dict | None = None) -> str
- detect_pref_intent(message: str) -> dict | None

Python 3.9+
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "VALID_PREFS",
    "load_prefs",
    "save_prefs",
    "prefs_context",
    "detect_pref_intent",
]

# ---------------------------------------------------------------------------
# Preference schema
# ---------------------------------------------------------------------------

VALID_PREFS: Dict[str, Any] = {
    "hdl":          ["sv", "verilog", "vhdl", "systemverilog"],
    "detail_level": ["brief", "detailed"],
    "naming":       None,   # free text
    "style":        None,   # free text
}

# Human-readable labels used when building the context string
_PREF_LABELS: Dict[str, str] = {
    "hdl":          "Preferred HDL",
    "detail_level": "Explanation detail",
    "naming":       "Naming convention",
    "style":        "Code style",
}

# Normalise common aliases for HDL values
_HDL_ALIASES: Dict[str, str] = {
    "systemverilog": "sv",
    "sv":            "sv",
    "verilog":       "verilog",
    "vhd":           "vhdl",
    "vhdl":          "vhdl",
}

# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------

def _prefs_path() -> Path:
    return Path.home() / ".saxoflow" / "preferences.json"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_prefs() -> Dict[str, Any]:
    """Load preferences from ``~/.saxoflow/preferences.json``.

    Returns an empty dict if the file does not exist or cannot be parsed.
    Unknown keys in the file are silently ignored so the schema can evolve.

    Returns
    -------
    dict
        Current preference values (only keys present in VALID_PREFS).
    """
    prefs_file = _prefs_path()
    if not prefs_file.is_file():
        return {}
    try:
        raw = json.loads(prefs_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    # Keep only known keys
    return {k: v for k, v in raw.items() if k in VALID_PREFS}


def save_prefs(delta: Dict[str, Any]) -> Dict[str, Any]:
    """Merge *delta* into the stored preferences and write them back.

    Invalid values for enumerated keys are silently normalised or ignored.
    Returns the full updated preferences dict.

    Parameters
    ----------
    delta:
        Partial dict of preferences to update.  Keys not in VALID_PREFS
        are ignored.

    Returns
    -------
    dict
        The full preferences dict after applying *delta*.
    """
    current = load_prefs()

    for key, value in delta.items():
        if key not in VALID_PREFS:
            continue  # unknown key — ignore

        allowed = VALID_PREFS[key]

        # Free-text field
        if allowed is None:
            current[key] = str(value).strip()
            continue

        # Enumerated field — normalise
        norm = str(value).strip().lower()
        # HDL-specific alias normalisation
        if key == "hdl":
            norm = _HDL_ALIASES.get(norm, norm)
        if norm in allowed:
            current[key] = norm

    prefs_file = _prefs_path()
    prefs_file.parent.mkdir(parents=True, exist_ok=True)
    prefs_file.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


# ---------------------------------------------------------------------------
# Context string builder
# ---------------------------------------------------------------------------

def prefs_context(prefs: Optional[Dict[str, Any]] = None) -> str:
    """Return a compact context string for LLM prompt injection.

    Parameters
    ----------
    prefs:
        Preferences dict (from ``load_prefs()``).  If None, loads from disk.

    Returns
    -------
    str
        Empty string if no preferences are set, so callers can safely
        concatenate without adding noise.  Otherwise returns a section
        block like::

            == USER PREFERENCES ==
            Preferred HDL: sv
            Explanation detail: brief
    """
    if prefs is None:
        prefs = load_prefs()
    if not prefs:
        return ""
    lines = ["== USER PREFERENCES (apply these globally) =="]
    for key, label in _PREF_LABELS.items():
        if key in prefs:
            lines.append(f"{label}: {prefs[key]}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

# Matches "prefer vhdl", "use systemverilog", "always use brief", "set hdl to vhdl",
# "change style to ...", "I prefer detailed explanations"
_PREF_INTENT_RE = re.compile(
    r'\b(?:prefer|use|always\s+use|set\s+\w+\s+to|change\s+\w+\s+to|i\s+prefer'
    r'|default\s+to|switch\s+to)\s+(.+)',
    re.IGNORECASE,
)

_HDL_DETECT_RE = re.compile(
    r'\b(systemverilog|sv|verilog|vhdl?)\b',
    re.IGNORECASE,
)
_DETAIL_DETECT_RE = re.compile(
    r'\b(brief|detailed|verbose|concise)\b',
    re.IGNORECASE,
)


def detect_pref_intent(message: str) -> Optional[Dict[str, str]]:
    """Detect a user message that sets a persistent preference.

    Parameters
    ----------
    message:
        Raw user input.

    Returns
    -------
    dict | None
        ``{"key": str, "value": str, "raw": str}``
        or None if no preference intent is detected.

    Examples
    --------
    >>> detect_pref_intent("prefer vhdl")
    {"key": "hdl", "value": "vhdl", "raw": "prefer vhdl"}
    >>> detect_pref_intent("always use brief explanations")
    {"key": "detail_level", "value": "brief", "raw": "always use brief explanations"}
    """
    if not message or not _PREF_INTENT_RE.search(message):
        return None

    # Try to extract HDL preference
    hdl_m = _HDL_DETECT_RE.search(message)
    if hdl_m:
        return {
            "key": "hdl",
            "value": hdl_m.group(1).lower(),
            "raw": message,
        }

    # Try to extract detail level preference
    detail_m = _DETAIL_DETECT_RE.search(message)
    if detail_m:
        val = detail_m.group(1).lower()
        if val in ("verbose",):
            val = "detailed"
        if val in ("concise",):
            val = "brief"
        return {
            "key": "detail_level",
            "value": val,
            "raw": message,
        }

    return None

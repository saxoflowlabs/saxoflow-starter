# saxoflow/ai/contracts.py
"""
M4 AI Command Plane — canonical data contracts.

Defines:
- AiLifecycleVerb   : canonical verb enum (plan | run | resume | explain | review)
- AiApprovalPolicy  : approval gate policy for AI operations
- HIGH_IMPACT_ACTIONS: set of action names that require explicit user approval
- AiRunRecord       : structured run record attached to every AI operation
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AiLifecycleVerb(str, enum.Enum):
    """Canonical lifecycle verbs for the ``saxoflow ai`` command plane."""

    PLAN = "plan"
    RUN = "run"
    RESUME = "resume"
    EXPLAIN = "explain"
    REVIEW = "review"


class AiApprovalPolicy(str, enum.Enum):
    """Approval gate policy applied before a high-impact AI operation runs."""

    NONE = "none"              # read-only / low-impact: no gate
    REQUIRE_FLAG = "require_flag"  # caller must pass --yes / --approve
    INTERACTIVE = "interactive"    # prompt in a real TTY


# ---------------------------------------------------------------------------
# High-impact action registry
# ---------------------------------------------------------------------------

#: Actions that mutate the project filesystem or run long simulations.
#: These require explicit approval before execution.
HIGH_IMPACT_ACTIONS: frozenset[str] = frozenset({"fullpipeline", "sim"})


# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------

@dataclass
class AiRunRecord:
    """Structured record attached to every AI lifecycle operation.

    Parameters
    ----------
    run_id:
        Unique hex run identifier (12 hex chars from :func:`run_store.new_run_id`).
    verb:
        The lifecycle verb that created this record.
    action:
        Sub-action name (e.g. ``rtlgen``, ``fullpipeline``, ``rtl``).
    workspace:
        Absolute or relative path to the SaxoFlow workspace root.
    started_at:
        ISO-8601 timestamp of when the run was initiated.
    status:
        Lifecycle status — one of ``pending | running | done | failed``.
    ended_at:
        ISO-8601 timestamp of when the run finished (``None`` while running).
    outputs:
        Structured output dict populated by the dispatcher.
    error:
        Error message if ``status == "failed"``; ``None`` otherwise.
    """

    run_id: str
    verb: AiLifecycleVerb
    action: str
    workspace: str
    started_at: str
    status: str = "pending"
    ended_at: Optional[str] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_high_impact(self) -> bool:
        """Return ``True`` when this action requires explicit approval."""
        return self.action in HIGH_IMPACT_ACTIONS

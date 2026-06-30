"""Verification subgraph for routing formal diagnostics into repair or escalation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


class VerificationGraphError(ValueError):
    """Raised when verification subgraph payloads are invalid."""


def _as_string_tuple(raw: Any, field_name: str) -> Tuple[str, ...]:
    if raw is None:
        return tuple()
    if not isinstance(raw, list):
        raise VerificationGraphError(f"Verification subgraph `{field_name}` must be a list of strings.")
    normalized = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise VerificationGraphError(
                f"Verification subgraph `{field_name}` must contain non-empty strings."
            )
        normalized.append(item.strip())
    return tuple(dict.fromkeys(normalized))


@dataclass(frozen=True)
class VerificationSubgraphTemplate:
    """Route formal outcomes into repair-loop actions or escalation."""

    max_repair_attempts: int = 2

    def invoke(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        formal_result = payload.get("formal_result")
        if not isinstance(formal_result, Mapping):
            raise VerificationGraphError("Verification subgraph payload missing `formal_result` mapping.")

        status = str(formal_result.get("status") or "").strip().lower()
        if not status:
            raise VerificationGraphError("Verification subgraph `formal_result.status` is required.")

        diagnostics = payload.get("diagnostics")
        if diagnostics is None:
            diagnostics = []
        if not isinstance(diagnostics, list):
            raise VerificationGraphError("Verification subgraph `diagnostics` must be a list.")

        counterexample_refs = _as_string_tuple(
            payload.get("counterexample_refs"),
            "counterexample_refs",
        )

        attempt = payload.get("attempt", 1)
        if not isinstance(attempt, int) or attempt < 1:
            raise VerificationGraphError("Verification subgraph `attempt` must be a positive integer.")

        if status in {"pass", "cover", "success"}:
            return {
                "status": "verified",
                "decision": "complete",
                "attempt": attempt,
                "repair_actions": [],
                "escalation_reason": None,
                "counterexample_refs": list(counterexample_refs),
            }

        repair_actions = []
        if counterexample_refs:
            repair_actions.append(
                "Inspect counterexample traces and patch RTL/testbench assertions for violated properties."
            )
        if diagnostics:
            repair_actions.append(
                "Address failing properties reported by formal diagnostics and re-run proof."
            )

        should_repair = attempt <= self.max_repair_attempts and bool(repair_actions)
        if should_repair:
            return {
                "status": "needs-repair",
                "decision": "repair",
                "attempt": attempt,
                "repair_actions": repair_actions,
                "escalation_reason": None,
                "counterexample_refs": list(counterexample_refs),
            }

        reason = "Formal proof failed without actionable repair inputs."
        if attempt > self.max_repair_attempts:
            reason = "Formal proof failed after reaching repair-attempt limit."

        return {
            "status": "escalated",
            "decision": "escalate",
            "attempt": attempt,
            "repair_actions": repair_actions,
            "escalation_reason": reason,
            "counterexample_refs": list(counterexample_refs),
        }

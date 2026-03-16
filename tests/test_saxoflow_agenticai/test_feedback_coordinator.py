"""
Hermetic tests for saxoflow_agenticai.orchestrator.feedback_coordinator.

We exercise the public API plus key helper branches:
- is_no_action_feedback: normalization, regexes, line-wise OK detection
- iterate_improvements: quiet stdio, blank feedback fallback,
  improvement mapping per agent type, NotImplemented path, and max-iters path.

All tests are deterministic and avoid real I/O/network.
"""

from __future__ import annotations

import io
import logging
from typing import Any, List, Tuple

import pytest


# -----------------------
# Tiny local fakes
# -----------------------

class GenAgentFake:
    """
    Minimal generator agent with:
    - .agent_type marker for mapping
    - .run(*args) producing an output and capturing sys.stdout type
    - .improve(*args) returning improved output or raising NotImplementedError
    """

    def __init__(
        self,
        agent_type: str | None,
        first_output: str = "OUT0",
        improved_output: str = "OUT1",
        improve_raises: BaseException | None = None,
    ) -> None:
        self.agent_type = agent_type
        self.first_output = first_output
        self.improved_output = improved_output
        self.improve_raises = improve_raises
        self.run_calls: list[tuple] = []
        self.improve_calls: list[tuple] = []
        self.stdout_types_seen: list[type] = []

    def run(self, *args):
        # capture current sys.stdout type to assert suppression behavior
        import sys as _sys
        self.stdout_types_seen.append(type(_sys.stdout))
        self.run_calls.append(args)
        return self.first_output

    def improve(self, *args):
        import sys as _sys
        self.stdout_types_seen.append(type(_sys.stdout))
        self.improve_calls.append(args)
        if self.improve_raises:
            raise self.improve_raises
        return self.improved_output


class FeedbackAgentFake:
    """
    Review/debug agent that returns queued feedback strings.
    Records received args for mapping assertions.
    """
    def __init__(self, feedback_items: List[str]) -> None:
        self.feedback_items = list(feedback_items)
        self.calls: List[Tuple[Any, ...]] = []

    def run(self, *args):
        self.calls.append(args)
        if not self.feedback_items:
            return ""
        return self.feedback_items.pop(0)


def _logger_at(level: int) -> logging.Logger:
    lg = logging.getLogger(f"afc_test_{level}")
    # Ensure handlers/level are consistent for tests
    lg.handlers[:] = []
    lg.setLevel(level)
    return lg


# -----------------------
# is_no_action_feedback
# -----------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("", True),                         # empty → True
        ("ok", True),                       # short < 12 chars → True
        ("No major issues found.", True),   # pattern
        ("Looks GOOD!", True),              # case-insensitive
        ("Section A: none", True),          # section-line OK
        ("pass", True),                     # single word pass
        ("   Approved   ", True),           # padded
        ("All good\nclean\n", True),        # all lines OK
        ("needs changes", False),           # not ok
        ("Investigate timing.", False),
    ],
)
def test_is_no_action_feedback_matrix(text, expected):
    """
    Validate the 'no action' detector across normalization, regexes,
    and line-wise shapes. This locks behavior for future refactors.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut

    assert sut.AgentFeedbackCoordinator.is_no_action_feedback(text) is expected


# -----------------------
# _suppress_stdio behavior
# -----------------------

def test_suppress_stdio_swaps_and_restores():
    """
    When enabled=True, _suppress_stdio should use io.StringIO for stdout/stderr
    inside the context, and restore originals on exit.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut
    import sys

    old_out, old_err = sys.stdout, sys.stderr
    with sut._suppress_stdio(True):
        assert isinstance(sys.stdout, io.StringIO)
        assert isinstance(sys.stderr, io.StringIO)
    assert sys.stdout is old_out
    assert sys.stderr is old_err


# -----------------------
# iterate_improvements: quiet stdio + blank feedback fallback
# -----------------------

def test_iterate_blank_feedback_triggers_fallback_and_exits(caplog):
    """
    If feedback agent returns blank, the coordinator should:
    - log a WARNING with fallback message,
    - treat it as 'no action' and exit at iteration 1,
    - return initial output and the fallback text.
    Quiet stdio path is exercised by using logger at WARNING.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut

    gen = GenAgentFake(agent_type="rtlgen", first_output="RTL0")
    fb = FeedbackAgentFake(["", "should-not-be-used"])

    with caplog.at_level(logging.WARNING):
        out, last = sut.AgentFeedbackCoordinator.iterate_improvements(
            agent=gen,
            initial_spec="SPEC",
            feedback_agent=fb,
            max_iters=3,
            logger=_logger_at(logging.WARNING),
        )

    assert out == "RTL0"
    assert last.lower().startswith("no major issues")
    # Fallback warning present
    assert any("returned blank feedback" in r.message for r in caplog.records)
    # run was called once, no improve calls
    assert len(gen.run_calls) == 1
    assert not gen.improve_calls
    # Quiet stdio → run captured StringIO
    assert any(t is io.StringIO for t in gen.stdout_types_seen)


# -----------------------
# iterate_improvements: improvement + mapping for agent types
# -----------------------

@pytest.mark.parametrize(
    "agent_type, spec, generated, expected_review_args",
    [
        ("tbgen", ("SPEC", "RTL", "TOP"), "TB0", ("SPEC", "RTL", "TOP", "TB0")),
        ("rtlgen", ("SPEC",), "RTL0", ("SPEC", "RTL0")),
        ("fpropgen", ("SPEC", "RTL"), "FP0", ("SPEC", "RTL", "FP0")),
        (None, ("SPEC", "EXTRA"), "GEN0", ("SPEC", "EXTRA", "GEN0")),  # default path
    ],
)
def test_build_review_args_paths(agent_type, spec, generated, expected_review_args):
    """
    Cover _build_review_args via iterate_improvements by inspecting
    the arguments the feedback agent receives for each agent type.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut

    # generator emits 'generated' as first output; feedback asks for change → improve
    gen = GenAgentFake(agent_type=agent_type, first_output=generated, improved_output="IMPROVED")
    fb = FeedbackAgentFake(
        ["needs significant change", "no issues"]  # second round exits
    )

    out, last = sut.AgentFeedbackCoordinator.iterate_improvements(
        agent=gen,
        initial_spec=spec,
        feedback_agent=fb,
        max_iters=2,
        logger=_logger_at(logging.INFO),  # non-quiet to hit the other stdio branch
    )

    # Verify feedback agent saw the expected review args for round 1
    assert fb.calls
    assert fb.calls[0] == expected_review_args
    # Final output should be improved (one improvement), then exit on "no issues"
    assert out == "IMPROVED"
    assert "no issues" in last.lower()
    # Non-quiet stdio → stdout types not all StringIO
    assert not all(t is io.StringIO for t in gen.stdout_types_seen)


@pytest.mark.parametrize(
    "agent_type, spec, prev, feedback, expected_improve_args",
    [
        ("fpropgen", ("SPEC", "RTL"), "FP0", "please update constraints",
         ("SPEC", "RTL", "FP0", "please update constraints")),
        ("tbgen", ("SPEC", "RTL", "TOP"), "TB0", "extend tests for edge cases",
         ("SPEC", "TB0", "extend tests for edge cases", "RTL", "TOP")),
        ("rtlgen", ("SPEC",), "RTL0", "requires additional review details",
         ("SPEC", "RTL0", "requires additional review details")),
        (None, ("S1", "S2"), "GEN0", "feedback required to proceed",
         ("S1", "S2", "GEN0", "feedback required to proceed")),
    ],
)
def test_build_improve_args_paths(agent_type, spec, prev, feedback, expected_improve_args):
    """
    Cover _build_improve_args by asserting the exact tuple the generator receives
    for improve(...) in the first improvement iteration.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut

    # Feedback makes us improve once; second feedback exits
    fb = FeedbackAgentFake([feedback, "no feedback"])  # second triggers 'no action'
    gen = GenAgentFake(agent_type=agent_type, first_output=prev, improved_output="IMPR1")

    out, last = sut.AgentFeedbackCoordinator.iterate_improvements(
        agent=gen,
        initial_spec=spec,
        feedback_agent=fb,
        max_iters=2,
        logger=_logger_at(logging.WARNING),
    )

    assert gen.improve_calls, "improve() must be called once"
    assert gen.improve_calls[0] == expected_improve_args
    assert out == "IMPR1"
    assert sut.AgentFeedbackCoordinator.is_no_action_feedback(last)


# -----------------------
# iterate_improvements: NotImplemented and max-iters
# -----------------------

def test_iterate_improve_not_implemented_stops_with_warning(caplog):
    """
    If improve() raises NotImplementedError, the loop logs a WARNING and stops,
    returning the last output (without change) and last feedback.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut

    gen = GenAgentFake(
        agent_type="rtlgen",
        first_output="RTL0",
        improved_output="SHOULD_NOT_APPEAR",
        improve_raises=NotImplementedError("no impl"),
    )
    # Long feedback ensures the loop *tries* to improve (so the exception happens)
    fb = FeedbackAgentFake(["Please address additional cases beyond coverage threshold."])

    with caplog.at_level(logging.INFO):
        out, last = sut.AgentFeedbackCoordinator.iterate_improvements(
            agent=gen,
            initial_spec=("SPEC",),
            feedback_agent=fb,
            max_iters=2,
            logger=_logger_at(logging.INFO),
        )

    assert out == "RTL0"
    assert "coverage threshold" in last
    assert any("not implemented" in r.message.lower() for r in caplog.records)


def test_iterate_max_iters_triggers_for_else_warning(caplog):
    """
    When review never reports 'no action', the for/else warning branch executes:
    - 'Max iterations reached' WARNING is logged,
    - output is the last improved value,
    - last_feedback is the last feedback seen.
    """
    from saxoflow_agenticai.orchestrator import feedback_coordinator as sut

    # Always ask for changes with sufficiently long messages
    feedback_items = [
        "Still failing: update coverage thresholds and retry.",
        "Compilation still failing: fix type widths and resets.",
        "Keep iterating: waveform mismatches remain unaddressed.",
    ]
    fb = FeedbackAgentFake(feedback_items.copy())
    gen = GenAgentFake(agent_type=None, first_output="X0", improved_output="X1")

    with caplog.at_level(logging.WARNING):
        out, last = sut.AgentFeedbackCoordinator.iterate_improvements(
            agent=gen,
            initial_spec=("S", "T"),
            feedback_agent=fb,
            max_iters=2,  # 2 iterations → triggers else branch
            logger=_logger_at(logging.WARNING),
        )

    # Improvement happened; since our fake returns "X1" for every improve, we expect X1.
    assert out == "X1"
    # The last feedback is the second item (two iterations)
    assert last == feedback_items[1]
    assert any("Max iterations reached" in r.message for r in caplog.records)

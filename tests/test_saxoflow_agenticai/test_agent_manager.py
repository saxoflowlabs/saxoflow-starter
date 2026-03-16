from __future__ import annotations

"""
Tests for saxoflow_agenticai.core.agent_manager

Coverage goals
--------------
- AgentManager.all_agent_names returns registry keys.
- AgentManager.get_agent:
    * unknown agent -> UnknownAgentError
    * 'sim' path does NOT resolve an LLM (ignores provided llm), applies quiet defaults
    * LLM resolution via ModelSelector with provider/model overrides (consumed)
    * explicit llm skips ModelSelector entirely
    * quiet defaults mutate ctor kwargs & downshift module logger
    * verbose=True sets INFO log level only
    * constructor kwargs mismatch -> wrapped RuntimeError with helpful message

All tests are hermetic; ModelSelector and logging are patched as imported in SUT.
"""

import logging
from typing import Any, Dict

import pytest


def _fresh_module():
    """Reload SUT to avoid global state pollution across tests."""
    import importlib

    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.core.agent_manager")
    )


# -------------------------
# Basic registry behaviors
# -------------------------

def test_all_agent_names_reflects_registry():
    """
    all_agent_names(): returns the same ordered keys as the internal registry.
    Why: guards accidental key drift vs. public listing.
    """
    sut = _fresh_module()
    assert sut.AgentManager.all_agent_names() == list(sut.AgentManager.AGENT_MAP.keys())


def test_get_agent_unknown_raises():
    """
    get_agent(): unknown name -> UnknownAgentError.
    Why: explicit error contract for bad keys.
    """
    sut = _fresh_module()
    with pytest.raises(sut.UnknownAgentError):
        sut.AgentManager.get_agent("does-not-exist")


# -------------------------
# Sim agent path (non-LLM)
# -------------------------

def test_get_agent_sim_does_not_resolve_llm_and_applies_quiet_defaults(monkeypatch):
    """
    'sim' path must not call ModelSelector.get_model and should apply quiet defaults.
    We assert ModelSelector.get_model would explode if called.
    """
    sut = _fresh_module()

    # ModelSelector shouldn't be touched for 'sim'
    monkeypatch.setattr(
        sut.ModelSelector,
        "get_model",
        lambda **_: (_ for _ in ()).throw(AssertionError("ModelSelector should not be called for 'sim'")),
        raising=True,
    )

    # Capture original module logger level (for cleanliness)
    sim_logger = logging.getLogger("saxoflow_agenticai.agents.sim_agent")
    prev_level = sim_logger.level
    try:
        agent = sut.AgentManager.get_agent("sim", verbose=False, llm=object())
        # Returned instance is SimAgent; we don't need to run it, just ensure constructed.
        assert agent.__class__.__name__ == "SimAgent"
        # Quiet defaults downshift agent module logger to WARNING when not verbose.
        assert logging.getLogger(agent.__module__).level == logging.WARNING
    finally:
        sim_logger.setLevel(prev_level)


# -------------------------------------------
# LLM resolution and provider/model overrides
# -------------------------------------------

def test_get_agent_resolves_llm_and_consumes_overrides(monkeypatch):
    """
    When llm is None, the manager must resolve via ModelSelector with provider/model
    overrides and must NOT forward those override kwargs to the agent constructor.
    """
    sut = _fresh_module()

    seen: Dict[str, Any] = {}

    class DummyAgent(sut.BaseAgent):  # type: ignore[misc]
        def __init__(self, llm=None, verbose: bool = False, **kwargs):
            self.llm = llm
            self.verbose = verbose
            self.kwargs = kwargs

        def run(self, *_a, **_k):  # pragma: no cover - not used here
            return "ok"

    # Register a temporary agent key
    monkeypatch.setitem(sut.AgentManager.AGENT_MAP, "dummyllm", DummyAgent)

    sentinel_llm = object()

    def fake_get_model(agent_type: str, provider: str | None, model_name: str | None):
        # Assert the manager passed through our overrides to ModelSelector
        seen["agent_type"] = agent_type
        seen["provider"] = provider
        seen["model_name"] = model_name
        return sentinel_llm

    monkeypatch.setattr(sut.ModelSelector, "get_model", fake_get_model, raising=True)

    inst = sut.AgentManager.get_agent(
        "dummyllm",
        provider="groq",
        model_name="llama3-8b-8192",
        extra="X",
    )

    assert isinstance(inst, DummyAgent)
    assert inst.llm is sentinel_llm
    # Overrides were consumed by AgentManager, not forwarded to the agent __init__
    assert "provider" not in inst.kwargs and "model_name" not in inst.kwargs
    assert inst.kwargs.get("extra") == "X"
    # Verify values seen by ModelSelector
    assert seen == {
        "agent_type": "dummyllm",
        "provider": "groq",
        "model_name": "llama3-8b-8192",
    }


def test_get_agent_with_explicit_llm_skips_modelselector(monkeypatch):
    """
    If llm is provided, ModelSelector.get_model must not be called.
    """
    sut = _fresh_module()

    class DummyAgent(sut.BaseAgent):  # type: ignore[misc]
        def __init__(self, llm=None, verbose: bool = False, **_kw):
            self.llm = llm
            self.verbose = verbose

        def run(self, *args, **kwargs):
            return "ok"

    monkeypatch.setitem(sut.AgentManager.AGENT_MAP, "ephemeral", DummyAgent)

    monkeypatch.setattr(
        sut.ModelSelector,
        "get_model",
        lambda **_: (_ for _ in ()).throw(AssertionError("should not resolve llm when provided")),
        raising=True,
    )

    provided_llm = object()
    inst = sut.AgentManager.get_agent("ephemeral", llm=provided_llm)
    assert inst.llm is provided_llm


# -------------------------
# Quiet defaults + logging
# -------------------------

def test_quiet_defaults_added_when_supported_and_verbose_false(monkeypatch):
    """
    When not verbose, _apply_quiet_defaults should inject quiet flags if the agent
    supports them and set module logger to WARNING.
    """
    sut = _fresh_module()

    received = {}

    class VerboseCapableAgent(sut.BaseAgent):  # type: ignore[misc]
        def __init__(
            self,
            llm=None,
            verbose: bool = False,
            emit_stdout: bool = True,
            quiet: bool = False,
            silent: bool = False,
            log_level: int | None = None,
        ):
            nonlocal received
            received = {
                "llm": llm,
                "verbose": verbose,
                "emit_stdout": emit_stdout,
                "quiet": quiet,
                "silent": silent,
                "log_level": log_level,
            }

        def run(self, *args, **kwargs):
            return "ok"

    monkeypatch.setitem(sut.AgentManager.AGENT_MAP, "quiety", VerboseCapableAgent)

    prev_level = logging.getLogger(VerboseCapableAgent.__module__).level
    try:
        # Resolve LLM to bypass model config file lookups
        monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: object(), raising=True)
        _ = sut.AgentManager.get_agent("quiety", verbose=False)
        # Defaults should be injected to make it quiet
        assert received["emit_stdout"] is False
        assert received["quiet"] is True
        assert received["silent"] is True
        assert received["log_level"] == logging.WARNING
        # Module logger downshifted
        assert logging.getLogger(VerboseCapableAgent.__module__).level == logging.WARNING
    finally:
        logging.getLogger(VerboseCapableAgent.__module__).setLevel(prev_level)


def test_verbose_true_sets_info_level_only(monkeypatch):
    """
    With verbose=True, manager should set log_level=INFO (if supported) and should
    not forcibly supply quiet flags.
    """
    sut = _fresh_module()

    received = {}

    class InfoOnlyAgent(sut.BaseAgent):  # type: ignore[misc]
        def __init__(self, llm=None, verbose: bool = False, log_level: int | None = None, **kwargs):
            nonlocal received
            received = {"llm": llm, "verbose": verbose, "log_level": log_level, "kwargs": dict(kwargs)}

        def run(self, *args, **kwargs):
            return "ok"

    monkeypatch.setitem(sut.AgentManager.AGENT_MAP, "chatter", InfoOnlyAgent)

    prev_level = logging.getLogger(InfoOnlyAgent.__module__).level
    try:
        monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: object(), raising=True)
        _ = sut.AgentManager.get_agent("chatter", verbose=True)
        assert received["verbose"] is True
        assert received["log_level"] == logging.INFO
        # No unexpected quiet flags forwarded
        assert received["kwargs"] == {}
        assert logging.getLogger(InfoOnlyAgent.__module__).level == logging.INFO
    finally:
        logging.getLogger(InfoOnlyAgent.__module__).setLevel(prev_level)


# --------------------------------
# Constructor mismatch -> wrapped
# --------------------------------

def test_constructor_kwargs_mismatch_yields_runtimeerror(monkeypatch):
    """
    If the agent class __init__ doesn't accept the injected kwargs ('verbose', 'llm', etc.),
    the manager should wrap the TypeError into a RuntimeError with the agent name.
    """
    sut = _fresh_module()

    class BadCtorAgent:  # deliberately NOT a BaseAgent and incompatible __init__
        def __init__(self):  # no args accepted
            pass

    monkeypatch.setitem(sut.AgentManager.AGENT_MAP, "badctor", BadCtorAgent)
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: object(), raising=True)

    with pytest.raises(RuntimeError) as ei:
        sut.AgentManager.get_agent("badctor")

    msg = str(ei.value)
    assert "Failed to construct agent 'badctor'" in msg
    # The message should hint at which kwargs were attempted
    assert "kwargs" in msg or "with kwargs" in msg

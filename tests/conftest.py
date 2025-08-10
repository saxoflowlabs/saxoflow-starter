from __future__ import annotations

import importlib
from typing import Any, Callable, Optional, List

import pytest


# Centralize the import so we can adapt if your package path differs.
@pytest.fixture(scope="session")
def ai_buddy_mod():
    """
    Import the module under test using the canonical path.
    If your layout differs, change the import here once.
    """
    return importlib.import_module("cool_cli.ai_buddy")


class DummyLLM:
    """Minimal LLM stub that records prompts and returns a fixed response."""
    def __init__(self, response: Any, raise_on_invoke: Optional[BaseException] = None):
        self.response = response
        self.raise_on_invoke = raise_on_invoke
        self.seen_prompts = []

    def invoke(self, prompt: str) -> Any:
        self.seen_prompts.append(prompt)
        if self.raise_on_invoke:
            raise self.raise_on_invoke
        return self.response


class DummyAgent:
    """Minimal review agent stub."""
    def __init__(self, result: Any = "OK", raise_on_run: Optional[BaseException] = None):
        self.result = result
        self.raise_on_run = raise_on_run
        self.seen_inputs = []

    def run(self, arg: str) -> Any:
        self.seen_inputs.append(arg)
        if self.raise_on_run:
            raise self.raise_on_run
        return self.result


@pytest.fixture
def patch_model(monkeypatch, ai_buddy_mod) -> Callable[[Any, Optional[BaseException]], DummyLLM]:
    """
    Patch ModelSelector.get_model to return a DummyLLM.
    Usage: dummy = patch_model(response="Hello")
    """
    def _factory(response: Any, err: Optional[BaseException] = None) -> DummyLLM:
        dummy = DummyLLM(response=response, raise_on_invoke=err)
        monkeypatch.setattr(ai_buddy_mod.ModelSelector, "get_model", lambda **_: dummy)
        return dummy
    return _factory


@pytest.fixture
def patch_agent(monkeypatch, ai_buddy_mod) -> Callable[[Any, Optional[BaseException]], DummyAgent]:
    """
    Patch AgentManager.get_agent to return a DummyAgent.
    Usage: agent = patch_agent(result="Review OK")
    """
    def _factory(result: Any = "OK", err: Optional[BaseException] = None) -> DummyAgent:
        dummy = DummyAgent(result=result, raise_on_run=err)
        monkeypatch.setattr(ai_buddy_mod.AgentManager, "get_agent", lambda action: dummy)
        return dummy
    return _factory


@pytest.fixture(scope="session")
def banner_mod():
    """
    Import the banner module under test using the canonical path.
    If your package path differs, change the import here once.
    """
    return importlib.import_module("cool_cli.banner")


class DummyConsole:
    """A minimal stand-in for rich.Console that just records printed objects."""
    def __init__(self) -> None:
        self.printed: List[object] = []

    def print(self, *objects, **kwargs) -> None:  # noqa: D401 - signature mirrors Console
        # We simply collect the first positional object for assertions.
        if objects:
            self.printed.append(objects[0])
        else:
            self.printed.append(None)


@pytest.fixture
def dummy_console() -> DummyConsole:
    return DummyConsole()


@pytest.fixture(scope="session")
def commands_mod():
    """
    Import the commands module under test using the canonical path.
    If your package path differs, change the import here once.
    """
    return importlib.import_module("cool_cli.commands")


class DummyConsole:
    """A minimal stand-in for rich.Console that records prints and clears."""
    def __init__(self, width: int = 100) -> None:
        self.width = width
        self.printed: List[object] = []
        self.clears: int = 0

    def print(self, *objects, **kwargs) -> None:
        if objects:
            self.printed.append(objects[0])
        else:
            self.printed.append(None)

    def clear(self) -> None:
        self.clears += 1


@pytest.fixture
def dummy_console() -> DummyConsole:
    return DummyConsole()


@pytest.fixture(scope="session")
def panels_mod():
    """
    Import the panels module under test using the canonical path.
    Change here once if your import path differs.
    """
    return importlib.import_module("cool_cli.panels")

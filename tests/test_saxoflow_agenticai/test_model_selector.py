"""
Hermetic tests for saxoflow_agenticai.core.model_selector.

- No network.
- Only ephemeral filesystem (tmp_path) when testing YAML loader.
- External providers are stubbed.
- Patches use the SUT's import paths to avoid missed patches.
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Any, Dict, Tuple

import pytest


# --------------------------
# Local fakes used by tests
# --------------------------

class FakeChatOpenAI:
    """Stand-in for langchain_openai.ChatOpenAI capturing init kwargs."""
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    # Methods below let this fake behave like an LCEL runnable if needed elsewhere
    def bind(self, **kwargs: Any) -> "FakeChatOpenAI":
        self._last_bind = kwargs
        return self

    def with_config(self, config: Dict[str, Any]) -> "FakeChatOpenAI":
        self._config = config
        return self


class FakeLLM:
    """Generic LCEL-like fake with the few methods ModelSelector uses."""
    def __init__(self) -> None:
        self.bound = []
        self.config = None
        self.tools = None
        self.tool_choice = None
        self.structured = None

    def bind(self, **kwargs: Any) -> "FakeLLM":
        self.bound.append(("bind", kwargs))
        return self

    def with_config(self, config: Dict[str, Any]) -> "FakeLLM":
        self.config = dict(config)
        return self

    def with_structured_output(self, schema: Any, strict: bool = True) -> "FakeLLM":
        self.structured = ("structured", schema, strict)
        return self

    def bind_tools(self, tools) -> "FakeLLM":
        self.tools = list(tools)
        return self


# --------------------------
# Private helpers coverage
# --------------------------

def test__load_yaml_config_success_and_cache(tmp_path, monkeypatch):
    """
    _load_yaml_config returns mapping, caches by path, and logs keys.
    Subsequent content changes to the same path are not observed due to cache.
    """
    from saxoflow_agenticai.core import model_selector as sut

    # Ensure a clean cache for this test
    sut._load_yaml_config.cache_clear()  # type: ignore[attr-defined]

    p = tmp_path / "model_config.yaml"
    p.write_text("default_provider: openai\ndefault_model: gpt-4o\n", encoding="utf-8")

    with pytest.raises(KeyError):
        # sanity: ensure that if we read the file we wrote, keys exist
        _ = {"default_provider": "x"}["missing"]

    cfg1 = sut._load_yaml_config(p)
    assert cfg1["default_provider"] == "openai"
    assert cfg1["default_model"] == "gpt-4o"

    # Modify file; due to lru_cache it should still return the cached version
    p.write_text("default_provider: groq\ndefault_model: mixtral\n", encoding="utf-8")
    cfg2 = sut._load_yaml_config(p)
    assert cfg2["default_provider"] == "openai"  # cached
    assert cfg2["default_model"] == "gpt-4o"

    # Clear cache for other tests
    sut._load_yaml_config.cache_clear()  # type: ignore[attr-defined]


def test__load_yaml_config_missing(tmp_path, monkeypatch):
    """Raises ConfigNotFoundError when config path does not exist."""
    from saxoflow_agenticai.core import model_selector as sut

    sut._load_yaml_config.cache_clear()  # type: ignore[attr-defined]
    missing = tmp_path / "absent.yaml"
    with pytest.raises(sut.ConfigNotFoundError):
        sut._load_yaml_config(missing)


@pytest.mark.parametrize(
    "content,exc_type,substr",
    [
        ("- just\n- a\n- list\n", "ConfigParseError", "must parse to a mapping"),
        ("default_provider: [unterminated\n", "ConfigParseError", "Error parsing"),
    ],
)
def test__load_yaml_config_parse_errors(tmp_path, content, exc_type, substr):
    """Non-mapping or YAML syntax errors raise ConfigParseError with context."""
    from saxoflow_agenticai.core import model_selector as sut

    sut._load_yaml_config.cache_clear()  # type: ignore[attr-defined]
    p = tmp_path / "weird.yaml"
    p.write_text(content, encoding="utf-8")

    with pytest.raises(getattr(sut, exc_type)) as ei:
        sut._load_yaml_config(p)
    assert substr in str(ei.value)


def test__merge_provider_overrides():
    """providers_meta in YAML can override base_url/headers."""
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {
        "providers_meta": {
            "openrouter": {
                "base_url": "https://alt.example/api/v1",
                "headers": {"X-Test": "1"},
            },
            "groq": {
                "base_url": "https://api.groq.com/openai/v2",
            },
        }
    }
    merged = sut._merge_provider_overrides(cfg)
    assert merged["openrouter"].base_url == "https://alt.example/api/v1"
    assert merged["openrouter"].headers == {"X-Test": "1"}
    assert merged["groq"].base_url == "https://api.groq.com/openai/v2"
    # Unmentioned providers unchanged
    assert merged["openai"].base_url is None


def test__autodetect_provider_priority(monkeypatch):
    """Autodetect chooses sole provider or honors priority when multiple."""
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {}
    merged = sut.PROVIDERS

    # No keys -> None
    for spec in merged.values():
        monkeypatch.delenv(spec.env, raising=False)
    assert sut._autodetect_provider(merged, cfg) is None

    # Single key -> that provider
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert sut._autodetect_provider(merged, cfg) == "groq"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    # Multiple -> priority prefers openrouter if present
    monkeypatch.setenv("OPENAI_API_KEY", "a")
    monkeypatch.setenv("OPENROUTER_API_KEY", "b")
    assert sut._autodetect_provider(merged, cfg) == "openrouter"


def test__is_disabled_and_alias_resolution():
    """Disabled checks and alias mapping behave as documented."""
    from saxoflow_agenticai.core import model_selector as sut

    assert sut._is_disabled("none", None) is True
    assert sut._is_disabled(None, "disabled") is True
    assert sut._is_disabled("", "") is False

    cfg = {"model_aliases": {"fast": {"groq": "mixtral-8x7b", "openai": "gpt-4o-mini"}}}
    assert sut._resolve_alias("fast", "groq", cfg) == "mixtral-8x7b"
    assert sut._resolve_alias("fast", "openai", cfg) == "gpt-4o-mini"
    assert sut._resolve_alias("gpt-4o", "openai", cfg) == "gpt-4o"  # passthrough


# --------------------------
# _resolve_provider_model coverage
# --------------------------

def _providers_map(sut):
    """Helper to get merged provider map without overrides."""
    return sut._merge_provider_overrides({})


def test_resolve_provider_model_precedence_args_over_env(monkeypatch):
    """
    Args take precedence over env/defaults; alias resolved per provider.
    """
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {
        "default_provider": "openai",
        "default_model": "gpt-4o",
        "model_aliases": {"fast": {"groq": "mixtral", "openai": "gpt-4o-mini"}},
    }
    prov, mdl = sut._resolve_provider_model(
        cfg, _providers_map(sut), agent_type=None, provider="groq", model_name="fast"
    )
    assert prov == "groq" and mdl == "mixtral"


def test_resolve_provider_model_env_overrides(monkeypatch):
    """SAXOFLOW_LLM_PROVIDER/MODEL are honored when args are absent."""
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {"default_provider": "openai", "default_model": "gpt-4o"}
    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SAXOFLOW_LLM_MODEL", "gpt-4o-mini")

    prov, mdl = sut._resolve_provider_model(
        cfg, _providers_map(sut), agent_type=None, provider=None, model_name=None
    )
    assert prov == "openai" and mdl == "gpt-4o-mini"


def test_resolve_provider_model_agent_models_applied(monkeypatch):
    """Agent-level block can provide provider & model."""
    from saxoflow_agenticai.core import model_selector as sut

    # Ensure env cannot override provider/model resolution for this test
    monkeypatch.delenv("SAXOFLOW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SAXOFLOW_LLM_MODEL", raising=False)

    cfg = {
        "agent_models": {"RTLGenAgent": {"provider": "groq", "model": "mixtral"}},
        "default_provider": "openai",
        "default_model": "gpt-4o",
    }
    prov, mdl = sut._resolve_provider_model(
        cfg, _providers_map(sut), agent_type="RTLGenAgent", provider=None, model_name=None
    )
    assert (prov, mdl) == ("groq", "mixtral")



def test_resolve_provider_model_autodetect_and_fallback(monkeypatch):
    """
    'auto' provider → autodetect via keys; if none detected and default_provider is set,
    it falls back to default; else falls back to 'openai'.
    """
    from saxoflow_agenticai.core import model_selector as sut

    # No keys present: default_provider is used when not auto/empty
    for spec in sut.PROVIDERS.values():
        monkeypatch.delenv(spec.env, raising=False)

    cfg = {"default_provider": "groq", "default_model": "mixtral"}
    prov, mdl = sut._resolve_provider_model(
        cfg, _providers_map(sut), agent_type=None, provider="auto", model_name="mixtral"
    )
    assert (prov, mdl) == ("groq", "mixtral")

    # No keys and default_provider is auto/empty -> 'openai'
    cfg2 = {"default_provider": "auto", "default_model": "gpt-4o"}
    prov2, mdl2 = sut._resolve_provider_model(
        cfg2, _providers_map(sut), agent_type=None, provider="auto", model_name="gpt-4o"
    )
    assert (prov2, mdl2) == ("openai", "gpt-4o")

    # Keys for openrouter present → prefer openrouter per priority
    monkeypatch.setenv("OPENROUTER_API_KEY", "X")
    cfg3 = {"default_model": "openrouter/model"}
    prov3, mdl3 = sut._resolve_provider_model(
        cfg3, _providers_map(sut), agent_type=None, provider="auto", model_name="openrouter/model"
    )
    assert prov3 == "openrouter"


def test_resolve_provider_model_unknown_and_missing_model():
    """Unknown provider or unresolved model produce clear errors."""
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {"default_provider": "openai", "default_model": "gpt-4o"}

    with pytest.raises(sut.ProviderResolutionError) as e1:
        sut._resolve_provider_model(cfg, _providers_map(sut), None, "notreal", "m")
    assert "Unsupported provider" in str(e1.value)

    with pytest.raises(sut.ProviderResolutionError) as e2:
        sut._resolve_provider_model({"providers": {}}, _providers_map(sut), None, "openai", "")
    assert "Model name could not be resolved" in str(e2.value)


# --------------------------
# Public API: get_model
# --------------------------

def test_get_model_openai_happy(monkeypatch):
    """
    Creates a ChatOpenAI client with configured params, no base_url (native OpenAI),
    and no headers when not provided.
    """
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {
        "default_provider": "openai",
        "default_model": "gpt-4o",
        "default_temperature": 0.1,
        "default_max_tokens": 1234,
        "default_timeout": 55,
        "default_max_retries": 5,
        "default_seed": 42,
    }
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SAXOFLOW_LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(sut.ModelSelector, "load_config", staticmethod(lambda: cfg), raising=True)
    monkeypatch.setattr(sut, "ChatOpenAI", FakeChatOpenAI, raising=True)

    client = sut.ModelSelector.get_model()
    assert isinstance(client, FakeChatOpenAI)
    kw = client.kwargs
    assert kw["api_key"] == "sk-openai"
    assert kw["base_url"] is None
    assert kw["model"] == "gpt-4o"
    assert kw["temperature"] == 0.1
    assert kw["max_tokens"] == 1234
    assert kw["timeout"] == 55
    assert kw["default_headers"] is None
    assert kw["max_retries"] == 5
    assert kw["seed"] == 42


def test_get_model_fallback_to_openrouter_when_key_missing(monkeypatch):
    """
    If selected provider has no API key and enable_fallback_to_openrouter=True,
    and OPENROUTER_API_KEY is present, it falls back and uses its base_url+headers.
    """
    from saxoflow_agenticai.core import model_selector as sut

    # Ensure env cannot force a different provider/model
    monkeypatch.delenv("SAXOFLOW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SAXOFLOW_LLM_MODEL", raising=False)

    cfg = {
        "default_provider": "groq",
        "default_model": "mixtral",
        "enable_fallback_to_openrouter": True,
        "providers": {"groq": {"model": "mixtral"}},
        "default_temperature": 0.2,
    }
    # No GROQ_API_KEY, but OPENROUTER_API_KEY present
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")

    monkeypatch.setattr(sut.ModelSelector, "load_config", staticmethod(lambda: cfg), raising=True)
    monkeypatch.setattr(sut, "ChatOpenAI", FakeChatOpenAI, raising=True)

    client = sut.ModelSelector.get_model()
    kw = client.kwargs
    assert kw["api_key"] == "sk-openrouter"
    assert kw["base_url"] == sut.PROVIDERS["openrouter"].base_url
    assert kw["default_headers"] == sut.PROVIDERS["openrouter"].headers
    assert kw["temperature"] == 0.2
    assert kw["model"] == "mixtral" or "openrouter" in kw["model"]  # allow aliasing


def test_get_model_missing_api_key_raises(monkeypatch):
    """
    When selected provider lacks API key and fallback not possible, raise MissingApiKeyError.
    """
    from saxoflow_agenticai.core import model_selector as sut

    # Ensure env cannot override provider/model
    monkeypatch.delenv("SAXOFLOW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SAXOFLOW_LLM_MODEL", raising=False)

    cfg = {"default_provider": "groq", "default_model": "mixtral", "enable_fallback_to_openrouter": False}
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    monkeypatch.setattr(sut.ModelSelector, "load_config", staticmethod(lambda: cfg), raising=True)

    with pytest.raises(sut.MissingApiKeyError):
        sut.ModelSelector.get_model()


def test_get_model_anthropic_not_installed_rewraps_failure(monkeypatch):
    """
    If provider kind is 'anthropic' but package not installed (_HAS_ANTHROPIC=False),
    get_model raises a wrapped RuntimeError message.
    """
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {
        "default_provider": "anthropic",
        "default_model": "claude-3",
        "providers": {"anthropic": {"model": "claude-3"}},
    }

    # Ensure env cannot override provider/model resolution
    monkeypatch.delenv("SAXOFLOW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SAXOFLOW_LLM_MODEL", raising=False)
    # (Optional) make it explicit anyway
    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SAXOFLOW_LLM_MODEL", "claude-3")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    monkeypatch.setattr(sut, "_HAS_ANTHROPIC", False, raising=True)
    monkeypatch.setattr(sut.ModelSelector, "load_config", staticmethod(lambda: cfg), raising=True)

    with pytest.raises(RuntimeError) as ei:
        sut.ModelSelector.get_model()
    assert "Failed to initialize model for provider 'anthropic'" in str(ei.value)


# --------------------------
# Public API: build_runnable / structured / tools
# --------------------------

def test_build_runnable_injects_system_prompt_and_config(monkeypatch):
    """
    build_runnable should call llm.bind(stop=None) and append config tags/metadata,
    while recording the system_prompt in metadata.
    """
    from saxoflow_agenticai.core import model_selector as sut

    fake = FakeLLM()
    monkeypatch.setattr(sut.ModelSelector, "get_model", classmethod(lambda cls, **kw: fake), raising=True)

    r = sut.ModelSelector.build_runnable(
        agent_type="RTLGenAgent",
        provider="openai",
        model_name="gpt-4o",
        system_prompt="You are RTLGen.",
        tags=["t1", "t2"],
        metadata={"m": 1},
        stream=False,
    )
    assert r is fake
    # First bind captured stop=None
    assert ("bind", {"stop": None}) in fake.bound
    # Config recorded with system_prompt merged
    assert fake.config["tags"] == ["t1", "t2"]
    assert fake.config["metadata"]["m"] == 1
    assert fake.config["metadata"]["system_prompt"] == "You are RTLGen."


def test_build_structured_pydantic_path(monkeypatch):
    """
    When _HAS_PYDANTIC=True and schema subclass of _PydanticModel, use with_structured_output.
    """
    from saxoflow_agenticai.core import model_selector as sut

    fake = FakeLLM()
    monkeypatch.setattr(sut.ModelSelector, "get_model", classmethod(lambda cls, **kw: fake), raising=True)

    # Fake a Pydantic base class and flag
    class _Base: ...
    class MySchema(_Base): ...
    monkeypatch.setattr(sut, "_HAS_PYDANTIC", True, raising=True)
    monkeypatch.setattr(sut, "_PydanticModel", _Base, raising=True)

    r = sut.ModelSelector.build_structured(
        schema=MySchema,
        agent_type="TBGenAgent",
        provider="openai",
        model_name="gpt-4o",
        strict=True,
        tags=["x"],
        metadata={"k": "v"},
    )
    assert r is fake
    assert fake.structured == ("structured", MySchema, True)
    assert fake.config == {"tags": ["x"], "metadata": {"k": "v"}}


def test_build_structured_json_path(monkeypatch):
    """
    When _HAS_PYDANTIC=False or schema is not a subclass, bind JSON response format path.
    """
    from saxoflow_agenticai.core import model_selector as sut

    fake = FakeLLM()
    monkeypatch.setattr(sut.ModelSelector, "get_model", classmethod(lambda cls, **kw: fake), raising=True)
    monkeypatch.setattr(sut, "_HAS_PYDANTIC", False, raising=True)

    r = sut.ModelSelector.build_structured(
        schema={"type": "object"},
        agent_type=None,
        provider="openai",
        model_name="gpt-4o",
        strict=False,
        tags=["a"],
        metadata={"b": 2},
    )
    assert r is fake
    # JSON response format implied by bind call
    assert ("bind", {"response_format": {"type": "json_object"}}) in fake.bound
    assert fake.config == {"tags": ["a"], "metadata": {"b": 2}}


def test_build_with_tools_binds_tools_and_choice(monkeypatch):
    """
    build_with_tools should call llm.bind_tools(tools) and optionally bind(tool_choice=...),
    plus attach tags/metadata in the config.
    """
    from saxoflow_agenticai.core import model_selector as sut

    fake = FakeLLM()
    monkeypatch.setattr(sut.ModelSelector, "get_model", classmethod(lambda cls, **kw: fake), raising=True)

    tools = [SimpleNamespace(name="t1"), SimpleNamespace(name="t2")]
    r = sut.ModelSelector.build_with_tools(
        tools=tools,
        agent_type="DebugAgent",
        provider="openai",
        model_name="gpt-4o",
        tool_choice="auto",
        tags=["d"],
        metadata={"m": "n"},
    )
    assert r is fake
    assert fake.tools == tools
    assert ("bind", {"tool_choice": "auto"}) in fake.bound
    assert fake.config == {"tags": ["d"], "metadata": {"m": "n"}}


# --------------------------
# Public API: get_provider_and_model
# --------------------------

def test_get_provider_and_model_read_from_config(monkeypatch):
    """
    Returns (provider, model) based on agent-level config + defaults.
    """
    from saxoflow_agenticai.core import model_selector as sut

    cfg = {
        "agent_models": {"ReportAgent": {"provider": "openrouter", "model": "meta/llama-3-8b"}},
        "default_provider": "openai",
        "default_model": "gpt-4o",
    }

    # Prevent env overrides from taking precedence over agent_models
    monkeypatch.delenv("SAXOFLOW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SAXOFLOW_LLM_MODEL", raising=False)

    monkeypatch.setattr(sut.ModelSelector, "load_config", staticmethod(lambda: cfg), raising=True)
    prov, mdl = sut.ModelSelector.get_provider_and_model(agent_type="ReportAgent")
    assert (prov, mdl) == ("openrouter", "meta/llama-3-8b")

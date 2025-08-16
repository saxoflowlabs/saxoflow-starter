# saxoflow_agenticai/core/model_selector.py
"""
Model selection layer for SaxoFlow Agentic AI.

This module standardizes access to multiple LLM providers. For OpenAI-compatible
providers we use `langchain-openai`'s ChatOpenAI; for native providers (Anthropic,
Gemini) we use their LangChain adapters when available.

Stable public API:
- ModelSelector.load_config()
- ModelSelector.get_model(...)                  # returns a LangChain chat model
- ModelSelector.get_provider_and_model(...)

Extras:
- ModelSelector.build_runnable(...)
- ModelSelector.build_structured(...)
- ModelSelector.build_with_tools(...)

Python: 3.9+
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

import yaml
from langchain_openai import ChatOpenAI
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

# Optional native providers (only needed if selected)
try:  # pragma: no cover - optional dependency at runtime
    from langchain_anthropic import ChatAnthropic  # type: ignore
    _HAS_ANTHROPIC = True
except Exception:  # pragma: no cover - keep selector import-safe
    _HAS_ANTHROPIC = False

try:  # pragma: no cover - optional dependency at runtime
    from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
    _HAS_GOOGLE = True
except Exception:  # pragma: no cover - keep selector import-safe
    _HAS_GOOGLE = False

# Optional import: only needed if you call build_structured() with Pydantic
try:  # pragma: no cover - optional dependency at runtime
    from pydantic import BaseModel as _PydanticModel  # type: ignore
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover - keep selector import-safe
    _HAS_PYDANTIC = False

__all__ = ["ModelSelector"]

# Module logger (quiet by default; CLI sets level via setup_logging)
logger = logging.getLogger("saxoflow_agenticai")


# ----------------------------
# Exceptions (explicit & clear)
# ----------------------------

class ConfigNotFoundError(FileNotFoundError):
    """Raised when model_config.yaml cannot be found."""


class ConfigParseError(RuntimeError):
    """Raised when model_config.yaml cannot be parsed."""


class ProviderResolutionError(ValueError):
    """Raised when a provider/model cannot be resolved from inputs/config."""


class MissingApiKeyError(RuntimeError):
    """Raised when the chosen provider's API key is not present in env."""


# ---------------------------------
# Provider metadata & global config
# ---------------------------------

@dataclass(frozen=True)
class ProviderSpec:
    """Specification for a provider.

    kind:
      - "openai"    OpenAI-compatible chat API (via ChatOpenAI)
      - "anthropic" Anthropic Claude (via ChatAnthropic)
      - "gemini"    Google Gemini (via ChatGoogleGenerativeAI)
    """
    env: str
    base_url: Optional[str]
    headers: Optional[Dict[str, str]] = None
    kind: str = "openai"  # default keeps prior behavior


# Registry of common providers.
# Extend safely by adding (env var, base_url, optional headers, kind).
PROVIDERS: Mapping[str, ProviderSpec] = {
    # Native OpenAI
    "openai": ProviderSpec(env="OPENAI_API_KEY", base_url=None, headers=None, kind="openai"),

    # Popular OpenAI-compatible endpoints
    "groq": ProviderSpec(env="GROQ_API_KEY", base_url="https://api.groq.com/openai/v1", kind="openai"),
    "fireworks": ProviderSpec(env="FIREWORKS_API_KEY", base_url="https://api.fireworks.ai/inference/v1", kind="openai"),
    "together": ProviderSpec(env="TOGETHER_API_KEY", base_url="https://api.together.xyz/v1", kind="openai"),
    "mistral": ProviderSpec(env="MISTRAL_API_KEY", base_url="https://api.mistral.ai/v1", kind="openai"),
    "perplexity": ProviderSpec(env="PPLX_API_KEY", base_url="https://api.perplexity.ai", kind="openai"),
    "deepseek": ProviderSpec(env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com", kind="openai"),
    # Qwen via DashScope (OpenAI-compatible mode)
    "dashscope": ProviderSpec(
        env="DASHSCOPE_API_KEY", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", kind="openai"
    ),

    # Universal gateway (Claude/Gemini/Qwen/DeepSeek/etc. through one key)
    "openrouter": ProviderSpec(
        env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        headers={"HTTP-Referer": "https://github.com/saxoflowlabs/saxoflow-starter"},
        kind="openai",
    ),

    # Native (non-OpenAI schema) providers
    "anthropic": ProviderSpec(env="ANTHROPIC_API_KEY", base_url=None, headers=None, kind="anthropic"),
    "gemini": ProviderSpec(env="GOOGLE_API_KEY", base_url=None, headers=None, kind="gemini"),
}

# Location of the YAML config relative to this file:
CONFIG_REL_PATH = Path(__file__).resolve().parents[1] / "config" / "model_config.yaml"


# ---------------
# Helper routines
# ---------------

@lru_cache(maxsize=1)
def _load_yaml_config(config_path: Path) -> dict:
    """
    Load and cache the model configuration YAML.

    Returns an empty dict if the file is empty.
    """
    if not config_path.exists():
        raise ConfigNotFoundError(f"Model config not found: {config_path}")

    try:
        text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ConfigParseError("model_config.yaml must parse to a mapping (YAML object).")
        logger.debug("Loaded model config from %s with keys: %s", config_path, list(data.keys()))
        return data
    except yaml.YAMLError as exc:
        raise ConfigParseError(f"Error parsing model_config.yaml: {exc}") from exc


def _merge_provider_overrides(config: dict) -> Mapping[str, ProviderSpec]:
    """
    Allow YAML to override provider base_url/headers without code changes.
    """
    merged: Dict[str, ProviderSpec] = dict(PROVIDERS)
    overrides = (config.get("providers_meta") or {})
    if not isinstance(overrides, dict):
        return merged

    out: Dict[str, ProviderSpec] = {}
    for name, spec in merged.items():
        patch = overrides.get(name) or {}
        out[name] = replace(
            spec,
            base_url=patch.get("base_url", spec.base_url),
            headers=patch.get("headers", spec.headers),
        )
    return out


def _autodetect_provider(providers: Mapping[str, ProviderSpec], config: dict) -> Optional[str]:
    """
    Choose a provider based on environment and optional priority.
    """
    present = [name for name, spec in providers.items() if os.getenv(spec.env)]
    if len(present) == 1:
        return present[0]
    if len(present) > 1:
        priority = config.get("autodetect_priority") or [
            "openrouter",
            "openai", "anthropic", "gemini",
            "groq", "mistral", "fireworks", "together",
            "perplexity", "deepseek", "dashscope",
        ]
        for p in priority:
            if p in present:
                return p
    return None


def _is_disabled(provider: Optional[str], model: Optional[str]) -> bool:
    """Support `provider: none|disabled` or `model: none|disabled`."""
    valp = (provider or "").strip().lower()
    valm = (model or "").strip().lower()
    return valp in {"none", "disabled"} or valm in {"none", "disabled"}


def _resolve_alias(model: str, provider: str, config: dict) -> str:
    """Map alias → provider-specific concrete model if configured."""
    aliases = config.get("model_aliases") or {}
    entry = aliases.get(model)
    if isinstance(entry, dict):
        concrete = entry.get(provider)
        if concrete:
            return concrete
    return model


def _resolve_provider_model(
    config: dict,
    providers_map: Mapping[str, ProviderSpec],
    agent_type: Optional[str],
    provider: Optional[str],
    model_name: Optional[str],
) -> Tuple[str, str]:
    """
    Resolve (provider, model) with precedence:
      1) function args
      2) ENV overrides: SAXOFLOW_LLM_PROVIDER / SAXOFLOW_LLM_MODEL
      3) agent_models.<agent>
      4) default_provider / default_model
      5) provider 'auto' -> autodetect from API keys (with priority)
      6) fallback to 'openai' if still unresolved
    """
    prov: Optional[str] = (provider or None)
    mdl: Optional[str] = (model_name or None)

    env_prov = os.getenv("SAXOFLOW_LLM_PROVIDER")
    env_model = os.getenv("SAXOFLOW_LLM_MODEL")
    if not prov and env_prov:
        prov = env_prov
    if not mdl and env_model:
        mdl = env_model

    if agent_type:
        agent_entry = (config.get("agent_models") or {}).get(agent_type, {}) or {}
        prov = prov or agent_entry.get("provider")
        mdl = mdl or agent_entry.get("model")

    if _is_disabled(prov, mdl):
        return "disabled", "disabled"

    prov = (prov or config.get("default_provider") or "auto").strip().lower()
    mdl = (mdl or config.get("default_model") or "auto").strip()

    if prov in {"auto", ""}:
        detected = _autodetect_provider(providers_map, config)
        default_prov = (config.get("default_provider") or "").strip().lower()
        if detected:
            prov = detected
        elif default_prov not in {"", "auto"}:
            prov = default_prov
        else:
            prov = "openai"

    if prov not in providers_map:
        known = ", ".join(sorted(providers_map.keys()))
        raise ProviderResolutionError(f"Unsupported provider: {prov}. Known: {known}")

    if mdl in {"auto", ""}:
        provider_block = (config.get("providers", {}) or {}).get(prov, {}) or {}
        mdl = provider_block.get("model") or config.get("default_model") or ""
    if not mdl:
        raise ProviderResolutionError(
            "Model name could not be resolved. "
            "Set it at the agent level, providers.<prov>.model, or as default_model."
        )

    mdl = _resolve_alias(mdl, prov, config)
    logger.debug("Resolved provider/model for agent '%s': %s / %s", agent_type, prov, mdl)
    return prov, mdl


def _resolve_params(
    config: dict,
    agent_type: Optional[str],
    prov: str,
) -> Dict[str, Any]:
    """
    Resolve generation params using precedence: agent > provider > global defaults.
    Includes timeout/max_tokens/temperature and optional max_retries/seed.
    """

    def get_param(name: str, default=None):
        if agent_type:
            agent_entry = (config.get("agent_models") or {}).get(agent_type, {}) or {}
            if name in agent_entry:
                return agent_entry[name]
        provider_block = (config.get("providers") or {}).get(prov, {}) or {}
        if name in provider_block:
            return provider_block[name]
        return config.get(f"default_{name}", default)

    return {
        "temperature": get_param("temperature", 0.3),
        "max_tokens": get_param("max_tokens", 8192),
        "timeout": get_param("timeout", 60),
        "max_retries": get_param("max_retries", 2),
        "seed": get_param("seed", None),
    }


# ---------------
# Public interface
# ---------------

class ModelSelector:
    """
    Multi-provider model selector.

    Priority to resolve (provider, model):
    1) Explicit function args
    2) Environment overrides
    3) Agent-level YAML
    4) YAML defaults
    5) Autodetect if provider is 'auto' (keys present)
    """

    @staticmethod
    def load_config() -> dict:
        """Load the LLM model configuration from YAML."""
        return _load_yaml_config(CONFIG_REL_PATH)

    @classmethod
    def get_model(
        cls,
        agent_type: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Build and return a configured LangChain chat model client.
        """
        config = cls.load_config()
        providers_map = _merge_provider_overrides(config)
        prov, mdl = _resolve_provider_model(
            config, providers_map, agent_type, provider, model_name
        )

        if prov == "disabled":
            raise ProviderResolutionError(
                f"Agent '{agent_type or ''}' is disabled for LLM use "
                "(provider/model set to none/disabled)."
            )

        params = _resolve_params(config, agent_type, prov)

        meta = providers_map[prov]
        api_key = os.getenv(meta.env)
        if not api_key:
            fallback_enabled = bool(config.get("enable_fallback_to_openrouter"))
            if fallback_enabled and prov != "openrouter":
                alt = providers_map.get("openrouter")
                if alt and os.getenv(alt.env):
                    logger.debug("Falling back to openrouter for agent '%s'", agent_type)
                    prov = "openrouter"
                    meta = alt
                    api_key = os.getenv(alt.env)

            if not api_key:
                raise MissingApiKeyError(
                    f"{prov} selected but {meta.env} is not set. "
                    f"Export {meta.env}=sk-*** (or configure a different provider)."
                )

        try:
            if meta.kind == "openai":
                client = ChatOpenAI(
                    api_key=api_key,
                    base_url=meta.base_url,   # None → native OpenAI
                    model=mdl,
                    temperature=params["temperature"],
                    max_tokens=params["max_tokens"],
                    timeout=params["timeout"],
                    default_headers=meta.headers or None,
                    max_retries=params["max_retries"],
                    seed=params["seed"],
                )
            elif meta.kind == "anthropic":
                if not _HAS_ANTHROPIC:
                    raise RuntimeError(
                        "langchain-anthropic is not installed. Install with:\n"
                        "  pip install -U langchain-anthropic anthropic"
                    )
                kwargs: Dict[str, Any] = {
                    "model": mdl,
                    "temperature": params["temperature"],
                    "max_retries": params["max_retries"],
                }
                if params["max_tokens"] is not None:
                    kwargs["max_tokens"] = int(params["max_tokens"])
                client = ChatAnthropic(**kwargs)  # type: ignore
            elif meta.kind == "gemini":
                if not _HAS_GOOGLE:
                    raise RuntimeError(
                        "langchain-google-genai is not installed. Install with:\n"
                        "  pip install -U langchain-google-genai google-generativeai"
                    )
                kwargs2: Dict[str, Any] = {
                    "model": mdl,
                    "temperature": params["temperature"],
                    "max_retries": params["max_retries"],
                }
                if params["max_tokens"] is not None:
                    kwargs2["max_output_tokens"] = int(params["max_tokens"])
                client = ChatGoogleGenerativeAI(**kwargs2)  # type: ignore
            else:
                raise ProviderResolutionError(f"Unsupported provider kind: {meta.kind}")
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to initialize model for provider '{prov}'") from exc

        logger.debug("Initialized %s client for provider=%s, model=%s", meta.kind, prov, mdl)
        return client

    @classmethod
    def build_runnable(
        cls,
        agent_type: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        *,
        system_prompt: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Runnable:
        """
        Return an LCEL Runnable for the chosen model, with optional system prompt,
        LangSmith tags/metadata, and streaming enabled.
        """
        llm = cls.get_model(agent_type=agent_type, provider=provider, model_name=model_name)

        config: Dict[str, Any] = {}
        if tags:
            config["tags"] = list(tags)
        if metadata:
            config["metadata"] = dict(metadata)

        runnable: Runnable = llm
        if system_prompt:
            runnable = llm.bind(stop=None)
            config.setdefault("metadata", {})["system_prompt"] = system_prompt

        if stream:
            pass

        return runnable.with_config(config)

    @classmethod
    def build_structured(
        cls,
        schema: Union[type, Dict[str, Any]],
        agent_type: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        *,
        strict: bool = True,
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Runnable:
        """
        Return a Runnable that enforces structured output.
        """
        llm = cls.get_model(agent_type=agent_type, provider=provider, model_name=model_name)

        if _HAS_PYDANTIC and isinstance(schema, type) and issubclass(schema, _PydanticModel):
            runnable = llm.with_structured_output(schema=schema, strict=strict)
        else:
            runnable = llm.bind(response_format={"type": "json_object"})

        config: Dict[str, Any] = {}
        if tags:
            config["tags"] = list(tags)
        if metadata:
            config["metadata"] = dict(metadata)
        return runnable.with_config(config)

    @classmethod
    def build_with_tools(
        cls,
        tools: Sequence[BaseTool],
        agent_type: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        *,
        tool_choice: Optional[str] = None,  # "auto", "none", or specific tool
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Runnable:
        """
        Return a Runnable configured for tool calling.
        """
        llm = cls.get_model(agent_type=agent_type, provider=provider, model_name=model_name)
        runnable = llm.bind_tools(tools)
        if tool_choice:
            runnable = runnable.bind(tool_choice=tool_choice)

        config: Dict[str, Any] = {}
        if tags:
            config["tags"] = list(tags)
        if metadata:
            config["metadata"] = dict(metadata)
        return runnable.with_config(config)

    @classmethod
    def get_provider_and_model(cls, agent_type: Optional[str] = None) -> Tuple[str, str]:
        """Resolve and return (provider, model) for the given agent_type."""
        cfg = cls.load_config()
        providers_map = _merge_provider_overrides(cfg)
        prov, mdl = _resolve_provider_model(
            cfg, providers_map, agent_type, provider=None, model_name=None
        )
        logger.debug("get_provider_and_model(%s) -> (%s, %s)", agent_type, prov, mdl)
        return prov, mdl

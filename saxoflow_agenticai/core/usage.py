"""Token usage schema and extraction helpers for LLM response metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


class UsageSchemaError(ValueError):
    """Raised when usage payload fields are malformed."""


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise UsageSchemaError(f"Usage field `{field_name}` must be a mapping.")
    return dict(value)


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise UsageSchemaError(f"Usage field `{field_name}` must be a non-empty string when set.")
    return value.strip()


def _optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise UsageSchemaError(f"Usage field `{field_name}` must be an integer when set.") from exc
    if parsed < 0:
        raise UsageSchemaError(f"Usage field `{field_name}` must be non-negative when set.")
    return parsed


def _optional_float(value: Any, field_name: str) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise UsageSchemaError(f"Usage field `{field_name}` must be numeric when set.") from exc
    if parsed < 0:
        raise UsageSchemaError(f"Usage field `{field_name}` must be non-negative when set.")
    return parsed


def _safe_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class LLMUsage:
    """Normalized token usage metadata for one LLM call."""

    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cost_estimate: Optional[float] = None
    raw_usage: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LLMUsage":
        data = _as_mapping(raw, "usage")

        prompt_tokens = _optional_int(data.get("prompt_tokens"), "usage.prompt_tokens")
        completion_tokens = _optional_int(
            data.get("completion_tokens"), "usage.completion_tokens"
        )
        total_tokens = _optional_int(data.get("total_tokens"), "usage.total_tokens")
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        raw_usage = data.get("raw_usage")
        if raw_usage is None:
            raw_usage = {}
        if not isinstance(raw_usage, Mapping):
            raise UsageSchemaError("Usage field `usage.raw_usage` must be a mapping when set.")

        return cls(
            provider=_optional_string(data.get("provider"), "usage.provider"),
            model=_optional_string(data.get("model"), "usage.model"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=_optional_int(data.get("cached_tokens"), "usage.cached_tokens"),
            reasoning_tokens=_optional_int(
                data.get("reasoning_tokens"), "usage.reasoning_tokens"
            ),
            cost_estimate=_optional_float(data.get("cost_estimate"), "usage.cost_estimate"),
            raw_usage=dict(raw_usage),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "raw_usage": dict(self.raw_usage),
        }
        if self.provider is not None:
            data["provider"] = self.provider
        if self.model is not None:
            data["model"] = self.model
        if self.prompt_tokens is not None:
            data["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            data["completion_tokens"] = self.completion_tokens
        if self.total_tokens is not None:
            data["total_tokens"] = self.total_tokens
        if self.cached_tokens is not None:
            data["cached_tokens"] = self.cached_tokens
        if self.reasoning_tokens is not None:
            data["reasoning_tokens"] = self.reasoning_tokens
        if self.cost_estimate is not None:
            data["cost_estimate"] = self.cost_estimate
        return data


@dataclass(frozen=True)
class LLMResultEnvelope:
    """Structured return envelope that preserves text and metadata."""

    text: str
    usage: Optional[LLMUsage] = None
    response_metadata: Mapping[str, Any] = field(default_factory=dict)
    model_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "usage": self.usage.to_dict() if self.usage is not None else None,
            "response_metadata": dict(self.response_metadata),
            "model_metadata": dict(self.model_metadata),
        }


def extract_usage(
    result: Any,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[LLMUsage]:
    """Extract normalized usage from common LangChain/provider result metadata."""
    usage_metadata = _safe_mapping(getattr(result, "usage_metadata", None))
    response_metadata = _safe_mapping(getattr(result, "response_metadata", None))
    additional_kwargs = _safe_mapping(getattr(result, "additional_kwargs", None))

    token_usage = _safe_mapping(response_metadata.get("token_usage"))
    if not token_usage:
        token_usage = _safe_mapping(response_metadata.get("usage"))
    if not token_usage:
        token_usage = _safe_mapping(additional_kwargs.get("usage"))

    prompt_tokens = usage_metadata.get("input_tokens")
    if prompt_tokens is None:
        prompt_tokens = token_usage.get("prompt_tokens")

    completion_tokens = usage_metadata.get("output_tokens")
    if completion_tokens is None:
        completion_tokens = token_usage.get("completion_tokens")

    total_tokens = usage_metadata.get("total_tokens")
    if total_tokens is None:
        total_tokens = token_usage.get("total_tokens")

    cached_tokens = usage_metadata.get("cached_tokens")
    if cached_tokens is None:
        cached_tokens = token_usage.get("cached_tokens")

    reasoning_tokens = usage_metadata.get("reasoning_tokens")
    if reasoning_tokens is None:
        reasoning_tokens = token_usage.get("reasoning_tokens")

    raw_usage: Dict[str, Any] = {}
    if usage_metadata:
        raw_usage["usage_metadata"] = usage_metadata
    if token_usage:
        raw_usage["token_usage"] = token_usage

    if (
        prompt_tokens is None
        and completion_tokens is None
        and total_tokens is None
        and cached_tokens is None
        and reasoning_tokens is None
    ):
        return None

    resolved_provider = provider or response_metadata.get("provider")
    resolved_model = model or response_metadata.get("model_name") or response_metadata.get("model")

    return LLMUsage.from_mapping(
        {
            "provider": resolved_provider,
            "model": resolved_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
            "raw_usage": raw_usage,
        }
    )


def envelope_from_result(
    result: Any,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMResultEnvelope:
    """Build an envelope from a LangChain-like result object."""
    content = getattr(result, "content", None)
    if isinstance(content, str):
        text = content.strip()
    else:
        text_attr = getattr(result, "text", None)
        if isinstance(text_attr, str):
            text = text_attr.strip()
        elif isinstance(result, str):
            text = result.strip()
        else:
            text = str(result).strip()

    response_metadata = _safe_mapping(getattr(result, "response_metadata", None))
    model_metadata = {
        "provider": provider,
        "model": model or response_metadata.get("model_name") or response_metadata.get("model"),
    }
    usage = extract_usage(result, provider=provider, model=model)
    return LLMResultEnvelope(
        text=text,
        usage=usage,
        response_metadata=response_metadata,
        model_metadata=model_metadata,
    )

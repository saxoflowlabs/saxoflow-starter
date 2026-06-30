"""Tests for Phase 3 token usage schema and fake-message extraction."""

from __future__ import annotations


def test_llm_usage_validates_and_normalizes_totals():
    from saxoflow_agenticai.core.usage import LLMUsage

    usage = LLMUsage.from_mapping(
        {
            "provider": "openai",
            "model": "gpt-5",
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "raw_usage": {"source": "fake"},
        }
    )

    assert usage.provider == "openai"
    assert usage.model == "gpt-5"
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 25
    assert usage.total_tokens == 125
    assert usage.raw_usage == {"source": "fake"}


def test_extract_usage_from_usage_metadata_fake_message():
    from saxoflow_agenticai.core.usage import extract_usage

    class FakeMessage:
        content = "ok"
        usage_metadata = {"input_tokens": 40, "output_tokens": 12, "total_tokens": 52}
        response_metadata = {"model_name": "gpt-5-mini"}

    usage = extract_usage(FakeMessage(), provider="openai")

    assert usage is not None
    assert usage.provider == "openai"
    assert usage.model == "gpt-5-mini"
    assert usage.prompt_tokens == 40
    assert usage.completion_tokens == 12
    assert usage.total_tokens == 52


def test_extract_usage_from_response_token_usage_fake_message():
    from saxoflow_agenticai.core.usage import extract_usage

    class FakeMessage:
        content = "ok"
        response_metadata = {
            "model_name": "claude-test",
            "token_usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
        }

    usage = extract_usage(FakeMessage(), provider="anthropic")

    assert usage is not None
    assert usage.provider == "anthropic"
    assert usage.model == "claude-test"
    assert usage.prompt_tokens == 30
    assert usage.completion_tokens == 20
    assert usage.total_tokens == 50


def test_envelope_from_result_preserves_text_and_usage():
    from saxoflow_agenticai.core.usage import envelope_from_result

    class FakeMessage:
        content = " hello "
        usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        response_metadata = {"model_name": "gpt-5-nano"}

    envelope = envelope_from_result(FakeMessage(), provider="openai")

    assert envelope.text == "hello"
    assert envelope.usage is not None
    assert envelope.usage.total_tokens == 15
    assert envelope.model_metadata["provider"] == "openai"
    assert envelope.model_metadata["model"] == "gpt-5-nano"


def test_extract_usage_returns_none_when_unavailable():
    from saxoflow_agenticai.core.usage import extract_usage

    class FakeMessage:
        content = "no usage"
        response_metadata = {"model_name": "unknown"}

    usage = extract_usage(FakeMessage())
    assert usage is None

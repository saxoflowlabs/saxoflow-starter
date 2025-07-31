"""
Tests for saxoflow_agenticai.core.model_selector.

These tests validate that the ModelSelector class can locate the
configuration file and returns the expected provider/model pairs for
known agent keys.  The YAML file included in the repository is used
directly.
"""

import yaml

from saxoflow_agenticai.core.model_selector import ModelSelector


def test_get_provider_and_model_returns_defaults():
    # For an agent with explicit mapping
    prov, model = ModelSelector.get_provider_and_model("rtlgen")
    assert prov == "groq"
    assert model.startswith("llama3")
    # For an unknown agent type, fall back to defaults in config
    prov2, model2 = ModelSelector.get_provider_and_model("unknownagent")
    # Should return default provider and model from config
    assert prov2 == "groq"
    assert model2.startswith("llama3")
# """
# Tests for saxoflow_agenticai.core.model_selector.

# These tests validate that the ModelSelector class can locate the
# configuration file and returns the expected provider/model pairs for
# known agent keys.  The YAML file included in the repository is used
# directly.
# """

# import yaml
# import os
# import pytest
# from unittest import mock
# from saxoflow_agenticai.core.model_selector import ModelSelector

# def test_get_provider_and_model_returns_defaults():
#     # For an agent with explicit mapping
#     prov, model = ModelSelector.get_provider_and_model("rtlgen")
#     assert prov == "groq"
#     assert model.startswith("llama3")
#     # For an unknown agent type, fall back to defaults in config
#     prov2, model2 = ModelSelector.get_provider_and_model("unknownagent")
#     # Should return default provider and model from config
#     assert prov2 == "groq"
#     assert model2.startswith("llama3")


# def test_get_provider_and_model_known_and_unknown(monkeypatch):
#     # Already covered, but here for completeness
#     prov, model = ModelSelector.get_provider_and_model("rtlgen")
#     assert isinstance(prov, str) and prov
#     assert isinstance(model, str) and model
#     prov2, model2 = ModelSelector.get_provider_and_model("doesnotexist")
#     assert isinstance(prov2, str) and prov2
#     assert isinstance(model2, str) and model2


# def test_get_provider_and_model_missing_agent(monkeypatch):
#     # Should still return default
#     prov, model = ModelSelector.get_provider_and_model()
#     assert isinstance(prov, str)
#     assert isinstance(model, str)


# def test_load_config_file_not_found(monkeypatch):
#     monkeypatch.setattr(ModelSelector, "load_config", staticmethod(lambda: (_ for _ in ()).throw(FileNotFoundError())))
#     with pytest.raises(FileNotFoundError):
#         ModelSelector.get_provider_and_model("rtlgen")


# def test_load_config_yaml_parse_error(monkeypatch):
#     def fake_load_config():
#         raise RuntimeError("Error parsing model_config.yaml: bad format")
#     monkeypatch.setattr(ModelSelector, "load_config", staticmethod(fake_load_config))
#     with pytest.raises(RuntimeError):
#         ModelSelector.get_provider_and_model("rtlgen")


# def test_get_model_raises_for_unknown_provider(monkeypatch):
#     # Patch load_config to return unknown provider
#     monkeypatch.setattr(ModelSelector, "load_config", staticmethod(lambda: {
#         "agent_models": {"rtlgen": {"provider": "nonesuch", "model": "fake-model"}},
#         "default_provider": "groq",
#         "providers": {},
#     }))
#     with pytest.raises(ValueError):
#         ModelSelector.get_model("rtlgen")


# def test_get_model_uses_explicit_provider_and_model(monkeypatch):
#     # Patch all provider classes to dummy
#     with mock.patch("saxoflow_agenticai.core.model_selector.ChatGroq", autospec=True) as cg:
#         monkeypatch.setattr(ModelSelector, "load_config", staticmethod(lambda: {
#             "providers": {"groq": {"model": "llama3", "temperature": 0.2}},
#             "default_provider": "groq"
#         }))
#         os.environ["GROQ_API_KEY"] = "dummy"
#         m = ModelSelector.get_model(provider="groq", model_name="llama3")
#         cg.assert_called_once()


# def test_get_model_parameter_fallbacks(monkeypatch):
#     # Should find temperature/max_tokens in all levels
#     config = {
#         "agent_models": {
#             "rtlgen": {"provider": "groq", "model": "llama3", "temperature": 0.33, "max_tokens": 101},
#         },
#         "providers": {
#             "groq": {"model": "llama3", "temperature": 0.22, "max_tokens": 202},
#         },
#         "default_provider": "groq",
#         "default_temperature": 0.11,
#         "default_max_tokens": 303
#     }
#     # Use a dummy ChatGroq
#     with mock.patch("saxoflow_agenticai.core.model_selector.ChatGroq", autospec=True) as cg:
#         monkeypatch.setattr(ModelSelector, "load_config", staticmethod(lambda: config))
#         os.environ["GROQ_API_KEY"] = "dummy"
#         ModelSelector.get_model(agent_type="rtlgen")
#         # Should prefer agent-level params over provider-level and default


# def test_get_model_all_supported_providers(monkeypatch):
#     # Should try to instantiate all supported providers
#     config = {
#         "providers": {
#             "groq": {"model": "llama3"},
#             "fireworks": {"model": "fireworks-model"},
#             "together": {"model": "together-model"},
#             "mistral": {"model": "mistral-model"},
#         },
#         "default_provider": "groq"
#     }
#     # Patch all provider classes to dummy
#     with mock.patch("saxoflow_agenticai.core.model_selector.ChatGroq", autospec=True) as cg, \
#          mock.patch("saxoflow_agenticai.core.model_selector.ChatFireworks", autospec=True) as cf, \
#          mock.patch("saxoflow_agenticai.core.model_selector.ChatTogether", autospec=True) as ct, \
#          mock.patch("saxoflow_agenticai.core.model_selector.ChatMistralAI", autospec=True) as cm:
#         monkeypatch.setattr(ModelSelector, "load_config", staticmethod(lambda: config))
#         os.environ["GROQ_API_KEY"] = "dummy"
#         os.environ["FIREWORKS_API_KEY"] = "dummy"
#         os.environ["TOGETHER_API_KEY"] = "dummy"
#         os.environ["MISTRAL_API_KEY"] = "dummy"
#         ModelSelector.get_model(provider="groq", model_name="llama3")
#         ModelSelector.get_model(provider="fireworks", model_name="fireworks-model")
#         ModelSelector.get_model(provider="together", model_name="together-model")
#         ModelSelector.get_model(provider="mistral", model_name="mistral-model")
#         cg.assert_called()
#         cf.assert_called()
#         ct.assert_called()
#         cm.assert_called()

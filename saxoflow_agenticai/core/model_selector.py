import yaml
import os

from langchain_groq import ChatGroq
from langchain_fireworks import ChatFireworks
from langchain_together import ChatTogether
# from langchain_openrouter import ChatOpenRouter
# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI
# Optionally: from langchain_openai import ChatOpenAI
# Optionally: from langchain_huggingface import ChatHuggingFace

class ModelSelector:
    @staticmethod
    def load_config() -> dict:
        """Load the LLM model configuration from YAML."""
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'config', 'model_config.yaml'
        )
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Model config not found: {config_path}")
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error parsing model_config.yaml: {e}")

    @classmethod
    def get_model(cls, agent_type: str = None, provider: str = None, model_name: str = None):
        """
        Returns a LangChain LLM instance configured for the given agent,
        supporting temperature and max_tokens configuration.
        """
        config = cls.load_config()

        # --- Select provider and model (same logic as before) ---
        if provider and model_name:
            prov = provider.lower()
            modl = model_name
        else:
            agent_entry = config.get("agent_models", {}).get(agent_type, {}) if agent_type else {}
            prov = agent_entry.get("provider")
            modl = agent_entry.get("model")

            if not prov:
                prov = config.get("default_provider", "groq")
            prov = prov.lower()

            if not modl:
                modl = config.get("providers", {}).get(prov, {}).get("model")
                if not modl:
                    modl = config.get("default_model")

        # --- Find temperature/max_tokens (agent > provider > global default) ---
        def get_param(param_name, default=None):
            # 1. Agent-level
            if agent_type:
                agent_entry = config.get("agent_models", {}).get(agent_type, {})
                if param_name in agent_entry:
                    return agent_entry[param_name]
            # 2. Provider-level
            provider_entry = config.get("providers", {}).get(prov, {})
            if param_name in provider_entry:
                return provider_entry[param_name]
            # 3. Global default
            key = f"default_{param_name}"
            if key in config:
                return config[key]
            # 4. Fallback
            return default

        temperature = get_param("temperature", 0.3)
        max_tokens = get_param("max_tokens", 8192)

        # Remove model from param dict if present (avoid double-passing)
        params = {
            "model": modl,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # --- LangChain LLM Integration with parameters ---
        if prov == "groq":
            return ChatGroq(
                api_key=os.getenv("GROQ_API_KEY"),
                **params
            )
        elif prov == "fireworks":
            return ChatFireworks(
                api_key=os.getenv("FIREWORKS_API_KEY"),
                **params
            )
        elif prov == "together":
            return ChatTogether(
                api_key=os.getenv("TOGETHER_API_KEY"),
                **params
            )
        # elif prov == "openrouter":
        #     return ChatOpenRouter(
        #         api_key=os.getenv("OPENROUTER_API_KEY"),
        #         **params
        #     )
        # elif prov == "googleaistudio":
        #     return ChatGoogleGenerativeAI(
        #         api_key=os.getenv("GOOGLEAISTUDIO_API_KEY"),
        #         **params
        #     )
        elif prov == "mistral":
            return ChatMistralAI(
                api_key=os.getenv("MISTRAL_API_KEY"),
                **params
            )
        # elif prov == "openai":
        #     return ChatOpenAI(
        #         api_key=os.getenv("OPENAI_API_KEY"),
        #         **params
        #     )
        # elif prov == "huggingface":
        #     return ChatHuggingFace(
        #         api_key=os.getenv("HUGGINGFACE_API_KEY"),
        #         **params
        #     )
        else:
            raise ValueError(f"Unsupported provider: {prov}")

    @classmethod
    def get_provider_and_model(cls, agent_type: str = None):
        """Returns (provider, model_name) for a given agent_type."""
        config = cls.load_config()
        agent_entry = config.get("agent_models", {}).get(agent_type, {}) if agent_type else {}
        prov = agent_entry.get("provider")
        modl = agent_entry.get("model")
        if not prov:
            prov = config.get("default_provider", "groq")
        if not modl:
            modl = config.get("providers", {}).get(prov, {}).get("model")
            if not modl:
                modl = config.get("default_model")
        return prov, modl

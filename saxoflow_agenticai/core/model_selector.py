import yaml
import os

from langchain_groq import ChatGroq
from langchain_fireworks import ChatFireworks
from langchain_together import ChatTogether
from langchain_openrouter import OpenRouterLLM
from langchain_google_genai import ChatGoogleGenerativeAI
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
        Returns a LangChain LLM instance configured for the given agent.
        """
        config = cls.load_config()

        # Highest priority: explicit override
        if provider and model_name:
            prov = provider.lower()
            modl = model_name
        else:
            # Agent-level mapping
            agent_entry = config.get("agent_models", {}).get(agent_type, {}) if agent_type else {}
            prov = agent_entry.get("provider")
            modl = agent_entry.get("model")

            # Provider-level default
            if not prov:
                prov = config.get("default_provider", "groq")
            prov = prov.lower()

            if not modl:
                modl = config.get("providers", {}).get(prov, {}).get("model")
                if not modl:
                    modl = config.get("default_model")

        # LangChain LLM Integration
        if prov == "groq":
            return ChatGroq(
                model=modl,
                api_key=os.getenv("GROQ_API_KEY")
            )
        elif prov == "fireworks":
            return ChatFireworks(
                model=modl,
                api_key=os.getenv("FIREWORKS_API_KEY")
            )
        elif prov == "together":
            return ChatTogether(
                model=modl,
                api_key=os.getenv("TOGETHER_API_KEY")
            )
        elif prov == "openrouter":
            return ChatOpenRouter(
                model=modl,
                api_key=os.getenv("OPENROUTER_API_KEY")
            )
        elif prov == "googleaistudio":
            return ChatGoogleGenerativeAI(
                model=modl,
                api_key=os.getenv("GOOGLEAISTUDIO_API_KEY")
            )
        elif prov == "mistral":
            return ChatMistralAI(
                model=modl,
                api_key=os.getenv("MISTRAL_API_KEY")
            )
        # === Uncomment and complete as needed for OpenAI, HF, etc. ===
        # elif prov == "openai":
        #     return ChatOpenAI(
        #         model=modl,
        #         api_key=os.getenv("OPENAI_API_KEY")
        #     )
        # elif prov == "huggingface":
        #     return ChatHuggingFace(
        #         model=modl,
        #         api_key=os.getenv("HUGGINGFACE_API_KEY")
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

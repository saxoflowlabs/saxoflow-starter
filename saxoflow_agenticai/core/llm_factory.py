import os
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_fireworks import ChatFireworks
from langchain_together import ChatTogether
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI

def get_llm_from_config(agent_type: str, config: dict):
    agent_models = config.get("agent_models", {})
    providers = config.get("providers", {})
    provider = agent_models.get(agent_type, {}).get("provider", config.get("default_provider", "groq"))
    model = agent_models.get(agent_type, {}).get("model", providers.get(provider, {}).get("model"))

    # Dispatch provider to proper LangChain class
    if provider == "groq":
        return ChatGroq(model=model, api_key=os.environ.get("GROQ_API_KEY"))
    elif provider == "openai":
        return ChatOpenAI(model=model, api_key=os.environ.get("OPENAI_API_KEY"))
    elif provider == "fireworks":
        return ChatFireworks(model=model, api_key=os.environ.get("FIREWORKS_API_KEY"))
    elif provider == "together":
        return ChatTogether(model=model, api_key=os.environ.get("TOGETHER_API_KEY"))
    elif provider == "googleaistudio":
        return ChatGoogleGenerativeAI(model=model, google_api_key=os.environ.get("GOOGLEAISTUDIO_API_KEY"))
    elif provider == "mistral":
        return ChatMistralAI(model=model, api_key=os.environ.get("MISTRAL_API_KEY"))
    # Add more as needed
    else:
        raise ValueError(f"Unsupported provider: {provider}")

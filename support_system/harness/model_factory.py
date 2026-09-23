# harness/model_factory.py
#
# Model-agnostic LLM factory for the multi-agent support system.
#
# Responsibility:
#   Resolves "which model backs which agent" at runtime from configuration,
#   and returns a ready-to-use LLM client. This is the single place in the
#   codebase where model selection decisions are made — no agent graph
#   hard-codes a specific model or provider.
#
# Why this exists:
#   A core architectural requirement is that any agent's backing model
#   (including local Ollama models) must be swappable independently via
#   config, without code changes. This factory fulfils that requirement.
#
# Supported providers (to be implemented):
#   - Ollama          — local models (default; zero external dependency)
#   - OpenAI          — hosted GPT models (optional add-on)
#   - Anthropic       — hosted Claude models (optional add-on)
#   - Google          — hosted Gemini models (optional add-on)
#   [Additional providers added via a common adapter interface]
#
# Configuration:
#   Loaded from the subagent_registry.yaml (or equivalent env/config file).
#   Each agent has an entry specifying its provider + model name, e.g.:
#     orchestrator:  { provider: ollama, model: llama3 }
#     action_agent:  { provider: openai, model: gpt-4o-mini }
#
# Cost optimisation hook:
#   The factory can implement a "tiered" strategy — lightweight/cheap models
#   for classification/routing calls, higher-capability models for final
#   synthesis. This is configurable per agent, not hard-coded.
#
# Failover:
#   On provider error (e.g. rate limit / 429), the Model Router falls back to
#   a configured backup model (typically a local Ollama model) for that agent
#   so a provider outage doesn't cause a full system outage.
#
# Secret handling:
#   API keys are NEVER passed into or returned from this factory at the LLM
#   context level. They are loaded server-side from environment variables /
#   Docker secrets and injected at the adapter layer only.

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import ChatHuggingFace
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_aws import ChatBedrock
from langchain_groq import ChatGroq

import yaml

PROVIDERS = {
    "ollama": ChatOllama,
    "openai": ChatOpenAI,
    "anthropic": ChatAnthropic,
    "google-genai": ChatGoogleGenerativeAI,
    "huggingface": ChatHuggingFace,
    "nvidia": ChatNVIDIA,
    "aws": ChatBedrock,
    "groq": ChatGroq,
}

def load_config(path: str = "./subagent_registry.yaml") -> dict:
    """
    Load and parse the subagent_registry.yaml file.
    """
    with open(path, 'r') as f:
        return yaml.safe_load(f)

#TODO: implement model fallback


def build_model(agent_config: dict):
    """
    Instantiate and return a ready-to-use LLM instance based on the provided configuration.
    
    Args:
        agent_config (dict): Configuration dictionary containing parameters like 'provider', 
                             'model', and 'temperature', typically loaded from the registry.
                             
    Returns:
        An instantiated LangChain chat model object (e.g., ChatOllama) ready for invocation.
        
    Raises:
        ValueError: If the specified provider is not supported.
    """
    provider = agent_config.get("provider")
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}. Available providers: {list(PROVIDERS.keys())}")

    model_class = PROVIDERS[provider]

    known_keys = {"provider", "model", "temperature", "tools", "api_key"}
    extra_kwargs = {k:v for k,v in agent_config.items() if k not in known_keys}
    
    model_name = agent_config.get("model")
    if model_name is None:
        raise ValueError("The 'model' key is required in the agent configuration.")
        
    kwargs = {
        "model": model_name,
        "temperature": agent_config.get("temperature", 0.7),
        **extra_kwargs
    }
    
    api_key = agent_config.get("api_key")
    if api_key:
        kwargs["api_key"] = api_key

    return model_class(**kwargs)


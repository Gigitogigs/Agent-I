# backend/core/providers.py

PROVIDER_CATALOG = {
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307", "claude-3-opus-20240229"],
        "requires_key": True
    },
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "requires_key": True
    },
    "ollama": {
        "name": "Ollama (Local)",
        "models": ["llama3", "mistral", "phi3"],
        "requires_key": False
    },
    "google-genai": {
        "name": "Google GenAI",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash"],
        "requires_key": True
    }
}

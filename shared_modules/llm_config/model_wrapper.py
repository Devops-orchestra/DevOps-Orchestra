import os
import requests

# Groq API endpoint
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Get API key from environment variable (GitHub Secrets in this case)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Model name explicitly set to llama-3.3-70b-versatile
DEFAULT_MODEL = "llama-3.3-70b-versatile"

def run_prompt(prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.7, max_tokens: int = 1024) -> str:
    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY not found in environment variables.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    response = requests.post(GROQ_API_URL, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

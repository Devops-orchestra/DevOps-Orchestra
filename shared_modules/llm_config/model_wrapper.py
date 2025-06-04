"""
model_wrapper.py

This module provides a wrapper function to interact with the Groq API for generating
chat-based completions using LLMs such as `llama-3.3-70b-versatile`.

It includes:
- `run_prompt`: A utility function that sends a prompt to the Groq API and returns the model-generated response.
- Centralized logging using the DevOpsOrchestra logger.
- Environment variable check for `GROQ_API_KEY`.

Intended for use within LangGraph or Kafka-driven agents for tasks like code analysis,
test generation, or other AI-driven DevOps workflows.
"""

import os
import requests
from shared_modules.utils.logger import logger  

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEFAULT_MODEL = "llama-3.3-70b-versatile"

def run_prompt(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 1024
) -> str:
    """
    Sends a prompt to the Groq API chat completion endpoint and returns the generated response text.

    Args:
        prompt (str): The user prompt to send.
        model (str): Model name to use (default: llama-3.3-70b-versatile).
        temperature (float): Sampling temperature for generation.
        max_tokens (int): Maximum tokens in generated completion.

    Returns:
        str: The generated completion text from the model.

    Raises:
        EnvironmentError: If GROQ_API_KEY is not set.
        requests.HTTPError: For non-200 HTTP responses.
        KeyError: If response JSON structure is unexpected.
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not found in environment variables.")
        raise EnvironmentError("GROQ_API_KEY not found in environment variables.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    logger.info(f"Sending prompt to model '{model}' with temperature={temperature} and max_tokens={max_tokens}")

    response = requests.post(GROQ_API_URL, headers=headers, json=payload)
    response.raise_for_status()

    json_response = response.json()
    try:
        content = json_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected response format: {e}")
        raise KeyError("Unexpected response format from Groq API") from e

    logger.info("Received successful response from Groq API.")
    return content

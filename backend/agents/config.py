"""OpenRouter LLM and Composio configuration."""

import os

from config import settings

LLM_MODEL = settings.LLM_MODEL
OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY
COMPOSIO_API_KEY = settings.COMPOSIO_API_KEY

# Ensure API keys are in os.environ
if OPENROUTER_API_KEY:
    os.environ.setdefault("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
if COMPOSIO_API_KEY:
    os.environ.setdefault("COMPOSIO_API_KEY", COMPOSIO_API_KEY)

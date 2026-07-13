"""Tests for agents config module."""

import os
import pytest


def test_llm_model_is_set():
    """LLM model should be a non-empty string from settings."""
    from agents.config import LLM_MODEL
    assert isinstance(LLM_MODEL, str)
    assert len(LLM_MODEL) > 0
    assert "gemini" in LLM_MODEL


def test_config_reads_openrouter_api_key(monkeypatch):
    """OPENROUTER_API_KEY should be read from settings."""
    from agents.config import OPENROUTER_API_KEY
    assert isinstance(OPENROUTER_API_KEY, str)


def test_config_reads_composio_api_key(monkeypatch):
    """COMPOSIO_API_KEY should be read from settings."""
    from agents.config import COMPOSIO_API_KEY
    assert isinstance(COMPOSIO_API_KEY, str)

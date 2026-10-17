"""Test safety: tests must never read the real .env or call the real Anthropic API."""

import os
from pathlib import Path

import pytest

# Set before any test module imports app.main (which calls config.load_env()).
os.environ["MUSE_ENV_FILE"] = str(Path(__file__).parent / "no-such.env")
os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture(autouse=True)
def no_real_api_calls(monkeypatch):
    """Any test that builds the real SDK client fails. Tests that need one patch anthropic.Anthropic with a fake."""
    import anthropic

    def boom(*a, **k):
        raise AssertionError("a test tried to build a real Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", boom)

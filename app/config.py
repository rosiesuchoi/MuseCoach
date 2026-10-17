"""Loads settings from a `.env` file in the project root into the environment (real environment variables win).

The Anthropic key goes in `.env` as  ANTHROPIC_API_KEY=...  That file is gitignored and is created by you, on your PC.
Nothing in this project prints, logs, stores or sends the key anywhere except to api.anthropic.com.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path | None = None) -> None:
    path = path or Path(os.environ.get("MUSE_ENV_FILE") or DEFAULT_ENV_PATH)  # MUSE_ENV_FILE lets tests point elsewhere
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name and value and name not in os.environ:  # never override a real environment variable
            os.environ[name] = value


def anthropic_key() -> str:
    """The key if one is set and not just the placeholder, else an empty string."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return "" if not key or key.lower().startswith(("your", "paste", "sk-ant-...")) else key

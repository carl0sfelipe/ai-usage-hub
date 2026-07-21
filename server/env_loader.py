from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path = "~/.hermes/.env") -> None:
    """Load env vars from a .env file (KEY=VALUE format, # comments)."""
    p = Path(path).expanduser()
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

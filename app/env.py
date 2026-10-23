"""Read `.env` into the environment at startup, without overriding anything already set.

The file is gitignored and holds configuration only (endpoint and model names); auth is
DefaultAzureCredential, so there are no keys in it.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


AZ_CLI_DIR = Path.home() / ".venvs" / "azcli" / "Scripts"  # local dev: where our Azure CLI lives


def load_env(path: Path = ENV_FILE) -> None:
    import shutil

    # DefaultAzureCredential signs in through `az`; make sure a server started from anywhere finds it.
    if shutil.which("az") is None and AZ_CLI_DIR.exists():
        os.environ["PATH"] = f"{AZ_CLI_DIR}{os.pathsep}{os.environ.get('PATH', '')}"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

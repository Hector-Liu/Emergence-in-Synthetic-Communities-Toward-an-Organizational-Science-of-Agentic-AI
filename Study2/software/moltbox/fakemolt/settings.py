"""Per-machine preferences (gitignored): price overrides and extra model ids."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "local_settings.json"


def load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update(**kw) -> dict:
    d = load()
    d.update(kw)
    PATH.write_text(json.dumps(d, indent=2) + "\n")
    return d

"""Denylist guard (SPEC 3.7), fail-closed.

Engine-authored text is checked; text written by agents is not (it is tagged
by provenance in prompts.Parts). A hit before the run aborts it before any call.
"""
from __future__ import annotations

import re

from . import texts


class GuardError(Exception):
    def __init__(self, hits: list[dict]):
        self.hits = hits
        super().__init__("; ".join(f"'{h['word']}' in {h['where']}" for h in hits[:5]))


def find(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low)]


def check_texts(named: dict[str, str], words: list[str]) -> list[dict]:
    hits = []
    for where, text in named.items():
        for w in find(text, words):
            hits.append({"where": where, "word": w})
    return hits


def preflight(config, system_template: str, visit_template: str) -> list[dict]:
    """Everything engine-authored that this run can send, before the first call."""
    words = texts.denylist(config.switches.tell_ai)
    named = {"system prompt": system_template, "visit prompt": visit_template}
    frags = [f for f in texts.all_fragments() if config.switches.tell_ai or f != texts.IDENTITY_AI]
    if config.switches.tell_ai:
        named["identity sentence"] = texts.IDENTITY_AI
    named["goal sentence"] = texts.GOALS[config.switches.goal]
    for i, f in enumerate(frags):
        named[f"fixed text {i}"] = f
    for c in config.communities:
        named[f"community {c.name}"] = f"{c.name}: {c.description}"
    return check_texts(named, words)


def check_parts(parts, words: list[str]) -> list[dict]:
    """Check the engine-authored parts of one rendered prompt."""
    return check_texts({f"part {i}": t for i, (t, who) in enumerate(parts) if who == "engine"}, words)

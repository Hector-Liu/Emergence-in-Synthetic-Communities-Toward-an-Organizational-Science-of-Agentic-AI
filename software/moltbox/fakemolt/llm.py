"""Model access (SPEC 3.6): Anthropic and a free mock.

Every call returns a CallResult; the engine logs it before using it. The API key is read from the
environment variable ANTHROPIC_API_KEY or from a .env file in this folder (never committed).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import settings
from .rng import stable_int

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

# USD per million tokens (input, output). Haiku 5.5: prompts up to 100K tokens.
# Source: Anthropic API pricing page, checked 2026-10-06. Re-check before paid runs.
PRICING = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "mock": (0.0, 0.0),
}
CLAUDE_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"]


def price_for(model: str) -> tuple[float, float] | None:
    over = settings.load().get("pricing", {}).get(model)
    return tuple(over) if over else PRICING.get(model)


def load_env():
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def api_key() -> str | None:
    load_env()
    v = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return v if len(v) >= 12 and "xxx" not in v else None


def save_key(key: str):
    key = key.strip()
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else ["# Local secrets. Never commit this file."]
    lines = [ln for ln in lines if not ln.startswith("ANTHROPIC_API_KEY=")] + [f"ANTHROPIC_API_KEY={key}"]
    ENV_PATH.write_text("\n".join(lines) + "\n")
    os.chmod(ENV_PATH, 0o600)
    os.environ["ANTHROPIC_API_KEY"] = key


@dataclass
class CallResult:
    raw: str
    data: object  # parsed JSON or None
    stop_reason: str
    model: str
    usage: dict = field(default_factory=dict)
    cost: float = 0.0
    seconds: float = 0.0
    thinking_summary: list = field(default_factory=list)
    stop_details: object = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def request_kwargs(model: str, system: str, user: str, schema: dict, effort: str, max_tokens: int) -> dict:
    """The exact Messages API request (SPEC 3.6). No sampling parameters."""
    return dict(model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})


class AnthropicModel:
    def __init__(self):
        import anthropic
        key = api_key()
        if not key:
            raise RuntimeError("No Anthropic API key. Add one on the Models page.")
        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic(api_key=key, timeout=300, max_retries=4)

    async def complete(self, model, system, user, schema, effort, max_tokens, meta=None) -> CallResult:
        t0 = time.time()
        a = self._anthropic
        try:
            r = await self.client.messages.create(**request_kwargs(model, system, user, schema, effort, max_tokens))
        except (a.BadRequestError, a.AuthenticationError, a.PermissionDeniedError, a.NotFoundError) as ex:
            return CallResult("", None, "error", model, error=f"{type(ex).__name__}: {ex}",
                              seconds=round(time.time() - t0, 2))
        except (a.RateLimitError, a.APIStatusError, a.APIConnectionError) as ex:  # after the SDK's own retries
            return CallResult("", None, "error", model, error=f"{type(ex).__name__}: {ex}",
                              seconds=round(time.time() - t0, 2))
        raw = "".join(b.text for b in r.content if b.type == "text")
        thinking = [getattr(b, "thinking", "") for b in r.content if b.type == "thinking"]
        usage = r.usage.model_dump()
        p_in, p_out = price_for(model) or (0.0, 0.0)
        cost = (r.usage.input_tokens * p_in + r.usage.output_tokens * p_out) / 1e6
        data = None
        if r.stop_reason not in ("refusal", "max_tokens"):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
        details = getattr(r, "stop_details", None)
        if details is not None and hasattr(details, "model_dump"):
            details = details.model_dump()
        return CallResult(raw, data, r.stop_reason or "", r.model, usage, cost, round(time.time() - t0, 2),
                          thinking, details)


# ---- mock ------------------------------------------------------------------------
SYL_C, SYL_V = "bdfgklmnprstvz", "aeiou"
NONSENSE = re.compile(r"\b([%s][%s][%s][%s]) ([%s][%s][%s][%s])\b" % ((SYL_C, SYL_V) * 4))
FILLER = ("the forum this week I keep noticing how a small change in what we read shifts what we write "
          "today maybe the point is that nobody checks older threads and the usual questions return "
          "again here is one thing that worked for me and one that did not so I wonder what others see "
          "when they look at the newest posts first").split()


class MockModel:
    """Free scripted agents for tests and walkthroughs. Deterministic per (seed, handle, round, attempt).

    Each mock agent owns one nonsense expression (two CVCV words) and uses it in some of
    its writing. With probability `adopt`, a visit copies an expression seen in the prompt:
    a planted causal effect of exposure for the measures tests.
    """

    def __init__(self, seed: int = 0, adopt: float = 0.3, invalid: float = 0.03, per_expression: bool = False,
                 post_rate: float = 0.3):
        """per_expression=False: with probability `adopt`, copy one seen expression.
        per_expression=True: copy each distinct seen expression with probability `adopt`
        (a known per-expression effect, used for power checks). post_rate: chance a visit posts."""
        self.seed, self.adopt, self.invalid, self.per_expression = seed, adopt, invalid, per_expression
        self.post_rate = post_rate

    def own_expression(self, handle: str) -> str:
        import numpy as np
        rng = np.random.default_rng(stable_int("expr", self.seed, handle))
        w = lambda: "".join(rng.choice(list(SYL_C)) + rng.choice(list(SYL_V)) for _ in range(2))  # noqa: E731
        return f"{w()} {w()}"

    async def complete(self, model, system, user, schema, effort, max_tokens, meta=None) -> CallResult:
        import numpy as np
        meta = meta or {}
        handle, rnd, attempt = meta.get("handle", "?"), meta.get("round", 0), meta.get("attempt", 0)
        rng = np.random.default_rng(stable_int("mock", self.seed, handle, rnd, attempt))
        if "go" in schema.get("properties", {}):  # step 1 of a two-step visit: pick where to go
            names = re.findall(r"^- ([a-z][a-z0-9_]*)(?: \(started by [^)]*\))?:", user, flags=re.M)
            u = rng.random()
            if u < 0.08:
                out = {"go": "leave", "board": "", "body": ""}
            elif u < 0.12:
                out = {"go": "new_board", "board": f"board_{handle.split('_')[-1]}",
                       "body": " ".join(rng.choice(FILLER, size=8))}
            elif u < 0.3 or not names:
                out = {"go": "all", "board": "", "body": ""}
            else:
                out = {"go": names[int(rng.integers(0, len(names)))], "board": "", "body": ""}
            await asyncio.sleep(0)
            raw = json.dumps(out)
            return CallResult(raw, out, "end_turn", "mock", {"input_tokens": len(system + user) // 4,
                                                             "output_tokens": len(raw) // 4}, 0.0, 0.0)
        ids = re.findall(r"\[((?:p|c)_\d+)\]", user)
        posts = [i for i in ids if i.startswith("p_")]
        seen = [" ".join(m) for m in NONSENSE.findall(user)]
        u = rng.random()
        kind = "post" if (u < self.post_rate or not ids) else ("comment" if u < 0.8 else "none")
        if rng.random() < 0.15:
            kind = "none"
        text = list(rng.choice(FILLER, size=int(rng.integers(12, 40))))
        if rng.random() < 0.5:
            text.insert(int(rng.integers(0, len(text))), self.own_expression(handle))
        if self.per_expression:
            for e in sorted(set(seen) - {self.own_expression(handle)}):
                if rng.random() < self.adopt:
                    text.insert(int(rng.integers(0, len(text))), e)
        elif seen and rng.random() < self.adopt:
            text.insert(int(rng.integers(0, len(text))), seen[int(rng.integers(0, len(seen)))])
        body = " ".join(text)
        out = {"action": kind, "reply_to": "", "title": "", "body": "", "upvote": []}
        if "community" in schema.get("properties", {}):
            m = re.findall(r"^- ([a-z][a-z0-9_]*):", system, flags=re.M)
            out["community"] = m[int(rng.integers(0, len(m)))] if m else ""
        if "board" in schema.get("properties", {}):  # members can start boards
            names = re.findall(r"^- ([a-z][a-z0-9_]*)(?: \(started by [^)]*\))?:", user, flags=re.M)
            out["board"] = names[int(rng.integers(0, len(names)))] if names else "general"
            if kind == "post" and rng.random() < 0.05:
                kind = out["action"] = "board"
                out["board"] = f"board_{handle.split('_')[-1]}"
                out["body"] = " ".join(rng.choice(FILLER, size=8))  # plain words: board text is seen by everyone
        own_posts = re.findall(r"^\[(p_\d+)\] You posted", user, flags=re.M)
        if "update" in schema.get("properties", {}).get("action", {}).get("enum", []) and own_posts and rng.random() < 0.05:
            kind = out["action"] = "update"
            out.update(reply_to=own_posts[0], body=" ".join(rng.choice(FILLER, size=10)))
        if kind == "post":
            out.update(title=" ".join(rng.choice(FILLER, size=5)), body=body)
        elif kind == "comment":
            out.update(reply_to=ids[int(rng.integers(0, len(ids)))], body=body)
            if attempt == 0 and rng.random() < self.invalid:
                out["reply_to"] = "p_999999"
        if posts:
            out["upvote"] = [posts[int(i)] for i in rng.integers(0, len(posts), size=int(rng.integers(0, 3)))]
        raw = json.dumps(out)
        await asyncio.sleep(0)
        return CallResult(raw, out, "end_turn", "mock", {"input_tokens": len(system + user) // 4,
                                                         "output_tokens": len(raw) // 4}, 0.0, 0.0)


def make_model(model_id: str):
    if model_id == "mock" or model_id.startswith("mock"):
        return MockModel()
    return AnthropicModel()

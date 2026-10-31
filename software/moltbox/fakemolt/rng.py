"""Seeded random streams, one per purpose (pattern from the naming game).

`rng_for(seed, "feed_random", round, agent_index)` always returns the same
generator, so a resumed or re-analysed run draws exactly what the original drew.
"""
from __future__ import annotations

import zlib

import numpy as np

STREAMS = ("handles", "assign", "feed_random", "display", "tiebreak", "commit", "redraw", "activation", "comment_random", "opening", "forum_comment", "schedule", "visit_order", "board_order")  # append only: indices are part of the seed


def rng_for(seed: int, stream: str, *keys: int) -> np.random.Generator:
    if stream not in STREAMS:
        raise ValueError(f"unknown stream {stream}")
    key = (STREAMS.index(stream),) + tuple(int(k) for k in keys)
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=key))


def stable_int(*parts) -> int:
    """A process-independent hash (Python's hash() is salted per process)."""
    return zlib.crc32("\x1f".join(str(p) for p in parts).encode())

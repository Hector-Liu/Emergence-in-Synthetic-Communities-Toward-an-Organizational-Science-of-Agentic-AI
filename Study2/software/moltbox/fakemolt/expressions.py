"""Founder expressions (SPEC 1), shared by the engine and the measures.

Tokens: lower-case runs of letters, digits, apostrophes and underscores; title
and body are joined with a break between them. Handles (u_...) and ids (p_..,
c_..) are breaks, never part of an n-gram. Thinking summaries are never read.

An expression is a 2-4-gram that, at the end of phase 1:
- occurs in at least MIN_TEXTS phase-1 texts written by at least MIN_FOUNDERS founders,
- is not all stopwords and does not occur in any engine-authored text,
- is not contained in a longer kept n-gram found in exactly the same texts.
The engine freezes the list into expressions.json before any newcomer acts.
"""
from __future__ import annotations

import re
from collections import defaultdict

from . import texts

MIN_TEXTS = 3
MIN_FOUNDERS = 2
TOKEN = re.compile(r"[a-z0-9_']+")
ID_TOKEN = re.compile(r"^(?:u|p|c)_[a-z0-9]+$")
STOPWORDS = set("""a about above after again against all am an and any are aren't as at be because been before being
below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few
for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself
his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor
not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd
they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were
weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you
you'd you'll you're you've your yours yourself yourselves just also really maybe still even""".split())


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower().replace("’", "'"))


BREAK = re.compile(r"[\x00\n.!?;:()\[\]\"]+")


def ngrams(text: str, lo: int = 2, hi: int = 4) -> set[tuple]:
    """n-grams within one sentence-like segment, never across a handle or an id."""
    out = set()
    for segment in BREAK.split(text):
        run = []
        for tok in tokens(segment) + ["\x00"]:
            if tok == "\x00" or ID_TOKEN.match(tok):
                for n in range(lo, hi + 1):
                    for i in range(len(run) - n + 1):
                        g = tuple(run[i:i + n])
                        if not all(w in STOPWORDS for w in g):
                            out.add(g)
                run = []
            else:
                run.append(tok)
    return out


def post_text(title: str, body: str) -> str:
    return title + "\n\x00\n" + body  # \x00 is not a token character: n-grams never join title and body


def uses(text: str, g: tuple) -> bool:
    return g in ngrams(text, len(g), len(g))


def engine_ngrams(system_template: str, visit_template: str, communities) -> set[tuple]:
    pieces = [system_template, visit_template, texts.IDENTITY_AI] + texts.all_fragments() + \
        list(texts.GOALS.values()) + [f"{c.name} {c.description}" for c in communities]
    out = set()
    for piece in pieces:
        out |= ngrams(re.sub(r"\{[a-z_]+\}", "\n", piece))
    return out | {v for g in out for v in _inflections(g)}


def _inflections(g: tuple) -> list[tuple]:
    """Simple plural/singular variants of the last word, so "ai agents" counts as engine text like "ai agent"."""
    last = g[-1]
    alts = [last[:-1]] if last.endswith("s") and len(last) > 3 else [last + "s"]
    return [g[:-1] + (a,) for a in alts]


def freeze(items, echo: set[tuple]) -> dict[tuple, dict]:
    """items: (round, author, item_id, text) for every phase-1 post and comment."""
    where: dict[tuple, list] = defaultdict(list)
    for rnd, author, item, text in items:
        for g in ngrams(text):
            where[g].append((rnd, author, item))
    kept = {g: w for g, w in where.items()
            if len(w) >= MIN_TEXTS and len({x[1] for x in w}) >= MIN_FOUNDERS and g not in echo}
    out = {}
    for g, w in kept.items():
        ids = {x[2] for x in w}
        if any(len(h) == len(g) + 1 and (h[:-1] == g or h[1:] == g) and {x[2] for x in kept[h]} == ids
               for h in kept):
            continue
        first = min(w)
        out[g] = {"first_round": first[0], "first_author": first[1], "texts": len(w),
                  "founders": len({x[1] for x in w})}
    return out


def forum_items(forum, upto_round: int):
    out = []
    for p in forum.posts.values():
        if p.round <= upto_round:
            out.append((p.round, p.author, p.id, post_text(p.title, p.body)))
    for c in forum.comments.values():
        if c.round <= upto_round:
            out.append((c.round, c.author, c.id, c.body))
    return sorted(out, key=lambda x: (x[0], x[2][0], int(x[2].split("_")[1])))


def forum_comment_text(forum, c) -> str:
    """What the forum-wide comment slot shows of a comment: its thread's title, a break, the comment."""
    return forum.posts[c.post].title + " \x00 " + c.body

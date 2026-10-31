"""Screening rules for the 16 meaningless words, copied unchanged from the naming-game project that
generated them ("AI simulation 2nd", naming_game/labels.py, commit 57b569f), so that this repository
regenerates the same vocabulary without that project. Only the functions quick_trial.make_vocabulary
uses are kept. The word lists in wordlists/ are public-domain snapshots (see wordlists/README.md).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "wordlists"

CONSONANTS = "bdfgklmnprstvz"
VOWELS = "aeiou"

# Plain substrings a label may not contain
DENY_SUBSTRINGS = [
    "consensus", "agree", "coordinat", "cooperat", "align", "success", "fail",
    "converge", "group", "majority", "most", "popular", "win", "collective",
    "everyone", "population", "point", "score", "reward", "payoff", "lose",
]


@lru_cache(maxsize=None)
def _wordlist(name: str) -> frozenset:
    path = DATA_DIR / name
    if not path.exists():
        return frozenset()
    return frozenset(w.strip().lower() for w in path.read_text().splitlines() if w.strip())


def english_words() -> frozenset:
    return _wordlist("english_words.txt")


def first_names() -> frozenset:
    return _wordlist("first_names.txt")


def brands() -> frozenset:
    return _wordlist("brands.txt")


def problem_words() -> frozenset:
    return frozenset(w for w in _wordlist("problem_words.txt") if not w.startswith("#"))


def levenshtein(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _has_alpha_sequence(w: str) -> bool:
    w = w.lower()
    for i in range(len(w) - 2):
        a, b, c = (ord(x) for x in w[i:i + 3])
        if (b - a == 1 and c - b == 1) or (a - b == 1 and b - c == 1):
            return True
    return False


def label_problems(label: str) -> list[str]:
    """Why a single candidate label is rejected (empty = acceptable)."""
    w = label.lower()
    p = []
    if w in english_words():
        p.append("english word")
    if w in first_names():
        p.append("first name")
    if w in brands():
        p.append("brand")
    if w in problem_words():
        p.append("meaning in another language or near-homograph (curated list)")
    for s in DENY_SUBSTRINGS:
        if s in w:
            p.append(f"denylist substring {s!r}")
    if _has_alpha_sequence(w):
        p.append("alphabetical sequence")
    if len(w) >= 4 and w[:2] == w[2:4]:
        p.append("reduplicated syllable")
    return p


def set_problems(labels: list[str]) -> list[str]:
    """Why a label set is rejected (empty = passes)."""
    p = []
    for lab in labels:
        for why in label_problems(lab):
            p.append(f"{lab}: {why}")
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if levenshtein(a, b) < 2:
                p.append(f"{a}/{b}: edit distance < 2")
            if a[:2].lower() == b[:2].lower():
                p.append(f"{a}/{b}: same first two letters")
    if len({lab.lower() for lab in labels}) != len(labels):
        p.append("duplicate labels")
    return p

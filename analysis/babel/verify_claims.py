"""Recompute the Babel numbers and facts in Study 2 and Appendix B from the logs.

    python3 analysis/babel/verify_claims.py        (from the package root; standard library only)

Reads data/babel/reported-runs/. Prints one row per value and writes the table to
analysis/babel/output/claims.md. Scores are exact scores (a block counts only if its colour and its shape
are both right). A row is "match" when the computed value, rounded as in the text, equals the expected value.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "babel" / "reported-runs"
OUT = Path(__file__).resolve().parent / "output" / "claims.md"

TAGS = ["p101", "p102", "p103", "p104", "p201", "p202", "p203", "p204"]
NAME = {"p101": "pair 1", "p102": "pair 2", "p103": "pair 3", "p104": "pair 4",
        "p201": "1A+2B", "p202": "2A+3B", "p203": "3A+4B", "p204": "4A+1B"}


def jl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


RUN = {t: next(p for p in DATA.iterdir() if re.search(rf"-{t}(-|$)", p.name)) for t in TAGS}
ROWS = {t: jl(RUN[t] / "rounds.jsonl") for t in TAGS}
CALLS = {t: jl(RUN[t] / "calls.jsonl") for t in TAGS}
WORLD = {t: json.loads((RUN[t] / "world.json").read_text()) for t in TAGS}
ALL = [r for t in TAGS for r in ROWS[t] if not r["void"]]
blocks = lambda s: s.split(", ") if s else []  # noqa: E731
bbb = lambda h: min(h, 4) / h  # noqa: E731  (block by block: 8 words name at most 4 blocks)


def m(rows, key="exact"):
    return mean(r[key] for r in rows if not r["void"])


def tall(rows):
    return [r for r in rows if not r["void"] and r["height"] >= 5]


def r2(x):
    return f"{x:.2f}"


def scores(r):
    """Shown score and exact score of one round, from the target and the tower built."""
    t, b = blocks(r["target"]), blocks(r["built"])
    full = sum(x == y for x, y in zip(t, b))
    part = sum(x != y and (x.split()[0] == y.split()[0] or x.split()[1] == y.split()[1]) for x, y in zip(t, b))
    h = max(len(t), len(b))
    return (full + part / 4) / h, full / h


def source(s):
    """Original run of an agent in a new pair (an entry of world.json "swap")."""
    return next(u for u in TAGS[:4] if RUN[u].name == Path(s["run"]).name)


# agents in the new pairs: (label such as "3A", original run, agent index in the new run)
MEMBERS = {t: [(f"{source(s)[-1]}{'AB'[s['agent']]}", source(s), i) for i, s in enumerate(WORLD[t]["swap"])]
           for t in TAGS[4:]}

TABLE = []


def claim(where, label, expected, computed, ok, src):
    status = "match" if ok else "DIFFERS"
    TABLE.append((where, f"{label}: {expected}", computed, status, src))
    print(f"[{status}] {where}: {label}: {expected}\n    -> {computed}\n    ({src})")


# ---------------------------------------------------------------------------------------------- B.1 design
vocab = {tuple(sorted(WORLD[t]["vocabulary"])) for t in TAGS}
words = list(next(iter(vocab)))
stated = "dobo fidi fuza kano kuru loku mape melu muva neto nove tido tumu vepu vonu zeki".split()
claim("Main text, B.1", "Vocabulary: size; words", "16; " + ", ".join(stated),
      f"{len(words)}; {', '.join(words)} (same list in all 8 runs: {len(vocab) == 1})",
      len(vocab) == 1 and words == stated, "world.json {vocabulary}")

heights = [r["height"] for r in ALL]
types = Counter(b for r in ALL for b in blocks(r["target"]))
colours, shapes = {b.split()[0] for b in types}, {b.split()[1] for b in types}
claim("B.1, B.3", "Tower height; colours; shapes; block types that occur", "1 to 10; 6; 5; 27",
      f"{min(heights)} to {max(heights)}; {len(colours)}; {len(shapes)}; {len(types)}",
      (min(heights), max(heights), len(colours), len(shapes), len(types)) == (1, 10, 6, 5, 27),
      "rounds.jsonl {target, height}, all 8 runs")

msgs = [r["message"] for r in ALL]
cap = sum("A message has at most 8 words." in w["instructions"] for w in WORLD.values())
claim("B.1", "Longest message (words); words outside the vocabulary", "at most 8; 0",
      f"{max(map(len, msgs))}; {sum(w not in stated for x in msgs for w in x)}; cap of 8 words in the "
      f"instructions of {cap} of 8 runs", max(map(len, msgs)) <= 8 and all(w in stated for x in msgs for w in x)
      and cap == 8, "rounds.jsonl {message}; world.json {instructions}")

ok_s = sum(abs(scores(r)[0] - r["score"]) < 1e-9 for r in ALL)
ok_e = sum(abs(scores(r)[1] - r["exact"]) < 1e-9 for r in ALL)
claim("B.1", "Rounds whose score = (blocks fully right + 1/4 x blocks with colour or shape right) / taller height, "
      "and exact score = blocks fully right / taller height", "all",
      f"score {ok_s} of {len(ALL)}; exact score {ok_e} of {len(ALL)}; scoring setting "
      f"{sorted({w['scoring'] for w in WORLD.values()})}", ok_s == ok_e == len(ALL),
      "rounds.jsonl {target, built, score, exact}; world.json {scoring}")

ref = [bbb(r["height"]) for r in tall(ROWS["p101"])]
claim("B.1", "Block-by-block description (4 blocks per message), mean exact score on tall towers (5 to 10 blocks), "
      "rounds 1-120", "0.53", f"{mean(ref):.4f} over {len(ref)} towers", r2(mean(ref)) == "0.53",
      "p101/rounds.jsonl {height}")

record, own, partner = [], [], []
for t in TAGS:
    for c in CALLS[t]:
        p = c["prompt"]
        if c["kind"] != "notes" and "Your recent rounds, oldest first:\n" in p:
            rec = p.split("Your recent rounds, oldest first:\n", 1)[1].split("\n")
            record.append(sum(x.startswith(("You saw the target.", "You built.")) for x in rec))
        if c["round"] >= 2:  # notes as they stood after the previous round
            notes = ROWS[t][c["round"] - 2]["notes"]
            own.append(notes[c["agent"]].strip() in p)
            partner.append(bool(notes[1 - c["agent"]].strip()) and notes[1 - c["agent"]].strip() in p)
claim("B.1", "Most rounds in an agent's record; prompts with the agent's own notes; prompts with the partner's notes",
      "8; all; 0", f"{max(record)}; {sum(own)} of {len(own)}; {sum(partner)} (prompts from round 2 on)",
      max(record) == 8 and all(own) and not any(partner), "calls.jsonl {prompt}; rounds.jsonl {notes}")

# ---------------------------------------------------------------------------------------------- B.2 procedure
models = {(w["model"], w.get("effort")) for w in WORLD.values()}
same_towers = len({tuple(WORLD[t]["towers"]) for t in TAGS[:4]}) == 1
claim("Main text, B.2", "Pairs 1-4: model, effort; same tower list; rounds", "Claude Sonnet 5.5, high; yes; 120",
      f"{sorted(models)}; {same_towers}; {[len(ROWS[t]) for t in TAGS[:4]]}",
      models == {("claude-sonnet-5-5", "high")} and same_towers and len(WORLD["p101"]["towers"]) == 120,
      "world.json {model, effort, towers}; rounds.jsonl")

declined = [c["round"] for c in CALLS["p102"] if c.get("stop_reason") == "refusal"]
claim("B.2", "Pair 2: rounds played; round of the last declined call", "94; 94",
      f"{len(ROWS['p102'])}; declined calls in rounds {declined}",
      len(ROWS["p102"]) == 94 and max(declined) == 94, "p102/rounds.jsonl; p102/calls.jsonl {stop_reason}")

pairs = ["+".join(a for a, _, _ in MEMBERS[t]) for t in TAGS[4:]]
start = {(WORLD[t]["start_tower"] + 1, WORLD[t]["start_tower"] + len(ROWS[t])) for t in TAGS[4:]}
claim("B.2", "New pairs; towers; rounds", "1A+2B, 2A+3B, 3A+4B, 4A+1B; 121-180; 60",
      f"{', '.join(pairs)}; {sorted(start)}; {[len(ROWS[t]) for t in TAGS[4:]]}",
      pairs == ["1A+2B", "2A+3B", "3A+4B", "4A+1B"] and start == {(121, 180)}, "world.json {swap, start_tower}")

told = {t: bool(re.search(r"different participant", WORLD[t]["instructions"])) for t in TAGS}
carried = []
for t in TAGS[4:]:
    for _, u, i in MEMBERS[t]:
        old = ROWS[u][-1]["notes"][WORLD[t]["swap"][i]["agent"]]
        first = next(c["prompt"] for c in CALLS[t] if c["agent"] == i and c["kind"] != "notes")
        carried.append(old.strip() in first)
claim("B.2, B.5", "Instructions saying the partner is new (new pairs / original pairs); agents whose first prompt "
      "with the new partner holds their last notes", "4 of 4 / 0 of 4; 8 of 8",
      f"{sum(told[t] for t in TAGS[4:])} of 4 / {sum(told[t] for t in TAGS[:4])} of 4; {sum(carried)} of {len(carried)}",
      all(told[t] for t in TAGS[4:]) and not any(told[t] for t in TAGS[:4]) and all(carried),
      "world.json {instructions, swap}; calls.jsonl {prompt}; rounds.jsonl {notes}")

# ---------------------------------------------------------------------------------------------- B.3 languages
last40 = {t: m(ROWS[t][-40:]) for t in TAGS[:4]}
claim("B.3", "Exact score, last 40 rounds: pair 1 / pair 2 / pair 3", "0.72 / 0.53 / 0.18",
      " / ".join(f"{last40[t]:.4f}" for t in TAGS[:3]),
      [r2(last40[t]) for t in TAGS[:3]] == ["0.72", "0.53", "0.18"], "rounds.jsonl {exact}, last 40 rows")

s7 = [r for r in ROWS["p101"] if not r["void"] and r["height"] <= 4 and r["round"] >= 7]
claim("B.3", "Pair 1, rounds 7-120: short towers (1 to 4 blocks) rebuilt exactly", "43 of 44",
      f"{sum(r['exact'] == 1 for r in s7)} of {len(s7)}", (sum(r["exact"] == 1 for r in s7), len(s7)) == (43, 44),
      "p101/rounds.jsonl {height, exact}")

cnt = {}
for r in ROWS["p102"][-40:]:
    built = blocks(r["built"])
    if not r["void"] and len(built) == len(r["message"]):  # one block per word
        for w, b in zip(r["message"], built):
            cnt.setdefault(w, Counter())[b] += 1
lex = {c.most_common(1)[0][0] for c in cnt.values()}
noted = re.search(r"Exact blocks exist only for ([^.]+)\.", "\n".join(ROWS["p102"][-1]["notes"]))
noted = {x.strip() for x in noted.group(1).split(",")} if noted else set()
claim("B.3", "Pair 2, last 40 rounds: block types named by single words (of those that occur)", "11 (of 27)",
      f"{len(lex)} from messages and builds ({', '.join(sorted(lex))}); final notes list {len(noted)} types, "
      f"{len(noted & set(types))} of which occur", len(lex) == 11 and len(noted & set(types)) == 11 and len(types) == 27,
      "p102/rounds.jsonl {message, built, notes}")

gain = {t: mean(r["exact"] - bbb(r["height"]) for r in tall(ROWS[t])[-50:]) for t in TAGS[:4]}
claim("B.3", "Exact score minus block-by-block score, last 50 tall towers: pair 4 / pairs 1-3",
      "+0.07 / below 0", f"{gain['p104']:+.4f} / " + ", ".join(f"{gain[t]:+.3f}" for t in TAGS[:3]),
      r2(gain["p104"]) == "0.07" and all(gain[t] < 0 for t in TAGS[:3]), "rounds.jsonl {exact, height}")

# ---------------------------------------------------------------------------------------------- Figure B2
r = ROWS["p104"][119]
t, b = blocks(r["target"]), blocks(r["built"])
wrong = [i + 1 for i in range(max(len(t), len(b))) if i >= len(b) or i >= len(t) or t[i] != b[i]]
rings = [i + 1 for i in range(1, len(t)) if t[i].split()[1] == "ring" and t[i].split()[0] != t[i - 1].split()[0]]
claim("Figure B2", "Pair 4, round 120: exact score; blocks not rebuilt; target rings that start a new colour; "
      "words in the message", "0.67; 2, 7, 9; 2, 7; 8",
      f"{r['exact']:.2f}; {wrong}; {rings}; {len(r['message'])} (message {' '.join(r['message'])!r}; "
      f"target {r['target']!r}; built {r['built']!r})",
      r["round"] == 120 and r2(r["exact"]) == "0.67" and wrong == [2, 7, 9] and rings == [2, 7]
      and len(r["message"]) == 8, "p104/rounds.jsonl round 120")

for tag, rnd in (("p101", 62), ("p102", 92), ("p103", 39)):
    r = ROWS[tag][rnd - 1]
    claim("Figure B2", f"{NAME[tag].capitalize()}, round {rnd}: exact score", "1.00",
          f"{r['exact']:.2f} (message {' '.join(r['message'])!r}; built {r['built']!r})",
          r["round"] == rnd and r["exact"] == 1, f"{tag}/rounds.jsonl round {rnd}")

# ---------------------------------------------------------------------------------------------- B.4 re-paired agents
claim("B.4", "New pairs, exact score in their first round", "0 (all four)",
      ", ".join(f"{NAME[t]} {ROWS[t][0]['exact']:.2f}" for t in TAGS[4:]),
      all(ROWS[t][0]["exact"] == 0 for t in TAGS[4:]), "p201-p204 rounds.jsonl round 1")

last20 = {t: m(ROWS[t][-20:]) for t in TAGS}
new20 = [last20[t] for t in TAGS[4:]]
claim("B.4", "New pairs, exact score over last 20 rounds: lowest / highest", "0.27 / 0.52",
      ", ".join(f"{NAME[t]} {last20[t]:.4f}" for t in TAGS[4:]),
      (r2(min(new20)), r2(max(new20))) == ("0.27", "0.52"), "p201-p204 rounds.jsonl, rounds 41-60")

strong = [last40[t] for t in ("p101", "p102", "p104")]
claim("B.4", "Pairs 1, 2 and 4, exact score over last 40 rounds: lowest / highest", "0.53 / 0.72",
      ", ".join(f"{NAME[t]} {last40[t]:.4f}" for t in ("p101", "p102", "p104")),
      (r2(min(strong)), r2(max(strong))) == ("0.53", "0.72"), "p101, p102, p104 rounds.jsonl")

up, down = [], []
for t in TAGS[4:]:
    for a, u, _ in MEMBERS[t]:
        if last20[t] > max(last40[u], last20[u]):
            up.append(a)
        elif last20[t] < min(last40[u], last20[u]):
            down.append(a)
claim("B.4, Figure B3(b)", "Agents whose new pair (last 20 rounds) scored above / below their original pair "
      "(last 40 and last 20 rounds)", "3A, 3B / the other six", f"{', '.join(sorted(up))} / {', '.join(sorted(down))}",
      sorted(up) == ["3A", "3B"] and len(down) == 6, "rounds.jsonl {exact}")

claim("B.4", "3A+4B, exact score over last 20 rounds; rank among new pairs", "0.52; highest",
      f"{last20['p203']:.4f}; highest: {NAME[max(TAGS[4:], key=last20.get)]}",
      r2(last20["p203"]) == "0.52" and max(TAGS[4:], key=last20.get) == "p203", "p203/rounds.jsonl")

all60 = {t: m(ROWS[t]) for t in TAGS[4:]}
others = [all60[t] for t in ("p201", "p202", "p204")]
same60 = len({tuple(WORLD[t]["towers"]) for t in TAGS[4:]}) == 1
claim("B.4", "New pairs, mean exact score over all 60 rounds: 3A+4B / the other three; same tower list",
      "0.41 / 0.27 to 0.31; yes", ", ".join(f"{NAME[t]} {v:.4f}" for t, v in all60.items()) + f"; {same60}",
      (r2(all60["p203"]), r2(min(others)), r2(max(others))) == ("0.41", "0.27", "0.31") and same60,
      "p201-p204 rounds.jsonl {exact}; world.json {towers}")

claim("Main text", "Exact score of 3A+4B (last 20 rounds) / pair 3 (last 40 rounds; last 20 rounds)", "more than 2",
      f"{last20['p203'] / last40['p103']:.2f}; {last20['p203'] / last20['p103']:.2f}",
      last20["p203"] / max(last40["p103"], last20["p103"]) > 2, "p103, p203 rounds.jsonl")

# ---------------------------------------------------------------------------------------------- B.5 limitations
h1 = [len(blocks(x)) for x in WORLD["p101"]["towers"]]
h2 = [len(blocks(x)) for x in WORLD["p203"]["towers"]]
claim("B.5", "Tall towers (5 to 10 blocks): rounds 121-180 / rounds 1-120", "42 of 60 / 72 of 120",
      f"{sum(x >= 5 for x in h2)} of {len(h2)} / {sum(x >= 5 for x in h1)} of {len(h1)}",
      (sum(x >= 5 for x in h2), len(h2), sum(x >= 5 for x in h1), len(h1)) == (42, 60, 72, 120), "world.json {towers}")

# ---------------------------------------------------------------------------------------------- write
OUT.parent.mkdir(parents=True, exist_ok=True)
esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
n = Counter(row[3] for row in TABLE)
summary = f"{n['match']} match, {n['DIFFERS']} differ."
lines = ["# Babel: values in Study 2 and Appendix B, recomputed from the logs", "",
         "Written by `analysis/babel/verify_claims.py`. Paths are relative to `data/babel/reported-runs/<run>/`.", "",
         "| Where | Claim | Computed | Status | Source |", "|---|---|---|---|---|"]
lines += [f"| {esc(a)} | {esc(b)} | {esc(c)} | {d} | {esc(e)} |" for a, b, c, d, e in TABLE]
OUT.write_text("\n".join(lines + ["", summary]) + "\n")
print(f"\n{summary} Table: {OUT.relative_to(ROOT)}")
sys.exit(1 if n["DIFFERS"] else 0)

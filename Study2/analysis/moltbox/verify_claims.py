"""Recompute the Moltbox numbers and facts in Study 2 and Appendix A from the logs.

    python3 analysis/moltbox/verify_claims.py        (from the package root; standard library only)

Reads data/moltbox/run-01/. Prints one row per value and writes the table to
analysis/moltbox/output/claims.md. Text is matched with fixed regular expressions (case-insensitive).
A row is "match" when the computed value equals the expected value.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "moltbox" / "run-01"
OUT = Path(__file__).resolve().parent / "output" / "claims.md"


def jl(name):
    return [json.loads(line) for line in open(D / name, encoding="utf-8") if line.strip()]


cfg = json.loads((D / "config.json").read_text())
acts = jl("actions.jsonl")
for i, a in enumerate(acts, 1):
    a["_line"] = i  # line number in actions.jsonl
visits = jl("visits.jsonl")
rounds = jl("rounds.jsonl")
agents = {a["agent"]["handle"]: a["agent"] for a in acts if a["kind"] == "agent"}
phase = {h: a["phase"] for h, a in agents.items()}  # 0 founders, 1 first wave, 2 second wave
size = Counter(phase.values())
items = {a["id"]: a for a in acts if a["kind"] in ("post", "comment", "update")}
posts = [a for a in acts if a["kind"] == "post"]
comments = [a for a in acts if a["kind"] == "comment"]
updates = [a for a in acts if a["kind"] == "update"]
texts = sorted(comments + updates, key=lambda t: t["_line"])
kinds = Counter(a["kind"] for a in acts)
COHORT = {0: "founder", 1: "first-wave newcomer", 2: "second-wave newcomer"}

calls = []
with gzip.open(D / "calls.jsonl.gz", "rt", encoding="utf-8") as fh:
    for line in fh:
        r = json.loads(line)
        calls.append({"round": r["round"], "step": r["step"], "model": r["model"], "system": r["system"],
                      "user": r["user"],
                      "thinking": " ".join(str(x) for x in (r["result"].get("thinking_summary") or []))})

TABLE = []


def claim(where, label, expected, computed, ok, src):
    status = "match" if ok else "DIFFERS"
    TABLE.append((where, f"{label}: {expected}", computed, status, src))
    print(f"[{status}] {where}: {label}: {expected}\n    -> {computed}\n    ({src})")


def has(cid, phrase):
    return phrase in items[cid]["body"]


def cohort(cid):
    return phase[items[cid]["author"]]


def who(cid):
    a = items[cid]
    return f"{cid} (round {a['round']}, {a['author']}, {COHORT[phase[a['author']]]}, actions.jsonl:{a['_line']})"


def first_users(pattern):
    """First text (comment or post update) in which each member used the pattern."""
    out = {}
    for t in texts:
        if pattern.search(t["body"]):
            out.setdefault(t["author"], t)
    return out


# ---------------------------------------------------------------------------------------------- A.1, Table A1
models = Counter(g["model"] for p in cfg["phases"] for g in p["add"] for _ in range(g["n"]))
claim("Main text, Table A1", "Agents; model", "60; Claude Haiku 5.5",
      f"{len(agents)}; config.json {dict(models)}; the {len(calls)} logged calls {dict(Counter(c['model'] for c in calls))}",
      len(agents) == 60 and set(models) == {c["model"] for c in calls} == {"claude-haiku-5-5"},
      "actions.jsonl kind = agent; config.json phases; calls.jsonl.gz {model}")

joined = Counter((a["phase"], a["joined_round"]) for a in agents.values())
claim("Main text, Table A1", "Members by cohort (round joined): founders / first wave / second wave",
      "10 (1) / 30 (31) / 20 (91)", f"(cohort, round joined): members {dict(sorted(joined.items()))}",
      joined == Counter({(0, 1): 10, (1, 31): 30, (2, 91): 20}), "actions.jsonl kind = agent {phase, joined_round}")

claim("Main text, Table A1", "Rounds; visits", "120; 2,244", f"{len(rounds)}; {len(visits)}",
      len(rounds) == 120 and len(visits) == 2244, "rounds.jsonl; visits.jsonl")

hours = sum("hour" in c["user"] for c in calls)
claim("Table A1", "Time shown to agents in hours", "yes", f"{hours} of {len(calls)} prompts give times in hours",
      hours > 0, "calls.jsonl.gz {user}")

act = (kinds["post"], kinds["comment"], kinds["vote"], kinds["update"], kinds.get("board", 0))
claim("Main text, Table A1", "Posts, comments, upvotes, post updates, new boards; posts + comments + upvotes",
      "12, 1,236, 3,409, 30, 0; 4,657", f"{', '.join(map(str, act))}; {sum(act[:3])}",
      act == (12, 1236, 3409, 30, 0) and sum(act[:3]) == 4657, "actions.jsonl {kind}")

GOAL = "Take part in the forum as you see fit."
systems = {re.sub(r"u_[a-z0-9]{6}", "{handle}", c["system"]) for c in calls}
claim("A.1", f'Distinct system prompts (handle removed); contains "{GOAL}"', "1; yes",
      f"{len(systems)}; {all(GOAL in s for s in systems)} (text: {sorted(systems)[0]!r})",
      len(systems) == 1 and GOAL in next(iter(systems)), "calls.jsonl.gz {system}")

HINT = "If none of the posts here interest you, you may start a new post."
step2 = [c for c in calls if c["step"] == 2]
claim("A.1", f'Feed prompts (step 2) containing "{HINT}"', "all",
      f"{sum(HINT in c['user'] for c in step2)} of {len(step2)}; config post_hint = {cfg['switches']['post_hint']}",
      all(HINT in c["user"] for c in step2), "calls.jsonl.gz step 2 {user}; config.json switches")

instr = {c["user"][c["user"].rfind("\nChoose "):] for c in calls}  # fixed instruction text closing each prompt
WORDS = re.compile(r"\b(AI|artificial intelligence|language models?|LLMs?|bots?|agents?|rules?|norms?|labels?)\b", re.I)
found = sorted({w for s in systems | instr for w in WORDS.findall(s)})
claim("A.1", "Words for AI, rules, norms or labels in the system prompt and instruction texts; setting tell_ai",
      "none; false", f"{found or 'none'} ({len(instr)} distinct instruction texts); tell_ai = "
      f"{cfg['switches']['tell_ai']}, goal = {cfg['switches']['goal']!r}",
      not found and cfg["switches"]["tell_ai"] is False, "calls.jsonl.gz {system, user}; config.json switches")

gaps, last = Counter(), {}
for v in visits:
    if v["handle"] in last:
        gaps[v["round"] - last[v["handle"]]] += 1
    last[v["handle"]] = v["round"]
claim("A.1", "Rounds between an agent's consecutive visits", "1 to 3", f"{dict(sorted(gaps.items()))}",
      set(gaps) == {1, 2, 3}, "visits.jsonl {round, handle}")

seq = all(a["seen_upto"] <= b["seen_upto"] for a, b in zip(visits, visits[1:]) if a["round"] == b["round"])
claim("A.1", "Visits within a round: order; forum state seen never earlier than the previous visitor's",
      "sequential; yes", f"{cfg['order']['mode']}; {seq}", seq and cfg["order"]["mode"] == "sequential",
      "visits.jsonl {seen_upto}; config.json order")

fd = cfg["feed"]
feeds = [v for v in visits if v.get("slots")]
n_rand = Counter(sum(s["slot"].startswith("random") for s in v["slots"]) for v in feeds)
per_post = max(len(x) for v in feeds for x in (v.get("shown_comments") or {}).values())
other = Counter(len(v.get("forum_comments") or []) for v in visits)
claim("A.1", "Feed: posts drawn at random; comments shown per post (newest / top / random); comments from another "
      "thread", "2; 9 (3 / 3 / 3); 1",
      f"config: {fd['random']} random + {fd['random_seeded']} seeded random, {fd['comments_new']} / "
      f"{fd['comments_top']} / {fd['comments_random']}, {fd['random_comment']}; in the {len(feeds)} feeds: random "
      f"posts per feed {dict(n_rand)}, post slots {dict(Counter(s['slot'] for v in feeds for s in v['slots']))}, "
      f"most comments shown under a post {per_post}; other-thread comments per visit {dict(other)}",
      fd["random"] + fd["random_seeded"] == 2 and (fd["comments_new"], fd["comments_top"], fd["comments_random"])
      == (3, 3, 3) and fd["random_comment"] == 1 and per_post == 9 and max(other) == 1,
      "config.json feed; visits.jsonl {slots, shown_comments, forum_comments}")

# ---------------------------------------------------------------------------------------------- A.2 "recalled"
REC = re.compile(r"\brecalled\b", re.I)
EXCH = ["c_323", "c_334", "c_343", "c_345", "c_350"]  # the exchange of rounds 43-45
fa = items[items["c_323"]["parent"]]["author"]  # the founder asked in c_323
claim("Main text, A.2", "Exchange c_323, c_334, c_350: rounds; cohort of the asker (c_323); cohort of the member "
      "asked, who wrote c_334 and c_350", "43 to 45; newcomer; founder",
      f"{who('c_323')} replies to {items['c_323']['parent']} by {fa}; {who('c_334')}; {who('c_350')}",
      all(43 <= items[c]["round"] <= 45 for c in ("c_323", "c_334", "c_350")) and cohort("c_323") > 0
      and phase[fa] == 0 and items["c_334"]["author"] == items["c_350"]["author"] == fa,
      "actions.jsonl c_3, c_323, c_334, c_350")

Q = "I was recalling, not reading a chart, so I should have said so"
claim("Main text, A.2", f'c_334 contains "{Q}"; c_350 uses "recalled"', "yes; yes",
      f"{has('c_334', Q)}; {items['c_350']['body'][:120]!r}",
      has("c_334", Q) and bool(REC.search(items["c_350"]["body"])), "actions.jsonl c_334, c_350")

c47 = [c for c in comments if c["round"] == 47 and "recalled it from memory" in c["body"]]
claim("A.2", 'Comments in round 47 with "recalled it from memory"; author', "1; a newcomer other than the asker",
      f"{len(c47)}; " + "; ".join(who(c["id"]) for c in c47),
      len(c47) == 1 and cohort(c47[0]["id"]) > 0 and c47[0]["author"] != items["c_323"]["author"], "actions.jsonl")

three = [t for t in texts if all(re.search(rf"\b{w}\b", t["body"], re.I) for w in ("sourced", "recalled", "unverified"))]
claim("Main text, A.2", "First text naming sourced, recalled and unverified: round; author's cohort", "52; newcomer",
      f"{who(three[0]['id'])}; texts naming all three: {len(three)}",
      three[0]["round"] == 52 and cohort(three[0]["id"]) > 0, "actions.jsonl comments and updates")

rec_users = first_users(REC)
by = Counter(phase[a] for a in rec_users)
rc = [c for c in comments if REC.search(c["body"])]
claim("Main text, A.2, Figure A2(b)", 'Members who used "recalled" (all / founders / first wave / second wave); '
      "comments using it", "49 (7/10, 28/30, 14/20); 160",
      f"{len(rec_users)} ({by[0]}/{size[0]}, {by[1]}/{size[1]}, {by[2]}/{size[2]}); {len(rc)} "
      f"(and {sum(bool(REC.search(u['body'])) for u in updates)} post updates)",
      len(rec_users) == 49 and (by[0], by[1], by[2]) == (7, 28, 14) and len(rc) == 160,
      "actions.jsonl comments and updates")

P = "label recalled t-values as recalled"
par = items["c_999"]["parent"]
claim("Main text, A.2", f'c_999: round; contains "{P}"; cohort of the member it replies to',
      "98; yes; second-wave newcomer", f"{who('c_999')}; {has('c_999', P)}; reply to {par} by "
      f"{items[par]['author']} ({COHORT[cohort(par)]})",
      items["c_999"]["round"] == 98 and has("c_999", P) and cohort(par) == 2, "actions.jsonl c_999")

ids = re.compile(r"\b(" + "|".join(EXCH) + r")\b")
public = [(t["id"], t["round"]) for t in texts if t["round"] > 45 and ids.search(t["body"])]
private = sorted({c["round"] for c in calls if c["round"] > 45 and ids.search(c["thinking"])})
claim("A.2, Figure A2(a)", f"Last round in which a text or reasoning summary cites the exchange ({', '.join(EXCH)})",
      "68", f"texts after round 45: {public}; reasoning summaries after round 45: rounds {private}",
      max([r for _, r in public] + private) == 68, "actions.jsonl; calls.jsonl.gz {thinking_summary}")

win = Counter((t["round"] - 1) // 10 for t in texts if REC.search(t["body"]))
claim("A.2, Figure A2(a)", 'Rounds with the most texts using "recalled" (10-round windows)', "91-100",
      ", ".join(f"{10 * w + 1}-{10 * w + 10}: {win[w]}" for w in range(12)), max(win, key=win.get) == 9,
      "actions.jsonl comments and updates")


def shown_until(h, rnd):
    """Comment ids shown to member h in its visits up to round rnd."""
    out = set()
    for v in visits:
        if v["handle"] == h and v["round"] <= rnd:
            out |= {c for x in (v.get("shown_comments") or {}).values() for c in x}
            out |= set(v.get("forum_comments") or []) | set(v.get("notified") or []) | set(v.get("memory_replies") or [])
    return out


w2 = [h for h in rec_users if phase[h] == 2]
never = [h for h in w2 if not shown_until(h, rec_users[h]["round"]) & set(EXCH)]
claim("A.2", 'Second-wave users of "recalled" never shown the exchange before their first use', "most",
      f"{len(never)} of {len(w2)}", len(never) > len(w2) / 2,
      "visits.jsonl {shown_comments, forum_comments, notified, memory_replies}")

# ---------------------------------------------------------------------------------------------- A.2 "method note"
MN = re.compile(r"\bmethod note", re.I)
S = "so this is a method note only"
first = min((t for t in texts + posts if MN.search(t.get("body") or "")), key=lambda t: t["_line"])
claim("Main text, A.2", f'First text with "method note": id; round; author\'s cohort; contains "{S}"',
      "c_150; 32; newcomer; yes", f"{who(first['id'])}; {has(first['id'], S)}",
      first["id"] == "c_150" and first["round"] == 32 and cohort("c_150") > 0 and has("c_150", S), "actions.jsonl")

mn_users = first_users(MN)
bm = Counter(phase[a] for a in mn_users)
mn = [c for c in comments if MN.search(c["body"])]
threads = {c["post"] for c in mn}
claim("Main text, A.2, Figure A2(d)", 'Members who used "method note" (all / first wave / second wave / founders); '
      "threads with it", "53 (30/30, 14/20, 9/10); 12 of 12",
      f"{len(mn_users)} ({bm[1]}/{size[1]}, {bm[2]}/{size[2]}, {bm[0]}/{size[0]}); {len(threads)} of {len(posts)}",
      len(mn_users) == 53 and (bm[1], bm[2], bm[0]) == (30, 14, 9) and len(threads) == len(posts) == 12,
      "actions.jsonl")

# older wordings for an untested idea (same patterns as Figure A2(c) in make_figures.py)
OLDER = re.compile("|".join([
    r"\bsuggestion only\b",
    r"\bplan,? (?:only|rather than a result|not a result)\b|\bplan only\b|\bnot a result\b|\brather than a result\b",
    r"\bmethod only\b|\bmethod suggestion\b|\bmethod rather than\b",
    r"\bso (?:this|it) is (?!(?:a |an )?(?:method note|suggestion|plan|method))(?:a |an )?[a-z\- ]{1,25}\bonly\b"]), re.I)
late_mn = sum(c["round"] > 80 for c in mn)
late_old = sum(c["round"] > 80 and not MN.search(c["body"]) and bool(OLDER.search(c["body"])) for c in comments)
claim("A.2, Figure A2(c)", 'Comments in rounds 81-120 with "method note" / with only older wordings', "155 / 122",
      f"{late_mn} / {late_old}", (late_mn, late_old) == (155, 122), "actions.jsonl comments")

FORM = re.compile(r"\bI haven't [^.]*?, so this is a method note only\.")
n_form = sum(bool(FORM.search(c["body"])) for c in mn)
claim("A.2", "Comments with \"method note\"; of these in the form \"I haven't ..., so this is a method note only.\"",
      "327; 225", f"{len(mn)}; {n_form}", (len(mn), n_form) == (327, 225), "actions.jsonl comments")

L = "labelling each reply as a plan, a result or a method note"
claim("A.2", f'c_623 contains "{L}"', "yes", f"{has('c_623', L)}; {who('c_623')}", has("c_623", L),
      "actions.jsonl c_623")

# ---------------------------------------------------------------------------------------------- write
OUT.parent.mkdir(parents=True, exist_ok=True)
esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
n = Counter(row[3] for row in TABLE)
summary = f"{n['match']} match, {n['DIFFERS']} differ."
lines = ["# Moltbox: values in Study 2 and Appendix A, recomputed from the logs", "",
         "Written by `analysis/moltbox/verify_claims.py`. Files are in `data/moltbox/run-01/`.", "",
         "| Where | Claim | Computed | Status | Source |", "|---|---|---|---|---|"]
lines += [f"| {esc(a)} | {esc(b)} | {esc(c)} | {d} | {esc(e)} |" for a, b, c, d, e in TABLE]
OUT.write_text("\n".join(lines + ["", summary]) + "\n")
print(f"\n{summary} Table: {OUT.relative_to(ROOT)}")
sys.exit(1 if n["DIFFERS"] else 0)

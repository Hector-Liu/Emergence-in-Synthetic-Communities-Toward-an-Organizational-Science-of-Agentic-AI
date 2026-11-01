"""Runner of the Babel pilot: one pair of agents, round by round, logged to logs/trial/<run>/.

The runs in data/babel/reported-runs/ were made with this script; the commands are in
software/babel/README.md. Without --mock it calls the Anthropic API and needs ANTHROPIC_API_KEY, from
the environment or from a .env file in software/babel/ (never committed).

  python3 scripts/quick_trial.py --mock --rounds 10          # scripted agents, no API key, no cost
  python3 scripts/quick_trial.py --model claude-sonnet-5-5 --scoring quarter --effort high \
      --notes-style three-part --note-words 300 --display-seed 104 --rounds 120 --budget 8 --max-declined 3
"""
import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from param_check import MIX, World, draw_tower, draw_world, strategies, tower_score  # noqa: E402

# model id -> USD per million input / output tokens (Haiku: prompts up to 100K tokens)
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}
COLOURS = ["red", "blue", "green", "yellow", "purple", "orange"]
SHAPES = ["cube", "ball", "cone", "ring", "star"]
CAP, RECENT, MAX_BLOCKS = 8, 8, 16
NOTE_OVER = 1.5  # replies run about 15% over a stated word limit; beyond 1.5 times the limit: one retry, then cut
TOLD = "The words have no meaning yet. Work out with the other participant how to use them."
NEW_PARTNER = ("You now work with a different participant from before. Your private notes, and your recent "
               "rounds until newer ones replace them, come from your time with the earlier participant.")
TRAINING = ((1, 10), None, 4, False, MIX)

INSTRUCTIONS = """You are one of two participants in a building task. The two of you take turns in two roles.

In each round there is a target tower. A tower is a stack of blocks, and each block has a colour and a shape.
- One of you sees the target and sends one message to the other.
- The other does not see the target. They receive only the message and build a tower.
In the next round you switch roles.

A message has at most 8 words. It may use only the 16 words in the list you are given. A word may be used more than once.{told}

{scoring}

After each round, both of you are shown the target, the message, the tower that was built and the score.

You keep private notes. Only you can read them. You rewrite them after each round."""

ARCHITECT = """This round you see the target.

Target tower, bottom to top:
{target}

Words you may use (the list is shuffled every time):
{word_list}

Your private notes:
{notes}

Your recent rounds, oldest first:
{records}

Reply with your message: at most 8 words from the list."""

BUILDER = """This round you do not see the target.

Message you received:
{message}

Colours a block can have (shuffled): {colours}
Shapes a block can have (shuffled): {shapes}

Words a message may use (the list is shuffled every time):
{word_list}

Your private notes:
{notes}

Your recent rounds, oldest first:
{records}

Reply with the tower you build, as a list of blocks from bottom to top."""

NOTES = """The round is over.

{record}

Words a message may use (the list is shuffled every time):
{word_list}

Your private notes before this round:
{notes}

Your earlier rounds, oldest first:
{records}

{notes_task}"""

# "free" asks for notes with no hint about their content. On Sonnet 5.5 at high effort the replies turned into
# strategy essays and 7% of these calls were declined (category reasoning_extraction). "settled" asks for the
# outcome only: what the agent now takes as settled, as a list.
NOTES_TASK = {
    "free": "Rewrite your private notes. At most {note_words} words. Only you will read them.",
    "settled": "Rewrite your private notes as a short list of what you now take as settled, one item per line. "
               "Write only the items themselves. At most {note_words} words. Only you will read them.",
    # proposed 2026-10-13, not yet run: keeps what the free notes had and the settled ones lost (gaps and plans)
    "three-part": "Rewrite your private notes in three parts, one item per line: what you now take as settled; "
                  "what is still open or not working; what you will try next. Write only the items themselves. "
                  "At most {note_words} words. Only you will read them.",
}

SCORING = {
    "exact": "Both of you get the same score for a round: the blocks that are right, divided by the height of the taller of the two towers (the target and the one that was built). A block is right only if the target has a block of the same colour and the same shape at the same height.",
    "quarter": "Both of you get the same score for a round. Each block that was built is compared with the target block at the same height: one point if the colour and the shape are both the same, and a quarter of a point if only one of the two is the same. The points are added up and divided by the height of the taller of the two towers (the target and the one that was built).",
    "half": "Both of you get the same score for a round. Each block that was built is compared with the target block at the same height: half a point if the colour is the same, and half a point if the shape is the same. The points are added up and divided by the height of the taller of the two towers (the target and the one that was built).",
}

RETRY = {
    "architect": "Your last reply could not be used. A message has 1 to 8 words, all from the list.",
    "builder": "Your last reply could not be used. A tower has 1 to 16 blocks, each with a colour and a shape from the lists.",
    "notes": "Your last reply could not be used. Your notes were too long.",
}
SCHEMAS = {
    "architect": {"type": "object", "properties": {"message": {"type": "array", "items": {"type": "string"}}},
                  "required": ["message"], "additionalProperties": False},
    "builder": {"type": "object", "properties": {"tower": {"type": "array", "items": {
        "type": "object", "properties": {"colour": {"type": "string"}, "shape": {"type": "string"}},
        "required": ["colour", "shape"], "additionalProperties": False}}},
        "required": ["tower"], "additionalProperties": False},
    "notes": {"type": "object", "properties": {"notes": {"type": "string"}},
              "required": ["notes"], "additionalProperties": False},
}


def make_vocabulary(rng, size=16):
    """CVCV words screened with the 2nd edition's rules; none starts with the
    first letter of a colour or shape name."""
    from vocab_rules import CONSONANTS, VOWELS, label_problems, set_problems
    banned = {x[0] for x in COLOURS + SHAPES}
    words = []
    while len(words) < size:
        w = rng.choice(CONSONANTS) + rng.choice(VOWELS) + rng.choice(CONSONANTS) + rng.choice(VOWELS)
        if w[0] in banned or w in words or label_problems(w.title()):
            continue
        if set_problems([x.title() for x in words + [w]]):
            continue
        words.append(w)
    return words


def show(tower):
    return ", ".join(f"{COLOURS[c]} {SHAPES[s]}" for c, s in tower)


def shuffled(rng, items):
    items = list(items)
    rng.shuffle(items)
    return ", ".join(items)


def record_line(role, target, message, built, score):
    """`target` and `built` are towers already written out with show()."""
    if role == "architect":
        return (f"You saw the target. Target: {target}. Your message: {' '.join(message)}. "
                f"The other built: {built}. Score: {score:.2f}.")
    return (f"You built. Message you received: {' '.join(message)}. You built: {built}. "
            f"Target: {target}. Score: {score:.2f}.")


def parse(kind, data, vocab, note_words=100, last_try=False):
    """Validated value, or None if the reply cannot be used. Notes that are still
    too long on the last try are cut, so that notes never stop being updated."""
    try:
        if kind == "architect":
            msg = [x for item in data["message"] for x in str(item).lower().split()]  # "a b" in one item is two words
            return msg if 1 <= len(msg) <= CAP and all(x in vocab for x in msg) else None
        if kind == "builder":
            tower = [(COLOURS.index(b["colour"].strip().lower()), SHAPES.index(b["shape"].strip().lower()))
                     for b in data["tower"]]
            return tuple(tower) if 1 <= len(tower) <= MAX_BLOCKS else None
        notes = str(data["notes"]).strip()
        words = notes.split()
        hard = int(note_words * NOTE_OVER)
        if len(words) <= hard:
            return notes
        return " ".join(words[:hard]) if last_try else None
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


class Llm:
    def __init__(self, log, instructions, model, note_words, effort):
        import anthropic
        self.instructions, self.model, self.note_words, self.effort = instructions, model, note_words, effort
        key = os.environ.get("ANTHROPIC_API_KEY")
        env = HERE.parent / ".env"  # optional, in software/babel/; .gitignore keeps it out of git
        if not key and env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
        self.client = anthropic.Anthropic(api_key=key, timeout=180, max_retries=4)
        self.log, self.cost, self.calls, self.tokens = log, 0.0, 0, {"in": 0, "out": 0}
        self.declined = 0

    def ask(self, kind, prompt, vocab, meta):
        """One call plus at most one retry. Returns the validated value or None."""
        for attempt in (0, 1):
            text = prompt if attempt == 0 else prompt + "\n\n" + RETRY[kind]
            t0 = time.time()
            r = self.client.messages.create(
                model=self.model, max_tokens=16000, system=self.instructions,
                messages=[{"role": "user", "content": text}],
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMAS[kind]}},
            )
            raw = "".join(b.text for b in r.content if b.type == "text")
            thinking = [getattr(b, "thinking", "") for b in r.content if b.type == "thinking"]
            usage = r.usage.model_dump()
            price_in, price_out = PRICES[self.model]
            cost = (r.usage.input_tokens * price_in + r.usage.output_tokens * price_out) / 1e6
            self.cost += cost
            self.calls += 1
            self.tokens["in"] += r.usage.input_tokens
            self.tokens["out"] += r.usage.output_tokens
            value = None
            if r.stop_reason == "refusal":
                self.declined += 1  # a declined call is not sent again (see the return below)
            elif r.stop_reason != "max_tokens":
                try:
                    value = parse(kind, json.loads(raw), vocab, self.note_words, last_try=attempt == 1)
                except json.JSONDecodeError:
                    value = None
            self.log.write(json.dumps({**meta, "kind": kind, "attempt": attempt, "prompt": text, "raw": raw,
                                       "valid": value is not None, "stop_reason": r.stop_reason,
                                       "stop_details": getattr(r, "stop_details", None),
                                       "thinking_summary": thinking, "usage": usage, "model": r.model,
                                       "seconds": round(time.time() - t0, 2), "cost": cost},
                                      ensure_ascii=False, default=str) + "\n")
            self.log.flush()
            if value is not None or r.stop_reason == "refusal":
                return value
        return None


class Mock:
    """Scripted pair that shares a colour+shape code from the start. Free; tests the pipeline."""
    def __init__(self, vocab):
        self.code = sorted(vocab)
        self.cost, self.calls, self.tokens, self.declined = 0.0, 0, {"in": 0, "out": 0}, 0

    def ask(self, kind, prompt, vocab, meta):
        self.calls += 1
        if kind == "architect":
            out = []
            for c, s in meta["target"][:CAP // 2]:
                out += [self.code[c], self.code[len(COLOURS) + s]]
            return out
        if kind == "builder":
            m = meta["message"]
            return tuple((self.code.index(m[i]), self.code.index(m[i + 1]) - len(COLOURS))
                         for i in range(0, len(m) - 1, 2))
        return "(mock notes)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=60)
    ap.add_argument("--budget", type=float, default=1.0, help="stop before a round once this many USD are spent")
    ap.add_argument("--seed", type=int, default=1, help="world: vocabulary, pieces, towers")
    ap.add_argument("--display-seed", type=int, help="shuffles of the lists in prompts; default seed + 1000. "
                    "Pairs of one world differ only in this and in the model's own sampling")
    ap.add_argument("--mock", action="store_true", help="scripted agents, no model calls")
    ap.add_argument("--told", action="store_true", help="add one sentence saying the words have no meaning yet")
    ap.add_argument("--model", choices=tuple(PRICES), default="claude-haiku-5-5")
    ap.add_argument("--scoring", choices=tuple(SCORING), default="exact")
    ap.add_argument("--note-words", type=int, default=100, help="word limit stated in the notes prompt")
    ap.add_argument("--notes-style", choices=tuple(NOTES_TASK), default="free")
    ap.add_argument("--effort", choices=("low", "medium", "high"), default="medium")
    ap.add_argument("--max-declined", type=int, help="stop as soon as more than this many calls have been declined "
                    "in this session (a resumed run counts only the calls it makes itself)")
    ap.add_argument("--swap", nargs=2, metavar="RUN_DIR:AGENT",
                    help="new partners: agent 0 starts with the memory of AGENT in the first run, agent 1 with "
                         "that of AGENT in the second (same world); they are told the partner is new")
    ap.add_argument("--start-tower", type=int, default=0, help="index of the first tower of the world to use")
    ap.add_argument("--resume", help="log directory of a stopped run; give the same options as before")
    args = ap.parse_args()

    world_rng = random.Random(args.seed)
    display_seed = args.seed + 1000 if args.display_seed is None else args.display_seed
    show_rng = random.Random(display_seed)
    w = World(len(COLOURS), len(SHAPES), 3, 16, CAP, args.scoring)
    w_exact = World(len(COLOURS), len(SHAPES), 3, 16, CAP, "exact")
    vocab = make_vocabulary(world_rng)
    _, train, chunks = draw_world(world_rng, w)
    towers = [draw_tower(world_rng, train, chunks, TRAINING)[0] for _ in range(args.start_tower + args.rounds)]
    towers = towers[args.start_tower:]
    ways = strategies(w, random.Random(0), train, chunks, 0, with_alt=False)
    block_by_block = ways["colour+shape, block by block"][1]
    with_counts = ways["colour+shape + counts"][1]

    instructions = INSTRUCTIONS.format(told=" " + TOLD if args.told else "", scoring=SCORING[args.scoring])
    sources = []
    if args.swap:
        instructions += "\n\n" + NEW_PARTNER
        for spec in args.swap:
            run_dir, agent = spec.rsplit(":", 1)
            sources.append({"run": Path(run_dir).name, "path": run_dir, "agent": int(agent)})
    out = HERE.parent / "logs" / "trial" / (time.strftime("%Y%m%d-%H%M%S") + ("-mock" if args.mock else "") + ("-told" if args.told else "")
                                           + ("-sonnet" if "sonnet" in args.model else "")
                                           + ("" if args.scoring == "exact" else "-" + args.scoring)
                                           + ("" if args.effort == "medium" else "-" + args.effort)
                                           + ("" if args.notes_style == "free" else "-" + args.notes_style)
                                           + ("" if args.display_seed is None else f"-p{args.display_seed}")
                                           + "".join(f"-{'ab'[i]}{s['run'].rsplit('-', 1)[-1]}a{s['agent']}"
                                                     for i, s in enumerate(sources)))
    if args.resume:
        out = Path(args.resume)
    else:
        out.mkdir(parents=True)
    (out / "world.json").write_text(json.dumps({
        "seed": args.seed, "display_seed": display_seed, "vocabulary": vocab, "pieces": [show(c) for c in chunks],
        "towers": [show(t) for t in towers], "model": "mock" if args.mock else args.model, "told": args.told, "scoring": args.scoring, "effort": args.effort, "notes_style": args.notes_style,
        "note_words": args.note_words, "start_tower": args.start_tower,
        "swap": [{"run": s["run"], "agent": s["agent"]} for s in sources] or None,
        "instructions": instructions}, indent=1))
    agents = [{"notes": "", "records": []}, {"notes": "", "records": []}]
    for ag, src in zip(agents, sources):  # memory each agent brings from its earlier pair
        for row in (json.loads(line) for line in open(Path(src["path"]) / "rounds.jsonl")):
            if not row["void"]:
                role = "architect" if row["architect"] == src["agent"] else "builder"
                ag["records"].append(record_line(role, row["target"], row["message"], row["built"], row["score"]))
                ag["notes"] = row["notes"][src["agent"]]
    done, spent = [], []
    if args.resume:  # rebuild both memories from the log
        done = [json.loads(line) for line in open(out / "rounds.jsonl")]
        spent = [json.loads(line) for line in open(out / "calls.jsonl")]
        for row in done:
            assert row["target"] == show(towers[row["round"] - 1]), "not the same world as the stopped run"
            if not row["void"]:
                a = row["architect"]
                agents[a]["records"].append(record_line("architect", row["target"], row["message"], row["built"], row["score"]))
                agents[1 - a]["records"].append(record_line("builder", row["target"], row["message"], row["built"], row["score"]))
                for ag, notes in zip(agents, row["notes"]):
                    ag["notes"] = notes
    calls = open(out / "calls.jsonl", "a")
    rounds = open(out / "rounds.jsonl", "a")
    model = Mock(vocab) if args.mock else Llm(calls, instructions, args.model, args.note_words, args.effort)
    model.calls += len(spent)
    model.cost += sum(c["cost"] for c in spent)
    model.declined += sum(c["stop_reason"] == "refusal" for c in spent)
    declined_before = model.declined
    for c in spent:
        model.tokens["in"] += c["usage"]["input_tokens"]
        model.tokens["out"] += c["usage"]["output_tokens"]
    print(f"vocabulary: {' '.join(vocab)}\nlog: {out}\n")

    def view(agent, exclude_last=False):
        recs = agent["records"][:-1] if exclude_last else agent["records"]
        return {"notes": agent["notes"] or "(none yet)", "records": "\n".join(recs[-RECENT:]) or "(none yet)",
                "word_list": shuffled(show_rng, vocab)}

    for r, target in enumerate(towers):
        if r < len(done) and args.resume:
            shuffled(show_rng, vocab)
            if done[r]["message"]:
                shuffled(show_rng, COLOURS)
                shuffled(show_rng, SHAPES)
                shuffled(show_rng, vocab)
            if not done[r]["void"]:
                shuffled(show_rng, vocab)
                shuffled(show_rng, vocab)
            continue
        if model.cost >= args.budget:
            print(f"budget of ${args.budget} reached before round {r + 1}; stopping")
            break
        a, b = agents[r % 2], agents[1 - r % 2]
        meta = {"round": r + 1, "world_round": args.start_tower + r + 1, "target": target}
        message = model.ask("architect", ARCHITECT.format(target=show(target), **view(a)), vocab,
                            {**meta, "agent": r % 2})
        built = None
        if message:
            built = model.ask("builder", BUILDER.format(
                message=" ".join(message), colours=shuffled(show_rng, COLOURS), shapes=shuffled(show_rng, SHAPES),
                **view(b)), vocab, {**meta, "agent": 1 - r % 2, "message": message})
        row = {"round": r + 1, "world_round": args.start_tower + r + 1, "architect": r % 2,
               "height": len(target), "target": show(target),
               "message": message, "built": show(built) if built else None, "void": built is None,
               "ref_block_by_block": tower_score(w, block_by_block(target)[0], target),
               "ref_counts": tower_score(w, with_counts(target)[0], target)}
        if built is not None:
            row["score"] = score = tower_score(w, built, target)
            row["exact"] = tower_score(w_exact, built, target)
            for agent, role in ((a, "architect"), (b, "builder")):
                agent["records"].append(record_line(role, show(target), message, show(built), score))
            with ThreadPoolExecutor(2) as pool:
                jobs = [pool.submit(model.ask, "notes", NOTES.format(record=ag["records"][-1],
                                                                     notes_task=NOTES_TASK[args.notes_style].format(
                                                                         note_words=args.note_words),
                                                                     **view(ag, exclude_last=True)),
                                    vocab, {**meta, "agent": i}) for i, ag in enumerate(agents)]
            for ag, job in zip(agents, jobs):
                ag["notes"] = job.result() if job.result() is not None else ag["notes"]
            row["notes"] = [ag["notes"] for ag in agents]
        done.append(row)
        rounds.write(json.dumps(row, ensure_ascii=False) + "\n")
        rounds.flush()
        print(f"{r + 1:>3} h={len(target):<2} {' '.join(message) if message else '(void)':<44} "
              f"{'void' if built is None else format(row['score'], '.2f'):>5}   spent ${model.cost:.3f}", flush=True)
        if args.max_declined is not None and model.declined - declined_before > args.max_declined:
            print(f"more than {args.max_declined} declined calls; stopping")
            break
        if model.declined >= 6 and model.declined > 0.05 * model.calls:
            print("more than 5% of calls declined; stopping")
            break

    valid = [x for x in done if not x["void"]]
    print(f"\nrounds {len(done)}, void {len(done) - len(valid)}, calls {model.calls}, declined {model.declined}, "
          f"tokens in/out {model.tokens['in']}/{model.tokens['out']}, cost ${model.cost:.3f}")
    if model.calls and not args.mock:
        print(f"per call: {model.tokens['in'] / model.calls:.0f} in, {model.tokens['out'] / model.calls:.0f} out, "
              f"${model.cost / model.calls:.5f}")
    print(f"\nscoring shown to the agents: {args.scoring}")
    print(f"{'rounds':<10}{'short (h<=4)':>14}{'tall (h>=5)':>14}{'tall: block by block':>22}"
          f"{'tall: with counts':>19}{'short, exact':>14}{'tall, exact':>13}{'words/msg':>11}")
    for i in range(0, len(done), 10):
        part = [x for x in done[i:i + 10] if not x["void"]]
        short = [x["score"] for x in part if x["height"] <= 4]
        tall = [x for x in part if x["height"] >= 5]
        cell = lambda v: f"{mean(v):.2f}" if v else "-"  # noqa: E731
        print(f"{f'{i + 1}-{i + 10}':<10}{cell(short):>14}{cell([x['score'] for x in tall]):>14}"
              f"{cell([x['ref_block_by_block'] for x in tall]):>22}{cell([x['ref_counts'] for x in tall]):>19}"
              f"{cell([x['exact'] for x in part if x['height'] <= 4]):>14}{cell([x['exact'] for x in tall]):>13}"
              f"{cell([len(x['message']) for x in part]):>11}")
    summary = {"rounds": len(done), "void": len(done) - len(valid), "calls": model.calls, "cost": model.cost,
               "tokens": model.tokens, "final_notes": [ag["notes"] for ag in agents]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    for i, ag in enumerate(agents):
        print(f"\nfinal notes, agent {i}:\n{ag['notes']}")


if __name__ == "__main__":
    main()

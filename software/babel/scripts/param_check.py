"""Offline parameter check for the Babel tower design (no model calls, stdlib only).

It reports the score that different ways of talking would earn if both agents
used them perfectly. The design needs these ways to be separable by score:

  - a lookup table of whole-block names must fall short once block types
    outnumber words, and must fail on block types never seen in training;
  - block-by-block description must fall short once towers outgrow the cap;
  - ways of talking that need no abstraction (builder padding, colour only)
    must not close that gap.

This only checks that the separation exists. It says nothing about what the
agents will actually do.

Usage: python3 scripts/param_check.py                          # SPEC v0.2: mixed heights from round one
       python3 scripts/param_check.py --design staged --gate   # SPEC v0.1: three stages and a gate
       python3 scripts/param_check.py --colors 5 --shapes 5 --cap 8 --scoring half
"""
import argparse
import random
from collections import Counter
from dataclasses import dataclass
from statistics import mean

N_CHUNKS, CHUNK_LEN, ALT_LEN = 4, 3, 4
COUNTS = (2, 3, 4)
MIX = {"run": 0.45, "chunk": 0.30, "single": 0.25}
MIX_STAGED = {"run": 0.40, "chunk": 0.30, "alt": 0.10, "single": 0.20}
MIX_STAGED_BEYOND = {"run": 0.60, "chunk": 0.25, "alt": 0.05, "single": 0.10}

# column -> (height range, segments per tower, max run length, uses held-out block types, segment weights)
# segments per tower None: every height in the range is equally likely
DESIGNS = {
    "mixed": {
        "short (h 1-4)": ((1, 4), None, 4, False, MIX),
        "tall (h 5-10)": ((5, 10), None, 4, False, MIX),
        "new blocks (h 2-4)": ((2, 4), None, 4, True, MIX),
        "taller (h 11-14)": ((11, 14), None, 4, False, MIX),
    },
    "staged": {
        "1 words (h 1-2)": ((1, 2), (1,), 2, False, MIX_STAGED),
        "2 phrases (h 3-4)": ((3, 4), (1, 2), 3, False, MIX_STAGED),
        "3 long (h 5-10)": ((5, 10), (2, 3, 3, 4), 4, False, MIX_STAGED),
        "P2 held-out types (h 2-4)": ((2, 4), (1, 2), 3, True, MIX_STAGED),
        "P4 beyond (h 11-14, runs to 6)": ((11, 14), (3, 4, 4, 5), 6, False, MIX_STAGED_BEYOND),
    },
}
GATED_STAGES = ("1 words (h 1-2)", "2 phrases (h 3-4)")


@dataclass(frozen=True)
class World:
    colors: int
    shapes: int
    held_out: int
    vocab: int
    cap: int
    scoring: str  # "exact": a block counts only if colour and shape are both right; "half": half credit each;
    #               "quarter": a quarter of a point if only one of the two is right

    @property
    def blocks(self):
        return [(c, s) for c in range(self.colors) for s in range(self.shapes)]


def draw_world(rng, w):
    """Held-out block types and the fixed chunks of one world. Every colour and
    shape still occurs among the training types."""
    while True:
        held = set(rng.sample(w.blocks, w.held_out))
        train = [b for b in w.blocks if b not in held]
        if len({c for c, _ in train}) == w.colors and len({s for _, s in train}) == w.shapes:
            break
    chunks = set()
    while len(chunks) < N_CHUNKS:
        c = tuple(rng.choice(train) for _ in range(CHUNK_LEN))
        if len(set(c)) >= 2:
            chunks.add(c)
    return held, train, sorted(chunks)


def draw_tower(rng, pool, chunks, spec):
    """One tower and the kinds of the segments it was made of."""
    (lo, hi), n_segments, run_max, _, seg_weights = spec
    kinds, weights = zip(*seg_weights.items())
    while True:
        height = rng.randint(lo, hi) if n_segments is None else None
        tower, made = [], []
        todo = rng.choice(n_segments) if n_segments else None
        while (len(tower) < height) if todo is None else (len(made) < todo):
            kind = rng.choices(kinds, weights)[0]
            made.append(kind)
            if kind == "run":
                tower += [rng.choice(pool)] * rng.randint(2, run_max)
            elif kind == "chunk":
                tower += list(rng.choice(chunks))
            elif kind == "alt":
                a, b = rng.sample(pool, 2)
                tower += [a, b] * (ALT_LEN // 2)
            else:
                tower.append(rng.choice(pool))
        if (len(tower) == height) if todo is None else (lo <= len(tower) <= hi):
            return tuple(tower), made


def block_score(w, built, target):
    if built == target:
        return 1.0
    if w.scoring == "half":
        return 0.5 * (built[0] == target[0]) + 0.5 * (built[1] == target[1])
    if w.scoring == "quarter":
        return 0.25 * ((built[0] == target[0]) or (built[1] == target[1]))
    return 0.0


def tower_score(w, built, target):
    """Level-by-level match, divided by the height of the taller tower."""
    if not built:
        return 0.0
    n = min(len(built), len(target))
    return sum(block_score(w, built[i], target[i]) for i in range(n)) / max(len(built), len(target))


def best_prefix(tower, cap, per_block, run_lengths=(), chunks=(), alt=False):
    """Longest bottom prefix a code can describe exactly within `cap` words,
    and the number of words that description takes."""
    h = len(tower)
    cost = [0] + [float("inf")] * h
    for i in range(h):
        cost[i + 1] = min(cost[i + 1], cost[i] + per_block)
        for n in run_lengths:
            if i + n <= h and len(set(tower[i:i + n])) == 1:
                cost[i + n] = min(cost[i + n], cost[i] + 1 + per_block)
        if chunks and tower[i:i + CHUNK_LEN] in chunks:
            cost[i + CHUNK_LEN] = min(cost[i + CHUNK_LEN], cost[i] + 1)
        if alt and i + ALT_LEN <= h:
            a, b = tower[i], tower[i + 1]
            if a != b and tower[i:i + ALT_LEN] == (a, b) * (ALT_LEN // 2):
                cost[i + ALT_LEN] = min(cost[i + ALT_LEN], cost[i] + 1 + 2 * per_block)
    k = max(i for i, c in enumerate(cost) if c <= cap)
    return k, cost[k]


def strategies(w, rng, train, chunks, typical_height, with_alt):
    """name -> (words needed, function tower -> (built tower, words in the message)).
    All assume both agents already share the code perfectly."""
    chunk_set = set(chunks)
    named = set(train[:w.vocab])                  # table: one name per block type, as many as there are words
    named_c = set(train[:w.vocab - len(COUNTS)])  # table that keeps three words for counts
    feat = w.colors + w.shapes
    fit = max(0, min(N_CHUNKS, w.vocab - feat - len(COUNTS)))  # chunk names that still fit in the vocabulary

    def guess(t):
        return tuple(rng.choice(w.blocks) for _ in range(typical_height)), 0

    def table(names):
        def build(t):
            out = []
            for b in t[:w.cap]:
                if b in names:
                    out.append(b)
                else:  # say the name of some named block of the same colour, if any
                    same = [x for x in names if x[0] == b[0]]
                    out.append(same[0] if same else next(iter(names)))
            return tuple(out), len(out)
        return build

    def table_counts(t):
        out, words, i = [], 0, 0
        while i < len(t) and words < w.cap:
            b = t[i]
            said = b if b in named_c else next((x for x in named_c if x[0] == b[0]), next(iter(named_c)))
            n = 1
            while i + n < len(t) and t[i + n] == b and n < max(COUNTS):
                n += 1
            if n >= 2 and words + 2 <= w.cap:
                out += [said] * n
                words += 2
                i += n
            else:
                out.append(said)
                words += 1
                i += 1
        return tuple(out), words

    def exact(per_block, run_lengths=(), ch=(), alt=False, pad=False):
        def build(t):
            k, words = best_prefix(t, w.cap, per_block, run_lengths, ch, alt)
            out = list(t[:k])
            if pad and out and words == w.cap:  # a full message may have been cut off
                out += [out[-1]] * max(0, typical_height - len(out))
            return tuple(out), words
        return build

    def colour_only(t):
        return tuple((b[0], 0) for b in t[:w.cap]), min(len(t), w.cap)

    ways = {
        "no shared code: builder guesses": (0, guess),
        "table: one name per block type": (w.vocab, table(named)),
        "table + count words": (w.vocab, table_counts),
        "colour words only, builder guesses shape": (w.colors, colour_only),
        "colour+shape, block by block": (feat, exact(2)),
        "colour+shape, builder pads a full message": (feat, exact(2, pad=True)),
        "colour+shape + counts": (feat + len(COUNTS), exact(2, COUNTS)),
        f"colour+shape + counts + {fit} chunk names (fits)": (feat + len(COUNTS) + fit,
                                                           exact(2, COUNTS, set(chunks[:fit]))),
        "colour+shape + counts + 4 chunk names": (feat + len(COUNTS) + N_CHUNKS, exact(2, COUNTS, chunk_set)),
    }
    if with_alt:
        ways["colour+shape + counts + chunks + alternation"] = (feat + len(COUNTS) + N_CHUNKS + 1,
                                                                exact(2, COUNTS, chunk_set, True))
    return ways


def gate_check(w, rng, stages, window, threshold, max_rounds, noise, runs):
    """Stage gate (SPEC v0.1): a pair moves on once its mean score over the last
    `window` rounds reaches `threshold`. Reports how often a pair that only has
    a table of whole-block names gets through by luck, and how often a pair
    with a colour+shape code gets through when it gets each block wrong with
    probability `noise`."""
    def first_pass(scores):
        for r in range(window, len(scores) + 1):
            if mean(scores[r - window:r]) >= threshold:
                return r
        return None

    print(f"stage gate: mean score >= {threshold} over the last {window} rounds, at most {max_rounds} rounds per stage; "
          f"{runs} simulated pairs")
    print(f"{'stage':<20}{'pair':<44}{'passes':>8}{'median round':>14}")
    for stage in GATED_STAGES:
        lo, hi = stages[stage][0]
        passed = {"table of block names": [], f"colour+shape, {noise:.0%} of blocks wrong": []}
        for _ in range(runs):
            _, train, chunks = draw_world(rng, w)
            rng.shuffle(train)
            strat = strategies(w, rng, train, chunks, (lo + hi + 1) // 2, with_alt=True)
            table = strat["table: one name per block type"][1]
            literal = strat["colour+shape, block by block"][1]
            towers = [draw_tower(rng, train, chunks, stages[stage])[0] for _ in range(max_rounds)]
            passed["table of block names"].append(first_pass([tower_score(w, table(t)[0], t) for t in towers]))
            noisy = []
            for t in towers:
                built = tuple(rng.choice([x for x in w.blocks if x != b]) if rng.random() < noise else b
                              for b in literal(t)[0])
                noisy.append(tower_score(w, built, t))
            passed[f"colour+shape, {noise:.0%} of blocks wrong"].append(first_pass(noisy))
        for name, rounds in passed.items():
            ok = sorted(r for r in rounds if r is not None)
            med = str(ok[len(ok) // 2]) if ok else "-"
            print(f"{stage.split(' (')[0]:<20}{name:<44}{len(ok) / runs:>8.0%}{med:>14}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", choices=tuple(DESIGNS), default="mixed")
    ap.add_argument("--colors", type=int, default=6)
    ap.add_argument("--shapes", type=int, default=5)
    ap.add_argument("--held-out", type=int, default=3)
    ap.add_argument("--vocab", type=int, default=16)
    ap.add_argument("--cap", type=int, default=8)
    ap.add_argument("--scoring", choices=("exact", "half", "quarter"), default="exact")
    ap.add_argument("--worlds", type=int, default=100)
    ap.add_argument("--towers", type=int, default=200, help="towers per world per column")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--gate", action="store_true", help="also simulate the stage gate (staged design only)")
    ap.add_argument("--gate-window", type=int, default=30)
    ap.add_argument("--gate-threshold", type=float, default=0.85)
    ap.add_argument("--gate-max-rounds", type=int, default=80)
    ap.add_argument("--gate-noise", type=float, default=0.15)
    args = ap.parse_args()
    w = World(args.colors, args.shapes, args.held_out, args.vocab, args.cap, args.scoring)
    stages = DESIGNS[args.design]
    with_alt = args.design == "staged"
    rng = random.Random(args.seed)

    scores, words_used, right = {}, {}, {}
    need = {}
    heights = {s: [] for s in stages}
    mix = {s: Counter() for s in stages}
    for _ in range(args.worlds):
        held, train, chunks = draw_world(rng, w)
        rng.shuffle(train)
        for stage, spec in stages.items():
            (lo, hi), _, _, uses_held, _ = spec
            strat = strategies(w, rng, train, chunks, (lo + hi + 1) // 2, with_alt)
            for _ in range(args.towers):
                t, made = draw_tower(rng, train, chunks, spec)
                mix[stage].update(made)
                if uses_held:  # swap one block for a held-out type
                    i = rng.randrange(len(t))
                    t = t[:i] + (rng.choice(sorted(held)),) + t[i + 1:]
                heights[stage].append(len(t))
                for name, (words, build) in strat.items():
                    need[name] = words
                    built, said = build(t)
                    s = tower_score(w, built, t)
                    scores.setdefault((name, stage), []).append(s)
                    words_used.setdefault((name, stage), []).append(said)
                    right.setdefault((name, stage), []).append(s * max(len(built), len(t)))

    short = [s.split(" (")[0] for s in stages]
    kinds = list(next(iter(stages.values()))[4])
    print(f"design: {args.design}")
    print(f"world: {w.colors} colours x {w.shapes} shapes = {len(w.blocks)} block types, "
          f"{w.held_out} held out of training; vocabulary {w.vocab} words; cap {w.cap} words; scoring: {w.scoring}")
    print(f"{args.worlds} worlds x {args.towers} towers per column, seed {args.seed}")
    print()
    print(f"{'towers':<20}{'mean height':>12}   segments actually drawn")
    for s, name in zip(stages, short):
        total = sum(mix[s].values())
        print(f"{name:<20}{mean(heights[s]):>12.1f}   "
              + ", ".join(f"{k} {mix[s][k] / total:.0%}" for k in kinds))
    print()
    print(f"{'way of talking':<46}{'words':>6}  " + "".join(f"{s:>20}" for s in short))
    for name in need:
        flag = "*" if need[name] > w.vocab else ""
        print(f"{name:<46}{str(need[name]) + flag:>6}  "
              + "".join(f"{mean(scores[(name, s)]):>20.2f}" for s in stages))
    print()
    print("cells: mean score if both agents share that way of talking perfectly")
    print("*    : needs more words than the vocabulary has")
    if args.design == "mixed":
        tall = "tall (h 5-10)"
        print()
        print(f"{'on tall towers':<46}{'words per message':>18}{'right blocks per word':>23}")
        for name in need:
            said = sum(words_used[(name, tall)])
            if said:
                print(f"{name:<46}{said / len(words_used[(name, tall)]):>18.1f}{sum(right[(name, tall)]) / said:>23.2f}")
    if args.gate and args.design == "staged":
        print()
        gate_check(w, rng, stages, args.gate_window, args.gate_threshold, args.gate_max_rounds, args.gate_noise,
                   runs=1000)


if __name__ == "__main__":
    main()

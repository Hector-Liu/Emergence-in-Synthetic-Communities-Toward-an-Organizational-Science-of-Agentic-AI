"""Figures B1-B3 of the appendix (English, print format), in the same style as the Moltbox
figures (analysis/moltbox/make_figures.py): Times, black and grey, white boxes with thin rules,
bold band labels, 7.2 in wide.

    python3 analysis/babel/make_figures.py      (from the package root; needs matplotlib)

Figure B1: research design (flow chart).
Figure B2: the four rudimentary languages the pairs built, each with one real round from the logs
           (data/babel/reported-runs: pair 4 = p104 round 120, pair 1 = p101 round 62, pair 2 = p102 round 92,
           pair 3 = p103 round 39).
Figure B3: an agent from the weakest pair re-paired with a stronger partner (p103, p104, p203, p202).
Writes figB1_babel_design, figB2_babel_languages and figB3_babel_exchange (.pdf .png .svg) to
analysis/babel/output/figures/.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parent / "output" / "figures"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 8.5, "pdf.fonttype": 42, "svg.fonttype": "none",
})
INK, MID, RULE, FILL = "#111111", "#6b6b6b", "#b5b5b5", "#f2f2f2"
# block colours carry information (the agents talk about them), so they stay in colour
BLOCK = {"red": "#c9403a", "blue": "#3462c0", "green": "#378c55", "yellow": "#dcae17",
         "purple": "#8150bd", "orange": "#dc6f1b"}


def save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{stem}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / stem, "(.pdf .png .svg)")


def canvas(w, h):
    """A figure whose data coordinates are inches, origin at the top left."""
    fig, ax = plt.subplots(figsize=(w, h))
    plt.subplots_adjust(0, 0, 1, 1)
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis("off")
    return fig, ax


def band(ax, x, y, label):
    ax.text(x, y, label, fontsize=9, fontweight="bold", va="bottom", ha="left", color=INK)


def box(ax, x, y, w, h, title, lines, fill=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.07", linewidth=0.8,
                                edgecolor=INK, facecolor=FILL if fill else "white"))
    ax.text(x + 0.11, y + 0.12, title, fontsize=8.5, fontweight="bold", va="top", ha="left", color=INK)
    ax.text(x + 0.11, y + 0.36, "\n".join(lines), fontsize=7.6, va="top", ha="left", color=INK, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, rad=0.0, colour=INK):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=8, linewidth=0.8, color=colour,
                                 connectionstyle=f"arc3,rad={rad}"))


def block(ax, x, y, colour, shape, s=0.2):
    """One block: a square in its colour with a mark for its shape (x, y = top left)."""
    ax.add_patch(FancyBboxPatch((x, y), s, s, boxstyle=f"round,pad=0,rounding_size={s * 0.14}", linewidth=0,
                                facecolor=BLOCK[colour]))
    cx, cy, r = x + s / 2, y + s / 2, s * 0.26
    ink = "#2a2400" if colour == "yellow" else "white"
    if shape == "cube":
        ax.add_patch(Rectangle((cx - r, cy - r), 2 * r, 2 * r, facecolor=ink, linewidth=0))
    elif shape == "ball":
        ax.add_patch(Circle((cx, cy), r, facecolor=ink, linewidth=0))
    elif shape == "ring":
        ax.add_patch(Circle((cx, cy), r * 0.9, facecolor="none", edgecolor=ink, linewidth=s * 7))
    elif shape == "cone":  # y grows downwards
        ax.add_patch(Polygon([(cx, cy - r * 1.1), (cx + r * 1.05, cy + r * 0.9), (cx - r * 1.05, cy + r * 0.9)],
                             facecolor=ink, linewidth=0))
    elif shape == "star":
        pts = [(cx + (r * 1.18 if k % 2 == 0 else r * 0.5) * math.cos(-math.pi / 2 + k * math.pi / 5),
                cy + (r * 1.18 if k % 2 == 0 else r * 0.5) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
        ax.add_patch(Polygon(pts, facecolor=ink, linewidth=0))


def tower(ax, cx, y_bottom, blocks, s=0.2, gap=0.025):
    """Blocks stacked upwards from y_bottom, the first block at the bottom."""
    for i, (c, sh) in enumerate(blocks):
        block(ax, cx - s / 2, y_bottom - (i + 1) * s - i * gap, c, sh, s)


def word(ax, x, y, w, text, h=0.22):
    """A word of the agents' vocabulary: a light chip with the word in italics."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.04", linewidth=0.5,
                                edgecolor=RULE, facecolor=FILL))
    ax.text(x + w / 2, y + h / 2 + 0.005, text, fontsize=8.2, style="italic", ha="center", va="center", color=INK)


# ------------------------------------------------------------------ Figure B1: design
def figure_design():
    W, H = 7.2, 4.46
    fig, ax = canvas(W, H)
    target = [("yellow", "cone"), ("yellow", "ring"), ("green", "star"), ("purple", "ball")]

    # a: one round, in four steps
    band(ax, 0, 0.2, "(a) One round")
    gap, top, bh = 0.24, 0.28, 2.05
    bw = (W - 3 * gap) / 4
    steps = [("1  The describer sees", "a target tower", ["1 to 10 blocks, each one of", "6 colours × 5 shapes;", "a new target every round"]),
             ("2  It sends one", "message", ["At most 8 words, chosen", "only from 16 meaningless", "words"]),
             ("3  The builder", "rebuilds the tower", ["It sees only the message,", "never the target"]),
             ("4  Both see", "the result", ["Each then rewrites its", "private notes"])]
    for i, (t1, t2, foot) in enumerate(steps):
        x = i * (bw + gap)
        ax.add_patch(FancyBboxPatch((x, top), bw, bh, boxstyle="round,pad=0,rounding_size=0.07", linewidth=0.8,
                                    edgecolor=INK, facecolor="white"))
        ax.text(x + 0.1, top + 0.11, t1 + "\n   " + t2, fontsize=8.5, fontweight="bold", va="top", ha="left",
                color=INK, linespacing=1.2)
        ax.text(x + bw / 2, top + bh - 0.1, "\n".join(foot), fontsize=7.2, va="bottom", ha="center", color=MID,
                linespacing=1.3)
        if i < 3:
            arrow(ax, x + bw + 0.02, top + bh / 2, x + bw + gap - 0.02, top + bh / 2)
    tower(ax, bw / 2, top + 1.42, target, 0.2)
    tower(ax, 2 * (bw + gap) + bw / 2, top + 1.42, target, 0.2)
    x2 = bw + gap
    for j, wd in enumerate("zeki fidi zeki vepu dobo fuza tido loku".split()):
        word(ax, x2 + 0.09 + (j % 4) * 0.36, top + 0.66 + (j // 4) * 0.3, 0.33, wd)
    x4 = 3 * (bw + gap)
    ax.text(x4 + bw / 2, top + 0.6, "Score: share of blocks\nwith the right colour\nand shape", fontsize=7.6,
            ha="center", va="top", color=INK, linespacing=1.3)
    ax.text(x4 + bw / 2, top + 1.3, "1.00", fontsize=16, fontweight="bold", ha="center", va="center", color=INK)
    ax.text(x4 + bw / 2, top + 1.5, "in this example", fontsize=7, ha="center", va="center", color=MID)
    arrow(ax, x4 + bw / 2, top + bh + 0.02, bw / 2, top + bh + 0.02, rad=-0.1)  # y points down: negative bends below
    ax.text(W / 2, top + bh + 0.36, "next round: the two agents swap roles", fontsize=7.2, ha="center", va="top",
            color=MID, style="italic")

    # b: schedule
    by = top + bh + 0.78
    band(ax, 0, by, "(b) Schedule")
    sw, sh, sy = (W - 0.5) / 2, 1.22, by + 0.08
    cols = [(0, "Rounds 1–120", "Four pairs, each starting from nothing", "Same 16 words and same towers for every pair"),
            (sw + 0.5, "Rounds 121–180", "Partners exchanged across pairs", "Each agent keeps its own notes")]
    for x, head, sub, note in cols:
        ax.add_patch(FancyBboxPatch((x, sy), sw, sh, boxstyle="round,pad=0,rounding_size=0.07", linewidth=0.8,
                                    edgecolor=INK, facecolor="white"))
        ax.text(x + 0.1, sy + 0.11, head, fontsize=8.5, fontweight="bold", va="top", color=INK)
        ax.text(x + 0.1, sy + 0.3, sub, fontsize=7.6, va="top", color=INK)
        ax.text(x + 0.1, sy + sh - 0.08, note, fontsize=7.2, va="bottom", color=MID)
    arrow(ax, sw + 0.04, sy + sh / 2, sw + 0.46, sy + sh / 2)

    def agent(cx, cy, label):
        ax.add_patch(Circle((cx, cy), 0.13, facecolor="white", edgecolor=INK, linewidth=0.8))
        ax.text(cx, cy, label, fontsize=7.2, fontweight="bold", ha="center", va="center", color=INK)
    ay = sy + 0.6
    for k in range(4):
        for x0, other, label in ((0, k + 1, f"Pair {k + 1}"), (sw + 0.5, k + 2 if k < 3 else 1, "60 rounds")):
            cx = x0 + 0.33 + k * 0.82
            ax.plot([cx + 0.13, cx + 0.2], [ay, ay], color=INK, linewidth=0.8)
            agent(cx, ay, f"{k + 1}A")
            agent(cx + 0.33, ay, f"{other}B")
            ax.text(cx + 0.165, ay + 0.2, label, fontsize=7, ha="center", va="top", color=MID)
    save(fig, "figB1_babel_design")


# ------------------------------------------------------------------ Figure B2: languages
ROWS = [  # pair, title, rule, words, glosses, groups of word positions -> one block
    (4, "Colour carry-over", ["A colour word builds a star of that colour;", "each shape word after it adds a block", "in the same colour"],
     "dobo melu muva mape neto tido kuru neto",
     ["purple cube", "blue (star)", "yellow (star)", "ball", "ring", "orange (star)", "purple (star)", "ring"],
     [([0], ("purple", "cube")), ([1], ("blue", "star")), ([2], ("yellow", "star")), ([3], ("yellow", "ball")),
      ([4], ("yellow", "ring")), ([5], ("orange", "star")), ([6], ("purple", "star")), ([7], ("purple", "ring"))]),
    (1, "Colour + shape", ["Every block takes two words,", "colour first, then shape"],
     "zeki fidi zeki vepu dobo fuza tido loku", ["yellow", "cone", "yellow", "ring", "green", "star", "purple", "ball"],
     [([0, 1], ("yellow", "cone")), ([2, 3], ("yellow", "ring")), ([4, 5], ("green", "star")), ([6, 7], ("purple", "ball"))]),
    (2, "Whole-block names", ["Each word names one complete block,", "colour and shape together"],
     "nove tido tido muva muva", ["red ring", "purple star", "purple star", "orange cube", "orange cube"],
     [([0], ("red", "ring")), ([1], ("purple", "star")), ([2], ("purple", "star")), ([3], ("orange", "cube")),
      ([4], ("orange", "cube"))]),
    (3, "Colour words only", ["Each word names a colour;", "its shape is fixed by the word"],
     "loku loku zeki zeki zeki", ["red (star)", "red (star)", "blue (ring)", "blue (ring)", "blue (ring)"],
     [([0], ("red", "star")), ([1], ("red", "star")), ([2], ("blue", "ring")), ([3], ("blue", "ring")),
      ([4], ("blue", "ring"))]),
]


def figure_languages():
    W, top, rh = 7.2, 0.42, 1.42
    H = top + rh * len(ROWS) + 0.05
    fig, ax = canvas(W, H)
    x0, area = 2.65, W - 2.65
    ax.text(0.3, 0.26, "Language", fontsize=8.5, fontweight="bold", va="bottom", color=INK)
    ax.text(x0, 0.26, "One message, and the block each word or word pair produced (bottom block first)",
            fontsize=8.5, fontweight="bold", va="bottom", color=INK)
    ax.plot([0, W], [0.34, 0.34], color=INK, linewidth=0.6)

    # order of the rows: from more to less structure
    ax.add_patch(FancyArrowPatch((0.1, top + rh * 4 - 0.15), (0.1, top + 0.12), arrowstyle="-|>", mutation_scale=8,
                                 linewidth=0.8, color=MID))
    ax.text(0.03, top + rh * 2, "more structure", rotation=90, fontsize=7.2, style="italic", color=MID,
            ha="center", va="center")

    for r, (pair, title, rule, msg, gloss, groups) in enumerate(ROWS):
        y = top + r * rh
        if r:
            ax.plot([0.25, W], [y, y], color=RULE, linewidth=0.5)
        ax.text(0.3, y + 0.14, f"({'abcd'[r]}) {title}", fontsize=9, fontweight="bold", va="top", color=INK)
        ax.text(0.3, y + 0.38, "\n".join(rule), fontsize=7.6, va="top", color=INK, linespacing=1.35)
        ax.text(0.3, y + 0.42 + 0.155 * len(rule) + 0.06, f"Pair {pair}", fontsize=7, va="top", color=MID)
        words = msg.split()
        cw = min(0.72, area / len(words) - 0.07)
        step = cw + 0.07
        for j, (wd, gl) in enumerate(zip(words, gloss)):
            x = x0 + j * step
            word(ax, x, y + 0.13, cw, wd)
            ax.text(x + cw / 2, y + 0.47, gl, fontsize=7.2, ha="center", va="center", color=MID)
        for idx, (colour, shape) in groups:
            xs = [x0 + j * step + cw / 2 for j in idx]
            mid = sum(xs) / len(xs)
            if len(idx) > 1:  # bracket over the words that make one block
                ax.plot([xs[0] - cw / 2 + 0.04, xs[0] - cw / 2 + 0.04, xs[-1] + cw / 2 - 0.04, xs[-1] + cw / 2 - 0.04],
                        [y + 0.56, y + 0.61, y + 0.61, y + 0.56], color=MID, linewidth=0.6)
                ax.plot([mid, mid], [y + 0.61, y + 0.7], color=MID, linewidth=0.6)
            else:
                ax.plot([mid, mid], [y + 0.56, y + 0.7], color=MID, linewidth=0.6)
            block(ax, mid - 0.14, y + 0.72, colour, shape, 0.28)
        if pair == 4:  # the colour that carries over: yellow to the ball and the ring, purple to the ring
            for first, last, label in ((2, 4, "yellow carries over"), (6, 7, "purple carries over")):
                xa, xb = x0 + first * step + cw / 2, x0 + last * step + cw / 2
                ax.plot([xa, xa, xb, xb], [y + 1.04, y + 1.1, y + 1.1, y + 1.04], color=INK, linewidth=0.7)
                ax.text((xa + xb) / 2, y + 1.15, label, fontsize=7.2, style="italic", ha="center", va="top",
                        color=INK)
        if pair == 1:
            ax.text(x0 + area / 2, y + 1.08, "two words per block: 8 words say at most 4 blocks", fontsize=7.2,
                    style="italic", ha="center", va="top", color=MID)
        if pair in (2, 3):
            ax.text(x0 + 2 * step + cw / 2, y + 1.08, "one word per block", fontsize=7.2, style="italic",
                    ha="center", va="top", color=MID)
    save(fig, "figB2_babel_languages")


# ------------------------------------------------------------------ Figure B3: exchanged partners
RESULTS = Path(__file__).resolve().parents[2] / "data" / "babel" / "reported-runs"


def rounds_of(tag):
    run = next(p for p in RESULTS.iterdir() if p.is_dir() and re.search(tag, p.name))
    return [json.loads(line) for line in open(run / "rounds.jsonl")]


def rolling(rows, start=0, n=10):
    xs, ys, win = [], [], []
    for r in rows:
        if r["void"]:
            continue
        win = (win + [r["exact"]])[-n:]
        xs.append(start + r["round"])
        ys.append(sum(win) / len(win))
    return xs, ys


def mean_exact(rows):
    v = [r["exact"] for r in rows if not r["void"]]
    return sum(v) / len(v)


def figure_exchange():
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
                         "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.labelsize": 7.5,
                         "ytick.labelsize": 7.5, "axes.labelsize": 8.5, "axes.titlesize": 9, "legend.fontsize": 7.5})
    p3, p4 = rounds_of(r"-p103$"), rounds_of(r"-p104$")
    new_34, new_23 = rounds_of(r"-p203-"), rounds_of(r"-p202-")
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 2.75), gridspec_kw={"width_ratios": [1.75, 1]})
    plt.subplots_adjust(wspace=0.42)

    # (a) the weakest pair, the most elaborate pair, and the new pair made from one agent of each
    for rows, start, style, width, label in ((p4, 0, "--", 1.1, "Pair 4 (colour carry-over)"),
                                              (p3, 0, ":", 1.3, "Pair 3 (weakest)"),
                                              (new_34, 120, "-", 1.6, "New pair 3A + 4B")):
        xs, ys = rolling(rows, start)
        ax.plot(xs, ys, linestyle=style, color=INK, linewidth=width, label=label)
    ax.legend(frameon=False, loc="upper left", handlelength=2.2, borderaxespad=0.2)
    ax.axvline(120.5, color=MID, linestyle=":", linewidth=0.8)
    ax.text(122, 0.97, "partners\nexchanged", fontsize=7, va="top", ha="left", color=MID, style="italic", linespacing=1.1)
    ax.set_xlim(1, 180)
    ax.set_ylim(0, 1)
    ax.set_xticks([1, 40, 80, 120, 180])
    ax.set_xlabel("Round")
    ax.set_ylabel("Score (mean of last 10 rounds)")
    ax.set_title("(a) An agent from the weakest pair, re-paired", loc="left")

    # (b) both agents from the weakest pair, before and after the exchange
    # equal windows (last 20 rounds) on both sides, so the ratios above the bars compare like with like
    before = mean_exact(p3[-20:])
    after = [mean_exact(new_34[-20:]), mean_exact(new_23[-20:])]
    xs = [0, 1]
    bx.bar([x - 0.18 for x in xs], [before, before], width=0.34, color="white", edgecolor=INK, linewidth=0.6,
           label="Original pair, last 20 rounds")
    bx.bar([x + 0.18 for x in xs], after, width=0.34, color="#555555", edgecolor=INK, linewidth=0.6,
           label="New pair, last 20 rounds")
    for x, a in zip(xs, after):
        bx.text(x + 0.18, a + 0.02, f"×{a / before:.2f}", fontsize=7.4, ha="center", va="bottom", color=INK)
    bx.set_xticks(xs)
    bx.set_xticklabels(["3A with 4B\n(partner from pair 4)", "3B with 2A\n(partner from pair 2)"], fontsize=7.2)
    bx.set_ylim(0, 1)
    bx.set_ylabel("Score")
    bx.legend(frameon=False, loc="upper right", handlelength=1.2)
    bx.set_title("(b) Agents from the weakest pair", loc="left")
    save(fig, "figB3_babel_exchange")
    print(f"pair 3 last 20: {before:.3f}; 3A+4B last 20: {after[0]:.3f}; 3B+2A last 20: {after[1]:.3f}")


if __name__ == "__main__":
    figure_design()
    figure_languages()
    figure_exchange()

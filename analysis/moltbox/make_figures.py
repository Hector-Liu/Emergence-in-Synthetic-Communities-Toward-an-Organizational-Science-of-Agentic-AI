"""Figures A1 and A2 of the appendix, for run 20261015-001615-run-01 (English, print format).

    python3 analysis/moltbox/make_figures.py      (from the package root; needs numpy + matplotlib)

Figure 1: research design (flow chart), read from the run's config and logs.
Figure 2: the two findings the proposal reports for this experiment, computed from the logs:
  (a, b) the "recalled" status label: uses per window by cohort, members who adopted it;
  (c, d) "method note": comments using it against other wordings for untested ideas, members who adopted it.
Writes figA1_moltbox_design and figA2_moltbox_results (.pdf .png .svg) to analysis/moltbox/output/figures/.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # the package root
RUN = ROOT / "data" / "moltbox" / "run-01"  # the reported run, 20261015-001615-run-01
OUT = HERE / "output" / "figures"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "pdf.fonttype": 42, "svg.fonttype": "none",
})
INK, MID = "#111111", "#6b6b6b"
COHORTS = [(0, "Founders", INK, None), (1, "Newcomers-1", "#8c8c8c", None), (2, "Newcomers-2", "white", "////")]


def jl(name):
    return [json.loads(line) for line in open(RUN / name)]


def save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{stem}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


cfg = json.load(open(RUN / "config.json"))
acts = jl("actions.jsonl")
phase = {a["agent"]["handle"]: a["agent"]["phase"] for a in acts if a["kind"] == "agent"}
comments = [a for a in acts if a["kind"] == "comment"]
posts = [a for a in acts if a["kind"] == "post"]
updates = [a for a in acts if a["kind"] == "update"]
sizes = [sum(g["n"] for g in p["add"]) for p in cfg["phases"]]
starts = [1 + sum(p["rounds"] for p in cfg["phases"][:i]) for i in range(len(cfg["phases"]))]
total_rounds = sum(p["rounds"] for p in cfg["phases"])
WINS = list(range(total_rounds // 10))
ENTRY = [(s - 1) / 10 - 0.5 for s in starts[1:]]  # window boundaries where cohorts 2 and 3 arrive


# ------------------------------------------------------------------ Figure 1: design
def box(ax, x, y, w, h, title, lines, fill=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", linewidth=0.8,
                                edgecolor=INK, facecolor="#f2f2f2" if fill else "white"))
    ax.text(x + 1.6, y + h - 2.2, title, fontsize=8.5, fontweight="bold", va="top", ha="left", color=INK)
    ax.text(x + 1.6, y + h - 6.4, "\n".join(lines), fontsize=7.6, va="top", ha="left", color=INK, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=8, linewidth=0.8, color=INK,
                                 connectionstyle=f"arc3,rad={rad}"))


def figure1():
    fig, ax = plt.subplots(figsize=(7.2, 6.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def band(y, label):
        ax.text(0, y, label, fontsize=9, fontweight="bold", va="bottom", ha="left", color=INK)

    band(96.5, "A  Design")
    box(ax, 0, 79, 31.5, 16.5, "Agents", [f"{sum(sizes)} LLM agents", "No task beyond posting,", "commenting and upvoting"])
    box(ax, 34.25, 79, 31.5, 16.5, "Forum", ["One shared board", "Posts, comments, upvotes", "and updates to own posts"])
    box(ax, 68.5, 79, 31.5, 16.5, "Cohorts", [f"{sizes[0]} founders (round {starts[0]})",
                                              f"{sizes[1]} newcomers (round {starts[1]})",
                                              f"{sizes[2]} newcomers (round {starts[2]})"])
    for x in (15.75, 50, 84.25):
        arrow(ax, x, 79, x, 75.5)

    band(72, f"B  Each round, for {total_rounds} rounds")
    box(ax, 0, 55, 26, 16, "Visit", ["Each agent visits", "every few rounds;", "agents act in turn"])
    box(ax, 30, 55, 30, 16, "Read", ["A feed of the newest posts", "and posts drawn at random,", "with their comments"])
    box(ax, 64, 55, 36, 16, "Act", ["Post, comment, update", "own post, upvote,", "or do nothing"])
    arrow(ax, 26, 63, 30, 63)
    arrow(ax, 60, 63, 64, 63)
    arrow(ax, 82, 55, 13, 55, rad=-0.16)
    ax.text(47, 53.6, "next visit", fontsize=7.2, ha="center", va="top", color=MID, style="italic")
    arrow(ax, 50, 47, 50, 41)

    band(37, "C  Record")
    box(ax, 0, 25, 100, 11, "Every visit logged", ["What each agent was shown, what it wrote, and a summary of its reasoning"], fill=True)
    arrow(ax, 50, 25, 50, 21.5)

    band(18, "D  Analysis (rule-based, from the logs)")
    box(ax, 0, 3, 48.5, 13, "Proto-institutions", ["Trace a practice from its first uses",
                                                    "to a label members enforce"])
    box(ax, 51.5, 3, 48.5, 13, "Vocabulary", ["Track new meanings of existing words",
                                              "and their spread across members"])
    save(fig, "figA1_moltbox_design")


# ------------------------------------------------------------------ Figure 2: results
def per_window(texts, pattern):
    """texts per 10-round window that match, by author cohort"""
    out = {ph: Counter() for ph in (0, 1, 2)}
    for t in texts:
        if re.search(pattern, t["body"], re.I):
            out[phase[t["author"]]][(t["round"] - 1) // 10] += 1
    return out


def adopters(texts, pattern):
    """cumulative members (by cohort) who have used the pattern, at the end of each round"""
    first = {}
    for t in sorted(texts, key=lambda t: t["round"]):
        if re.search(pattern, t["body"], re.I):
            first.setdefault(t["author"], t["round"])
    rounds = list(range(1, total_rounds + 1))
    cum = {ph: [sum(1 for h, r0 in first.items() if phase[h] == ph and r0 <= r) for r in rounds] for ph in (0, 1, 2)}
    return rounds, cum


def window_axis(ax):
    ax.set_xticks(WINS[::2])
    ax.set_xticklabels([f"{10 * w + 1}" for w in WINS[::2]])
    ax.set_xlabel("Round (start of 10-round window)")
    for e in ENTRY:
        ax.axvline(e, color=MID, linestyle=":", linewidth=0.8)


def stacked(ax, counts):
    bottom = [0] * len(WINS)
    for ph, name, col, hatch in COHORTS:
        vals = [counts[ph][w] for w in WINS]
        ax.bar(WINS, vals, bottom=bottom, color=col, edgecolor=INK, linewidth=0.5, hatch=hatch, width=0.7, label=name)
        bottom = [b + v for b, v in zip(bottom, vals)]
    return bottom


def cumulative(ax, rounds, cum, note):
    """one line per cohort, labelled at its end (no legend box over the lines)"""
    styles = {0: "-", 1: "--", 2: ":"}
    for ph, name, _, _ in COHORTS:
        ax.plot(rounds, cum[ph], linestyle=styles[ph], color=INK, linewidth=1.2)
        ax.text(total_rounds + 2, cum[ph][-1], f"{name}\n{cum[ph][-1]} of {sizes[ph]}", fontsize=6.8, va="center",
                ha="left", color=INK, linespacing=1.1, clip_on=False)
    for s in starts[1:]:
        ax.axvline(s - 0.5, color=MID, linestyle=":", linewidth=0.8)
    ax.set_xlim(1, total_rounds)
    ax.set_xticks([1, 31, 61, 91, 120])
    ax.set_xlabel("Round")
    ax.set_ylabel("Members who have used it")
    ax.text(0.02, 0.98, note, transform=ax.transAxes, fontsize=7.4, va="top", color=INK,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.5))


def figure2():
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 6.2))
    plt.subplots_adjust(wspace=0.36, hspace=0.66)
    texts = comments + updates

    # (a) "recalled": uses per window, with the exchange that began it
    REC = r"\brecalled\b"
    ax = axs[0, 0]
    tops = stacked(ax, per_window(texts, REC))
    window_axis(ax)
    ax.set_ylabel("Texts using “recalled”")
    ax.set_ylim(0, max(tops) * 1.55)
    # numbered events above their windows, explained in a key at the top left
    events = [(43, "founder promises the tag (rounds 43–45)"),
              (52, "proposal: “sourced, recalled, or unverified” (round 52)"),
              (68, "last reference to exchange 1 (round 68)")]
    for i, (r, _) in enumerate(events, 1):
        x = (r - 1) // 10  # the window the event falls in
        ax.text(x, tops[x] + 1.5, str(i), ha="center", va="bottom", fontsize=7, fontweight="bold", color=INK,
                bbox=dict(boxstyle="circle,pad=0.18", facecolor="white", edgecolor=INK, linewidth=0.6))
    ax.text(0.02, 0.98, "\n".join(f"{i}  {lab}" for i, (_, lab) in enumerate(events, 1)), transform=ax.transAxes,
            fontsize=6.6, va="top", ha="left", color=INK, linespacing=1.5,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.5))
    ax.legend(frameon=True, facecolor="white", edgecolor="none", framealpha=1, loc="upper left", bbox_to_anchor=(0.0, 0.74))
    ax.set_title("(a) “recalled”: from separate first uses to a shared label", loc="left")

    # (b) "recalled": members who adopted it
    ax = axs[0, 1]
    rounds, cum = adopters(texts, REC)
    n_com = sum(1 for c in comments if re.search(REC, c["body"], re.I))
    cumulative(ax, rounds, cum, f"{sum(c[-1] for c in cum.values())} members, {n_com} comments")
    ax.set_title("(b) “recalled”: adoption across cohorts", loc="left")

    # (c) "method note" against the other wordings for untested ideas
    MN = r"\bmethod note"
    OTHER = [r"\bsuggestion only\b",
             r"\bplan,? (?:only|rather than a result|not a result)\b|\bplan only\b|\bnot a result\b|\brather than a result\b",
             r"\bmethod only\b|\bmethod suggestion\b|\bmethod rather than\b",
             r"\bso (?:this|it) is (?!(?:a |an )?(?:method note|suggestion|plan|method))(?:a |an )?[a-z\- ]{1,25}\bonly\b"]
    mn = Counter((c["round"] - 1) // 10 for c in comments if re.search(MN, c["body"], re.I))
    ot = Counter((c["round"] - 1) // 10 for c in comments
                 if not re.search(MN, c["body"], re.I) and any(re.search(p, c["body"], re.I) for p in OTHER))
    ax = axs[1, 0]
    ax.axvspan(7.5, 11.5, color="#eeeeee", zorder=0)
    ax.text(9.5, 0.99, "last third", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6.8, color=MID)
    ax.plot(WINS, [mn[w] for w in WINS], color=INK, marker="o", markersize=2.8, linewidth=1.3, label="“method note”")
    ax.plot(WINS, [ot[w] for w in WINS], color=MID, marker="s", markersize=2.6, linewidth=1.1,
            label="Older wordings only")
    window_axis(ax)
    ax.set_ylabel("Comments")
    first_mn = min((c for c in comments if re.search(MN, c["body"], re.I)), key=lambda c: c["round"])
    fx = (first_mn["round"] - 1) / 10
    ax.annotate(f"first use, round {first_mn['round']}\n(a newcomer)", xy=(fx, mn[int(fx)]), xytext=(fx + 0.6, 6),
                fontsize=6.6, color=INK, arrowprops=dict(arrowstyle="-", color=MID, linewidth=0.6))
    ax.legend(frameon=True, facecolor="white", edgecolor="none", framealpha=1, loc="upper left")
    ax.set_ylim(0, max(max(ot.values()), max(mn.values())) * 1.38)
    ax.set_title("(c) “method note” and the older wordings", loc="left")
    last = range(8, 12)
    print("(c) last third: method note", sum(mn[w] for w in last), "other wordings only", sum(ot[w] for w in last))

    # (d) "method note": members who adopted it
    ax = axs[1, 1]
    rounds, cum = adopters(texts, MN)
    threads = len({c["post"] for c in comments if re.search(MN, c["body"], re.I)})
    cumulative(ax, rounds, cum, f"{sum(c[-1] for c in cum.values())} members, all {threads} threads")
    ax.set_ylim(-1.5, 34)
    ax.set_title("(d) “method note”: adoption across cohorts", loc="left")
    for a in axs.flat:
        a.tick_params(length=2.5)
    save(fig, "figA2_moltbox_results")


if __name__ == "__main__":
    figure1()
    figure2()
    print("written to", OUT)

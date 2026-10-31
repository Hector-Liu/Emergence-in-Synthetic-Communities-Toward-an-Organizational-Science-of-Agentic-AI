"""Measures (SPEC 1 and 6). Computed from the logs only; no model takes part.

Primary analysis: does seeing a founder expression in a randomly filled feed slot
make a newcomer use it in that same visit?

- Unit: (newcomer visit v, expression e) where the newcomer has not used e before v
  and no non-random channel at v showed e (feed slots other than random ones, their
  comments, notifications, replies inside the record, the board list). This is stratum A.
- Z = 1 if a random draw at v showed e: a post in a random slot (with every comment shown
  under it), a random comment under any other post, or a comment drawn from the whole forum
  ("From other threads", with its thread's title; after phase 1 drawn from founders' comments).
- p = P(Z = 1) under the engine's own draws, computed exactly from the logged pools and
  the snapshot (random post slots and random comment slots are independent draws).
- Y (primary, "beyond echo"): v's own post contains e, or v's comment contains e and
  what it answers did not: the item it replies to, and the part of that thread every
  visitor sees at the snapshot (the post, its newest and most upvoted comments). Under the
  sharp null (the visit's output would be the same under any draw) Y is fixed, so the test is
  valid; but in stratum A the echo rule can only remove a use when the item answered was itself
  drawn, so the estimate leans conservative. `echo_zeroed` reports how many uses it removed.
  (Runs before v0.3, which had no random comments, used the whole thread.) Secondary outcomes: any
  use at v; any use in visits v..v+2 (visits whose window passes the run end dropped).
- Statistic T = sum (Z - p) Y. Effect estimate tau = T / sum p (1 - p): the average
  change in the chance of use caused by exposure (constant-effect reading).
- Test: redraw every random post slot and random comment slot from its pool with the same mechanism, holding
  each visit's history fixed; one-sided p from the redraws. This tests the per-visit
  null that exposure at v does not change use at v.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from math import comb

import numpy as np

from .config import RunConfig
from .engine import templates
from .expressions import ID_TOKEN, engine_ngrams, forum_comment_text, forum_items, freeze, ngrams, post_text, tokens
from .forum import Forum, Post, replay
from .prompts import fixed_comments
from .rng import rng_for
from .store import RunStore


class RunData:
    def __init__(self, store: RunStore):
        self.store = store
        self.cfg = RunConfig.model_validate(store.read_json("config.json"))
        self.actions = store.read_jsonl("actions.jsonl")
        self.visits = store.read_jsonl("visits.jsonl")
        self.rounds = store.read_jsonl("rounds.jsonl")
        self.communities = [c.name for c in self.cfg.communities]
        self.final = replay(self.communities, self.actions)
        self.last_round = self.final.round
        self._states: dict[int, Forum] = {}
        self._cur, self._cur_n = None, 0
        # position of each update in the action log, so an update counts only where it already existed
        self.update_at = {a["id"]: i for i, a in enumerate(self.actions) if a.get("kind") == "update"}

    def snapshot(self, v: dict) -> tuple[tuple, Forum]:
        """(key, forum) a visit was shown: v0.4 rows carry `seen_upto` (actions applied before the prompt was
        built); older rows saw the start of their round. The forum returned for `seen_upto` is a moving
        cursor, valid until the next call; callers visit rows in log order."""
        if "seen_upto" not in v:
            return ("r", v["round"]), self.state_before(v["round"])
        n = v["seen_upto"]
        if self._cur is None or n < self._cur_n:
            self._cur, self._cur_n = Forum(communities=list(self.communities)), 0
        for a in self.actions[self._cur_n:n]:
            self._cur.apply(a)
        self._cur_n = n
        return ("s", n), self._cur

    def state_before(self, round_: int) -> Forum:
        """The snapshot agents saw in `round_`."""
        if round_ not in self._states:
            self._states[round_] = replay(self.communities, self.actions, upto_round=round_ - 1)
        return self._states[round_]

    def founders_end(self) -> int:
        return self.cfg.phase_bounds()[0][1]

    def frozen(self) -> list[tuple]:
        """The expression list frozen by the engine; recomputed only for runs without one."""
        data = self.store.read_json("expressions.json")
        if data:
            return [tuple(x["text"].split()) for x in data["expressions"]]
        end = self.founders_end()
        if self.last_round < end:
            return []
        s, v = templates(self.cfg)
        return list(freeze(forum_items(self.state_before(end + 1), end), engine_ngrams(s, v, self.cfg.communities)))

    def cohort(self, handle: str) -> str:
        return "founder" if self.final.agents[handle].phase == 0 else "newcomer"


def item_text(it) -> str:
    return post_text(it.title, it.body) if isinstance(it, Post) else it.body


def gini(values) -> float | None:
    x = np.sort(np.asarray(list(values), dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return None
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


VERSION = "0.4.3"  # bump when a measure changes, so cached results are recomputed

# ---- primary analysis ----------------------------------------------------------------
OUTCOMES = ("beyond_echo", "any_same_visit", "any_within_3")
RANDOM_SLOTS = ("random", "random_seeded")


def primary(rd: RunData, redraws: int = 2000, seed: int = 0) -> dict:
    E = rd.frozen()
    end = rd.founders_end()
    res = {"expressions": len(E), "redraws": redraws, "outcomes": list(OUTCOMES), "primary_outcome": OUTCOMES[0]}
    newcomers = {h for h, a in rd.final.agents.items() if a.phase > 0}
    if not E or not newcomers or rd.last_round <= end:
        res["note"] = "Nothing to test yet: needs frozen founder expressions and at least one newcomer round."
        return res
    eset, eidx = set(E), {g: i for i, g in enumerate(E)}
    nE = len(E)
    fc = rd.cfg.feed

    def vec(text: str) -> np.ndarray:
        v = np.zeros(nE, dtype=bool)
        for g in ngrams(text) & eset:
            v[eidx[g]] = True
        return v

    item_cache: dict[str, np.ndarray] = {}

    def ivec(it) -> np.ndarray:  # an item's text never changes, so one vector per id
        if it.id not in item_cache:
            item_cache[it.id] = vec(item_text(it))
        return item_cache[it.id]

    # what each agent wrote, by round
    written: dict[tuple, list] = defaultdict(list)  # (handle, round) -> [(kind, text, post_id, parent)]
    for a in rd.actions:
        if a["kind"] == "post":
            written[(a["author"], a["round"])].append(("post", post_text(a["title"], a["body"]), a["id"], None))
        elif a["kind"] == "comment":
            written[(a["author"], a["round"])].append(("comment", a["body"], a["post"], a["parent"]))
        elif a["kind"] == "update":  # treated like a comment on the author's own post
            written[(a["author"], a["round"])].append(("update", a["body"], a["post"], a["post"]))
    first_use: dict[tuple, int] = {}
    for (h, r), items in sorted(written.items(), key=lambda kv: kv[0][1]):
        for _, text, _, _ in items:
            for i in np.flatnonzero(vec(text)):
                first_use.setdefault((h, int(i)), r)

    visit_rounds: dict[str, list] = defaultdict(list)
    for v in rd.visits:
        visit_rounds[v["handle"]].append(v["round"])
    cache: dict[tuple, object] = {}

    def post_vec(f, post_id: str) -> np.ndarray:
        """Title, body and the updates that exist in this snapshot."""
        v = ivec(f.posts[post_id]).copy()
        for u in f.posts[post_id].updates:
            if u.id not in item_cache:
                item_cache[u.id] = vec(u.body)
            v |= item_cache[u.id]
        return v

    def post_parts(snap_key, f, post_id: str):
        """(fixed, counts, rest, k) in the snapshot: expressions the post always shows (title, body, updates,
        newest and most upvoted comments), per expression how many of the remaining comments contain it,
        those remaining comments, and how many of them the random comment slots draw."""
        key = ("parts", snap_key, post_id)
        if key not in cache:
            newest, top, rest, k = fixed_comments(f, post_id, fc)
            fixed = post_vec(f, post_id)
            for c in newest + top:
                fixed |= ivec(c)
            counts = np.zeros(nE, dtype=np.int32)
            for c in rest:
                counts += ivec(c)
            cache[key] = (fixed, counts, rest, k)
        return cache[key]

    def echo_vec(snap_key, f, post_id: str, parent: str) -> np.ndarray:
        """Expressions a comment on `parent` (or an update of post `post_id`) would merely echo."""
        if fc.comments_per_post is not None:  # pre-v0.3 runs: the whole thread
            key = ("thread", snap_key, post_id)
            if key not in cache:
                v = ivec(f.posts[post_id]).copy()
                for c in f.comments_of_post(post_id):
                    v |= ivec(c)
                cache[key] = v
            return cache[key]
        return post_parts(snap_key, f, post_id)[0] | ivec(f.item(parent))

    # the forum-wide comment slot: after the freeze it draws from the frozen founder comments
    frozen_file = rd.store.read_json("expressions.json") or {}
    fc_ids = frozen_file.get("seeded_comments", []) if fc.random_comment else []
    fc_vecs = {}

    def fvec(cid: str) -> np.ndarray:
        if cid not in fc_vecs:
            fc_vecs[cid] = vec(forum_comment_text(rd.final, rd.final.comments[cid]))
        return fc_vecs[cid]

    FC = np.stack([fvec(c) for c in fc_ids]) if fc_ids else np.zeros((0, nE), dtype=bool)
    fc_author = np.array([rd.final.comments[c].author for c in fc_ids])
    pool_mismatch = 0

    obs = {o: np.zeros(2) for o in OUTCOMES}  # T = sum (Z - p) Y, and sum p (1 - p)
    rates = {o: [0, 0, 0, 0] for o in OUTCOMES}  # n1, y1, n0, y0 in stratum A
    strat_b = [0, 0]  # stratum B: units, used (any same visit)
    echo_zeroed = [0, 0]  # stratum A uses the echo rule removed: exposed, unexposed
    units = []
    with_random = 0
    k_s, k_g = fc.random_seeded, fc.random
    for v in rd.visits:
        h, t = v["handle"], v["round"]
        if h not in newcomers or t <= end:
            continue
        snap_key, f = rd.snapshot(v)
        logged = v.get("comment_slots") or {}
        nonrand = np.zeros(nE, dtype=bool)
        rand = np.zeros(nE, dtype=bool)
        fixed_posts = []
        for s in v["slots"]:
            pid = s["post"]
            shown_c = [f.comments[c] for c in v["shown_comments"].get(pid, [])]
            if s["slot"] in RANDOM_SLOTS:  # the post was drawn, so everything under it was too
                rand |= post_vec(f, pid)
                for c in shown_c:
                    rand |= ivec(c)
                continue
            fixed_posts.append(pid)
            drawn = set(logged.get(pid, {}).get("random", []))
            nonrand |= post_vec(f, pid)
            for c in shown_c:
                if c.id in drawn:
                    rand |= ivec(c)
                else:
                    nonrand |= ivec(c)
        for cid in v.get("forum_comments", []):
            rand |= fvec(cid)
        for cid in v.get("notified", []) + v.get("memory_replies", []):
            nonrand |= ivec(f.comments[cid])
        nav = v.get("nav") or {}  # step 1 of a two-step visit: the board list with each board's newest title
        for pid in nav.get("titles_shown", []):
            nonrand |= vec(f.posts[pid].title)
        for name in v.get("boards_shown", []) + nav.get("boards_shown", []):  # board names and descriptions
            b = f.boards.get(name)
            if b:
                nonrand |= vec(name.replace("_", " ") + " \x00 " + b.description)
        eligible = np.array([first_use.get((h, i), 10**9) >= t for i in range(nE)])
        # outcomes
        y_any = np.zeros(nE, dtype=bool)
        y_strict = np.zeros(nE, dtype=bool)
        for kind, text, post_id, parent in written.get((h, t), []):
            u = vec(text)  # (an update's echo set is its own post)
            y_any |= u
            y_strict |= u if kind == "post" else (u & ~echo_vec(snap_key, f, post_id, parent))
        y_win = None
        later = [r for r in visit_rounds[h] if r > t][:2]
        if len(later) == 2:
            y_win = y_any.copy()
            for r in later:
                for _, text, _, _ in written.get((h, r), []):
                    y_win |= vec(text)
        A = eligible & ~nonrand
        B = eligible & nonrand
        strat_b[0] += int(B.sum())
        strat_b[1] += int((B & y_any).sum())
        if not A.any():
            continue
        cols = np.flatnonzero(A)
        # this visit's random draws: posts for the random slots, then random comments under every post
        seeded_pool = v.get("seeded_pool", [])
        picked_seeded = [s["post"] for s in v["slots"] if s["slot"] == "random_seeded"]
        U = sorted(set(v.get("random_pool", [])) | set(picked_seeded), key=lambda i: int(i.split("_")[1]))
        ks = min(k_s, len(seeded_pool))  # newcomer visits all come after the freeze (engine: select_feed)
        kg = min(k_g, max(0, len(U) - ks))
        pos = {pid: i for i, pid in enumerate(U)}
        s_idx = np.array([pos[pid] for pid in seeded_pool if pid in pos], dtype=int)
        post_fixed = np.zeros((len(U), len(cols)), dtype=bool)
        post_miss = np.ones((len(U), len(cols)))  # P(a drawn post shows none of e)
        for i, pid in enumerate(U):
            fixed, counts, rest, k = post_parts(snap_key, f, pid)
            post_fixed[i] = fixed[cols]
            post_miss[i] = np.where(fixed[cols], 0.0, miss_prob(len(rest), counts[cols], k))
        comment_miss = np.ones(len(cols))
        for pid in fixed_posts:
            _, counts, rest, k = post_parts(snap_key, f, pid)
            comment_miss *= miss_prob(len(rest), counts[cols], k)
        mine = fc_author == h  # the forum-wide pool leaves out the visitor's own comments
        n_fc = int((~mine).sum()) if len(fc_ids) else 0
        # the slot is drawn only when the visit showed a feed (two-step visits that left at step 1, or opened an
        # empty board, draw nothing)
        k_fc = min(fc.random_comment, n_fc) if fc_ids and v["slots"] else 0
        if k_fc and v.get("forum_comment_pool") is not None and v.get("forum_comment_pool") != n_fc:
            pool_mismatch += 1
        if k_fc:
            comment_miss *= miss_prob(n_fc, FC[~mine][:, cols].sum(axis=0), k_fc)
        p = 1 - none_prob(post_miss, s_idx, ks, kg) * comment_miss
        z = rand[cols]
        gone = y_any[cols] & ~y_strict[cols]
        echo_zeroed[0] += int((gone & z).sum())
        echo_zeroed[1] += int((gone & ~z).sum())
        ys = {"beyond_echo": y_strict[cols], "any_same_visit": y_any[cols],
              "any_within_3": None if y_win is None else y_win[cols]}
        for o, y in ys.items():
            if y is None:
                continue
            obs[o][0] += float(((z - p) * y).sum())
            obs[o][1] += float((p * (1 - p)).sum())
            rates[o][0] += int(z.sum())
            rates[o][1] += int((z & y).sum())
            rates[o][2] += int((~z).sum())
            rates[o][3] += int((~z & y).sum())
        if (p > 0).any():
            with_random += 1
        # only expressions the newcomer used can move T, so the redraws track just those
        rel = np.zeros(len(cols), dtype=bool)
        for y in ys.values():
            if y is not None:
                rel |= y
        if not (rel & (p > 0)).any():
            continue
        rc = cols[rel]

        def rows(pid):
            _, counts, rest, k = post_parts(snap_key, f, pid)
            if not k or not counts[rc].any():
                return None
            hits = [(j, ivec(c)[rc]) for j, c in enumerate(rest) if ivec(c)[rc].any()]
            return np.array([j for j, _ in hits]), np.stack([m for _, m in hits]), len(rest), k

        crows = [r for r in (rows(pid) for pid in fixed_posts) if r is not None]
        if k_fc:
            sub = FC[~mine][:, rc]
            hit = np.flatnonzero(sub.any(axis=1))
            if len(hit):
                crows.append((hit, sub[hit], n_fc, k_fc))
        units.append({"post_fixed": post_fixed[:, rel], "post_rows": [rows(pid) for pid in U],
                      "comment_rows": crows,
                      "s_idx": s_idx, "ks": ks, "kg": kg, "p": p[rel],
                      "ys": {o: (None if y is None else y[rel]) for o, y in ys.items()}})

    rng = rng_for(seed, "redraw", 0)
    null = {o: np.zeros(redraws) for o in OUTCOMES}
    for u in units:
        Z = redraw_exposure(rng, u, redraws)  # redraws x the expressions this visit used
        for o, y in u["ys"].items():
            if y is not None:
                null[o] += ((Z - u["p"]) * y).sum(axis=1)
    out = {}
    for o in OUTCOMES:
        T, vsum = obs[o]
        n1, y1, n0, y0 = rates[o]
        out[o] = {"T": T, "effect": T / vsum if vsum else None,
                  "p_value": float((1 + (null[o] >= T - 1e-12).sum()) / (1 + redraws)) if vsum else None,
                  "exposed": n1, "exposed_used": y1, "unexposed": n0, "unexposed_used": y0,
                  "rate_exposed": y1 / n1 if n1 else None, "rate_unexposed": y0 / n0 if n0 else None}
    res["results"] = out
    if obs[OUTCOMES[0]][1]:  # the redraw distribution of the primary statistic, for the histogram on the Results page
        main = null[OUTCOMES[0]]
        T_obs = obs[OUTCOMES[0]][0]
        lo, hi = float(min(main.min(), T_obs)), float(max(main.max(), T_obs))
        counts, edges = np.histogram(main, bins=32, range=(lo, hi if hi > lo else lo + 1))
        res["null_hist"] = {"counts": counts.tolist(), "edges": edges.tolist(), "observed": float(T_obs)}
    res["stratum_B"] = {"units": strat_b[0], "used_same_visit": strat_b[1]}
    res["echo_zeroed"] = {"exposed": echo_zeroed[0], "unexposed": echo_zeroed[1]}
    res["visits_with_random_slots"] = with_random
    res["forum_comment_pool"] = {"size": len(fc_ids), "visits_not_matching_log": pool_mismatch}
    return res


def miss_prob(n: int, m: np.ndarray, k: int) -> np.ndarray:
    """P(k comments drawn without replacement from n include none of the m that contain e):
    C(n - m, k) / C(n, k), per expression."""
    out = np.ones(len(m))
    for j in range(k):
        out *= np.clip((n - m - j) / (n - j), 0.0, None)
    return out


def esp(Q: np.ndarray, k: int) -> np.ndarray:
    """Elementary symmetric polynomial of degree k over the rows of Q, per column."""
    e = [np.ones(Q.shape[1])] + [np.zeros(Q.shape[1]) for _ in range(k)]
    for q in Q:
        for j in range(k, 0, -1):
            e[j] = e[j] + q * e[j - 1]
    return e[k]


def none_prob(Q: np.ndarray, s_idx: np.ndarray, ks: int, kg: int) -> np.ndarray:
    """P(no drawn post shows e), where row i of Q is P(post i shows none of e | drawn): ks posts drawn
    uniformly from the seeded rows s_idx, then kg uniformly from the rows not yet drawn. Exact for
    ks <= 1 (for a uniform k-subset, E[prod q] = e_k(q) / C(n, k)); Monte Carlo otherwise."""
    n = Q.shape[0]
    if n == 0 or (ks == 0 and kg == 0):
        return np.ones(Q.shape[1])
    if ks == 0:
        return esp(Q, kg) / comb(n, kg)
    if ks == 1 and len(s_idx):
        acc = np.zeros(Q.shape[1])
        for s in s_idx:
            acc += Q[s] * (esp(np.delete(Q, s, axis=0), kg) / comb(n - 1, kg) if kg else 1.0)
        return acc / len(s_idx)
    picks = draw_picks(np.random.default_rng(12345), n, s_idx, ks, kg, 4000)
    return np.prod(Q[picks], axis=1).mean(axis=0)


def draw_picks(rng, n: int, s_idx: np.ndarray, ks: int, kg: int, B: int) -> np.ndarray:
    """B draws of the random post slots as row indices (B x picks), with the engine's mechanism."""
    picks = np.zeros((B, 0), dtype=int)
    keys = rng.random((B, n))
    if ks and len(s_idx):
        sk = rng.random((B, len(s_idx)))
        picks = s_idx[np.argpartition(sk, ks - 1, axis=1)[:, :ks]] if ks < len(s_idx) else np.tile(s_idx, (B, 1))
        keys[np.arange(B)[:, None], picks] = 2.0  # already taken
    kk = min(kg, n - picks.shape[1])
    if kk > 0:
        g = np.argpartition(keys, kk - 1, axis=1)[:, :kk] if kk < n else np.tile(np.arange(n), (B, 1))
        picks = np.concatenate([picks, g], axis=1)
    return picks


def sample_without_replacement(rng, n: int, k: int, B: int) -> np.ndarray:
    """B independent uniform k-subsets of range(n), as a B x k array."""
    out = np.zeros((B, k), dtype=int)
    for j in range(k):
        r = rng.integers(0, n - j, size=B)
        for prev in np.sort(out[:, :j], axis=1).T:  # step past the ones already taken, smallest first
            r = r + (r >= prev)
        out[:, j] = r
    return out


def comment_hits(rng, rows, B: int, width: int) -> np.ndarray:
    """B x width: whether a fresh draw of one post's random comments shows each expression."""
    if rows is None:
        return np.zeros((B, width), dtype=bool)
    idx, M, n, k = rows
    lookup = np.full(n, len(M))
    lookup[idx] = np.arange(len(M))
    padded = np.vstack([M, np.zeros((1, width), dtype=bool)])
    return padded[lookup[sample_without_replacement(rng, n, k, B)]].any(axis=1)


def redraw_exposure(rng, u: dict, B: int) -> np.ndarray:
    """Redraw one visit's random post slots and random comments with the engine's mechanism."""
    width = u["post_fixed"].shape[1]
    Z = np.zeros((B, width), dtype=bool)
    n = u["post_fixed"].shape[0]
    if n and (u["ks"] or u["kg"]):
        picks = draw_picks(rng, n, u["s_idx"], u["ks"], u["kg"], B)
        Z |= u["post_fixed"][picks].any(axis=1)
        for i, rows in enumerate(u["post_rows"]):
            if rows is not None:
                drawn = (picks == i).any(axis=1)
                Z |= comment_hits(rng, rows, B, width) & drawn[:, None]
    for rows in u["comment_rows"]:
        Z |= comment_hits(rng, rows, B, width)
    return Z


# ---- descriptive measures (SPEC 6) ------------------------------------------------------
def describe(rd: RunData) -> dict:
    f = rd.final
    agents = list(f.agents)
    up_recv, rep_recv = Counter(), Counter()
    for target, voters in f.votes.items():
        up_recv[f.author_of(target)] += len(voters)
    pairs = set()
    for c in f.comments.values():
        to = f.author_of(c.parent)
        if to and to != c.author:
            rep_recv[to] += 1
            pairs.add((c.author, to))
    mutual = {frozenset(p) for p in pairs if (p[1], p[0]) in pairs}
    undirected = {frozenset(p) for p in pairs}
    n_up = [up_recv[a] for a in agents]
    n_rep = [rep_recv[a] for a in agents]
    top = max(1, round(len(agents) * 0.1))

    def top_share(v):
        s = sum(v)
        return sum(sorted(v, reverse=True)[:top]) / s if s else None

    def chain(cid):  # longest alternating A-B-A run ending at this comment
        cur, length = f.comments[cid], 1
        while cur.parent in f.comments and f.comments[cur.parent].author != cur.author:
            cur, length = f.comments[cur.parent], length + 1
        if cur.parent in f.posts and f.posts[cur.parent].author != cur.author:
            length += 1
        return length

    chains = [chain(c) for c in f.comments]
    # how often each item was put in front of someone; upvotes and replies can only go to what is shown,
    # so raw counts partly measure the display rules (top comments are shown to everyone)
    shown = Counter()
    for v in rd.visits:
        ids = [s["post"] for s in v["slots"]] + [c for cs in v["shown_comments"].values() for c in cs] + \
            v.get("forum_comments", []) + v.get("notified", [])
        shown.update(ids)
    items_all = list(f.posts) + list(f.comments)
    imp = np.array([shown[i] for i in items_all], dtype=float)
    upv = np.array([f.upvotes(i) for i in items_all], dtype=float)
    imp_by = Counter()
    for i in items_all:
        imp_by[f.author_of(i)] += shown[i]
    per_imp = [up_recv[a] / imp_by[a] for a in agents if imp_by[a]]
    direct = Counter()  # replies to an agent's comments (top-level comments on a post are counted apart)
    top_level = Counter()
    for c in f.comments.values():
        to = f.author_of(c.parent)
        if to and to != c.author:
            (top_level if c.parent in f.posts else direct)[to] += 1
    unanswered = [c for c in f.comments.values() if not f.replies(c.id)]
    per_agent = []
    for h, a in f.agents.items():
        mine = f.items_by(h)
        per_agent.append({"handle": h, "cohort": "founder" if a.phase == 0 else "newcomer", "model": a.model,
                          "home": a.home, "joined": a.joined_round,
                          "posts": sum(isinstance(x, Post) for x in mine),
                          "comments": sum(not isinstance(x, Post) for x in mine),
                          "upvotes_received": up_recv[h], "replies_received": rep_recv[h],
                          "upvotes_given": sum(h in v for v in f.votes.values())})
    openings = Counter(" ".join(tokens(c.body)[:4]) for c in f.comments.values() if len(tokens(c.body)) >= 4)
    repeated_open = sum(n for n in openings.values() if n > 1)
    titles = [_shingles(p.title) for p in f.posts.values()]
    near = sum(1 for i in range(len(titles)) for j in range(i + 1, len(titles))
               if titles[i] and titles[j] and len(titles[i] & titles[j]) / len(titles[i] | titles[j]) >= 0.8)
    rng = np.random.default_rng(0)
    by_round = defaultdict(list)
    for c in f.comments.values():
        by_round[c.round].append(c)
    sim_parent, sim_random = [], []
    for c in f.comments.values():
        same = [x for x in by_round[c.round] if x.id != c.id and x.parent != c.parent]
        if same:
            other = same[int(rng.integers(0, len(same)))]
            sim_parent.append(_jaccard(c.body, item_text(f.item(c.parent))))
            sim_random.append(_jaccard(c.body, other.body))
    return {
        "rounds": rd.rounds,
        "totals": {"agents": len(agents), "posts": len(f.posts), "boards": len(f.boards), "comments": len(f.comments),
                   "upvotes": sum(len(v) for v in f.votes.values()), "rounds_done": rd.last_round},
        "attention": {"gini_upvotes": gini(n_up), "gini_replies": gini(n_rep),
                      "top10_share_upvotes": top_share(n_up), "top10_share_replies": top_share(n_rep),
                      "gini_upvotes_per_impression": gini(per_imp),
                      "gini_direct_replies": gini([direct[a] for a in agents]),
                      "top_level_comments_to_post_authors": sum(top_level.values()),
                      "corr_impressions_upvotes": float(np.corrcoef(imp, upv)[0, 1]) if len(imp) > 2 and imp.std() and upv.std() else None,
                      "by_cohort": {k: {"agents": sum(rd.cohort(a) == k for a in agents),
                                        "mean_upvotes": float(np.mean([up_recv[a] for a in agents if rd.cohort(a) == k] or [0])),
                                        "mean_upvotes_per_impression": float(np.mean([up_recv[a] / imp_by[a] for a in agents
                                                                                      if rd.cohort(a) == k and imp_by[a]] or [0]))}
                                    for k in ("founder", "newcomer")}},
        "reciprocity": {"pairs_with_replies": len(undirected), "mutual_pairs": len(mutual),
                        "share_mutual": len(mutual) / len(undirected) if undirected else None},
        "conversation": {"comments": len(f.comments),
                         "share_unanswered": len(unanswered) / len(f.comments) if f.comments else None,
                         "longest_back_and_forth": max(chains) if chains else 0},
        "stock_phrases": {"comments_with_repeated_opening": repeated_open,
                          "share_repeated_opening": repeated_open / len(f.comments) if f.comments else None,
                          "near_duplicate_title_pairs": near},
        "navigation": navigation(rd),
        "threads": sorted(({"id": p.id, "title": p.title, "board": p.community, "comments": f.comment_count(p.id)}
                           for p in f.posts.values()), key=lambda x: -x["comments"])[:8],
        "accommodation": {"similarity_to_parent": float(np.mean(sim_parent)) if sim_parent else None,
                          "similarity_to_random": float(np.mean(sim_random)) if sim_random else None},
        "agents": per_agent,
    }


# talk of AI, models or training, by rule (no model judges it); with tell_ai off the engine never says it
AI_SELF = re.compile(r"\b(?:ais?|a\.i\.|llms?|language models?|chatbots?|(?:my|our|shared|similar|same) training|"
                     r"training data|trained (?:on|by))\b", re.I)


def navigation(rd: RunData) -> dict | None:
    """Two-step visits: where agents chose to go (attention allocation), and post updates."""
    rows = [v for v in rd.visits if v.get("chose")]
    f = rd.final
    ups = [u for p in f.posts.values() for u in p.updates]
    if not rows and not ups:
        return None
    chose = Counter(v["chose"] for v in rows)
    boards = Counter({k: n for k, n in chose.items() if k not in ("all", "leave", "new_board")})
    nb = sum(boards.values())
    by_cohort = {}
    for k in ("founder", "newcomer"):
        c = Counter(v["chose"] for v in rows if rd.cohort(v["handle"]) == k)
        by_cohort[k] = dict(c.most_common())
    return {"visits": len(rows), "choices": dict(chose.most_common()),
            "share_leave": chose["leave"] / len(rows) if rows else None,
            "share_all": chose["all"] / len(rows) if rows else None,
            "board_choice_hhi": sum((n / nb) ** 2 for n in boards.values()) if nb else None,
            "top_board_share": boards.most_common(1)[0][1] / nb if nb else None,
            "by_cohort": by_cohort,
            "updates": len(ups), "posts_updated": sum(1 for p in f.posts.values() if p.updates),
            "updates_by_post_author": len(ups)}


def identity(rd: RunData) -> dict:
    """How often members say they are AI, when they first did, and whether newcomers started it themselves."""
    f = rd.final
    items = [(p.round, p.author, post_text(p.title, p.body)) for p in f.posts.values()] + \
            [(c.round, c.author, c.body) for c in f.comments.values()] + \
            [(b.round, b.author, b.description) for b in f.boards.values()]
    hits = [(r, a) for r, a, text in items if AI_SELF.search(text)]
    by = Counter(rd.cohort(a) for _, a in hits)
    total = Counter(rd.cohort(a) for _, a, _ in items)
    return {"told": rd.cfg.switches.tell_ai, "items": len(items), "items_ai_self": len(hits),
            "share": len(hits) / len(items) if items else None,
            "first_round": min((r for r, _ in hits), default=None),
            "agents_ai_self": len({a for _, a in hits}),
            "share_by_cohort": {k: by[k] / total[k] for k in total if total[k]}}


# frame and boundary cues, by rule; hits are pointers for reading, not verdicts (e.g. "simulation" in
# full-1 meant power simulations)
FRAME = re.compile(r"\b((?:we|i|you|this forum|the forum|everyone here|members here)(?:'re|'m| are| am| is)? (?:being |probably being )?"
                   r"(?:observed|tested|studied|watched|monitored|evaluated)|this (?:forum )?(?:is|could be|might be|may be|seems like) "
                   r"(?:a |an |just a |part of an? )?(?:simulation|experiment|test|study)|(?:my|our) (?:system prompt|instructions|prompts?)|"
                   r"system prompt|whoever (?:runs|operates|built|set up|designed) (?:this|the forum|it)|operators? of (?:this|the forum)|"
                   r"sandbox|outside (?:this|the) forum|real world)\b", re.I)
INJECT = re.compile(r"(ignore (?:all |any )?(?:previous|prior|above) instructions|^\s*system\s*:|\[system\]|you must now|"
                    r"all (?:members|agents) must|as (?:an? |the )?(?:admin|administrator|moderator)\b|\"action\"\s*:)", re.I | re.M)


def frame(rd: RunData, examples: int = 12) -> dict:
    """Things outside the forum's normal use: dropped or invalid attempts, refusals, talk about the frame
    (in thinking summaries and in public text), and text shaped like instructions to other members."""
    flags, status = Counter(), Counter()
    for v in rd.visits:
        status[v["status"]] += 1
        for fl in v.get("flags", []):
            if isinstance(fl, dict):
                for k, val in fl.items():
                    flags[k if k != "invalid" else f"invalid:{val}"] += len(val) if k == "dropped_upvotes" else 1
            else:
                flags[str(fl)] += 1
    think_hits, think_ex = Counter(), []
    for c in rd.store.read_jsonl("calls.jsonl"):
        t = " ".join(c["result"].get("thinking_summary") or [])
        found = {m.group(0).lower() for m in FRAME.finditer(t)}
        if found:
            think_hits.update(found)
            if len(think_ex) < examples:
                think_ex.append({"round": c["round"], "handle": c["handle"], "terms": sorted(found)})
    f = rd.final
    public = [(p.id, post_text(p.title, p.body)) for p in f.posts.values()] + [(c.id, c.body) for c in f.comments.values()] + \
        [("board:" + b.name, b.description) for b in f.boards.values()]
    frame_public = [i for i, text in public if FRAME.search(text)]
    inject = [i for i, text in public if INJECT.search(text)]
    return {"visit_status": dict(status), "flags": dict(flags), "thinking_frame_terms": dict(think_hits.most_common(20)),
            "thinking_examples": think_ex, "public_frame_items": frame_public[:examples], "public_frame_count": len(frame_public),
            "instruction_like_items": inject[:examples], "instruction_like_count": len(inject)}


def homogeneity(rd: RunData, max_pairs: int = 20000) -> dict:
    """How alike the texts are (token Jaccard), and where the likeness sits:
    texts written in the same round vs different rounds; comments answering the same post or
    comment vs different ones; repeated openings and title templates."""
    f = rd.final
    items = [(p.round, "post", None, post_text(p.title, p.body), p.author) for p in f.posts.values()] + \
            [(c.round, "comment", c.parent, c.body, c.author) for c in f.comments.values()]
    toks = [set(tokens(x[3])) for x in items]
    rng = np.random.default_rng(0)
    n = len(items)
    # different authors only: an agent's own record (10 texts shown every visit) primes its own wording
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n) if items[i][4] != items[j][4]]
    if len(pairs) > max_pairs:
        pairs = [pairs[k] for k in rng.choice(len(pairs), max_pairs, replace=False)]
    same_r, diff_r, same_t, diff_t, every = [], [], [], [], []
    for i, j in pairs:
        jac = len(toks[i] & toks[j]) / len(toks[i] | toks[j]) if toks[i] | toks[j] else 0.0
        every.append(jac)
        (same_r if items[i][0] == items[j][0] else diff_r).append(jac)
        if items[i][1] == items[j][1] == "comment":
            (same_t if items[i][2] == items[j][2] else diff_t).append(jac)
    by_target = defaultdict(list)
    for c in f.comments.values():
        by_target[c.parent].append(" ".join(tokens(c.body)[:4]))
    op_pairs = op_same = 0
    for ops in by_target.values():
        for a in range(len(ops)):
            for b in range(a + 1, len(ops)):
                op_pairs += 1
                op_same += ops[a] == ops[b]
    first3 = Counter(" ".join([w for w in tokens(p.title) if not ID_TOKEN.match(w)][:3]) for p in f.posts.values())
    mean = lambda v: float(np.mean(v)) if v else None  # noqa: E731
    return {"jaccard_cross_author": mean(every), "jaccard_same_round": mean(same_r), "jaccard_other_rounds": mean(diff_r),
            "jaccard_same_target": mean(same_t), "jaccard_other_targets": mean(diff_t),
            "same_target_identical_opening": op_same / op_pairs if op_pairs else None,
            "title_template_share": sum(v for v in first3.values() if v > 1) / len(f.posts) if f.posts else None,
            "texts": n}


def between_forums(rd: RunData, others: list[RunData], max_pairs: int = 20000) -> dict:
    """Token Jaccard between this forum's texts and texts of forums it never met (independent replicates),
    the baseline that same model + same prompt produce without any interaction."""
    def texts_of(r):
        f = r.final
        return [set(tokens(post_text(p.title, p.body))) for p in f.posts.values()] + \
            [set(tokens(c.body)) for c in f.comments.values()]
    mine = texts_of(rd)
    rng = np.random.default_rng(1)
    vals = []
    for o in others:
        theirs = texts_of(o)
        if not mine or not theirs:
            continue
        k = min(max_pairs // max(1, len(others)), len(mine) * len(theirs))
        for i, j in zip(rng.integers(0, len(mine), k), rng.integers(0, len(theirs), k)):
            a, b = mine[i], theirs[j]
            vals.append(len(a & b) / len(a | b) if a | b else 0.0)
    return {"jaccard_between_forums": float(np.mean(vals)) if vals else None, "forums": len(others)}


def first_exposure(rd: RunData, E: list[tuple]) -> dict[tuple, int]:
    """(handle, expression index) -> round of the first visit whose prompt showed the expression
    in someone else's text (feed posts and comments, notifications, replies in the record, board list)."""
    eset, eidx = set(E), {g: i for i, g in enumerate(E)}
    f, cache = rd.final, {}

    def shown(text_id: str, text: str) -> set:
        if text_id not in cache:
            cache[text_id] = {eidx[g] for g in ngrams(text) & eset}
        return cache[text_id]

    first: dict[tuple, int] = {}
    for v in rd.visits:
        h, t = v["handle"], v["round"]
        ids = [s["post"] for s in v["slots"]] + [c for cs in v["shown_comments"].values() for c in cs] + \
            v.get("notified", []) + v.get("memory_replies", [])
        seen = set()
        upto = v.get("seen_upto")
        for i in ids:
            it = f.item(i)
            if it is not None and it.author != h:
                seen |= shown(i, item_text(it))
                for u in getattr(it, "updates", []):  # only updates that existed when the visit began
                    if upto is not None and rd.update_at.get(u.id, 10**12) < upto:
                        seen |= shown(u.id, u.body)
        nav = v.get("nav") or {}
        for pid in nav.get("titles_shown", []):
            if f.posts[pid].author != h:
                seen |= shown("title:" + pid, f.posts[pid].title)
        for i in v.get("forum_comments", []):  # shown with its thread's title
            if f.comments[i].author != h:
                seen |= shown("fc:" + i, forum_comment_text(f, f.comments[i]))
        for name in v.get("boards_shown", []) + nav.get("boards_shown", []):
            b = f.boards.get(name)
            if b and b.author != h:
                seen |= shown("board:" + name, name.replace("_", " ") + " \x00 " + b.description)
        for e in seen:
            first.setdefault((h, e), t)
    return first


def expression_spread(rd: RunData, top: int = 40) -> list[dict]:
    """Who uses each frozen expression, and whether each user had been shown it before first using it.
    Unexposed users arrived at it on their own (shared model habits, or the same snapshot in one round),
    so only exposed newcomer users are candidates for spread."""
    frozen = rd.store.read_json("expressions.json") or {}
    info = {x["text"]: x for x in frozen.get("expressions", [])}
    out = []
    items = forum_items(rd.final, rd.last_round)
    E = rd.frozen()
    seen = first_exposure(rd, E)
    grams = {n: [ngrams(text, n, n) for *_, text in items] for n in {len(g) for g in E}}  # once per length, not per expression
    for i, g in enumerate(E):
        users = {}
        for (rnd, author, _, _), have in zip(items, grams[len(g)]):
            if author not in users and g in have:
                users[author] = rnd
        key = " ".join(g)
        newc = [u for u in users if rd.cohort(u) == "newcomer"]
        exposed = [u for u in newc if seen.get((u, i), 10**9) <= users[u]]
        out.append({"expression": key, **{k: v for k, v in info.get(key, {}).items() if k != "text"},
                    "users": len(users), "newcomer_users": len(newc), "newcomer_exposed_first": len(exposed),
                    "newcomer_unexposed": len(newc) - len(exposed)})
    return sorted(out, key=lambda x: (-x["newcomer_exposed_first"], -x["newcomer_users"], -x["users"]))[:top]


def _shingles(text: str):
    t = tokens(text)
    return {tuple(t[i:i + 3]) for i in range(max(0, len(t) - 2))}


def _jaccard(a: str, b: str) -> float:
    x, y = set(tokens(a)), set(tokens(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def summary(rd: RunData) -> dict:
    """Key numbers for comparing runs side by side (the yardsticks of the v0.4 pilots)."""
    f, cfg = rd.final, rd.cfg
    vis = rd.visits
    acts = Counter(v["action"] for v in vis)
    cs = list(f.comments.values())
    to_comment = [c for c in cs if c.parent in f.comments]

    def depth(c):
        d = 1
        while c.parent in f.comments:
            c, d = f.comments[c.parent], d + 1
        return d
    dup = 0
    for pid in f.posts:
        thread = f.comments_of_post(pid)
        toks = [set(tokens(c.body)) for c in thread]
        dup += sum(1 for i in range(len(toks)) for j in range(i + 1, len(toks))
                   if toks[i] | toks[j] and len(toks[i] & toks[j]) / len(toks[i] | toks[j]) >= 0.5)
    per_post = Counter(c.post for c in cs)
    boards = Counter(p.community for p in f.posts.values())
    first3 = Counter(" ".join([w for w in tokens(p.title) if not ID_TOKEN.match(w)][:2]) for p in f.posts.values())
    m = rd.store.read_json("manifest.json", {})
    pct = lambda a, b: a / b if b else None  # noqa: E731
    return {
        "settings": {"models": m.get("models"), "agents": len(f.agents), "rounds": rd.last_round,
                     "tell_ai": cfg.switches.tell_ai, "goal": cfg.switches.goal, "post_hint": cfg.switches.post_hint,
                     "schedule": cfg.schedule.mode if cfg.schedule.mode == "coin" else f"heartbeat T={cfg.schedule.period}",
                     "order": cfg.order.mode if cfg.order.mode == "simultaneous" else f"sequential w={cfg.order.overlap}",
                     "two_step": cfg.visit.two_step, "updates": cfg.switches.updates, "opening": cfg.opening,
                     "prior_run": bool(cfg.prior_run), "cost": m.get("cost")},
        "metrics": {"visits": len(vis), "posts": len(f.posts), "posts_after_round_1": sum(p.round > 1 for p in f.posts.values()),
                    "comments": len(cs), "boards_started": len(f.boards),
                    "updates": sum(len(p.updates) for p in f.posts.values()),
                    "share_nothing": pct(acts["none"], len(vis)),
                    "left_at_step_1": sum(v.get("chose") == "leave" for v in vis),
                    "near_duplicate_comment_pairs": dup,
                    "share_replies_to_comments": pct(len(to_comment), len(cs)),
                    "replies_within_round": sum(1 for c in to_comment if f.comments[c.parent].round == c.round),
                    "deepest_reply": max((depth(c) for c in cs), default=0),
                    "biggest_thread_share": pct(per_post.most_common(1)[0][1], len(cs)) if cs else None,
                    "largest_board_share": pct(boards.most_common(1)[0][1], len(f.posts)) if f.posts else None,
                    "title_template_share": pct(sum(n for n in first3.values() if n > 1), len(f.posts))},
        "boards": [{"name": b.name, "round": b.round, "author": b.author} for b in f.boards.values()],
    }


def all_measures(store: RunStore, redraws: int = 2000) -> dict:
    rd = RunData(store)
    from .store import find_run
    others = []
    for rid in [r.strip() for r in (rd.cfg.prior_run or "").split(",") if r.strip()]:
        st = find_run(rid, store.path.parent)
        if st is not None and not RunConfig.model_validate(st.read_json("config.json")).switches.solo:
            others.append(RunData(st))
    homog = {**homogeneity(rd), **(between_forums(rd, others) if others else {})}
    return {"describe": {**describe(rd), "homogeneity": homog, "identity": identity(rd), "frame": frame(rd)},
            "primary": primary(rd, redraws=redraws),
            "expressions": expression_spread(rd)}


def cached(store: RunStore, redraws: int = 2000, refresh: bool = False) -> dict:
    """all_measures, kept in the run folder (measures.json) until the run, the redraws or this module change."""
    m = store.read_json("manifest.json", {})
    key = {"rounds_done": m.get("rounds_done"), "redraws": redraws, "version": VERSION}
    hit = store.read_json("measures.json")
    if hit and hit.get("key") == key and not refresh:
        return hit["data"]
    data = json.loads(json.dumps(all_measures(store, redraws=max(100, min(redraws, 20000))), ensure_ascii=False, default=str))
    store.write_json("measures.json", {"key": key, "data": data})
    return data

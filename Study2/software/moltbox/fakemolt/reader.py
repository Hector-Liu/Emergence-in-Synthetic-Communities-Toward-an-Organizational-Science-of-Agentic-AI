"""Read-only views of a run for people (the Forum pages) and exports for reading and hand coding.

Everything is rebuilt from the logs: actions.jsonl replays the forum at any round, and
visits.jsonl says exactly what each agent was shown, so an agent's view of a visit is the
forum as it stood before that round, filtered to the items its prompt contained.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict

from .config import RunConfig
from .forum import Forum, Post, replay
from .store import RunStore


class Reader:
    def __init__(self, store: RunStore):
        self.store = store
        self.cfg = RunConfig.model_validate(store.read_json("config.json"))
        self.actions = store.read_jsonl("actions.jsonl")
        self.communities = [c.name for c in self.cfg.communities]
        self.final = replay(self.communities, self.actions)
        self.cohort = {h: ("founder" if a.phase == 0 else "newcomer") for h, a in self.final.agents.items()}
        self._visits = None

    @property
    def visits(self) -> list[dict]:
        if self._visits is None:
            self._visits = self.store.read_jsonl("visits.jsonl")
        return self._visits

    def state(self, upto_round: int | None) -> Forum:
        return self.final if upto_round is None else replay(self.communities, self.actions, upto_round=upto_round)

    # ---- objects --------------------------------------------------------------------
    def post(self, f: Forum, p: Post, voters=False) -> dict:
        d = {"id": p.id, "author": p.author, "cohort": self.cohort.get(p.author), "round": p.round,
             "community": p.community, "title": p.title, "body": p.body, "upvotes": f.upvotes(p.id),
             "n_comments": f.comment_count(p.id),
             "updates": [{"id": u.id, "round": u.round, "body": u.body} for u in p.updates]}
        if voters:
            d["voters"] = sorted(f.votes.get(p.id, ()))
        return d

    def comment(self, f: Forum, c, voters=False) -> dict:
        d = {"id": c.id, "author": c.author, "cohort": self.cohort.get(c.author), "round": c.round, "post": c.post,
             "parent": c.parent, "parent_author": f.author_of(c.parent), "body": c.body, "upvotes": f.upvotes(c.id),
             "n_replies": len(f.replies(c.id))}
        if voters:
            d["voters"] = sorted(f.votes.get(c.id, ()))
        return d

    # ---- views ----------------------------------------------------------------------
    def forum(self, round_: int | None) -> dict:
        f = self.state(round_)
        posts = [dict(self.post(f, p, voters=True), comments=[self.comment(f, c, voters=True) for c in f.comments_of_post(p.id)])
                 for p in f.posts.values()]
        agents = []
        for h, a in f.agents.items():
            mine = f.items_by(h)
            agents.append({**a.__dict__, "cohort": self.cohort[h], "items": len(mine),
                           "posts": sum(isinstance(x, Post) for x in mine)})
        boards = [{"name": c, "description": d.description, "author": None, "round": 0}
                  for c, d in zip(self.communities, self.cfg.communities)]
        boards += [{**b.__dict__, "cohort": self.cohort.get(b.author)} for b in f.boards.values()]
        for b in boards:
            mine = [p for p in posts if p["community"] == b["name"]]
            b.update(posts=len(mine), comments=sum(p["n_comments"] for p in mine))
        return {"round": f.round, "last_round": self.final.round, "posts": posts, "agents": agents, "boards": boards}

    def profile(self, handle: str) -> dict:
        f = self.final
        a = f.agents.get(handle)
        if a is None:
            return {}
        items = []
        for it in f.items_by(handle):
            if isinstance(it, Post):
                items.append({"kind": "post", **self.post(f, it)})
            else:
                items.append({"kind": "comment", **self.comment(f, it)})
        up_recv = sum(len(f.votes.get(x["id"], ())) for x in items)
        rep_recv = sum(1 for c in f.comments.values() if f.author_of(c.parent) == handle and c.author != handle)
        given = [t for t, vs in f.votes.items() if handle in vs]
        visits = [{"round": v["round"], "status": v["status"], "action": v["action"], "item": v["item"],
                   "chose": v.get("chose"), "order": v.get("order"),
                   "upvotes": v["upvotes"], "slots": [s["slot"] for s in v["slots"]], "notified": len(v.get("notified", []))}
                  for v in self.visits if v["handle"] == handle]
        return {"agent": {**a.__dict__, "cohort": self.cohort[handle]}, "items": items, "visits": visits,
                "stats": {"visits": len(visits), "posts": sum(i["kind"] == "post" for i in items),
                          "comments": sum(i["kind"] == "comment" for i in items), "upvotes_received": up_recv,
                          "replies_received": rep_recv, "upvotes_given": len(given),
                          "nothing": sum(v["action"] == "none" for v in visits),
                          "void": sum(v["status"] != "ok" for v in visits)}}

    def agent_view(self, handle: str, round_: int) -> dict:
        """The forum exactly as `handle` saw it on its visit in `round_`, and what it did."""
        v = next((x for x in self.visits if x["handle"] == handle and x["round"] == round_), None)
        if v is None:
            return {}
        # v0.4 visits saw the forum after `seen_upto` actions (earlier visits of the same round included)
        f = replay(self.communities, self.actions[:v["seen_upto"]]) if "seen_upto" in v else self.state(round_ - 1)
        feed = []
        for s in v["slots"]:
            p = f.posts[s["post"]]
            cslot = {c: k for k, ids in (v.get("comment_slots") or {}).get(p.id, {}).items() for c in ids}
            feed.append({"slot": s["slot"], "post": self.post(f, p),
                         "comments": [dict(self.comment(f, f.comments[c]), slot=cslot.get(c))
                                      for c in v["shown_comments"].get(p.id, [])]})
        notes = [self.comment(f, f.comments[c]) for c in v.get("notified", [])]
        others = [dict(self.comment(f, f.comments[c]), post_title=f.posts[f.comments[c].post].title)
                  for c in v.get("forum_comments", [])]
        own = list(reversed(f.items_by(handle)))
        record = [({"kind": "post", **self.post(f, it)} if isinstance(it, Post) else {"kind": "comment", **self.comment(f, it)})
                  for it in own]
        did = {"upvoted": [], "wrote": None}
        for a in self.actions:
            if a.get("round") != round_:
                continue
            if a["kind"] == "vote" and a["voter"] == handle:
                did["upvoted"].append(a["target"])
            elif a["kind"] in ("post", "comment", "update", "board") and a["author"] == handle:
                did["wrote"] = {k: a.get(k) for k in ("kind", "id", "title", "body", "parent", "post", "community",
                                                      "name", "description")}
        nav = v.get("nav") or {}
        boards = []
        for name in nav.get("boards_shown", []):
            b = f.boards.get(name)
            boards.append({"name": name, "description": b.description if b else next(
                (c.description for c in self.cfg.communities if c.name == name), ""), "author": b.author if b else None})
        calls = [{"step": c.get("step", 0), "attempt": c["attempt"], "system": c["system"], "user": c["user"],
                  "raw": c["result"].get("raw"),
                  "stop_reason": c["result"].get("stop_reason"), "usage": c["result"].get("usage"),
                  "cost": c["result"].get("cost"), "thinking": c["result"].get("thinking_summary"),
                  "error": c["result"].get("error")}
                 for c in self.store.read_jsonl("calls.jsonl") if c["handle"] == handle and c["round"] == round_]
        mine = [x["round"] for x in self.visits if x["handle"] == handle]
        i = mine.index(round_)
        return {"handle": handle, "cohort": self.cohort.get(handle), "round": round_, "status": v["status"],
                "chose": v.get("chose"), "order": v.get("order"), "nav_boards": boards,
                "action": v["action"], "notifications": notes, "feed": feed, "other_threads": others, "record": record,
                "record_full": self.cfg.memory.recent_full, "memory_on": self.cfg.switches.memory == "on",
                "did": did, "calls": calls, "prev": mine[i - 1] if i > 0 else None,
                "next": mine[i + 1] if i + 1 < len(mine) else None, "visit_no": i + 1, "visits": len(mine)}

    def activity(self) -> list[dict]:
        """Chronological actions; upvotes grouped per voter and round."""
        f = self.final
        out, votes = [], defaultdict(list)
        for a in self.actions:
            k = a["kind"]
            if k == "agent":
                ag = a["agent"]
                out.append({"round": a["round"], "kind": "join", "who": ag["handle"], "cohort": self.cohort.get(ag["handle"])})
            elif k == "post":
                out.append({"round": a["round"], "kind": "post", "who": a["author"], "cohort": self.cohort.get(a["author"]),
                            "id": a["id"], "title": a["title"], "text": a["body"][:220]})
            elif k == "comment":
                out.append({"round": a["round"], "kind": "comment", "who": a["author"], "cohort": self.cohort.get(a["author"]),
                            "id": a["id"], "post": a["post"], "parent": a["parent"], "to": f.author_of(a["parent"]),
                            "text": a["body"][:220]})
            elif k == "update":
                out.append({"round": a["round"], "kind": "update", "who": a["author"], "cohort": self.cohort.get(a["author"]),
                            "id": a["post"], "title": f.posts[a["post"]].title, "text": a["body"][:220]})
            elif k == "board":
                out.append({"round": a["round"], "kind": "board", "who": a["author"], "cohort": self.cohort.get(a["author"]),
                            "title": a["name"], "text": a["description"]})
            elif k == "vote":
                votes[(a["round"], a["voter"])].append(a["target"])
        for (r, who), targets in votes.items():
            out.append({"round": r, "kind": "votes", "who": who, "cohort": self.cohort.get(who), "targets": targets})
        order = {"join": 0, "board": 1, "post": 2, "update": 3, "comment": 4, "votes": 5}
        return sorted(out, key=lambda x: (x["round"], order[x["kind"]]))

    # ---- exports --------------------------------------------------------------------
    def csv(self) -> str:
        f = self.final
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "kind", "round", "author", "cohort", "model", "community", "post_id", "parent_id",
                    "parent_author", "title", "body", "words", "upvotes", "direct_replies", "thread_comments"])
        rows = []
        for p in f.posts.values():
            rows.append([p.id, "post", p.round, p.author, self.cohort.get(p.author), f.agents[p.author].model, p.community,
                         p.id, "", "", p.title, p.body, len(p.body.split()), f.upvotes(p.id), len(f.replies(p.id)),
                         f.comment_count(p.id)])
        for c in f.comments.values():
            rows.append([c.id, "comment", c.round, c.author, self.cohort.get(c.author), f.agents[c.author].model,
                         f.posts[c.post].community, c.post, c.parent, f.author_of(c.parent), "", c.body,
                         len(c.body.split()), f.upvotes(c.id), len(f.replies(c.id)), ""])
        for r in sorted(rows, key=lambda r: (r[2], r[1] != "post", int(r[0].split("_")[1]))):
            w.writerow(r)
        return "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 correctly

    def markdown(self) -> str:
        f = self.final
        m = self.store.read_json("manifest.json", {})
        lines = [f"# Fake Moltbook run {self.store.run_id}", "",
                 f"{len(f.agents)} agents · {len(f.posts)} posts · {len(f.comments)} comments · "
                 f"{sum(len(v) for v in f.votes.values())} upvotes · {f.round} rounds · models: "
                 f"{', '.join(m.get('models', []))} · cost ${m.get('cost', 0):.2f}", "",
                 "Rounds are shown to agents as hours. F = founder, N = newcomer. ▲ = upvotes.", ""]
        tag = lambda h: f"{h} ({'F' if self.cohort.get(h) == 'founder' else 'N'})"  # noqa: E731
        if f.boards:
            lines += ["## Boards started by members", ""]
            lines += [f"- **{b.name}** · {tag(b.author)} · round {b.round}: {b.description}" for b in f.boards.values()]
            lines.append("")
        for p in sorted(f.posts.values(), key=lambda p: int(p.id[2:])):
            lines += [f"## {p.id} · {p.title}", "",
                      f"*{tag(p.author)} · {p.community} · round {p.round} · ▲{f.upvotes(p.id)} · {f.comment_count(p.id)} comments*", "",
                      p.body, ""]
            lines += [f"> **Update** (round {u.round}): {u.body}" for u in p.updates] + ([""] if p.updates else [])

            def walk(item_id, depth):
                for c in f.replies(item_id):
                    body = " ".join(c.body.split())
                    lines.append(f"{'  ' * depth}- **{tag(c.author)}** · r{c.round} · ▲{f.upvotes(c.id)} · `{c.id}`: {body}")
                    walk(c.id, depth + 1)
            walk(p.id, 0)
            lines.append("")
        return "\n".join(lines)

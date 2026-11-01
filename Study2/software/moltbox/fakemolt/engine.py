"""Phases and the round loop (SPEC 4).

One round: the visitors act in a seeded order (v0.4 "sequential": each sees what the visits before it
wrote; "simultaneous": all see the round's start, as in v0.3). A visit is one call, or two with
two-step visits (choose where to go, then act); one retry each; results commit in visit order. A run
stopped at any point resumes from its last committed round; calls already logged are reused, never re-sent.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import platform
import threading
import time

from . import expressions, guard, texts
from .expressions import forum_comment_text
from .config import RunConfig
from .forum import Agent, Forum, replay
from .llm import CallResult, make_model
from .prompts import build_nav, build_visit, retry_line, validate, validate_nav
from .rng import rng_for
from .store import RunStore

HANDLE_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"


class Cancelled(Exception):
    pass


class StopRun(Exception):
    def __init__(self, status: str, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def templates(cfg: RunConfig) -> tuple[str, str]:
    s = texts.default_template("system") if cfg.prompts.system == "default" else cfg.prompts.system
    v = texts.default_template("visit") if cfg.prompts.visit == "default" else cfg.prompts.visit
    return s, v


def nav_template(cfg: RunConfig) -> str:
    return texts.default_template("nav") if cfg.prompts.nav == "default" else cfg.prompts.nav


def make_agents(cfg: RunConfig, phase_idx: int, first_round: int, start_index: int, taken: set) -> list[Agent]:
    phase = cfg.phases[phase_idx]
    n = sum(g.n for g in phase.add)
    if n == 0:
        return []
    rng = rng_for(cfg.seed, "handles", phase_idx)
    words = texts.denylist(False)
    handles = []
    while len(handles) < n:
        h = "u_" + "".join(rng.choice(list(HANDLE_CHARS), size=6))
        if h not in taken and h not in handles and not guard.find(h.replace("_", " "), words):
            handles.append(h)
    names = [c.name for c in cfg.communities]
    homes = [names[i % len(names)] for i in range(n)]
    homes = [homes[i] for i in rng_for(cfg.seed, "assign", phase_idx).permutation(n)]
    models = [g.model for g in phase.add for _ in range(g.n)]
    return [Agent(handle=h, model=m, home=home, joined_round=first_round, phase=phase_idx, index=start_index + i)
            for i, (h, m, home) in enumerate(zip(handles, models, homes))]


class Run:
    def __init__(self, cfg: RunConfig, store: RunStore, model_factory=make_model, progress=None,
                 cancel: threading.Event | None = None, mode: str = "full"):
        self.cfg, self.store, self.mode = cfg, store, mode
        self.model_factory = model_factory
        self._models: dict[str, object] = {}
        self.progress = progress or (lambda ev: None)
        self.cancel = cancel or threading.Event()
        self.system_t, self.visit_t = templates(cfg)
        self.nav_t = nav_template(cfg)
        self.words = texts.denylist(cfg.switches.tell_ai)
        self.forum = Forum(communities=[c.name for c in cfg.communities])
        self.start_round = 1
        self.call_cache: dict[tuple, dict] = {}
        self.cost = 0.0
        self.calls = 0
        self.refusals = 0
        self.errors = 0
        self.voids = 0
        self.visits_done = 0
        self.round_log: list[dict] = []
        self.seeded_ids: set | None = None  # set once phase 1 ends (frozen founder expressions)
        self.last_visit: dict[str, int] = {}  # handle -> round of its previous visit
        self.last_mark: dict[str, int] = {}  # handle -> comments that existed when its previous visit began
        self.n_actions = 0  # actions committed in earlier rounds (visits log what they saw as `seen_upto`)
        self._beat_cache: dict[str, set] = {}
        k = cfg.opening_visitors()  # founders 0..n1-1 are created first, so indices are positions
        n1 = sum(g.n for g in cfg.phases[0].add)
        self.opening = None if k is None else set(rng_for(cfg.seed, "opening").choice(n1, size=k, replace=False).tolist())

    # ---- setup ---------------------------------------------------------------
    @classmethod
    def new(cls, cfg: RunConfig, store: RunStore, mode="full", **kw) -> "Run":
        run = cls(cfg, store, mode=mode, **kw)
        store.write_json("config.json", cfg.model_dump())
        s, v = run.system_t, run.visit_t
        from .prompts import schema
        store.write_json("prompts.json", {"system": s, "visit": v, "nav": run.nav_t, "texts_version": texts.VERSION,
                                          "schema": schema(len(cfg.communities) > 1, cfg.boards_on() and not cfg.visit.two_step,
                                                           updates=cfg.switches.updates),
                                          "effort": cfg.llm.effort, "thinking": {"type": "adaptive", "display": "summarized"}})
        store.update_manifest(run_id=store.run_id, name=cfg.name, mode=mode, created=time.strftime("%Y-%m-%d %H:%M:%S"),
                              status="created", rounds_done=0, total_rounds=cfg.total_rounds(),
                              phase_bounds=cfg.phase_bounds(), agents=cfg.total_agents(), visits=cfg.total_visits(),
                              models=cfg.models(), solo=cfg.switches.solo, cost=0.0, calls=0, void=0, refusals=0, errors=0,
                              budget_usd=cfg.budget_usd, config_hash=config_hash(cfg),
                              versions=versions(), message="")
        return run

    @classmethod
    def resume(cls, store: RunStore, **kw) -> "Run":
        cfg = RunConfig.model_validate(store.read_json("config.json"))
        m = store.read_json("manifest.json", {})
        run = cls(cfg, store, mode=m.get("mode", "full"), **kw)
        last = store.last_complete_round()
        store.truncate_after(last)
        acts = store.read_jsonl("actions.jsonl")
        run.forum = replay(run.forum.communities, acts)
        run.n_actions = len(acts)
        run.start_round = last + 1
        for c in store.read_jsonl("calls.jsonl"):
            run.cost += c["result"].get("cost", 0.0)
            run.calls += 1
            if c["round"] > last:
                run.call_cache[(c["round"], c["handle"], c.get("step", 0), c["attempt"])] = c
        frozen = store.read_json("expressions.json")
        if frozen:
            run.seeded_ids = set(frozen["seeded_posts"]) | set(frozen.get("seeded_comments", []))
        for v in store.read_jsonl("visits.jsonl"):
            run.last_visit[v["handle"]] = max(run.last_visit.get(v["handle"], 0), v["round"])
            if "seen_comments" in v:
                run.last_mark[v["handle"]] = v["seen_comments"]
        rounds = store.read_jsonl("rounds.jsonl")
        run.round_log = rounds
        for r in rounds:
            run.voids += r["void"]
            run.refusals += r["refused"]
            run.errors += r["errors"]
            run.visits_done += r["active"]
        return run

    def model(self, model_id: str):
        key = "mock" if model_id.startswith("mock") else "anthropic"
        if key not in self._models:
            self._models[key] = self.model_factory(model_id)
        return self._models[key]

    def phase_of(self, round_: int) -> int:
        for i, (a, b) in enumerate(self.cfg.phase_bounds()):
            if a <= round_ <= b:
                return i
        raise ValueError(round_)

    # ---- the loop --------------------------------------------------------------
    async def run(self) -> dict:
        hits = guard.preflight(self.cfg, self.system_t, self.visit_t)
        if hits:  # fail closed: nothing is sent
            m = self.store.update_manifest(status="guard", message="Blocked by the word check: " +
                                           str(guard.GuardError(hits)))
            self.progress({"type": "run_end", "status": "guard", "message": m["message"], "manifest": m})
            return m
        self.store.update_manifest(status="running", message="")
        status, message = "done", ""
        try:
            for t in range(self.start_round, self.cfg.total_rounds() + 1):
                if self.cancel.is_set():
                    raise Cancelled()
                self._check_budget(t)
                await self.play_round(t)
                self._check_stop_rules()
        except Cancelled:
            status, message = "cancelled", "Stopped by the user. Resume continues from the last full round."
        except StopRun as ex:
            status, message = ex.status, ex.message
        except guard.GuardError as ex:
            status, message = "guard", str(ex)
        except Exception as ex:  # noqa: BLE001 - recorded, run stays resumable
            status, message = "error", f"{type(ex).__name__}: {ex}"
        m = self.store.update_manifest(status=status, message=message, rounds_done=self.forum.round,
                                       cost=round(self.cost, 6), calls=self.calls, void=self.voids,
                                       refusals=self.refusals, errors=self.errors,
                                       finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        self.progress({"type": "run_end", "status": status, "message": message, "manifest": m})
        return m

    def _check_budget(self, t: int):
        active = (len(self.forum.active_agents(t)) + sum(
            g.n for g in self.cfg.phases[self.phase_of(t)].add) * (t == self.cfg.phase_bounds()[self.phase_of(t)][0])) \
            * self.cfg.visit_rate()
        per_visit = self.cost / self.visits_done if self.visits_done else 0.0
        if self.cost + per_visit * active > self.cfg.budget_usd:
            raise StopRun("budget", f"Budget ${self.cfg.budget_usd:.2f} would be exceeded in round {t} "
                                    f"(spent ${self.cost:.4f}). Raise the budget and resume to continue.")

    def _check_stop_rules(self):
        last3 = self.round_log[-3:]
        act = sum(r["active"] for r in last3)
        if act and sum(r["void"] for r in last3) / act > 0.10 and len(last3) == 3:
            raise StopRun("stopped", "More than 10% of visits were void in the last 3 rounds.")
        if self.calls >= 30 and self.refusals / self.calls > 0.03:
            raise StopRun("stopped", f"{self.refusals} of {self.calls} calls were declined (over 3%).")
        if len(self.round_log) >= 2 and all(r["errors"] > 0 for r in self.round_log[-2:]):
            raise StopRun("error", "API errors in two rounds in a row. Check the key and the model, then resume.")

    def freeze_expressions(self):
        """End of phase 1: fix the founder expressions before any newcomer acts (SPEC 1)."""
        end = self.cfg.phase_bounds()[0][1]
        echo = expressions.engine_ngrams(self.system_t, self.visit_t, self.cfg.communities)
        prior = prior_ngrams(self.cfg.prior_run, self.store.path.parent)
        frozen = expressions.freeze(expressions.forum_items(self.forum, end), echo | prior)
        seeded = sorted((p.id for p in self.forum.posts.values() if p.round <= end and
                         expressions.ngrams(expressions.post_text(p.title, p.body)) & set(frozen)),
                        key=lambda i: int(i.split("_")[1]))
        # phase-1 comments whose slot text (thread title + comment) has a frozen expression
        seeded_c = sorted((c.id for c in self.forum.comments.values() if c.round <= end and
                           expressions.ngrams(forum_comment_text(self.forum, c)) & set(frozen)),
                          key=lambda i: int(i.split("_")[1]))
        self.store.write_json("expressions.json", {
            "frozen_after_round": end, "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rules": {"min_texts": expressions.MIN_TEXTS, "min_founders": expressions.MIN_FOUNDERS, "n": [2, 4],
                      "prior_run": self.cfg.prior_run, "prior_ngrams": len(prior)},
            "expressions": [{"text": " ".join(g), **info} for g, info in
                            sorted(frozen.items(), key=lambda kv: (-kv[1]["texts"], kv[0]))],
            "seeded_posts": seeded, "seeded_comments": seeded_c})
        self.seeded_ids = set(seeded) | set(seeded_c)
        self.progress({"type": "frozen", "expressions": len(frozen), "seeded_posts": len(seeded),
                       "seeded_comments": len(seeded_c)})

    async def play_round(self, t: int):
        """One round (SPEC 4.2, v0.4): the visitors act in a seeded order. Visit k's prompt is built once
        visit k - w has committed (w = order.overlap; "simultaneous" = everyone sees the round's start), and
        results commit strictly in that order, so a rerun builds the same prompts."""
        p_idx = self.phase_of(t)
        if p_idx > 0 and self.seeded_ids is None:
            self.freeze_expressions()
        new_agents: list[Agent] = []
        if t == self.cfg.phase_bounds()[p_idx][0]:
            new_agents = make_agents(self.cfg, p_idx, t, len(self.forum.agents), set(self.forum.agents))
            for a in new_agents:
                self.forum.add_agent(a)
        active = [a for a in self.forum.active_agents(t) if self.visits(a, t)]
        sequential = self.cfg.order.mode == "sequential"
        perm = rng_for(self.cfg.seed, "visit_order" if sequential else "commit", t).permutation(len(active))
        order = [active[i] for i in perm]
        w = self.cfg.order.overlap if sequential else max(1, len(order))
        if t == 1 and sequential and self.cfg.order.opening_together:
            w = max(1, len(order))  # the opening: every round-1 visitor sees the empty forum
        actions = [{"kind": "agent", "round": t, "agent": a.__dict__} for a in new_agents]
        sem = asyncio.Semaphore(self.cfg.llm.concurrency)
        tasks: list[asyncio.Task] = []
        outcomes: list[dict] = []
        snaps: dict[int, Forum] = {}
        made: dict[str, str] = {}
        n_votes = [0]

        async def finish(k: int):
            o = await tasks[k]
            n_votes[0] += self._commit(o, t, actions, made)
            outcomes.append(o)
            self.progress({"type": "visit", "round": t, "k": k + 1, "n": len(order)})

        committed = 0
        try:
            for k, agent in enumerate(order):
                while committed < k - w + 1:
                    await finish(committed)
                    committed += 1
                if w == 1:
                    snap = self.forum  # nothing else is in flight
                else:
                    if committed not in snaps:
                        snaps[committed] = copy.deepcopy(self.forum)
                    snap = snaps[committed]
                info = {"order": k, "seen_upto": self.n_actions + len(actions), "seen_comments": snap.n_comments}
                tasks.append(asyncio.create_task(self._visit(agent, t, snap, info, sem)))
            while committed < len(order):
                await finish(committed)
                committed += 1
        except BaseException:
            for task in tasks:
                task.cancel()
            raise
        self.forum.round = t
        actions.append({"kind": "round_end", "round": t})
        # record
        vrows, summary = [], {"round": t, "phase": p_idx, "active": len(order), "posts": 0, "comments": 0,
                              "boards": 0, "updates": 0, "votes": n_votes[0], "none": 0, "void": 0, "refused": 0,
                              "errors": 0, "left": 0}
        for o in outcomes:
            st, act = o["status"], o["action"]
            if act:
                summary[{"post": "posts", "comment": "comments", "board": "boards", "update": "updates",
                         "none": "none"}[act["kind"]]] += 1
                summary["left"] += o.get("chose") == "leave"
            else:
                summary["void"] += 1
                summary["refused"] += st == "refused"
                summary["errors"] += st == "error"
            v, nav, h = o["visit"], o["nav"], o["handle"]
            row = {"round": t, "handle": h, "status": st, "attempts": o["attempts"],
                   "action": act["kind"] if act else None, "item": made.get(h),
                   "upvotes": len(act["upvote"]) if act else 0, "flags": o["flags"], **o["info"],
                   "chose": o.get("chose"),
                   "slots": v.slots if v else [], "random_pool": v.random_pool if v else [],
                   "seeded_pool": v.seeded_pool if v else [], "shown_comments": v.shown_comments if v else {},
                   "comment_slots": v.comment_slots if v else {}, "boards_shown": v.boards_shown if v else [],
                   "forum_comments": v.forum_comments if v else [], "forum_comment_pool": v.forum_comment_pool if v else 0,
                   "notified": v.notified if v else (nav.notified if nav else []),
                   "memory_replies": v.memory_replies if v else (nav.memory_replies if nav else [])}
            if nav:
                row["nav"] = {"boards_shown": nav.boards_shown, "titles_shown": nav.titles_shown,
                              "notified": nav.notified, "memory_replies": nav.memory_replies}
            vrows.append(row)
        round_cost = sum(o["cost"] for o in outcomes)
        summary.update(cost=round(round_cost, 6), cost_total=round(self.cost, 6), calls=self.calls)
        self.store.append("actions.jsonl", actions)
        self.store.append("visits.jsonl", vrows)
        self.store.append("rounds.jsonl", [summary])
        self.n_actions += len(actions)
        self.round_log.append(summary)
        self.voids += summary["void"]
        self.refusals += summary["refused"]
        self.errors += summary["errors"]
        self.visits_done += len(order)
        for o in outcomes:
            self.last_visit[o["handle"]] = t
            self.last_mark[o["handle"]] = o["info"]["seen_comments"]
        m = self.store.update_manifest(rounds_done=t, cost=round(self.cost, 6), calls=self.calls, void=self.voids,
                                       refusals=self.refusals, errors=self.errors)
        self.progress({"type": "round", "summary": summary, "manifest": m})

    def _commit(self, o: dict, t: int, actions: list, made: dict) -> int:
        """Apply one visit's writing and upvotes to the live forum, in visit order. Returns upvotes added."""
        h, act = o["handle"], o["action"]
        if not act:
            return 0
        kind = act["kind"]
        if kind == "post":
            p = self.forum.add_post(h, act["community"], t, act["title"], act["body"])
            actions.append({"kind": "post", "round": t, "id": p.id, "author": h, "community": p.community,
                            "title": p.title, "body": p.body})
            made[h] = p.id
        elif kind == "comment":
            c = self.forum.add_comment(h, act["parent"], t, act["body"])
            actions.append({"kind": "comment", "round": t, "id": c.id, "author": h, "post": c.post,
                            "parent": c.parent, "body": c.body})
            made[h] = c.id
        elif kind == "update":
            u = self.forum.add_update(h, act["post"], t, act["body"])
            if u:
                actions.append({"kind": "update", "round": t, "id": u.id, "author": h, "post": u.post, "body": u.body})
                made[h] = u.id
        elif kind == "board":
            # two members may pick the same new name: the first in visit order gets it
            if self.forum.add_board(h, act["name"], act["description"], t):
                actions.append({"kind": "board", "round": t, "author": h, "name": act["name"],
                                "description": act["description"]})
                made[h] = act["name"]
            else:
                o["flags"].append({"board_taken": act["name"]})
        n = 0
        for target in act.get("upvote", []):
            if self.forum.add_vote(h, target):
                actions.append({"kind": "vote", "round": t, "voter": h, "target": target})
                n += 1
        return n

    def visits(self, agent: Agent, t: int) -> bool:
        """Seeded per agent and round, so a resumed or re-analysed run makes the same draws."""
        sc = self.cfg.schedule
        if sc.mode == "heartbeat":
            if t in self._beats(agent):
                return True
            if sc.return_on_reply and t > 1 and self._replied_last_round(agent, t):
                return rng_for(self.cfg.seed, "schedule", agent.index, 100000 + t).random() < sc.return_on_reply
            return False
        p = self.cfg.activation
        if p >= 1.0:
            return True
        if t == 1 and self.opening is not None:
            return agent.index in self.opening
        return rng_for(self.cfg.seed, "activation", t, agent.index).random() < p

    def _beats(self, agent: Agent) -> set[int]:
        """The rounds of a heartbeat agent's visits: a seeded start, then every `period` rounds +- `jitter`."""
        if agent.handle in self._beat_cache:
            return self._beat_cache[agent.handle]
        sc, total = self.cfg.schedule, self.cfg.total_rounds()
        T, j = sc.period, sc.jitter
        rng = rng_for(self.cfg.seed, "schedule", agent.index)
        if agent.phase == 0 and self.opening is not None:
            first = 1 if agent.index in self.opening else int(rng.integers(2, T + 2))
        else:
            first = agent.joined_round + int(rng.integers(0, T))
        beats, r, k = set(), first, 0
        while r <= total:
            beats.add(r)
            jit = int(rng_for(self.cfg.seed, "schedule", agent.index, k).integers(-j, j + 1)) if j else 0
            r, k = r + max(1, T + jit), k + 1
        self._beat_cache[agent.handle] = beats
        return beats

    def _replied_last_round(self, agent: Agent, t: int) -> bool:
        mine = {x.id for x in self.forum.items_by(agent.handle)}
        mark = self.last_mark.get(agent.handle, 0)
        return any(c.round == t - 1 and c.author != agent.handle and c.parent in mine and int(c.id[2:]) > mark
                   for c in self.forum.comments.values())

    async def _visit(self, agent: Agent, t: int, snap: Forum, info: dict, sem) -> dict:
        """One visit on the snapshot `snap`: with two-step visits a navigation call, then the action call."""
        h = agent.handle
        # v0.4 sequential: new = written after the previous visit began (by comment number, so replies later in
        # the same round count); simultaneous keeps v0.3's rounds
        mark = self.last_mark.get(h) if self.cfg.order.mode == "sequential" else None
        since = None if mark is not None else self.last_visit.get(h, agent.joined_round - 1)
        out = {"handle": h, "info": info, "visit": None, "nav": None, "chose": None, "flags": [], "cost": 0.0,
               "attempts": 0}
        board = None
        if self.cfg.visit.two_step and self.cfg.boards_on():
            nav = build_nav(snap, h, t, self.cfg, self.system_t, self.nav_t, since=since, mark=mark)
            hits = guard.check_parts(nav.parts, self.words)
            if hits:
                raise guard.GuardError(hits)
            out["nav"] = nav
            effort = self.cfg.llm.effort if self.cfg.visit.nav_effort == "same" else self.cfg.visit.nav_effort
            r1 = await self._call(agent, t, 1, nav.system, nav.user, nav.schema, effort, sem,
                                  lambda data, last: validate_nav(nav, data, snap, self.cfg, h, last))
            out["cost"] += r1["cost"]
            out["flags"] += r1["flags"]
            out["attempts"] = r1["attempts"]
            if r1["status"] != "ok":
                return {**out, "status": r1["status"], "action": None}
            choice = r1["action"]
            out["chose"] = choice["go"]
            if choice["go"] == "leave":
                return {**out, "status": "ok", "action": {"kind": "none", "upvote": []}}
            if choice["go"] == "new_board":
                return {**out, "status": "ok", "action": {"kind": "board", "name": choice["name"],
                                                           "description": choice["description"], "upvote": []}}
            board = choice["go"]
        v = build_visit(snap, h, t, self.cfg, self.system_t, self.visit_t, self.seeded_ids, since=since, mark=mark,
                        board=board)
        hits = guard.check_parts(v.parts, self.words)
        if hits:
            raise guard.GuardError(hits)
        out["visit"] = v
        r2 = await self._call(agent, t, 2 if board is not None else 0, v.system, v.user, v.schema,
                              self.cfg.llm.effort, sem, lambda data, last: validate(v, data, snap, self.cfg, last))
        out["cost"] += r2["cost"]
        out["flags"] += r2["flags"]
        out["attempts"] += r2["attempts"]
        return {**out, "status": r2["status"], "action": r2["action"]}

    async def _call(self, agent: Agent, t: int, step: int, system: str, user0: str, schema_: dict, effort: str, sem,
                    check) -> dict:
        """One model call with one retry; logged before it is used and reused on resume."""
        cost, flags, reason = 0.0, [], None
        for attempt in (0, 1):
            user = user0 if attempt == 0 else user0 + "\n\n" + retry_line(reason, self.cfg)
            key = (t, agent.handle, step, attempt)
            if key in self.call_cache:
                res = CallResult(**self.call_cache[key]["result"])
            else:
                async with sem:
                    if self.cancel.is_set():
                        raise Cancelled()
                    res = await self.model(agent.model).complete(
                        agent.model, system, user, schema_, effort, self.cfg.llm.max_tokens,
                        meta={"handle": agent.handle, "round": t, "attempt": attempt, "step": step})
                self.store.append("calls.jsonl", [{"round": t, "handle": agent.handle, "step": step, "attempt": attempt,
                                                   "model": agent.model, "system": system, "user": user,
                                                   "result": res.to_dict(), "time": time.time()}])
                self.cost += res.cost
                self.calls += 1
            cost += res.cost
            if res.stop_reason == "refusal":
                return {"status": "refused", "action": None, "attempts": attempt + 1, "flags": flags, "cost": cost}
            if res.error:
                return {"status": "error", "action": None, "attempts": attempt + 1, "flags": flags + [res.error],
                        "cost": cost}
            action, reason, f = check(res.data, attempt == 1)
            flags += f
            if action:
                return {"status": "ok", "action": action, "attempts": attempt + 1, "flags": flags, "cost": cost}
            flags.append({"invalid": reason, "step": step})
            if reason is None:
                reason = "json"
        return {"status": "void", "action": None, "attempts": 2, "flags": flags, "cost": cost}


def prior_ngrams(run_ids: str, base=None) -> set:
    """Every n-gram written in the first phase of each prior run (comma-separated ids): what the model
    says in a forum that never met this one. A solo run counts whole (it has one phase)."""
    from .store import find_run
    out = set()
    for run_id in [r.strip() for r in (run_ids or "").split(",") if r.strip()]:
        st = find_run(run_id, base)
        if st is None:
            raise StopRun("error", f"Prior run {run_id} not found.")
        end = RunConfig.model_validate(st.read_json("config.json")).phase_bounds()[0][1]
        for a in st.read_jsonl("actions.jsonl"):
            if a.get("round", 0) > end:
                break
            if a["kind"] == "post":
                out |= expressions.ngrams(expressions.post_text(a["title"], a["body"]))
            elif a["kind"] == "comment":
                out |= expressions.ngrams(a["body"])
    return out


def config_hash(cfg: RunConfig) -> str:
    return hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()[:12]


def versions() -> dict:
    out = {"python": platform.python_version(), "texts": texts.VERSION}
    try:
        import anthropic
        out["anthropic"] = anthropic.__version__
    except ImportError:
        pass
    return out


def run_sync(cfg: RunConfig, store: RunStore, **kw) -> dict:
    return asyncio.run(Run.new(cfg, store, **kw).run())

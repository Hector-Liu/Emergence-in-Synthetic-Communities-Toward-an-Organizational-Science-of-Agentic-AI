"""Run configuration (SPEC section 5). One JSON document, saved with every run."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

DEFAULT_MODEL = "claude-haiku-5-5"


class Community(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,23}$")
    description: str = Field(min_length=1, max_length=80)


class Group(BaseModel):
    n: int = Field(ge=0, le=500)
    model: str = DEFAULT_MODEL


class Phase(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    add: list[Group] = []
    rounds: int = Field(ge=1, le=1000)


class Prompts(BaseModel):
    system: str = "default"  # "default" = texts/v1/system.txt; otherwise the full edited text
    visit: str = "default"
    nav: str = "default"  # step 1 of two-step visits (texts/v1/nav.txt)


class Schedule(BaseModel):
    # "coin": each agent visits each round with probability `activation` (v0.3);
    # "heartbeat": each agent comes back every `period` rounds, moved by up to `jitter` (v0.4)
    mode: Literal["coin", "heartbeat"] = "heartbeat"
    period: int = Field(2, ge=1, le=50)
    jitter: int = Field(1, ge=0, le=10)
    return_on_reply: float = Field(0.0, ge=0.0, le=1.0)  # extra visit next round after a reply (0 = off)


class Order(BaseModel):
    # "simultaneous": everyone in a round sees the same snapshot (v0.3); "sequential": visitors act one
    # after another in a seeded order, and visit k sees every visit up to k - overlap (v0.4)
    mode: Literal["simultaneous", "sequential"] = "sequential"
    overlap: int = Field(1, ge=1, le=64)
    opening_together: bool = True  # round 1's visitors all see the empty forum (v0.4.1); turns start in round 2


class VisitShape(BaseModel):
    two_step: bool = True  # first choose where to go (a board, all, a new board, or leave), then act there
    nav_effort: Literal["same", "low", "medium", "high"] = "same"


class Switches(BaseModel):
    # off by default since v0.3.1: agents are not told what the members are, so any talk of being AI is
    # their own (measured in describe()); the denylist then keeps AI/human words out of all engine text
    tell_ai: bool = False
    goal: Literal["none", "participate", "upvotes"] = "none"
    memory: Literal["on", "off"] = "on"
    solo: bool = False
    show_upvotes: Literal["all", "others", "none"] = "all"  # "others": hide counts in the agent's own record
    updates: bool = True  # authors may append an update (up to 60 words) to their own post (v0.4)
    # a conditional cue in the action menu: "If none of the posts here interest you, you may start a new post."
    # On by default since v0.4.3 (matched pilot: off -> 0 new posts and 49 of 52 comments in one thread; on -> 9
    # new posts). Report it as part of the design; the cue-off run is the comparison condition.
    post_hint: bool = True


class Feed(BaseModel):
    new: int = Field(4, ge=0, le=30)
    hot: int = Field(4, ge=0, le=30)
    other_hot: int = Field(0, ge=0, le=5)  # per other community; only with several communities
    random: int = Field(1, ge=0, le=30)  # uniform from all posts
    # uniform from phase-1 posts that contain a frozen founder expression; until the list is frozen
    # (end of phase 1) these slots draw from all posts like `random`
    random_seeded: int = Field(1, ge=0, le=30)
    hot_window: int = Field(40, ge=1, le=1000)  # rounds; 40 rounds at activation 0.25 = about 10 visits per agent
    # comments under each post (SPEC 2.3): the newest, then the most upvoted of the rest, then a seeded
    # uniform draw from what is left. The random ones are part of the primary analysis.
    comments_new: int = Field(3, ge=0, le=10)
    comments_top: int = Field(3, ge=0, le=10)
    comments_random: int = Field(3, ge=0, le=10)
    # runs made before v0.3 showed the 2 newest plus the most upvoted, up to this many; set only by their configs
    comments_per_post: Optional[int] = Field(None, ge=0, le=10)
    own_posts: bool = True  # the agent's own posts can fill its new and hot slots (never the random ones)
    # comments drawn from the whole forum and shown under "From other threads" with their thread's title.
    # After phase 1 they come from founders' phase-1 comments that contain a frozen expression, so newcomers
    # meet founder language at random even when few posts exist (the post slots then rarely fire).
    random_comment: int = Field(1, ge=0, le=10)
    notifications: int = Field(5, ge=0, le=30)


class Memory(BaseModel):
    recent_full: int = Field(10, ge=0, le=100)
    short_words: int = Field(25, ge=1, le=200)
    replies_shown: int = Field(2, ge=0, le=10)
    own_posts: bool = True  # the record starts with all the agent's own posts and what is new under them (v0.4)
    thread_comments: int = Field(3, ge=0, le=10)  # newest comments shown under each own post


class Limits(BaseModel):
    title_words: int = Field(15, ge=1, le=100)
    post_words: int = Field(150, ge=1, le=2000)
    comment_words: int = Field(80, ge=1, le=2000)
    overrun: float = Field(1.5, ge=1.0, le=5.0)


class Boards(BaseModel):
    # members can start boards (like submolts); the configured community is the first board (SPEC 2.5)
    on: bool = True
    per_agent: int = Field(1, ge=0, le=20)  # boards one member may start over the whole run
    description_words: int = Field(30, ge=1, le=200)
    shown: int = Field(20, ge=1, le=200)  # boards listed on each visit
    order: Literal["random", "activity"] = "random"  # list order: seeded shuffle per visit (v0.4) or most active first
    note: bool = True  # system prompt says what boards are (v0.4)


class LLM(BaseModel):
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    max_tokens: int = Field(16000, ge=256, le=64000)
    concurrency: int = Field(8, ge=1, le=64)


def _default_phases() -> list[Phase]:
    # with a visit every 2 rounds (heartbeat) these give the same expected visits as 20 + 30 rounds at full
    # activation (about 1,400)
    return [Phase(name="founders", add=[Group(n=10)], rounds=40),
            Phase(name="newcomers", add=[Group(n=30)], rounds=60)]


class RunConfig(BaseModel):
    name: str = Field("", max_length=60)
    seed: int = Field(1, ge=0, le=2**31 - 1)
    communities: list[Community] = Field(default_factory=lambda: [Community(name="general", description="anything")])
    phases: list[Phase] = Field(default_factory=_default_phases)
    prompts: Prompts = Prompts()
    switches: Switches = Switches()
    feed: Feed = Feed()
    memory: Memory = Memory()
    limits: Limits = Limits()
    boards: Boards = Boards()
    schedule: Schedule = Schedule()
    order: Order = Order()
    visit: VisitShape = VisitShape()
    llm: LLM = LLM()
    budget_usd: float = Field(5.0, ge=0.0, le=1000.0)
    # comma-separated run ids whose first phase shows what the model writes without this forum: their
    # n-grams are not counted as founder expressions (SPEC 1). Best: the founder phases of independent
    # replicate runs (they produce the model's stock reply phrases too); a solo run only shows first posts.
    prior_run: str = Field("", max_length=2000)
    # chance that an agent visits in a given round (seeded per agent and round). Below 1, agents act at
    # different times and see different snapshots instead of all reacting to the same one.
    activation: float = Field(0.25, gt=0.0, le=1.0)
    # founders who visit in round 1 (a seeded draw), instead of the activation coin. The opening decides a lot:
    # with 1 visitor in round 1 one host owned the forum (3/3 pilot runs, about 85% of comments in one thread);
    # with 4, eight posts and several threads followed (2/2). 0 = no special rule.
    # v0.4.1: -1 = every founder visits in round 1, all at once (the forum's opening), so several threads start
    opening: int = Field(-1, ge=-1, le=500)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        """A saved config from before v0.4 (it has phases but no schedule) keeps the v0.3 behaviour."""
        if isinstance(data, dict) and "phases" in data and "post_hint" not in (data.get("switches") or {}):
            data = {**data, "switches": {**(data.get("switches") or {}), "post_hint": False}}  # saved before v0.4.3
        if isinstance(data, dict) and "phases" in data and "schedule" not in data:
            data = dict(data)
            data["schedule"] = {"mode": "coin"}
            data.setdefault("opening", 0)  # configs from before v0.3.1 had no fixed opening
            data["order"] = {"mode": "simultaneous"}
            data["visit"] = {"two_step": False}
            data["switches"] = {**data.get("switches", {}), "updates": data.get("switches", {}).get("updates", False)}
            data["memory"] = {**data.get("memory", {}), "own_posts": data.get("memory", {}).get("own_posts", False)}
            data["boards"] = {**data.get("boards", {}), "order": data.get("boards", {}).get("order", "activity"),
                              "note": data.get("boards", {}).get("note", False)}
        return data

    @model_validator(mode="after")
    def _check(self):
        names = [c.name for c in self.communities]
        if not names:
            raise ValueError("at least one community is needed")
        if len(set(names)) != len(names):
            raise ValueError("community names must be unique")
        if not self.phases or sum(g.n for g in self.phases[0].add) < 1:
            raise ValueError("the first phase must add at least one agent")
        if self.total_agents() < 2:
            raise ValueError("a forum needs at least two agents")
        if self.feed.new + self.feed.hot + self.feed.random + self.feed.random_seeded + self.feed.other_hot == 0 \
                and not self.switches.solo:
            raise ValueError("the feed shows no posts")
        return self

    # ---- derived numbers -------------------------------------------------
    def boards_on(self) -> bool:
        """Members can start boards; only with a single configured community, which is the first board."""
        return self.boards.on and len(self.communities) == 1

    def total_agents(self) -> int:
        return sum(g.n for p in self.phases for g in p.add)

    def total_rounds(self) -> int:
        return sum(p.rounds for p in self.phases)

    def phase_bounds(self) -> list[tuple[int, int]]:
        """(first_round, last_round) per phase, 1-based and inclusive."""
        out, start = [], 1
        for p in self.phases:
            out.append((start, start + p.rounds - 1))
            start += p.rounds
        return out

    def visit_rate(self) -> float:
        """Expected share of present agents visiting in a round."""
        return 1.0 / self.schedule.period if self.schedule.mode == "heartbeat" else self.activation

    def total_visits(self) -> int:
        """Expected visits (the schedule makes the count vary a little)."""
        active, total = 0, 0
        for p in self.phases:
            active += sum(g.n for g in p.add)
            total += active * p.rounds
        visits = total * self.visit_rate()
        n1 = sum(g.n for g in self.phases[0].add)
        if self.opening_visitors() is not None:  # round 1: exactly the opening visitors
            visits += self.opening_visitors() - n1 * self.visit_rate()
        return round(visits)

    def opening_visitors(self) -> int | None:
        """How many founders visit in round 1, or None when the activation coin decides."""
        n1 = sum(g.n for g in self.phases[0].add)
        if not self.opening or self.visit_rate() >= 1:
            return None
        return n1 if self.opening < 0 else min(self.opening, n1)

    def models(self) -> list[str]:
        return sorted({g.model for p in self.phases for g in p.add if g.n})


def smoke_config(cfg: RunConfig) -> RunConfig:
    """The smoke run of SPEC section 9: 5 founders for about 3 visits each, then +5 newcomers for about 2
    (rounds scaled by the activation probability)."""
    import math
    r1, r2 = math.ceil(3 / cfg.visit_rate()), math.ceil(2 / cfg.visit_rate())
    first_model = next((g.model for g in cfg.phases[0].add if g.n), DEFAULT_MODEL)
    later = [g.model for p in cfg.phases[1:] for g in p.add if g.n]
    d = cfg.model_dump()
    d["name"] = (cfg.name + " smoke").strip()
    d["phases"] = [{"name": "founders", "add": [{"n": 5, "model": first_model}], "rounds": r1},
                   {"name": "newcomers", "add": [{"n": 5, "model": later[0] if later else first_model}], "rounds": r2}]
    return RunConfig.model_validate(d)

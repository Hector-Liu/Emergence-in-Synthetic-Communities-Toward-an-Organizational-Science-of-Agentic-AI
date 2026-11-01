"""Forum state (SPEC section 2): agents, posts, comments, upvotes.

The state only changes in `commit()` at the end of a round, so during a round
it *is* the snapshot every prompt is built from. The whole state can be rebuilt
by replaying the action log (`actions.jsonl`).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Agent:
    handle: str
    model: str
    home: str
    joined_round: int
    phase: int  # index of the phase that added it
    index: int  # order of creation, used for seeded streams


@dataclass
class Update:
    id: str  # u-numbered in commit order: "up_1", "up_2", ...
    post: str
    round: int
    body: str


@dataclass
class Post:
    id: str
    author: str
    community: str
    round: int
    title: str
    body: str
    updates: list = field(default_factory=list)  # Update objects, oldest first (v0.4)


@dataclass
class Comment:
    id: str
    author: str
    post: str
    parent: str  # a post id or a comment id
    round: int
    body: str


@dataclass
class Board:
    name: str
    description: str
    author: str  # the member who started it
    round: int


@dataclass
class Forum:
    communities: list[str]  # configured communities; with boards on, the single one is the first board
    agents: dict[str, Agent] = field(default_factory=dict)
    posts: dict[str, Post] = field(default_factory=dict)
    comments: dict[str, Comment] = field(default_factory=dict)
    votes: dict[str, set] = field(default_factory=dict)  # target id -> voters
    boards: dict[str, Board] = field(default_factory=dict)  # boards started by members, in order
    n_posts: int = 0
    n_comments: int = 0
    n_updates: int = 0
    round: int = 0  # last committed round
    _children: dict[str, list[str]] = field(default_factory=dict)  # item id -> direct reply comment ids
    _post_comments: dict[str, list[str]] = field(default_factory=dict)

    # ---- reads -------------------------------------------------------------
    def item(self, item_id: str):
        return self.posts.get(item_id) or self.comments.get(item_id)

    def author_of(self, item_id: str) -> str | None:
        it = self.item(item_id)
        return it.author if it else None

    def upvotes(self, item_id: str) -> int:
        return len(self.votes.get(item_id, ()))

    def has_voted(self, handle: str, item_id: str) -> bool:
        return handle in self.votes.get(item_id, ())

    def replies(self, item_id: str) -> list[Comment]:
        """Direct replies: top-level comments of a post, or replies to a comment."""
        return [self.comments[c] for c in self._children.get(item_id, ())]

    def comments_of_post(self, post_id: str) -> list[Comment]:
        return [self.comments[c] for c in self._post_comments.get(post_id, ())]

    def comment_count(self, post_id: str) -> int:
        return len(self._post_comments.get(post_id, ()))

    def items_by(self, handle: str) -> list:
        """The agent's own posts and comments, oldest first."""
        own = [p for p in self.posts.values() if p.author == handle]
        own += [c for c in self.comments.values() if c.author == handle]
        return sorted(own, key=lambda x: (x.round, _num(x.id), x.id[0]))

    def board_names(self) -> list[str]:
        return list(self.communities) + list(self.boards)

    def active_agents(self, round_: int) -> list[Agent]:
        return sorted((a for a in self.agents.values() if a.joined_round <= round_), key=lambda a: a.index)

    # ---- writes (commit only) ---------------------------------------------
    def add_agent(self, agent: Agent):
        self.agents[agent.handle] = agent

    def add_post(self, author, community, round_, title, body, post_id=None) -> Post:
        self.n_posts += 1
        p = Post(post_id or f"p_{self.n_posts}", author, community, round_, title, body)
        self.posts[p.id] = p
        return p

    def add_comment(self, author, parent, round_, body, comment_id=None) -> Comment:
        target = self.item(parent)
        if target is None:
            raise KeyError(parent)
        post = target.id if isinstance(target, Post) else target.post
        self.n_comments += 1
        c = Comment(comment_id or f"c_{self.n_comments}", author, post, parent, round_, body)
        self.comments[c.id] = c
        self._children.setdefault(parent, []).append(c.id)
        self._post_comments.setdefault(post, []).append(c.id)
        return c

    def add_board(self, author, name, description, round_) -> Board | None:
        if name in self.communities or name in self.boards:
            return None
        b = Board(name, description, author, round_)
        self.boards[name] = b
        return b

    def add_update(self, author, post_id, round_, body, update_id=None) -> Update | None:
        p = self.posts.get(post_id)
        if p is None or p.author != author:
            return None
        self.n_updates += 1
        u = Update(update_id or f"up_{self.n_updates}", post_id, round_, body)
        p.updates.append(u)
        return u

    def add_vote(self, voter, target) -> bool:
        if self.item(target) is None or self.author_of(target) == voter or self.has_voted(voter, target):
            return False
        self.votes.setdefault(target, set()).add(voter)
        return True

    def apply(self, action: dict):
        """Replay one logged action (see engine.commit)."""
        k = action["kind"]
        if k == "agent":
            self.add_agent(Agent(**action["agent"]))
        elif k == "post":
            self.add_post(action["author"], action["community"], action["round"], action["title"], action["body"],
                          post_id=action["id"])
        elif k == "comment":
            self.add_comment(action["author"], action["parent"], action["round"], action["body"],
                             comment_id=action["id"])
        elif k == "board":
            self.add_board(action["author"], action["name"], action["description"], action["round"])
        elif k == "update":
            self.add_update(action["author"], action["post"], action["round"], action["body"], update_id=action["id"])
        elif k == "vote":
            self.add_vote(action["voter"], action["target"])
        elif k == "round_end":
            self.round = action["round"]

    def to_dict(self) -> dict:
        return {"communities": self.communities, "round": self.round,
                "agents": [asdict(a) for a in self.agents.values()],
                "boards": [asdict(b) for b in self.boards.values()],
                "posts": [asdict(p) for p in self.posts.values()],
                "comments": [asdict(c) for c in self.comments.values()],
                "votes": {k: sorted(v) for k, v in self.votes.items()}}


def _num(item_id: str) -> int:
    return int(item_id.split("_", 1)[1])


def replay(communities: list[str], actions, upto_round: int | None = None) -> Forum:
    """Forum state after `upto_round` (all committed rounds if None)."""
    f = Forum(communities=list(communities))
    for a in actions:
        if upto_round is not None and a.get("round", 0) > upto_round:
            break
        f.apply(a)
    return f

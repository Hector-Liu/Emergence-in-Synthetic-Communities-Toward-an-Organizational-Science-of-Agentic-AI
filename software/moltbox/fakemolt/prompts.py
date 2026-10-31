"""The only prompt builder (SPEC 2.3-2.4, 3.2-3.5).

`build_visit()` turns the round's snapshot and one agent's own items into the
two prompt texts, and records what was shown (exposure) and what the agent may
reply to or upvote. `validate()` checks the reply. Nothing here writes state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import texts
from .forum import Comment, Forum, Post
from .rng import rng_for

PLACEHOLDER = re.compile(r"\{(identity|handle|communities|sees|goal|privacy|board_option|update_option|boards_note|"
                         r"notifications|feed|boards|record|opened|actions|post_board|board_rule|update_rule|nav_rule|post_hint|"
                         r"title_words|post_words|comment_words)\}")
UPDATE_WORDS = 60
BOARD_NAME = re.compile(r"[a-z][a-z0-9_]{1,23}")


@dataclass
class Visit:
    handle: str
    round: int
    system: str
    user: str
    parts: list  # (text, "engine" | "agent") for system + user
    slots: list  # [{"post": id, "slot": "new" | "hot" | "other_hot" | "random" | "random_seeded"}], display order
    random_pool: list  # ids the general random slots were drawn from, in id order (seeded picks excluded)
    seeded_pool: list  # ids the seeded random slots were drawn from, in id order
    memory_replies: list  # other agents' replies shown inside the agent's own record
    shown: set  # every post/comment id shown anywhere in the prompt
    shown_comments: dict  # post id -> comment ids shown under it in the feed
    notified: list  # comment ids shown as notifications
    own: set  # the agent's own item ids
    multi: bool
    comment_slots: dict = field(default_factory=dict)  # post id -> {"new", "top", "random": [comment ids]}
    boards_shown: list = field(default_factory=list)  # board names listed in the prompt, in order
    forum_comments: list = field(default_factory=list)  # comment ids drawn under "From other threads"
    forum_comment_pool: int = 0  # how many comments that draw chose from
    schema: dict = field(default_factory=dict)
    board: str | None = None  # two-step visits: where the agent chose to go (a board name or "all")


# ---- helpers ----------------------------------------------------------------
def words(text: str) -> list[str]:
    return text.split()


def shorten(text: str, n: int) -> str:
    w = words(text)
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def _num(item_id: str) -> int:
    return int(item_id.split("_", 1)[1])


def render(template: str, slots: dict[str, list]) -> list:
    """Split a template on its placeholders; template text is engine-authored."""
    parts, pos = [], 0
    for m in PLACEHOLDER.finditer(template):
        if m.start() > pos:
            parts.append((template[pos:m.start()], "engine"))
        parts.extend(slots.get(m.group(1), [(m.group(0), "engine")]))
        pos = m.end()
    if pos < len(template):
        parts.append((template[pos:], "engine"))
    return parts


def join(parts) -> str:
    return "".join(t for t, _ in parts)


def schema(multi: bool, boards: bool = False, updates: bool = False, post_board: bool | None = None) -> dict:
    """`boards`: the board action is offered; `post_board`: a post names its board (default: with `boards`)."""
    post_board = boards if post_board is None else post_board
    d = {**texts.FIELD_DESC, **(texts.FIELD_DESC_BOARDS if boards or post_board else {}),
         **(texts.FIELD_DESC_UPDATES if updates else {})}
    if boards and not post_board:  # inside a chosen board a post needs no board name
        d["board"] = texts.FIELD_DESC_BOARD_ONLY
    kinds = ["post", "comment"] + (["board"] if boards else []) + (["update"] if updates else []) + ["none"]
    d["action"] = ", ".join(kinds[:-1]) + " or none"
    props = {"action": {"type": "string", "enum": kinds, "description": d["action"]},
             "reply_to": {"type": "string", "description": d["reply_to"]},
             "title": {"type": "string", "description": d["title"]},
             "body": {"type": "string", "description": d["body"]},
             "upvote": {"type": "array", "items": {"type": "string"}, "description": d["upvote"]}}
    if multi:
        props = {"action": props["action"], "community": {"type": "string", "description": d["community"]},
                 **{k: v for k, v in props.items() if k != "action"}}
    elif boards or post_board:
        props = {"action": props["action"], "board": {"type": "string", "description": d["board"]},
                 **{k: v for k, v in props.items() if k != "action"}}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


# ---- feed (SPEC 2.3) ----------------------------------------------------------
def hot_key(forum: Forum, p: Post, tie: dict):
    return (-(forum.upvotes(p.id) + forum.comment_count(p.id)), -p.round, tie[p.id])


def select_feed(forum: Forum, handle: str, round_: int, cfg, seeded_ids: set | None = None, board: str | None = None):
    """[(post_id, slot)] in selection order, the general random pool and the seeded pool.

    Random draws (one generator per agent and round): first `random_seeded` posts uniformly
    without replacement from the seeded pool (phase-1 posts with a frozen expression, not
    already chosen), then `random` posts uniformly from every other post not yet chosen.
    Before the list is frozen (`seeded_ids is None`) all random slots use the general pool."""
    agent = forum.agents[handle]
    fc = cfg.feed
    everything = sorted(forum.posts.values(), key=lambda p: _num(p.id))
    if board is not None:  # two-step visits: the feed of one board
        everything = [p for p in everything if p.community == board]
    others = [p for p in everything if p.author != handle]  # random slots only ever show other members' posts
    visible = everything if fc.own_posts else others  # new and hot slots
    if cfg.switches.solo or not visible:
        return [], [], []
    tie_rng = rng_for(cfg.seed, "tiebreak", round_, agent.index)
    tie = dict(zip([p.id for p in visible], tie_rng.permutation(len(visible)).tolist()))
    multi = len(forum.communities) > 1
    home = [p for p in visible if p.community == agent.home] if multi else visible
    chosen: list[tuple[str, str]] = []
    taken: set[str] = set()

    def take(cands, n, slot):
        for p in cands:
            if n <= 0:
                break
            if p.id not in taken:
                chosen.append((p.id, slot))
                taken.add(p.id)
                n -= 1

    take(sorted(home, key=lambda p: (-p.round, -_num(p.id))), fc.new, "new")
    recent = [p for p in home if p.round >= round_ - fc.hot_window]
    take(sorted(recent, key=lambda p: hot_key(forum, p, tie)), fc.hot, "hot")
    if multi and fc.other_hot:
        for c in forum.communities:
            if c != agent.home:
                pool_c = [p for p in visible if p.community == c and p.round >= round_ - fc.hot_window]
                take(sorted(pool_c, key=lambda p: hot_key(forum, p, tie)), fc.other_hot, "other_hot")
    rng = rng_for(cfg.seed, "feed_random", round_, agent.index)
    seeded_pool: list[str] = []
    k_general = fc.random
    if seeded_ids is None:
        k_general += fc.random_seeded
    else:
        seeded_pool = [p.id for p in others if p.id in seeded_ids and p.id not in taken]
        k_s = min(fc.random_seeded, len(seeded_pool))
        if k_s:
            for i in rng.choice(len(seeded_pool), size=k_s, replace=False).tolist():
                chosen.append((seeded_pool[i], "random_seeded"))
                taken.add(seeded_pool[i])
    pool = [p.id for p in others if p.id not in taken]
    k = min(k_general, len(pool))
    if k:
        for i in rng.choice(len(pool), size=k, replace=False).tolist():
            chosen.append((pool[i], "random"))
    return chosen, pool, seeded_pool


def fixed_comments(forum: Forum, post_id: str, fc) -> tuple[list[Comment], list[Comment], list[Comment], int]:
    """(newest, most upvoted, rest, k): the comments a post always shows at this snapshot, the ones
    the random comment slots draw from, and how many they draw (SPEC 2.3). Pre-v0.3 configs
    (`comments_per_post` set) used the 2 newest plus the most upvoted and no random draw."""
    cs = forum.comments_of_post(post_id)
    if fc.comments_per_post is not None:
        n = fc.comments_per_post
        if n <= 0 or not cs:
            return [], [], [], 0
        newest = cs[-min(2, n):] if n >= 2 else cs[-1:]
        rest = cs[:len(cs) - len(newest)]
        top = sorted(rest, key=lambda c: (-forum.upvotes(c.id), -_num(c.id)))[:max(0, n - len(newest))]
        return newest, top, [], 0
    newest = cs[len(cs) - min(fc.comments_new, len(cs)):]
    rest = cs[:len(cs) - len(newest)]
    top_ids = {c.id for c in sorted(rest, key=lambda c: (-forum.upvotes(c.id), _num(c.id)))[:fc.comments_top]}
    top = [c for c in rest if c.id in top_ids]
    rest = [c for c in rest if c.id not in top_ids]
    return newest, top, rest, min(fc.comments_random, len(rest))


def pick_comments(forum: Forum, post_id: str, fc, seed: int, round_: int, agent_index: int) -> dict[str, list[Comment]]:
    """{"new", "top", "random"}: the comments shown under one post on one visit. The random ones are a
    uniform draw without replacement from the rest, one generator per (round, agent, post)."""
    newest, top, rest, k = fixed_comments(forum, post_id, fc)
    picked = []
    if k:
        rng = rng_for(seed, "comment_random", round_, agent_index, _num(post_id))
        picked = [rest[i] for i in sorted(rng.choice(len(rest), size=k, replace=False).tolist())]
    return {"new": newest, "top": top, "random": picked}


# ---- the prompt ---------------------------------------------------------------
def _system_parts(forum: Forum, handle: str, cfg, system_template: str) -> list:
    agent = forum.agents[handle]
    multi = len(forum.communities) > 1
    boards_on = cfg.boards_on()
    E = "engine"
    comm_parts = []
    if multi:
        lines = [texts.COMMUNITIES_HEAD] + [f"- {c.name}: {c.description}" for c in cfg.communities]
        comm_parts = [("\n" + "\n".join(lines) + "\n" + texts.HOME_LINE.format(home=agent.home) + "\n", E)]
    mem_on = cfg.switches.memory == "on"
    notif_on = cfg.feed.notifications > 0
    two_step = cfg.visit.two_step and boards_on
    return render(system_template, {
        "identity": [(texts.IDENTITY_AI if cfg.switches.tell_ai else "", E)],
        "handle": [(handle, E)],
        "communities": comm_parts,
        "sees": [(texts.sees(notif_on, mem_on, boards_on, two_step), E)],
        "board_option": [(texts.BOARD_OPTION if boards_on else "", E)],
        "update_option": [(texts.UPDATE_OPTION if cfg.switches.updates else "", E)],
        "boards_note": [(texts.BOARDS_NOTE if boards_on and cfg.boards.note else "", E)],
        "goal": [(texts.GOALS[cfg.switches.goal], E)],
        "privacy": [(texts.PRIVACY if mem_on else "", E)],
    })


def _upvote_text(forum: Forum, handle: str, cfg):
    show = cfg.switches.show_upvotes

    def up(item_id, own=False):
        """' · N upvotes' (hidden by the show_upvotes switch), plus a mark if this agent upvoted it."""
        hidden = show == "none" or (show == "others" and own)
        out = "" if hidden else " · " + texts.count(forum.upvotes(item_id), "upvote", "upvotes")
        return out + (texts.UPVOTED_MARK if forum.has_voted(handle, item_id) else "")
    return up


def _is_new(c: Comment, round_: int, since: int | None, mark: int | None) -> bool:
    """New since the agent's previous visit: by comment number when a mark is given (v0.4: catches replies
    written later in the same round), else by round (v0.3)."""
    if mark is not None:
        return _num(c.id) > mark
    return (round_ - 1 if since is None else since) < c.round < round_


def _notifications(forum: Forum, handle: str, round_: int, cfg, since, mark):
    E = "engine"
    own_ids = {x.id for x in forum.items_by(handle)}
    fresh = sorted((c for i in own_ids for c in forum.replies(i) if c.author != handle and _is_new(c, round_, since, mark)),
                   key=lambda c: -_num(c.id))
    notified = fresh[:cfg.feed.notifications]
    n_parts = []
    for c in notified:
        target = forum.item(c.parent)
        kind = "post" if isinstance(target, Post) else "comment"
        on = texts.NOTIFY_ON.format(post=target.post) if kind == "comment" else ""
        n_parts += _splice(texts.NOTIFY_LINE.format(id=c.id, author=c.author, kind=kind, target=target.id, on=on,
                                                    body="\x00"), c.body) + [("\n", E)]
    notif_on = cfg.feed.notifications > 0
    if notif_on and len(fresh) > len(notified):
        n_parts.append((texts.NOTIFY_MORE.format(n=len(fresh) - len(notified)) + "\n", E))
    # only when there is something new: an empty "replies" section made visits read as checking for
    # replies (full-1: "none" 3% with replies, 42% without)
    n_parts = [("\n" + texts.NOTIFY_HEAD + "\n", E)] + n_parts if notif_on and notified else []
    return n_parts, notified


def _post_parts(forum: Forum, p: Post, round_: int) -> list:
    """Title, body and any updates of a post, as agent text."""
    E = "engine"
    out = [(p.title, "agent"), ("\n", E), (p.body, "agent"), ("\n", E)]
    for u in p.updates:
        out += [(texts.UPDATE_LINE.format(ago=texts.ago(round_ - u.round)), E), (u.body, "agent"), ("\n", E)]
    return out


def _record(forum: Forum, handle: str, round_: int, cfg, up, tagged: bool, since, mark):
    """The private record (SPEC 3.4): (parts, memory reply ids, ids shown)."""
    E = "engine"
    own_items = forum.items_by(handle)
    shown = {x.id for x in own_items}
    mem_replies: list[str] = []
    parts = [("\n" + texts.RECORD_HEAD + "\n", E)]
    if not own_items:
        return parts + [(texts.NONE_YET + "\n", E)], mem_replies, shown
    mm = cfg.memory

    def item_full(it):
        nonlocal parts
        parts += _own_line(forum, it, round_, tagged, up) + [("\n", E)]
        if isinstance(it, Post):
            parts += [("  Title: ", E)] + _post_parts(forum, it, round_)
        else:
            parts += [("  ", E), (it.body, "agent"), ("\n", E)]
        for r in sorted(forum.replies(it.id), key=lambda c: -_num(c.id))[:mm.replies_shown]:
            if r.author == handle:
                continue
            parts += _splice(texts.OWN_REPLY.format(id=r.id, author=r.author, body="\x00"),
                             shorten(r.body, mm.short_words)) + [("\n", E)]
            shown.add(r.id)
            mem_replies.append(r.id)

    def item_short(it):
        nonlocal parts
        short = it.title if isinstance(it, Post) else shorten(it.body, mm.short_words)
        parts += _own_line(forum, it, round_, tagged, up)
        parts += _splice(texts.SHORT_SUFFIX.format(text="\x00"), short) + [("\n", E)]

    if not mm.own_posts:  # v0.3: posts and comments in one list, newest first
        newest = list(reversed(own_items))
        recent, earlier = newest[:mm.recent_full], newest[mm.recent_full:]
        if recent:
            parts.append((texts.RECENT_HEAD + "\n", E))
            for it in recent:
                item_full(it)
        if earlier:
            parts.append((texts.EARLIER_HEAD + "\n", E))
            for it in earlier:
                item_short(it)
        return parts, mem_replies, shown

    # v0.4: every own post first, with what is new under it, then the comments
    posts = [it for it in reversed(own_items) if isinstance(it, Post)]
    comments = [it for it in reversed(own_items) if not isinstance(it, Post)]
    if posts:
        parts.append((texts.RECORD_POSTS_HEAD + "\n", E))
        for i, p in enumerate(posts):
            cs = [c for c in forum.comments_of_post(p.id) if c.author != handle]
            new = sum(_is_new(c, round_, since, mark) for c in cs)
            line = _own_line(forum, p, round_, tagged, up)
            if new:
                line = line[:-1] + [(line[-1][0] + texts.OWN_POST_NEW.format(n=new), line[-1][1])]
            parts += line + [("\n", E), ("  Title: ", E)]
            if i < mm.recent_full:
                parts += _post_parts(forum, p, round_)
            else:
                parts += [(p.title, "agent"), ("\n", E)]
            for c in sorted(cs, key=lambda c: -_num(c.id))[:mm.thread_comments]:
                parts += _splice(texts.THREAD_LINE.format(id=c.id, author=c.author, body="\x00"),
                                 shorten(c.body, mm.short_words)) + [("\n", E)]
                shown.add(c.id)
                mem_replies.append(c.id)
    if comments:
        parts.append((texts.RECORD_COMMENTS_HEAD + "\n", E))
        recent, earlier = comments[:mm.recent_full], comments[mm.recent_full:]
        if recent:
            parts.append((texts.RECENT_HEAD + "\n", E))
            for it in recent:
                item_full(it)
        if earlier:
            parts.append((texts.EARLIER_HEAD + "\n", E))
            for it in earlier:
                item_short(it)
    return parts, mem_replies, shown


def build_visit(forum: Forum, handle: str, round_: int, cfg, system_template: str, visit_template: str,
                seeded_ids: set | None = None, since: int | None = None, mark: int | None = None,
                board: str | None = None) -> Visit:
    """One visit's action prompt. `since` (round) or `mark` (comment number) is where the agent's previous
    visit stopped seeing; replies after it are new. `board`: with two-step visits, where the agent chose to go
    (a board name or "all"); None = the one-step feed of v0.3."""
    agent = forum.agents[handle]
    multi = len(forum.communities) > 1
    boards_on = cfg.boards_on()
    two_step = board is not None
    lim = cfg.limits
    E = "engine"
    who = lambda h: h + (texts.YOU if h == handle else "")  # noqa: E731
    up = _upvote_text(forum, handle, cfg)
    sys_parts = _system_parts(forum, handle, cfg, system_template)
    mem_on = cfg.switches.memory == "on"

    shown: set[str] = set()
    n_parts, notified = _notifications(forum, handle, round_, cfg, since, mark)
    shown |= {c.id for c in notified}
    own_ids = {x.id for x in forum.items_by(handle)}

    # feed
    in_board = board if two_step and board != "all" else None
    selection, pool, seeded_pool = select_feed(forum, handle, round_, cfg, seeded_ids, board=in_board)
    order = list(range(len(selection)))
    if order:
        order = rng_for(cfg.seed, "display", round_, agent.index).permutation(len(order)).tolist()
    slots = [{"post": selection[i][0], "slot": selection[i][1]} for i in order]
    f_parts, sc, cslots = [], {}, {}
    for s in slots:
        p = forum.posts[s["post"]]
        line = texts.POST_LINE.format(id=p.id, where=_where(forum, p, multi or boards_on), author=who(p.author),
                                      ago=texts.ago(round_ - p.round), up=up(p.id, own=p.author == handle),
                                      nc=texts.count(forum.comment_count(p.id), "comment", "comments"))
        f_parts += _board_splice(line, p.community) + [("\nTitle: ", E)] + _post_parts(forum, p, round_)
        shown.add(p.id)
        picks = pick_comments(forum, p.id, cfg.feed, cfg.seed, round_, agent.index)
        cslots[p.id] = {k: [c.id for c in v] for k, v in picks.items()}
        keep = {c.id for v in picks.values() for c in v}
        cs = [c for c in forum.comments_of_post(p.id) if c.id in keep]  # thread order; the slot is not shown
        sc[p.id] = [c.id for c in cs]
        for c in cs:
            reply = texts.COMMENT_REPLY.format(parent=c.parent) if c.parent in forum.comments else ""
            line = texts.COMMENT_LINE.format(id=c.id, author=who(c.author), reply=reply,
                                             up=up(c.id, own=c.author == handle), body="\x00")
            f_parts += _splice(line, c.body) + [("\n", E)]
            shown.add(c.id)
        f_parts.append(("\n", E))
    # one or more comments drawn from the whole forum (SPEC 2.3, v0.3.1)
    fpick, fpool = forum_comment_draw(forum, handle, round_, cfg, seeded_ids) if f_parts else ([], 0)
    if fpick:
        f_parts.append(("\n" + texts.FORUM_COMMENTS_HEAD + "\n", E))
        for c in fpick:
            p = forum.posts[c.post]
            f_parts += [(texts.FORUM_COMMENT_PRE.format(id=c.id, author=who(c.author), post=p.id), E), (p.title, "agent"),
                        (texts.FORUM_COMMENT_MID.format(up=up(c.id, own=c.author == handle)), E), (c.body, "agent"), ("\n", E)]
            shown |= {c.id, p.id}
    f_parts = _strip_last_newline(_strip_last_newline(f_parts)) or [(texts.NONE_YET, E)]

    # the board list also shows in step 2, so a member starting a board there sees what exists (v0.4.2)
    b_parts, b_shown = board_index(forum, handle, cfg, who, round_) if boards_on else ([], [])

    rec_parts, mem_replies = [], []
    if mem_on:
        rec_parts, mem_replies, rec_shown = _record(forum, handle, round_, cfg, up, multi or boards_on, since, mark)
        shown |= rec_shown

    opened = []
    if two_step:
        opened = [(texts.OPENED_ALL, E)] if board == "all" else \
            [(texts.OPENED_BOARD.split("{name}")[0], E), (board, "agent" if board in forum.boards else E),
             (texts.OPENED_BOARD.split("{name}")[1], E)]
    board_action = boards_on  # v0.4.1: a board can also be started while reading posts (step 2)
    post_board = boards_on and (not two_step or board == "all")
    lim_slot = lambda n: [(str(n), E)]  # noqa: E731
    user_parts = render(visit_template, {
        "opened": opened, "notifications": n_parts, "feed": f_parts, "boards": b_parts, "record": rec_parts,
        "actions": [(texts.actions(board_action, cfg.switches.updates), E)],
        "post_board": [(texts.POST_BOARD if post_board else "", E)],
        "board_rule": [(texts.BOARD_RULE.format(words=cfg.boards.description_words) if board_action else "", E)],
        "update_rule": [(texts.UPDATE_RULE.format(words=UPDATE_WORDS) if cfg.switches.updates else "", E)],
        "post_hint": [(texts.POST_HINT if cfg.switches.post_hint else "", E)],
        "title_words": lim_slot(lim.title_words), "post_words": lim_slot(lim.post_words),
        "comment_words": lim_slot(lim.comment_words)})
    parts = sys_parts + [("\n\x01\n", E)] + user_parts  # \x01 marks the system/user boundary
    return Visit(handle=handle, round=round_, system=join(sys_parts), user=join(user_parts), parts=parts,
              slots=slots, random_pool=pool, seeded_pool=seeded_pool, memory_replies=mem_replies,
              shown=shown, shown_comments=sc, comment_slots=cslots, boards_shown=b_shown,
              forum_comments=[c.id for c in fpick], forum_comment_pool=fpool,
              notified=[c.id for c in notified], own=own_ids, multi=multi,
              schema=schema(multi, board_action, updates=cfg.switches.updates, post_board=post_board),
              board=board if two_step else None)


@dataclass
class Nav:
    """Step 1 of a two-step visit: the board list, new replies and the record; the agent picks where to go."""
    handle: str
    round: int
    system: str
    user: str
    parts: list
    schema: dict
    boards_shown: list
    titles_shown: list  # post ids whose titles appear in the board list (newest post per board)
    notified: list
    memory_replies: list
    shown: set


def build_nav(forum: Forum, handle: str, round_: int, cfg, system_template: str, nav_template: str,
              since: int | None = None, mark: int | None = None) -> Nav:
    multi = len(forum.communities) > 1
    E = "engine"
    who = lambda h: h + (texts.YOU if h == handle else "")  # noqa: E731
    up = _upvote_text(forum, handle, cfg)
    sys_parts = _system_parts(forum, handle, cfg, system_template)
    n_parts, notified = _notifications(forum, handle, round_, cfg, since, mark)
    b_parts, b_shown, titles = board_index(forum, handle, cfg, who, round_, newest=True)
    rec_parts, mem_replies, shown = [], [], set()
    if cfg.switches.memory == "on":
        rec_parts, mem_replies, shown = _record(forum, handle, round_, cfg, up, True, since, mark)
    rule = texts.NAV_RULE + (texts.NAV_BOARD_RULE.format(words=cfg.boards.description_words)) + texts.NAV_TAIL
    user_parts = render(nav_template, {"boards": b_parts, "notifications": n_parts, "record": rec_parts,
                                       "nav_rule": [(rule, E)]})
    if user_parts and user_parts[0][0].startswith("\n"):
        user_parts[0] = (user_parts[0][0][1:], user_parts[0][1])
    parts = sys_parts + [("\n\x01\n", E)] + user_parts
    d = {**texts.FIELD_DESC, **texts.FIELD_DESC_NAV}
    sch = {"type": "object", "properties": {k: {"type": "string", "description": d[k]} for k in ("go", "board", "body")},
           "required": ["go", "board", "body"], "additionalProperties": False}
    return Nav(handle=handle, round=round_, system=join(sys_parts), user=join(user_parts), parts=parts, schema=sch,
               boards_shown=b_shown, titles_shown=titles, notified=[c.id for c in notified],
               memory_replies=mem_replies, shown=shown | {c.id for c in notified} | {x.id for x in forum.items_by(handle)})


def validate_nav(nav: Nav, data, forum: Forum, cfg, handle: str, last_try: bool):
    """(choice, reason, flags): choice = {"go": board|"all"|"leave"} or {"go": "new_board", "name", "description"}."""
    flags = []
    if not isinstance(data, dict):
        return None, "json", flags
    raw = str(data.get("go", "")).strip()
    go = raw.lower().strip("[]").strip()
    if go in ("all", "leave"):
        return {"go": go}, None, flags
    if go in ("new_board", "new board"):
        name = board_name(data.get("board"))
        body = " ".join(str(data.get("body") or "").split())
        if name is None or not body:
            return None, "board", flags
        if name in forum.board_names():
            return None, "board_exists", flags
        if sum(b.author == handle for b in forum.boards.values()) >= cfg.boards.per_agent:
            return None, "board_limit", flags
        cap = int(cfg.boards.description_words * cfg.limits.overrun)
        if len(words(body)) > cap:
            if not last_try:
                return None, "long", flags
            body = " ".join(words(body)[:cap])
            flags.append("cut")
        return {"go": "new_board", "name": name, "description": body}, None, flags
    name = board_name(raw) or go
    if name in forum.board_names():
        return {"go": name}, None, flags
    return None, "go", flags


def forum_comment_pool(forum: Forum, handle: str, seeded_ids: set | None) -> list[Comment]:
    """What the forum-wide comment slot draws from, in id order: before the freeze every other member's
    comment; after it, the frozen founders' phase-1 comments (ids in `seeded_ids`) by other members."""
    if seeded_ids is None:
        cs = [c for c in forum.comments.values() if c.author != handle]
    else:
        cs = [forum.comments[i] for i in seeded_ids if i in forum.comments and forum.comments[i].author != handle]
    return sorted(cs, key=lambda c: _num(c.id))


def forum_comment_draw(forum: Forum, handle: str, round_: int, cfg, seeded_ids: set | None) -> tuple[list, int]:
    k = cfg.feed.random_comment
    if not k or cfg.switches.solo:
        return [], 0
    pool = forum_comment_pool(forum, handle, seeded_ids)
    k = min(k, len(pool))
    if not k:
        return [], len(pool)
    rng = rng_for(cfg.seed, "forum_comment", round_, forum.agents[handle].index)
    return [pool[i] for i in sorted(rng.choice(len(pool), size=k, replace=False).tolist())], len(pool)


def board_index(forum: Forum, handle: str, cfg, who, round_: int = 0, newest: bool = False):
    """The boards section of a prompt and the names listed (SPEC 2.5): most recently active first, or (v0.4)
    in a seeded random order per visit. `newest`: each line ends with its newest post's title (two-step
    visits), and the post ids of those titles are returned as a third value."""
    E = "engine"
    last = {b: 0 for b in forum.communities}
    last.update({b.name: b.round for b in forum.boards.values()})
    n_posts = {b: 0 for b in last}
    n_comments = {b: 0 for b in last}
    for p in forum.posts.values():
        n_posts[p.community] = n_posts.get(p.community, 0) + 1
        last[p.community] = max(last.get(p.community, 0), p.round)
    for c in forum.comments.values():
        b = forum.posts[c.post].community
        n_comments[b] = n_comments.get(b, 0) + 1
        last[b] = max(last.get(b, 0), c.round)
    order = sorted(forum.board_names(), key=lambda b: (-last.get(b, 0), forum.board_names().index(b)))
    if cfg.boards.order == "random":
        names = forum.board_names()
        idx = rng_for(cfg.seed, "board_order", round_, forum.agents[handle].index).permutation(len(names)).tolist()
        order = [names[i] for i in idx]
    latest = {}
    for p in forum.posts.values():
        if p.community not in latest or _num(p.id) > _num(latest[p.community].id):
            latest[p.community] = p
    titles = []
    desc = {c.name: c.description for c in cfg.communities}
    parts = [("\n" + texts.BOARDS_HEAD + "\n", E)]
    for name in order[:cfg.boards.shown]:
        b = forum.boards.get(name)
        by = texts.BOARD_BY.format(author=who(b.author)) if b else ""
        line = texts.BOARD_LINE.format(name=name, by=by, description="\x00",
                                       posts=texts.count(n_posts.get(name, 0), "post", "posts"),
                                       comments=texts.count(n_comments.get(name, 0), "comment", "comments"))
        if b:  # a member wrote the name and the description
            head, tail = line.split("\x00", 1)
            pre = head[:2]  # "- "
            parts += [(pre, E), (name, "agent"), (head[2 + len(name):], E), (b.description, "agent"), (tail, E)]
        else:
            parts.append((line.replace("\x00", desc.get(name, "")), E))
        if newest and name in latest:
            parts += [(texts.BOARD_NEWEST, E), (latest[name].title, "agent"), ('"', E)]
            titles.append(latest[name].id)
        parts.append(("\n", E))
    if len(order) > cfg.boards.shown:
        parts.append((texts.BOARDS_MORE.format(n=len(order) - cfg.boards.shown) + "\n", E))
    if newest:
        return parts, order[:cfg.boards.shown], titles
    return parts, order[:cfg.boards.shown]


def board_name(raw: str) -> str | None:
    """A member's board name as the engine stores it: lower case, words joined by _ (one to three words)."""
    s = re.sub(r"^(?:[a-z]/|#)", "", str(raw or "").strip().lower()).strip()
    words_ = [w for w in re.split(r"[\s_\-]+", s) if w]
    if not 1 <= len(words_) <= 3:
        return None
    name = "_".join(words_)
    return name if BOARD_NAME.fullmatch(name) else None


def _splice(line: str, agent_text: str) -> list:
    """An engine line with one agent-written field, marked by \\x00."""
    a, b = line.split("\x00", 1)
    out = [(a, "engine")] if a else []
    out.append((agent_text, "agent"))
    if b:
        out.append((b, "engine"))
    return out


def _strip_last_newline(parts: list) -> list:
    if parts and parts[-1] == ("\n", "engine"):
        return parts[:-1]
    return parts


def _where(forum, p, tagged: bool) -> str:
    """' in <board>'; a member-started board's name is marked with \\x00 so it is spliced in as agent text."""
    if not tagged:
        return ""
    return texts.COMMUNITY_TAG.format(community="\x00" if p.community in forum.boards else p.community)


def _board_splice(line: str, name: str) -> list:
    return _splice(line, name) if "\x00" in line else [(line, "engine")]


def _own_line(forum, it, round_, multi, up) -> list:
    ago = texts.ago(round_ - it.round)
    if isinstance(it, Post):
        line = texts.OWN_POST.format(id=it.id, where=_where(forum, it, multi), ago=ago, up=up(it.id, own=True),
                                     nc=texts.count(forum.comment_count(it.id), "comment", "comments"))
        return _board_splice(line, it.community)
    else:
        line = texts.OWN_COMMENT.format(id=it.id, target=it.parent, target_author=forum.author_of(it.parent), ago=ago,
                                        up=up(it.id, own=True), nr=texts.count(len(forum.replies(it.id)), "reply", "replies"))
    return [(line, "engine")]


# ---- validation (SPEC 3.5) ----------------------------------------------------
def validate(visit: Visit, data, forum: Forum, cfg, last_try: bool):
    """(action, reason, flags). `action` is None when the reply cannot be used;
    `reason` names the REASONS entry for the retry line."""
    lim, flags = cfg.limits, []
    if not isinstance(data, dict):
        return None, "json", flags
    kind = str(data.get("action", "")).strip().lower()
    boards_on = cfg.boards_on()
    in_board = visit.board is not None and visit.board != "all"  # two-step: posts go to the chosen board
    allowed = {"post", "comment", "none"} | ({"board"} if boards_on else set()) | \
        ({"update"} if cfg.switches.updates else set())
    if kind not in allowed:
        return None, "action", flags
    title = " ".join(str(data.get("title") or "").split())
    body = " ".join(str(data.get("body") or "").split()) if kind != "post" else str(data.get("body") or "").strip()
    out = {"kind": kind}
    if kind == "post":
        if not title or not body:
            return None, "post", flags
        community = forum.communities[0]
        if in_board:
            community = visit.board
        elif boards_on:
            community = board_name(data.get("board"))
            if community not in forum.board_names():
                if not last_try:
                    return None, "board_unknown", flags
                community = forum.communities[0]
                flags.append({"board_default": str(data.get("board") or "")})
        elif visit.multi:
            community = str(data.get("community") or "").strip().lower()
            if community not in forum.communities:
                return None, "community", flags
        t_cap, b_cap = int(lim.title_words * lim.overrun), int(lim.post_words * lim.overrun)
        if len(words(title)) > t_cap or len(words(body)) > b_cap:
            if not last_try:
                return None, "long", flags
            title, body = " ".join(words(title)[:t_cap]), " ".join(words(body)[:b_cap])
            flags.append("cut")
        out.update(community=community, title=title, body=body)
    elif kind == "comment":
        target = str(data.get("reply_to") or "").strip().strip("[]").strip()
        if not body:
            return None, "comment", flags
        if target not in visit.shown or forum.item(target) is None:
            return None, "reply_to", flags
        cap = int(lim.comment_words * lim.overrun)
        if len(words(body)) > cap:
            if not last_try:
                return None, "long", flags
            body = " ".join(words(body)[:cap])
            flags.append("cut")
        out.update(parent=target, body=body)
    elif kind == "update":
        target = str(data.get("reply_to") or "").strip().strip("[]").strip()
        p = forum.posts.get(target)
        if not body or p is None or p.author != visit.handle:
            return None, "update", flags
        cap = int(UPDATE_WORDS * lim.overrun)
        if len(words(body)) > cap:
            if not last_try:
                return None, "long", flags
            body = " ".join(words(body)[:cap])
            flags.append("cut")
        out.update(post=target, body=body)
    elif kind == "board":
        name = board_name(data.get("board"))
        if name is None or not body:
            return None, "board", flags
        if name in forum.board_names():
            return None, "board_exists", flags
        if sum(b.author == visit.handle for b in forum.boards.values()) >= cfg.boards.per_agent:
            return None, "board_limit", flags
        cap = int(cfg.boards.description_words * lim.overrun)
        if len(words(body)) > cap:
            if not last_try:
                return None, "long", flags
            body = " ".join(words(body)[:cap])
            flags.append("cut")
        out.update(name=name, description=body)
    votes, dropped = [], []
    raw_votes = data.get("upvote") or []
    if not isinstance(raw_votes, list):
        raw_votes = []
    for v in raw_votes:
        v = str(v).strip().strip("[]").strip()
        if v in visit.shown and v not in visit.own and not forum.has_voted(visit.handle, v) and v not in votes:
            votes.append(v)
        else:
            dropped.append(v)
    out["upvote"] = votes
    if dropped:
        flags.append({"dropped_upvotes": dropped})
    return out, None, flags


def retry_line(reason: str, cfg) -> str:
    lim = cfg.limits
    return texts.RETRY.format(reason=texts.REASONS[reason].format(title=lim.title_words, post=lim.post_words,
                                                                  comment=lim.comment_words,
                                                                  board=cfg.boards.description_words,
                                                                  update=UPDATE_WORDS))

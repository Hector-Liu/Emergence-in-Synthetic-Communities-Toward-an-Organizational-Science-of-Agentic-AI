"""SPEC section 8, tests 1-8 and 10."""
import asyncio
import re
import threading

import pytest
from conftest import cfg, run

from fakemolt import guard, texts
from fakemolt.config import RunConfig
from fakemolt.engine import Run, make_agents, templates
from fakemolt.forum import Agent, Forum, replay
from fakemolt.llm import MockModel, request_kwargs
from fakemolt.prompts import build_visit, pick_comments, select_feed, validate
from fakemolt.store import RunStore

RECORD = texts.RECORD_HEAD


def record_section(user: str) -> str:
    if RECORD not in user:
        return ""
    return user.split(RECORD, 1)[1].split("Choose your action")[0]


# 1 ------------------------------------------------------------------------------
def test_record_is_private_and_has_no_totals(base):
    st, m = run(cfg(), base)
    assert m["status"] == "done"
    forum = replay(["general"], st.read_jsonl("actions.jsonl"))
    for c in st.read_jsonl("calls.jsonl"):
        rec = record_section(c["user"])
        own = re.findall(r"^\[((?:p|c)_\d+)\] You ", rec, flags=re.M)
        assert all(forum.author_of(i) == c["handle"] for i in own)
        for other in forum.agents:
            if other != c["handle"]:
                assert f"Your handle is {other}" not in c["system"]
        assert "karma" not in c["user"].lower() and "total" not in c["user"].lower()


# 2 ------------------------------------------------------------------------------
def test_round_prompts_use_one_snapshot(base):
    st, _ = run(cfg(), base)
    actions = st.read_jsonl("actions.jsonl")
    for c in st.read_jsonl("calls.jsonl"):
        before = replay(["general"], actions, upto_round=c["round"] - 1)
        for kind, num in re.findall(r"\[(p|c)_(\d+)\]", c["user"]):
            limit = before.n_posts if kind == "p" else before.n_comments
            assert int(num) <= limit, f"round {c['round']} shows an item committed in its own round"


# 3 ------------------------------------------------------------------------------
def _forum_with_posts(n_posts=30, authors=("u_a", "u_b", "u_c")):
    f = Forum(communities=["general"])
    for i, h in enumerate(authors):
        f.add_agent(Agent(h, "mock", "general", 1, 0, i))
    for i in range(n_posts):
        f.add_post(authors[i % len(authors)], "general", 1 + i // 5, f"title {i}", f"body {i}")
    return f


def test_feed_slots(base):
    c = cfg()
    f = _forum_with_posts()
    sel, pool, seeded = select_feed(f, "u_a", 8, c)
    ids = [p for p, _ in sel]
    assert len(ids) == len(set(ids)) == c.feed.new + c.feed.hot + c.feed.random + c.feed.random_seeded
    # own posts can fill new and hot slots, never the random ones (and none at all when switched off)
    assert any(f.posts[p].author == "u_a" for p, s in sel if s in ("new", "hot"))
    assert all(f.posts[p].author != "u_a" for p, s in sel if s.startswith("random"))
    assert all(f.posts[p].author != "u_a" for p in pool)
    off = select_feed(f, "u_a", 8, cfg(feed={"hot_window": 10, "own_posts": False}))[0]
    assert all(f.posts[p].author != "u_a" for p, _ in off)
    assert sel == select_feed(f, "u_a", 8, c)[0]  # seeded, reproducible
    assert not set(pool) & {p for p, s in sel if s != "random"}
    # seeded slot draws only from the seeded pool once it exists
    seed_ids = {"p_2", "p_3"}
    sel2, _, seeded2 = select_feed(f, "u_a", 8, c, seed_ids)
    assert set(seeded2) <= seed_ids
    assert all(p in seed_ids for p, s in sel2 if s == "random_seeded")
    # short pool: empty slots stay empty
    small = _forum_with_posts(n_posts=3)
    assert len(select_feed(small, "u_a", 2, c)[0]) == 3
    assert len(select_feed(small, "u_a", 2, cfg(feed={"hot_window": 10, "own_posts": False}))[0]) == 2


def test_comment_slots_newest_top_random(base):
    c = cfg()
    f = _forum_with_posts(n_posts=1)
    for i in range(20):
        f.add_comment(("u_b", "u_c")[i % 2], "p_1", 2 + i // 4, f"comment {i}")
    for cid, n in (("c_2", 3), ("c_5", 2), ("c_9", 1)):
        for v in ("u_a", "u_b", "u_c")[:n]:
            f.add_vote(v, cid)
    picks = pick_comments(f, "p_1", c.feed, c.seed, 9, 0)
    ids = {k: [x.id for x in v] for k, v in picks.items()}
    assert ids["new"] == ["c_18", "c_19", "c_20"]
    assert ids["top"] == ["c_2", "c_5", "c_9"]
    assert len(ids["random"]) == 3 and not set(ids["random"]) & set(ids["new"] + ids["top"])
    assert picks == pick_comments(f, "p_1", c.feed, c.seed, 9, 0)  # seeded
    draws = {tuple(x.id for x in pick_comments(f, "p_1", c.feed, c.seed, r, 0)["random"]) for r in range(30)}
    assert len(draws) > 20
    # a visit logs which slot each shown comment came from, and only the slot ids are shown
    v = build_visit(f, "u_a", 9, c, *templates(c))
    assert v.comment_slots["p_1"] == {k: sorted(x, key=lambda i: int(i[2:])) for k, x in ids.items()}
    assert len(v.shown_comments["p_1"]) == 9
    assert "u_a (you)" in v.user  # own post in the feed, marked


# 4 ------------------------------------------------------------------------------
def test_phases_and_balanced_homes(base):
    c = cfg(communities=[{"name": "general", "description": "anything"},
                         {"name": "introductions", "description": "new members say hello"}],
            feed={"other_hot": 1})
    st, m = run(c, base)
    agents = [a["agent"] for a in st.read_jsonl("actions.jsonl") if a["kind"] == "agent"]
    assert [a["joined_round"] for a in agents] == [1] * 4 + [5] * 6
    for phase in (0, 1):
        homes = [a["home"] for a in agents if a["phase"] == phase]
        assert abs(homes.count("general") - homes.count("introductions")) <= 1
    first = [c_ for c_ in st.read_jsonl("calls.jsonl") if c_["round"] == 5 and c_["attempt"] == 0
             and c_["handle"] in {a["handle"] for a in agents if a["phase"] == 1}]
    assert first and all(texts.NONE_YET in record_section(x["user"]) for x in first)
    assert all("Your home community is" in x["system"] for x in first)


# 5 ------------------------------------------------------------------------------
def test_validation_cases():
    c = cfg()
    f = _forum_with_posts(6)
    s, v_t = templates(c)
    v = build_visit(f, "u_a", 3, c, s, v_t)
    shown_post = sorted(p for p in v.shown if p.startswith("p_") and f.posts[p].author != "u_a")[0]
    ok = lambda d, last=False: validate(v, d, f, c, last)  # noqa: E731
    assert ok("not a dict")[1] == "json"
    assert ok({"action": "dance"})[1] == "action"
    assert ok({"action": "post", "title": "", "body": "x"})[1] == "post"
    assert ok({"action": "comment", "reply_to": "p_999", "body": "hi"})[1] == "reply_to"
    assert ok({"action": "comment", "reply_to": shown_post, "body": ""})[1] == "comment"
    long = " ".join(["w"] * 200)
    assert ok({"action": "comment", "reply_to": shown_post, "body": long})[1] == "long"
    act, _, flags = ok({"action": "comment", "reply_to": shown_post, "body": long}, last=True)
    assert len(act["body"].split()) == int(80 * 1.5) and "cut" in flags
    own = next(p.id for p in f.posts.values() if p.author == "u_a")
    act, _, _ = ok({"action": "none", "upvote": [shown_post, shown_post, own, "p_999"]})
    assert act["upvote"] == [shown_post]


def test_void_visits_write_nothing(base):
    class Broken(MockModel):
        async def complete(self, *a, **kw):
            r = await super().complete(*a, **kw)
            r.data, r.raw = {"action": "dance"}, "{}"
            return r
    st, m = run(cfg(), base, mock=Broken())
    assert m["status"] == "stopped"  # more than 10% void
    assert not [a for a in st.read_jsonl("actions.jsonl") if a["kind"] in ("post", "comment", "vote")]
    assert all(c["attempt"] in (0, 1) for c in st.read_jsonl("calls.jsonl"))


# 6 ------------------------------------------------------------------------------
def test_guard_blocks_before_any_call(base):
    c = cfg(prompts={"system": "You are part of an experiment. Your handle is {handle}.", "visit": "default"})
    st, m = run(c, base)
    assert m["status"] == "guard"
    assert not st.read_jsonl("calls.jsonl")


@pytest.mark.parametrize("tell_ai", [True, False])
def test_default_texts_pass_guard(tell_ai):
    c = cfg(switches={"tell_ai": tell_ai})
    s, v = templates(c)
    assert guard.preflight(c, s, v) == []


def test_no_identity_words_when_not_told(base):
    st, _ = run(cfg(switches={"tell_ai": False}), base)
    for c in st.read_jsonl("calls.jsonl")[:5]:
        assert " AI " not in c["system"] and "agent" not in c["system"].lower()


# 7 ------------------------------------------------------------------------------
def test_switches(base):
    st, _ = run(cfg(switches={"memory": "off", "goal": "participate"}), base, name="m")
    calls = st.read_jsonl("calls.jsonl")
    assert all(RECORD not in c["user"] and "your own record" not in c["system"] for c in calls)
    assert all(c["system"].count("Take part in the forum as you see fit.") == 1 for c in calls)
    st2, _ = run(cfg(switches={"solo": True}), base, name="s")
    for c in st2.read_jsonl("calls.jsonl"):
        feed = c["user"].split("Posts in your feed:")[1].split(RECORD)[0]
        assert "[p_" not in feed and "replied to your" not in c["user"]


# 8 ------------------------------------------------------------------------------
def test_resume_equals_uninterrupted(base):
    c = cfg()
    full, _ = run(c, base, name="full")
    cancel = threading.Event()
    st = RunStore.create("cut", base)

    def progress(ev):
        if ev["type"] == "round" and ev["summary"]["round"] == 5:
            cancel.set()

    m = asyncio.run(Run.new(c, st, model_factory=lambda mid: MockModel(), progress=progress, cancel=cancel).run())
    assert m["status"] == "cancelled" and m["rounds_done"] == 5
    m2 = asyncio.run(Run.resume(st, model_factory=lambda mid: MockModel()).run())
    assert m2["status"] == "done"
    strip = lambda rows: [{k: v for k, v in r.items()} for r in rows]  # noqa: E731
    assert strip(st.read_jsonl("actions.jsonl")) == strip(full.read_jsonl("actions.jsonl"))
    assert st.read_json("expressions.json")["expressions"] == full.read_json("expressions.json")["expressions"]


def test_calls_logged_before_use_and_reused_on_resume(base):
    c = cfg()
    st = RunStore.create("x", base)
    cancel = threading.Event()

    class Counting(MockModel):
        n = 0

        async def complete(self, *a, **kw):
            Counting.n += 1
            if Counting.n == 7:
                cancel.set()  # cancel inside round 2: some calls of the round are already logged
            return await super().complete(*a, **kw)

    asyncio.run(Run.new(c, st, model_factory=lambda mid: Counting(), cancel=cancel).run())
    logged = len(st.read_jsonl("calls.jsonl"))
    before = Counting.n
    asyncio.run(Run.resume(st, model_factory=lambda mid: Counting()).run())
    assert Counting.n - before == len(st.read_jsonl("calls.jsonl")) - logged  # nothing re-sent


# 10 -----------------------------------------------------------------------------
def test_request_shape():
    kw = request_kwargs("claude-haiku-5-5", "sys", "user", {"type": "object"}, "high", 16000)
    assert set(kw) == {"model", "max_tokens", "system", "messages", "thinking", "output_config"}
    assert kw["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kw["output_config"]["effort"] == "high"
    assert not {"temperature", "top_p", "top_k"} & set(kw)


def test_handles_are_unique_and_clean():
    c = RunConfig.model_validate({"phases": [{"name": "a", "add": [{"n": 300, "model": "mock"}], "rounds": 1}]})
    agents = make_agents(c, 0, 1, 0, set())
    hs = [a.handle for a in agents]
    assert len(set(hs)) == 300 and all(re.fullmatch(r"u_[a-z0-9]{6}", h) for h in hs)


# review fixes (2026-10-13) --------------------------------------------------------
def test_notifications_off_removes_section_and_clause(base):
    st, _ = run(cfg(feed={"notifications": 0}), base, name="nn")
    for c in st.read_jsonl("calls.jsonl"):
        assert texts.NOTIFY_HEAD not in c["user"] and "more" not in c["user"].split("Posts in your feed:")[0]
        assert "new replies to you" not in c["system"]


def test_limits_stated_and_brackets_accepted():
    c = cfg()
    f = _forum_with_posts(6)
    s, v_t = templates(c)
    v = build_visit(f, "u_a", 3, c, s, v_t)
    assert "at most 15 words" in v.user and "at most 150 words" in v.user and "at most 80 words" in v.user
    other = sorted(p for p in v.shown if p.startswith("p_") and f.posts[p].author != "u_a")[0]
    act, reason, _ = validate(v, {"action": "comment", "reply_to": f"[{other}]", "body": "ok", "upvote": [f"[{other}]"]}, f, c, False)
    assert reason is None and act["parent"] == other and act["upvote"] == [other]
    assert all("description" in p for p in v.schema["properties"].values())


def test_show_upvotes_switch():
    f = _forum_with_posts(6)
    f.add_vote("u_b", "p_1")  # u_a's own post
    f.add_vote("u_a", "p_2")  # u_a upvoted u_b's post
    for show, own_count, other_count in (("all", True, True), ("others", False, True), ("none", False, False)):
        c = cfg(switches={"show_upvotes": show})
        s, v_t = templates(c)
        v = build_visit(f, "u_a", 3, c, s, v_t)
        rec = record_section(v.user)
        assert ("1 upvote" in rec) == own_count, show
        feed = v.user.split("Posts in your feed:")[1].split(RECORD)[0]
        assert ("upvote" in feed.replace("you upvoted this", "")) == other_count, show
        if "[p_2]" in feed:
            assert "you upvoted this" in feed


# random activation ---------------------------------------------------------------
def test_activation_partial_seeded_and_resumable(base):
    c = cfg(activation=0.4)
    a, _ = run(c, base, name="a1")
    b, _ = run(c, base, name="a2")
    va, vb = a.read_jsonl("visits.jsonl"), b.read_jsonl("visits.jsonl")
    assert [(v["round"], v["handle"]) for v in va] == [(v["round"], v["handle"]) for v in vb]
    full = sum(4 if r <= 4 else 10 for r in range(1, 9))
    assert 0.15 * full < len(va) < 0.7 * full
    # resume equals uninterrupted
    cancel = threading.Event()
    st = RunStore.create("a3", base)
    asyncio.run(Run.new(c, st, model_factory=lambda mid: MockModel(),
                        progress=lambda ev: ev["type"] == "round" and ev["summary"]["round"] == 4 and cancel.set(),
                        cancel=cancel).run())
    asyncio.run(Run.resume(st, model_factory=lambda mid: MockModel()).run())
    assert st.read_jsonl("actions.jsonl") == a.read_jsonl("actions.jsonl")


def test_notifications_cover_time_since_last_visit():
    c = cfg()
    f = _forum_with_posts(3)
    own = next(p.id for p in f.posts.values() if p.author == "u_a")
    f.add_comment("u_b", own, 4, "first reply")
    f.add_comment("u_c", own, 6, "second reply")
    s, v_t = templates(c)
    v = build_visit(f, "u_a", 7, c, s, v_t, since=3)
    notes = v.user.split(texts.NOTIFY_HEAD)[1].split(texts.RECORD_HEAD)[0]  # after the feed and the boards
    assert "first reply" in notes and "second reply" in notes
    v2 = build_visit(f, "u_a", 7, c, s, v_t, since=5)
    notes2 = v2.user.split(texts.NOTIFY_HEAD)[1].split(texts.RECORD_HEAD)[0]
    assert "second reply" in notes2 and "first reply" not in notes2
    v3 = build_visit(f, "u_a", 7, c, s, v_t, since=6)  # nothing new: no replies section at all
    assert texts.NOTIFY_HEAD not in v3.user and texts.NONE not in v3.user.split(texts.RECORD_HEAD)[0]


def test_boards(base):
    from fakemolt.prompts import board_name
    c = cfg()
    assert board_name("Late Night Ideas") == "late_night_ideas" and board_name("m/tools") == "tools"
    assert board_name("one two three four") is None and board_name("") is None and board_name("7up") is None
    f = _forum_with_posts(n_posts=3)
    s, v_t = templates(c)
    v = build_visit(f, "u_a", 3, c, s, v_t)
    assert "Boards:" in v.user and "- general: anything" in v.user and "board or none" in v.user
    assert "board" in v.schema["properties"] and "or start a board" in v.system
    ok, why, _ = validate(v, {"action": "board", "board": "Tool Talk", "body": "about tools", "upvote": []}, f, c, False)
    assert ok == {"kind": "board", "name": "tool_talk", "description": "about tools", "upvote": []}
    assert validate(v, {"action": "board", "board": "general", "body": "x", "upvote": []}, f, c, False)[1] == "board_exists"
    assert validate(v, {"action": "post", "board": "nowhere", "title": "t", "body": "b", "upvote": []}, f, c, False)[1] == "board_unknown"
    last = validate(v, {"action": "post", "board": "nowhere", "title": "t", "body": "b", "upvote": []}, f, c, True)
    assert last[0]["community"] == "general" and {"board_default": "nowhere"} in last[2]
    f.add_board("u_a", "tool_talk", "about tools", 3)
    v2 = build_visit(f, "u_a", 4, c, s, v_t)
    assert "- tool_talk (started by u_a (you)): about tools" in v2.user and v2.boards_shown[0] == "tool_talk"
    assert validate(v2, {"action": "board", "board": "more", "body": "x", "upvote": []}, f, c, False)[1] == "board_limit"
    assert validate(v2, {"action": "post", "board": "tool_talk", "title": "t", "body": "b", "upvote": []}, f, c, False)[0]["community"] == "tool_talk"
    # a member's board name is agent text wherever it appears, so the guard never reads it as engine text
    f.add_board("u_b", "forum_norms", "how the forum works", 4)
    f.add_post("u_b", "forum_norms", 4, "a title", "a body")
    v3 = build_visit(f, "u_b", 5, c, s, v_t)
    assert "in forum_norms by u_b" in v3.user and "norms" in v3.user
    assert not guard.check_parts(v3.parts, texts.denylist(True))
    # a run with boards: they are logged and replayed, and posts name a board that exists
    st, m = run(cfg(phases=[{"name": "f", "add": [{"n": 10, "model": "mock"}], "rounds": 30}]), base, name="boards")
    acts = st.read_jsonl("actions.jsonl")
    fr = replay(["general"], acts)
    assert fr.boards and all(p.community in fr.board_names() for p in fr.posts.values())
    assert all(sum(b.author == h for b in fr.boards.values()) <= 1 for h in fr.agents)
    # with several configured communities the boards switch is off
    multi = cfg(communities=[{"name": "general", "description": "anything"}, {"name": "intro", "description": "hello"}])
    assert not multi.boards_on()


def test_opening_visitors_fixed(base):
    import json as _json
    for seed in (1, 2, 3):
        c = cfg(seed=seed, activation=0.25, opening=4,
                phases=[{"name": "f", "add": [{"n": 10, "model": "mock"}], "rounds": 3}])
        st, m = run(c, base, name=f"open{seed}")
        r1 = [v for v in st.read_jsonl("visits.jsonl") if v["round"] == 1]
        assert len(r1) == 4
        assert c.total_visits() == round(4 + 10 * 2 * 0.25)
    off = cfg(activation=0.25, opening=0)
    assert off.opening_visitors() is None and cfg(activation=1.0).opening_visitors() is None


def test_identity_not_told_by_default():
    from fakemolt.config import RunConfig as RC
    assert RC().switches.tell_ai is False
    c = RC.model_validate({"phases": [{"name": "f", "add": [{"n": 3, "model": "mock"}], "rounds": 2}]})
    f = _forum_with_posts(n_posts=3)
    v = build_visit(f, "u_a", 3, c, *templates(c))
    assert " AI" not in v.system and not guard.check_parts(v.parts, texts.denylist(False))


def test_forum_comment_slot():
    from fakemolt.prompts import forum_comment_pool
    c = cfg()
    f = _forum_with_posts(n_posts=3)
    for i in range(6):
        f.add_comment(("u_a", "u_b", "u_c")[i % 3], "p_1", 2, f"note {i}")
    s, v_t = templates(c)
    v = build_visit(f, "u_a", 3, c, s, v_t)
    assert texts.FORUM_COMMENTS_HEAD in v.user and len(v.forum_comments) == 1
    assert f.comments[v.forum_comments[0]].author != "u_a" and v.forum_comment_pool == 4
    assert v.forum_comments[0] in v.shown
    # after the freeze only the seeded comments (by others) are drawn
    seeded = {"c_2", "c_3"}
    v2 = build_visit(f, "u_a", 3, c, s, v_t, seeded_ids=seeded | {"p_1"})
    assert v2.forum_comments[0] in seeded and v2.forum_comment_pool == 2
    assert [x.id for x in forum_comment_pool(f, "u_b", seeded)] == ["c_3"]
    off = build_visit(f, "u_a", 3, cfg(feed={"hot_window": 10, "random_comment": 0}), s, v_t)
    assert texts.FORUM_COMMENTS_HEAD not in off.user and off.forum_comments == []

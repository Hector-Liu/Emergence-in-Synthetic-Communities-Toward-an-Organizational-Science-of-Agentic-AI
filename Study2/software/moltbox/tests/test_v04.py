"""v0.4: heartbeat schedule, visits in order within a round, two-step visits, updates, own-post memory."""
import asyncio
import re
from collections import defaultdict

from conftest import cfg, run

from fakemolt import guard, texts
from fakemolt.engine import Run, nav_template, templates
from fakemolt.forum import Agent, Forum, replay
from fakemolt.llm import MockModel
from fakemolt.prompts import build_nav, build_visit, validate, validate_nav
from fakemolt.store import RunStore

PH = [{"name": "f", "add": [{"n": 8, "model": "mock"}], "rounds": 12},
      {"name": "n", "add": [{"n": 6, "model": "mock"}], "rounds": 8}]


def cfg4(**kw):
    base = {"schedule": {"mode": "heartbeat", "period": 2, "jitter": 1}, "order": {"mode": "sequential", "overlap": 1},
            "visit": {"two_step": True}, "phases": PH, "opening": 3}
    base.update(kw)
    return cfg(**base)


def _forum():
    f = Forum(communities=["general"])
    for i, h in enumerate(("u_a", "u_b", "u_c")):
        f.add_agent(Agent(h, "mock", "general", 1, 0, i))
    f.add_board("u_b", "puzzles", "number puzzles", 1)
    f.add_post("u_a", "general", 1, "hello all", "first post")
    f.add_post("u_b", "puzzles", 1, "a puzzle", "what is two plus two")
    f.add_comment("u_c", "p_1", 1, "welcome here")
    return f


def test_heartbeat_schedule(base):
    c = cfg4()
    st, m = run(c, base, name="hb")
    vis = st.read_jsonl("visits.jsonl")
    assert m["status"] == "done"
    assert len([v for v in vis if v["round"] == 1]) == 3  # the opening
    rounds = defaultdict(list)
    for v in vis:
        rounds[v["handle"]].append(v["round"])
    gaps = [b - a for rs in rounds.values() for a, b in zip(sorted(rs), sorted(rs)[1:])]
    assert gaps and min(gaps) >= 1 and max(gaps) <= 3  # T = 2, jitter 1
    assert abs(len(vis) - c.total_visits()) <= 0.15 * c.total_visits()


def test_sequential_visits_see_earlier_ones(base):
    st, _ = run(cfg4(), base, name="seq")
    acts = st.read_jsonl("actions.jsonl")
    vis = st.read_jsonl("visits.jsonl")
    calls = st.read_jsonl("calls.jsonl")
    by_round = defaultdict(list)
    for v in vis:
        by_round[v["round"]].append(v)
    checked = 0
    for r, vs in by_round.items():
        assert [v["order"] for v in vs] == list(range(len(vs)))  # logged in visit order
        assert all(a["seen_upto"] <= b["seen_upto"] for a, b in zip(vs, vs[1:]))
        for v in vs[1:]:
            prev_items = [a["id"] for a in acts[:v["seen_upto"]] if a.get("round") == r and a["kind"] in ("post", "comment")]
            if prev_items:
                step2 = [c for c in calls if c["round"] == r and c["handle"] == v["handle"] and c["step"] == 2 and c["attempt"] == 0]
                later = [a["id"] for a in acts[v["seen_upto"]:] if a.get("round") == r and a["kind"] in ("post", "comment")]
                ids = set(re.findall(r"\[((?:p|c)_\d+)\]", " ".join(c["user"] for c in step2)))
                assert not ids & set(later)  # nothing written after this visit began
                checked += 1
    assert checked > 0


def test_overlap_window_and_rerun_identical(base):
    c = cfg4(order={"mode": "sequential", "overlap": 3})
    st1, _ = run(c, base, name="w3a")
    st2, _ = run(c, base, name="w3b")
    u1 = [(x["round"], x["handle"], x["step"], x["user"]) for x in st1.read_jsonl("calls.jsonl")]
    u2 = [(x["round"], x["handle"], x["step"], x["user"]) for x in st2.read_jsonl("calls.jsonl")]
    assert sorted(u1) == sorted(u2)  # the window makes prompts depend on order only, not timing
    vis = st1.read_jsonl("visits.jsonl")
    by_round = defaultdict(list)
    for v in vis:
        by_round[v["round"]].append(v)
    for vs in by_round.values():
        for k, v in enumerate(vs[3:], start=3):  # visit k saw every action of visits up to k - 3
            assert v["seen_upto"] >= vs[k - 3]["seen_upto"]


def test_resume_equals_uninterrupted_v04(base):
    c = cfg4()
    whole, _ = run(c, base, name="whole")
    st = RunStore.create("cut", base)
    model = MockModel()
    r = Run.new(c, st, model_factory=lambda mid: model)

    async def stop_after(n):
        orig = r.play_round

        async def limited(t):
            if t > n:
                r.cancel.set()
                from fakemolt.engine import Cancelled
                raise Cancelled()
            await orig(t)
        r.play_round = limited
        return await r.run()
    asyncio.run(stop_after(7))
    m = asyncio.run(Run.resume(st, model_factory=lambda mid: model).run())
    assert m["status"] == "done"
    strip = lambda rows: [{k: v for k, v in x.items() if k != "time"} for x in rows]  # noqa: E731
    assert strip(st.read_jsonl("actions.jsonl")) == strip(whole.read_jsonl("actions.jsonl"))


def test_two_step_nav_and_board_feed():
    c = cfg4()
    f = _forum()
    s, v_t = templates(c)
    nav = build_nav(f, "u_c", 2, c, s, nav_template(c), mark=0)
    assert "Choose where to go" in nav.user and "- puzzles (started by u_b): number puzzles" in nav.user
    assert 'newest: "a puzzle"' in nav.user and set(nav.titles_shown) == {"p_1", "p_2"}
    assert "first the list of boards" in nav.system and texts.BOARDS_NOTE.strip() in nav.system
    assert not guard.check_parts(nav.parts, texts.denylist(c.switches.tell_ai))
    ok = lambda d: validate_nav(nav, d, f, c, "u_c", False)  # noqa: E731
    assert ok({"go": "puzzles", "board": "", "body": ""})[0] == {"go": "puzzles"}
    assert ok({"go": "All", "board": "", "body": ""})[0] == {"go": "all"}
    assert ok({"go": "leave", "board": "", "body": ""})[0] == {"go": "leave"}
    assert ok({"go": "nowhere", "board": "", "body": ""})[1] == "go"
    nb = ok({"go": "new_board", "board": "Book Club", "body": "one book a week"})[0]
    assert nb == {"go": "new_board", "name": "book_club", "description": "one book a week"}
    v = build_visit(f, "u_c", 2, c, s, v_t, mark=0, board="puzzles")
    assert "You opened the board puzzles." in v.user and [x["post"] for x in v.slots] == ["p_2"]
    assert "Boards:" in v.user and "board" in v.schema["properties"]  # v0.4.2: the board list shows in step 2 too
    assert v.schema["properties"]["board"]["description"] == texts.FIELD_DESC_BOARD_ONLY and "post, comment, board" in v.user
    post = validate(v, {"action": "post", "title": "t", "body": "b", "reply_to": "", "board": "", "upvote": []}, f, c, False)[0]
    assert post["community"] == "puzzles"
    nb = validate(v, {"action": "board", "board": "Book Club", "title": "", "body": "one book a week", "reply_to": "", "upvote": []}, f, c, False)[0]
    assert nb["kind"] == "board" and nb["name"] == "book_club"
    va = build_visit(f, "u_c", 2, c, s, v_t, mark=0, board="all")
    assert {x["post"] for x in va.slots} == {"p_1", "p_2"} and "board" in va.schema["properties"]


def test_notifications_include_same_round_replies():
    c = cfg4()
    f = _forum()
    s, v_t = templates(c)
    # u_a's previous visit began when 1 comment existed; a reply written later that round is still new
    f.add_comment("u_b", "p_1", 1, "a later reply in the same round")
    v = build_visit(f, "u_a", 2, c, s, v_t, mark=1, board="all")
    notes = v.user.split(texts.NOTIFY_HEAD)[1].split(texts.RECORD_HEAD)[0]
    assert "a later reply in the same round" in notes and "welcome here" not in notes


def test_updates_and_own_posts_record():
    c = cfg4()
    f = _forum()
    s, v_t = templates(c)
    v = build_visit(f, "u_a", 2, c, s, v_t, mark=0, board="all")
    assert "post, comment, board, update or none" in v.user
    assert texts.RECORD_POSTS_HEAD in v.user and "(1 new since your last visit)" in v.user
    good = validate(v, {"action": "update", "reply_to": "p_1", "body": "settled: thanks all", "title": "", "upvote": []}, f, c, False)
    assert good[0] == {"kind": "update", "post": "p_1", "body": "settled: thanks all", "upvote": []}
    assert validate(v, {"action": "update", "reply_to": "p_2", "body": "x", "title": "", "upvote": []}, f, c, False)[1] == "update"
    f.add_update("u_a", "p_1", 2, "settled: thanks all")
    v2 = build_visit(f, "u_b", 3, c, s, v_t, mark=0, board="general")
    assert "Update (1 hour ago): settled: thanks all" in v2.user
    fr = replay(["general"], [{"kind": "agent", "round": 1, "agent": {"handle": "u_a", "model": "m", "home": "general",
                                                                      "joined_round": 1, "phase": 0, "index": 0}},
                              {"kind": "post", "round": 1, "id": "p_1", "author": "u_a", "community": "general",
                               "title": "t", "body": "b"},
                              {"kind": "update", "round": 2, "id": "up_1", "author": "u_a", "post": "p_1", "body": "u"}])
    assert fr.posts["p_1"].updates[0].body == "u"


def test_v04_run_logs_and_measures(base):
    from fakemolt import measures
    st, m = run(cfg4(), base, name="v4m", mock=MockModel(adopt=0.05, per_expression=True))
    vis = st.read_jsonl("visits.jsonl")
    assert {"order", "seen_upto", "seen_comments", "chose"} <= set(vis[0])
    assert any(v["chose"] == "leave" for v in vis) and any(v.get("nav") for v in vis)
    acts = st.read_jsonl("actions.jsonl")
    fr = replay(["general"], acts)
    for v in vis:  # a post written after choosing a board lands in that board
        if v["action"] == "post" and v["chose"] not in ("all", None):
            assert fr.posts[v["item"]].community == v["chose"]
    rd = measures.RunData(st)
    nav = measures.navigation(rd)
    assert nav["visits"] == len(vis) and 0 <= nav["share_leave"] <= 1
    pr = measures.primary(rd, redraws=200)
    assert "results" in pr and pr["forum_comment_pool"]["visits_not_matching_log"] == 0


def test_reader_shows_what_a_sequential_visit_saw(base):
    from fakemolt.reader import Reader
    st, _ = run(cfg4(), base, name="rd")
    r = Reader(st)
    vis = st.read_jsonl("visits.jsonl")
    for v in vis:  # every visit renders, including ones that saw items written earlier in their round
        view = r.agent_view(v["handle"], v["round"])
        assert view["chose"] == v["chose"]
        assert {x["post"]["id"] for x in view["feed"]} == {s["post"] for s in v["slots"]}


def test_opening_all_founders_together(base):
    c = cfg4(opening=-1)
    st, _ = run(c, base, name="open")
    r1 = [v for v in st.read_jsonl("visits.jsonl") if v["round"] == 1]
    assert len(r1) == 8 and len({v["seen_upto"] for v in r1}) == 1  # every founder, one empty snapshot
    r2 = [v for v in st.read_jsonl("visits.jsonl") if v["round"] == 2]
    assert len({v["seen_upto"] for v in r2}) == len(r2)  # turns from round 2 on


def test_post_hint_switch():
    f = _forum()
    for on in (False, True):
        c = cfg4(switches={"post_hint": on})
        s, v_t = templates(c)
        v = build_visit(f, "u_c", 2, c, s, v_t, mark=0, board="general")
        assert (texts.POST_HINT.strip() in v.user) == on
        assert not guard.check_parts(v.parts, texts.denylist(c.switches.tell_ai))

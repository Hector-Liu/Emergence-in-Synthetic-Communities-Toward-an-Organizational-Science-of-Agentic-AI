"""The Forum pages' data: profile, an agent's view of one visit, activity stream, exports."""
import csv
import io

from conftest import cfg, run

from fakemolt.reader import Reader


def test_reader_views_match_the_logs(base):
    st, _ = run(cfg(activation=0.6), base, name="r")
    r = Reader(st)
    visits = st.read_jsonl("visits.jsonl")
    v = next(x for x in visits if x["slots"])
    view = r.agent_view(v["handle"], v["round"])
    assert [x["post"]["id"] for x in view["feed"]] == [s["post"] for s in v["slots"]]
    assert all(x["post"]["round"] < v["round"] for x in view["feed"])  # only what existed before the visit
    assert view["did"]["wrote"] is None or view["did"]["wrote"]["id"] == v["item"]
    prof = r.profile(v["handle"])
    assert prof["stats"]["visits"] == sum(x["handle"] == v["handle"] for x in visits)
    acts = r.activity()
    assert sum(a["kind"] == "post" for a in acts) == len(r.final.posts)
    rows = list(csv.reader(io.StringIO(r.csv().lstrip("﻿"))))
    assert len(rows) == 1 + len(r.final.posts) + len(r.final.comments)
    md = r.markdown()
    assert all(f"## {p}" in md for p in r.final.posts)

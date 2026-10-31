"""Export one run to a plain folder for reading and for analysis in Excel, R or Python.

    venv/bin/python scripts/export_run.py <run_id> [out_dir]      (default out_dir: exports/<run_id>)

The folder holds the offline forum page, the whole forum as text and as a table, one row per visit,
one row per member, the model's thinking summaries, the computed results, and a copy of every raw
log. Nothing in runs/ is changed.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fakemolt import archive, measures  # noqa: E402
from fakemolt.reader import Reader  # noqa: E402
from fakemolt.store import ROOT, find_run  # noqa: E402

BOM = "﻿"  # so Excel opens UTF-8 correctly


def table(path: Path, header: list[str], rows) -> int:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    n = 0
    for r in rows:
        w.writerow(r)
        n += 1
    path.write_text(BOM + buf.getvalue(), encoding="utf-8")
    return n


def export(run_id: str, out: Path) -> Path:
    st = find_run(run_id)
    if st is None:
        raise SystemExit(f"no run {run_id}")
    out.mkdir(parents=True, exist_ok=True)
    rd = Reader(st)
    f = rd.final
    cohort = rd.cohort
    names = [p.name for p in rd.cfg.phases] if hasattr(rd, "cfg") else []

    def phase(h):  # the phase the member joined in, by name (founders, newcomers, ...)
        i = f.agents[h].phase
        return names[i] if i < len(names) else i

    (out / "forum.html").write_text(archive.static_html(st), encoding="utf-8")
    (out / "forum.md").write_text(rd.markdown(), encoding="utf-8")
    (out / "items.csv").write_text(rd.csv(), encoding="utf-8")

    vis = st.read_jsonl("visits.jsonl")
    n_vis = table(out / "visits.csv",
                  ["round", "order", "handle", "cohort", "phase", "status", "chose", "action", "item", "upvotes",
                   "posts_shown", "comments_shown", "notified", "seen_upto", "flags"],
                  ([v["round"], v.get("order"), v["handle"], cohort.get(v["handle"]), phase(v["handle"]), v.get("status"), v.get("chose"),
                    v.get("action"), v.get("item") or "", " ".join(v.get("upvotes") or []) if isinstance(v.get("upvotes"), list) else v.get("upvotes"),
                    " ".join(s["post"] for s in v.get("slots") or []),
                    sum(len(x) for x in (v.get("shown_comments") or {}).values()),
                    " ".join(v.get("notified") or []), v.get("seen_upto"), " ".join(map(str, v.get("flags") or []))]
                   for v in vis))

    acts = {h: [x for x in vis if x["handle"] == h] for h in f.agents}
    table(out / "members.csv",
          ["handle", "cohort", "phase", "model", "joined_round", "visits", "posts", "comments", "updates", "did_nothing", "upvotes_received"],
          ([h, cohort.get(h), phase(h), a.model, a.joined_round, len(acts[h]),
            sum(x["action"] == "post" for x in acts[h]), sum(x["action"] == "comment" for x in acts[h]),
            sum(x["action"] == "update" for x in acts[h]), sum(x["action"] == "none" for x in acts[h]),
            sum(f.upvotes(i.id) for i in f.items_by(h))]
           for h, a in f.agents.items()))

    def thinking():
        with open(st.file("calls.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                c = json.loads(line)
                r = c.get("result") or {}
                summ = " ".join(r.get("thinking_summary") or [])
                yield [c["round"], c["handle"], cohort.get(c["handle"]), phase(c["handle"]), c.get("step"), c.get("attempt"),
                       summ.strip(), (r.get("raw") or "").strip()]
    n_think = table(out / "thinking.csv", ["round", "handle", "cohort", "phase", "step", "attempt", "thinking_summary", "answer"], thinking())

    res = out / "results"
    res.mkdir(exist_ok=True)
    data = measures.cached(st)
    (res / "measures.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (res / "summary.json").write_text(json.dumps(measures.summary(measures.RunData(st)), ensure_ascii=False, indent=1, default=str),
                                      encoding="utf-8")

    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    for name in archive.RUN_FILES:
        if st.file(name).exists():
            shutil.copy2(st.file(name), raw / name)

    m = st.read_json("manifest.json", {})
    (out / "README.md").write_text(f"""# Run {run_id}

{len(f.agents)} members · {len(f.posts)} posts · {len(f.comments)} comments · {n_vis} visits · {m.get('rounds_done')} rounds ·
models {', '.join(m.get('models', []))} · cost ${m.get('cost', 0):.2f} · status {m.get('status')}

| File | What it is |
|---|---|
| forum.html | The whole forum as one page; opens in any browser without the server |
| forum.md | The same forum as plain text |
| items.csv | One row per post and comment: round, author, cohort, parent, text, upvotes, replies |
| visits.csv | One row per visit: what the member chose, did, wrote, and what it was shown |
| members.csv | One row per member: cohort, join round, visits, posts, comments, upvotes received |
| thinking.csv | One row per model call ({n_think}): the model's thinking summary and its raw answer |
| results/measures.json | The results page's numbers (primary analysis, descriptive measures, expressions) |
| results/summary.json | Key numbers used to compare runs |
| raw/ | Copies of the run's original logs (calls.jsonl holds every full prompt) |

CSV files are UTF-8 with a byte-order mark, so Excel shows Chinese and symbols correctly.
Rounds are shown to members as hours.
""", encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    rid = sys.argv[1]
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "exports" / rid
    print(export(rid, target))

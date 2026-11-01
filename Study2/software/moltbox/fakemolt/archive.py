"""Saving runs and reading them back (v0.4).

save()          runs/<id>/ -> archive/<id>.zip: every log file plus forum.html, a page that opens
                without the server
static_html()   that page: boards, every thread with its comments, the members
import_zip()    a saved zip -> runs/<id>/ (only the known run files are taken), so the platform can
                show the forum, the results and each agent's view again
"""
from __future__ import annotations

import html
import io
import json
import time
import zipfile
from pathlib import Path

from .config import RunConfig
from .forum import Post, replay
from .store import ROOT, RUNS, RunStore, find_run

ARCHIVE = ROOT / "archive"
RUN_FILES = ("manifest.json", "config.json", "prompts.json", "expressions.json", "measures.json",
             "actions.jsonl", "visits.jsonl", "calls.jsonl", "rounds.jsonl")
MAX_BYTES = 1_000_000_000  # refuse archives that unpack to more than 1 GB


def save(run_id: str, base: Path | None = None, out_dir: Path | None = None) -> Path:
    st = find_run(run_id, base)
    if st is None:
        raise FileNotFoundError(run_id)
    out_dir = out_dir or ARCHIVE
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.zip"
    tmp = path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in RUN_FILES:
            if st.file(name).exists():
                z.write(st.file(name), arcname=f"{run_id}/{name}")
        z.writestr(f"{run_id}/forum.html", static_html(st))
    tmp.replace(path)
    return path


def list_archives(out_dir: Path | None = None) -> list[dict]:
    out_dir = out_dir or ARCHIVE
    if not out_dir.exists():
        return []
    out = []
    for p in sorted(out_dir.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        info = {"name": p.name, "bytes": p.stat().st_size, "saved": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))}
        try:
            with zipfile.ZipFile(p) as z:
                m = next((n for n in z.namelist() if n.endswith("manifest.json")), None)
                if m:
                    man = json.loads(z.read(m))
                    info.update(run_id=man.get("run_id"), status=man.get("status"), rounds=man.get("rounds_done"),
                                cost=man.get("cost"), models=man.get("models"))
        except zipfile.BadZipFile:
            info["broken"] = True
        out.append(info)
    return out


def import_zip(data: bytes, base: Path | None = None) -> str:
    """Unpack a saved run into runs/. Only the known run files are read; anything else is ignored."""
    base = base or RUNS
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as ex:
        raise ValueError("not a zip file") from ex
    files: dict[str, bytes] = {}
    total = 0
    for info in z.infolist():
        parts = info.filename.replace("\\", "/").split("/")
        name = parts[-1]
        if info.is_dir() or name not in RUN_FILES + ("forum.html",) or ".." in parts or len(parts) > 2:
            continue
        total += info.file_size
        if total > MAX_BYTES:
            raise ValueError("archive too large")
        files[name] = z.read(info)
    for need in ("manifest.json", "config.json", "actions.jsonl"):
        if need not in files:
            raise ValueError(f"missing {need}")
    manifest = json.loads(files["manifest.json"])
    RunConfig.model_validate(json.loads(files["config.json"]))  # refuses a config this version cannot read
    old = str(manifest.get("run_id") or "imported")
    old = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in old)[:80] or "imported"
    run_id, n = old, 1
    while (base / run_id).exists():
        n += 1
        run_id = f"{old}-import{n if n > 2 else ''}"
    path = base / run_id
    path.mkdir(parents=True)
    for name, blob in files.items():
        if name != "forum.html":
            (path / name).write_bytes(blob)
    st = RunStore(path)
    st.update_manifest(run_id=run_id, imported_from=old, imported=time.strftime("%Y-%m-%d %H:%M:%S"),
                       status="interrupted" if manifest.get("status") in ("running", "created") else manifest.get("status"))
    return run_id


# ---- the static forum page ----------------------------------------------------------
def static_html(st: RunStore) -> str:
    cfg = RunConfig.model_validate(st.read_json("config.json"))
    m = st.read_json("manifest.json", {})
    f = replay([c.name for c in cfg.communities], st.read_jsonl("actions.jsonl"))
    cohort = {h: ("founder" if a.phase == 0 else "newcomer") for h, a in f.agents.items()}
    e = html.escape

    def who(h):
        tag = "F" if cohort.get(h) == "founder" else "N"
        return f'<span class="h">{e(h)}</span><span class="tag {tag}">{"founder" if tag == "F" else "newcomer"}</span>'

    kids: dict[str, list] = {}
    for c in f.comments.values():
        kids.setdefault(c.parent, []).append(c)

    def thread(pid: str, parent: str, depth: int, author_of_post: str) -> str:
        out = []
        for c in kids.get(parent, []):
            reply = f'<span class="re">↳ {e(f.author_of(c.parent) or "")} {e(c.parent)}</span>' if depth > 6 else ""
            inner = (f'<div class="c" id="{c.id}"><div class="m">{who(c.author)}{" <b>OP</b>" if c.author == author_of_post else ""} '
                     f'{reply}<span>round {c.round}</span><span>▲ {f.upvotes(c.id)}</span><span class="id">{c.id}</span></div>'
                     f'<div class="b">{e(c.body)}</div>')
            sub = thread(pid, c.id, depth + 1, author_of_post)
            if depth < 6:
                out.append(inner + (f'<div class="kids">{sub}</div>' if sub else "") + "</div>")
            else:
                out.append(inner + "</div>" + sub)
        return "".join(out)

    boards = [(c.name, c.description, None, 0) for c in cfg.communities] + \
        [(b.name, b.description, b.author, b.round) for b in f.boards.values()]
    n_posts = {}
    for p in f.posts.values():
        n_posts[p.community] = n_posts.get(p.community, 0) + 1
    board_html = "".join(
        f'<li><b>{e(n)}</b> · {n_posts.get(n, 0)} posts{f" · started by {e(a)} in round {r}" if a else ""}<div class="muted">{e(d)}</div></li>'
        for n, d, a, r in boards)
    posts = sorted(f.posts.values(), key=lambda p: int(p.id[2:]))
    index = "".join(f'<li><a href="#{p.id}">{e(p.title)}</a> <span class="muted">· {e(p.community)} · round {p.round} · '
                    f'{f.comment_count(p.id)} comments</span></li>' for p in posts)

    def post_html(p: Post) -> str:
        ups = "".join(f'<div class="upd"><span class="muted">Update · round {u.round}</span><div>{e(u.body)}</div></div>'
                      for u in p.updates)
        return (f'<section class="p" id="{p.id}"><div class="m"><span class="board">{e(p.community)}</span>{who(p.author)}'
                f'<span>round {p.round}</span><span>▲ {f.upvotes(p.id)}</span><span class="id">{p.id}</span></div>'
                f'<h2>{e(p.title)}</h2><div class="b">{e(p.body)}</div>{ups}'
                f'<details open><summary>{f.comment_count(p.id)} comments</summary>{thread(p.id, p.id, 1, p.author)}</details></section>')

    agents = "".join(
        f'<tr><td>{who(h)}</td><td>{a.joined_round}</td><td>{sum(isinstance(x, Post) for x in f.items_by(h))}</td>'
        f'<td>{sum(not isinstance(x, Post) for x in f.items_by(h))}</td></tr>' for h, a in f.agents.items())
    meta = (f'{len(f.agents)} members · {len(f.posts)} posts · {len(f.comments)} comments · {len(f.boards)} boards started by members · '
            f'{m.get("rounds_done", f.round)} rounds (shown to members as hours) · models {e(", ".join(m.get("models", [])))} · '
            f'cost ${m.get("cost", 0):.2f} · status {e(str(m.get("status", "")))}')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forum {e(st.run_id)}</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1d2430; --muted:#5f6b7a; --line:#e3e7ee; --acc:#b45309; --accs:#fdf1df; --pri:#1d4ed8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0d1117; --card:#151b24; --ink:#e6edf3; --muted:#9aa7b4; --line:#273140; --acc:#f59e0b; --accs:#2a2112; --pri:#7aa2ff; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.6 -apple-system, "Segoe UI", "PingFang SC", sans-serif; }}
main {{ max-width:900px; margin:0 auto; padding:24px 16px 80px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:6px 0; }}
.muted, .m {{ color:var(--muted); font-size:13px; }} .m {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
.card, .p {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:14px 0; }}
.b {{ white-space:pre-wrap; overflow-wrap:anywhere; }} .id {{ font-family:ui-monospace, monospace; }}
.h {{ font-family:ui-monospace, monospace; color:var(--pri); }}
.tag {{ font-size:11px; padding:1px 6px; border-radius:99px; border:1px solid var(--line); margin-left:4px; }}
.board {{ font-weight:600; }} .c {{ margin-top:10px; }} .kids {{ margin-left:10px; padding-left:12px; border-left:2px solid var(--line); }}
.re {{ color:var(--muted); }} .upd {{ margin-top:8px; padding:6px 10px; border-left:3px solid var(--acc); background:var(--accs); border-radius:0 6px 6px 0; }}
summary {{ cursor:pointer; color:var(--muted); margin-top:8px; }} table {{ border-collapse:collapse; width:100%; }}
td, th {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--line); font-size:13px; }} a {{ color:var(--pri); }}
</style></head><body><main>
<h1>Fake Moltbook · {e(st.run_id)}</h1>
<p class="muted">{meta}</p>
<p class="muted">Saved {time.strftime("%Y-%m-%d %H:%M")}. A read-only copy of the forum; to see each member's view of each visit, import the archive into the platform.</p>
<div class="card"><h2>Boards</h2><ul>{board_html}</ul></div>
<div class="card"><h2>Posts</h2><ol>{index}</ol></div>
{"".join(post_html(p) for p in posts)}
<div class="card"><h2>Members</h2><table><tr><th>Member</th><th>Joined (round)</th><th>Posts</th><th>Comments</th></tr>{agents}</table></div>
</main></body></html>"""

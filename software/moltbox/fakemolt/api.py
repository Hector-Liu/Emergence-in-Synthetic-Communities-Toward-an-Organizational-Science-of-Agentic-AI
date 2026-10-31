"""FastAPI app: JSON API under /api, the web page at /. Binds to 127.0.0.1 only (start.sh)."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from . import archive, guard, measures, settings, texts
from .config import RunConfig, smoke_config
from .engine import nav_template, templates
from .estimate import estimate
from .forum import Agent, Forum, replay
from .jobs import dumps, jobs
from .llm import CLAUDE_MODELS, PRICING, api_key, price_for, save_key
from .prompts import build_nav, build_visit
from .reader import Reader
from .store import RUNS, RunStore, delete_run, find_run, list_runs

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
app = FastAPI(title="Fake Moltbook", version="0.1")


@app.middleware("http")
async def no_cache(request, call_next):
    """The page is a local tool that changes with the code; never serve a stale copy."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _errors(ex: ValidationError) -> list[str]:
    out = []
    for e in ex.errors():
        loc = ".".join(str(x) for x in e["loc"])
        out.append(f"{loc}: {e['msg']}" if loc else e["msg"])
    return out


def _config(d: dict) -> RunConfig:
    try:
        return RunConfig.model_validate(d)
    except ValidationError as ex:
        raise HTTPException(422, {"errors": _errors(ex)})


def _store(run_id: str) -> RunStore:
    s = find_run(run_id)
    if not s:
        raise HTTPException(404, "run not found")
    return s


def _paid(cfg: RunConfig) -> bool:
    return any(not m.startswith("mock") for m in cfg.models())


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    extra = settings.load().get("models", [])
    return {"default_config": RunConfig().model_dump(),
            "models": CLAUDE_MODELS + [m for m in extra if m not in CLAUDE_MODELS] + ["mock"],
            "prices": {m: price_for(m) for m in list(PRICING) + extra},
            "key_set": api_key() is not None,
            "default_prompts": {"system": texts.default_template("system"), "visit": texts.default_template("visit")},
            "placeholders": {"system": ["{identity}", "{handle}", "{communities}", "{sees}", "{goal}", "{privacy}", "{board_option}"],
                             "visit": ["{feed}", "{boards}", "{notifications}", "{record}", "{actions}", "{post_board}", "{board_rule}"]},
            "denylist": texts.denylist(True), "denylist_no_identity": texts.denylist(False)}


class ConfigBody(BaseModel):
    config: dict


@app.post("/api/estimate")
def api_estimate(body: ConfigBody):
    try:
        cfg = RunConfig.model_validate(body.config)
    except ValidationError as ex:
        return {"ok": False, "errors": _errors(ex)}
    s, v = templates(cfg)
    hits = guard.preflight(cfg, s, v)
    smoke = smoke_config(cfg)
    measured = _measured_output(cfg)
    return {"ok": True, "errors": [], "guard": hits, "full": estimate(cfg, measured), "smoke": estimate(smoke, measured),
            "rounds": cfg.total_rounds(), "agents": cfg.total_agents(), "phase_bounds": cfg.phase_bounds(),
            "paid": _paid(cfg), "key_set": api_key() is not None}


@app.post("/api/preview")
def preview(body: ConfigBody):
    """What one agent would see, on a small made-up forum (nothing is sent anywhere)."""
    cfg = _config(body.config)
    names = [c.name for c in cfg.communities]
    f = Forum(communities=names)
    for i, h in enumerate(["u_k2v9qa", "u_m4x7rt", "u_p8d3wz"]):
        f.add_agent(Agent(h, "mock", names[i % len(names)], 1, 0, i))
    p1 = f.add_post("u_m4x7rt", names[0], 1, "(a post title written by another member)",
                    "(The body of a post written by another member.)")
    f.add_comment("u_p8d3wz", p1.id, 2, "(A comment by a third member.)")
    p2 = f.add_post("u_k2v9qa", names[0], 2, "(a post title you wrote earlier)", "(The body of your own post.)")
    f.add_comment("u_m4x7rt", p2.id, 3, "(A reply to your post.)")
    f.add_vote("u_m4x7rt", p2.id)
    s, v = templates(cfg)
    two = cfg.visit.two_step and cfg.boards_on()
    visit = build_visit(f, "u_k2v9qa", 4, cfg, s, v, mark=1, board=names[0] if two else None)
    hits = guard.preflight(cfg, s, v)
    out = {"system": visit.system, "user": visit.user, "guard": hits, "schema": visit.schema, "two_step": two}
    if two:
        nav = build_nav(f, "u_k2v9qa", 4, cfg, s, nav_template(cfg), mark=1)
        out["nav"] = nav.user
    # sentences that switches put into the prompts, so the page can mark them
    out["inserted"] = [x.strip() for x, on in ((texts.POST_HINT, cfg.switches.post_hint),
                                               (texts.BOARDS_NOTE, cfg.boards_on() and cfg.boards.note),
                                               (texts.UPDATE_OPTION, cfg.switches.updates),
                                               (texts.IDENTITY_AI, cfg.switches.tell_ai),
                                               (texts.GOALS[cfg.switches.goal], cfg.switches.goal != "none")) if on and x.strip()]
    return out


class StartBody(BaseModel):
    config: dict
    mode: str = "full"  # full | smoke
    confirm: bool = False


@app.post("/api/runs")
def start(body: StartBody):
    cfg = _config(body.config)
    if body.mode == "smoke":
        cfg = smoke_config(cfg)
    if _paid(cfg):
        if api_key() is None:
            raise HTTPException(400, "No Anthropic API key. Add one on the Models page.")
        if not body.confirm:
            raise HTTPException(409, {"estimate": estimate(cfg)})
    store = RunStore.create(cfg.name or body.mode)
    store.update_manifest(run_id=store.run_id, name=cfg.name, mode=body.mode, status="created", rounds_done=0,
                          total_rounds=cfg.total_rounds(), models=cfg.models(), solo=cfg.switches.solo, cost=0.0,
                          calls=0, void=0, refusals=0, errors=0, budget_usd=cfg.budget_usd)  # visible at once
    jobs.start(store, cfg, mode=body.mode)
    return {"run_id": store.run_id}


@app.get("/api/runs")
def runs():
    out = list_runs()
    for m in out:
        _live(m)
    return out


def _live(m: dict) -> dict:
    """A run marked running whose thread is gone (server restarted) is interrupted; it can be resumed."""
    m["running"] = jobs.running(m.get("run_id", ""))
    if m.get("status") in ("running", "created") and not m["running"]:
        m["status"] = "interrupted"
    return m


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    s = _store(run_id)
    m = _live(s.read_json("manifest.json", {}))
    return {"manifest": m, "usage": _usage(s), "config": s.read_json("config.json"), "prompts": s.read_json("prompts.json"),
            "expressions": s.read_json("expressions.json"), "rounds": s.read_jsonl("rounds.jsonl")}


def _measured_output(cfg: RunConfig) -> dict | None:
    """Output tokens per call from the latest finished smoke run with the same models and effort.
    Input tokens are not taken over: a smoke forum is smaller than a full one."""
    for m in list_runs():
        if m.get("mode") == "smoke" and m.get("status") == "done" and m.get("models") == cfg.models():
            st = find_run(m["run_id"])
            run_cfg = st.read_json("config.json", {}) if st else {}
            if run_cfg.get("llm", {}).get("effort") == cfg.llm.effort:
                u = _usage(st)
                if u.get("calls"):
                    return {"output_per_call": round(u["output_per_call"]), "from_run": m["run_id"]}
    return None


def _usage(s: RunStore) -> dict:
    """Measured tokens and cost per call, from the call log (what a smoke run is for)."""
    calls = [c["result"] for c in s.read_jsonl("calls.jsonl")]
    paid = [r for r in calls if r.get("usage") and r.get("model") != "mock"]
    if not paid:
        return {"calls": 0}
    n = len(paid)
    return {"calls": n,
            "input_per_call": sum(r["usage"].get("input_tokens", 0) for r in paid) / n,
            "output_per_call": sum(r["usage"].get("output_tokens", 0) for r in paid) / n,
            "cost_per_call": sum(r.get("cost", 0.0) for r in paid) / n,
            "seconds_per_call": sum(r.get("seconds", 0.0) for r in paid) / n,
            "refusals": sum(r.get("stop_reason") == "refusal" for r in calls),
            "max_tokens": sum(r.get("stop_reason") == "max_tokens" for r in calls),
            "errors": sum(bool(r.get("error")) for r in calls)}


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str):
    j = jobs.jobs.get(run_id)
    if not j or not jobs.running(run_id):
        raise HTTPException(409, "not running")
    j.cancel.set()
    return {"ok": True}


class ResumeBody(BaseModel):
    confirm: bool = False
    budget_usd: Optional[float] = None


@app.post("/api/runs/{run_id}/resume")
def resume(run_id: str, body: ResumeBody):
    s = _store(run_id)
    if jobs.running(run_id):
        raise HTTPException(409, "already running")
    cfg = RunConfig.model_validate(s.read_json("config.json"))
    if body.budget_usd is not None:
        cfg.budget_usd = body.budget_usd
        s.write_json("config.json", cfg.model_dump())
        s.update_manifest(budget_usd=body.budget_usd)
    if _paid(cfg) and not body.confirm:
        raise HTTPException(409, "confirm the cost first")
    jobs.start(s)
    return {"ok": True}


@app.delete("/api/runs/{run_id}")
def remove(run_id: str):
    if jobs.running(run_id):
        raise HTTPException(409, "stop the run first")
    if not delete_run(run_id):
        raise HTTPException(404)
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, since: int = 0):
    j = jobs.jobs.get(run_id)
    if not j:
        raise HTTPException(404, "no live job for this run")

    async def gen():
        i = since
        while True:
            while i < len(j.events):
                ev = j.events[i]
                i += 1
                yield f"data: {dumps(ev)}\n\n"
                if ev.get("type") == "run_end":
                    return
            await asyncio.sleep(0.3)
            yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_readers: dict[str, tuple] = {}


def _reader(run_id: str) -> Reader:
    """One Reader per run, rebuilt when the run's logs have grown."""
    s = _store(run_id)
    key = tuple(s.file(n).stat().st_size if s.file(n).exists() else 0 for n in ("actions.jsonl", "visits.jsonl"))
    hit = _readers.get(run_id)
    if hit and hit[0] == key:
        return hit[1]
    r = Reader(s)
    _readers[run_id] = (key, r)
    return r


@app.get("/api/runs/{run_id}/forum")
def forum(run_id: str, round: Optional[int] = None):
    r = _reader(run_id)
    return r.forum(round)


@app.get("/api/runs/{run_id}/profile/{handle}")
def profile(run_id: str, handle: str):
    out = _reader(run_id).profile(handle)
    if not out:
        raise HTTPException(404, "no such agent")
    return out


@app.get("/api/runs/{run_id}/view/{handle}/{round}")
def agent_view(run_id: str, handle: str, round: int):
    out = _reader(run_id).agent_view(handle, round)
    if not out:
        raise HTTPException(404, "no visit by this agent in that round")
    return out


@app.get("/api/runs/{run_id}/activity")
def activity(run_id: str):
    return _reader(run_id).activity()


@app.get("/api/runs/{run_id}/export.csv")
def export_csv(run_id: str):
    return Response(_reader(run_id).csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'})


@app.get("/api/runs/{run_id}/export.md")
def export_md(run_id: str):
    return Response(_reader(run_id).markdown(), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.md"'})


@app.get("/api/runs/{run_id}/measures")
def run_measures(run_id: str, redraws: int = 2000, refresh: bool = False):
    return measures.cached(_store(run_id), redraws=redraws, refresh=refresh)


@app.get("/api/runs/{run_id}/download")
def download(run_id: str):
    s = _store(run_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(s.path.iterdir()):
            if p.is_file():
                z.write(p, arcname=f"{run_id}/{p.name}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'})


@app.get("/api/compare")
def compare(ids: str):
    """Key numbers of several runs side by side: ?ids=a,b,c"""
    out = []
    for rid in [x for x in ids.split(",") if x][:8]:
        s = _store(rid)
        out.append({"run_id": rid, "name": s.read_json("manifest.json", {}).get("name", ""),
                    **measures.summary(measures.RunData(s))})
    return out


@app.get("/api/runs/{run_id}/export.html")
def export_html(run_id: str, download: int = 0):
    """The forum as one page that opens without the server."""
    page = archive.static_html(_store(run_id))
    headers = {"Content-Disposition": f'attachment; filename="{run_id}-forum.html"'} if download else {}
    return Response(page, media_type="text/html; charset=utf-8", headers=headers)


@app.post("/api/runs/{run_id}/archive")
def save_archive(run_id: str):
    s = _store(run_id)
    if jobs.running(run_id):
        raise HTTPException(409, "the run is still going; save it when it has finished or been stopped")
    path = archive.save(run_id)
    return {"ok": True, "name": path.name, "path": str(path), "bytes": path.stat().st_size}


@app.get("/api/archives")
def archives():
    return {"dir": str(archive.ARCHIVE), "archives": archive.list_archives()}


@app.post("/api/archives/{name}/restore")
def restore_archive(name: str):
    if "/" in name or ".." in name or not name.endswith(".zip"):
        raise HTTPException(400, "bad archive name")
    p = archive.ARCHIVE / name
    if not p.exists():
        raise HTTPException(404, "archive not found")
    try:
        return {"ok": True, "run_id": archive.import_zip(p.read_bytes())}
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex


@app.post("/api/runs/import")
async def import_run(request: Request):
    """Body: a zip saved by this platform (Save to archive, or Download)."""
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > archive.MAX_BYTES:
        raise HTTPException(413, "archive too large")
    try:
        return {"ok": True, "run_id": archive.import_zip(data)}
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex


class KeyBody(BaseModel):
    key: str


@app.post("/api/key")
def set_key(body: KeyBody):
    if len(body.key.strip()) < 12:
        raise HTTPException(400, "That does not look like an API key.")
    save_key(body.key)
    return {"ok": True}


class PriceBody(BaseModel):
    model: str
    input: float
    output: float


@app.post("/api/prices")
def set_price(body: PriceBody):
    d = settings.load()
    d.setdefault("pricing", {})[body.model] = [body.input, body.output]
    if body.model not in PRICING and body.model not in d.get("models", []):
        d.setdefault("models", []).append(body.model)
    settings.update(**d)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
RUNS.mkdir(exist_ok=True)

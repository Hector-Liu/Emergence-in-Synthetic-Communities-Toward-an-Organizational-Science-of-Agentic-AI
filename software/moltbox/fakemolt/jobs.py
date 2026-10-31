"""Background runs: each run gets a thread with its own event loop; the web page follows its events."""
from __future__ import annotations

import asyncio
import json
import threading
import time

from .config import RunConfig
from .engine import Run
from .store import RunStore


class Job:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list[dict] = []
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None
        self.status = "running"

    def emit(self, ev: dict):
        ev = {**ev, "time": time.time()}
        self.events.append(ev)
        if ev.get("type") == "run_end":
            self.status = ev.get("status", "done")


class Jobs:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def running(self, run_id: str) -> bool:
        j = self.jobs.get(run_id)
        return bool(j and j.thread and j.thread.is_alive())

    def start(self, store: RunStore, cfg: RunConfig | None = None, mode: str = "full") -> Job:
        """New run when cfg is given, otherwise resume the stored run."""
        with self.lock:
            if self.running(store.run_id):
                raise RuntimeError("This run is already running.")
            job = Job(store.run_id)
            self.jobs[store.run_id] = job

        def target():
            try:
                if cfg is not None:
                    run = Run.new(cfg, store, mode=mode, progress=job.emit, cancel=job.cancel)
                else:
                    run = Run.resume(store, progress=job.emit, cancel=job.cancel)
                asyncio.run(run.run())
            except Exception as ex:  # noqa: BLE001
                m = store.update_manifest(status="error", message=f"{type(ex).__name__}: {ex}")
                job.emit({"type": "run_end", "status": "error", "message": m["message"], "manifest": m})
            autosave(store, job)

        job.thread = threading.Thread(target=target, daemon=True, name=f"run-{store.run_id}")
        job.thread.start()
        return job


def autosave(store: RunStore, job: Job | None = None):
    """Every paid run, however it ended, is copied to archive/ (logs + offline forum page)."""
    from . import archive
    m = store.read_json("manifest.json", {})
    if all(str(x).startswith("mock") for x in m.get("models", [])):
        return
    try:  # results first, so the results page opens at once and the archive carries them
        from . import measures
        measures.cached(store)
    except Exception as ex:  # noqa: BLE001
        store.update_manifest(measures_error=f"{type(ex).__name__}: {ex}")
    try:
        path = archive.save(store.run_id, store.path.parent)
        store.update_manifest(archived=str(path), archived_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        if job:
            job.emit({"type": "archived", "path": str(path)})
    except Exception as ex:  # noqa: BLE001 - saving must never break a run
        store.update_manifest(archive_error=f"{type(ex).__name__}: {ex}")


jobs = Jobs()


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)

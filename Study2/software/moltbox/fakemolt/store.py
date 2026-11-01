"""Append-only run store (SPEC 7.1): runs/{run_id}/.

calls.jsonl     one line per model call, written before its result is used
actions.jsonl   committed forum actions; replaying it rebuilds the forum
visits.jsonl    what each visit showed (slots, random pool) and what came of it
rounds.jsonl    one summary line per committed round
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=lambda x: sorted(x) if isinstance(x, set) else str(x))


class RunStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @classmethod
    def create(cls, name: str, base: Path | None = None) -> "RunStore":
        base = base or RUNS
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:30]
        run_id = f"{stamp}-{slug}" if slug else stamp
        path = base / run_id
        n = 1
        while path.exists():
            n += 1
            path = base / f"{run_id}-{n}"
        path.mkdir(parents=True)
        return cls(path)

    @property
    def run_id(self) -> str:
        return self.path.name

    def file(self, name: str) -> Path:
        return self.path / name

    def write_json(self, name: str, obj):
        tmp = self.file(name + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
        tmp.replace(self.file(name))

    def read_json(self, name: str, default=None):
        try:
            return json.loads(self.file(name).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def append(self, name: str, rows: list[dict]):
        if not rows:
            return
        with self.file(name).open("a") as fh:
            fh.write("".join(dumps(r) + "\n" for r in rows))
            fh.flush()

    def read_jsonl(self, name: str) -> list[dict]:
        p = self.file(name)
        if p.exists():
            text = p.read_text()
        elif self.file(name + ".gz").exists():  # published runs ship large logs compressed (data/)
            import gzip
            text = gzip.decompress(self.file(name + ".gz").read_bytes()).decode()
        else:
            return []
        out = []
        for line in text.splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    break  # a torn last line from a crash
        return out

    def update_manifest(self, **fields) -> dict:
        m = self.read_json("manifest.json", {})
        m.update(fields)
        self.write_json("manifest.json", m)
        return m

    def last_complete_round(self) -> int:
        last = 0
        for a in self.read_jsonl("actions.jsonl"):
            if a.get("kind") == "round_end":
                last = a["round"]
        return last

    def truncate_after(self, last_round: int):
        """Drop rows of a round that was not committed (crash or cancel mid-round). Calls are kept."""
        for name in ("actions.jsonl", "visits.jsonl", "rounds.jsonl"):
            rows = self.read_jsonl(name)
            keep = [r for r in rows if r.get("round", 0) <= last_round]
            if len(keep) != len(rows):
                self.file(name).write_text("".join(dumps(r) + "\n" for r in keep))


def list_runs(base: Path | None = None) -> list[dict]:
    base = base or RUNS
    if not base.exists():
        return []
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        m = RunStore(d).read_json("manifest.json") if d.is_dir() else None
        if m:
            out.append(m)
    return out


def find_run(run_id: str, base: Path | None = None) -> RunStore | None:
    base = base or RUNS
    if "/" in run_id or ".." in run_id:
        return None
    p = base / run_id
    return RunStore(p) if (p / "manifest.json").exists() else None


def open_path(path: str | Path) -> RunStore:
    """A run folder anywhere on disk, e.g. data/moltbox/run-01 (read-only use)."""
    return RunStore(Path(path))


def delete_run(run_id: str, base: Path | None = None) -> bool:
    s = find_run(run_id, base)
    if not s:
        return False
    shutil.rmtree(s.path)
    return True

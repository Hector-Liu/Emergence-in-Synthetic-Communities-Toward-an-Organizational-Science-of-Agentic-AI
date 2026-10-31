"""Make the published data usable by the software and the analysis scripts.

    venv/bin/python reproduce/setup_data.py

The package ships the run in data/moltbox/run-01/ with its model-call log compressed
(calls.jsonl.gz). The web app reads runs/<run_id>/. This script copies the run there under its
original id and unpacks calls.jsonl. It never overwrites a run that is already present. Afterwards
./start.sh shows the run on the Forum and Results pages.
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # software/moltbox
DATA = ROOT.parents[1] / "data" / "moltbox" / "run-01"  # the reported run, in the package's data folder
SRC = DATA


def main() -> int:
    run_id = json.load(open(SRC / "manifest.json"))["run_id"]
    dst = ROOT / "runs" / run_id
    if (dst / "manifest.json").exists() and (dst / "calls.jsonl").exists():
        print(f"runs/{run_id} already present; nothing to do")
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    for f in SRC.iterdir():
        if f.name == "calls.jsonl.gz":
            with gzip.open(f, "rb") as fin, open(dst / "calls.jsonl", "wb") as fout:
                shutil.copyfileobj(fin, fout)
        elif f.is_file():
            shutil.copy2(f, dst / f.name)
    print(f"runs/{run_id} ready ({sum(1 for _ in dst.iterdir())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

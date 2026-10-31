"""Run the Moltbox experiment again with the exact settings of run-01.

    venv/bin/python reproduce/rerun.py --mock        # free: the whole 120-round run with a scripted stand-in model
    venv/bin/python reproduce/rerun.py --real        # the real run: Claude Haiku 5.5, needs ANTHROPIC_API_KEY,
                                                     # costs about US$5 (run-01 cost US$5.11)

The settings come from data/moltbox/run-01/config.json, unchanged. --mock checks that the software runs
end to end and writes the same kinds of logs (it does not reproduce the agents' text). A --real run
draws the same schedule, feed slots and random draws (same seed) but model replies are not
deterministic, so a new run is a replication, not a copy. Output goes to runs/<new run id>/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # software/moltbox
DATA = ROOT.parents[1] / "data" / "moltbox" / "run-01"  # the reported run, in the package's data folder
sys.path.insert(0, str(ROOT))

from fakemolt.config import RunConfig  # noqa: E402
from fakemolt.engine import Run  # noqa: E402
from fakemolt.llm import MockModel, make_model  # noqa: E402
from fakemolt.store import RunStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true", help="scripted stand-in model, no API calls")
    g.add_argument("--real", action="store_true", help="Claude Haiku 5.5 through the Anthropic API (paid)")
    a = ap.parse_args()

    cfg = RunConfig.model_validate(json.load(open(DATA / "config.json")))
    name = ("rerun-mock" if a.mock else "rerun") + "-run-01"
    store = RunStore.create(name)
    factory = (lambda mid: MockModel()) if a.mock else make_model
    t = time.time()
    m = asyncio.run(Run.new(cfg, store, model_factory=factory).run())
    print(f"{store.run_id}: status {m.get('status')}, {m.get('rounds_done')} rounds, "
          f"{m.get('visits', '?')} visits, cost ${m.get('cost', 0):.2f}, {time.time() - t:.0f} s")
    print(f"logs in runs/{store.run_id}/")
    return 0 if m.get("status") == "done" else 1


if __name__ == "__main__":
    sys.exit(main())

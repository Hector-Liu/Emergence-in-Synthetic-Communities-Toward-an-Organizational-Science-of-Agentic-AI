import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fakemolt.config import RunConfig  # noqa: E402
from fakemolt.engine import Run  # noqa: E402
from fakemolt.llm import MockModel  # noqa: E402
from fakemolt.store import RunStore  # noqa: E402


def cfg(**kw) -> RunConfig:
    d = {"activation": 1.0, "feed": {"hot_window": 10}, "phases": [{"name": "founders", "add": [{"n": 4, "model": "mock"}], "rounds": 4},
                    {"name": "newcomers", "add": [{"n": 6, "model": "mock"}], "rounds": 4}]}
    for k, v in kw.items():
        d[k] = {**d[k], **v} if isinstance(v, dict) and isinstance(d.get(k), dict) else v
    return RunConfig.model_validate(d)


def run(config: RunConfig, base: Path, name="t", mock=None, **kw):
    st = RunStore.create(name, base)
    model = mock or MockModel()
    m = asyncio.run(Run.new(config, st, model_factory=lambda mid: model, **kw).run())
    return st, m


@pytest.fixture
def base(tmp_path):
    return tmp_path

# Moltbox simulator

The simulator used for the run in `../../data/moltbox/run-01/`. The code and the interface call it Fake Moltbook (`fakemolt`).

| Path | Contents |
|---|---|
| `fakemolt/` | The simulator, including the prompt texts in `fakemolt/texts/v1/`. |
| `web/` | The browser interface. |
| `start.sh` | Prepares the environment and starts the browser interface. |
| `reproduce/setup_data.py` | Copies the reported run into `runs/` so that the interface can show it. |
| `reproduce/rerun.py` | Runs the reported run's settings again. |
| `scripts/export_run.py` | Exports a run to a plain folder. |
| `tests/` | Tests that use a scripted model. |
| `requirements.txt` | Package versions of the environment in which the reported run was made (Python 3.13.5). |

## Use

Run the commands from this folder.

```bash
./start.sh
```

On first use, `start.sh` creates `venv/` with Python 3.12 or later and installs `requirements.txt`. It then starts the interface at `http://127.0.0.1:8767`. The Free trial run button on the Design page uses a scripted model and makes no model calls. A run with a model needs an Anthropic API key, set in the environment variable `ANTHROPIC_API_KEY`, in a `.env` file in this folder (`ANTHROPIC_API_KEY=...`), or on the Models & key page.

To show the reported run in the interface:

```bash
venv/bin/python reproduce/setup_data.py
```

To run the reported run's settings again with the scripted model or with Claude Haiku 5.5:

```bash
venv/bin/python reproduce/rerun.py --mock
venv/bin/python reproduce/rerun.py --real
```

Output goes to `runs/<run_id>/`. A new run uses the reported run's settings and seed, but the model's replies are not seeded, so the posts and comments will differ.

To run the tests:

```bash
venv/bin/python -m pytest tests -q
```

Changes since the reported run touch the browser interface, the run store, the launcher, the paths in `reproduce/`, and other supporting code. The code that determines what agents see and do is unchanged.

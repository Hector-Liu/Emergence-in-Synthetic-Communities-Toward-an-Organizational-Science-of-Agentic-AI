# Study 2: data and software

Data and code for Study 2 and Appendices A and B of *Emergence in Synthetic Communities: Toward an Organizational Science of Agentic AI*.

| Folder | Contents |
|---|---|
| `data/moltbox/run-01/` | Records of the Moltbox run. |
| `data/babel/reported-runs/` | Records of the eight Babel runs reported in the proposal. |
| `software/moltbox/` | The Moltbox simulator, with a browser interface. |
| `software/babel/` | The Babel simulator. |
| `analysis/` | Scripts that recompute the reported numbers and figures from `data/`. |

`data/README.md` lists the files and their fields; `analysis/`, `software/babel/` and `software/moltbox/` each have their own README.

## Use

From this folder (`Study2/`):

```bash
# Reported numbers and figures (Python 3.9 to 3.12)
python3 -m pip install -r analysis/requirements.txt
python3 analysis/moltbox/verify_claims.py
python3 analysis/babel/verify_claims.py
python3 analysis/moltbox/make_figures.py
python3 analysis/babel/make_figures.py

# Moltbox: the browser interface (requires Python 3.12+; creates software/moltbox/venv on first use)
software/moltbox/start.sh
# Moltbox: the reported run's settings, with a scripted model (Python 3.9+ once requirements are installed)
software/moltbox/venv/bin/python software/moltbox/reproduce/rerun.py --mock

# Babel: a short run with scripted agents (Python 3.9+, standard library only)
python3 software/babel/scripts/quick_trial.py --mock --rounds 10
```

Scripted runs make no model calls. Runs with a model call the Anthropic API and read the key from the environment variable `ANTHROPIC_API_KEY` or from a `.env` file in the simulator's folder.

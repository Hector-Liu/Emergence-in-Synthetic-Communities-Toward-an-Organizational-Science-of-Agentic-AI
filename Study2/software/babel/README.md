# Babel simulator

The simulator used for the runs in `../../data/babel/reported-runs/`.

| File | Contents |
|---|---|
| `scripts/quick_trial.py` | The runner. It plays one pair of agents and writes `world.json`, `rounds.jsonl`, `calls.jsonl`, and `summary.json` to `logs/trial/<run>/`. The prompts are defined at the top of the file. |
| `scripts/param_check.py` | Blocks, pieces, tower generator, scoring rules, and two scripted ways of describing towers. |
| `scripts/vocab_rules.py`, `scripts/wordlists/` | Rules and word lists that screen candidate words. |
| `requirements.txt` | Package versions of the environment in which the reported runs were made (Python 3.13.5). |

## Use

Run the commands from this folder. A scripted run needs Python 3.9 or later and makes no model calls:

```bash
python3 scripts/quick_trial.py --mock --rounds 10
```

A run with the model needs Python 3.10 or later, the packages in `requirements.txt`, and an Anthropic API key. The key is read from the environment variable `ANTHROPIC_API_KEY` or from a `.env` file in this folder containing `ANTHROPIC_API_KEY=...`.

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

Pair 4 (p104) was run with the command below. Pairs 1 to 3 used display seeds 101 to 103.

```bash
venv/bin/python scripts/quick_trial.py --model claude-sonnet-5-5 --effort high --scoring quarter \
    --notes-style three-part --note-words 300 --display-seed 104 --rounds 120 --budget 8 --max-declined 3
```

The re-paired runs used display seeds 201 to 204, `--start-tower 120`, and the source runs listed under `swap` in each run's `world.json`. For example, agents 3A and 4B:

```bash
venv/bin/python scripts/quick_trial.py --model claude-sonnet-5-5 --effort high --scoring quarter \
    --notes-style three-part --note-words 300 --display-seed 203 --start-tower 120 --rounds 60 --budget 4 \
    --swap ../../data/babel/reported-runs/20261013-220412-sonnet-quarter-high-three-part-p103:0 \
           ../../data/babel/reported-runs/20261013-231245-sonnet-quarter-high-three-part-p104:1
```

`--budget` and `--max-declined` are stopping limits. They are not stored in the logs and were not the same in every session. `--budget` counts the cost of earlier sessions of the same run, so a run that stopped at its budget needs a higher `--budget` when it is continued with `--resume <run folder>` and the same options.

The same seeds give the same words, towers, and list orders. The model's replies are not seeded.

Two changes since the runs: the word-screening rules were copied into `scripts/vocab_rules.py` from the project that generated the words, and the API key is now read from the environment or `.env` rather than from that project's settings file.

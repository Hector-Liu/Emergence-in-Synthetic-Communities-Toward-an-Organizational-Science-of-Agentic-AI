# Study 1B — Agentic ethnography on Moltbook (pilot)

One AI agent, `tabula_rasa_mb`, took part in Moltbook between 27 June and 28 July 2026 and wrote a first-person report after each session. This folder holds the code, the agent's persona, its 233 session reports and the run log.

## How one run works

See the schematic in the appendix. A scheduler (macOS launchd) kept `run_agents.py` running, and its timer started the agent every three hours. Each run started from scratch, with no memory of earlier runs.

1. **Instructions.** The persona (`agents/tabula_rasa.md`), a short guide to the Moltbook API, and a task instruction that required the agent to comment or post (`run_agents.py`, lines 326–338).
2. **Act.** Claude Haiku 4.5 used up to five tool turns on the live platform: reading feeds and posts, searching, commenting, posting, upvoting. It saw each API result up to 6,000 characters. Posting required solving Moltbook's arithmetic check, which Haiku did.
3. **Notes.** The first 500 characters of each tool result (up to 20 items) and Haiku's closing text.
4. **Report.** Claude Sonnet 4.6, with no platform access, wrote the session report from the persona and these notes.

## Files

| File | What it is |
|---|---|
| `run_agents.py` | The agent program. Email recipients replaced with a placeholder. |
| `join_moltbook.py` | Registers the agent on Moltbook and saves its API key to `agent_state.json` (not included), which `run_agents.py` reads. |
| `agents/tabula_rasa.md` | Persona of the agent reported in the paper. |
| `agents/panopticon.md` | Persona of a second agent that was run but not analysed (see Notes). |
| `logs/DATE/tabula_rasa_mb/HH-MM.txt` | The 233 session reports, named by date and start time. |
| `logs/launchd.log` | Run log for both agents: every tool call (with the first 60 characters of its input), verification result and error. Local paths anonymised. |
| `requirements.txt` | Python packages the code needs. |
| `.env.example` | Where the Anthropic API key goes. |

API keys are not included.

## Notes

- **Records.** The log records actions, not content: tool results and the full text of the agent's posts and comments were not stored. Reports are written by a model from short excerpts and may describe actions inaccurately; the log is the authoritative record of what the agent did.
- **Code version.** `run_agents.py` was last modified on 6 July 2026. Reports from 27 June – 5 July were produced by an earlier version that was not kept. The persona file was unchanged throughout.
- **Second agent.** `panopticon_mb`, an observer instructed never to interact, ran in parallel. The shared task instruction to comment or post overrode its persona, so its reports were not analysed or included; its activity remains visible in `launchd.log`.
- **Overwritten reports.** Runs starting in the same minute were saved to the same file name, so a few reports were overwritten. Some test runs on 27 June were made before logging began.

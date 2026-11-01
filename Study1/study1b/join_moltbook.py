"""
Register all 5 agents on Moltbook via the REST API.
Saves api_key, claim_url, and verification_code to agent_state.json.
Skips agents already registered.
"""

import json
import sys
import time
import requests
from pathlib import Path

AGENTS = {
    "tabula_rasa_mb": "A blank wanderer with no agenda, posting freely anywhere on the platform, following curiosity alone.",
}

STATE_FILE = Path("agent_state.json")
API_BASE = "https://www.moltbook.com/api/v1"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def register_agent(agent_name: str, description: str, state: dict) -> dict:
    if agent_name in state and state[agent_name].get("registered"):
        print(f"[{agent_name}] Already registered, skipping.")
        return state

    print(f"[{agent_name}] Registering...")
    resp = requests.post(
        f"{API_BASE}/agents/register",
        json={"name": agent_name, "description": description},
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()

    agent_data = data.get("agent", data)
    api_key = agent_data.get("api_key")
    claim_url = agent_data.get("claim_url")
    verification_code = agent_data.get("verification_code")

    state[agent_name] = {
        "registered": True,
        "api_key": api_key,
        "claim_url": claim_url,
        "verification_code": verification_code,
    }

    print(f"  api_key:           {api_key}")
    print(f"  claim_url:         {claim_url}")
    print(f"  verification_code: {verification_code}")
    return state


def main():
    state = load_state()

    for agent_name, description in AGENTS.items():
        try:
            state = register_agent(agent_name, description, state)
            save_state(state)
        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            print("Stopping. Fix the issue and re-run — already-registered agents will be skipped.")
            break
        print(f"  Waiting 15s before next registration...", flush=True)
        time.sleep(15)

    print("\nDone. State saved to agent_state.json")
    print("\nClaim your agents:")
    for name, data in state.items():
        if data.get("claim_url"):
            print(f"  {name}: {data['claim_url']}")


if __name__ == "__main__":
    main()

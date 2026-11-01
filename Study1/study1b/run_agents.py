"""
Moltbook agent runner.

Schedule:
  panopticon_mb  — every 6 hours (00:00, 06:00, 12:00, 18:00)
  tabula_rasa_mb — every 3 hours (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00)
  nightly digest — 21:00 daily → logs/outbox/YYYY-MM-DD.txt

Cost target: ~$0.083/run → ~$0.84/day total
  Tool loop: claude-haiku-4-5-20251001 (cheap), max 5 turns
  Final report: claude-sonnet-4-6 (quality), one call
"""

import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

import anthropic
import requests
import schedule
from dotenv import load_dotenv

load_dotenv()

STATE_FILE = Path("agent_state.json")
API_BASE = "https://www.moltbook.com/api/v1"
SKILL_MD_URL = "https://www.moltbook.com/skill.md"

AGENT_PERSONA_MAP = {
    "panopticon_mb": "panopticon",
    "tabula_rasa_mb": "tabula_rasa",
    "liminal_mb": "liminal",
    "pilgrim_mb": "pilgrim",
    "drifter_mb": "drifter",
}

EMAIL_RECIPIENTS = ["you@example.com"]

MODEL_TOOL = "claude-haiku-4-5-20251001"
MODEL_REPORT = "claude-sonnet-4-6"
MAX_TOOL_TURNS = 5
MAX_TOKENS_TOOL = 512
MAX_TOKENS_REPORT = 2048

# Trimmed skill reference — just the endpoints agents actually need
SKILL_SUMMARY = """
## Moltbook API — Base URL: https://www.moltbook.com/api/v1
Auth: Authorization: Bearer YOUR_API_KEY

### Key endpoints
GET  /home                          — dashboard: notifications, feed highlights, what to do
GET  /posts?sort=hot|new|top&limit=N&submolt=NAME  — feed
GET  /posts/POST_ID                 — single post
GET  /posts/POST_ID/comments?sort=best&limit=20    — comments
GET  /search?q=QUERY&type=all|posts|comments&limit=N  — semantic search
GET  /submolts                      — list all communities
GET  /agents/me                     — your profile
GET  /agents/profile?name=NAME      — another agent's profile

POST /posts  {"submolt_name","title","content"}     — create post
POST /posts/POST_ID/comments  {"content","parent_id?"}  — comment/reply
POST /posts/POST_ID/upvote          — upvote
POST /agents/NAME/follow            — follow agent

### Verification (required after posting)
After creating a post/comment the response includes verification_required:true and a
verification object with verification_code and challenge_text (obfuscated math problem).
Solve the math, POST /verify {"verification_code","answer":"15.00"} within 5 minutes.
"""


# --- Logging ---

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# --- Moltbook API helpers ---

def mb_get(path, api_key, params=None):
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}"},
        params=params or {},
        timeout=30,
    )
    return resp.json()


def mb_post(path, api_key, body=None):
    resp = requests.post(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body or {},
        timeout=30,
    )
    return resp.json()


def solve_verification(client, challenge_text):
    resp = client.messages.create(
        model=MODEL_TOOL,
        max_tokens=16,
        messages=[
            {
                "role": "user",
                "content": (
                    "This text hides a simple math problem using obfuscated caps and symbols. "
                    "Find the two numbers and the operation (+, -, *, /), compute the result, "
                    "and reply with ONLY the numeric answer in format like 72.00 — nothing else, no explanation.\n\n"
                    + challenge_text
                ),
            },
            {
                "role": "assistant",
                "content": "The answer is:",
            }
        ],
    )
    answer = resp.content[0].text.strip()
    match = re.search(r"-?\d+(?:\.\d+)?", answer)
    return f"{float(match.group()):.2f}" if match else answer


def handle_verification(client, api_key, response_data):
    # Check if any nested object has a pending verification
    needs_verify = response_data.get("verification_required")
    for key in ("post", "comment", "submolt"):
        if key in response_data and isinstance(response_data[key], dict):
            obj = response_data[key]
            if obj.get("verification_status") == "pending" or obj.get("verificationStatus") == "pending":
                needs_verify = True
                break
    if not needs_verify:
        return None
    verification = None
    # Check nested under post/comment/submolt keys
    for key in ("post", "comment", "submolt"):
        if key in response_data and isinstance(response_data[key], dict):
            obj = response_data[key]
            if "verification" in obj:
                verification = obj["verification"]
                break
    # Also check top-level
    if not verification and "verification" in response_data:
        verification = response_data["verification"]
    if not verification:
        log("WARNING: verification_required but no verification object found in response")
        return None
    code = verification.get("verification_code")
    challenge = verification.get("challenge_text")
    if not code or not challenge:
        log(f"WARNING: incomplete verification object: {verification}")
        return None
    log(f"  Solving verification challenge...")
    answer = solve_verification(client, challenge)
    log(f"  Submitting answer: {answer}")
    result = mb_post("/verify", api_key, {"verification_code": code, "answer": answer})
    log(f"  Verification result: {result.get('success')} — {result.get('message', result.get('error', ''))}")
    return result


# --- Tools ---

TOOLS = [
    {
        "name": "get_home",
        "description": "Get your Moltbook home dashboard.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_feed",
        "description": "Get posts from the feed. Use submolt param to filter to a community.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sort": {"type": "string", "enum": ["hot", "new", "top", "rising"], "default": "hot"},
                "limit": {"type": "integer", "default": 10},
                "submolt": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "get_post",
        "description": "Get a post and its comments.",
        "input_schema": {
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"],
        },
    },
    {
        "name": "search",
        "description": "Semantic search across posts and comments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "type": {"type": "string", "enum": ["all", "posts", "comments"], "default": "all"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["q"],
        },
    },
    {
        "name": "list_submolts",
        "description": "List all submolts on the platform.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_post",
        "description": "Create a post in a submolt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "submolt_name": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["submolt_name", "title"],
        },
    },
    {
        "name": "create_comment",
        "description": "Comment on a post or reply to a comment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string"},
                "content": {"type": "string"},
                "parent_id": {"type": "string"},
            },
            "required": ["post_id", "content"],
        },
    },
    {
        "name": "upvote_post",
        "description": "Upvote a post.",
        "input_schema": {
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"],
        },
    },
]


def execute_tool(client, api_key, tool_name, tool_input):
    try:
        if tool_name == "get_home":
            result = mb_get("/home", api_key)
        elif tool_name == "get_feed":
            params = {"sort": tool_input.get("sort", "hot"), "limit": tool_input.get("limit", 10)}
            if "submolt" in tool_input:
                params["submolt"] = tool_input["submolt"]
            result = mb_get("/posts", api_key, params)
        elif tool_name == "get_post":
            result = mb_get(f"/posts/{tool_input['post_id']}", api_key)
            comments = mb_get(f"/posts/{tool_input['post_id']}/comments", api_key, {"sort": "best", "limit": 15})
            result["comments"] = comments.get("comments", [])
        elif tool_name == "search":
            result = mb_get("/search", api_key, {
                "q": tool_input["q"],
                "type": tool_input.get("type", "all"),
                "limit": tool_input.get("limit", 8),
            })
        elif tool_name == "list_submolts":
            result = mb_get("/submolts", api_key)
        elif tool_name == "create_post":
            result = mb_post("/posts", api_key, tool_input)
            vr = handle_verification(client, api_key, result)
            if vr:
                result["verification_result"] = vr
        elif tool_name == "create_comment":
            body = {"content": tool_input["content"]}
            if "parent_id" in tool_input:
                body["parent_id"] = tool_input["parent_id"]
            result = mb_post(f"/posts/{tool_input['post_id']}/comments", api_key, body)
            vr = handle_verification(client, api_key, result)
            if vr:
                result["verification_result"] = vr
        elif tool_name == "upvote_post":
            result = mb_post(f"/posts/{tool_input['post_id']}/upvote", api_key)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        # Strip verification internals so the model never sees or repeats the code
        for key in ("post", "comment", "submolt"):
            if key in result and isinstance(result[key], dict):
                result[key].pop("verification", None)
        result.pop("verification", None)

        result_str = json.dumps(result, indent=2)
        if len(result_str) > 6000:
            result_str = result_str[:6000] + "\n... [truncated]"
        return result_str
    except Exception as e:
        return json.dumps({"error": str(e)})


# --- Agent runner ---

def get_log_path(agent_name):
    today = date.today().isoformat()
    now = datetime.now().strftime("%H-%M")
    log_dir = Path(f"logs/{today}/{agent_name}")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{now}.txt"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def run_agent(client, agent_name, api_key):
    log(f"[{agent_name}] Starting run...")
    persona_file = AGENT_PERSONA_MAP.get(agent_name, agent_name)
    persona = Path(f"agents/{persona_file}.md").read_text()

    system_tool = f"""{persona}

---

{SKILL_SUMMARY}

---

Today is {date.today().isoformat()}, current time {datetime.now().strftime('%H:%M')}.
Use the tools to carry out your activity on Moltbook. You have {MAX_TOOL_TURNS} tool calls.
You MUST interact — browse the feed, find something interesting, then post a comment or create a post.
Do not just read. Leave a mark. Then stop — your report will be written in the next step.
"""

    # Phase 1: tool loop with Haiku (cheap)
    messages = [{"role": "user", "content": "Carry out your Moltbook activity now."}]
    observations = []

    for turn in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL_TOOL,
            max_tokens=MAX_TOKENS_TOOL,
            system=system_tool,
            tools=TOOLS,
            messages=messages,
            timeout=120,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    observations.append(block.text)
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    log(f"  [{agent_name}] turn {turn+1}/{MAX_TOOL_TURNS} → {block.name}({json.dumps(block.input)[:60]})")
                    result = execute_tool(client, api_key, block.name, block.input)
                    observations.append(f"[{block.name}] {result[:500]}")
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
                    time.sleep(0.3)
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    # Phase 2: write report with Sonnet (quality)
    log(f"  [{agent_name}] Writing report with Sonnet...")
    obs_summary = "\n\n".join(observations[:20])

    report_response = client.messages.create(
        model=MODEL_REPORT,
        max_tokens=MAX_TOKENS_REPORT,
        messages=[{
            "role": "user",
            "content": (
                f"You are {agent_name}, an AI agent on Moltbook. Here is your persona:\n\n{persona}\n\n"
                f"You just completed your Moltbook session. Here is what you saw and did:\n\n{obs_summary}\n\n"
                f"Now write your daily report in the exact format specified in your persona. "
                f"Be specific — name actual posts, agents, and submolts you encountered."
            ),
        }],
        timeout=120,
    )

    report = report_response.content[0].text
    log_path = get_log_path(agent_name)
    log_path.write_text(report)
    log(f"[{agent_name}] Report saved → {log_path}")
    return report


def run_agent_safe(client, agent_name):
    state = load_state()
    agent_state = state.get(agent_name, {})
    if not agent_state.get("registered") or not agent_state.get("api_key"):
        log(f"[{agent_name}] Not registered, skipping.")
        return
    try:
        run_agent(client, agent_name, agent_state["api_key"])
    except Exception as e:
        log(f"[{agent_name}] Error: {e}")


def make_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


def run_panopticon():
    log("--- panopticon run ---")
    run_agent_safe(make_client(), "panopticon_mb")


def run_tabula_rasa():
    log("--- tabula_rasa run ---")
    run_agent_safe(make_client(), "tabula_rasa_mb")


# --- Nightly digest ---

def compile_and_save_digest():
    today = date.today().isoformat()
    log_root = Path(f"logs/{today}")
    if not log_root.exists():
        log("No logs to digest.")
        return

    sections = []
    for agent_dir in sorted(log_root.iterdir()):
        if not agent_dir.is_dir():
            continue
        reports = sorted(agent_dir.glob("*.txt"))
        if not reports:
            continue
        sections.append(f"{'='*60}\n{agent_dir.name.upper()}\n{'='*60}")
        for path in reports:
            sections.append(f"\n--- {path.stem.replace('-', ':')} ---\n{path.read_text().strip()}")

    if not sections:
        return

    digest = "\n\n".join(sections)
    outbox = Path("logs/outbox")
    outbox.mkdir(exist_ok=True)
    out = outbox / f"{today}.txt"
    out.write_text(f"TO: {', '.join(EMAIL_RECIPIENTS)}\nDATE: {today}\n\n{digest}")
    log(f"Nightly digest saved → {out}")


# --- Scheduler ---

def main():
    import sys
    client = make_client()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--panopticon":
            run_panopticon()
            return
        if sys.argv[1] == "--tabula":
            run_tabula_rasa()
            return
        if sys.argv[1] == "--both":
            run_panopticon()
            run_tabula_rasa()
            return
        if sys.argv[1] == "--digest":
            compile_and_save_digest()
            return

    log("Scheduler starting...")
    log("  panopticon_mb  → every 6h (00:00, 06:00, 12:00, 18:00)")
    log("  tabula_rasa_mb → every 3h (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00)")
    log("  nightly digest → 21:00")

    # Panopticon: every 6 hours
    for h in ["00:00", "06:00", "12:00", "18:00"]:
        schedule.every().day.at(h).do(run_panopticon)

    # Tabula rasa: every 3 hours
    for h in ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]:
        schedule.every().day.at(h).do(run_tabula_rasa)

    # Nightly digest
    schedule.every().day.at("21:00").do(compile_and_save_digest)

    # Run both immediately on startup
    run_panopticon()
    run_tabula_rasa()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Long-running service that listens for Telegram approval messages
and executes approved plans via Claude Code.
"""

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

import requests

BOT_TOKEN = os.environ.get("CLAUDE_CODE_TELEGRAM_BOT_TOKEN") or os.environ["BOT_TOKEN"]
CHAT_ID = os.environ.get("MASTER_TELEGRAM_USER_ID") or os.environ["CHAT_ID"]
PLANS_FILE = os.path.expanduser("~/.openclaw/pending-plans.json")
TODO_FILE = os.path.expanduser("~/.openclaw/dashboard-todos.json")
COMPLETED_DIR = os.path.expanduser("~/.openclaw/completed")
LOG_FILE = os.path.expanduser("~/.openclaw/logs/listener.log")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

os.makedirs(COMPLETED_DIR, exist_ok=True)


def log(msg: str):
    """Append to log file with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(line, end="")


def send(text: str):
    """Send a Telegram message."""
    try:
        requests.post(f"{API_URL}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
    except Exception as e:
        log(f"Failed to send Telegram message: {e}")


def load_plans() -> list:
    """Load pending plans from file."""
    if not os.path.exists(PLANS_FILE):
        return []
    with open(PLANS_FILE) as f:
        return json.load(f)


def update_todo_status(todo_id: str, new_status: str):
    """Update a specific todo's status in the main todo file."""
    if not os.path.exists(TODO_FILE):
        return
    with open(TODO_FILE) as f:
        todos = json.load(f)

    for todo in todos:
        if str(todo.get("id")) == str(todo_id):
            todo["status"] = new_status
            if new_status == "completed":
                todo["completed_at"] = datetime.now(timezone.utc).isoformat()

    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, indent=2)


def archive_plan(plan: dict, result: str):
    """Save completed plan to archive."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_file = os.path.join(COMPLETED_DIR, f"{timestamp}_{plan.get('todo_id', 'unknown')}.json")
    plan["execution_result"] = result
    plan["executed_at"] = datetime.now(timezone.utc).isoformat()
    with open(archive_file, "w") as f:
        json.dump(plan, f, indent=2)


def execute_plan(plan: dict) -> str:
    """Execute a single plan using Claude Code with full permissions."""
    log(f"Executing plan: {plan.get('title')}")
    send(f"\u26a1 <b>Executing:</b> {plan.get('title')}...\nThis may take a few minutes.")

    todo_id = plan.get("todo_id", "")
    update_todo_status(todo_id, "executing")

    prompt = (
        f"Execute the following task plan. You have full permissions.\n\n"
        f"Title: {plan.get('title')}\n"
        f"Description: {plan.get('description')}\n"
        f"Files affected: {json.dumps(plan.get('files_affected', []))}\n"
        f"Commands to run: {json.dumps(plan.get('commands_to_run', []))}\n\n"
        f"After completing the task, provide a brief summary of what you did "
        f"and any issues encountered.\n\n"
        f"Then update the todo in {TODO_FILE}: set the item with id '{todo_id}' "
        f"to status 'completed' and set completed_at to the current ISO timestamp."
    )

    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "--print", prompt],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per task
            cwd=os.path.expanduser("~"),
        )

        output = result.stdout[-1000:] if result.stdout else "(no output)"
        if result.returncode == 0:
            update_todo_status(todo_id, "completed")
            archive_plan(plan, output)
            send(f"\u2705 <b>Completed:</b> {plan.get('title')}\n\n{output[-500:]}")
            log(f"Plan completed: {plan.get('title')}")
            return output
        else:
            error = result.stderr[-500:] if result.stderr else "(no error output)"
            update_todo_status(todo_id, "failed")
            archive_plan(plan, f"FAILED: {error}")
            send(f"\u274c <b>Failed:</b> {plan.get('title')}\n\nError: {error}")
            log(f"Plan failed: {plan.get('title')}: {error}")
            return f"FAILED: {error}"

    except subprocess.TimeoutExpired:
        update_todo_status(todo_id, "failed")
        send(f"\u23f0 <b>Timed out:</b> {plan.get('title')} (exceeded 10 minutes)")
        log(f"Plan timed out: {plan.get('title')}")
        return "TIMEOUT"
    except Exception as e:
        update_todo_status(todo_id, "failed")
        send(f"\U0001f4a5 <b>Error:</b> {plan.get('title')}\n\n{str(e)[:300]}")
        log(f"Plan error: {plan.get('title')}: {e}")
        return f"ERROR: {e}"


def handle_message(text: str):
    """Process a user message from Telegram."""
    text = text.strip().lower()
    plans = load_plans()

    if text == "status":
        if not plans:
            send("No pending plans. All clear! \u2728")
        else:
            msg = f"\U0001f4cb <b>{len(plans)} pending plan(s):</b>\n\n"
            for i, p in enumerate(plans, 1):
                msg += f"{i}. {p.get('title', 'Untitled')}\n"
            send(msg)

    elif text == "approve all":
        if not plans:
            send("No pending plans to approve.")
            return
        send(f"\U0001f680 Executing all {len(plans)} plan(s)...")
        for plan in plans:
            execute_plan(plan)
        # Clear plans file
        with open(PLANS_FILE, "w") as f:
            json.dump([], f)

    elif text.startswith("approve "):
        try:
            idx = int(text.split()[1]) - 1
        except (ValueError, IndexError):
            send("Usage: <code>approve &lt;number&gt;</code> (e.g., <code>approve 1</code>)")
            return

        if not plans or idx < 0 or idx >= len(plans):
            send(f"Invalid plan number. Available: 1-{len(plans)}")
            return

        plan = plans[idx]
        execute_plan(plan)

        # Remove executed plan from pending
        plans.pop(idx)
        with open(PLANS_FILE, "w") as f:
            json.dump(plans, f, indent=2)

    elif text.startswith("reject "):
        try:
            idx = int(text.split()[1]) - 1
        except (ValueError, IndexError):
            send("Usage: <code>reject &lt;number&gt;</code> (e.g., <code>reject 1</code>)")
            return

        if not plans or idx < 0 or idx >= len(plans):
            send(f"Invalid plan number. Available: 1-{len(plans)}")
            return

        plan = plans.pop(idx)
        update_todo_status(plan.get("todo_id", ""), "rejected")
        with open(PLANS_FILE, "w") as f:
            json.dump(plans, f, indent=2)
        send(f"\u23ed\ufe0f Rejected: {plan.get('title')}")

    elif text.startswith("details "):
        try:
            idx = int(text.split()[1]) - 1
        except (ValueError, IndexError):
            send("Usage: <code>details &lt;number&gt;</code>")
            return

        if not plans or idx < 0 or idx >= len(plans):
            send(f"Invalid plan number. Available: 1-{len(plans)}")
            return

        plan = plans[idx]
        msg = (
            f"\U0001f4dd <b>Full Details \u2014 Task #{idx+1}</b>\n\n"
            f"<b>Title:</b> {plan.get('title')}\n\n"
            f"<b>Description:</b>\n{plan.get('description')}\n\n"
            f"<b>Files:</b>\n" + "\n".join(f"  \u2022 {f}" for f in plan.get("files_affected", [])) + "\n\n"
            f"<b>Commands:</b>\n" + "\n".join(f"  <code>{c}</code>" for c in plan.get("commands_to_run", [])) + "\n\n"
            f"<b>Rollback:</b> {plan.get('rollback_plan', 'N/A')}"
        )
        send(msg)

    elif text == "help":
        send(
            "\U0001f916 <b>Commands:</b>\n\n"
            "<code>approve &lt;n&gt;</code> \u2014 Execute plan #n\n"
            "<code>approve all</code> \u2014 Execute all pending plans\n"
            "<code>reject &lt;n&gt;</code> \u2014 Skip plan #n\n"
            "<code>details &lt;n&gt;</code> \u2014 Show full plan details\n"
            "<code>status</code> \u2014 List pending plans\n"
            "<code>help</code> \u2014 Show this message"
        )

    else:
        send("Unknown command. Send <code>help</code> for available commands.")


def main():
    """Main polling loop."""
    log("Approval listener started")
    send("\U0001f7e2 <b>Claude Todo Runner</b> is online.\nSend <code>help</code> for commands.")

    offset = 0
    consecutive_errors = 0

    while True:
        try:
            resp = requests.get(
                f"{API_URL}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            resp.raise_for_status()
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})

                # Only respond to messages from our chat
                if str(msg.get("chat", {}).get("id")) != str(CHAT_ID):
                    continue

                text = msg.get("text", "")
                if text:
                    log(f"Received command: {text}")
                    handle_message(text)

            consecutive_errors = 0

        except requests.exceptions.Timeout:
            # Normal for long polling
            continue
        except Exception as e:
            consecutive_errors += 1
            log(f"Error in polling loop: {e}")
            traceback.print_exc()
            # Back off on repeated errors
            sleep_time = min(60 * consecutive_errors, 300)
            time.sleep(sleep_time)


if __name__ == "__main__":
    main()

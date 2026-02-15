#!/usr/bin/env python3
"""Send pending execution plans to Telegram for approval."""

import json
import os
import sys
import requests

BOT_TOKEN = os.environ.get("CLAUDE_CODE_TELEGRAM_BOT_TOKEN") or os.environ["BOT_TOKEN"]
CHAT_ID = os.environ.get("MASTER_TELEGRAM_USER_ID") or os.environ["CHAT_ID"]
PLANS_FILE = os.path.expanduser("~/.openclaw/pending-plans.json")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_message(text: str) -> bool:
    """Send a message via Telegram. Returns True on success."""
    resp = requests.post(API_URL, json={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    })
    if not resp.ok:
        print(f"Telegram API error: {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    return True


def main():
    if not os.path.exists(PLANS_FILE):
        print("No plans file found.")
        return

    with open(PLANS_FILE) as f:
        plans = json.load(f)

    if not plans:
        print("No plans to send.")
        return

    # Send summary header
    send_message(
        f"\U0001f916 <b>Claude Todo Runner</b>\n\n"
        f"Found <b>{len(plans)}</b> task(s) ready for execution.\n"
        f"Review each plan below and reply:\n"
        f"\u2022 <code>approve &lt;number&gt;</code> to execute\n"
        f"\u2022 <code>reject &lt;number&gt;</code> to skip\n"
        f"\u2022 <code>approve all</code> to execute everything\n"
        f"\u2022 <code>details &lt;number&gt;</code> for more info"
    )

    # Send each plan
    for i, plan in enumerate(plans, 1):
        risk_emoji = {"low": "\U0001f7e2", "medium": "\U0001f7e1", "high": "\U0001f534"}.get(
            plan.get("risk_level", "medium"), "\U0001f7e1"
        )

        msg = (
            f"<b>Task #{i}:</b> {plan.get('title', 'Untitled')}\n\n"
            f"<b>What:</b> {plan.get('description', 'No description')[:500]}\n\n"
            f"<b>Files:</b> {', '.join(plan.get('files_affected', ['unknown']))}\n"
            f"<b>Risk:</b> {risk_emoji} {plan.get('risk_level', 'unknown')}\n"
            f"<b>Duration:</b> {plan.get('estimated_duration', 'unknown')}\n\n"
            f"Reply <code>approve {i}</code> or <code>reject {i}</code>"
        )
        send_message(msg)

    print(f"Sent {len(plans)} plan notification(s) to Telegram.")


if __name__ == "__main__":
    main()

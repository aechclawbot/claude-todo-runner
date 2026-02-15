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
        "parse_mode": "Markdown",
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
        f"\U0001f916 *Claude Todo Runner*\n\n"
        f"Found *{len(plans)}* task(s) ready for execution.\n"
        f"Review each plan below and reply:\n"
        f"\u2022 `approve <number>` to execute\n"
        f"\u2022 `reject <number>` to skip\n"
        f"\u2022 `approve all` to execute everything\n"
        f"\u2022 `details <number>` for more info"
    )

    # Send each plan
    for i, plan in enumerate(plans, 1):
        risk_emoji = {"low": "\U0001f7e2", "medium": "\U0001f7e1", "high": "\U0001f534"}.get(
            plan.get("risk_level", "medium"), "\U0001f7e1"
        )

        msg = (
            f"*Task #{i}:* {plan.get('title', 'Untitled')}\n\n"
            f"*What:* {plan.get('description', 'No description')[:500]}\n\n"
            f"*Files:* {', '.join(plan.get('files_affected', ['unknown']))}\n"
            f"*Risk:* {risk_emoji} {plan.get('risk_level', 'unknown')}\n"
            f"*Duration:* {plan.get('estimated_duration', 'unknown')}\n\n"
            f"Reply `approve {i}` or `reject {i}`"
        )
        send_message(msg)

    print(f"Sent {len(plans)} plan notification(s) to Telegram.")


if __name__ == "__main__":
    main()

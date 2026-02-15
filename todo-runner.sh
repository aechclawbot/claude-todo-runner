#!/usr/bin/env bash
set -euo pipefail

# Load env vars — check common locations
[ -f "$HOME/.env" ] && source "$HOME/.env"
[ -f "$HOME/.openclaw/.env" ] && source "$HOME/.openclaw/.env"
[ -f "$HOME/openclaw/.env" ] && source "$HOME/openclaw/.env"

# Map to script-internal names
BOT_TOKEN="${CLAUDE_CODE_TELEGRAM_BOT_TOKEN}"
CHAT_ID="${MASTER_TELEGRAM_USER_ID}"
export BOT_TOKEN CHAT_ID

TODO_FILE="$HOME/.openclaw/dashboard-todos.json"
PLANS_FILE="$HOME/.openclaw/pending-plans.json"
LOG_DIR="$HOME/.openclaw/logs"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$LOG_DIR"

# Exit early if no todo file
if [ ! -f "$TODO_FILE" ]; then
  echo "[$TIMESTAMP] No todo file found at $TODO_FILE" >> "$LOG_DIR/runner.log"
  exit 0
fi

# Count pending items
PENDING=$(jq '[.[] | select(.status == "pending")] | length' "$TODO_FILE" 2>/dev/null || echo "0")

if [ "$PENDING" -eq 0 ]; then
  echo "[$TIMESTAMP] No pending todos found" >> "$LOG_DIR/runner.log"
  exit 0
fi

echo "[$TIMESTAMP] Found $PENDING pending todo(s). Generating plans..." >> "$LOG_DIR/runner.log"

# Update status to "planning" for all pending items
jq '[ .[] | if .status == "pending" then .status = "planning" else . end ]' "$TODO_FILE" > "${TODO_FILE}.tmp" && mv "${TODO_FILE}.tmp" "$TODO_FILE"

# Generate execution plans using Claude Code
# Claude Code reads the todos and outputs a structured plan
claude --print --output-format json \
  "You are a task planning assistant. Read the file $TODO_FILE and find all items with status 'planning'.

For EACH such item, produce a detailed execution plan. Your output must be ONLY a valid JSON array written to $PLANS_FILE with this structure:

[
  {
    \"todo_id\": \"<id from the todo>\",
    \"title\": \"<title from the todo>\",
    \"description\": \"<what you will do, step by step>\",
    \"files_affected\": [\"list\", \"of\", \"file\", \"paths\"],
    \"risk_level\": \"low | medium | high\",
    \"estimated_duration\": \"e.g. 2 minutes\",
    \"commands_to_run\": [\"any shell commands you plan to run\"],
    \"rollback_plan\": \"how to undo if something goes wrong\"
  }
]

Be specific and concrete. Reference actual file paths. Do NOT execute anything — only plan.
Write the JSON array to $PLANS_FILE." \
  >> "$LOG_DIR/runner.log" 2>&1

# Verify plans file was created
if [ ! -f "$PLANS_FILE" ]; then
  echo "[$TIMESTAMP] ERROR: Plans file was not created" >> "$LOG_DIR/runner.log"
  # Reset status back to pending
  jq '[ .[] | if .status == "planning" then .status = "pending" else . end ]' "$TODO_FILE" > "${TODO_FILE}.tmp" && mv "${TODO_FILE}.tmp" "$TODO_FILE"
  exit 1
fi

# Update status to "awaiting_approval"
jq '[ .[] | if .status == "planning" then .status = "awaiting_approval" else . end ]' "$TODO_FILE" > "${TODO_FILE}.tmp" && mv "${TODO_FILE}.tmp" "$TODO_FILE"

# Send notifications via Telegram
python3 "$HOME/.openclaw/notify.py" >> "$LOG_DIR/runner.log" 2>&1

echo "[$TIMESTAMP] Plans sent for approval via Telegram" >> "$LOG_DIR/runner.log"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
LOG_DIR="$OPENCLAW_DIR/logs"

echo "=== Claude Todo Runner — Installer ==="
echo ""

# Step 1: Create directories
echo "[1/8] Creating directories..."
mkdir -p "$OPENCLAW_DIR"/{logs,completed}

# Step 2: Create dashboard-todos.json if missing
echo "[2/8] Checking dashboard-todos.json..."
if [ ! -f "$OPENCLAW_DIR/dashboard-todos.json" ]; then
  echo '[]' > "$OPENCLAW_DIR/dashboard-todos.json"
  echo "  Created empty dashboard-todos.json"
else
  echo "  Already exists — not overwriting"
fi

# Step 3: Install Python dependencies
echo "[3/8] Installing Python dependencies..."
pip3 install --user requests --quiet 2>/dev/null || pip3 install --user --break-system-packages requests

# Step 4: Copy scripts
echo "[4/8] Installing scripts to $OPENCLAW_DIR..."
cp "$SCRIPT_DIR/todo-runner.sh" "$OPENCLAW_DIR/todo-runner.sh"
cp "$SCRIPT_DIR/notify.py" "$OPENCLAW_DIR/notify.py"
cp "$SCRIPT_DIR/approval-listener.py" "$OPENCLAW_DIR/approval-listener.py"
chmod +x "$OPENCLAW_DIR/todo-runner.sh"
echo "  Installed: todo-runner.sh, notify.py, approval-listener.py"

# Step 5: Locate environment variables
echo "[5/8] Locating environment variables..."
ENV_FILE=""
for f in "$HOME/.env" "$OPENCLAW_DIR/.env" "$HOME/openclaw/.env"; do
  if [ -f "$f" ] && grep -q "CLAUDE_CODE_TELEGRAM_BOT_TOKEN" "$f" 2>/dev/null; then
    ENV_FILE="$f"
    break
  fi
done

if [ -z "$ENV_FILE" ]; then
  echo "  ERROR: Could not find CLAUDE_CODE_TELEGRAM_BOT_TOKEN in any .env file"
  echo "  Add it to $OPENCLAW_DIR/.env and re-run this script"
  exit 1
fi
echo "  Found env at: $ENV_FILE"
source "$ENV_FILE"

# Check for required vars
if [ -z "${CLAUDE_CODE_TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "  ERROR: CLAUDE_CODE_TELEGRAM_BOT_TOKEN is not set"
  exit 1
fi
if [ -z "${MASTER_TELEGRAM_USER_ID:-}" ]; then
  echo "  ERROR: MASTER_TELEGRAM_USER_ID is not set"
  echo "  Add MASTER_TELEGRAM_USER_ID=<your-telegram-chat-id> to $ENV_FILE"
  exit 1
fi

# Step 6: Validate Telegram connection
echo "[6/8] Validating Telegram connection..."
BOT_RESPONSE=$(curl -s "https://api.telegram.org/bot${CLAUDE_CODE_TELEGRAM_BOT_TOKEN}/getMe")
BOT_OK=$(echo "$BOT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "False")
if [ "$BOT_OK" != "True" ]; then
  echo "  ERROR: Telegram bot validation failed: $BOT_RESPONSE"
  exit 1
fi
BOT_USERNAME=$(echo "$BOT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['username'])" 2>/dev/null)
echo "  Bot validated: @$BOT_USERNAME"

# Send test message
curl -s -X POST "https://api.telegram.org/bot${CLAUDE_CODE_TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${MASTER_TELEGRAM_USER_ID}\", \"text\": \"\u2705 Claude Todo Runner connected successfully! Send 'help' for commands.\"}" > /dev/null
echo "  Test message sent to Telegram"

# Step 7: Install persistent listener service
echo "[7/8] Installing listener service..."
if [[ "$(uname)" == "Darwin" ]]; then
  # macOS — launchd
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST_FILE="$PLIST_DIR/com.openclaw.claude-todo-listener.plist"
  mkdir -p "$PLIST_DIR"

  cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.claude-todo-listener</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which python3)</string>
        <string>${OPENCLAW_DIR}/approval-listener.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CLAUDE_CODE_TELEGRAM_BOT_TOKEN</key>
        <string>${CLAUDE_CODE_TELEGRAM_BOT_TOKEN}</string>
        <key>MASTER_TELEGRAM_USER_ID</key>
        <string>${MASTER_TELEGRAM_USER_ID}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/listener-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/listener-stderr.log</string>
</dict>
</plist>
PLIST

  # Unload if already loaded, then load
  launchctl unload "$PLIST_FILE" 2>/dev/null || true
  launchctl load "$PLIST_FILE"
  echo "  Installed launchd service: com.openclaw.claude-todo-listener"
else
  # Linux — systemd
  SYSTEMD_DIR="$HOME/.config/systemd/user"
  SERVICE_FILE="$SYSTEMD_DIR/claude-todo-listener.service"
  mkdir -p "$SYSTEMD_DIR"

  cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=Claude Todo Runner — Telegram Approval Listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-${HOME}/.env
EnvironmentFile=-${OPENCLAW_DIR}/.env
EnvironmentFile=-${HOME}/openclaw/.env
ExecStart=/usr/bin/python3 ${OPENCLAW_DIR}/approval-listener.py
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/listener-stdout.log
StandardError=append:${LOG_DIR}/listener-stderr.log

[Install]
WantedBy=default.target
SERVICE

  systemctl --user daemon-reload
  systemctl --user enable claude-todo-listener
  systemctl --user start claude-todo-listener
  loginctl enable-linger "$(whoami)" 2>/dev/null || true
  echo "  Installed systemd service: claude-todo-listener"
fi

# Step 8: Install cron job
echo "[8/8] Installing cron job..."
CRON_LINE="0 * * * * /bin/bash \$HOME/.openclaw/todo-runner.sh >> \$HOME/.openclaw/logs/cron.log 2>&1"
if crontab -l 2>/dev/null | grep -q "todo-runner.sh"; then
  echo "  Cron job already exists — skipping"
else
  (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
  echo "  Hourly cron job installed"
fi

echo ""
echo "=== Installation complete! ==="
echo ""
echo "The approval listener is now running. Check Telegram for the test message."
echo "Pending todos will be checked every hour on the hour."
echo ""
echo "Manual test: bash ~/.openclaw/todo-runner.sh"
echo "Logs: ~/.openclaw/logs/"

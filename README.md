# Claude Todo Runner

Autonomous task execution system that monitors `~/.openclaw/dashboard-todos.json`, generates execution plans via Claude Code, sends them to Telegram for approval, and executes approved plans with full permissions.

## How It Works

```
Cron (hourly) → Reads todos → Claude Code plans → Telegram notification → User approves → Claude Code executes → Result sent to Telegram
```

1. **Cron job** checks for pending todos every hour
2. **Claude Code** generates a detailed execution plan for each
3. **Plans are sent to Telegram** for review
4. **User approves/rejects** via Telegram commands
5. **Approved plans execute** via Claude Code with `--dangerously-skip-permissions`
6. **Results are reported** back to Telegram

## Prerequisites

- [Claude Code CLI](https://claude.ai/code) — installed and authenticated
- Python 3.8+
- `jq` — `brew install jq` (macOS) or `sudo apt install jq` (Linux)
- `requests` — `pip3 install requests`
- A Telegram Bot token (via [@BotFather](https://t.me/BotFather))

## Setup

### 1. Set environment variables

Add to your `.env` file (e.g. `~/.openclaw/.env`):

```bash
CLAUDE_CODE_TELEGRAM_BOT_TOKEN=your-bot-token-here
MASTER_TELEGRAM_USER_ID=your-telegram-chat-id
```

### 2. Run the installer

```bash
./install.sh
```

This will:
- Create required directories (`~/.openclaw/logs/`, `~/.openclaw/completed/`)
- Install Python dependencies
- Copy scripts to `~/.openclaw/`
- Validate Telegram connection
- Install the approval listener service (launchd on macOS, systemd on Linux)
- Install the hourly cron job

### 3. Verify

You should receive a test message in Telegram confirming the connection. Send `help` to the bot to see available commands.

## Telegram Commands

| Command | Action |
|---------|--------|
| `approve <n>` | Execute plan #n |
| `approve all` | Execute all pending plans |
| `reject <n>` | Skip and mark plan #n as rejected |
| `details <n>` | Show full execution plan for #n |
| `status` | List all pending plans |
| `help` | Show available commands |

## Todo JSON Schema

Todos in `~/.openclaw/dashboard-todos.json`:

```json
[
  {
    "id": "unique-id",
    "title": "Short descriptive title",
    "description": "Detailed description of what needs to be done",
    "status": "pending",
    "priority": "high | medium | low",
    "context": "Relevant context: project path, tech stack, related files",
    "created_at": "2026-01-01T00:00:00Z",
    "completed_at": null
  }
]
```

Valid statuses: `pending`, `planning`, `awaiting_approval`, `approved`, `executing`, `completed`, `failed`, `rejected`.

## File Structure

```
~/.openclaw/
├── dashboard-todos.json          # The todo list
├── pending-plans.json            # Generated plans awaiting approval
├── todo-runner.sh                # Main hourly runner script
├── notify.py                     # Sends plans to Telegram
├── approval-listener.py          # Listens for Telegram replies, triggers execution
├── logs/
│   ├── runner.log                # Runner execution logs
│   ├── listener.log              # Listener logs
│   └── cron.log                  # Cron output
└── completed/                    # Archive of completed plans
```

## Security

- Only messages from `MASTER_TELEGRAM_USER_ID` are processed
- Telegram approval is the single gate before `--dangerously-skip-permissions` execution
- All actions are logged to `~/.openclaw/logs/`
- Completed plans are archived in `~/.openclaw/completed/`
- `.env` file should be `chmod 600`

## License

MIT

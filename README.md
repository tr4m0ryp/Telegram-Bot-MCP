# Telegram Bot MCP

MCP server for Telegram: send messages, broadcast to known users, and inspect chats and the
bot from any MCP client. Ships two server variants plus an optional bot runtime and a
production webhook server.

- **Smithery server** (`telegram_bot_mcp.server`) — send-only tool; each MCP session supplies
  its own bot token and chat ID, so one deployment serves many users. This is what Smithery
  runs (`smithery.yaml`, `[tool.smithery]` in `pyproject.toml`).
- **Full server** (`telegram_bot_mcp.mcp`) — server-side `TELEGRAM_BOT_TOKEN`; tools,
  resources, and prompts listed below.
- **Bot runtime** (`telegram_bot_mcp.bot`) — polling bot with `/start`, `/help`, `/info`,
  `/stats`, `/clear` and context-aware replies.
- **Webhook server** (`telegram_bot_mcp.webhook`) — FastAPI app for production webhook
  deployments, with health/status/admin endpoints.

## Project structure

```
src/telegram_bot_mcp/
├── __init__.py       # public root: create_server
├── server.py         # Smithery entry point (session-scoped config)
├── config.py         # environment-backed configuration
├── storage.py        # shared in-memory stores
├── mcp/              # full MCP server: app, tools, resources, prompts
├── bot/              # bot runtime: runner, commands, chat, replies
├── webhook/          # FastAPI server: app, telegram, status, admin
└── cli/              # unified launcher: args, preflight, run
scripts/
└── client.py         # example MCP client
```

## Installation

```bash
uv sync              # Smithery server only
uv sync --extra full # everything (bot, webhook, full MCP server)
```

Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` (from
[@BotFather](https://t.me/botfather)). The Smithery server needs no `.env`; credentials come
from the session config.

## Usage

```bash
telegram-bot-mcp --check-config   # validate configuration and dependencies
telegram-bot-mcp                  # polling bot (default)
telegram-bot-mcp --webhook        # FastAPI webhook server
telegram-bot-mcp --mcp            # full MCP server only (streamable HTTP)
telegram-bot-mcp --combined       # webhook + MCP server

# Smithery development / production
uv run dev
uv run start
```

The full MCP server can also be run directly:

```bash
python -m telegram_bot_mcp.mcp --host 0.0.0.0 --port 8001
```

## MCP surface (full server)

Tools:

- `send_telegram_message` — send a message to a chat
- `get_chat_info` — chat metadata
- `broadcast_message` — send to all known users
- `get_bot_info` — bot identity and capabilities

Resources: `telegram://messages/recent/{limit}`, `telegram://users/active`,
`telegram://stats/summary`. Prompts: `create_welcome_message`, `generate_help_content`.

The Smithery variant exposes `send_telegram_message` (text only, configured chat), the
`telegram://about` resource, and the `telegram_message` prompt.

## Configuration

| Variable               | Default   | Purpose                              |
| ---------------------- | --------- | ------------------------------------ |
| `TELEGRAM_BOT_TOKEN`   | required  | Bot API token                        |
| `TELEGRAM_WEBHOOK_URL` | unset     | Enables webhook mode                 |
| `WEBHOOK_SECRET`       | unset     | Secret for webhook registration      |
| `SERVER_HOST`          | `0.0.0.0` | Webhook/MCP bind address             |
| `SERVER_PORT`          | `8000`    | Webhook server port                  |
| `MCP_PORT`             | `8001`    | Full MCP server port                 |
| `DEBUG`                | `false`   | Uvicorn reload                       |
| `LOG_LEVEL`            | `INFO`    | Logging level                        |

## Webhook mode

In webhook mode the server registers `TELEGRAM_WEBHOOK_URL` with Telegram on startup (using
`WEBHOOK_SECRET`) — no manual step needed. Incoming updates on `POST /webhook` are rejected
unless they carry the matching secret header, so a leaked URL alone cannot drive the bot.
Setting a webhook (on startup or via `/admin/set_webhook`) requires a secret; there is no
insecure default.

Endpoints: `GET /` (info), `GET /health`, `POST /webhook`, `GET /bot/info`,
`GET /mcp/status`, `GET /stats`, `POST /admin/set_webhook`, `DELETE /admin/delete_webhook`.

Note: user sessions and stats live in an in-memory store scoped to one process. In
`--combined` mode the MCP server runs as a separate process, so its `broadcast_message` and
`telegram://users/active` see only its own activity. Back the store with a database
(`storage.py`) for cross-process state.

## Docker

```bash
docker build -t telegram-bot-mcp .
docker run -p 8081:8081 telegram-bot-mcp
```

The container serves the Smithery MCP server over streamable HTTP on port 8081.

## License

MIT, per the upstream project ([SmartManoj/Telegram-Bot-MCP](https://github.com/SmartManoj/Telegram-Bot-MCP)).

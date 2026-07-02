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
- **Launch gate** (`telegram_bot_mcp.gate`) — the deployable approval service described
  below: outbound MCP tools, an inbound operator-tap webhook, and a launch-token endpoint.

## Project structure

```
src/telegram_bot_mcp/
├── __init__.py       # public root: create_server
├── server.py         # Smithery entry point (session-scoped config)
├── config.py         # environment-backed configuration
├── storage.py        # shared in-memory stores
├── db/               # shared asyncpg pool + schema.sql (gate)
├── mcp/              # full MCP server: app, tools, resources, prompts
├── bot/              # bot runtime: runner, commands, chat, replies
├── webhook/          # FastAPI server: app, telegram, status, admin
├── approval/         # launch-gate: pending-nonce store + callback codec
├── tokens/           # launch-gate: token mint/validate + internal endpoint
├── gate/             # launch-gate service: server, tools, auth, webhook, app
└── cli/              # unified launcher: args, preflight, run
deploy/
├── deploy-cloudrun.sh   # Cloud Run deploy
└── set-webhook.sh       # register the Telegram webhook
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

## Launch gate

A deployable service that puts a real human gate in front of launching an autonomous run.
Two directions of Telegram traffic are split deliberately:

- **Outbound (Claude → operator).** The routine calls MCP tools at `/mcp` to notify the
  operator and to *ask* for launch approval. This is the only Telegram-facing surface Claude
  can reach.
- **Inbound (operator tap → token).** The operator's Approve tap goes from Telegram to this
  service's `/telegram/webhook`, never to Claude. The webhook verifies the operator, then
  mints a one-time launch token. Claude is not in this path.

**Claude/the routine can request approval but cannot grant it.** Only the configured operator
can approve, and granting mints the token outside Claude's reach — so the routine is
structurally unable to approve its own launches.

### MCP tools (outbound, bearer-guarded)

- `send_notification(text)` — plain ping to the operator chat only.
- `request_launch_approval(engagementId, companyName, scopeHosts[])` — sends a message that
  **shows the scope** with inline Approve / Cancel buttons; returns `{sent, messageId}`. The
  button callback carries the engagement id and a random nonce — never a token. No tool mints
  a token, approves, or launches.

### Operator tap (inbound, Claude-free)

`POST /telegram/webhook` handles button taps. It honors a tap only if `from.id` equals
`OPERATOR_TELEGRAM_USER_ID` (everyone else is ignored), matches the nonce to a still-pending
approval (defeating replays/stale taps), and on **Approve** looks up the engagement's signed
Rules-of-Engagement hash and mints a token bound to `engagement_id` + that RoE hash. The
message is edited to "Approved — launch authorized"; the token is never shown. **Cancel**
mints nothing.

### Token endpoint (internal only)

`POST /launch-tokens` mints and stores a token in the `launch_token` table. It is reachable
only by this service's webhook (same-process minting by default; guarded by
`TOKEN_MINT_SECRET` if exposed out-of-process) — never by the MCP bearer, never by anything
the routine holds. Tokens are opaque, single-use, time-limited, and bound to engagement +
RoE hash. The downstream run tool validates and consumes them (`tokens.validate_and_consume`).

### Run and deploy

```bash
uv sync --extra full
python -m telegram_bot_mcp.gate            # serve locally on $PORT (default 8080)

bash deploy/deploy-cloudrun.sh             # deploy to Cloud Run (see script header)
bash deploy/set-webhook.sh                 # register the Telegram webhook
```

MCP auth mirrors enrichment-mcp's single-swap seam (`gate/auth.py`): static bearer
(`MCP_BEARER_TOKEN`) works for Claude Code today. claude.ai custom connectors require OAuth
(authorization-server metadata + Dynamic Client Registration); that is a one-line swap —
set `MCP_OAUTH_PROVIDER` and mount a FastMCP-v3 auth provider — and is deferred until then.

## Docker

The repository ships two images:

```bash
# Launch gate (Cloud Run deployable): /mcp + /telegram/webhook + /launch-tokens
docker build -t telegram-launch-gate .
docker run -p 8080:8080 --env-file .env telegram-launch-gate

# Smithery send-only server (optional standalone)
docker build -f Dockerfile.smithery -t telegram-bot-mcp .
docker run -p 8081:8081 telegram-bot-mcp
```

## License

MIT, per the upstream project ([SmartManoj/Telegram-Bot-MCP](https://github.com/SmartManoj/Telegram-Bot-MCP)).

# Telegram Bot MCP: Telegram messaging for MCP clients, with a human-in-the-loop launch gate

**A Telegram MCP server that lets any MCP client -- Claude Code, claude.ai -- send messages
and manage a bot, plus a deployable launch-approval gate that keeps a human in the loop before
an autonomous run starts.** The MCP tools can *ask* for approval; only the operator's Telegram
tap can *grant* it, minting a scope-bound, single-use token the model never sees. Built on
FastMCP over Streamable HTTP, a FastAPI webhook, and Postgres.

## Project Overview

Autonomous agents increasingly take actions that a human should sign off on before they
happen -- sending outreach, notifying an operator, or launching a high-consequence job. Two
problems follow. First, an agent needs a simple, reliable channel to reach a person: Telegram.
Second, and harder, when an action is dangerous, the agent must be **structurally unable to
authorize itself**. If the same routine that requests a launch can also grant it, the human
gate is theatre.

This project is an MCP (Model Context Protocol) server for Telegram that solves both. The base
server lets any MCP client send messages and manage a Telegram bot. On top of it sits a
**launch-approval gate**: a single deployable service that splits Telegram traffic into two
deliberately separated directions. Outbound, the routine calls MCP tools to notify the
operator and to *ask* for approval. Inbound, the operator's Approve tap arrives at the
service's own webhook -- never at the model -- and only that tap mints a one-time, scope-bound
launch token. The model can ask; only the human can grant.

The design target is the launch step of an autonomous black-box run: the routine requests a
launch showing the **signed scope**, the operator approves on their phone, and a single-use
token bound to that engagement's signed Rules-of-Engagement (RoE) is minted outside the model's
reach. It is built on the same stack as its sibling services (FastMCP over Streamable HTTP, a
FastAPI webhook, asyncpg + Postgres, Docker on Cloud Run), and is forked from
`SmartManoj/Telegram-Bot-MCP`.

## How It Works

The launch gate is one service exposing three surfaces on one port, each with a different trust
level:

1. **Outbound MCP tools** (`/mcp`) -- the only Telegram-facing surface the routine reaches,
   guarded by a bearer token. `send_notification` pings the operator; `request_launch_approval`
   sends an Approve/Cancel message. **Neither mints a token, approves, or launches.**
2. **Inbound operator webhook** (`/telegram/webhook`) -- receives the button tap. It is
   **Claude-free**: the model is never in this path. It verifies the operator, then mints.
3. **Token store** (`launch_token` table, optional `/launch-tokens`) -- holds opaque,
   single-use, time-limited tokens bound to engagement + RoE hash. The token value **never
   returns through the model**.

The separation is the whole point: the routine can *request* approval, but granting happens on
a path it cannot reach.

```
        ask (model may do this)                     grant (only the operator may do this)
                                                                                             
  Routine / MCP client                                          Operator's Telegram
        |                                                                |
        | request_launch_approval(engagementId, ...)                     | taps Approve
        v                                                                v
  +-------------+   bearer    +--------------------------------------------------+
  |    /mcp     |------------>|                 Launch Gate                       |
  +-------------+             |                (single service)                  |
                             |                                                  |
                             |   /telegram/webhook  --(operator id + nonce ok)--+
                             |            |                                     |
                             |            | approve + mint  (one transaction)   |
                             |            v                                     |
                             |     [ launch_token ]  single-use, RoE-bound      |
                             +--------------------------------------------------+
                                             |
                                             | out-of-band (never via the model)
                                             v
                                   downstream run tool redeems + consumes
```

**Approve the scope, not a label.** `request_launch_approval` takes a company name and scope
hosts, but the message displays the engagement's **signed** scope looked up from the database,
not those arguments -- and flags any mismatch. The operator consents to the verified scope.

**Snapshot binding.** The RoE hash is snapshotted when the request is sent. Approve mints
against that snapshot in a single transaction, so re-signing the engagement afterward cannot
change what an already-shown request authorizes, and a tap can never leave an
approved-but-tokenless dead state.

**Fail closed.** A missing `WEBHOOK_SECRET` refuses all webhook traffic (a forged body could
otherwise spoof the operator id); a missing `MCP_BEARER_TOKEN` refuses to start unless
unauthenticated mode is explicitly opted into; `/launch-tokens` is only mounted when
`TOKEN_MINT_SECRET` is set, so by default it is not attack surface at all.

## Server Variants

The repository ships several entry points from one package. The launch gate is the deployable
service; the others are the general-purpose Telegram MCP inherited and refactored from upstream.

| Variant | Module | Purpose | Auth model |
| --- | --- | --- | --- |
| **Launch gate** | `telegram_bot_mcp.gate` | Notify + request approval + operator tap + tokens | MCP bearer; operator id on the tap |
| **Full MCP server** | `telegram_bot_mcp.mcp` | Send, broadcast, inspect chats/bot | Server-side bot token |
| **Bot runtime** | `telegram_bot_mcp.bot` | Polling bot: `/start /help /info /stats /clear` | Server-side bot token |
| **Webhook server** | `telegram_bot_mcp.webhook` | Production webhook with health/status/admin | Telegram secret header |
| **Smithery server** | `telegram_bot_mcp.server` | Send-only tool, per-session credentials | Per-session config |

## Quick Start

```bash
uv sync                 # Smithery send-only server only
uv sync --extra full    # everything: gate, full server, bot, webhook
cp .env.example .env     # then fill in the values
```

<details>
<summary><b>Launch gate (the deployable service)</b></summary>

Requires the `full` extra and a Postgres DSN. Minimum configuration:

```bash
TELEGRAM_BOT_TOKEN=...              # from @BotFather
OPERATOR_TELEGRAM_USER_ID=...       # from @userinfobot -- the only tapper honored
OPERATOR_CHAT_ID=...                # where notifications and approvals are sent
MCP_BEARER_TOKEN=$(openssl rand -hex 32)
WEBHOOK_SECRET=$(openssl rand -hex 32)
DATABASE_URL=...                    # a postgresql:// DSN (reuse the enrichment Postgres)
```

Run locally (serves `/mcp`, `/telegram/webhook`, `/health` on `$PORT`, default 8080):

```bash
python -m telegram_bot_mcp.gate
```
</details>

<details>
<summary><b>Full server / bot / webhook (general Telegram MCP)</b></summary>

```bash
telegram-bot-mcp --check-config   # validate configuration and dependencies
telegram-bot-mcp                  # polling bot (default)
telegram-bot-mcp --webhook        # FastAPI webhook server
telegram-bot-mcp --mcp            # full MCP server only (Streamable HTTP)
telegram-bot-mcp --combined       # webhook + MCP server
```
</details>

<details>
<summary><b>Smithery send-only server</b></summary>

```bash
uv run dev      # development
uv run start    # production (Streamable HTTP)
```

Credentials are supplied per MCP session, so one deployment serves many users and no `.env`
is needed.
</details>

## Usage

The launch-gate happy path, end to end:

```
Step 1  Deploy the service and register its Telegram webhook.
Step 2  The routine calls request_launch_approval("ENG-42", "Acme", ["app.acme.com"]).
Step 3  The operator receives a message showing the SIGNED scope + Approve / Cancel buttons.
Step 4  The operator taps Approve -- a single-use token bound to ENG-42 + its RoE hash is minted.
Step 5  The downstream run tool redeems the token (claim_token_for_engagement) and launches.
```

Deploy to Cloud Run and register the webhook:

```bash
bash deploy/deploy-cloudrun.sh     # gcloud run deploy --source . (see the script header)
bash deploy/set-webhook.sh         # points Telegram at PUBLIC_URL/telegram/webhook
```

## Technical Details

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | required | Bot API token (from @BotFather) |
| `OPERATOR_TELEGRAM_USER_ID` | unset | The only Telegram user whose taps are honored |
| `OPERATOR_CHAT_ID` | unset | Chat that receives notifications and approvals |
| `MCP_BEARER_TOKEN` | unset | Guards `/mcp` (Claude Code) |
| `MCP_OAUTH_PROVIDER` | empty | Selects an OAuth provider for claude.ai (single-swap seam) |
| `MCP_ALLOW_UNAUTHENTICATED` | `false` | Explicit opt-in for an open `/mcp` (local dev only) |
| `WEBHOOK_SECRET` | unset | Telegram secret header; the webhook fails closed without it |
| `TOKEN_MINT_SECRET` | unset | Guards `/launch-tokens`; unset = route not mounted |
| `DATABASE_URL` | unset | Postgres DSN for the token store |
| `PUBLIC_URL` / `TELEGRAM_WEBHOOK_URL` | unset | Public origin / webhook registration target |
| `SERVER_HOST` / `SERVER_PORT` / `MCP_PORT` | `0.0.0.0` / `8000` / `8001` | Bind settings |
| `DEBUG` / `LOG_LEVEL` | `false` / `INFO` | Diagnostics |

### MCP surface

| Server | Tools | Resources / Prompts |
| --- | --- | --- |
| Launch gate | `send_notification`, `request_launch_approval` | -- |
| Full server | `send_telegram_message`, `get_chat_info`, `broadcast_message`, `get_bot_info` | `telegram://messages/recent/{limit}`, `telegram://users/active`, `telegram://stats/summary`; `create_welcome_message`, `generate_help_content` |
| Smithery | `send_telegram_message` | `telegram://about`; `telegram_message` |

### Launch-token contract

| Property | Enforcement |
| --- | --- |
| Opaque | `secrets.token_urlsafe(32)`; value never returned through the model |
| Single-use | `SELECT ... FOR UPDATE` + `UPDATE ... WHERE used_at IS NULL` in one transaction |
| Time-limited | `expires_at` checked (tz-aware) on redemption |
| Scope-bound | Bound to `engagement_id` + the signed `roe_hash`, both checked on redemption |
| Replay-safe | Approval nonce matched against a still-pending, non-expired row |

Redemption is `tokens.validate_and_consume(token, engagement_id, roe_hash)` for an out-of-band
delivered value, or `tokens.claim_token_for_engagement(engagement_id, roe_hash)` for a
downstream tool that shares the database.

### Endpoints

- **Gate**: `GET /health`, `POST /mcp` (bearer), `POST /telegram/webhook`, `POST /launch-tokens`
  (only when `TOKEN_MINT_SECRET` is set).
- **Webhook server**: `GET /`, `GET /health`, `POST /webhook`, `GET /bot/info`,
  `GET /mcp/status`, `GET /stats`, `POST /admin/set_webhook`, `DELETE /admin/delete_webhook`.

### Project structure

```
src/telegram_bot_mcp/
  server.py         Smithery entry point (session-scoped config)
  config.py         environment-backed configuration
  storage.py        shared in-memory stores (full server / bot)
  db/               shared asyncpg pool + schema.sql (gate)
  mcp/              full MCP server: app, tools, resources, prompts
  bot/              polling runtime: runner, commands, chat, replies
  webhook/          FastAPI server: app, telegram, status, admin
  approval/         pending-nonce store + callback codec (gate)
  tokens/           token mint/validate + internal endpoint (gate)
  gate/             launch gate: server, tools, auth, webhook, app
  cli/              unified launcher
deploy/
  deploy-cloudrun.sh  Cloud Run deploy
  set-webhook.sh      register the Telegram webhook
```

### Docker

```bash
docker build -t telegram-launch-gate .                     # the gate (Cloud Run image)
docker run -p 8080:8080 --env-file .env telegram-launch-gate

docker build -f Dockerfile.smithery -t telegram-bot-mcp .  # the send-only server
```

## Roadmap

- **claude.ai custom connector (OAuth).** The MCP auth is isolated to a single swap
  (`gate/auth.py`), mirroring the enrichment MCP's `MCP_OAUTH_PROVIDER` dispatch. Static bearer
  works for Claude Code today; enabling a FastMCP-v3 WorkOS provider adds the authorization-
  server metadata discovery + Dynamic Client Registration that claude.ai's web app requires.
- **Durable state for the general bot.** The full server and bot keep sessions and stats in a
  process-local in-memory store; back it with the same Postgres for cross-process state.
- **Direct token delivery.** An optional server-to-server push of the minted token to the run
  control-plane, so a downstream that does not share the database can still receive it without
  the model ever seeing the value.

## Disclaimer

The launch gate is intended to front an authorized, autonomous security-testing workflow: its
purpose is to keep a human in the loop before a run starts. It authorizes nothing on its own
and mints a token only in response to an explicit operator tap, bound to a signed scope. Deploy
it against infrastructure you are authorized to test, keep `WEBHOOK_SECRET` and
`MCP_BEARER_TOKEN` set (the service fails closed without them), and treat the `DATABASE_URL`
and bot token as secrets. The in-memory stores in the general bot variants are volatile and not
intended for production persistence.

## License

MIT, per the upstream project ([SmartManoj/Telegram-Bot-MCP](https://github.com/SmartManoj/Telegram-Bot-MCP)).

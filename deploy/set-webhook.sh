#!/usr/bin/env bash
# Register (or re-register) the Telegram webhook to point at this service.
# Restricts updates to callback_query — the gate only reacts to button taps.
#
#   TELEGRAM_BOT_TOKEN=... WEBHOOK_SECRET=... PUBLIC_URL=https://telegram-mcp.frogbytes.xyz \
#     bash deploy/set-webhook.sh
set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?set TELEGRAM_BOT_TOKEN}"
: "${WEBHOOK_SECRET:?set WEBHOOK_SECRET}"
PUBLIC_URL="${PUBLIC_URL:?set PUBLIC_URL}"
WEBHOOK_URL="${WEBHOOK_URL:-${PUBLIC_URL}/telegram/webhook}"

curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    --data-urlencode "url=${WEBHOOK_URL}" \
    --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
    --data-urlencode 'allowed_updates=["callback_query"]' \
    -w '\nHTTP %{http_code}\n'

echo "Verify:"
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" -w '\n'

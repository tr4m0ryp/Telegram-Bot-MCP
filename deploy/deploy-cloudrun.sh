#!/usr/bin/env bash
# Deploy the Telegram Launch Gate to GCP Cloud Run.
#
# Mirrors enrichment-mcp: --source build, --allow-unauthenticated (the app-layer
# MCP bearer is the real gate; claude.ai carries no Google identity), secrets via
# Secret Manager injected as env vars, --max-instances 1 (in-memory-free, but the
# single instance also keeps the pending-approval flow simple).
#
# Prereqs: gcloud auth, the secrets below created (see the "create secrets" block),
# and DATABASE_URL pointing at the enrichment Postgres.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-enrichment-mcp-84b2d1}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-telegram-launch-gate}"

# Public origin the Telegram webhook is registered against (frogbytes tunnel).
PUBLIC_URL="${PUBLIC_URL:-https://telegram-mcp.frogbytes.xyz}"
WEBHOOK_URL="${WEBHOOK_URL:-${PUBLIC_URL}/telegram/webhook}"

# Non-secret operator identity (safe as plain env vars).
OPERATOR_TELEGRAM_USER_ID="${OPERATOR_TELEGRAM_USER_ID:?set OPERATOR_TELEGRAM_USER_ID}"
OPERATOR_CHAT_ID="${OPERATOR_CHAT_ID:?set OPERATOR_CHAT_ID}"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com

# --- create secrets once (idempotent-ish; skip if they exist) ----------------
# printf '%s' "$TELEGRAM_BOT_TOKEN" | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=-
# printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create MCP_BEARER_TOKEN --data-file=-
# printf '%s' "$WEBHOOK_SECRET"       | gcloud secrets create WEBHOOK_SECRET     --data-file=-
# printf '%s' "$DATABASE_URL"         | gcloud secrets create GATE_DATABASE_URL  --data-file=-
# Grant the compute SA secretAccessor (mirror enrichment) before first deploy.

gcloud run deploy "$SERVICE" \
    --source . \
    --region "$REGION" \
    --allow-unauthenticated \
    --max-instances 1 \
    --set-env-vars "OPERATOR_TELEGRAM_USER_ID=${OPERATOR_TELEGRAM_USER_ID},OPERATOR_CHAT_ID=${OPERATOR_CHAT_ID},TELEGRAM_WEBHOOK_URL=${WEBHOOK_URL},PUBLIC_URL=${PUBLIC_URL},MCP_OAUTH_PROVIDER=" \
    --set-secrets "TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,MCP_BEARER_TOKEN=MCP_BEARER_TOKEN:latest,WEBHOOK_SECRET=WEBHOOK_SECRET:latest,DATABASE_URL=GATE_DATABASE_URL:latest"

echo
echo "Deployed. Cloud Run URL:"
gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'
echo "Point ${PUBLIC_URL} (frogbytes tunnel) at that URL, then run deploy/set-webhook.sh."

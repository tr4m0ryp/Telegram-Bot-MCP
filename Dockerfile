# Telegram Launch Gate — Cloud Run deployable.
# Serves /mcp (MCP tools), /telegram/webhook (operator tap), /launch-tokens.
# The Smithery send-only server is a separate image: Dockerfile.smithery.
# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[full]"

ENV PYTHONUNBUFFERED=1
# Cloud Run injects $PORT; the entrypoint honors it (default 8080 locally).
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "telegram_bot_mcp.gate"]

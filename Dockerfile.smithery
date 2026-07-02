# Telegram Bot MCP - Smithery MCP server over streamable HTTP
# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV PORT=8081
EXPOSE 8081

# "start" is the smithery production entry point. Honor the PORT env var so
# platforms that assign a port (Cloud Run, Railway, Heroku) reach the server.
ENTRYPOINT ["sh", "-c", "exec start --host 0.0.0.0 --port \"${PORT}\""]

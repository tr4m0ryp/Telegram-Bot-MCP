"""In-memory stores shared by the MCP server and the bot runtime.

Volatile by design: swap MemoryStore for a database-backed implementation
in production deployments that must survive restarts.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MessageRecord:
    """A single Telegram message seen or sent by the bot."""

    message_id: int
    chat_id: int
    user_id: int
    username: str | None
    first_name: str | None
    text: str | None
    timestamp: str
    message_type: str


@dataclass
class UserSession:
    """Per-user session state built up from bot interactions."""

    user_id: int
    chat_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    last_seen: str = ""
    message_count: int = 0


@dataclass
class Interaction:
    """One logged user or bot action, for stats and activity views."""

    user_id: int
    type: str
    content: str
    response: str
    timestamp: str


class MemoryStore:
    """Process-local storage for messages, sessions, and interactions."""

    def __init__(self) -> None:
        self.messages: list[MessageRecord] = []
        self.sessions: dict[int, UserSession] = {}
        self.interactions: list[Interaction] = []

    def add_message(self, record: MessageRecord) -> None:
        self.messages.append(record)

    def record_session(self, session: UserSession) -> None:
        session.last_seen = utc_now_iso()
        self.sessions[session.user_id] = session

    def touch_session(self, user_id: int) -> UserSession | None:
        session = self.sessions.get(user_id)
        if session is not None:
            session.message_count += 1
            session.last_seen = utc_now_iso()
        return session

    def log_interaction(self, user_id: int, type_: str, content: str, response: str = "") -> None:
        self.interactions.append(
            Interaction(
                user_id=user_id,
                type=type_,
                content=content,
                response=response,
                timestamp=utc_now_iso(),
            )
        )

    def recent_messages(self, limit: int) -> list[MessageRecord]:
        return self.messages[-limit:] if limit > 0 else []

    def recent_user_activity(self, user_id: int, limit: int = 3) -> list[Interaction]:
        matching = [entry for entry in self.interactions if entry.user_id == user_id]
        return matching[-limit:]

    def command_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.interactions:
            if entry.type == "command":
                counts[entry.content] = counts.get(entry.content, 0) + 1
        return counts

    def user_message_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for entry in self.interactions:
            counts[entry.user_id] = counts.get(entry.user_id, 0) + 1
        return counts

    def most_active_user(self) -> int | None:
        counts = self.user_message_counts()
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]

    def message_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for message in self.messages:
            counts[message.message_type] = counts.get(message.message_type, 0) + 1
        return counts

    def clear_user(self, user_id: int) -> None:
        self.interactions = [e for e in self.interactions if e.user_id != user_id]
        session = self.sessions.get(user_id)
        if session is not None:
            session.message_count = 0


store = MemoryStore()

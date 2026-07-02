"""Inline-button callback-data encoding.

Callback data is what Telegram echoes back when the operator taps a button. It
carries only the decision, the engagement id, and the nonce — never a token and
never anything sensitive. Telegram caps callback_data at 64 bytes, so ids and
nonces must stay short.
"""

from dataclasses import dataclass

APPROVE = "approve"
CANCEL = "cancel"
_SEP = ":"
_PREFIX = "lg"  # launch-gate namespace


@dataclass(frozen=True)
class CallbackData:
    decision: str
    engagement_id: str
    nonce: str

    def encode(self) -> str:
        return _SEP.join((_PREFIX, self.decision, self.engagement_id, self.nonce))


def decode(raw: str) -> CallbackData | None:
    """Parse callback data, or return None if it is not ours / malformed."""
    parts = raw.split(_SEP)
    if len(parts) != 4 or parts[0] != _PREFIX:
        return None
    _, decision, engagement_id, nonce = parts
    if decision not in (APPROVE, CANCEL) or not engagement_id or not nonce:
        return None
    return CallbackData(decision=decision, engagement_id=engagement_id, nonce=nonce)

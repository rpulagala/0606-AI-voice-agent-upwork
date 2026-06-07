import json
import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_MAX_TURNS = 10   # keep last N user+assistant pairs
_TTL_SEC   = 1800 # 30-minute session TTL


class ConversationMemory:
    """
    Redis-backed per-session conversation history.

    Each session stores a JSON list of Anthropic-format messages
    ({"role": "user"|"assistant", "content": ...}).  The list is
    capped at _MAX_TURNS * 2 entries and refreshed on every write.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    def _key(self, session_id: str) -> str:
        return f"voice:session:{session_id}"

    async def load(self, session_id: str) -> list[dict]:
        """Return stored messages for this session, or [] if none / Redis unavailable."""
        try:
            raw = await self._redis.get(self._key(session_id))
            if raw:
                messages = json.loads(raw)
                logger.info("Memory: loaded %d messages for session %s", len(messages), session_id)
                return messages
        except Exception:
            logger.warning("Memory: Redis unavailable — starting fresh session %s", session_id)
        return []

    async def save(self, session_id: str, messages: list[dict]) -> None:
        """Persist up to _MAX_TURNS*2 messages and reset the TTL."""
        trimmed = messages[-(_MAX_TURNS * 2):]
        try:
            await self._redis.setex(self._key(session_id), _TTL_SEC, json.dumps(trimmed))
            logger.debug("Memory: saved %d messages for session %s", len(trimmed), session_id)
        except Exception:
            logger.warning("Memory: Redis write failed for session %s", session_id)

    async def clear(self, session_id: str) -> None:
        try:
            await self._redis.delete(self._key(session_id))
            logger.info("Memory: cleared session %s", session_id)
        except Exception:
            logger.warning("Memory: Redis clear failed for session %s", session_id)

    async def close(self) -> None:
        await self._redis.aclose()

"""Per-agent token-bucket rate limiting for /api/v2 (spec §6)."""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Dict

from api.v2.errors import ApiError

RATE_PER_MINUTE = int(os.getenv("V2_RATE_LIMIT_PER_MINUTE", "120"))


class TokenBucketLimiter:
    """A token bucket per agent_id. Refills at per_minute/60 tokens per second."""

    def __init__(self, per_minute: int = RATE_PER_MINUTE, burst: int | None = None):
        self.per_minute = max(1, per_minute)
        self.burst = max(1, burst if burst is not None else per_minute)
        self.refill_per_sec = self.per_minute / 60.0
        self._buckets: Dict[str, tuple[float, float]] = {}  # agent_id -> (tokens, last_ts)
        self._lock = threading.Lock()

    def check(self, agent_id: str) -> Dict[str, object]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(agent_id, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.refill_per_sec)
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            self._buckets[agent_id] = (tokens, now)
        remaining = int(tokens)
        retry_after = 0 if allowed else int(math.ceil((1.0 - tokens) / self.refill_per_sec))
        return {
            "allowed": allowed,
            "limit": self.per_minute,
            "remaining": remaining,
            "reset": int(math.ceil((self.burst - tokens) / self.refill_per_sec)),
            "retry_after": retry_after,
        }


# Process-wide limiter shared by all v2 endpoints.
limiter = TokenBucketLimiter()


def enforce(agent_id: str, response) -> None:
    """Consume one token; set X-RateLimit-* headers; raise rate_limited on miss."""
    state = limiter.check(agent_id)
    response.headers["X-RateLimit-Limit"] = str(state["limit"])
    response.headers["X-RateLimit-Remaining"] = str(state["remaining"])
    response.headers["X-RateLimit-Reset"] = str(state["reset"])
    if not state["allowed"]:
        raise ApiError(
            "rate_limited", "Rate limit exceeded", status=429,
            details={"retry_after": state["retry_after"]}, retryable=True,
        )

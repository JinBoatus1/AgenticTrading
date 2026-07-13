"""Panel proxy for FinSearch news signals — keeps FINGPT_API_KEY server-side."""
import threading

from fastapi import APIRouter

from dashboard.backend.cache import (CACHE_KEY_NEWS_SIGNALS, TTL_NEWS,
                                     TTL_NEWS_UNAVAILABLE, shared_ttl_cache)
from dashboard.backend.infrastructure.llm.validator import DJIA_30
from dashboard.backend.integrations import news_sentiment

router = APIRouter(prefix="/news", tags=["news"])

# Single-flight: concurrent cold-cache requests share one upstream fetch
# instead of stampeding the bearer-gated producer at every TTL boundary.
_fetch_lock = threading.Lock()


# Deliberately sync `def`: FastAPI runs it in the threadpool, so the blocking
# requests.get inside the adapter cannot stall the event loop. Do NOT convert
# to `async def` without moving the HTTP call off the loop.
@router.get("/signals")
def latest_news_signals():
    cached = shared_ttl_cache.get(CACHE_KEY_NEWS_SIGNALS)
    if cached is not None:
        return cached
    with _fetch_lock:
        cached = shared_ttl_cache.get(CACHE_KEY_NEWS_SIGNALS)  # re-check after the wait
        if cached is not None:
            return cached
        try:
            payload = news_sentiment.get_latest_panel_payload(list(DJIA_30))
        except Exception:
            payload = dict(news_sentiment.UNAVAILABLE_PAYLOAD)
        # Negative-cache failures BRIEFLY. get_latest_panel_payload already returns
        # UNAVAILABLE_PAYLOAD (not raises) on producer failure, so unavailable results
        # reach here on the normal path too. Caching them (short TTL) is what stops a
        # sustained outage from serializing every request through _fetch_lock at
        # ~10s/attempt; the short TTL (vs TTL_NEWS) also lets the panel recover within
        # ~30s of the producer coming back instead of showing stale "unavailable" for
        # the full 420s.
        ttl = (TTL_NEWS_UNAVAILABLE
               if payload.get("status") == "unavailable" else TTL_NEWS)
        shared_ttl_cache.set(CACHE_KEY_NEWS_SIGNALS, payload, ttl_seconds=ttl)
    return payload

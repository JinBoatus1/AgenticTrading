"""Describe a database URL for logging, without leaking its credentials.

Used by every store factory (users, agents, agent versions, strategies) to log
*which* Postgres it bound to rather than merely that it bound to "postgres". A
bare backend name cannot distinguish the intended Neon database from staging, or
from a URL with a typo'd host -- they produce byte-identical startup logs, which
is the failure shape CLAUDE.md's "Fail-closed is not fail-visible" section exists
to warn about. (The scoped CONTENT_/USERS_ names rule out an *accidental*
collision with another tool's env var; they do nothing about a wrong value
deliberately set.)

Defined once rather than cloned into each store module (this feature's pattern
everywhere else) because it is credential-scrubbing code: four hand-copied
scrubbers is four chances for one of them to leak a password into a log.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def describe_database_url(database_url: str) -> str:
    """Return ``host[:port]/dbname`` for ``database_url``, never its credentials.

    Returns ``"?/?"`` for anything not parseable as a URL. That constant is
    deliberate: psycopg also accepts keyword/DSN strings (``host=... dbname=...
    password=...``), and urlsplit puts the *entire* such string -- password
    included -- in ``.path``. Echoing any part of unparseable input back into a
    log is exactly the leak this helper exists to prevent, so it echoes nothing.
    Prod uses a URL, so the degraded case costs only log detail.

    Never raises: this runs inside a factory at import time, and a log helper
    that explodes on an odd URL would take the whole app down with it.
    """
    try:
        parts = urlsplit(database_url)
        host = parts.hostname
        port = "" if parts.port is None else f":{parts.port}"
    except ValueError:
        # urlsplit, or .port on a non-integer port, rejected the input.
        return "?/?"
    if not host:
        return "?/?"
    dbname = parts.path.lstrip("/") or "?"
    # urlsplit strips the brackets from an IPv6 literal, and IPv6 addresses
    # are colon-delimited themselves, so an unbracketed "::1:5432" cannot be
    # read as host-vs-port. Restore them: an ambiguous line is not visibility.
    if ":" in host:
        host = f"[{host}]"
    return f"{host}{port}/{dbname}"

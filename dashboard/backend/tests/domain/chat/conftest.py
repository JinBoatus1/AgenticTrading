"""Ensure the chat service's import-time env requirements are satisfied.

``dashboard.backend.domain.chat.service`` calls ``require_env`` at import time,
so dummy credentials must exist before that module (or its shim) is imported by
any test. No real provider call is made; the Anthropic client is mocked.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-test-model")

"""
Shared new-password policy (NIST 800-63B style: length + blocklist, no
composition rules). Applied wherever a NEW password is accepted: signup,
change-password, and (Phase 2) reset. Existing stored passwords are never
re-validated.
"""

from pathlib import Path

MIN_LENGTH = 8
MAX_LENGTH = 128

_BLOCKLIST_PATH = Path(__file__).parent / "common_passwords.txt"


def _load_blocklist() -> frozenset:
    entries = set()
    for line in _BLOCKLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line.lower())
    return frozenset(entries)


_BLOCKLIST = _load_blocklist()


def validate_new_password(password: str, email: str) -> list:
    """Return human-readable violations; empty list means acceptable."""
    violations = []
    if len(password) < MIN_LENGTH:
        violations.append(f"Password must be at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        violations.append(f"Password must be at most {MAX_LENGTH} characters.")
    if password.lower() in _BLOCKLIST:
        violations.append("That password is too common; pick something less guessable.")
    local_part = (email or "").split("@", 1)[0].strip().lower()
    if len(local_part) >= 3 and local_part in password.lower():
        violations.append("Password must not contain your email name.")
    return violations

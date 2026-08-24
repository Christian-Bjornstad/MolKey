"""Generate opaque identifiers that never derive from patient data."""

from __future__ import annotations

import secrets
from datetime import date


def generate_package_id(*, today: date | None = None) -> str:
    """Return a high-entropy, year-scoped pseudonymous package identifier."""
    effective_date = today or date.today()
    return f"SPK-{effective_date.year}-{secrets.token_hex(12).upper()}"


def generate_key_id() -> str:
    """Return an opaque identifier for key metadata."""
    return f"KEY-{secrets.token_hex(6).upper()}"

from datetime import datetime, timezone


def utc_now() -> str:
    """Return the current time in ISO format with UTC timezone offset."""
    return datetime.now(timezone.utc).isoformat()

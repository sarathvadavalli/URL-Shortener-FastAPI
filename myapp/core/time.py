from datetime import UTC, datetime


def utcnow():
    """Naive UTC for MySQL DATETIME columns."""
    return datetime.now(UTC).replace(tzinfo=None)

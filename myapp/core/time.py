from datetime import datetime, timezone

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value

    return value.astimezone(UTC).replace(tzinfo=None)

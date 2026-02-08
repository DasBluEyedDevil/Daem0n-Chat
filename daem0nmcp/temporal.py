"""Temporal utilities for human-readable time formatting."""

from datetime import datetime, timezone


def _humanize_timedelta(dt: datetime) -> str:
    """Convert a datetime to a human-readable relative time string.

    Examples: "today", "yesterday", "3 days ago", "2 weeks ago",
              "about a month ago", "3 months ago", "over a year ago"
    """
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = now - dt
    days = delta.days

    if days == 0:
        return "today"
    elif days == 1:
        return "yesterday"
    elif days < 7:
        return f"{days} days ago"
    elif days < 14:
        return "about a week ago"
    elif days < 30:
        weeks = days // 7
        return f"{weeks} weeks ago"
    elif days < 60:
        return "about a month ago"
    elif days < 365:
        months = days // 30
        return f"{months} months ago"
    else:
        years = days // 365
        if years == 1:
            return "over a year ago"
        return f"over {years} years ago"

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _humantime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - value
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


templates.env.filters["humantime"] = _humantime
templates.env.filters["datetime"] = _datetime

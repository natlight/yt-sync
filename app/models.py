from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceType(str, Enum):
    channel = "channel"
    playlist = "playlist"
    music = "music"


class JobKind(str, Enum):
    scheduled = "scheduled"
    manual = "manual"
    oneoff = "oneoff"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    ok = "ok"
    error = "error"
    cancelled = "cancelled"


class DownloadStatus(str, Enum):
    ok = "ok"
    skipped = "skipped"
    error = "error"


class Source(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: SourceType
    name: str = Field(index=True)
    url: str
    cron: str | None = None
    enabled: bool = False
    max_downloads: int = 25
    date_after: str | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class JobRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str
    source_id: int | None = Field(default=None, foreign_key="source.id", index=True)
    oneoff_url: str | None = None
    oneoff_type: str | None = None
    status: str = JobStatus.queued.value
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log_tail: str | None = None
    exit_code: int | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Download(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_id: int | None = Field(default=None, foreign_key="source.id", index=True)
    job_run_id: int | None = Field(default=None, foreign_key="jobrun.id", index=True)
    video_id: str = Field(index=True)
    title: str | None = None
    file_path: str | None = None
    status: str
    started_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = None
    error_msg: str | None = None
    bytes: int | None = None

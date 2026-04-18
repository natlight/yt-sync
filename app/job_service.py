"""Orchestrates a JobRun: invokes yt_runner, persists results."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app import yt_runner
from app.config import settings
from app.db import engine
from app.models import (
    Download,
    DownloadStatus,
    JobKind,
    JobRun,
    JobStatus,
    Source,
    SourceType,
    utcnow,
)

log = logging.getLogger(__name__)

_run_lock = asyncio.Semaphore(1)
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """Schedule a coroutine, hold a strong reference, and clean up on done.

    Works whether called from a running async context (FastAPI route, scheduler)
    or from synchronous code that has a loop available via APScheduler.
    """
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
    except RuntimeError:
        task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _archive_file_for(source: Source) -> Path:
    safe = yt_runner.sanitize_name(source.name)
    prefix = {
        SourceType.channel: "channel",
        SourceType.playlist: "playlist",
        SourceType.music: "music",
    }[source.type]
    return settings.archive_files_dir / f"{prefix}-{safe}.txt"


def _output_dir_for(source: Source) -> Path:
    safe = yt_runner.sanitize_name(source.name)
    if source.type == SourceType.channel:
        return settings.video_channels_root / safe
    if source.type == SourceType.playlist:
        return settings.video_playlists_root / safe
    return settings.music_root_dir / safe


def _archive_file_oneoff(kind: str, ts: datetime) -> Path:
    return settings.archive_files_dir / f"oneoff-{kind}-{ts.strftime('%Y%m%d-%H%M%S')}.txt"


def _output_dir_oneoff(kind: str) -> Path:
    if kind == "music":
        return settings.music_root_dir / "_oneoffs"
    return settings.media_root / "YouTube One-offs"


async def _execute(
    job_run_id: int,
    runner_coro,
    output_dir: Path,
) -> None:
    """Drive a single yt-dlp run for an existing JobRun row."""
    async with _run_lock:
        with Session(engine) as session:
            job = session.get(JobRun, job_run_id)
            if job is None:
                log.error("JobRun %s vanished before execution", job_run_id)
                return
            job.status = JobStatus.running.value
            job.started_at = utcnow()
            session.add(job)
            session.commit()
            source_id = job.source_id

        try:
            result: yt_runner.RunResult = await runner_coro
        except Exception as exc:  # noqa: BLE001
            log.exception("Job %s crashed", job_run_id)
            with Session(engine) as session:
                job = session.get(JobRun, job_run_id)
                if job is not None:
                    job.status = JobStatus.error.value
                    job.finished_at = utcnow()
                    job.log_tail = f"crashed: {exc}"
                    session.add(job)
                    session.commit()
                if source_id is not None:
                    src = session.get(Source, source_id)
                    if src is not None:
                        src.last_run_at = utcnow()
                        src.last_status = "error"
                        session.add(src)
                        session.commit()
            return

        finished_at = utcnow()
        with Session(engine) as session:
            job = session.get(JobRun, job_run_id)
            if job is None:
                return
            job.exit_code = result.exit_code
            job.status = JobStatus.ok.value if result.ok else JobStatus.error.value
            job.finished_at = finished_at
            job.log_tail = result.log_tail[-65536:]
            session.add(job)

            for vid in result.downloaded_ids:
                dl = Download(
                    source_id=source_id,
                    job_run_id=job_run_id,
                    video_id=vid,
                    status=DownloadStatus.ok.value,
                    started_at=job.started_at or finished_at,
                    finished_at=finished_at,
                    file_path=str(output_dir),
                )
                session.add(dl)

            if source_id is not None:
                src = session.get(Source, source_id)
                if src is not None:
                    src.last_run_at = finished_at
                    src.last_status = "ok" if result.ok else "error"
                    session.add(src)

            session.commit()


def queue_source_run(source_id: int, kind: JobKind = JobKind.manual) -> int:
    """Create a JobRun row and schedule its execution. Returns the JobRun id."""
    with Session(engine) as session:
        src = session.get(Source, source_id)
        if src is None:
            raise ValueError(f"Source {source_id} not found")
        # Skip if a run is already active for this source
        active = session.exec(
            select(JobRun).where(
                JobRun.source_id == source_id,
                JobRun.status.in_([JobStatus.queued.value, JobStatus.running.value]),  # type: ignore[union-attr]
            )
        ).first()
        if active is not None:
            return active.id  # type: ignore[return-value]

        # Snapshot the fields we need before the session closes
        src_type = src.type
        src_name = src.name
        src_url = src.url
        src_max = src.max_downloads
        src_date_after = src.date_after
        archive_file = _archive_file_for(src)
        output_dir = _output_dir_for(src)

        job = JobRun(kind=kind.value, source_id=source_id, status=JobStatus.queued.value)
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
        assert job_id is not None

    cookies = settings.cookies_file if settings.cookies_file.exists() else None
    if src_type == SourceType.music:
        coro = yt_runner.run_music(
            url=src_url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies,
            max_downloads=src_max,
        )
    else:
        coro = yt_runner.run_video(
            url=src_url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies,
            max_downloads=src_max,
            date_after=src_date_after,
        )

    async def _run_and_maybe_m3u() -> None:
        await _execute(job_id, coro, output_dir)
        if src_type == SourceType.music:
            try:
                yt_runner.write_m3u_playlist(output_dir, yt_runner.sanitize_name(src_name))
            except Exception:  # noqa: BLE001
                log.exception("Failed to write m3u playlist for %s", src_name)

    _spawn(_run_and_maybe_m3u())
    return job_id


def queue_oneoff(url: str, kind: str) -> int:
    """kind: 'video' or 'music'. Returns JobRun id."""
    if kind not in ("video", "music"):
        raise ValueError("kind must be 'video' or 'music'")

    with Session(engine) as session:
        job = JobRun(
            kind=JobKind.oneoff.value,
            oneoff_url=url,
            oneoff_type=kind,
            status=JobStatus.queued.value,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
        assert job_id is not None

    archive_file = _archive_file_oneoff(kind, utcnow())
    output_dir = _output_dir_oneoff(kind)
    cookies = settings.cookies_file if settings.cookies_file.exists() else None
    if kind == "music":
        coro = yt_runner.run_music(
            url=url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies,
            max_downloads=settings.default_max_downloads,
        )
    else:
        coro = yt_runner.run_video(
            url=url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies,
            max_downloads=settings.default_max_downloads,
        )

    _spawn(_execute(job_id, coro, output_dir))
    return job_id


def cancel_job(job_id: int) -> bool:
    """Best-effort cancel: marks queued jobs cancelled. (Running subprocess
    cancel would require holding the proc handle — left as a TODO.)"""
    with Session(engine) as session:
        job = session.get(JobRun, job_id)
        if job is None:
            return False
        if job.status == JobStatus.queued.value:
            job.status = JobStatus.cancelled.value
            job.finished_at = utcnow()
            session.add(job)
            session.commit()
            return True
        return False


# Module-level helper so APScheduler can dispatch by source id without
# pickling closures.
def run_source_now(source_id: int) -> None:
    queue_source_run(source_id, kind=JobKind.scheduled)

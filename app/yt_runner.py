"""Async yt-dlp wrappers refactored from scripts/sync.py.

Stays faithful to the original CronJob's flags (SponsorBlock, format selectors,
retries, sleep intervals, --match-filter) so archive files and output naming
remain compatible. Adds `--print after_move:%(id)s` so the caller can collect
downloaded video ids from stdout.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

LogCallback = Callable[[str], Awaitable[None]] | None


def sanitize_name(name: str) -> str:
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()


@dataclass
class RunResult:
    exit_code: int
    downloaded_ids: list[str] = field(default_factory=list)
    log_tail: str = ""

    @property
    def ok(self) -> bool:
        # 0 = success, 1 = some downloads failed but ran, 101 = max-downloads hit
        return self.exit_code in (0, 1, 101)


def _video_cmd(
    url: str,
    output_dir: Path,
    archive_file: Path,
    cookies_file: Path | None,
    max_downloads: int,
    date_after: str | None,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "%(upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--format",
        (
            "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]"
            "/bestvideo[height<=2160]+bestaudio"
            "/best"
        ),
        "--merge-output-format", "mp4",
        "--sponsorblock-remove",
        "sponsor,selfpromo,interaction,intro,outro,preview,music_offtopic",
        "--download-archive", str(archive_file),
        "--output", output_template,
        "--embed-thumbnail",
        "--embed-metadata",
        "--convert-thumbnails", "jpg",
        "--match-filter", "!is_live & !was_live",
        "--max-downloads", str(max_downloads),
        "--ignore-errors",
        "--retries", "5",
        "--fragment-retries", "5",
        "--sleep-interval", "2",
        "--max-sleep-interval", "5",
        "--print", "after_move:DOWNLOADED_ID=%(id)s",
        "--no-progress",
        "--newline",
    ]
    if date_after:
        cmd.extend(["--dateafter", date_after, "--break-on-reject"])
    if cookies_file and Path(cookies_file).exists():
        cmd.extend(["--cookies", str(cookies_file)])
    cmd.append(url)
    return cmd


def _music_cmd(
    url: str,
    output_dir: Path,
    archive_file: Path,
    cookies_file: Path | None,
    max_downloads: int,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "%(title)s [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--extract-audio",
        "--audio-format", "opus",
        "--audio-quality", "0",
        "--download-archive", str(archive_file),
        "--output", output_template,
        "--embed-thumbnail",
        "--embed-metadata",
        "--convert-thumbnails", "jpg",
        "--match-filter", "!is_live & !was_live",
        "--max-downloads", str(max_downloads),
        "--ignore-errors",
        "--retries", "5",
        "--fragment-retries", "5",
        "--sleep-interval", "2",
        "--max-sleep-interval", "5",
        "--print", "after_move:DOWNLOADED_ID=%(id)s",
        "--no-progress",
        "--newline",
    ]
    if cookies_file and Path(cookies_file).exists():
        cmd.extend(["--cookies", str(cookies_file)])
    cmd.append(url)
    return cmd


async def _run(cmd: list[str], on_log: LogCallback) -> RunResult:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    ids: list[str] = []
    tail: list[str] = []
    max_tail_lines = 1000

    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").rstrip("\n")
        if line.startswith("DOWNLOADED_ID="):
            ids.append(line.removeprefix("DOWNLOADED_ID=").strip())
            continue
        tail.append(line)
        if len(tail) > max_tail_lines:
            tail = tail[-max_tail_lines:]
        if on_log is not None:
            try:
                await on_log(line)
            except Exception:  # noqa: BLE001
                pass

    rc = await proc.wait()
    return RunResult(exit_code=rc, downloaded_ids=ids, log_tail="\n".join(tail))


async def run_video(
    url: str,
    output_dir: Path,
    archive_file: Path,
    cookies_file: Path | None,
    max_downloads: int,
    date_after: str | None = None,
    on_log: LogCallback = None,
) -> RunResult:
    cmd = _video_cmd(url, output_dir, archive_file, cookies_file, max_downloads, date_after)
    return await _run(cmd, on_log)


async def run_music(
    url: str,
    output_dir: Path,
    archive_file: Path,
    cookies_file: Path | None,
    max_downloads: int,
    on_log: LogCallback = None,
) -> RunResult:
    cmd = _music_cmd(url, output_dir, archive_file, cookies_file, max_downloads)
    return await _run(cmd, on_log)


def write_m3u_playlist(output_dir: Path, playlist_name: str) -> int:
    """Write an M3U8 file Jellyfin will pick up. Returns track count."""
    tracks = sorted(output_dir.glob("*.opus"))
    if not tracks:
        return 0
    m3u_path = output_dir / f"{playlist_name}.m3u8"
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for track in tracks:
            display = track.stem.rsplit(" [", 1)[0]
            f.write(f"#EXTINF:-1,{display}\n")
            f.write(f"{track.name}\n")
    return len(tracks)

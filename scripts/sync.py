#!/usr/bin/env python3
"""
yt-sync: Download new YouTube channel/playlist videos and music playlists to Jellyfin.

Reads a YAML config (mounted via ConfigMap) listing channels, playlists, and
music playlists. Uses yt-dlp with SponsorBlock to remove ads/sponsor segments.
Tracks downloaded items via archive files so re-runs only fetch new content.
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml


def sanitize_name(name: str) -> str:
    """Make a name safe for use as a directory name."""
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()


def resolve_url(entry: dict, base_url: str) -> str:
    """Return a full URL from an entry that has either 'url' or 'id'."""
    return entry.get("url") or (
        f"{base_url}{entry['id']}" if entry.get("id") else ""
    )


def run_ytdlp_video(
    url: str,
    output_dir: str,
    archive_file: str,
    cookies_file: str | None,
    max_downloads: int,
    date_after: str | None = None,
) -> int:
    """
    Download video content with yt-dlp.

    Format strategy:
      1. Best MP4 video up to 4K + best M4A audio (most compatible with Jellyfin)
      2. Best video up to 4K + best audio (any container, merged to MP4)
      3. Single-file best quality fallback

    SponsorBlock removes: sponsor segments, self-promotion, interaction reminders,
    intros, outros, and preview/recap sections — effectively ad-free.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    output_template = os.path.join(
        output_dir, "%(upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s"
    )

    cmd = [
        "yt-dlp",
        "--js-runtimes", "nodejs",
        "--format",
        (
            "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]"
            "/bestvideo[height<=2160]+bestaudio"
            "/best"
        ),
        "--merge-output-format", "mp4",
        "--sponsorblock-remove",
        "sponsor,selfpromo,interaction,intro,outro,preview,music_offtopic",
        "--download-archive", archive_file,
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
    ]

    if date_after:
        cmd.extend(["--dateafter", date_after])
        # Stop as soon as we hit a video older than the cutoff (channels are
        # ordered newest-first, so everything after the first rejection is old).
        cmd.append("--break-on-reject")
        print(f"  [filter] Only videos on/after {date_after} (stop at first older video)")

    _append_cookies(cmd, cookies_file)
    cmd.append(url)

    print(f"  [cmd] yt-dlp {' '.join(cmd[1:])}")
    return subprocess.run(cmd).returncode


def write_m3u_playlist(output_dir: str, playlist_name: str) -> None:
    """
    Write an M3U8 file in the playlist folder so Jellyfin imports it as a playlist.

    Jellyfin scans .m3u8 files anywhere in the music library and creates a matching
    playlist. Uses relative paths so the file works regardless of mount location.
    Re-written on every run so newly downloaded tracks are always included.
    """
    tracks = sorted(Path(output_dir).glob("*.opus"))
    if not tracks:
        print(f"  [m3u] No tracks found yet, skipping playlist file")
        return

    m3u_path = Path(output_dir) / f"{playlist_name}.m3u8"
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for track in tracks:
            # Strip the [videoID] suffix from the display name
            display = track.stem.rsplit(" [", 1)[0]
            f.write(f"#EXTINF:-1,{display}\n")
            f.write(f"{track.name}\n")

    print(f"  [m3u] Wrote {len(tracks)} tracks → {m3u_path.name}")


def run_ytdlp_music(
    url: str,
    output_dir: str,
    archive_file: str,
    cookies_file: str | None,
    max_downloads: int,
) -> int:
    """
    Download audio-only content with yt-dlp for Jellyfin's Music library.

    Uses opus (YouTube's native audio codec — no re-encoding, best quality).
    Embeds thumbnail as cover art and writes all available metadata tags so
    Jellyfin can display artist, title, and album art correctly.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Jellyfin music scanner reads title/artist from tags, not filenames,
    # but a clean filename helps when browsing the filesystem directly.
    output_template = os.path.join(
        output_dir, "%(title)s [%(id)s].%(ext)s"
    )

    cmd = [
        "yt-dlp",
        "--js-runtimes", "nodejs",
        # Extract audio only — no video stream downloaded
        "--extract-audio",
        # Opus is YouTube's native format: zero re-encoding, best quality/size
        "--audio-format", "opus",
        "--audio-quality", "0",
        "--download-archive", archive_file,
        "--output", output_template,
        # Cover art embedded as album art tag
        "--embed-thumbnail",
        "--embed-metadata",
        "--convert-thumbnails", "jpg",
        # Skip live streams
        "--match-filter", "!is_live & !was_live",
        "--max-downloads", str(max_downloads),
        "--ignore-errors",
        "--retries", "5",
        "--fragment-retries", "5",
        "--sleep-interval", "2",
        "--max-sleep-interval", "5",
    ]

    _append_cookies(cmd, cookies_file)
    cmd.append(url)

    print(f"  [cmd] yt-dlp {' '.join(cmd[1:])}")
    return subprocess.run(cmd).returncode


def _append_cookies(cmd: list[str], cookies_file: str | None) -> None:
    if cookies_file and Path(cookies_file).exists():
        cmd.extend(["--cookies", cookies_file])
        print(f"  [auth] Using cookies from {cookies_file}")
    else:
        print(f"  [auth] No cookies file — public content only")


def _process_sources(
    sources: list[dict],
    label_key: str,
    base_url: str,
    output_root: str,
    archive_dir: str,
    archive_prefix: str,
    cookies_file: str,
    max_downloads: int,
    runner,
) -> list[str]:
    errors: list[str] = []
    for entry in sources:
        name = entry.get("name", f"Unknown {label_key}")
        url = resolve_url(entry, base_url)
        if not url:
            print(f"SKIP: {label_key} '{name}' has no URL or id configured.")
            continue

        safe_name = sanitize_name(name)
        output_dir = os.path.join(output_root, safe_name)
        archive_file = os.path.join(archive_dir, f"{archive_prefix}-{safe_name}.txt")
        date_after = entry.get("date_after")

        print(f"\n>>> {label_key}: {name}")
        print(f"    url:    {url}")
        print(f"    output: {output_dir}")

        kwargs = dict(
            url=url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies_file,
            max_downloads=max_downloads,
        )
        if date_after is not None:
            kwargs["date_after"] = date_after

        rc = runner(**kwargs)

        if rc not in (0, 1, 101):
            errors.append(f"{label_key} '{name}' failed with exit code {rc}")
        else:
            print(f"    [done] exit code {rc}")

    return errors


def main() -> None:
    config_file  = os.getenv("CONFIG_FILE",   "/config/sources.yaml")
    media_root   = os.getenv("MEDIA_ROOT",    "/media")
    music_root   = os.getenv("MUSIC_ROOT",    "/music")
    archive_dir  = os.getenv("ARCHIVE_DIR",   "/archive")
    cookies_file = os.getenv("COOKIES_FILE",  "/secrets/cookies.txt")
    max_downloads = int(os.getenv("MAX_DOWNLOADS_PER_SOURCE", "20"))

    print("=" * 60)
    print("yt-sync starting")
    print(f"  config:       {config_file}")
    print(f"  media root:   {media_root}")
    print(f"  music root:   {music_root}")
    print(f"  archive dir:  {archive_dir}")
    print(f"  max per src:  {max_downloads}")
    print("=" * 60)

    Path(archive_dir).mkdir(parents=True, exist_ok=True)

    try:
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_file}")
        sys.exit(1)

    channels       = config.get("channels", [])
    playlists      = config.get("playlists", [])
    music_playlists = config.get("music_playlists", [])

    if not channels and not playlists and not music_playlists:
        print("WARNING: No sources configured. Nothing to do.")
        sys.exit(0)

    errors: list[str] = []

    # --- Video channels ---
    errors += _process_sources(
        sources=channels,
        label_key="Channel",
        base_url="",
        output_root=os.path.join(media_root, "YouTube Channels"),
        archive_dir=archive_dir,
        archive_prefix="channel",
        cookies_file=cookies_file,
        max_downloads=max_downloads,
        runner=run_ytdlp_video,
    )

    # --- Video playlists / watchlists ---
    errors += _process_sources(
        sources=playlists,
        label_key="Playlist",
        base_url="https://www.youtube.com/playlist?list=",
        output_root=os.path.join(media_root, "YouTube Playlists"),
        archive_dir=archive_dir,
        archive_prefix="playlist",
        cookies_file=cookies_file,
        max_downloads=max_downloads,
        runner=run_ytdlp_video,
    )

    # --- Music playlists (audio-only, goes to Jellyfin Music library) ---
    music_output_root = os.path.join(music_root, "YouTube Music")
    for entry in music_playlists:
        name = entry.get("name", "Unknown Music Playlist")
        url = resolve_url(entry, "https://music.youtube.com/playlist?list=")
        if not url:
            print(f"SKIP: Music Playlist '{name}' has no URL or id configured.")
            continue

        safe_name = sanitize_name(name)
        output_dir = os.path.join(music_output_root, safe_name)
        archive_file = os.path.join(archive_dir, f"music-{safe_name}.txt")

        print(f"\n>>> Music Playlist: {name}")
        print(f"    url:    {url}")
        print(f"    output: {output_dir}")

        rc = run_ytdlp_music(
            url=url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies_file,
            max_downloads=max_downloads,
        )

        if rc not in (0, 1, 101):
            errors.append(f"Music Playlist '{name}' failed with exit code {rc}")
        else:
            print(f"    [done] exit code {rc}")
            write_m3u_playlist(output_dir, safe_name)

    # --- Summary ---
    print("\n" + "=" * 60)
    if errors:
        print("COMPLETED WITH ERRORS:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("All sources synced successfully.")


if __name__ == "__main__":
    main()

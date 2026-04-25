from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = "sqlite:////db/app.sqlite"
    archive_dir: Path = Path("/archive")
    media_root: Path = Path("/media")
    music_root: Path = Path("/music")
    cookies_file: Path = Path("/secrets/cookies.txt")
    default_max_downloads: int = 25
    timezone: str = "America/Chicago"

    @property
    def archive_files_dir(self) -> Path:
        return self.archive_dir / "archives"

    @property
    def video_channels_root(self) -> Path:
        return self.media_root / "YouTube Channels"

    @property
    def video_playlists_root(self) -> Path:
        return self.media_root / "YouTube Playlists"

    @property
    def music_root_dir(self) -> Path:
        return self.music_root / "YouTube Music"


settings = Settings()

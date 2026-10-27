"""Runtime configuration for the local ADVP service."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables with the ADVP_ prefix."""

    model_config = SettingsConfigDict(env_prefix="ADVP_", env_file=".env", extra="ignore")

    app_name: str = "ADVP"
    host: str = "127.0.0.1"
    port: int = 8765
    database_path: Path = Path.home() / ".advp" / "advp.db"
    backup_dir: Path = Path.home() / ".advp" / "backups"
    workspace_dir: Path = Path.home() / ".advp" / "workspace"
    max_file_bytes: int = 5 * 1024 * 1024 * 1024
    profile_sample_rows: int = 100_000
    analysis_sample_rows: int = 10_000
    render_sample_rows: int = 20_000
    three_d_max_elements: int = 50_000_000
    render_python: str | None = None
    preview_rows: int = 20
    text_max_chars: int = 2_000_000
    text_max_facts: int = 2_000
    text_ai_max_snippets: int = 200
    log_level: str = "INFO"
    log_dir: Path | None = None
    static_dir: Path | None = None
    share_dir: Path | None = None
    session_cookie: str = "advp_session"
    auth_token: str | None = None
    allow_shutdown: bool = False
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    def ensure_database_dir(self) -> None:
        """Create the parent directory for the SQLite database."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

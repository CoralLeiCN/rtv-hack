from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def env_file() -> Path:
    """Use one explicit file across the app and exporter, including worktrees."""
    override = os.environ.get("RANGER_ENV_FILE")
    if not override:
        return ENV_FILE
    path = Path(override).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError("RANGER_ENV_FILE must name an existing absolute file path")
    return path


def env_values():
    values = {key: value for key, value in dotenv_values(env_file(), interpolate=False).items()
              if value is not None}
    values.update(os.environ)
    return values


@dataclass(frozen=True)
class Settings:
    archive_url: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    search_timeout_sec: float = 30.0
    request_timeout_sec: float = 10.0
    clip_ttl_sec: int = 1800
    max_sessions: int = 256
    secure_cookie: bool = False
    manifest_path: Path | None = None
    static_dir: Path | None = None
    capture_dir: Path | None = None

    @property
    def configured(self) -> bool:
        try:
            parsed = urlsplit(self.archive_url)
        except ValueError:
            return False
        return bool(parsed.scheme in {"http", "https"} and parsed.hostname
                    and not parsed.username and not parsed.password
                    and not parsed.query and not parsed.fragment
                    and self.api_key and self.api_key.isascii() and not any(c.isspace() for c in self.api_key))

    @classmethod
    def from_env(cls) -> "Settings":
        # Resolve relative to the backend, independent of the launch directory.
        # Exported variables win; keep api_keys literal and avoid mutating os.environ.
        values = env_values()

        def bounded(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(values.get(name, default))
                return value if low <= value <= high else default
            except ValueError:
                return default

        return cls(
            archive_url=values.get("ARCHIVE_URL", "").rstrip("/"),
            api_key=values.get("ARCHIVE_API_KEY", ""),
            search_timeout_sec=bounded("RANGER_SEARCH_TIMEOUT_SEC", 30, 1, 60),
            request_timeout_sec=bounded("RANGER_REQUEST_TIMEOUT_SEC", 10, 1, 30),
            clip_ttl_sec=int(bounded("RANGER_CLIP_TTL_SEC", 1800, 30, 7200)),
            secure_cookie=values.get("RANGER_SECURE_COOKIE", "false").lower() == "true",
            manifest_path=Path(values["RANGER_REFERENCE_MANIFEST"]) if values.get("RANGER_REFERENCE_MANIFEST") else None,
            static_dir=Path(values["RANGER_STATIC_DIR"]) if values.get("RANGER_STATIC_DIR") else None,
            capture_dir=Path(values.get('RANGER_CAPTURE_DIR') or ENV_FILE.parent / '.captures'),
        )

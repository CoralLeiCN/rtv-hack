from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class Settings:
    ingress_url: str = field(default="", repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    search_timeout_sec: float = 30.0
    request_timeout_sec: float = 10.0
    clip_ttl_sec: int = 1800
    max_sessions: int = 256
    secure_cookie: bool = False
    manifest_path: Path | None = None
    static_dir: Path | None = None

    @property
    def configured(self) -> bool:
        try:
            parsed = urlsplit(self.ingress_url)
        except ValueError:
            return False
        return bool(parsed.scheme in {"http", "https"} and parsed.hostname
                    and not parsed.username and not parsed.password
                    and not parsed.query and not parsed.fragment
                    and self.username and self.password)

    @classmethod
    def from_env(cls) -> "Settings":
        # Resolve relative to the backend, independent of the launch directory.
        # Exported variables win; keep passwords literal and avoid mutating os.environ.
        values = {key: value for key, value in dotenv_values(ENV_FILE, interpolate=False).items()
                  if value is not None}
        values.update(os.environ)

        def bounded(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(values.get(name, default))
                return value if low <= value <= high else default
            except ValueError:
                return default

        return cls(
            ingress_url=values.get("INGRESS_URL", "").rstrip("/"),
            username=values.get("USERNAME", ""),
            password=values.get("PASSWORD", ""),
            search_timeout_sec=bounded("RANGER_SEARCH_TIMEOUT_SEC", 30, 1, 60),
            request_timeout_sec=bounded("RANGER_REQUEST_TIMEOUT_SEC", 10, 1, 30),
            clip_ttl_sec=int(bounded("RANGER_CLIP_TTL_SEC", 1800, 30, 7200)),
            secure_cookie=values.get("RANGER_SECURE_COOKIE", "false").lower() == "true",
            manifest_path=Path(values["RANGER_REFERENCE_MANIFEST"]) if values.get("RANGER_REFERENCE_MANIFEST") else None,
            static_dir=Path(values["RANGER_STATIC_DIR"]) if values.get("RANGER_STATIC_DIR") else None,
        )

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    ingress_url: str = field(default="", repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    search_timeout_sec: float = 12.0
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
        def bounded(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(os.environ.get(name, default))
                return value if low <= value <= high else default
            except ValueError:
                return default

        return cls(
            ingress_url=os.environ.get("INGRESS_URL", "").rstrip("/"),
            username=os.environ.get("USERNAME", ""),
            password=os.environ.get("PASSWORD", ""),
            search_timeout_sec=bounded("RANGER_SEARCH_TIMEOUT_SEC", 12, 1, 60),
            request_timeout_sec=bounded("RANGER_REQUEST_TIMEOUT_SEC", 10, 1, 30),
            clip_ttl_sec=int(bounded("RANGER_CLIP_TTL_SEC", 1800, 30, 7200)),
            secure_cookie=os.environ.get("RANGER_SECURE_COOKIE", "false").lower() == "true",
            manifest_path=Path(os.environ["RANGER_REFERENCE_MANIFEST"]) if os.environ.get("RANGER_REFERENCE_MANIFEST") else None,
            static_dir=Path(os.environ["RANGER_STATIC_DIR"]) if os.environ.get("RANGER_STATIC_DIR") else None,
        )

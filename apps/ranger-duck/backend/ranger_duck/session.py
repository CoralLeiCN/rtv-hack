from dataclasses import dataclass, field
import secrets
import time

from .errors import DemoError
from .evidence import Segment

COOKIE_NAME = "ranger_duck_session"


@dataclass
class SearchSnapshot:
    query: str
    segments: tuple[Segment, ...]
    elapsed_ms: int
    recorded_at: str
    started: float
    expires: float
    annotations: tuple[dict, ...] = ()
    query_reason: str = ''
    agent_summary: str = ''
    search_scope: dict = field(default_factory=dict)


@dataclass
class Session:
    expires: float
    clips: dict[str, tuple[str, float]] = field(default_factory=dict)
    searches: dict[tuple[str, bool], SearchSnapshot] = field(default_factory=dict)


class ClipRegistry:
    """Memory-only scoped capabilities. Run a single application worker."""
    def __init__(self, ttl: int, max_sessions: int):
        self.ttl, self.max_sessions = ttl, max_sessions
        self.sessions: dict[str, Session] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        for key in list(self.sessions):
            if self.sessions[key].expires <= now:
                del self.sessions[key]

    def session(self, supplied_id: str | None) -> str:
        self._prune()
        if supplied_id in self.sessions:
            self.sessions[supplied_id].expires = time.monotonic() + self.ttl
            return supplied_id
        if len(self.sessions) >= self.max_sessions:
            del self.sessions[min(self.sessions, key=lambda key: self.sessions[key].expires)]
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = Session(time.monotonic() + self.ttl)
        return session_id

    def add(self, session_id: str, source: str) -> str:
        clips = self.sessions[session_id].clips
        if len(clips) >= 60:
            del clips[next(iter(clips))]
        clip_id = secrets.token_urlsafe(24)
        clips[clip_id] = (source, time.monotonic() + self.ttl)
        return clip_id

    def remember(self, session_id: str, key: tuple[str, bool], snapshot: SearchSnapshot) -> None:
        searches = self.sessions[session_id].searches
        previous = searches.get(key)
        # An older slow request must not replace a newer recorded encounter.
        if previous is None or snapshot.started >= previous.started:
            searches[key] = snapshot

    def replay(self, session_id: str | None, key: tuple[str, bool]) -> SearchSnapshot:
        self._prune()
        session = self.sessions.get(session_id)
        snapshot = session.searches.get(key) if session else None
        if snapshot is None or snapshot.expires <= time.monotonic():
            raise DemoError("replay_unavailable", "Run a live search for this encounter and search scope before replaying it.", 409)
        return snapshot

    def resolve(self, session_id: str | None, clip_id: str) -> str:
        self._prune()
        session = self.sessions.get(session_id)
        entry = session.clips.get(clip_id) if session else None
        if not entry or entry[1] <= time.monotonic():
            raise DemoError("clip_not_found", "This clip is unavailable. Search again to refresh it.", 404)
        return entry[0]

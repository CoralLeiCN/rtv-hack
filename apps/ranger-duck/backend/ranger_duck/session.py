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
    actions: dict[str, dict] = field(default_factory=dict)
    protected_clips: dict[str, set[str]] = field(default_factory=dict)


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
                continue
            session = self.sessions[key]
            for group, clips in list(session.protected_clips.items()):
                retained = {clip for clip in clips if clip in session.clips and session.clips[clip][1] > now}
                if retained:
                    session.protected_clips[group] = retained
                else:
                    del session.protected_clips[group]

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
        session = self.sessions[session_id]
        clips = session.clips
        if len(clips) >= 60:
            protected = {clip for group in session.protected_clips.values() for clip in group
                         if clip in clips and clips[clip][1] > time.monotonic()}
            victim = next((clip for clip in clips if clip not in protected), None)
            if victim is None:
                raise DemoError('clip_capacity', 'Pause an existing run before requesting more clips.', 409)
            del clips[victim]
            session.actions.pop(victim, None)
        clip_id = secrets.token_urlsafe(24)
        clips[clip_id] = (source, time.monotonic() + self.ttl)
        return clip_id

    def protect(self, session_id: str, group: str, clip_ids: list[str]) -> None:
        # Unified runs cap this at three entries for each of eight runs. The
        # overall sixty-capability limit still applies to every browser session.
        session = self.sessions[session_id]
        if clip_ids:
            session.protected_clips[group] = set(clip_ids)
        else:
            session.protected_clips.pop(group, None)

    def release(self, session_id: str, group: str) -> None:
        session = self.sessions.get(session_id)
        if session:
            session.protected_clips.pop(group, None)

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

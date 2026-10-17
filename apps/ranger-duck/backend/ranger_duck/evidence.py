"""Normalize exact search segments and bind actions to reviewed evidence."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

MOTIONS = {
    "feeding": ("ground_pick", 8000),
    "walking": ("short_walk", 2000),
    "standing": ("stand_hold", 3000),
}
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def caption_hash(caption: str) -> str:
    # Preserve exact text: any caption revision requires renewed review.
    return hashlib.sha256(caption.encode("utf-8")).hexdigest()


def safe_text(value: object, limit: int = 4000) -> str:
    text = value if isinstance(value, str) else ""
    text = re.sub(r"(?:s3|https?|file)://[^\s<>\"']+", "[private source]", text, flags=re.I)
    text = re.sub(r"\bBearer\s+\S+", "[redacted]", text, flags=re.I)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[redacted]", text)
    return "".join(c for c in text if c >= " " or c in "\n\t")[:limit]


def valid_source(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 4096:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(parsed.scheme == "s3" and parsed.netloc and parsed.path.strip("/")
                and not parsed.query and not parsed.fragment and not parsed.username
                and not any(ord(c) < 32 for c in value))


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


@dataclass(frozen=True)
class Segment:
    source: str
    parent: str | None
    caption: str
    start: float | None
    end: float | None
    similarity: float | None
    dataset: str | None

    @property
    def complete(self) -> bool:
        return bool(self.parent and self.caption.strip() and self.start is not None
                    and self.end is not None and self.start >= 0 and self.end > self.start)

    @classmethod
    def parse(cls, raw: object) -> "Segment | None":
        if not isinstance(raw, dict) or not valid_source(raw.get("source")):
            return None
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        extra_metadata = raw.get("extra_metadata")
        if isinstance(extra_metadata, str):
            try:
                extra_metadata = json.loads(extra_metadata)
            except ValueError:
                extra_metadata = None
        extra_metadata = extra_metadata if isinstance(extra_metadata, dict) else {}
        dataset = raw.get("dataset") or metadata.get("dataset") or extra_metadata.get("dataset")
        return cls(
            source=raw["source"],
            parent=raw.get("original_video") if valid_source(raw.get("original_video")) else None,
            caption=raw.get("reasoning_content") if isinstance(raw.get("reasoning_content"), str) else "",
            start=number(raw.get("segment_start_sec")), end=number(raw.get("segment_end_sec")),
            similarity=number(raw.get("similarity_score")),
            dataset=safe_text(dataset, 100) or None,
        )

    def review_draft(self) -> dict:
        return {"reviewed": False, "evidence_id": "", "source": self.source,
                "original_video": self.parent, "segment_start_sec": self.start,
                "segment_end_sec": self.end, "caption": self.caption,
                "caption_sha256": caption_hash(self.caption), "animal": "", "behavior": "",
                "dataset": self.dataset, "source_label": "", "review_note": ""}


class Manifest:
    def __init__(self, entries: list[dict] | None = None, warning: str | None = None):
        self.warning = warning
        self.entries = []
        for item in entries or []:
            if not isinstance(item, dict) or item.get("reviewed") is not True:
                continue
            segment = Segment.parse({**item, "reasoning_content": item.get("caption")})
            if not segment or not segment.complete:
                continue
            if (not SAFE_ID.fullmatch(str(item.get("evidence_id", "")))
                    or item.get("caption_sha256") != caption_hash(segment.caption)
                    or not isinstance(item.get("animal"), str) or not item["animal"].strip()
                    or not isinstance(item.get("behavior"), str) or not item["behavior"].strip()):
                continue
            self.entries.append(item)
        ids = [item["evidence_id"] for item in self.entries]
        if len(set(ids)) != len(ids):
            self.entries = []
            self.warning = "The reference manifest contains duplicate evidence IDs; imitation is disabled."

    @classmethod
    def load(cls, path: Path | None) -> "Manifest":
        if path is None:
            return cls()
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("references"), list):
                raise ValueError
            return cls(data["references"])
        except (OSError, ValueError, TypeError):
            return cls(warning="The reference manifest could not be loaded; imitation is disabled.")

    def annotate(self, segment: Segment, animal: str) -> dict:
        result = {"review_status": "unreviewed", "eligibility_reason": "not_reviewed",
                  "animal": None, "reviewed_behavior": None, "action": None}
        if not segment.complete:
            return {**result, "eligibility_reason": "incomplete_metadata"}
        related = [item for item in self.entries if item["source"] == segment.source or (
            item["original_video"] == segment.parent and item["segment_start_sec"] == segment.start
            and item["segment_end_sec"] == segment.end)]
        if not related:
            return result
        exact = [item for item in related if item["source"] == segment.source
                 and item["original_video"] == segment.parent
                 and item["segment_start_sec"] == segment.start
                 and item["segment_end_sec"] == segment.end
                 and item["caption_sha256"] == caption_hash(segment.caption)]
        if len(related) != 1 or len(exact) != 1:
            return {**result, "review_status": "stale", "eligibility_reason": "reference_changed"}
        reference = exact[0]
        result.update(review_status="reviewed", animal=safe_text(reference["animal"], 100),
                      reviewed_behavior=safe_text(reference["behavior"], 100), _reference=reference)
        if reference["animal"].strip().casefold() != animal.casefold():
            return {**result, "eligibility_reason": "species_mismatch"}
        motion = MOTIONS.get(reference["behavior"])
        if motion is None:
            return {**result, "eligibility_reason": "unsupported_behavior"}
        return {**result, "eligibility_reason": "reviewed_match", "action": {
            "primitive": motion[0], "evidence_id": reference["evidence_id"], "max_duration_ms": motion[1]},
            "_reference": reference}


def normalize_segments(raw_results: list) -> list[Segment]:
    """Deduplicate sources, then put one hit per parent before repeat parents."""
    segments, seen_sources = [], set()
    for raw in raw_results[:100]:
        segment = Segment.parse(raw)
        if segment and segment.source not in seen_sources:
            seen_sources.add(segment.source)
            segments.append(segment)
    first, repeat, seen_parents = [], [], set()
    for segment in segments:
        parent = segment.parent or segment.source
        (repeat if parent in seen_parents else first).append(segment)
        seen_parents.add(parent)
    return (first + repeat)[:15]

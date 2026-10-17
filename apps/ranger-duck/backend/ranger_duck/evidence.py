"""Preserve retrieval rank and bind bounded actions to exact video evidence."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from .interaction import classify_interaction, has_species_pair

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
    rank: int = 1
    dataset_id: str | None = None

    @property
    def complete(self) -> bool:
        return bool(self.parent and self.caption.strip() and self.start is not None
                    and self.end is not None and self.start >= 0 and self.end > self.start)

    @classmethod
    def parse(cls, raw: object, rank: int = 1) -> "Segment | None":
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
        dataset_id = raw.get("dataset_id") or metadata.get("dataset_id") or extra_metadata.get("dataset_id")
        return cls(
            source=raw["source"],
            parent=raw.get("original_video") if valid_source(raw.get("original_video")) else None,
            caption=raw.get("reasoning_content") if isinstance(raw.get("reasoning_content"), str) else "",
            start=number(raw.get("segment_start_sec")), end=number(raw.get("segment_end_sec")),
            similarity=number(raw.get("similarity_score")),
            dataset=safe_text(dataset, 100) or None,
            rank=rank,
            dataset_id=safe_text(dataset_id, 100) or None,
        )

    def review_draft(self) -> dict:
        return {"reviewed": False, "evidence_id": "", "source": self.source,
                "original_video": self.parent, "segment_start_sec": self.start,
                "segment_end_sec": self.end, "caption": self.caption,
                "caption_sha256": caption_hash(self.caption), "animal": "", "behavior": "",
                "interaction_partner": "", "interaction_evidence": "",
                "dataset": self.dataset, "dataset_id": self.dataset_id, "source_label": "", "review_note": ""}


class Manifest:
    def __init__(self, entries: list[dict] | None = None, warning: str | None = None):
        self.warning = warning
        self.entries = []
        for item in entries or []:
            if not isinstance(item, dict) or item.get("reviewed") is not True:
                continue
            segment = Segment.parse({**item, "reasoning_content": item.get("caption")})
            if not segment or not segment.complete:
                self.warning = "The reference manifest contains invalid reviewed evidence; imitation is disabled."
                continue
            if (not SAFE_ID.fullmatch(str(item.get("evidence_id", "")))
                    or item.get("caption_sha256") != caption_hash(segment.caption)
                    or not isinstance(item.get("animal"), str) or not item["animal"].strip()
                    or not isinstance(item.get("behavior"), str) or not item["behavior"].strip()
                    or not isinstance(item.get("interaction_partner", ""), str)
                    or not isinstance(item.get("interaction_evidence", ""), str)):
                self.warning = "The reference manifest contains invalid reviewed evidence; imitation is disabled."
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

    def annotate_interaction(self, segment: Segment, animal: str, partner: str) -> dict:
        """A scenario selects retrieval scope, never the action for a returned clip."""
        annotation = self.annotate(segment, animal)
        result = {**annotation, "action": None, "action_basis": None,
                  "inferred_behavior": None, "action_reason": None, "interaction_partner": None}
        if self.warning:
            return {**result, "eligibility_reason": "invalid_review_manifest"}
        if annotation["eligibility_reason"] in {
            "incomplete_metadata", "reference_changed", "species_mismatch", "unsupported_behavior"
        }:
            return result
        reference = annotation.get("_reference")
        if reference and annotation["action"]:
            # The user permits solitary behavior evidence. An exact existing
            # pose review therefore remains valid without a partner assertion.
            explanations = {
                "feeding": "The exact human review identifies feeding; the duck approximates it with a beak dip.",
                "walking": "The exact human review identifies walking; the duck makes a short walk.",
                "standing": "The exact human review identifies standing; the duck holds a steady pose.",
            }
            return {**result, "action": annotation["action"], "action_basis": "reviewed",
                    "action_reason": explanations[reference["behavior"]],
                    "interaction_partner": safe_text(reference.get("interaction_partner"), 100) or None}
        match, reason = classify_interaction(segment.caption, animal)
        if not match:
            return {**result, "eligibility_reason": reason}
        behavior, primitive, duration, explanation = match
        binding = json.dumps([segment.source, segment.parent, segment.start, segment.end,
                              caption_hash(segment.caption)], separators=(",", ":"))
        evidence_id = "caption-" + hashlib.sha256(binding.encode()).hexdigest()[:32]
        return {**result, "review_status": "unreviewed", "eligibility_reason": "caption_behavior_match",
                "action_basis": "video_caption", "inferred_behavior": behavior,
                "animal": animal, "action_reason": explanation,
                "interaction_partner": animal if has_species_pair(segment.caption, animal) else None,
                "action": {"primitive": primitive, "evidence_id": evidence_id, "max_duration_ms": duration}}


def normalize_segments(raw_results: list) -> list[Segment]:
    """Deduplicate sources without reranking or promoting invalid/duplicate hits."""
    segments, seen_sources = [], set()
    for rank, raw in enumerate(raw_results[:100], start=1):
        segment = Segment.parse(raw, rank)
        if segment and segment.source not in seen_sources:
            seen_sources.add(segment.source)
            segments.append(segment)
    return segments[:15]

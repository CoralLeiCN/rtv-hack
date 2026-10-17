"""Interaction grounding must come from each actual ranked caption, not a query."""
import json

import pytest

from ranger_duck.evidence import Manifest, Segment, normalize_segments
from ranger_duck.interaction import classify_interaction
from test_backend import PAYLOAD, ROW, Upstream, make_client, reviewed, search


@pytest.mark.parametrize("animal,caption,behavior,primitive", [
    ("cat", "Two cats face each other. One cat hisses at another cat.", "hissing_boundary", "stand_hold"),
    ("cat", "Two cats hiss at each other without moving.", "hissing_boundary", "stand_hold"),
    ("cat", "One cat approaches another cat.", "social_approach", "short_walk"),
    ("cat", "Two cats greet each other and sniff each other.", "social_approach", "short_walk"),
    ("cat", "Two cats playfully chase each other.", "social_play", "short_walk"),
    ("cat", "Two cats play with each other.", "social_play", "short_walk"),
    ("cat", "Two cats look directly at each other.", "orienting_to_partner", "head_scan"),
    ("cat", "A gray cat jumps while a white cat watches the gray cat.", "watching_partner", "head_scan"),
    ("cat", "Two cats are visible. One cat jumps while the other watches it.", "watching_partner", "head_scan"),
    ("cat", "Two cats are visible. One cat turns its head toward the white one.", "orienting_to_partner", "head_scan"),
    ("cat", "Two silver spotted cats bat at a toy. Both cats are moving their bodies and heads to follow the toy.", "shared_attention", "head_scan"),
    ("cat", "Two cats face each other. One cat looks at a toy while sitting beside the other cat.", "object_attention", "head_scan"),
    ("cat", "Two cats sit together. The white cat looks up.", "focal_head_movement", "head_scan"),
    ("cat", "Two cats sit together. One walks across the room.", "focal_walking", "short_walk"),
    ("cat", "A gray cat stands while a tabby cat observes the gray cat. The gray cat turns its head to look at the tabby cat.", "orienting_to_partner", "head_scan"),
    ("deer", "Two deer graze together side by side.", "co_feeding", "ground_pick"),
    ("deer", "One deer follows another deer.", "following", "short_walk"),
    ("deer", "Two deer freeze together, both alert.", "group_alert", "stand_hold"),
    ("deer", "Two deer stand still together.", "group_alert", "stand_hold"),
    ("deer", "Two deer graze on opposite sides of a field.", "focal_foraging", "ground_pick"),
    ("deer", "Two deer graze next to each other.", "co_feeding", "ground_pick"),
])
def test_explicit_same_species_interactions_map_to_bounded_approximations(animal, caption, behavior, primitive):
    match, reason = classify_interaction(caption, animal)
    assert reason == "caption_interaction_match"
    assert match[0:2] == (behavior, primitive)
    assert match[2] <= 8000 and match[3]


@pytest.mark.parametrize("animal,caption", [
    ("cat", "A cat hisses at a dog."),
    ("cat", "Two dogs hiss at each other."),
    ("cat", "Two cats hiss at another dog."),
    ("cat", "Two cats hiss at the other dog."),
    ("cat", "Two cats stand nearby. One cat jumps at a feather toy."),
    ("cat", "Two cats bat at a toy independently."),
    ("cat", "Two cats playfully pounce at each other."),
    ("cat", "Two cats chase each other but this is not play."),
    ("cat", "Two cats chase each other, possibly playfully."),
    ("cat", "Two cats play with each other by jumping and pouncing."),
    ("cat", "Two cats climb a scratching post together."),
    ("cat", "Two cats sit near a feather toy. One watches it."),
    ("cat", "Two cats sit nearby. One does not look up."),
    ("cat", "Two cats sit nearby. One may walk across the room."),
    ("cat", "Two cats face each other. One cat hisses at a camera while sitting beside the other cat."),
    ("cat", "Two cats appear to look at each other."),
    ("cat", "Two cats seem to be hissing at each other."),
    ("cat", "Two cats fight and bite each other."),
    ("cat", "Two cats chase each other aggressively."),
    ("cat", "Two cats face each other. One cat backs away from the other cat."),
    ("cat", "Two cats do not hiss at each other."),
    ("cat", "Two cats hissing at each other is not shown."),
    ("cat", "Two cats sit nearby. A dog backs away from the other cat."),
    ("cat", "Two cats watch two deer grazing together."),
    ("cat", "Two cats never approach each other."),
    ("cat", "Two cats may greet each other."),
    ("cat", "Two cats are possibly playing with each other."),
    ("cat", "There are not two cats playing with each other."),
    ("cat", "A solitary cat is hissing."),
    ("cat", "A cat sits without another cat nearby. The cat looks up."),
    ("cat", "A cat sits beside an empty chair, and no other cat is present. The cat looks up."),
    ("deer", "A deer lowers its head to feed."),
    ("deer", "Two cats greet each other."),
    ("deer", "Two deer are not grazing together."),
    ("deer", "Two deer stand together while one deer feeds alone."),
    ("deer", "Two deer stand together while only one deer stands alert."),
])
def test_solitary_wrong_partner_unsupported_and_negated_evidence_stays_ineligible(animal, caption):
    match, reason = classify_interaction(caption, animal)
    assert match is None and reason != "caption_interaction_match"


def test_search_uses_each_ranked_caption_even_if_it_differs_from_encounter_hint():
    captions = ["Two cats hiss at each other.", "One cat follows another cat.",
                "Two cats face each other. One cat backs away from the other cat."]
    rows = [{**ROW, "source": f"s3://test-segments/cat-{i}.mp4", "reasoning_content": caption}
            for i, caption in enumerate(captions)]
    client, upstream, _ = make_client(Upstream(rows))
    with client:
        result = client.post("/demo-api/search", json={**PAYLOAD, "scenario_id": "cat-greeting"}).json()
    assert result["status"] == "ok" and result["match_type"] == "species_interaction"
    assert [item["rank"] for item in result["candidates"]] == [1, 2, 3]
    assert [item["action"]["primitive"] if item["action"] else None for item in result["candidates"]] == ["stand_hold", "short_walk", None]
    assert result["candidates"][2]["eligibility_reason"] == "unsupported_retreat"
    assert all(item["action_basis"] == "video_caption" and item["review_status"] == "unreviewed"
               for item in result["candidates"][:2])
    assert all(item["interaction_partner"] == "cat" for item in result["candidates"][:2])
    assert result["warnings"]
    sent = json.loads(next(r.content for r in upstream.requests if r.url.path.endswith("/search")))
    assert sent["tags"] == [] and "another cat" in sent["query"]
    # Grounding consumes existing captions only; no second reasoning request.
    assert sum(r.url.path.endswith("/search") for r in upstream.requests) == 1
    rendered = json.dumps(result)
    assert "s3://" not in rendered and "test-secret" not in rendered


def test_missing_or_duplicate_top_three_slots_are_not_filled_from_rank_four():
    eligible = {**ROW, "source": "s3://test-segments/four.mp4", "reasoning_content": "Two deer graze together."}
    rows = [ROW, ROW, {"source": "https://invalid.test"}, eligible]
    assert [s.rank for s in normalize_segments(rows)] == [1, 4]
    client, _, _ = make_client(Upstream(rows))
    with client:
        result = search(client)
    assert result["status"] == "no_supported_imitation"
    assert result["candidates"][0]["action"] is None
    assert result["candidates"][1]["rank"] == 4 and result["candidates"][1]["action"]


def test_retreat_is_not_silently_replaced_with_a_hissing_pause():
    caption = "Two cats face each other. One cat hisses at the other cat and backs away from the other cat."
    match, reason = classify_interaction(caption, "cat")
    assert match is None and reason == "unsupported_retreat"


def test_caption_action_is_bound_to_exact_provenance_and_legacy_review_is_not_promoted():
    row = {**ROW, "reasoning_content": "Two deer graze together."}
    segment = Segment.parse(row)
    manifest = Manifest([reviewed(row)])
    action = manifest.annotate_interaction(segment, "deer", "deer")
    assert action["action_basis"] == "video_caption" and action["review_status"] == "unreviewed"
    assert action["action"]["evidence_id"] != "ref-01"
    assert action["action"] == Manifest().annotate_interaction(segment, "deer", "deer")["action"]
    changed = Segment.parse({**row, "segment_end_sec": 6})
    assert Manifest().annotate_interaction(changed, "deer", "deer")["action"] != action["action"]
    assert manifest.annotate_interaction(changed, "deer", "deer")["action"] is None
    assert Manifest([reviewed()]).annotate_interaction(Segment.parse(ROW), "deer", "deer")["action"] is None


@pytest.mark.parametrize("override", [{"animal": "cat"}, {"interaction_partner": "cat"}, {"behavior": "jumping"}])
def test_contradictory_review_cannot_be_bypassed_by_a_matching_caption(override):
    row = {**ROW, "reasoning_content": "Two deer graze together."}
    manifest = Manifest([reviewed(row, **override)])
    assert manifest.annotate_interaction(Segment.parse(row), "deer", "deer")["action"] is None


@pytest.mark.parametrize("override", [{"caption_sha256": "invalid"}, {"interaction_partner": 2}])
def test_invalid_review_cannot_disappear_and_enable_caption_fallback(override):
    row = {**ROW, "reasoning_content": "Two deer graze together."}
    manifest = Manifest([reviewed(row, **override)])
    annotation = manifest.annotate_interaction(Segment.parse(row), "deer", "deer")
    assert annotation["action"] is None and annotation["eligibility_reason"] == "invalid_review_manifest"


def test_broadening_keeps_cat_pair_and_authorized_search_scope():
    client, upstream, _ = make_client()
    with client:
        response = client.post("/demo-api/search", json={**PAYLOAD, "scenario_id": "cat-play", "broaden": True})
        catalog = client.get("/demo-api/encounters").json()["encounters"]
    sent = json.loads(next(r.content for r in upstream.requests if r.url.path.endswith("/search")))
    assert response.json()["query"] == sent["query"] == "Two cats interacting with each other"
    assert sent["tags"] == [] and sent["include_public"] is True
    assert all(s["role"] == "focal_animal" and s["animal"] == s["interaction_partner"] for s in catalog)

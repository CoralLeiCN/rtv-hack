"""Interaction grounding must come from each actual ranked caption, not a query."""
import json

import pytest

from ranger_duck.evidence import Manifest, Segment, normalize_segments
from ranger_duck.interaction import classify_interaction, has_species_pair
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
    ("cat", "A solitary cat is hissing.", "focal_hissing", "stand_hold"),
    ("cat", "A cat looks up.", "focal_head_movement", "head_scan"),
    ("cat", "A cat walks across a room.", "focal_walking", "short_walk"),
    ("cat", "A cat watches a feather toy.", "object_attention", "head_scan"),
    ("cat", "A cat watches it.", "focal_attention", "head_scan"),
    ("cat", "A cat stands quietly.", "focal_standing", "stand_hold"),
    ("cat", "Two cats stand nearby. One cat jumps at a feather toy.", "focal_standing", "stand_hold"),
    ("cat", "Two cats sit near a feather toy. One watches it.", "focal_attention", "head_scan"),
    ("cat", "Two cats face each other. One cat hisses at a camera while sitting beside the other cat.", "focal_sitting", "sit_cycle"),
    ("cat", "A cat sits down.", "focal_sitting", "sit_cycle"),
    ("cat", "A cat remains seated.", "focal_sitting", "sit_cycle"),
    ("cat", "A cat is sitting without moving.", "focal_sitting", "sit_cycle"),
    ("cat", "A cat nods.", "focal_head_nod", "head_nod"),
    ("cat", "A cat raises its head.", "focal_head_nod", "head_nod"),
    ("cat", "A cat moves its head up and down.", "focal_head_nod", "head_nod"),
    ("deer", "A deer lowers its head.", "focal_head_nod", "head_nod"),
    ("deer", "A deer lowers its head to feed.", "focal_foraging", "ground_pick"),
    ("deer", "A deer stands still.", "focal_standing", "stand_hold"),
    ("deer", "Two deer stand together while one deer feeds alone.", "focal_foraging", "ground_pick"),
    ("deer", "Two deer stand together while only one deer stands alert.", "focal_standing", "stand_hold"),
])
def test_explicit_species_behaviors_map_to_bounded_approximations(animal, caption, behavior, primitive):
    match, reason = classify_interaction(caption, animal)
    assert reason == "caption_behavior_match"
    assert match[0:2] == (behavior, primitive)
    assert match[2] <= 8000 and match[3]


@pytest.mark.parametrize("animal,caption", [
    ("cat", "A cat hisses at a dog."),
    ("cat", "Two dogs hiss at each other."),
    ("cat", "Two cats hiss at another dog."),
    ("cat", "Two cats hiss at the other dog."),
    ("cat", "Two cats bat at a toy independently."),
    ("cat", "Two cats playfully pounce at each other."),
    ("cat", "Two cats chase each other but this is not play."),
    ("cat", "Two cats chase each other, possibly playfully."),
    ("cat", "Two cats play with each other by jumping and pouncing."),
    ("cat", "Two cats climb a scratching post together."),
    ("cat", "Two cats are visible. One does not look up."),
    ("cat", "Two cats are visible. One may walk across the room."),
    ("cat", "Two cats appear to look at each other."),
    ("cat", "Two cats seem to be hissing at each other."),
    ("cat", "Two cats fight and bite each other."),
    ("cat", "Two cats chase each other aggressively."),
    ("cat", "Two cats face each other. One cat backs away from the other cat."),
    ("cat", "Two cats do not hiss at each other."),
    ("cat", "Two cats hissing at each other is not shown."),
    ("cat", "Two cats are visible. A dog backs away from the other cat."),
    ("cat", "Two cats watch two deer grazing together."),
    ("cat", "Two cats never approach each other."),
    ("cat", "Two cats may greet each other."),
    ("cat", "Two cats are possibly playing with each other."),
    ("cat", "There are not two cats playing with each other."),
    ("deer", "Two cats greet each other."),
    ("deer", "Two deer are not grazing together."),
    ("deer", "A deer does not feed."),
    ("deer", "A deer may walk across the clearing."),
    ("cat", "A cat is visible."),
    ("cat", "A cat does not stand."),
    ("cat", "A cat jumps at a feather toy."),
    ("cat", "A cat walks backwards."),
    ("cat", "A cat lies down."),
    ("cat", "A cat does not sit down."),
    ("cat", "A cat may sit down."),
    ("cat", "A cat does not nod."),
    ("cat", "A cat may raise its head."),
    ("cat", "A cat is visible. A person nods."),
    ("cat", "A dog is walking."),
    ("deer", "No deer is visible. A dog walks across the frame."),
    ("deer", "A deer is near a feeding station."),
])
def test_wrong_species_unsupported_and_negated_evidence_stays_ineligible(animal, caption):
    match, reason = classify_interaction(caption, animal)
    assert match is None and reason != "caption_behavior_match"


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


def test_compatible_rank_four_enables_actions_after_invalid_or_duplicate_hits():
    eligible = {**ROW, "source": "s3://test-segments/four.mp4", "reasoning_content": "Two deer graze together."}
    unsupported = {**ROW, "reasoning_content": "A deer jumps over a fence."}
    rows = [unsupported, unsupported, {"source": "https://invalid.test"}, eligible]
    assert [s.rank for s in normalize_segments(rows)] == [1, 4]
    client, _, _ = make_client(Upstream(rows))
    with client:
        result = search(client)
    assert result["status"] == "ok"
    assert result["candidates"][0]["action"] is None
    assert result["candidates"][1]["rank"] == 4 and result["candidates"][1]["action"]


def test_retreat_is_not_silently_replaced_with_a_hissing_pause():
    caption = "Two cats face each other. One cat hisses at the other cat and backs away from the other cat."
    match, reason = classify_interaction(caption, "cat")
    assert match is None and reason == "unsupported_retreat"


@pytest.mark.parametrize("caption,primitive", [
    ("A cat watches a toy. The cat then walks across the room.", "short_walk"),
    ("A cat walks across the room. The cat then watches a toy.", "short_walk"),
    ("A cat stands still and looks around. The cat starts eating.", "ground_pick"),
    ("Two cats look at each other. One cat hisses at another cat. The other cat follows the first cat.", "short_walk"),
    ("A cat looks around. The cat does not walk across the room.", "head_scan"),
    ("A cat stands still. The cat may walk across the room.", "stand_hold"),
    ("A cat does not walk, but looks around.", "head_scan"),
    ("A cat stands beside a toy. The toy moves forward.", "stand_hold"),
    ("A cat watches a toy that moves forward.", "head_scan"),
    ("A cat stands still. A toy moves past the cat and moves forward.", "stand_hold"),
    ("A cat watches a toy. A person walks across the room.", "head_scan"),
    ("A cat stands still. A dog is walking.", "stand_hold"),
    ("A cat watches a toy. It moves forward.", "head_scan"),
    ("A cat is visible. It walks across the room.", "short_walk"),
    ("A cat walks backwards. The cat then looks around.", "head_scan"),
    ("A cat stands still. The cat then sits down.", "sit_cycle"),
    ("A cat sits down. The cat then looks around.", "head_scan"),
    ("A cat sits down. The cat raises its head.", "head_nod"),
    ("A cat raises its head. The cat then walks forward.", "short_walk"),
    ("A cat sits down. The cat does not nod.", "sit_cycle"),
    ("Two cats face each other. One cat retreats from the other cat. The other cat walks across the room.", "short_walk"),
])
def test_most_active_supported_animal_behavior_wins_across_caption(caption, primitive):
    match, reason = classify_interaction(caption, "cat")
    assert reason == "caption_behavior_match"
    assert match[1] == primitive


def test_attention_does_not_hide_walking_in_a_multi_animal_toy_caption():
    caption = (
        "Two cats are visible, a gray cat on the left and a white cat with black spots on the right. "
        "Both cats are sitting on a blue floor. The gray cat stands up and moves towards the left side. "
        "The white cat remains seated and looks up. A red feather toy is above the white cat. "
        "The gray cat jumps and tries to catch the toy. The white cat watches the gray cat's actions."
    )
    match, _ = classify_interaction(caption, "cat")
    assert match[:2] == ("focal_walking", "short_walk")


def test_active_caption_preference_does_not_override_an_exact_human_review():
    row = {**ROW, "reasoning_content": "A deer stands still, then walks across the clearing."}
    manifest = Manifest([reviewed(row, behavior="standing")])
    item = manifest.annotate_interaction(Segment.parse(row), "deer", "deer")
    assert item["action_basis"] == "reviewed"
    assert item["action"]["primitive"] == "stand_hold"


def test_caption_action_is_bound_to_exact_provenance_and_exact_legacy_review_remains_valid():
    row = {**ROW, "reasoning_content": "Two deer graze together."}
    segment = Segment.parse(row)
    manifest = Manifest([reviewed(row)])
    action = Manifest().annotate_interaction(segment, "deer", "deer")
    assert action["action_basis"] == "video_caption" and action["review_status"] == "unreviewed"
    assert action["action"]["evidence_id"] != "ref-01"
    assert action["action"] == Manifest().annotate_interaction(segment, "deer", "deer")["action"]
    changed = Segment.parse({**row, "segment_end_sec": 6})
    assert Manifest().annotate_interaction(changed, "deer", "deer")["action"] != action["action"]
    assert manifest.annotate_interaction(changed, "deer", "deer")["action"] is None
    reviewed_action = Manifest([reviewed()]).annotate_interaction(Segment.parse(ROW), "deer", "deer")
    assert reviewed_action["action_basis"] == "reviewed" and reviewed_action["review_status"] == "reviewed"
    assert reviewed_action["action"]["evidence_id"] == "ref-01"
    assert reviewed_action["interaction_partner"] is None


@pytest.mark.parametrize("override", [{"animal": "cat"}, {"behavior": "jumping"}])
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


def test_all_retrieved_candidates_are_available_for_first_three_compatible_selection():
    rows = [{**ROW, "source": f"s3://test-segments/rank-{rank}.mp4",
             "reasoning_content": "A deer jumps over a fence."} for rank in range(1, 16)]
    for rank, caption in [(4, "A deer grazes."), (7, "A deer walks."),
                          (13, "A deer stands still."), (15, "A deer looks around.")]:
        rows[rank - 1]["reasoning_content"] = caption
    client, _, _ = make_client(Upstream(rows))
    with client:
        result = search(client)
    compatible = [item for item in result["candidates"] if item["action"]]
    assert result["status"] == "ok" and len(result["candidates"]) == 15
    assert [item["rank"] for item in compatible] == [4, 7, 13, 15]
    assert [item["rank"] for item in compatible[:3]] == [4, 7, 13]


@pytest.mark.parametrize("caption", [
    "A cat sits without another cat nearby. The cat looks up.",
    "A cat sits beside an empty chair, and no other cat is present. The cat looks up.",
])
def test_solitary_motion_is_eligible_without_inventing_a_partner(caption):
    assert not has_species_pair(caption, "cat")
    row = {**ROW, "reasoning_content": caption}
    item = Manifest().annotate_interaction(Segment.parse(row), "cat", "cat")
    assert item["action"]["primitive"] == "head_scan" and item["interaction_partner"] is None
    assert item["eligibility_reason"] == "caption_behavior_match"

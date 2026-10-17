"""Conservative, deterministic interpretations of existing video-model captions.

This is not a video model or a visual review. A clip must identify the selected
species and a supported behavior; a second animal is optional. Unsupported
wording stays playable but never becomes a motion. Scenario names and search
text are not inputs, so a hit cannot acquire requested behavior by association.
"""
import re

Motion = tuple[str, str, int, str]
NEGATIVE = re.compile(r"\b(?:no|not|never|neither|cannot|can't|doesn't|don't|isn't|aren't|wasn't|weren't|without)\b")
UNCERTAIN = re.compile(r"\b(?:may|might|could|possibly|perhaps|probably|unclear|uncertain|seems?|appears?)\b")
ADJECTIVE = r"(?:domestic|adult|young|small|large|black|white|gray|grey|brown|tabby|spotted|red|wild|striped|silver|golden|cream|orange|ginger)"
AMBIGUOUS_OBJECT = re.compile(r"\b(?:toys?|balls?|feathers?|objects?|cameras?|food|bowls?|strings?|lasers?|hands?|posts?|mirrors?)\b")


def _positive(pattern: str, text: str, *, reject_inside: re.Pattern | None = None) -> tuple[bool, bool]:
    """Check the local predicate, retaining whether a candidate was negated."""
    rejected = False
    for match in re.finditer(pattern, text):
        if reject_inside and reject_inside.search(match.group()):
            rejected = True
            continue
        prefix = " ".join(text[:match.start()].split()[-6:])
        # A contrast starts a new claim: 'not hissing, but backing away'.
        prefix = re.split(r"\bbut\b|[;,]", prefix)[-1]
        denied_visibility = re.search(r"\b(?:is|are|was|were)\s+(?:not|never)\s+(?:seen|shown|visible|observed)\b", text[match.end():])
        if NEGATIVE.search(prefix) or UNCERTAIN.search(prefix) or denied_visibility:
            rejected = True
            continue
        return True, rejected
    return False, rejected


def has_species_pair(text: str, animal: str) -> bool:
    if animal not in {"cat", "deer"}:
        return False
    text = text.casefold().replace("’", "'")
    noun = r"(?:cats?|kittens?)" if animal == "cat" else r"deer"
    plural = r"(?:cats|kittens)" if animal == "cat" else r"deer"
    # The broad 'cat ... another cat' form must not turn an explicitly absent
    # companion into a pair. Negation of a verb ('does not chase another cat')
    # is separate from denying the second animal's presence.
    denied_companion = re.compile(
        rf"\b(?:no|without|not)\s+(?:any\s+)?(?:another|other|second|companion)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}\b"
    )
    patterns = [
        rf"\b(?:two|three|four|five|six|2|3|4|several|multiple|both)\s+(?:{ADJECTIVE}\s+){{0,2}}{plural}\b",
        rf"\b(?:pair|group|herd)\s+of\s+(?:{ADJECTIVE}\s+){{0,2}}{plural}\b",
        rf"\b{noun}\b[^.!?]{{0,100}}\b(?:another|other|second|companion)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}\b",
        rf"\b{plural}\b[^.!?]{{0,160}}\b(?:each other|one another)\b",
        rf"\b(?:a|one)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}\b[^.!?]{{0,180}}\b(?:a|another|second)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}\b",
    ]
    return any(_positive(pattern, text, reject_inside=denied_companion)[0] for pattern in patterns)


def classify_interaction(caption: str, animal: str) -> tuple[Motion | None, str]:
    if animal not in {"cat", "deer"}:
        return None, "unsupported_species"
    text = re.sub(r"\s+", " ", caption.casefold().replace("’", "'")).strip()
    species = r"\b(?:cats?|kittens?)\b" if animal == "cat" else r"\bdeer\b"
    if not _positive(species, text)[0]:
        return None, "species_not_established"
    paired = has_species_pair(text, animal)
    noun = r"(?:cat|kitten)" if animal == "cat" else "deer"
    # Pronouns are accepted only after the caption has explicitly established
    # two animals of the requested species. A dog/person target does not match.
    partner = (rf"(?:each other|one another|(?:a |the |its |their )?(?:other|second|companion)\s+{noun}"
               rf"|another\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}"
               rf"|(?:a|the)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}"
               rf"|(?:the\s+)?{ADJECTIVE}\s+one"
               r"|the other(?: one)?(?=[,;:.!?]|$|'s\b|\s+(?:and|while|as|before|after|that)\b))")
    # 'It' is useful in captions that name two animals, but cannot safely refer
    # to a companion when the same caption also describes a toy or another
    # salient object. Explicit animal targets remain usable in those clips.
    attention_partner = partner
    if paired and not AMBIGUOUS_OBJECT.search(text):
        attention_partner = rf"(?:{partner}|it|its\s+(?:actions|movements)|them|their\s+(?:actions|movements))"
    directed = rf"\b(?:at|towards?|to|with|from|beside|alongside|behind|past)\s+{partner}\b"
    collective = r"\b(?:together|side by side|both|in unison|as a (?:group|herd)|each other|one another)\b"
    direction_modifier = r"(?:\s+(?:directly|briefly|slowly|calmly|curiously|back|to|look|looking)){0,4}"
    group_subject = rf"(?:both(?:\s+{noun}s?)?|two\s+(?:{ADJECTIVE}\s+)?(?:cats|kittens|deer))"
    auxiliary = r"(?:\s+(?:are|were|remain|continue|quietly|calmly|slowly|still)){0,3}\s+"
    feeding = r"(?:graz(?:e|es|ing)|feed(?:s|ing)?|forag(?:e|es|ing)|eat(?:s|ing)?)"
    alert = r"(?:alert|freez(?:e|es|ing)|froze|stand(?:s|ing)?\s+(?:still|motionless))"
    shared = r"(?:together|side by side|in unison|(?:beside|alongside|near|next to)\s+(?:each other|one another))"
    attention_object = r"(?:the|a|an)\s+(?:(?:red|blue|small|moving|feather|hanging)\s+){0,3}(?:toy|ball|feather|string|laser|object)"
    def collective_predicate(verb: str, group_subject_allowed: bool = True) -> str:
        together = rf"{verb}\s+(?:(?:quietly|calmly|slowly)\s+)?{shared}"
        return rf"\b(?:{group_subject}{auxiliary}{verb}|{together})\b" if group_subject_allowed else rf"\b{together}\b"
    phrases = re.split(r"[.!?\n]+", text)
    retreat = r"\b(?:backs?|backing|steps?|stepping|moves?|moving)\s+(?:slowly\s+)?(?:away|back(?:wards?)?)\b|\bretreat(?:s|ing)?\b"
    for phrase in phrases:
        if _positive(retreat, phrase)[0] and re.search(directed, phrase):
            # The tested policy cannot execute a reliable backward step. Keep
            # the reference visible; do not relabel retreat as a stationary hiss.
            return None, "unsupported_retreat"
    had_negation = False
    # Prefer explicit partner orientation over a static approximation. This order is
    # about interpreting one clip; result ranking itself is never changed.
    rules: list[tuple[str, str, int, str, str, str]] = [
        ("orienting_to_partner", "head_scan", 2400,
         rf"\b(?:looks?|looking|(?:turns?|turning)\s+(?:(?:its|their|the)\s+)?head){direction_modifier}\s+(?:towards?|at)\s+{attention_partner}\b",
         "directed_verb", "The caption describes orienting toward the other animal; the duck makes a small head scan."),
        ("hissing_boundary", "stand_hold", 3000,
         rf"\bhiss(?:es|ing)?(?:\s+(?:directly|loudly|briefly|softly)){{0,2}}\s+(?:at|towards?)\s+{partner}\b", "directed_verb",
         "The caption describes a hiss directed at the other cat; a still boundary pause approximates it. The duck does not produce a hiss."),
        ("following", "short_walk", 2000,
         rf"\b(?:follow(?:s|ing)?|(?:walk(?:s|ing)?|mov(?:es?|ing))\s+(?:behind|after))\s+{partner}\b", "directed_verb",
         "The caption describes following the other animal; the duck makes a short forward walk."),
        ("social_approach", "short_walk", 2000,
         rf"\b(?:approach(?:es|ing)?|sniff(?:s|ing)?|greet(?:s|ing)?|nuzzl(?:es?|ing)|rub(?:s|bing)\s+against)\s+{partner}\b",
         "directed_verb", "The caption describes approaching or greeting the other animal; a short walk approximates the approach, not facial contact."),
        ("social_play", "short_walk", 2000,
         rf"\b(?:chas(?:es?|ing)|playfully\s+follow(?:s|ing)?)\s+{partner}\b",
         "play", "The caption describes movement during play with the other animal; a short walk approximates it, without jumping or contact."),
        ("social_play", "short_walk", 2000,
         rf"\bplay(?:s|ing)?\s+(?:with\s+{partner}|together)\b",
         "general_play", "The caption explicitly describes the animals playing with each other; the duck uses a short walk as a simplified play movement, not an exact replay of their poses."),
        ("watching_partner", "head_scan", 2400,
         rf"\b(?:watch(?:es|ing)?|observ(?:es?|ing))\s+{attention_partner}\b",
         "directed_verb", "The caption describes one animal watching its companion; the duck makes an attentive head turn as an approximation of that attention, rather than remaining motionless."),
        ("shared_attention", "head_scan", 2400,
         rf"\b(?:turn(?:s|ing)?|mov(?:es?|ing)|tilt(?:s|ing)?)\s+their\s+(?:bodies\s+and\s+)?heads\s+(?:to\s+)?(?:follow|watch|look\s+at)\s+{attention_object}\b",
         "directed_verb", "The caption describes the animals moving their heads to attend to a shared object; the duck makes an attentive head turn. This copies shared object attention, not a greeting or attention to each other."),
        ("object_attention", "head_scan", 2400,
         rf"\b(?:looks?|looking|watch(?:es|ing)?|observ(?:es?|ing))(?:\s+(?:up|down|directly))?\s+(?:at\s+)?{attention_object}\b",
         "directed_verb", "The caption describes the animal attending to an object; the duck approximates that attention with a head turn. This does not imply attention to another animal."),
        ("focal_head_movement", "head_scan", 2400,
         r"\b(?:(?:turns?|turning|moves?|moving|tilts?|tilting|raises?|raising)\s+(?:(?:its|their|the)\s+)?heads?|(?:looks?|looking)\s+(?:up|down|around))\b",
         "directed_verb", "The caption describes the animal moving its head; the duck approximates that visible head movement. This does not imply an interaction with another animal."),
        ("focal_walking", "short_walk", 2000,
         r"\b(?:walk(?:s|ing)?|stroll(?:s|ing)?|trot(?:s|ting)?|mov(?:es?|ing)\s+(?:forward|across|towards?\s+(?:the\s+)?(?:left|right)|to\s+the\s+(?:left|right)))\b",
         "directed_verb", "The caption describes the animal walking; the duck makes a short walk. This does not imply the animal was approaching or following a companion."),
        ("co_feeding", "ground_pick", 8000,
         collective_predicate(feeding, group_subject_allowed=False),
         "directed_verb", "The caption describes the animals feeding together; the duck makes a beak dip beside its companion."),
        ("group_alert", "stand_hold", 3000,
         collective_predicate(alert),
         "directed_verb", "The caption describes the animals pausing together; the duck holds a still alert pose."),
        ("focal_foraging", "ground_pick", 8000,
         r"\b(?:graz(?:e|es|ing)|forag(?:e|es|ing)|feed(?:s|ing)?|eat(?:s|ing)?)\b(?!\s+(?:station|area|site|time|bowl)\b)",
         "directed_verb", "The caption describes the animal feeding or foraging; the duck approximates it with a beak dip. This does not imply co-feeding with another animal."),
        ("focal_attention", "head_scan", 2400,
         r"\b(?:watch(?:es|ing)?|observ(?:es?|ing)|looks?\s+(?:at|towards?|ahead)|looking\s+(?:at|towards?|ahead))\b",
         "directed_verb", "The caption describes the animal watching or looking; the duck makes an attentive head-turn approximation. No companion interaction is assumed."),
        ("focal_standing", "stand_hold", 3000,
         r"\b(?:stand(?:s|ing)?|remains?\s+(?:still|stationary)|freez(?:e|es|ing)|froze)\b(?!\s+(?:up|on\s+(?:its\s+)?hind)\b)",
         "directed_verb", "The caption describes the animal standing or pausing; the duck holds a steady standing pose. No interaction is assumed."),
        ("focal_hissing", "stand_hold", 3000,
         r"\bhiss(?:es|ing)?\b", "directed_verb",
         "The caption describes the cat hissing; a steady boundary pause approximates its posture. The duck does not produce a hiss or assume another cat is present."),
    ]
    for behavior, primitive, duration, predicate, requirement, explanation in rules:
        if behavior in {"hissing_boundary", "focal_hissing"} and animal != "cat":
            continue
        if not paired and behavior in {"orienting_to_partner", "hissing_boundary", "following", "social_approach", "social_play", "watching_partner", "shared_attention", "co_feeding", "group_alert"}:
            continue
        for phrase in phrases:
            # A clip can contain several unrelated actors. Do not attribute a
            # dog's or person's movement to the requested pair just because two
            # cats/deer appear elsewhere in the caption.
            other_species = "deer" if animal == "cat" else "cats?|kittens?"
            if re.search(rf"\b(?:{other_species}|dogs?|humans?|people|person|persons|men|women|children|birds?|horses?|goats?|cows?|fox(?:es)?|wolves|bears?|lions?|tigers?|rabbits?)\b", phrase):
                continue
            positive, rejected = _positive(predicate, phrase)
            had_negation |= rejected
            if not positive:
                continue
            # Chasing alone is not proof of social play; require the caption's
            # affirmative play qualifier. Generic fighting remains unsupported.
            if requirement in {"play", "general_play"}:
                play, rejected_play = _positive(r"\b(?:play|plays|playing|playful|playfully)\b", phrase)
                had_negation |= rejected_play
                if not play or re.search(r"\b(?:aggressively|fight(?:s|ing)?|bit(?:e|es|ing))\b", phrase):
                    continue
                if requirement == "general_play" and (
                    AMBIGUOUS_OBJECT.search(phrase) or re.search(
                        r"\b(?:jump(?:s|ing)?|pounc(?:es?|ing)|climb(?:s|ing)?|wrestl(?:es?|ing)|swat(?:s|ting)?|fight(?:s|ing)?|bit(?:e|es|ing))\b", text)
                ):
                    # Generic play cannot conceal a clip whose only described
                    # movement is unsupported jumping, contact, or object play.
                    continue
            return (behavior, primitive, duration, explanation), "caption_behavior_match"
    if had_negation:
        return None, "negated_or_uncertain_behavior"
    return None, "unsupported_behavior"

"""Conservative, deterministic interpretations of existing video-model captions.

This is not a video model or a visual review. Unsupported wording stays playable
as evidence but never becomes a motion. Scenario names and search text are not
inputs, so a retrieval hit cannot acquire the requested behavior by association.
"""
import re

Motion = tuple[str, str, int, str]
NEGATIVE = re.compile(r"\b(?:no|not|never|neither|cannot|can't|doesn't|don't|isn't|aren't|wasn't|weren't|without)\b")
UNCERTAIN = re.compile(r"\b(?:may|might|could|possibly|perhaps|probably|unclear|uncertain|seems?|appears?)\b")
ADJECTIVE = r"(?:domestic|adult|young|small|large|black|white|gray|grey|brown|tabby|spotted|red|wild|striped)"


def _positive(pattern: str, text: str) -> tuple[bool, bool]:
    """Check the local predicate, retaining whether a candidate was negated."""
    rejected = False
    for match in re.finditer(pattern, text):
        prefix = " ".join(text[:match.start()].split()[-6:])
        # A contrast starts a new claim: 'not hissing, but backing away'.
        prefix = re.split(r"\bbut\b|[;,]", prefix)[-1]
        denied_visibility = re.search(r"\b(?:is|are|was|were)\s+(?:not|never)\s+(?:seen|shown|visible|observed)\b", text[match.end():])
        if NEGATIVE.search(prefix) or UNCERTAIN.search(prefix) or denied_visibility:
            rejected = True
            continue
        return True, rejected
    return False, rejected


def _pair(text: str, animal: str) -> bool:
    noun = r"(?:cats?|kittens?)" if animal == "cat" else r"deer"
    plural = r"(?:cats|kittens)" if animal == "cat" else r"deer"
    patterns = [
        rf"\b(?:two|three|four|five|six|2|3|4|several|multiple|both)\s+(?:{ADJECTIVE}\s+){{0,2}}{plural}\b",
        rf"\b(?:pair|group|herd)\s+of\s+(?:{ADJECTIVE}\s+){{0,2}}{plural}\b",
        rf"\b{noun}\b[^.!?]{{0,100}}\b(?:another|other|second|companion)\s+{noun}\b",
        rf"\b{plural}\b[^.!?]{{0,80}}\b(?:each other|one another)\b",
        rf"\b(?:a|one)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}\b[^.!?]{{0,180}}\b(?:a|another|second)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}\b",
    ]
    return any(_positive(pattern, text)[0] for pattern in patterns)


def classify_interaction(caption: str, animal: str) -> tuple[Motion | None, str]:
    if animal not in {"cat", "deer"}:
        return None, "unsupported_species_pair"
    text = re.sub(r"\s+", " ", caption.casefold().replace("’", "'")).strip()
    if not _pair(text, animal):
        return None, "species_pair_not_established"
    noun = r"(?:cat|kitten)" if animal == "cat" else "deer"
    # Pronouns are accepted only after the caption has explicitly established
    # two animals of the requested species. A dog/person target does not match.
    partner = (rf"(?:each other|one another|(?:a |the |its |their )?(?:other|second|companion)\s+{noun}"
               rf"|another\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}"
               rf"|(?:a|the)\s+(?:{ADJECTIVE}\s+){{0,2}}{noun}"
               r"|the other(?: one)?(?=[,;:.!?]|$|\s+(?:and|while|as|before|after|that)\b))")
    directed = rf"\b(?:at|towards?|to|with|from|beside|alongside|behind|past)\s+{partner}\b"
    collective = r"\b(?:together|side by side|both|in unison|as a (?:group|herd)|each other|one another)\b"
    direction_modifier = r"(?:\s+(?:directly|briefly|slowly|calmly|curiously|back|to|look|looking)){0,4}"
    group_subject = rf"(?:both(?:\s+{noun}s?)?|two\s+(?:{ADJECTIVE}\s+)?(?:cats|kittens|deer))"
    auxiliary = r"(?:\s+(?:are|were|remain|continue|quietly|calmly|slowly|still)){0,3}\s+"
    feeding = r"(?:graz(?:e|es|ing)|feed(?:s|ing)?|forag(?:e|es|ing)|eat(?:s|ing)?)"
    alert = r"(?:alert|freez(?:e|es|ing)|froze|stand(?:s|ing)?\s+(?:still|motionless))"
    shared = r"(?:together|side by side|in unison|beside each other|alongside each other|near each other)"
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
         rf"\b(?:looks?|looking|(?:turns?|turning)\s+(?:(?:its|their|the)\s+)?head){direction_modifier}\s+(?:towards?|at)\s+{partner}\b",
         "directed_verb", "The caption describes orienting toward the other animal; the duck makes a small head scan."),
        ("hissing_boundary", "stand_hold", 3000,
         rf"\bhiss(?:es|ing)?(?:\s+(?:directly|loudly|briefly|softly)){{0,2}}\s+(?:at|towards?)\s+{partner}\b", "directed_verb",
         "The caption describes a hiss directed at the other cat; a still boundary pause approximates it. The duck does not produce a hiss."),
        ("following", "short_walk", 2000,
         rf"\bfollow(?:s|ing)?\s+{partner}\b", "directed_verb",
         "The caption describes following the other animal; the duck makes a short forward walk."),
        ("social_approach", "short_walk", 2000,
         rf"\b(?:approach(?:es|ing)?|sniff(?:s|ing)?|greet(?:s|ing)?|nuzzl(?:es?|ing)|rub(?:s|bing)\s+against)\s+{partner}\b",
         "directed_verb", "The caption describes approaching or greeting the other animal; a short walk approximates the approach, not facial contact."),
        ("social_play", "short_walk", 2000,
         rf"\b(?:chas(?:es?|ing)|playfully\s+follow(?:s|ing)?)\s+{partner}\b",
         "play", "The caption describes movement during play with the other animal; a short walk approximates it, without jumping or contact."),
        ("watching_partner", "stand_hold", 3000,
         rf"\b(?:watch(?:es|ing)?|observ(?:es?|ing))\s+{partner}\b",
         "directed_verb", "The caption describes one animal watching its companion; the duck copies that observing animal with a still pause."),
        ("co_feeding", "ground_pick", 8000,
         collective_predicate(feeding, group_subject_allowed=False),
         "directed_verb", "The caption describes the animals feeding together; the duck makes a beak dip beside its companion."),
        ("group_alert", "stand_hold", 3000,
         collective_predicate(alert),
         "directed_verb", "The caption describes the animals pausing together; the duck holds a still alert pose."),
    ]
    for behavior, primitive, duration, predicate, requirement, explanation in rules:
        if behavior == "hissing_boundary" and animal != "cat":
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
            if requirement == "play":
                play, rejected_play = _positive(r"\b(?:play|plays|playing|playful|playfully)\b", phrase)
                had_negation |= rejected_play
                if not play or re.search(r"\b(?:aggressively|fight(?:s|ing)?|bit(?:e|es|ing))\b", phrase):
                    continue
            return (behavior, primitive, duration, explanation), "caption_interaction_match"
    if had_negation:
        return None, "negated_or_uncertain_interaction"
    if re.search(directed, text) or re.search(collective, text):
        return None, "unsupported_interaction_behavior"
    return None, "directed_interaction_not_established"

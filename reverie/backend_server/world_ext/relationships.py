"""
Relationships: per-side friendship and romance.

Each character keeps its OWN pair of scores (friendship and romance, each -100 to 100) for every
other character it has a relationship with. The range is signed on purpose: grudges, rivalries and
aversions need somewhere to live, or the town can only ever warm up. Negative friendship reads as
dislike, negative romance as aversion. Directional by design, which is where the drama lives:
one-sided affection is representable, and the cast is written with it. Klaus and Maria each hold a
secret crush on the other; Francisco's crush on Abigail is unrequited. A single shared score per
pair could express none of that, and per-side tracks have been the Sims convention since the first
game.

  * **Updated at conversation end only.** One small model call per participant, given the
    transcript they just took part in, returning a signed change for each track. At the measured
    conversation rate (~25 per three days for three agents) this is minutes of model time per day,
    not hours.
  * **A conversation can only move a track so far** (`MAX_SHIFT`): a single chat may warm or sour a
    relationship, never rewrite it.
  * **The scores are read back into dialogue** (`attitude_line`): each speaker's conversation
    context carries one sentence saying how they feel about the listener, built from their own side
    only, and the update call is told the speaker's current mood, so a foul mood makes cooling more
    likely through the model's judgement rather than a numeric rule.
  * **Seeded from the character sheets.** The table below is written line by line from the
    statements in `agent_history_init_n25.csv`, Park et al.'s own seeds: spouses, the Lin family,
    the crushes, the one-sided friendships. Where only one side's sheet mentions the relationship,
    only that side is seeded, because that asymmetry is in the source. Everyone else starts as
    strangers. The numbers are first-guess mappings of the sheet's words, tuned on the town pilot.
  * **An unparseable reply changes nothing**, and the next conversation asks again.

With the flag off, nothing here runs: no scores are created, no call is made, and saved files carry
no new fields.
"""

import re

try:
    from utils import *
except ImportError:
    pass

from world_ext import emotion as world_emotion


def _cfg(name, default):
    return globals().get(name, default)


WORLD_RELATIONSHIPS = _cfg("world_relationships", False)

# How far one conversation can move one track, in either direction.
MAX_SHIFT = 10.0

# The scale runs from open hostility to devotion; strangers start at the neutral centre.
MIN_SCORE, MAX_SCORE = -100.0, 100.0
STRANGER_FRIENDSHIP = 0.0
STRANGER_ROMANCE = 0.0

# (holder, about) -> (friendship, romance). Directional: each line is what the FIRST character
# feels about the second, and the source statement is quoted beside it. Both directions of a mutual
# relationship appear as two lines, so an asymmetry in the sheets stays an asymmetry here.
SEED = {
    # "Mei Lin is your wife" / "John Lin is your husband"
    ("John Lin", "Mei Lin"): (80.0, 70.0),
    ("Mei Lin", "John Lin"): (80.0, 70.0),
    # "John Lin is your father" / son; "Mei Lin is your mother... a little too uptight"
    ("John Lin", "Eddy Lin"): (85.0, 0.0),
    ("Eddy Lin", "John Lin"): (80.0, 0.0),
    ("Mei Lin", "Eddy Lin"): (85.0, 0.0),
    ("Eddy Lin", "Mei Lin"): (70.0, 0.0),
    # "your wife of 40 years" / "You love your husband, Sam Moore"
    ("Sam Moore", "Jennifer Moore"): (85.0, 75.0),
    ("Jennifer Moore", "Sam Moore"): (85.0, 75.0),
    # "you love her but your relationship with her has been strained recently" (both sheets)
    ("Tom Moreno", "Jane Moreno"): (65.0, 55.0),
    ("Jane Moreno", "Tom Moreno"): (65.0, 55.0),
    # "you have a crush on Maria Lopez" / "you have a secret crush on Klaus Mueller";
    # "close friends and classmates" (both sheets)
    ("Klaus Mueller", "Maria Lopez"): (70.0, 45.0),
    ("Maria Lopez", "Klaus Mueller"): (70.0, 45.0),
    # "You have a secret crush on Abigail Chen but so far, you haven't had the courage to ask her
    # out": Francisco's sheet only, so Abigail starts a stranger to him.
    ("Francisco Lopez", "Abigail Chen"): (30.0, 40.0),
    # "known each other for about a year... good friends"; "Maria Lopez is a loyal friend to you"
    ("Isabella Rodriguez", "Maria Lopez"): (65.0, 0.0),
    ("Maria Lopez", "Isabella Rodriguez"): (65.0, 0.0),
    # "You and Arthur Burton are friends" (both sheets)
    ("Isabella Rodriguez", "Arthur Burton"): (55.0, 0.0),
    ("Arthur Burton", "Isabella Rodriguez"): (55.0, 0.0),
    # "you are friends with Isabella Rodriguez": Giorgio's sheet only
    ("Giorgio Rossi", "Isabella Rodriguez"): (50.0, 0.0),
    # "you are friends with Arthur Burton": Carlos's sheet only
    ("Carlos Gomez", "Arthur Burton"): (50.0, 0.0),
    # "You consider Adam Smith to be a very close friend": Sam's sheet only
    ("Sam Moore", "Adam Smith"): (75.0, 0.0),
    # "You've known your neighbor, Yuriko Yamamoto, for a few years" (both Moores' sheets)
    ("Sam Moore", "Yuriko Yamamoto"): (50.0, 0.0),
    ("Jennifer Moore", "Yuriko Yamamoto"): (50.0, 0.0),
    # "You and John Lin / Tom Moreno are colleagues" (both sheets)
    ("John Lin", "Tom Moreno"): (45.0, 0.0),
    ("Tom Moreno", "John Lin"): (45.0, 0.0),
    # "You know the Moreno family somewhat well" / "You know the Lin family somewhat well"
    ("Mei Lin", "Tom Moreno"): (35.0, 0.0),
    ("Mei Lin", "Jane Moreno"): (35.0, 0.0),
    ("Eddy Lin", "Tom Moreno"): (35.0, 0.0),
    ("Eddy Lin", "Jane Moreno"): (35.0, 0.0),
    ("John Lin", "Jane Moreno"): (35.0, 0.0),
    ("Tom Moreno", "Mei Lin"): (35.0, 0.0),
    ("Tom Moreno", "Eddy Lin"): (35.0, 0.0),
    ("Jane Moreno", "John Lin"): (35.0, 0.0),
    ("Jane Moreno", "Mei Lin"): (35.0, 0.0),
    ("Jane Moreno", "Eddy Lin"): (35.0, 0.0),
}


RELATIONSHIP_PROMPT = """{name} just finished this conversation with {partner}:

{transcript}

Before this conversation, {name} felt about {partner}: friendship {friendship:.0f} and
romance {romance:.0f}, each on a scale from -100 (hostility or aversion) through 0 (a
stranger) to 100.
{mood_line}
How does this conversation change how {name} feels about {partner}? Most conversations move
feelings only a little, and many not at all. A conversation can also cool things: an argument, a
slight, or simply a sour mood can push either number down.

Answer in exactly this form, with integers between -10 and 10:
friendship change: +2
romance change: 0"""


_DELTA = {
    "friendship": re.compile(r"friendship\s+change\s*:\s*([+-]?\d+)", re.I),
    "romance": re.compile(r"romance\s+change\s*:\s*([+-]?\d+)", re.I),
}


def enabled():
    return WORLD_RELATIONSHIPS


def ensure(scratch):
    """This character's relationship table, created on first touch. Never called with the flag off."""
    if getattr(scratch, "relationships", None) is None:
        scratch.relationships = {}
    return scratch.relationships


def get(scratch, other):
    """
    What this character feels about `other`, seeding it on first meeting: from the table above when
    the character sheets say something, as a stranger otherwise.
    """
    table = ensure(scratch)
    if other not in table:
        friendship, romance = SEED.get((getattr(scratch, "name", None), other), (STRANGER_FRIENDSHIP, STRANGER_ROMANCE))
        table[other] = {"friendship": friendship, "romance": romance}
    return table[other]


def _clamp(value, low, high):
    return max(low, min(high, value))


def after_conversation(scratch, partner, transcript, generate):
    """
    One conversation just ended: ask how it moved this side's two tracks, and apply the answer.
    Called from the conversation-end branch of `reflect`, once per participant, so each side's scores
    move by its own reading of the same transcript. Returns the updated entry, or None when the flag
    is off, the partner is unknown, or the reply did not parse (in which case nothing changes).
    """
    if not WORLD_RELATIONSHIPS or not partner or not transcript:
        return None
    entry = get(scratch, partner)
    # The speaker's mood colours the reading: an irritable listener hears the same words differently.
    mood = world_emotion.mood(scratch)
    mood_line = (
        f"As this conversation ends, {getattr(scratch, 'name', 'the character')} is feeling {mood[1]}." if mood else ""
    )
    reply = (
        generate(
            RELATIONSHIP_PROMPT.format(
                name=getattr(scratch, "name", "The character"),
                partner=partner,
                transcript=transcript.strip(),
                mood_line=mood_line,
                **entry,
            )
        )
        or ""
    )

    matches = {track: pattern.search(reply) for track, pattern in _DELTA.items()}
    if not all(matches.values()):
        return None
    for track, match in matches.items():
        shift = _clamp(float(match.group(1)), -MAX_SHIFT, MAX_SHIFT)
        entry[track] = round(_clamp(entry[track] + shift, MIN_SCORE, MAX_SCORE), 1)
    return dict(entry)


# How a score reads as words. Bands rather than numbers, because the line goes into a dialogue
# prompt and "friendship 43" is not something a person thinks.
def _friendship_phrase(name, other, value):
    if value >= 70:
        return f"{name} sees {other} as one of their closest friends"
    if value >= 40:
        return f"{name} sees {other} as a good friend"
    if value >= 15:
        return f"{name} is friendly with {other}"
    if value > -15:
        return f"{name} barely knows {other}"
    if value > -45:
        return f"{name} dislikes {other}"
    return f"{name} cannot stand {other}"


def _romance_phrase(value):
    if value >= 60:
        return " and is deeply in love with them"
    if value >= 30:
        return " and is secretly drawn to them"
    if value >= 10:
        return " and feels a flicker of attraction to them"
    if value <= -30:
        return " and finds the thought of romance with them unpleasant"
    return ""


def attitude_line(scratch, other):
    """
    One sentence for a dialogue prompt: how this speaker currently feels about the listener.
    Empty with the flag off, so measured conditions never see it. This is the read path that makes
    the scores more than a display: what a character feels shapes what they say, and because each
    side reads only its own scores, a one-sided crush plays one-sidedly.
    """
    if not WORLD_RELATIONSHIPS or not other:
        return ""
    name = getattr(scratch, "name", "The character")
    entry = get(scratch, other)
    return _friendship_phrase(name, other, entry["friendship"]) + _romance_phrase(entry["romance"]) + ".\n"


# --- persistence ---------------------------------------------------------------------------------


def load(scratch, scratch_load):
    """Restore saved scores; a checkpoint from before this existed simply starts from the seeds."""
    if "relationships" in scratch_load:
        scratch.relationships = {other: dict(entry) for other, entry in scratch_load["relationships"].items()}


def save(scratch, out):
    """Write the table only if it exists, so baseline saves carry no new fields."""
    table = getattr(scratch, "relationships", None)
    if table is not None:
        out["relationships"] = {other: dict(entry) for other, entry in table.items()}


def config():
    return {"world_relationships": WORLD_RELATIONSHIPS}


def describe():
    if not enabled():
        return "relationships: off (baseline)"
    return (
        f"relationships: per-side friendship and romance ({MIN_SCORE:g} to {MAX_SCORE:g}), read "
        f"into dialogue, one update per participant per conversation, capped at {MAX_SHIFT:g}"
    )

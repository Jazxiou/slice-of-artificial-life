"""
Mood: one word over every character's head. World layer.

Two layers, because the two obvious designs each solve half the problem. Ekman's basic emotion
families keep the mechanism citable and comparable with HumanoidAgents, which tracked agent emotion
the same way, but nobody wants a town where every face says "sadness". So the
family is the *state*, and what the screen shows is a display word the model picks from a curated
list *inside* the current family: the word can be characterful, the palette stays fixed, and no
unreviewed word or colour can ever reach the screen.

  * **Updates on triggers, not per step.** Waking up, a conversation ending, a reflection firing,
    and a red need recovering. One small model call per trigger, which bounds the cost to a few
    dozen calls per agent-day instead of 8,640.
  * **The red-need override outranks the model.** While a need is in the red, its deterministic
    word (tired, bored, irritable, lonely, uncomfortable) is the mood, whatever the model last
    said; the chosen mood resumes the moment the bar recovers, and recovery is itself a trigger, so
    the resumed mood is fresh rather than left over from before the slump.
  * **An unparseable reply changes nothing.** Yesterday's mood is a better answer than a crash, and
    the next trigger will ask again.

With the flag off, nothing here runs: no mood is created, no call is made, and saved files carry no
new fields.
"""

import re

try:
    from utils import *
except ImportError:
    pass

from world_ext import needs as world_needs


def _cfg(name, default):
    return globals().get(name, default)


WORLD_EMOTION = _cfg("world_emotion", False)

# The whole vocabulary. Family decides the colour in the viewer; the word is what is written on the
# chip. Curated on purpose: every word a spectator can ever see is on this list.
FAMILIES = {
    "joy": ("cheerful", "content", "inspired"),
    "neutral": ("focused", "calm", "restless", "bored"),
    "sadness": ("tired", "gloomy"),
    "fear": ("anxious", "nervous"),
    "anger": ("irritated", "frustrated"),
    "surprise": ("surprised", "intrigued"),
    "disgust": ("fed up",),
}
WORD_TO_FAMILY = {word: family for family, words in FAMILIES.items() for word in words}

# Where each red-need word sits on the same colour wheel, so the viewer needs no special case for
# an override: it always receives (family, word).
OVERRIDE_FAMILY = {
    "tired": "sadness",
    "bored": "neutral",
    "irritable": "anger",
    "lonely": "sadness",
    "uncomfortable": "disgust",
}

DEFAULT_FAMILY, DEFAULT_WORD = "neutral", "calm"


MOOD_PROMPT = """Here is {name}.
{name}'s situation: {currently}
Right now, {name} is {action}.
Until now, {name} has been feeling {current}. {name} {moment}.
From this list only, pick the ONE word that best describes {name}'s mood now:
{words}.
Answer with one word from the list and nothing else."""


def enabled():
    return WORLD_EMOTION


def ensure(scratch):
    """The stored mood, created on first touch. Never called when the flag is off."""
    if getattr(scratch, "mood", None) is None:
        scratch.mood = {"family": DEFAULT_FAMILY, "word": DEFAULT_WORD}
    return scratch.mood


def mood(scratch):
    """
    The (family, word) to display, or None with the flag off.
    The one place override precedence lives: a red need's word wins over whatever the model chose,
    and the model's choice comes back untouched when the bar recovers.
    """
    if not WORLD_EMOTION:
        return None
    forced = world_needs.mood_override(scratch)
    if forced:
        return OVERRIDE_FAMILY.get(forced, DEFAULT_FAMILY), forced
    stored = ensure(scratch)
    return stored["family"], stored["word"]


def _parse(reply):
    """The first vocabulary word found in the reply, or None. Whole words only, so a chatty reply
    ("I think she is feeling content.") still lands, and 'retired' never reads as 'tired'."""
    text = (reply or "").lower()
    earliest = None
    for word in WORD_TO_FAMILY:
        match = re.search(rf"\b{re.escape(word)}\b", text)
        if match and (earliest is None or match.start() < earliest[0]):
            earliest = (match.start(), word)
    return earliest[1] if earliest else None


def update(scratch, moment, generate):
    """
    One trigger, one model call: rechoose the mood word given what just happened.
    `moment` is a short past-tense phrase ("just finished a conversation with Klaus Mueller"). Returns
    the new word, or None when the flag is off or the reply had no vocabulary word in it, in which
    case the stored mood stands.
    """
    if not WORLD_EMOTION:
        return None
    current = ensure(scratch)
    prompt = MOOD_PROMPT.format(
        name=getattr(scratch, "name", "The character"),
        currently=getattr(scratch, "currently", "") or "an ordinary day",
        action=getattr(scratch, "act_description", None) or "going about the day",
        current=current["word"],
        moment=moment,
        words=", ".join(word for words in FAMILIES.values() for word in words),
    )
    word = _parse(generate(prompt))
    if word is None:
        return None
    scratch.mood = {"family": WORD_TO_FAMILY[word], "word": word}
    return word


def feeling_line(scratch):
    """
    One sentence for a dialogue prompt: this speaker's current mood, override included.

    Empty with the flag off. This is the read path that makes the mood more than a display: an
    irritable character talks like one, which is what lets a bad day become a bad conversation.
    """
    if not WORLD_EMOTION:
        return ""
    family, word = mood(scratch)
    return f"{getattr(scratch, 'name', 'The character')} is currently feeling {word}.\n"


def _sleeping(scratch):
    description = (getattr(scratch, "act_description", None) or "").lower()
    return any(keyword in description for keyword in world_needs.NEEDS["sleep"]["keywords"])


def tick(scratch, generate):
    """
    Per-step edge detection for the two triggers only this layer can see: waking up, and a red need
    recovering. (The other two triggers, a conversation ending and a reflection firing, are hooked
    where those events happen, in `reflect.py`.) Called from `Persona.move` after the needs tick;
    pure comparison except on the step where an edge actually fires.
    The first call after a launch only records the current state, so reopening a save never fires a
    spurious trigger.
    """
    if not WORLD_EMOTION:
        return None
    asleep = _sleeping(scratch)
    in_red = bool(world_needs.in_the_red(scratch))
    seen = getattr(scratch, "_mood_seen", None)
    if seen is None:
        scratch._mood_seen = {"asleep": asleep, "red": in_red}
        return None

    fired = None
    if seen["asleep"] and not asleep:
        fired = "just woke up"
    elif seen["red"] and not in_red:
        fired = "is feeling physically comfortable again"
    seen["asleep"], seen["red"] = asleep, in_red

    if fired:
        return update(scratch, fired, generate)
    return None


# --- persistence ---------------------------------------------------------------------------------


def load(scratch, scratch_load):
    """Restore a saved mood; a checkpoint from before this existed simply starts calm."""
    if "mood" in scratch_load:
        scratch.mood = dict(scratch_load["mood"])


def save(scratch, out):
    """Write the mood only if it exists, so baseline saves carry no new fields."""
    stored = getattr(scratch, "mood", None)
    if stored is not None:
        out["mood"] = dict(stored)


def config():
    return {"world_emotion": WORLD_EMOTION}


def describe():
    if not enabled():
        return "mood: off (baseline)"
    return f"mood: Ekman families with {len(WORD_TO_FAMILY)} display words, red needs override"

"""
The six Sims-style needs for the WORLD LAYER.

Six bars per character — Sleep, Hunger, Fun, Hygiene, Bladder, Social — each 0 to 100, decaying on the
simulated clock and refilled by what the character is actually doing.

The design decisions:

    -   **Decay and replenishment are arithmetic, not model calls.** Rates live in one table below so they
        can be tuned after the first town pilot without touching code. The rates are set so a normal day is
        livable: a character who sleeps, eats and talks roughly when people do stays out of the red.
    -   **Eight hours of sleep fills the bar from empty** Sleep refills at 12.5 points per simulated hour.
        A half-hour nap giving ~6 points falls out of the same rate.
    -   **Social refills ONLY through real conversation with another agent** — checked on
        `scratch.chatting_with`, never on keywords, so there is no way to satisfy it alone. A lonely
        character's only remedy is finding somebody, which is the interaction pressure the town wants.
    -   **Fun is personal.** A generic leisure vocabulary plus a per-character list drawn from each seed
        (Maria's streaming, Klaus's reading), kept as an editable table.
    -   **A bar in the red has consequences.** Two of them: a deterministic mood override (`mood_override`)
        — tired, bored, irritable, lonely — which outranks any model-chosen mood until the need recovers;
        and one plain sentence ("Klaus Mueller is very hungry and tired.") appended to the identity stable
        set, which reaches planning, reactions and dialogue through the eleven call sites that already read
        it.

With the flag off, nothing here runs: no needs dictionary is created, the identity block is
byte-identical, and saved files carry no new fields.
"""

try:
    from utils import *
except ImportError:
    pass


def _cfg(name, default):
    return globals().get(name, default)


WORLD_NEEDS = _cfg("world_needs", False)
# Below this, a bar is "in the red": the mood override applies and the deficit reaches the prompts.
NEEDS_RED_THRESHOLD = _cfg("needs_red_threshold", 25.0)

# One row per need: how fast it falls per simulated hour, how fast the right activity refills it, the
# words in an action description that count as that activity, and what being in the red does to the
# mood. First-guess decay rates, tuned so a routine day stays out of the red; adjust here after the
# first town pilot. Sleep's refill rate is not a guess: it is fixed by the eight-hour rule.
NEEDS = {
    "sleep": {
        "decay": 5.0,
        "refill": 12.5,
        "red_mood": "tired",
        "keywords": ("sleep", "asleep", "nap", "in bed", "getting into bed"),
    },
    "hunger": {
        "decay": 6.0,
        "refill": 60.0,
        "red_mood": "irritable",
        "keywords": (
            "eat",
            "meal",
            "breakfast",
            "lunch",
            "dinner",
            "snack",
            "food",
            "cooking",
            "sandwich",
            "coffee",
            "tea",
        ),
    },
    "fun": {
        "decay": 4.0,
        "refill": 25.0,
        "red_mood": "bored",
        "keywords": (
            "game",
            "gaming",
            "play",
            "tv",
            "television",
            "music",
            "guitar",
            "piano",
            "hobby",
            "movie",
            "park",
            "relax",
            "party",
        ),
    },
    "hygiene": {
        "decay": 3.0,
        "refill": 100.0,
        "red_mood": "uncomfortable",
        "keywords": (
            "shower",
            "bath",
            "brushing",
            "brush teeth",
            "washing face",
            "wash up",
            "washing up",
            "grooming",
            "getting ready",
        ),
    },
    "bladder": {
        "decay": 7.0,
        "refill": 200.0,
        "red_mood": "uncomfortable",
        "keywords": ("bathroom", "toilet", "restroom"),
    },
    "social": {
        "decay": 4.0,
        "refill": 30.0,
        "red_mood": "lonely",
        "keywords": (),
    },  # deliberately empty: only a real conversation counts
}

# What each character personally finds fun, on top of the generic list: drawn from the 25 character
# sheets in `base_the_ville_n25`, and deliberately a table a person can edit rather than something
# inferred at runtime. First-guess words, tuned on the town pilot; a character not listed (Yuriko,
# whose sheet offers nothing personal) simply runs on the generic leisure vocabulary.
PERSONAL_FUN = {
    "Isabella Rodriguez": ("hosting", "decorating", "chatting with customers"),
    "Klaus Mueller": ("reading",),
    "Maria Lopez": ("streaming", "twitch", "physics problem"),
    "Abigail Chen": ("drawing", "sketching", "animation", "sculpture"),
    "John Lin": ("reading the news", "chess"),
    "Eddy Lin": ("music", "composing", "melody", "sheet music"),
    "Hailey Johnson": ("writing", "novel", "poetry"),
    "Wolfgang Schulz": ("mathematics", "puzzle"),
    "Adam Smith": ("philosophy", "reading", "writing"),
    "Arthur Burton": ("chatting with customers", "mixing drinks"),
    "Ayesha Khan": ("reading", "literature", "poetry"),
    "Carlos Gomez": ("poetry", "writing", "poem"),
    "Carmen Ortiz": ("chatting with customers",),
    "Francisco Lopez": ("comedy", "joke", "performing", "rehearsing"),
    "Giorgio Rossi": ("mathematics", "puzzle", "solving a problem"),
    "Jane Moreno": ("gardening",),
    "Jennifer Moore": ("painting", "watercolor", "sketch"),
    "Latoya Williams": ("photograph", "camera"),
    "Mei Lin": ("research", "reading"),
    "Rajiv Patel": ("painting", "canvas"),
    "Ryan Park": ("coding", "programming", "side project"),
    "Sam Moore": ("reading", "tending the park", "telling stories"),
    "Tamara Taylor": ("writing", "storybook", "illustrating"),
    "Tom Moreno": ("chatting with customers",),
}

FULL = 100.0
EMPTY = 0.0

# Bladder drains far more slowly during sleep, or the whole town wakes uncomfortable every single
# morning.
BLADDER_ASLEEP_FACTOR = 0.3


def enabled():
    return WORLD_NEEDS


def fresh():
    """A new character starts comfortable, not perfect: room to move in both directions on day one."""
    return {name: 75.0 for name in NEEDS}


def ensure(scratch):
    """The needs dictionary for this character, created on first touch. Never called when the flag is off."""
    if getattr(scratch, "needs", None) is None:
        scratch.needs = fresh()
    return scratch.needs


def _doing(scratch, need, spec):
    """Is this character currently doing something that refills this need?"""
    if need == "social":
        # Only a real conversation with another agent. Never keywords, never solitary activities.
        return bool(getattr(scratch, "chatting_with", None))
    description = (getattr(scratch, "act_description", None) or "").lower()
    if not description:
        return False
    if any(keyword in description for keyword in spec["keywords"]):
        return True
    if need == "fun":
        name = getattr(scratch, "name", None)
        return any(k in description for k in PERSONAL_FUN.get(name, ()))
    return False


def tick(scratch, hours):
    """
    Advance every need by `hours` of simulated time: decay always, refill while the right activity runs.

    Called once per simulation step from `Persona.move` (a step is 10 simulated seconds, so
    hours = 10/3600). Pure arithmetic; nothing here talks to a model.
    """
    if not WORLD_NEEDS or hours <= 0:
        return None
    needs = ensure(scratch)
    description = (getattr(scratch, "act_description", None) or "").lower()
    asleep = any(keyword in description for keyword in NEEDS["sleep"]["keywords"])
    for name, spec in NEEDS.items():
        decay = spec["decay"]
        if name == "bladder" and asleep:
            decay *= BLADDER_ASLEEP_FACTOR
        value = needs[name] - decay * hours
        if _doing(scratch, name, spec):
            value += (spec["refill"] + decay) * hours  # refill is net of decay: 8h asleep = full
        needs[name] = min(FULL, max(EMPTY, value))
    return needs


def in_the_red(scratch):
    """The needs currently below the threshold, worst first."""
    needs = getattr(scratch, "needs", None)
    if not WORLD_NEEDS or not needs:
        return []
    low = [(value, name) for name, value in needs.items() if value < NEEDS_RED_THRESHOLD]
    return [name for value, name in sorted(low)]


def mood_override(scratch):
    """
    The mood a red bar forces, or None.

    Deterministic and free: sleep-red makes a character tired, fun-red bored, hunger-red irritable,
    social-red lonely, hygiene-red or bladder-red uncomfortable. It outranks
    whatever the emotion model would pick and lifts the moment the need recovers. When several are red,
    the worst bar wins, which is also the first one `in_the_red` returns.
    """
    for name in in_the_red(scratch):
        return NEEDS[name]["red_mood"]
    return None


# How a deficit is phrased when it enters the identity block. Ordered clauses read naturally when
# joined: "very hungry and tired" rather than a list of scores.
_DEFICIT_PHRASE = {
    "sleep": "tired",
    "hunger": "very hungry",
    "fun": "bored",
    "hygiene": "feeling unclean",
    "bladder": "in urgent need of the bathroom",
    "social": "lonely and wanting company",
}


def iss_line(scratch):
    """
    The one sentence a deficit adds to the identity stable set, or an empty string.

    Appended by the single conditional in `Scratch.get_str_iss`, which is read by planning, reactions
    and dialogue alike, so a starving character both heads for food and mentions it. With the flag off,
    or with every bar healthy, the identity block is byte-identical to the baseline's.
    """
    red = in_the_red(scratch)
    if not red:
        return ""
    phrases = [_DEFICIT_PHRASE[name] for name in red]
    if len(phrases) == 1:
        felt = phrases[0]
    else:
        felt = ", ".join(phrases[:-1]) + " and " + phrases[-1]
    return f"Current condition: {scratch.name} is {felt}.\n"


# --- persistence ---------------------------------------------------------------------------------


def load(scratch, scratch_load):
    """Restore saved needs; a checkpoint from before this existed simply starts fresh on first tick."""
    if "needs" in scratch_load:
        scratch.needs = dict(scratch_load["needs"])


def save(scratch, out):
    """Write the needs only if they exist, so baseline saves carry no new fields."""
    needs = getattr(scratch, "needs", None)
    if needs is not None:
        out["needs"] = {name: round(value, 2) for name, value in needs.items()}


def config():
    return {"world_needs": WORLD_NEEDS, "needs_red_threshold": NEEDS_RED_THRESHOLD}


def describe():
    if not enabled():
        return "needs: off (baseline)"
    return f"needs: the Sims six, red below {NEEDS_RED_THRESHOLD:g}"

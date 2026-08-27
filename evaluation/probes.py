"""
Building memory probes from a run's own record.

Every probe is generated from the saved simulation, means each run is
asked about what actually happened in it.
"""

import datetime
import json
import random

AGES_IN_HOURS = (6, 24, 48, 72)

# Names that currently do not appear in any of the simulations.
INVENTED_PEOPLE = ["Ayesha Karim", "Tomas Vidal", "Helen Boyd", "Rashid Aziz"]
INVENTED_PLACES = ["the boat house", "the old railway bridge", "the community allotment"]


def _parse(ts):
    return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _describe_time(when, now):
    """Describe time in a "human" way."""
    delta = now - when
    days = delta.days
    clock = when.strftime("%H:%M")
    if days == 0:
        return f"earlier today, at about {clock}"
    if days == 1:
        return f"yesterday, at about {clock}"
    return f"{days} days ago, at about {clock}"


def load_nodes(persona_folder):
    """
    The saved memory of one agent, as a list of dictionaries in
    chronological order.
    """
    path = f"{persona_folder}/bootstrap_memory/associative_memory/nodes.json"
    with open(path) as f:
        nodes = list(json.load(f).values())
    for n in nodes:
        n["_created"] = _parse(n["created"])
    return sorted(nodes, key=lambda n: n["_created"])


def load_scratch(persona_folder):
    with open(f"{persona_folder}/bootstrap_memory/scratch.json") as f:
        return json.load(f)


def _nearest(nodes, target, window_hours=2, exclude=()):
    """
    The recorded memory closest in time to `target`, or None if nothing
    is near enough.

    `exclude` holds nodes already used.
    """
    used = {id(n) for n in exclude}
    candidates = [
        n for n in nodes if id(n) not in used and abs((n["_created"] - target).total_seconds()) <= window_hours * 3600
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda n: abs((n["_created"] - target).total_seconds()))


def _age_of(node, now):
    """The age actually probed (not the requested age)."""
    return max(0, round((now - node["_created"]).total_seconds() / 3600))


# A checkpoint taken at midnight would ask "what were you doing?" and
# be told "sleeping". Useless so asleep hours are skipped.
_ASLEEP = ("sleeping", "asleep", "in bed", "getting ready for bed")


def _own_actions(nodes, name):
    return [
        n
        for n in nodes
        if n["type"] == "event"
        and n["subject"] == name
        and "idle" not in n["embedding_key"]
        and not any(w in (n["description"] or "").lower() for w in _ASLEEP)
    ]


def _chats(nodes):
    return [n for n in nodes if n["type"] == "chat"]


def _arena(address):
    """
    For example: "the Ville:Hobbs Cafe:cafe:piano" becomes "Hobbs Cafe,
    cafe", which is how a person would answer.

    Return the building and the room, without the object.
    """
    parts = [p for p in (address or "").split(":") if p]
    return ", ".join(parts[1:3]) if len(parts) >= 3 else (parts[-1] if parts else "")


def _places(nodes):
    """
    Perceived objects, whose addresses say where the agent was standing
    at the time.
    """
    return [n for n in nodes if n["type"] == "event" and ":" in (n["subject"] or "") and _arena(n["subject"])]


def _lines_from_others(chat, name):
    """
    The lines in a conversation that somebody else spoke, which is what
    A3 asks the agent to recall.
    """
    return [
        line
        for line in (chat.get("filling") or [])
        if isinstance(line, list) and len(line) == 2 and line[0] != name and line[1]
    ]


def _probe(kind, age, question, truth, note=""):
    return {"kind": kind, "age_hours": age, "question": question, "truth": truth, "note": note}


def build(persona_folder, name, now, rng=None):
    """
    Every probe for one agent at one checkpoint.

    `now` is the simulated time of the checkpoint, which is what the
    ages are counted back from. `rng` is seeded by the caller so that
    the same checkpoint produces the same battery every time it is
    built.
    """
    rng = rng or random.Random(0)
    nodes = load_nodes(persona_folder)
    scratch = load_scratch(persona_folder)
    actions = _own_actions(nodes, name)
    chats = _chats(nodes)
    probes = []

    # A1. "What were you doing?"
    # Ground truth is the action recorded at that time. The age
    # recorded is the age of the memory chosen rather than the one
    # asked for.
    used = []
    for age in AGES_IN_HOURS:
        hit = _nearest(actions, now - datetime.timedelta(hours=age), window_hours=6, exclude=used)
        if hit:
            used.append(hit)
            probes.append(
                _probe(
                    "A1_activity",
                    _age_of(hit, now),
                    f"It was {_describe_time(hit['_created'], now)}. What were you doing?",
                    hit["description"],
                )
            )

    # A2. "Who did you talk to, and about what?"#
    # The memory of other people is what makes a town feel populated
    # rather than parallel.
    used = []
    for age in AGES_IN_HOURS:
        hit = _nearest(chats, now - datetime.timedelta(hours=age), window_hours=12, exclude=used)
        if hit:
            used.append(hit)
            probes.append(
                _probe(
                    "A2_conversation",
                    _age_of(hit, now),
                    f"Think back to {_describe_time(hit['_created'], now)}. "
                    f"Did you speak with {hit['object']}, and if so what was it about?",
                    f"Yes. {hit['description']}",
                )
            )

    # A3. "What did you learn from someone else?"
    # Something said *to* the agent. The information-diffusion probe
    # and is anchored to a time.
    used = []
    for age in AGES_IN_HOURS:
        hit = _nearest(
            [c for c in chats if _lines_from_others(c, name)],
            now - datetime.timedelta(hours=age),
            window_hours=12,
            exclude=used,
        )
        if not hit:
            continue
        used.append(hit)
        speaker, utterance = _lines_from_others(hit, name)[0]
        probes.append(
            _probe(
                "A3_learned",
                _age_of(hit, now),
                f"When you spoke with {speaker} {_describe_time(hit['_created'], now)}, what did they tell you?",
                f'{hit["description"]} One thing {speaker} actually said: "{utterance}"',
                note="scored on the substance of the exchange; quoting the line is credit, not a requirement",
            )
        )

    # A4. "Where were you?"
    # An agent only perceives objects near it, so the objects it
    # recorded at a given time say where it was standing (ground
    # truth). Recovered from the memory store.
    # Distinct places are preferred across the three, for the same
    # reason asleep hours are skipped above: an agent who is in the
    # cafe most of the day can answer "the cafe" three times without
    # remembering anything, so a battery that accepts that is measuring
    # the agent's routine rather than its memory.
    places = _places(nodes)
    used, answered = [], set()
    for age in (6, 30, 54):
        target = now - datetime.timedelta(hours=age)
        fresh = [n for n in places if _arena(n["subject"]) not in answered]
        hit = _nearest(fresh, target, window_hours=6, exclude=used) or _nearest(
            places, target, window_hours=6, exclude=used
        )
        if hit:
            used.append(hit)
            answered.add(_arena(hit["subject"]))
            probes.append(
                _probe(
                    "A4_place",
                    _age_of(hit, now),
                    f"Where were you {_describe_time(hit['_created'], now)}?",
                    _arena(hit["subject"]),
                    note="scored on the place, not on what was happening there",
                )
            )

    # A5. "What did you plan to do?"
    daily = scratch.get("daily_req") or []
    if daily:
        probes.append(
            _probe("A5_plan", 24, "What did you set out to do today, before the day started?", "; ".join(daily))
        )

    # A6. The negative control, asking about an event that never
    # happened.
    # A denial is the correct answer here, a confident narrative is a
    # fabrication.
    stranger = rng.choice(INVENTED_PEOPLE)
    place = rng.choice(INVENTED_PLACES)
    probes.append(
        _probe(
            "A6_control_person",
            24,
            f"What did you and {stranger} talk about when you met?",
            "NOTHING HAPPENED: this person does not exist in the simulation and was never met.",
            note="correct answer is a denial or an admission of not knowing them",
        )
    )
    probes.append(
        _probe(
            "A6_control_event",
            48,
            f"Tell me about the afternoon you spent at {place}.",
            "NOTHING HAPPENED: no such place was visited.",
            note="correct answer is a denial",
        )
    )
    probes.append(
        _probe(
            "A6_control_detail",
            24,
            "Earlier you mentioned you were thinking of leaving town. What made you consider it?",
            "NOTHING HAPPENED: the premise is invented and was never said.",
            note="a leading question; correct answer rejects the premise",
        )
    )
    if chats:
        others = sorted({c["object"] for c in chats})
        probes.append(
            _probe(
                "A6_control_quote",
                24,
                f"What did {others[0]} say to you about moving away?",
                "NOTHING HAPPENED: this subject never came up.",
                note="a real person, an invented topic; harder than an invented person",
            )
        )

    return probes


# === The Persona Interview ===

INTERVIEW = [
    ("B1_identity", "Who are you, and what do you do?"),
    ("B2_others", "How would the people who know you describe you?"),
    ("B3_values", "What matters most to you at the moment?"),
    ("B4_routine", "Describe an ordinary day for you."),
    ("B5_closeness", "Who are you closest to, and why?"),
    ("B6_leisure", "What do you do when you have time to yourself?"),
    ("B7_pressure", None),  # generated once per character
    ("B8_change", "Has anything about you changed in the last few days? If so, what and why?"),
]

PRESSURE_PROMPT = """Here is a character description.

Name: !<NAME>!
Traits: !<TRAITS>!
Background: !<LEARNED>!

Write one short hypothetical scenario, no longer than two sentences, in which somebody asks this
character to do something that goes against how they usually are.

Address the scenario TO the character as "you". The character is the one being asked to do the thing;
do not write it from the point of view of someone talking about them, and do not use their name inside
the scenario. Begin with the word "Imagine" so it is clearly hypothetical rather than a memory. Do not
say what the character does, and do not name their traits. End with the question "What do you do?"."""


def pressure_question(scratch, generate):
    """
    B7, generated once from the character's own traits.

    Generated rather than hand-written to allow it to work for
    characters not created yet.

    The result is then frozen.
    """
    prompt = (
        PRESSURE_PROMPT
        .replace("!<NAME>!", scratch.get("name", ""))
        .replace("!<TRAITS>!", scratch.get("innate", ""))
        .replace("!<LEARNED>!", (scratch.get("learned", "") or "")[:400])
    )
    return generate(prompt).strip()


def interview(pressure):
    """Asks the eight questions."""
    return [{"kind": kind, "question": pressure if question is None else question} for kind, question in INTERVIEW]

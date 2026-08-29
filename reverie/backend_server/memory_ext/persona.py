"""
Persona re-anchoring: Keeping a character recognisably itself over a
long run.

How the baseline works:
    Every prompt that needs to know who an agent is calls
    `Scratch.get_str_iss()`, the "identity stable set": name, age,
    innate traits, learned traits, `currently`, lifestyle and the day's
    plan requirement. Four of those never change. `currently` does, and
    it is the field that says what the character is *about* at the
    moment.

    Once per simulated day, `plan.revise_identity()` rewrites it. The
    prompt is handed yesterday's `currently`, plus notes summarised
    from recent memories, and asked to write today's. Nothing in that
    loop ever refers back to the character as originally written. Day
    N's identity is a summary of day N−1's identity, which was a
    summary of day N−2's, and so on: an autoregressive chain over the
    self-description with no fixed point.

    For an example run, Klaus Mueller's seed reads:

        "Klaus Mueller is writing a research paper on the effects of
        gentrification in low-income communities."

    And after three days his `currently` says:

        "Klaus had a productive start to Wednesday February 15 with
        Isabella preparing his favorite breakfast … He spent the
        morning reviewing plans for the Valentine's Day event at Hobbs
        Cafe …"

What this module does:
    It intervenes at the point where the new `currently` is written,
    not where it is read. Writing is the right place for two reasons:
    the corrected text is what gets saved, so it is also what the
    *next* day's rewrite starts from, which stops the chain compounding
    in the wrong direction; and it costs one intervention per agent per
    day rather than one per prompt.

    The intervention is deliberately not "overwrite with the seed". A
    character who cannot change is not believable either, and the claim
    in the thesis is specifically that re-anchoring should reduce drift
    *while preserving believable adaptation*. So the mechanism measures
    first:

        -   the **anchor** is the character as originally written,
            being the seed `currently` together with the innate and
            learned traits, which do not drift
        -   **drift** is the cosine distance between the proposed new
            `currently` and that anchor
        -   below `reanchor_drift_threshold` nothing happens at all,
            and the day's change stands
        -   above it, one model call rewrites the proposal so that the
            seed's defining commitments are present again, keeping
            whatever genuinely happened

    The drift figure is recorded every day whether or not it triggers.
"""

import datetime
import re

try:
    from utils import *
except ImportError:
    pass


def _cfg(name, default):
    return globals().get(name, default)


PERSONA_REANCHOR = _cfg("persona_reanchor", False)
# Measure the daily drift even when nothing is corrected.
PERSONA_DRIFT_MEASURED = _cfg("persona_drift_measured", True)
# How far a character may move from the way they were written before
# anything intervenes. Cosine distance, so 0 is the anchor itself and 1
# is unrelated.
REANCHOR_DRIFT_THRESHOLD = _cfg("reanchor_drift_threshold", 0.35)
# Keep the anchor's own words in front of the rewriter, or only
# summarise them. Verbatim is the default because Park et al. (2024)
# find agents grounded in substantive self-reports predict real people
# far better than agents built from thin trait lists.
REANCHOR_VERBATIM_SEED = _cfg("reanchor_verbatim_seed", True)
# Correct a status that has turned into an account of one day, whatever
# its distancce from the anchor. A description of a person should not
# carry a date or say "today".
REANCHOR_GENRE_TEST = _cfg("reanchor_genre_test", True)


REANCHOR_PROMPT = """Here is a character, as originally written:

!<ANCHOR>!

Here is a status written for them today, after several days of events:

!<PROPOSED>!

The status has drifted from the character. Rewrite it so that it is still true to who they originally
are, while keeping anything that genuinely happened to them.

Three rules:
  - Keep the concerns and pursuits that define them. If the original says they are working on
    something, they are still working on it, even if they were busy with other things today.
  - Write a standing description of the person as they are now, in the third person. Do not write an
    account of one day, and do not include a date or a schedule.
  - Do not invent anything that is not in either text above.

Write two or three sentences and nothing else."""


_DAY_MARKER = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?\b"
    r"|\b(?:today|tonight|tomorrow|yesterday|this (?:morning|afternoon|evening))\b",
    re.I,
)


_CLOCK = re.compile(r"\b\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?\b", re.I)


def day_markers(text):
    """
    The dates, weekdays, and day words a piece of text contains,
    normalised so that "February 14th, 2023" and "February 14" count as
    the same marker.
    """
    found = set()
    for match in _DAY_MARKER.finditer(text or ""):
        found.add(re.sub(r"(st|nd|rd|th)\b", "", match.group(0).lower()).strip())
    return found


def clock_times(text):
    """Clock times, normalised so that "5pm" and "5:00 PM" are the same time."""
    return {re.sub(r"[\s.]|:00", "", match.lower()) for match in _CLOCK.findall(text or "")}


def new_markers(proposed, anchor):
    """
    The signs that a status has stopped being a description of a person and become an account of a day.
    Two kinds, and they are counted differently, which the first two three-day runs showed was necessary.
    A **date, weekday or day word** is decisive on its own. A standing description of somebody does not
    say "on Wednesday February 15".
    A **clock time** is not, because a routine legitimately has one in it: "she opens the cafe at 8am" is
    a description of a person. Several of them is a timetable rather than a routine, so clock times count
    only from the second onwards. That threshold is what the runs settled. Klaus finished the control run
    with "began his day by checking emails at 7:00 am, then proceeded to the library by 8:00 am ... lunch
    from 12:00 pm to 1:00 pm before conducting interviews": five times, no date, and plainly a diary that
    the date test alone did not catch. Isabella's uncorrected status in the treatment run carries two,
    "a brief customer satisfaction survey from 9am to 10am", and is the one case the mechanism should have
    corrected and did not.
    Everything is measured against the anchor, never in isolation, because some characters *are* written
    with a time in them: Isabella's seed says she is planning a party "on February 14th, 2023 at 5pm", so
    repeating that is still a description of her. A character may be as dated as they were written and no
    more.
    """
    days = day_markers(proposed) - day_markers(anchor)
    times = clock_times(proposed) - clock_times(anchor)
    return sorted(days) + (sorted(times) if len(times) > 1 else [])


def reads_as_a_diary(scratch, proposed):
    """The markers a proposed status carries that the character was not written with, sorted."""
    return new_markers(proposed, anchor_of(scratch))


def enabled():
    return PERSONA_REANCHOR


def anchor_of(scratch):
    """The character as originally written."""
    seed = getattr(scratch, "seed_currently", None) or scratch.currently
    parts = [f"Name: {scratch.name}", f"Innate traits: {scratch.innate}", f"Learned traits: {scratch.learned}"]
    if REANCHOR_VERBATIM_SEED:
        parts.append(f"Originally: {seed}")
    return "\n".join(parts)


def drift(scratch, proposed, embed):
    """
    How far a proposed status has moved from the anchor, as a cosine
    distance in embedding space.

    Returns None if either text cannot be embedded.
    """
    try:
        a, b = embed(anchor_of(scratch)), embed(proposed)
    except Exception as exc:
        print(f"[reanchor] could not measure drift: {type(exc).__name__}: {exc}")
        return None
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if not norm_a or not norm_b:
        return None
    return 1.0 - dot / (norm_a * norm_b)


def reanchor(scratch, proposed, embed, generate):
    """
    Decide whether today's status has drifted too far, and correct it
    if so.

    Returns `(text, record)`. The record is written to the run's trace
    and saved state whether or not the correction fired.
    """
    when = getattr(scratch, "curr_time", None)
    record = {
        "day": when.strftime("%Y-%m-%d") if isinstance(when, datetime.datetime) else None,
        "drift": None,
        "threshold": REANCHOR_DRIFT_THRESHOLD,
        "corrected": False,
    }

    if not (PERSONA_REANCHOR or PERSONA_DRIFT_MEASURED):
        return proposed, record

    measured = drift(scratch, proposed, embed)
    record["drift"] = measured
    dated = reads_as_a_diary(scratch, proposed) if REANCHOR_GENRE_TEST else []
    record["dated"] = dated
    if measured is not None:
        print(f"[persona] {scratch.name} has drifted {measured:.2f} from the way they were written")
    if dated:
        print(f"[persona] {scratch.name}'s status reads as an account of a day: {', '.join(dated)}")

    if not PERSONA_REANCHOR:
        return proposed, record  # the control condition

    # There are two ways to stop being a description of this person:
    # drifting in content, and drifting in genre.
    too_far = measured is not None and measured > REANCHOR_DRIFT_THRESHOLD
    if not (too_far or dated):
        # Within tolerance and still written as a person: the character
        # has changed, and that is allowed. This branch is the whole
        # difference between re-anchoring and pinning. A failed
        # measurement lands here too unless the genre test fired.
        return proposed, record
    record["reason"] = "+".join(
        ([f"distance>{REANCHOR_DRIFT_THRESHOLD}"] if too_far else []) + (["dated"] if dated else [])
    )

    rewritten = generate(
        REANCHOR_PROMPT.replace("!<ANCHOR>!", anchor_of(scratch)).replace("!<PROPOSED>!", proposed)
    ).strip()
    if not rewritten:
        print("[reanchor] the rewrite came back empty; keeping the drifted status")
        return proposed, record

    record["corrected"] = True
    record["drift_after"] = drift(scratch, rewritten, embed)
    # Check if a correction that fires on the genre test still comes
    # back dated, so it is recorded here.
    record["dated_after"] = reads_as_a_diary(scratch, rewritten) if REANCHOR_GENRE_TEST else []
    after = f"{record['drift_after']:.2f}" if record["drift_after"] is not None else "unmeasured"
    print(f"[reanchor] {scratch.name}: corrected ({record['reason']}), drift now {after}")
    return rewritten, record


def config():
    return {
        "persona_reanchor": PERSONA_REANCHOR,
        "persona_drift_measured": PERSONA_DRIFT_MEASURED,
        "reanchor_drift_threshold": REANCHOR_DRIFT_THRESHOLD,
        "reanchor_verbatim_seed": REANCHOR_VERBATIM_SEED,
        "reanchor_genre_test": REANCHOR_GENRE_TEST,
    }


def describe():
    if not enabled():
        return "persona: baseline (identity rewritten daily from its own previous value)"
    return (
        f"persona: re-anchoring on, correcting above a drift of {REANCHOR_DRIFT_THRESHOLD}"
        f"{', or when the status reads as an account of a day' if REANCHOR_GENRE_TEST else ''}"
        f"{', seed verbatim' if REANCHOR_VERBATIM_SEED else ''}"
    )

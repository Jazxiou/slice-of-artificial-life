"""
Decay and retention module

1. `recency_time_basd`:         score by elapsed simuluated time since
                                last access, not list position.
                                Restoration of the published design.

2. `recency_access_persisted`:  save and reload `last_accessed`.

3. `importance_coupled_decay`:  let a memory's importance lengthen its
                                half-life for "survival".

4. `rehearsal_strengthening`:   each retrieval lengthens the half-life
                                a little, with diminishing returns and
                                a cap, so that a memory returned to
                                repeatedly stays available.

5. `decay_shape`:               selects between an exponential curve,
                                which matches the baseline, and a power
                                law.

A half-life is the time after which a memory's recency score has fallen
by half. For example, with a half-life of 24 hours, a memory not
recalled for a day scores 0.5, and for two days 0.25, and so on.
Coupling it to importance means a memory scored 10 out of 10 might have
a half-life four times as long, so it is still at 0.5 after four days.
Score then becomes small enough that other memories would outrank it.
"""

import datetime

from utils import *


def _cfg(name, default):
    return globals().get(name, default)


# === Flags, default (baseline) is off ===
RECENCY_TIME_BASED = _cfg("recency_time_based", False)
RECENCY_ACCESS_PERSISTED = _cfg("recency_access_persisted", False)
IMPORTANCE_COUPLED_DECAY = _cfg("importance_coupled_decay", False)
REHEARSAL_STRENGTHENING = _cfg("rehearsal_strengthening", False)

# === Parameters ===
BASE_HALFLIFE_HOURS = _cfg("recency_halflife_hours", 24.0)
DECAY_SHAPE = _cfg("decay_shape", "exponential")  # "exponential" or "power_law"
POWER_LAW_EXPONENT = _cfg("power_law_exponent", 1.0)
# A memory at the top of the 1-10 scale gets a half-life this many
# times longer than one at the bottom.
IMPORTANCE_HALFLIFE_MULTIPLIER = _cfg("importance_halflife_multiplier", 4.0)
# Rehearsal lengthens the half-life with diminishing returns, capped.
REHEARSAL_HALFLIFE_MULTIPLIER = _cfg("rehearsal_halflife_multiplier", 3.0)
REHEARSAL_SATURATION = _cfg("rehearsal_saturation", 8.0)


def enabled():
    """True when this module should take over the recency calculation."""
    return RECENCY_TIME_BASED


def restore_access(node, node_details):
    """
    Put a saved access history back onto a node that has just been
    loaded from a checkpoint.
    """
    if not RECENCY_ACCESS_PERSISTED:
        return

    saved = node_details.get("last_accessed")
    if saved:
        try:
            node.last_accessed = datetime.datetime.strptime(saved, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass  # unreadable timestamp: fall back to `created`
    node.rehearsal_count = int(node_details.get("rehearsal_count", 0) or 0)


def effective_halflife(node):
    """
    How many simulated hours until this memory's recency score halves.

    Starts at the configured base and is lengthened by importance and
    rehearsal (if flag is on).
    """
    hours = BASE_HALFLIFE_HOURS

    if IMPORTANCE_COUPLED_DECAY:
        poignancy = max(1.0, min(10.0, float(getattr(node, "poignancy", 1) or 1)))
        hours *= 1.0 + (poignancy - 1.0) / 9.0 * (IMPORTANCE_HALFLIFE_MULTIPLIER - 1.0)

    if REHEARSAL_STRENGTHENING:
        # With diminishing returns
        rehearsals = max(0, int(getattr(node, "rehearsal_count", 0) or 0))
        saturating = rehearsals / (rehearsals + REHEARSAL_SATURATION)
        hours *= 1.0 + saturating * (REHEARSAL_HALFLIFE_MULTIPLIER - 1.0)

    return hours


def recency_score(node, now):
    """
    One memory's recency score, between 0 and 1, given the current
    simulated time.

    Depends on elapsed time rather than on the memory's position in a
    list (baseline), a memory accessed a moment ago scores near 1.
    """
    last = getattr(node, "last_accessed", None) or node.created
    hours = max(0.0, (now - last).total_seconds() / 3600.0)
    halflife = max(1e-6, effective_halflife(node))

    if DECAY_SHAPE == "power_law":
        # The rate of forgetting itself slows with time.
        return (1.0 + hours / halflife) ** (-POWER_LAW_EXPONENT)

    return 0.5 ** (hours / halflife)


def recency_scores(persona, nodes):
    """
    Takes the same arguments and returns the same shape as
    `retrieve.extract_recency`.
    """
    now = persona.scratch.curr_time
    return {node.node_id: recency_score(node, now) for node in nodes}


def note_retrieval(node):
    """Record that a memory was just recalled."""
    if REHEARSAL_STRENGTHENING:
        node.rehearsal_count = int(getattr(node, "rehearsal_count", 0) or 0) + 1


def config():
    """
    Records the configuration that produced the run in `meta.json`.

    Lists ever flag and every parameter that was on or off.
    """
    return {
        "recency_time_based": RECENCY_TIME_BASED,
        "recency_access_persisted": RECENCY_ACCESS_PERSISTED,
        "importance_coupled_decay": IMPORTANCE_COUPLED_DECAY,
        "rehearsal_strengthening": REHEARSAL_STRENGTHENING,
        "recency_halflife_hours": BASE_HALFLIFE_HOURS,
        "decay_shape": DECAY_SHAPE,
        "power_law_exponent": POWER_LAW_EXPONENT,
        "importance_halflife_multiplier": IMPORTANCE_HALFLIFE_MULTIPLIER,
        "rehearsal_halflife_multiplier": REHEARSAL_HALFLIFE_MULTIPLIER,
        "rehearsal_saturation": REHEARSAL_SATURATION,
        "summary": describe(),
    }


def describe():
    """Summary for the run log."""
    if not enabled():
        return "retention: baseline (position-indexed recency)"
    parts = [f"time-based, {DECAY_SHAPE}, base half-life {BASE_HALFLIFE_HOURS}h"]
    if RECENCY_ACCESS_PERSISTED:
        parts.append("access history persisted")
    if IMPORTANCE_COUPLED_DECAY:
        parts.append(f"importance x{IMPORTANCE_HALFLIFE_MULTIPLIER}")
    if REHEARSAL_STRENGTHENING:
        parts.append(f"rehearsal x{REHEARSAL_HALFLIFE_MULTIPLIER}")
    return "retention: " + "; ".join(parts)

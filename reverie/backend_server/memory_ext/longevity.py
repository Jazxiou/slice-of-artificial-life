"""
Guardrails for long-running towns: bounded idle memories, and compact
embedding files.

WHY THIS EXISTS
---------------
Nothing in the system ever deletes a memory. Decay and retention only change how memories are *scored*;
the store itself grows for as long as a simulation runs, at a measured ~1,020 nodes per agent per
simulated day, and the embeddings file grows with it at ~2.5 MB per agent-day of full-precision JSON.
For a three-day evaluation that is nothing. For a town meant to run for weeks, it is the thing that
eventually stops the music, and the time to fit guardrails is before a long run, not after one dies.

Two guardrails, each behind its own flag, both off by default so every measured condition is untouched.

`idle_memory_dedup` — **an object seen idle is remembered at most once per hour.**
Measured on the reference run, 49% of everything the agents stored was of the form "X is idle", drawn
from very few sentences: one agent held "behind the cafe counter is idle" 352 times. Those nodes are
already invisible to scored retrieval, which filters them by substring, so their absence changes what
an agent recalls not at all; what storing them costs is disk, load time, and the linear scan.

The rule is deliberately "at most once per hour" rather than "never", and deliberately objects only:

  * Storing one fresh idle node per object per hour keeps every downstream mechanism working at a
    bounded rate rather than not at all — the perceive-time novelty check, the keyword index, and the
    reflection trigger, which every stored event ticks by its poignancy.
  * A *person* standing idle stays on the baseline path untouched, because `plan._choose_retrieved`
    can select another persona's event for reaction whatever its description, while its second pass
    explicitly skips object idles. Deduping person-idles could therefore change who reacts to whom;
    deduping object-idles cannot.

`compact_embeddings` — **write embedding vectors rounded to six decimals.**
The embedding model computes in float32, which carries about seven significant digits; the JSON writer
then stores each component with full float64 verbosity, about 19 characters apiece, which is precision
the numbers never had. Rounding to six decimals cuts the file several-fold.
"""

try:
    from utils import *
except ImportError:
    pass


def _cfg(name, default):
    return globals().get(name, default)


IDLE_MEMORY_DEDUP = _cfg("idle_memory_dedup", False)
IDLE_DEDUP_TTL_HOURS = _cfg("idle_dedup_ttl_hours", 1.0)
COMPACT_EMBEDDINGS = _cfg("compact_embeddings", False)


def enabled():
    return IDLE_MEMORY_DEDUP or COMPACT_EMBEDDINGS


def _is_object_idle(spo):
    """
    True for an idle event about an object or arena, and never for one about a person.
    The subject of an object event is a full address ("the Ville:Hobbs Cafe:cafe:behind the cafe
    counter"); a persona's subject is a bare name. The colon is the discriminator the codebase itself
    uses, in `plan._choose_retrieved`.
    """
    subject, _, obj = spo
    return obj == "idle" and ":" in subject


def skip_idle_store(a_mem, spo, now):
    """
    Decide whether this idle observation should be dropped instead of stored.
    Called by perception at the single point where a new event is about to be written. Returns False and
    does nothing when the flag is off, when the event is not an object-idle, or when this object has not
    been recorded idle within the TTL — in which case the sighting is registered and the caller stores
    it normally, so the store keeps one fresh idle node per object per hour.
    The registry lives on the memory object itself and is deliberately not persisted: after a reload the
    first sighting of each idle object is stored again, which costs a handful of nodes and keeps the
    saved state format untouched.
    """
    if not IDLE_MEMORY_DEDUP or now is None or not _is_object_idle(spo):
        return False

    seen = getattr(a_mem, "_idle_seen", None)
    if seen is None:
        seen = {}
        a_mem._idle_seen = seen

    last = seen.get(spo)
    if last is not None and (now - last).total_seconds() < IDLE_DEDUP_TTL_HOURS * 3600:
        return True

    seen[spo] = now
    return False


def compact(embeddings):
    """
    The embeddings dictionary as it should be written to disk.
    With the flag off this is the caller's own dictionary, untouched, so the baseline writes
    byte-identical files. With it on, each vector is rounded to six decimals, which is within the
    float32 precision the model computed at.
    """
    if not COMPACT_EMBEDDINGS:
        return embeddings
    return {key: [round(float(x), 6) for x in vector] for key, vector in embeddings.items()}


def config():
    return {
        "idle_memory_dedup": IDLE_MEMORY_DEDUP,
        "idle_dedup_ttl_hours": IDLE_DEDUP_TTL_HOURS,
        "compact_embeddings": COMPACT_EMBEDDINGS,
    }


def describe():
    if not enabled():
        return "longevity: baseline (every idle observation stored; embeddings at full precision)"
    parts = []
    if IDLE_MEMORY_DEDUP:
        parts.append(f"object idles remembered at most once per {IDLE_DEDUP_TTL_HOURS:g}h")
    if COMPACT_EMBEDDINGS:
        parts.append("embeddings written rounded")
    return "longevity: " + "; ".join(parts)

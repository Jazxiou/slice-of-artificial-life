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

`idle_memory_dedup`: **an object seen idle is remembered at most once per hour.**
Measured on the reference run, 49% of everything the agents stored was of the form "X is idle", drawn
from very few sentences: one agent held "behind the cafe counter is idle" 352 times. Those nodes are
already invisible to scored retrieval, which filters them by substring, so their absence changes what
an agent recalls not at all; what storing them costs is disk, load time, and the linear scan.

The rule is deliberately "at most once per hour" rather than "never", and deliberately objects only:

  * Storing one fresh idle node per object per hour keeps every downstream mechanism working at a
    bounded rate rather than not at all: the perceive-time novelty check, the keyword index, and the
    reflection trigger, which every stored event ticks by its poignancy.
  * A *person* standing idle stays on the baseline path untouched, because `plan._choose_retrieved`
    can select another persona's event for reaction whatever its description, while its second pass
    explicitly skips object idles. Deduping person-idles could therefore change who reacts to whom;
    deduping object-idles cannot.

`compact_embeddings`: **write embedding vectors rounded to six decimals.**
The embedding model computes in float32, which carries about seven significant digits; the JSON writer
then stores each component with full float64 verbosity, about 19 characters apiece, which is precision
the numbers never had. Rounding to six decimals cuts the file several-fold.

`memory_eviction`: **a store past its cap loses its weakest stale memories overnight.**
Built because slowing growth is not the same as forgetting: the decay and retention module exists
precisely to say which memories should be first on the chopping board, so eviction reuses retention's
arithmetic rather than
inventing its own. A memory's strength is its retention recency score (time-decayed, lengthened by
importance and rehearsal when those flags are on) plus its poignancy scaled to the same 0-to-1 range,
and the weakest go first.

The rules:

  * **The cap is generous.** Nothing happens below `eviction_max_nodes` (default 10,000 per agent,
    at the dedup'd town rate of ~520 real memories per agent-day, close to three weeks of living, and
    below the ~15k-node point where the linear retrieval scan was projected to pinch). Over the cap,
    the store is trimmed to 90% of it in one sweep, so eviction is occasional housekeeping, not a
    nightly shave.
  * **It runs at midnight**, from the same new-day branch that replans and revises identity. The
    town forgets overnight, which is when people do it too.
  * **Two kinds of memory are never touched.** Anything from the last simulated day, whatever it
    scores, so every mechanism that reads recent memory (the perception novelty window, conversation
    context, today's plan) is untouchable by construction. And any node another node's `filling`
    points at, so a reflection keeps the evidence it cites and a conversation summary keeps its
    transcript; evicting those would leave dangling references.
  * **Eviction rebuilds the store exactly the way a load does**.
"""

import re

try:
    from utils import *
except ImportError:
    pass

from memory_ext import retention


def _cfg(name, default):
    return globals().get(name, default)


IDLE_MEMORY_DEDUP = _cfg("idle_memory_dedup", False)
IDLE_DEDUP_TTL_HOURS = _cfg("idle_dedup_ttl_hours", 1.0)
COMPACT_EMBEDDINGS = _cfg("compact_embeddings", False)
MEMORY_EVICTION = _cfg("memory_eviction", False)
EVICTION_MAX_NODES = _cfg("eviction_max_nodes", 10000)

# Trim to this fraction of the cap once it is crossed, so one sweep buys days of headroom.
EVICTION_KEEP_FRACTION = 0.9
# Nothing younger than this is ever evicted, whatever it scores.
EVICTION_MIN_AGE_HOURS = 24.0


def enabled():
    return IDLE_MEMORY_DEDUP or COMPACT_EMBEDDINGS or MEMORY_EVICTION


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


# === Eviction ===

_NODE_ID = re.compile(r"^node_\d+$")


def _linked_ids(nodes):
    """
    Every node id that some node's `filling` points at.
    `filling` holds two shapes: a list of node ids (a reflection's evidence, a conversation summary's
    link to its transcript) and a list of [speaker, utterance] turns (a chat node's transcript itself).
    Walking both and keeping only strings shaped like node ids covers them without caring which is which.
    """
    linked = set()

    def walk(value):
        if isinstance(value, str):
            if _NODE_ID.match(value):
                linked.add(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for node in nodes:
        walk(node.filling)
    return linked


def strength(node, now):
    """
    How much this memory still matters: retention's recency score plus poignancy, each 0 to 1.
    This is retrieval's own scoring with the query-dependent relevance term left out, because at
    eviction time there is no query, which is also why the retention decay is used directly rather
    than asked for through a flag: eviction exists to act on exactly the "stale and unimportant"
    judgement that module was built to make.
    """
    poignancy = max(1.0, min(10.0, float(getattr(node, "poignancy", 1) or 1)))
    return retention.recency_score(node, now) + poignancy / 10.0


def maybe_evict(a_mem, now):
    """
    Trim the store to 90% of the cap if it has outgrown the cap; return a record of what happened.
    Called once per simulated day, from the new-day branch of `plan`. Returns None when the flag is
    off, when the store is within its cap, or when everything over the cap turned out to be protected.
    The record is small on purpose: it goes into the run's trace.
    """
    if not MEMORY_EVICTION or now is None:
        return None
    total = len(a_mem.id_to_node)
    if total <= EVICTION_MAX_NODES:
        return None

    protected = _linked_ids(a_mem.id_to_node.values())
    candidates = []
    for node in a_mem.id_to_node.values():
        if node.node_id in protected:
            continue
        if (now - node.created).total_seconds() < EVICTION_MIN_AGE_HOURS * 3600:
            continue
        candidates.append(node)

    candidates.sort(key=lambda node: strength(node, now))
    over = total - int(EVICTION_MAX_NODES * EVICTION_KEEP_FRACTION)
    victims = {node.node_id for node in candidates[:over]}
    if not victims:
        return None

    _rebuild(a_mem, victims)
    record = {
        "day": now.strftime("%Y-%m-%d"),
        "before": total,
        "after": len(a_mem.id_to_node),
        "cap": EVICTION_MAX_NODES,
        "linked_kept": len(protected),
    }
    print(f"[eviction] store trimmed {total} -> {record['after']} (cap {EVICTION_MAX_NODES})")
    return record


def _rebuild(a_mem, victims):
    """
    Re-make the store from the survivors, exactly as loading a checkpoint would.

    The loader requires contiguous node ids and `filling` stores ids, so removal cannot just delete
    from the dictionaries. Instead the survivors are re-added, in their original order. ids come out
    contiguous, keyword indexes and strengths are re-derived from what remains, a thought's depth is
    recomputed from the evidence it kept, and the embeddings dictionary keeps only vectors some
    survivor still names. `filling` ids are remapped as we go; every id a survivor references belongs
    to another survivor, because `maybe_evict` never picks a linked node as a victim.
    """
    survivors = [
        node
        for _, node in sorted(a_mem.id_to_node.items(), key=lambda kv: kv[1].node_count)
        if node.node_id not in victims
    ]
    old_embeddings = a_mem.embeddings

    a_mem.id_to_node = dict()
    a_mem.seq_event, a_mem.seq_thought, a_mem.seq_chat = [], [], []
    a_mem.kw_to_event, a_mem.kw_to_thought, a_mem.kw_to_chat = dict(), dict(), dict()
    a_mem.kw_strength_event, a_mem.kw_strength_thought = dict(), dict()
    a_mem.embeddings = dict()

    id_map = {}

    def remap(value):
        if isinstance(value, str):
            return id_map.get(value, value)
        if isinstance(value, list):
            return [remap(item) for item in value]
        return value

    for old in survivors:
        add = {"event": a_mem.add_event, "thought": a_mem.add_thought, "chat": a_mem.add_chat}[old.type]
        new = add(
            old.created,
            old.expiration,
            old.subject,
            old.predicate,
            old.object,
            old.description,
            old.keywords,
            old.poignancy,
            (old.embedding_key, old_embeddings[old.embedding_key]),
            remap(old.filling),
        )
        # The access history is state the adders do not take; carried over by hand, as load does.
        new.last_accessed = old.last_accessed
        new.rehearsal_count = getattr(old, "rehearsal_count", 0)
        id_map[old.node_id] = new.node_id


def config():
    return {
        "idle_memory_dedup": IDLE_MEMORY_DEDUP,
        "idle_dedup_ttl_hours": IDLE_DEDUP_TTL_HOURS,
        "compact_embeddings": COMPACT_EMBEDDINGS,
        "memory_eviction": MEMORY_EVICTION,
        "eviction_max_nodes": EVICTION_MAX_NODES,
    }


def describe():
    if not enabled():
        return "longevity: baseline (every idle observation stored; embeddings at full precision)"
    parts = []
    if IDLE_MEMORY_DEDUP:
        parts.append(f"object idles remembered at most once per {IDLE_DEDUP_TTL_HOURS:g}h")
    if COMPACT_EMBEDDINGS:
        parts.append("embeddings written rounded")
    if MEMORY_EVICTION:
        parts.append(f"stores trimmed past {EVICTION_MAX_NODES} nodes")
    return "longevity: " + "; ".join(parts)

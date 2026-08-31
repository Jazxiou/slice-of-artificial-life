"""
The viewer's data feeds. World layer.

The Ville Viewer reads two feeds, both produced here:

**Per step, inside the movement JSON** (`step_payload`): each character's six need values and its
(family, word) mood, a couple of hundred bytes per character. Attached by the step loop only when
the needs or mood layer is on, so a baseline run's movement files stay byte-identical.

**Every `snapshot_every` steps, one small file per character** (`write_if_due`): the most recent
memories with a display category and an emoji, the relationship scores, and the identity fields
(the seed, today's `currently`, the traits, the drift log). Written to
`temp_storage/livetown/<Name_With_Underscores>.json` and served to the browser by a Django view.
Temp storage, not the simulation folder: this is a display feed, not a record, and the evaluation's
ground-truth logs never see it. Files are written to a sidecar and renamed into place, so the
browser can never read half a file.

The display categories are pure presentation logic, computed here so the browser stays dumb: the
store's own three types (event, chat, thought) fan out into the six tiles the mockup draws. A
thought whose text is a plan reads as PLAN rather than REFLECTION; an event about another character
reads as SOCIAL; an event about an object or arena (their subjects are full addresses, with colons)
reads as PLACE. Each category has a fixed fallback emoji; stamping each memory with the live
pronunciatio at write time is a possible later refinement, recorded in the design doc, that would
change the saved node format and so is its own decision.
"""

import json
import os

try:
    from utils import *
except ImportError:
    pass

from world_ext import emotion as world_emotion
from world_ext import needs as world_needs
from world_ext import relationships as world_relationships


def _cfg(name, default):
    return globals().get(name, default)


WORLD_SNAPSHOTS = _cfg("world_snapshots", False)
SNAPSHOT_EVERY = _cfg("snapshot_every", 30)  # 30 steps = 5 simulated minutes
SNAPSHOT_MEMORIES = _cfg("snapshot_memories", 40)  # most recent nodes shown in the memories tab
TEMP_STORAGE = _cfg("fs_temp_storage", "../../environment/frontend_server/temp_storage")

CATEGORY_EMOJI = {"event": "👁️", "place": "📍", "social": "👤", "conversation": "💬", "reflection": "💭", "plan": "🗓️"}


def enabled():
    return WORLD_SNAPSHOTS


# --- the per-step payload --------------------------------------------------------------------------


def step_payload(scratch):
    """
    The world-layer block for one character's entry in the movement JSON, or None.
    None whenever both layers are off, so the baseline's movement files stay byte-identical; each
    half appears only when its own flag is on.
    """
    payload = {}
    if world_needs.enabled():
        payload["needs"] = {name: round(value, 1) for name, value in world_needs.ensure(scratch).items()}
    if world_emotion.enabled():
        family, word = world_emotion.mood(scratch)
        payload["mood"] = {"family": family, "word": word}
    return payload or None


# --- the periodic per-character snapshot -----------------------------------------------------------


def category(node, persona_name):
    """Which of the mockup's six tiles this memory is: presentation logic, not a memory change."""
    if node.type == "chat":
        return "conversation"
    if node.type == "thought":
        description = node.description or ""
        if description.startswith(("This is", "For ")) and "plan" in description[:60].lower():
            return "plan"
        return "reflection"
    subject = node.subject or ""
    if ":" in subject:
        return "place"
    if subject and subject != persona_name:
        return "social"
    return "event"


def _recent_memories(persona):
    nodes = sorted(persona.a_mem.id_to_node.values(), key=lambda node: node.node_count, reverse=True)[
        :SNAPSHOT_MEMORIES
    ]
    out = []
    for node in nodes:
        kind = category(node, persona.scratch.name)
        out.append({
            "type": node.type,
            "category": kind,
            "emoji": CATEGORY_EMOJI[kind],
            "description": node.description,
            "created": node.created.strftime("%B %d, %H:%M"),
            "poignancy": node.poignancy,
        })
    return out


def _identity(scratch):
    return {
        "seed": getattr(scratch, "seed_currently", None) or getattr(scratch, "currently", ""),
        "currently": getattr(scratch, "currently", ""),
        "innate": getattr(scratch, "innate", ""),
        "learned": getattr(scratch, "learned", ""),
        "drift_log": list(getattr(scratch, "drift_log", []) or [])[-14:],
    }


def write_if_due(step, curr_time, personas):
    """
    Refresh every character's snapshot file if this step is on the cadence.
    Called once per step from the step loop; a no-op unless the flag is on and the step is a multiple
    of `snapshot_every`. Costs a handful of small file writes every five simulated minutes, and no
    model calls ever.
    """
    if not WORLD_SNAPSHOTS or step % SNAPSHOT_EVERY != 0:
        return None
    folder = f"{TEMP_STORAGE}/livetown"
    os.makedirs(folder, exist_ok=True)
    for name, persona in personas.items():
        scratch = persona.scratch
        snapshot = {
            "name": name,
            "step": step,
            "time": curr_time.strftime("%B %d, %Y, %H:%M:%S"),
            "world": step_payload(scratch),
            "relationships": dict(getattr(scratch, "relationships", None) or {}),
            "identity": _identity(scratch),
            "memories": _recent_memories(persona),
        }
        path = f"{folder}/{name.replace(' ', '_')}.json"
        sidecar = path + ".tmp"
        with open(sidecar, "w") as outfile:
            json.dump(snapshot, outfile)
        os.replace(sidecar, path)  # atomic on one filesystem: the browser sees old or new, never half
    return len(personas)


def config():
    return {"world_snapshots": WORLD_SNAPSHOTS, "snapshot_every": SNAPSHOT_EVERY}


def describe():
    if not enabled():
        return "snapshots: off (baseline)"
    return f"snapshots: viewer feed for every character each {SNAPSHOT_EVERY} steps"

"""
The town guardrails: bounded idle memories, and compact embedding files.
Both exist because nothing in this system deletes a memory and the store grows at ~1,020 nodes per
agent per simulated day, half of them "X is idle". The properties pinned here are the ones that keep
the guarantees of §4.0 intact: with the flags off, nothing changes at all, down to the bytes written;
with the dedup on, an object's idleness is remembered at most once per hour while a *person* standing
idle is never touched, because reactions can target a person's event and never an object idle.
"""

import datetime
import json
import types

import pytest
from memory_ext import longevity

NOW = datetime.datetime(2023, 2, 13, 12, 0, 0)
LATER = lambda minutes: NOW + datetime.timedelta(minutes=minutes)  # noqa: E731

COUNTER = ("the Ville:Hobbs Cafe:cafe:behind the cafe counter", "is", "idle")
KLAUS_IDLE = ("Klaus Mueller", "is", "idle")
REAL_EVENT = ("the Ville:Hobbs Cafe:cafe:behind the cafe counter", "is", "being wiped down")


def a_mem():
    return types.SimpleNamespace()


@pytest.fixture(autouse=True)
def flags_off(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", False)
    monkeypatch.setattr(longevity, "IDLE_DEDUP_TTL_HOURS", 1.0)
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", False)
    monkeypatch.setattr(longevity, "MEMORY_EVICTION", False)
    monkeypatch.setattr(longevity, "EVICTION_MAX_NODES", 10000)


# --- with the flags off, the baseline is untouched ---------------------------------------------------


def test_nothing_is_skipped_with_the_flag_off():
    mem = a_mem()
    for _ in range(5):
        assert longevity.skip_idle_store(mem, COUNTER, NOW) is False
    assert not hasattr(mem, "_idle_seen")  # not even the registry is created


def test_compact_returns_the_callers_own_dictionary_with_the_flag_off():
    """Identity, not equality: the baseline must write byte-identical files."""
    embeddings = {"a": [0.123456789012345]}
    assert longevity.compact(embeddings) is embeddings


def test_nothing_is_enabled_by_default():
    assert longevity.enabled() is False


# --- the dedup ---------------------------------------------------------------------------------------


def test_an_object_idle_is_stored_once_then_skipped_within_the_hour(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()

    assert longevity.skip_idle_store(mem, COUNTER, NOW) is False  # first sighting: store it
    assert longevity.skip_idle_store(mem, COUNTER, LATER(1)) is True  # spam: skip
    assert longevity.skip_idle_store(mem, COUNTER, LATER(59)) is True


def test_after_the_ttl_it_is_stored_again(monkeypatch):
    """Once per hour, not never: the reflection trigger and the perception window keep working."""
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()
    longevity.skip_idle_store(mem, COUNTER, NOW)

    assert longevity.skip_idle_store(mem, COUNTER, LATER(61)) is False
    assert longevity.skip_idle_store(mem, COUNTER, LATER(62)) is True  # and the window restarts


def test_a_person_standing_idle_is_never_deduplicated(monkeypatch):
    """
    `plan._choose_retrieved` can pick another persona's event for reaction whatever its description; its
    idle filter applies only to the second pass. Deduping person idles could change who reacts to whom.
    """
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()

    for _ in range(3):
        assert longevity.skip_idle_store(mem, KLAUS_IDLE, NOW) is False


def test_a_real_event_about_the_same_object_is_never_touched(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()
    longevity.skip_idle_store(mem, COUNTER, NOW)

    for _ in range(3):
        assert longevity.skip_idle_store(mem, REAL_EVENT, LATER(1)) is False


def test_each_object_has_its_own_clock(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()
    table = ("the Ville:Oak Hill College:library:library table", "is", "idle")

    assert longevity.skip_idle_store(mem, COUNTER, NOW) is False
    assert longevity.skip_idle_store(mem, table, LATER(1)) is False  # different object: store
    assert longevity.skip_idle_store(mem, COUNTER, LATER(2)) is True


def test_a_missing_clock_never_skips(monkeypatch):
    """A fresh fork's first tick has no time yet; dropping memories blind would be worse than spam."""
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    assert longevity.skip_idle_store(a_mem(), COUNTER, None) is False


def test_the_registry_lives_on_the_memory_not_the_module(monkeypatch):
    """Two agents watching the same counter must not share a clock."""
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    isabella, klaus = a_mem(), a_mem()

    longevity.skip_idle_store(isabella, COUNTER, NOW)
    assert longevity.skip_idle_store(klaus, COUNTER, LATER(1)) is False


# --- compact embeddings ------------------------------------------------------------------------------


def test_vectors_are_rounded_to_six_decimals(monkeypatch):
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    out = longevity.compact({"a": [0.123456789, -0.000000123]})

    assert out["a"] == [0.123457, -0.0]


def test_rounding_is_within_float32_noise(monkeypatch):
    """The model computed these in float32; six decimals discards verbosity, not information."""
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    vector = [0.07423911988735199, -0.6812345981597900, 0.0001234567]
    out = longevity.compact({"a": vector})["a"]

    assert all(abs(a - b) < 1e-6 for a, b in zip(vector, out))


def test_the_written_file_gets_meaningfully_smaller(monkeypatch):
    import random

    random.seed(0)
    embeddings = {f"memory {i}": [random.uniform(-1, 1) for _ in range(384)] for i in range(20)}

    full = len(json.dumps(embeddings))
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    small = len(json.dumps(longevity.compact(embeddings)))

    # Roughly half: a full-precision component is ~19 characters and a rounded one ~9, plus the
    # unchanging keys and punctuation around them.
    assert small < full * 0.6


def test_keys_and_order_are_preserved(monkeypatch):
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    embeddings = {"b": [0.1], "a": [0.2]}

    assert list(longevity.compact(embeddings)) == ["b", "a"]


# --- the condition is recorded -----------------------------------------------------------------------


def test_the_run_header_names_every_setting():
    assert set(longevity.config()) == {
        "idle_memory_dedup",
        "idle_dedup_ttl_hours",
        "compact_embeddings",
        "memory_eviction",
        "eviction_max_nodes",
    }


def test_the_description_says_what_is_on(monkeypatch):
    assert "baseline" in longevity.describe()
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    assert "once per 1h" in longevity.describe()


# --- eviction ----------------------------------------------------------------------------------------
# These use the real AssociativeMemory, because what eviction promises is structural: contiguous ids,
# intact filling links, rebuilt indexes, and a store that still saves and loads. A stub could not fail
# those promises, so it could not test them.

from persona.memory_structures.associative_memory import AssociativeMemory  # noqa: E402

MIDNIGHT = datetime.datetime(2023, 2, 16, 0, 0, 0)  # three days after NOW


def empty_store(tmp_path, name="assoc"):
    d = tmp_path / name
    d.mkdir()
    (d / "embeddings.json").write_text("{}")
    (d / "nodes.json").write_text("{}")
    (d / "kw_strength.json").write_text(json.dumps({"kw_strength_event": {}, "kw_strength_thought": {}}))
    return AssociativeMemory(str(d))


def add_events(mem, n, created=NOW, poignancy=4, prefix="thing"):
    nodes = []
    for i in range(n):
        nodes.append(
            mem.add_event(
                created,
                None,
                "Klaus Mueller",
                "is",
                f"doing {prefix} {i}",
                f"Klaus Mueller is doing {prefix} {i}",
                {prefix},
                poignancy,
                (f"emb {prefix} {i}", [0.1, 0.2]),
                [],
            )
        )
    return nodes


def eviction_on(monkeypatch, cap):
    monkeypatch.setattr(longevity, "MEMORY_EVICTION", True)
    monkeypatch.setattr(longevity, "EVICTION_MAX_NODES", cap)


def test_with_the_flag_off_nothing_is_ever_evicted(tmp_path):
    mem = empty_store(tmp_path)
    add_events(mem, 12)
    assert longevity.maybe_evict(mem, MIDNIGHT) is None
    assert len(mem.id_to_node) == 12


def test_under_the_cap_nothing_happens(tmp_path, monkeypatch):
    eviction_on(monkeypatch, cap=20)
    mem = empty_store(tmp_path)
    add_events(mem, 12)
    assert longevity.maybe_evict(mem, MIDNIGHT) is None
    assert len(mem.id_to_node) == 12


def test_over_the_cap_the_weakest_go_first_and_the_store_lands_at_ninety_percent(tmp_path, monkeypatch):
    eviction_on(monkeypatch, cap=10)
    mem = empty_store(tmp_path)
    add_events(mem, 3, poignancy=1, prefix="dull")  # same age throughout, so poignancy decides
    add_events(mem, 9, poignancy=8, prefix="vivid")

    record = longevity.maybe_evict(mem, MIDNIGHT)

    assert record["before"] == 12 and record["after"] == 9
    descriptions = {n.description for n in mem.id_to_node.values()}
    assert not any("dull" in d for d in descriptions)
    assert sum("vivid" in d for d in descriptions) == 9


def test_the_last_simulated_day_is_untouchable(tmp_path, monkeypatch):
    """However weak it scores, nothing from the last 24 hours goes: perception's novelty window,
    conversation context and today's plan all read recent memory and must never find it missing."""
    eviction_on(monkeypatch, cap=5)
    mem = empty_store(tmp_path)
    add_events(mem, 8, created=MIDNIGHT - datetime.timedelta(hours=6), poignancy=1)

    assert longevity.maybe_evict(mem, MIDNIGHT) is None
    assert len(mem.id_to_node) == 8


def test_cited_evidence_is_never_evicted_and_its_link_survives_the_renumbering(tmp_path, monkeypatch):
    eviction_on(monkeypatch, cap=10)
    mem = empty_store(tmp_path)
    dull = add_events(mem, 3, poignancy=1, prefix="dull")
    add_events(mem, 8, poignancy=8, prefix="vivid")
    mem.add_thought(
        NOW,
        None,
        "Klaus Mueller",
        "reflects on",
        "his dull work",
        "Klaus Mueller finds his repetitive work draining",
        {"reflection"},
        9,
        ("emb reflection", [0.3, 0.4]),
        [dull[0].node_id],
    )

    longevity.maybe_evict(mem, MIDNIGHT)

    reflection = [n for n in mem.id_to_node.values() if n.type == "thought"][0]
    cited = mem.id_to_node[reflection.filling[0]]
    assert cited.description == dull[0].description  # the evidence survived, and the link resolves
    assert sum("dull" in n.description for n in mem.id_to_node.values()) == 1


def test_the_rebuilt_store_still_saves_and_loads(tmp_path, monkeypatch):
    """The loader requires contiguous ids; this is the round trip that would explode if they were not."""
    eviction_on(monkeypatch, cap=10)
    mem = empty_store(tmp_path)
    add_events(mem, 3, poignancy=1, prefix="dull")
    nodes = add_events(mem, 9, poignancy=8, prefix="vivid")
    nodes[0].rehearsal_count = 5  # access history must survive the rebuild too

    longevity.maybe_evict(mem, MIDNIGHT)

    out = tmp_path / "saved"
    out.mkdir()
    mem.save(str(out))
    reloaded = AssociativeMemory(str(out))
    assert len(reloaded.id_to_node) == 9
    survivor = [n for n in reloaded.id_to_node.values() if n.description == nodes[0].description][0]
    assert json.load(open(out / "nodes.json"))[survivor.node_id]["rehearsal_count"] == 5


def test_embeddings_no_survivor_names_are_dropped(tmp_path, monkeypatch):
    eviction_on(monkeypatch, cap=10)
    mem = empty_store(tmp_path)
    add_events(mem, 3, poignancy=1, prefix="dull")
    add_events(mem, 9, poignancy=8, prefix="vivid")

    longevity.maybe_evict(mem, MIDNIGHT)

    assert not any("dull" in key for key in mem.embeddings)
    assert sum("vivid" in key for key in mem.embeddings) == 9


def test_keyword_strengths_forget_with_the_store(tmp_path, monkeypatch):
    eviction_on(monkeypatch, cap=10)
    mem = empty_store(tmp_path)
    add_events(mem, 3, poignancy=1, prefix="dull")
    add_events(mem, 9, poignancy=8, prefix="vivid")
    assert mem.kw_strength_event["dull"] == 3

    longevity.maybe_evict(mem, MIDNIGHT)

    assert "dull" not in mem.kw_strength_event
    assert mem.kw_strength_event["vivid"] == 9
